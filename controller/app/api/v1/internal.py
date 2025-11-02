# services/controller/app/api/v1/internal.py
"""
Internal API Endpoints - forwards WS ops to the WS process (/ocx/*)
and persists heartbeat into the DB so the DB is the source of truth.
"""
from __future__ import annotations
import os
import logging
from datetime import datetime
from typing import Dict, Any, Optional, List

from fastapi import APIRouter, HTTPException, Depends , Body
import httpx

from sqlalchemy import text, select, bindparam
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import JSONB

from collections import deque
import logging
import json

# Independence mode removed - now orchestrator-side concern
from fastapi import Query

from ...db.database import get_db
from ...models.organization import OrchestratorInstance
from ...models.orchestrator import OrchestratorConnection
from ...models.orchestrator_message import OrchestratorMessage
from ...controller_config import controller_config

log = logging.getLogger(__name__)
router = APIRouter(prefix="/internal", tags=["Internal"])

def _ok(message: str, **data: Any) -> Dict[str, Any]:
    out = {"success": True, "message": message, "timestamp": datetime.utcnow().isoformat()}
    out.update(data)
    return out

def _ws_base() -> str:
    host = os.getenv("CONTROLLER_OCS_HTTP_HOST", "localhost")
    port = os.getenv("CONTROLLER_OCS_HTTP_PORT", "8010")
    return f"http://{host}:{port}"


# ----- In-memory log buffer -----
_LOG_BUFFER_MAX = 2000
_LOG_BUFFER: deque[dict] = deque(maxlen=_LOG_BUFFER_MAX)

class _BufferHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = self.format(record) if self.formatter else record.getMessage()
            _LOG_BUFFER.append({
                "timestamp": datetime.utcfromtimestamp(record.created).isoformat() + "Z",
                "level": record.levelname,
                "message": msg,
                "source": record.name,
            })
        except Exception:
            # Never let logging crash the app
            pass

# Register the handler once
if not any(isinstance(h, _BufferHandler) for h in logging.getLogger().handlers):
    _buf_handler = _BufferHandler()
    # optional: pretty-ish format for file/console; buffer stores 'message' text anyway
    _buf_handler.setFormatter(logging.Formatter("%(message)s"))
    logging.getLogger().addHandler(_buf_handler)


# ---------- Health ----------
@router.get("/health")
async def internal_health():
    # Check if there are any active WebSocket connections
    ws = {"status": "down", "active_connections": 0}
    try:
        from ...utils.controller_state import list_orchestrators
        active_orchs = list_orchestrators(public=True)
        if active_orchs and len(active_orchs) > 0:
            ws["status"] = "ok"
            ws["active_connections"] = len(active_orchs)
        else:
            ws["status"] = "down"
            ws["active_connections"] = 0
    except Exception as e:
        ws["error"] = str(e)
        ws["status"] = "down"
    return _ok("Internal API healthy", service="controller-internal-api", ws=ws)

# ---------- Config-backed list (not live) ----------
@router.get("/orchestrators")
async def list_registered_orchestrators(
    organization_id: Optional[str] = None,
    status: Optional[str] = None
):
    cfg = controller_config.get_config()
    orgs = cfg.get("organizations", {})
    out: List[Dict[str, Any]] = []
    for org_id, data in orgs.items():
        if organization_id and organization_id != org_id:
            continue
        if status and data.get("status") != status:
            continue
        out.append({
            "orchestrator_id": f"orch-{org_id}",
            "organization_id": org_id,
            "name": data.get("name", org_id),
            "status": data.get("status", "inactive"),
            "health_status": "unknown",
            "internal_url": (data.get("metadata") or {}).get("internal_url"),
            "registered_at": data.get("last_seen"),
        })
    return {"success": True, "orchestrators": out, "total_count": len(out),
            "filters": {"organization_id": organization_id, "status": status}}

# ---------- LIVE (proxied from OCS HTTP: /ocx/orchestrators) ----------
@router.get("/orchestrators/live")
async def live_orchestrators():
    """
    Accepts either dict or list from OCS and normalizes to:
    { success, items:[{orchestrator_id,last_seen,status}], live_ids:[...] }
    """
    base = _ws_base()
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            r = await client.get(f"{base}/ocx/orchestrators")
        r.raise_for_status()
        raw = r.json() or {}

        items: List[Dict[str, Any]] = []
        if isinstance(raw, dict):
            for oid, payload in raw.items():
                payload = payload or {}
                items.append({
                    "orchestrator_id": oid,
                    "last_seen": payload.get("last_seen"),
                    "status": payload.get("status") or "active",
                })
        elif isinstance(raw, list):
            for x in raw:
                oid = x.get("orchestrator_id")
                if not oid:
                    continue
                items.append({
                    "orchestrator_id": oid,
                    "last_seen": x.get("last_seen"),
                    "status": x.get("status", "active"),
                })

        live_ids = [it["orchestrator_id"] for it in items if it.get("status") == "active"]
        return _ok("Live orchestrators retrieved", items=items, count=len(live_ids), live_ids=live_ids)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"WS query failed: {e}")

@router.get("/orchestrators/live/{orch_id}")
async def live_orchestrator(orch_id: str):
    base = _ws_base()
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            r = await client.get(f"{base}/ocx/orchestrators")
        r.raise_for_status()
        raw = r.json() or {}
        if isinstance(raw, dict):
            if orch_id in raw:
                payload = raw[orch_id] or {}
                return _ok("Live orchestrator retrieved", orchestrator={
                    "orchestrator_id": orch_id,
                    "last_seen": payload.get("last_seen"),
                    "status": payload.get("status") or "active",
                })
        elif isinstance(raw, list):
            for x in raw:
                if x.get("orchestrator_id") == orch_id:
                    return _ok("Live orchestrator retrieved", orchestrator=x)
        raise HTTPException(status_code=404, detail="Orchestrator not connected")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"WS query failed: {e}")

@router.get("/logs")
async def get_logs(
    q: str | None = Query(None, description="Search substring"),
    level: str | None = Query(None, description="DEBUG|INFO|WARNING|ERROR|CRITICAL"),
    limit: int = Query(200, ge=1, le=1000),
):
    """
    Returns recent in-memory logs (newest first).
    Filters by substring and/or level if provided.
    """
    lvl = (level or "").upper().strip()
    needle = (q or "").strip().lower()

    # Snapshot to avoid mutating while iterating
    data = list(_LOG_BUFFER)

    # Filter
    if lvl:
        data = [r for r in data if r.get("level", "").upper() == lvl]
    if needle:
        data = [r for r in data if needle in (r.get("message","").lower() + " " + r.get("source","").lower())]

    # Newest first
    data.sort(key=lambda r: r.get("timestamp",""), reverse=True)

    return {
        "success": True,
        "data": {
            "items": data[:limit],
            "total": len(data),
        }
    }


# ---------- Registration & heartbeats (DB is source of truth) ----------
@router.post("/orchestrators/register")
async def register_orchestrator(registration: Dict[str, Any], db: AsyncSession = Depends(get_db)):
    """
    Register orchestrator instance - aligned with orchestrator's approach.
    Each orchestrator instance represents one organization.
    """
    org_id = registration.get("organization_id")
    orch_id = registration.get("orchestrator_id") or f"orch-{org_id}"
    name = registration.get("name") or org_id or "unknown-org"
    
    if not org_id:
        raise HTTPException(400, "organization_id is required")

    # Create/update organization (unified schema)
    try:
        from ...models.organization import Organization
        from sqlalchemy.dialects.postgresql import insert as pg_insert
        
        res = await db.execute(select(Organization).where(Organization.org_id == org_id))
        org = res.scalars().first()
        
        features = registration.get("features", {})
        
        if org:
            # Update existing organization
            org.org_name = name
            org.location = registration.get("location", "unknown")
            org.features = features
            org.admin_email = registration.get("admin_email")
            org.support_email = registration.get("support_email")
            org.website = registration.get("website")
            org.updated_at = datetime.utcnow()
        else:
            # Create new organization
            org = Organization(
                org_id=org_id,
                org_name=name,
                orchestrator_id=org_id,
                status="inactive",  # Will become active on WebSocket connection
                keepalive_enabled=True,
                location=registration.get("location", "unknown"),
                features=features,
                admin_email=registration.get("admin_email"),
                support_email=registration.get("support_email"),
                website=registration.get("website"),
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )
            db.add(org)
        
        await db.commit()
        
        # Initialize statistics
        await db.execute(text("""
            INSERT INTO org_statistics (org_id)
            VALUES (:org_id)
            ON CONFLICT (org_id) DO NOTHING
        """), {"org_id": org_id})
        await db.commit()
        
        # Update config for backward compatibility (optional)
        try:
            cfg = controller_config.get_config()
            orgs = cfg.setdefault("organizations", {})
            orgs[org_id] = {
                "name": name,
                "location": registration.get("location", "unknown"),
                "metadata": registration.get("environment_variables") or {},
                "features": features,
                "last_seen": datetime.utcnow().isoformat(),
                "status": "inactive",
            }
            controller_config.update_config(cfg)
        except Exception as e:
            log.warning("Config update failed (non-critical): %s", e)

    except Exception as e:
        log.error("DB registration failed: %s", e)
        await db.rollback()
        raise HTTPException(500, f"Registration failed: {str(e)}")

    return _ok(
        "Organization registered (inactive until WebSocket connection)",
        orchestrator_id=org_id,
        organization_name=name,
        status=org.status,
        controller_endpoints={
            "heartbeat": "/api/v1/internal/orchestrators/heartbeat",
            "deregister": f"/api/v1/internal/orchestrators/{org_id}/deregister",
            "status": f"/api/v1/controller/orchestrator-instances/{org_id}",
        },
        note="Organization will become active when orchestrator connects via WebSocket"
    )

@router.post("/orchestrators/heartbeat")
async def orchestrator_heartbeat(heartbeat: Dict[str, Any], db: AsyncSession = Depends(get_db)):
    """
    Update orchestrator instance heartbeat - aligned with orchestrator's approach.
    Updates the orchestrator instance status and last_seen timestamp.
    """
    orch_id = heartbeat.get("orchestrator_id")
    org_id = heartbeat.get("organization_id") or orch_id  # Fallback to orch_id if org_id not provided
    
    if not orch_id:
        raise HTTPException(400, "orchestrator_id is required")

    now = datetime.utcnow()

    # Update organization (unified schema)
    try:
        from ...models.organization import Organization
        res = await db.execute(select(Organization).where(Organization.org_id == org_id))
        org = res.scalars().first()
        
        log.info("DEBUG: Looking for orchestrator %s, found org: %s", org_id, org is not None)
        
        if org:
            # Unconditional processing - no independence checks
            org.status = "active"
            org.last_seen = now
            org.updated_at = now
            
            # Update features if provided in heartbeat
            if "features" in heartbeat:
                current_features = org.features or {}
                current_features.update(heartbeat["features"])
                org.features = current_features
        else:
            # Create minimal org if missing (shouldn't happen with proper registration)
            org = Organization(
                org_id=org_id,
                org_name=heartbeat.get("name") or org_id,
                orchestrator_id=org_id,
                status="active",
                last_seen=now,
                keepalive_enabled=True,
                features=heartbeat.get("features", {}),
                created_at=now,
                updated_at=now
            )
            db.add(org)

        await db.commit()
        
        # Update config for backward compatibility (optional)
        try:
            cfg = controller_config.get_config()
            orgs = cfg.get("organizations", {})
            if org_id in orgs:
                orgs[org_id]["last_seen"] = now.isoformat()
                orgs[org_id]["status"] = "active"
                controller_config.update_config(cfg)
        except Exception:
            pass  # Non-critical

    except Exception as e:
        log.error("DB heartbeat update failed: %s", e)
        await db.rollback()
        raise HTTPException(500, f"Heartbeat update failed: {str(e)}")

    return _ok("Heartbeat stored", orchestrator_id=org_id, organization_name=instance.organization_name)

@router.delete("/orchestrators/{orchestrator_id}/deregister")
async def deregister_orchestrator(orchestrator_id: str, db: AsyncSession = Depends(get_db)):
    try:
        # Update database - mark as inactive (unified schema)
        await db.execute(
            text("""
                UPDATE organizations 
                SET status = 'inactive', updated_at = NOW()
                WHERE org_id = :orch_id
            """),
            {"orch_id": orchestrator_id}
        )
        await db.commit()
        
        # Update config for backward compatibility
        cfg = controller_config.get_config()
        orgs = cfg.get("organizations", {})
        org_id = orchestrator_id.replace("orch-", "")
        if org_id in orgs:
            orgs[org_id]["status"] = "inactive"
            controller_config.update_config(cfg)
    except Exception as e:
        log.warning("Deregister failed: %s", e)
        pass
    return _ok("Orchestrator deregistered", orchestrator_id=orchestrator_id, status="inactive")


# Independence endpoints removed - orchestrator-side concern now

# Orchestrator Message Endpoints
@router.post("/orchestrators/{orchestrator_id}/messages")
async def create_orchestrator_message(
    orchestrator_id: str,
    message_data: Dict[str, Any] = Body(default={}),
    db: AsyncSession = Depends(get_db)
):
    """
    Create a new message from orchestrator (recommendation or monitoring).
    """
    message_type = message_data.get("message_type", "monitoring")
    content = message_data.get("content", "")
    metadata = message_data.get("metadata", {})
    
    if not content:
        raise HTTPException(400, "Message content is required")
    
    if message_type not in ["recommendation", "monitoring"]:
        raise HTTPException(400, "Message type must be 'recommendation' or 'monitoring'")
    
    try:
        # Generate unique message ID
        message_id = f"msg_{orchestrator_id}_{int(datetime.utcnow().timestamp())}"
        
        message = OrchestratorMessage(
            id=message_id,
            orchestrator_id=orchestrator_id,
            message_type=message_type,
            content=content,
            message_metadata=metadata,
            status="pending",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        
        db.add(message)
        await db.commit()
        
        return _ok(
            "Message created successfully",
            message_id=message_id,
            orchestrator_id=orchestrator_id,
            message_type=message_type,
            status="pending"
        )
        
    except Exception as e:
        log.error("Failed to create message: %s", e)
        await db.rollback()
        raise HTTPException(500, f"Failed to create message: {str(e)}")

@router.get("/orchestrators/{orchestrator_id}/messages")
async def get_orchestrator_messages(
    orchestrator_id: str,
    message_type: Optional[str] = None,
    status: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    """
    Get messages from a specific orchestrator.
    """
    try:
        query = select(OrchestratorMessage).where(OrchestratorMessage.orchestrator_id == orchestrator_id)
        
        if message_type:
            query = query.where(OrchestratorMessage.message_type == message_type)
        if status:
            query = query.where(OrchestratorMessage.status == status)
            
        query = query.order_by(OrchestratorMessage.created_at.desc())
        
        result = await db.execute(query)
        messages = result.scalars().all()
        
        return _ok(
            "Messages retrieved successfully",
            orchestrator_id=orchestrator_id,
            messages=[msg.to_dict() for msg in messages],
            total_count=len(messages)
        )
        
    except Exception as e:
        log.error("Failed to get messages: %s", e)
        raise HTTPException(500, f"Failed to get messages: {str(e)}")

@router.put("/messages/{message_id}/status")
async def update_message_status(
    message_id: str,
    status_data: Dict[str, Any] = Body(default={}),
    db: AsyncSession = Depends(get_db)
):
    """
    Update message status (accept/dismiss).
    """
    new_status = status_data.get("status", "")
    
    if new_status not in ["accepted", "dismissed"]:
        raise HTTPException(400, "Status must be 'accepted' or 'dismissed'")
    
    try:
        result = await db.execute(select(OrchestratorMessage).where(OrchestratorMessage.id == message_id))
        message = result.scalars().first()
        
        if not message:
            raise HTTPException(404, f"Message {message_id} not found")
        
        message.status = new_status
        message.updated_at = datetime.utcnow()
        
        await db.commit()
        
        return _ok(
            f"Message {new_status} successfully",
            message_id=message_id,
            status=new_status,
            orchestrator_id=message.orchestrator_id
        )
        
    except HTTPException:
        raise
    except Exception as e:
        log.error("Failed to update message status: %s", e)
        await db.rollback()
        raise HTTPException(500, f"Failed to update message status: {str(e)}")

@router.get("/messages")
async def get_all_messages(
    message_type: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 100,
    db: AsyncSession = Depends(get_db)
):
    """
    Get all orchestrator messages across all orchestrators.
    """
    try:
        query = select(OrchestratorMessage)
        
        if message_type:
            query = query.where(OrchestratorMessage.message_type == message_type)
        if status:
            query = query.where(OrchestratorMessage.status == status)
            
        query = query.order_by(OrchestratorMessage.created_at.desc()).limit(limit)
        
        result = await db.execute(query)
        messages = result.scalars().all()
        
        return _ok(
            "All messages retrieved successfully",
            messages=[msg.to_dict() for msg in messages],
            total_count=len(messages)
        )
        
    except Exception as e:
        log.error("Failed to get all messages: %s", e)
        raise HTTPException(500, f"Failed to get all messages: {str(e)}")

# ──────────────────────────────────────────────────────────────────────────────
# Authentication Endpoints
# ──────────────────────────────────────────────────────────────────────────────
@router.post("/auth/login")
async def login(
    credentials: Dict[str, Any] = Body(default={}),
    db: AsyncSession = Depends(get_db)
):
    """
    Superadmin login endpoint.
    For now, uses dummy credentials: michelleprabhu / password123
    """
    username = credentials.get("username", "")
    password = credentials.get("password", "")
    
    # Dummy validation for now
    if username == "michelleprabhu" and password == "password123":
        return _ok(
            "Login successful",
            user={
                "username": username,
                "role": "superadmin",
                "token": "dummy-session-token-" + username
            }
        )
    else:
        raise HTTPException(401, "Invalid credentials")
