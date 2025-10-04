# services/controller/app/api/v1/controller.py
from __future__ import annotations
import os
import logging
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any

from fastapi import APIRouter, Query, Path, Depends, HTTPException, Header
from pydantic import BaseModel
from sqlalchemy import text, bindparam
from sqlalchemy.dialects.postgresql import JSONB


# ──────────────────────────────────────────────────────────────────────────────
# DB (async) with safe fallback
# ──────────────────────────────────────────────────────────────────────────────
try:
    from ...db.database import get_db  # type: ignore
    from sqlalchemy.ext.asyncio import AsyncSession  # type: ignore
    _HAVE_DB = True
except Exception:  # pragma: no cover
    AsyncSession = object  # type: ignore
    async def get_db():  # type: ignore
        yield None
    _HAVE_DB = False

# Models (safe import) — imported for type hints / potential ORM use in future
try:
    from ...models.organization import OrchestratorInstance  # type: ignore
    from ...models.orchestrator import OrchestratorConnection  # type: ignore
except Exception:  # pragma: no cover
    OrchestratorInstance = None  # type: ignore
    OrchestratorConnection = None  # type: ignore

# Config singleton (still used for /organizations create + legacy fallbacks)
from ...controller_config import controller_config

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────────────
# Auth guard (dev bearer). If DEV_BEARER_TOKEN is unset → no auth required.
# ──────────────────────────────────────────────────────────────────────────────
_DEV_TOKEN = os.getenv("DEV_BEARER_TOKEN")

def _dev_auth(authorization: Optional[str] = Header(None)):
    if not _DEV_TOKEN:
        return  # auth disabled in dev if env not set
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    if authorization.split(" ", 1)[1] != _DEV_TOKEN:
        raise HTTPException(status_code=403, detail="Invalid token")

router = APIRouter(prefix="/controller", tags=["Controller"], dependencies=[Depends(_dev_auth)])

# ──────────────────────────────────────────────────────────────────────────────
# Schemas
# ──────────────────────────────────────────────────────────────────────────────
class APIResponse(BaseModel):
    success: bool
    data: Optional[Dict[str, Any]] = None
    message: str
    timestamp: str = datetime.utcnow().isoformat()

class PaginatedResponse(BaseModel):
    items: List[Dict[str, Any]]
    page: int
    page_size: int
    total_items: int
    total_pages: int
    has_next: bool
    has_prev: bool

class OrchestratorCreate(BaseModel):
    org_id: str
    name: str
    location: str
    metadata: dict = {}
    features: dict = {}

class FeatureUpdate(BaseModel):
    features: dict

# Heartbeat freshness window (seconds) used to compute active/inactive purely from DB
_HEARTBEAT_TTL_SEC = int(os.getenv("HEARTBEAT_TTL_SEC", "600"))

# ──────────────────────────────────────────────────────────────────────────────
# Health / simple analytics (stub)
# ──────────────────────────────────────────────────────────────────────────────
@router.get("/health")
async def get_controller_health():
    return {
        "status": "healthy",
        "service": "controller",
        "dependencies": {"database": "present" if _HAVE_DB else "absent", "config": "healthy"},
        "timestamp": datetime.utcnow().isoformat()
    }

@router.get("/overview")
async def get_overview(
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    refresh: bool = Query(False),
    db: AsyncSession = Depends(get_db)
):
    cfg = controller_config.get_config()
    org_count = len(cfg.get("organizations", {}))
    data = {
        "period": {
            "start": (start_date or datetime.utcnow() - timedelta(days=30)).isoformat(),
            "end":   (end_date or datetime.utcnow()).isoformat(),
        },
        "active_organizations": org_count,
        "total_cost": 1200.50,          # stub
        "total_requests": 250,          # stub
        "system_health": 98.5,          # stub
    }
    return APIResponse(success=True, data=data, message="System overview retrieved successfully")

@router.get("/costs")
async def get_costs(
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    granularity: str = Query("day", pattern="^(hour|day|week|month)$"),
    group_by: Optional[str] = Query(None, pattern="^(organization|model|provider|department)$"),
    organization_ids: Optional[str] = Query(None),
    include_forecast: bool = Query(False),
    db: AsyncSession = Depends(get_db)
):
    now = datetime.utcnow()
    if not start_date:
        start_date = now - timedelta(days=30)
    if not end_date:
        end_date = now

    days = max(1, (end_date.date() - start_date.date()).days)
    history = []
    base = 100.0
    for i in range(days + 1):
        d = (start_date + timedelta(days=i)).date().isoformat()
        val = base + i * 3.2 + ((i * 17) % 9) * 1.3
        history.append({"date": d, "cost": round(val, 2)})

    data = {
        "granularity": granularity,
        "forecast": {"end_of_month_cost": 385.75} if include_forecast else None,
        "history": history,
    }
    return APIResponse(success=True, data=data, message="Cost metrics retrieved successfully")

@router.get("/logs")
async def get_logs(
    page_size: int = Query(100, ge=1, le=1000),
    level: Optional[str] = Query(None, pattern="^(DEBUG|INFO|WARNING|ERROR|CRITICAL)$"),
    source: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db)
):
    """
    Get system logs - compatibility endpoint for frontend.
    Returns the same data as internal/logs but with controller naming.
    """
    # Simple stub implementation for now
    logs_data = [
        {
            "timestamp": "2025-09-24T17:50:00.000000Z",
            "level": "INFO",
            "message": "Controller service started",
            "source": "controller.app.main"
        },
        {
            "timestamp": "2025-09-24T17:49:30.000000Z",
            "level": "WARNING", 
            "message": "Heartbeat poker connection failed",
            "source": "controller.app.cron.heartbeat_poker"
        }
    ]
    
    return APIResponse(
        success=True,
        data={"items": logs_data, "total": len(logs_data)},
        message="System logs retrieved"
    )

# ──────────────────────────────────────────────────────────────────────────────
# Orchestrators — DB-only reads (status computed from last_heartbeat/last_seen_at)
# ──────────────────────────────────────────────────────────────────────────────
@router.get("/orchestrator-instances")
async def list_orchestrator_instances(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """
    List orchestrator instances - aligned with orchestrator's approach.
    Each instance represents one organization.
    """
    total = int((await db.execute(text("SELECT COUNT(*) FROM orchestrator_instances;"))).scalar() or 0)

    q = text(f"""
      SELECT
        orchestrator_id,
        organization_name,
        location,
        status,
        health_status,
        last_seen,
        features,
        session_config,
        is_independent,
        privacy_mode,
        internal_url,
        monitoring_enabled,
        created_at,
        updated_at
      FROM orchestrator_instances
      ORDER BY orchestrator_id
      OFFSET :off LIMIT :lim;
    """)
    rows = (await db.execute(q, {"off": (page - 1) * page_size, "lim": page_size})).mappings().all()

    items = [{
        "orchestrator_id": r["orchestrator_id"],
        "organization_name": r["organization_name"],
        "location": r["location"],
        "status": "independent" if r["is_independent"] else r["status"],  # Override status for independent orchestrators
        "health_status": r["health_status"],
        "last_seen": r["last_seen"].isoformat() if r["last_seen"] else None,
        "features": r["features"] or {},
        "session_config": r["session_config"] or {},
        "is_independent": r["is_independent"],
        "privacy_mode": r["privacy_mode"],
        "internal_url": r["internal_url"],
        "monitoring_enabled": r["monitoring_enabled"],
        "created_at": r["created_at"].isoformat() if r["created_at"] else None,
        "updated_at": r["updated_at"].isoformat() if r["updated_at"] else None,
    } for r in rows]

    resp = PaginatedResponse(
        items=items,
        page=page, page_size=page_size,
        total_items=total, total_pages=(total + page_size - 1)//page_size,
        has_next=page * page_size < total, has_prev=page > 1
    )
    return APIResponse(success=True, data=resp.dict(), message="Orchestrator instances retrieved")


@router.get("/orchestrators")
async def list_orchestrators(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """
    List orchestrators - compatibility endpoint for frontend.
    Returns the same data as orchestrator-instances but with orchestrator naming.
    """
    total = int((await db.execute(text("SELECT COUNT(*) FROM orchestrator_instances;"))).scalar() or 0)

    q = text(f"""
      SELECT
        orchestrator_id,
        organization_name,
        location,
        status,
        health_status,
        last_seen,
        features,
        session_config,
        is_independent,
        privacy_mode,
        internal_url,
        database_url,
        redis_url,
        container_id,
        image_name,
        environment_variables,
        phoenix_endpoint,
        monitoring_enabled,
        admin_email,
        support_email,
        website,
        created_at,
        updated_at,
        last_activity
      FROM orchestrator_instances
      ORDER BY created_at DESC
      LIMIT {page_size} OFFSET {(page - 1) * page_size}
    """)

    rows = (await db.execute(q)).mappings().all()
    items = [{
        "orchestrator_id": r["orchestrator_id"],
        "organization_id": r["orchestrator_id"],  # For dashboard compatibility
        "name": r["organization_name"],  # For dashboard compatibility
        "organization_name": r["organization_name"],
        "location": r["location"],
        "status": "independent" if r["is_independent"] else r["status"],  # Override status for independent orchestrators
        "health_status": r["health_status"],
        "last_seen": r["last_seen"].isoformat() if r["last_seen"] else None,
        "features": r["features"] or {},
        "session_config": r["session_config"] or {},
        "is_independent": r["is_independent"],
        "privacy_mode": r["privacy_mode"],
        "internal_url": r["internal_url"],
        "database_url": r["database_url"],
        "redis_url": r["redis_url"],
        "container_id": r["container_id"],
        "image_name": r["image_name"],
        "environment_variables": r["environment_variables"] or {},
        "phoenix_endpoint": r["phoenix_endpoint"],
        "monitoring_enabled": r["monitoring_enabled"],
        "admin_email": r["admin_email"],
        "support_email": r["support_email"],
        "website": r["website"],
        "created_at": r["created_at"].isoformat() if r["created_at"] else None,
        "updated_at": r["updated_at"].isoformat() if r["updated_at"] else None,
        "last_activity": r["last_activity"].isoformat() if r["last_activity"] else None,
    } for r in rows]

    resp = PaginatedResponse(
        items=items,
        page=page, page_size=page_size,
        total_items=total, total_pages=(total + page_size - 1)//page_size,
        has_next=page * page_size < total, has_prev=page > 1
    )
    return APIResponse(success=True, data=resp.dict(), message="Orchestrators retrieved")


@router.get("/orchestrator-instances/live")
async def get_live_orchestrator_instances(db: AsyncSession = Depends(get_db)):
    """
    Get live orchestrator instances - aligned with orchestrator's approach.
    Shows instances that are currently active and connected.
    """
    q = text(f"""
      SELECT
        orchestrator_id,
        organization_name,
        location,
        status,
        health_status,
        last_seen,
        features,
        session_config,
        is_independent,
        privacy_mode,
        internal_url,
        monitoring_enabled
      FROM orchestrator_instances
      WHERE status = 'active'
        AND last_seen IS NOT NULL
        AND NOW() - last_seen <= INTERVAL '{_HEARTBEAT_TTL_SEC} seconds';
    """)
    rows = (await db.execute(q)).mappings().all()

    live_map = {
        r["orchestrator_id"]: {
            "organization_name": r["organization_name"],
            "location": r["location"],
            "status": r["status"],
            "health_status": r["health_status"],
            "last_seen": r["last_seen"].isoformat() if r["last_seen"] else None,
            "features": r["features"] or {},
            "session_config": r["session_config"] or {},
            "is_independent": r["is_independent"],
            "privacy_mode": r["privacy_mode"],
            "internal_url": r["internal_url"],
            "monitoring_enabled": r["monitoring_enabled"],
        }
        for r in rows
    }
    return APIResponse(
        success=True,
        data={"orchestrator_instances": live_map, "total_count": len(live_map)},
        message="Live orchestrator instances retrieved"
    )

@router.get("/orchestrators/live")
async def get_live_orchestrators(db: AsyncSession = Depends(get_db)):
    """
    Get live orchestrators - compatibility endpoint for frontend.
    Returns the same data as orchestrator-instances/live but with orchestrator naming.
    """
    q = text(f"""
      SELECT
        orchestrator_id,
        organization_name,
        location,
        status,
        health_status,
        last_seen,
        features,
        session_config,
        is_independent,
        privacy_mode,
        internal_url,
        monitoring_enabled
      FROM orchestrator_instances
      WHERE status = 'active'
        AND last_seen IS NOT NULL
        AND NOW() - last_seen <= INTERVAL '{_HEARTBEAT_TTL_SEC} seconds';
    """)
    rows = (await db.execute(q)).mappings().all()

    live_map = {
        r["orchestrator_id"]: {
            "orchestrator_id": r["orchestrator_id"],
            "organization_id": r["orchestrator_id"],  # For frontend compatibility
            "organization_name": r["organization_name"],
            "name": r["organization_name"],
            "location": r["location"],
            "status": "independent" if r["is_independent"] else r["status"],  # Override status for independent orchestrators
            "health_status": r["health_status"],
            "last_seen": r["last_seen"].isoformat() if r["last_seen"] else None,
            "features": r["features"] or {},
            "session_config": r["session_config"] or {},
            "is_independent": r["is_independent"],
            "privacy_mode": r["privacy_mode"],
            "internal_url": r["internal_url"],
            "monitoring_enabled": r["monitoring_enabled"],
            "metadata": {
                "features": r["features"] or {}
            }
        }
        for r in rows
    }
    return APIResponse(
        success=True,
        data={"orchestrators": live_map, "total_count": len(live_map)},
        message="Live orchestrators retrieved"
    )

@router.get("/orchestrators/live/{orchestrator_id}")
async def get_live_orchestrator(orchestrator_id: str, db: AsyncSession = Depends(get_db)):
    q = text(f"""
      SELECT
        orchestrator_id,
        COALESCE(organization_id,'') AS organization_id,
        COALESCE(name, orchestrator_id) AS name,
        metadata,
        last_heartbeat,
        last_seen_at,
        CASE
          WHEN COALESCE(last_heartbeat, last_seen_at) IS NOT NULL
           AND NOW() - COALESCE(last_heartbeat, last_seen_at) <= INTERVAL '{_HEARTBEAT_TTL_SEC} seconds'
          THEN 'active'
          ELSE 'inactive'
        END AS status
      FROM orchestrators
      WHERE orchestrator_id = :oid;
    """)
    r = (await db.execute(q, {"oid": orchestrator_id})).mappings().first()
    if not r or r["status"] != "active":
        raise HTTPException(404, "Orchestrator not connected")

    data = {
        "organization_id": r["organization_id"],
        "orchestrator": {
            "orchestrator_id": r["orchestrator_id"],
            "name": r["name"],
            "status": r["status"],
            "last_seen": r["last_heartbeat"] or r["last_seen_at"],
            "metadata": r["metadata"] or {},
        }
    }
    return APIResponse(success=True, data=data, message="Live orchestrator from DB")

@router.get("/orchestrators/{orchestrator_id}")
async def get_orchestrator(orchestrator_id: str = Path(...), db: AsyncSession = Depends(get_db)):
    q = text(f"""
      SELECT
        orchestrator_id,
        COALESCE(organization_id,'') AS organization_id,
        COALESCE(name, orchestrator_id) AS name,
        metadata,
        last_heartbeat,
        last_seen_at,
        COALESCE(health_status,'unknown') AS health_status,
        CASE
          WHEN COALESCE(last_heartbeat, last_seen_at) IS NOT NULL
           AND NOW() - COALESCE(last_heartbeat, last_seen_at) <= INTERVAL '{_HEARTBEAT_TTL_SEC} seconds'
          THEN 'active'
          ELSE 'inactive'
        END AS status
      FROM orchestrators
      WHERE orchestrator_id = :oid;
    """)
    row = (await db.execute(q, {"oid": orchestrator_id})).mappings().first()
    if not row:
        raise HTTPException(404, f"Orchestrator {orchestrator_id} not found")

    data = {
        "orchestrator_id": row["orchestrator_id"],
        "organization_id": row["organization_id"],
        "name": row["name"],
        "status": row["status"],
        "health_status": row["health_status"],
        "last_seen": row["last_heartbeat"] or row["last_seen_at"],
        "metadata": row["metadata"] or {},
    }
    return APIResponse(success=True, data=data, message="Orchestrator details from DB")


# ──────────────────────────────────────────────────────────────────────────────
# Organizations — DB-first read (fallback to config on DB error only)
# ──────────────────────────────────────────────────────────────────────────────
@router.get("/organizations")
async def list_organizations(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db)
):
    try:
        total = int((await db.execute(text("SELECT COUNT(*) FROM organizations;"))).scalar() or 0)
        q = text("""
          SELECT
            organization_id,
            COALESCE(name, organization_id) AS name,
            COALESCE((settings->>'location'), 'unknown') AS location,
            COALESCE(is_active, false) AS is_active,
            settings
          FROM organizations
          ORDER BY organization_id
          OFFSET :off LIMIT :lim;
        """)
        rows = (await db.execute(q, {"off": (page - 1) * page_size, "lim": page_size})).mappings().all()

        items: List[Dict[str, Any]] = []
        for o in rows:
            settings = dict(o["settings"] or {})
            features = dict((settings.get("features") or {}))
            meta = dict((settings.get("metadata") or {}))
            location = o["location"] or meta.get("location") or "unknown"
            items.append({
                "organization_id": o["organization_id"],
                "name": o["name"],
                "location": location,
                "status": "active" if o["is_active"] else "inactive",
                "last_seen": None,
                "metadata": meta,
                "features": features,
            })

        resp = PaginatedResponse(
            items=items,
            page=page, page_size=page_size, total_items=total,
            total_pages=(total + page_size - 1)//page_size,
            has_next=page * page_size < total, has_prev=page > 1
        )
        return APIResponse(success=True, data=resp.dict(), message="Organizations retrieved from DB")
    except Exception as e:  # pragma: no cover
        logger.warning("DB read (list organizations) failed, falling back to config: %s", e)

    orgs = controller_config.get_config().get("organizations", {})
    items: List[Dict[str, Any]] = []
    for org_id, org in orgs.items():
        items.append({
            "organization_id": org_id,
            "name": org.get("name", org_id),
            "location": org.get("location", "unknown"),
            "status": org.get("status", "inactive"),
            "last_seen": org.get("last_seen"),
            "metadata": org.get("metadata", {}),
            "features": org.get("features", {}),
        })
    total = len(items)
    start = (page - 1) * page_size
    resp = PaginatedResponse(
        items=items[start:start+page_size],
        page=page, page_size=page_size, total_items=total,
        total_pages=(total + page_size - 1)//page_size,
        has_next=page * page_size < total, has_prev=page > 1
    )
    return APIResponse(success=True, data=resp.dict(), message="Organizations retrieved from config (fallback)")

@router.get("/organizations/{org_id}")
async def get_organization(org_id: str, db: AsyncSession = Depends(get_db)):
    """
    DB-first read:
    - status = 'active' iff ANY orchestrator for this org has a fresh heartbeat
    - last_seen = most recent of (last_heartbeat, last_seen_at) across the org
    Falls back to config only if DB access fails or org row is missing.
    """
    try:
        q = text(f"""
          WITH live_orchs AS (
            SELECT DISTINCT COALESCE(organization_id,'') AS organization_id
            FROM orchestrators
            WHERE COALESCE(last_heartbeat, last_seen_at) IS NOT NULL
              AND NOW() - COALESCE(last_heartbeat, last_seen_at)
                    <= INTERVAL '{_HEARTBEAT_TTL_SEC} seconds'
          ),
          agg_last_seen AS (
            SELECT
              COALESCE(organization_id,'') AS organization_id,
              MAX(COALESCE(last_heartbeat, last_seen_at)) AS last_seen
            FROM orchestrators
            GROUP BY COALESCE(organization_id,'')
          )
          SELECT
            o.organization_id,
            COALESCE(o.name, o.organization_id) AS name,
            COALESCE((o.settings->>'location'), 'unknown') AS location,
            CASE WHEN lo.organization_id IS NOT NULL THEN TRUE ELSE FALSE END AS is_live,
            al.last_seen,
            o.settings
          FROM organizations o
          LEFT JOIN live_orchs  lo USING (organization_id)
          LEFT JOIN agg_last_seen al USING (organization_id)
          WHERE o.organization_id = :oid;
        """)
        o = (await db.execute(q, {"oid": org_id})).mappings().first()
        if o:
            settings = dict(o["settings"] or {})
            features = dict((settings.get("features") or {}))
            meta     = dict((settings.get("metadata") or {}))
            location = o["location"] or meta.get("location") or "unknown"
            return APIResponse(
                success=True,
                data={
                    "organization_id": o["organization_id"],
                    "name": o["name"],
                    "location": location,
                    "status": "active" if o["is_live"] else "inactive",
                    "last_seen": o["last_seen"].isoformat() if o["last_seen"] else None,
                    "metadata": meta,
                    "features": features,
                },
                message="Organization from DB (status = liveness)",
            )
    except Exception as e:  # pragma: no cover
        logger.warning("DB read (get organization) failed, falling back to config: %s", e)

    # Fallback to config (legacy)
    orgs = controller_config.get_config().get("organizations", {})
    if org_id not in orgs:
        raise HTTPException(404, "Organization not found")
    org = orgs[org_id]
    return APIResponse(
        success=True,
        data={
            "organization_id": org_id,
            "name": org.get("name", org_id),
            "location": org.get("location", "unknown"),
            "status": org.get("status", "inactive"),
            "last_seen": org.get("last_seen"),
            "metadata": org.get("metadata", {}),
            "features": org.get("features", {}),
        },
        message="Organization from config (fallback)",
    )

@router.post("/organizations")
async def create_organization(org_data: OrchestratorCreate, db: AsyncSession = Depends(get_db)):
    """
    Create a new organization in the database.
    """
    try:
        # Check if organization already exists
        existing = await db.execute(
            text("SELECT organization_id FROM organizations WHERE organization_id = :org_id"),
            {"org_id": org_data.org_id}
        )
        if existing.fetchone():
            raise HTTPException(400, f"Organization {org_data.org_id} already exists")

        # Create organization
        from ..models.organization import Organization
        from sqlalchemy.dialects.postgresql import insert
        
        settings = {
            "location": org_data.location,
            "features": org_data.features or {},
            "metadata": org_data.metadata or {}
        }
        
        stmt = insert(Organization).values(
            organization_id=org_data.org_id,
            name=org_data.name,
            location=org_data.location,
            is_active=True,
            settings=settings,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        
        await db.execute(stmt)
        await db.commit()
        
        return APIResponse(
            success=True,
            data={
                "organization_id": org_data.org_id,
                "name": org_data.name,
                "location": org_data.location,
                "is_active": True
            },
            message=f"Organization {org_data.org_id} created successfully"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Failed to create organization: {e}")
        raise HTTPException(500, f"Failed to create organization: {str(e)}")

@router.post("/orchestrator-instances")
async def create_orchestrator_instance(instance_data: OrchestratorCreate, db: AsyncSession = Depends(get_db)):
    """
    Create orchestrator instance - aligned with orchestrator's approach.
    Each instance represents one organization.
    """
    try:
        # Check if instance already exists
        existing = await db.execute(
            text("SELECT orchestrator_id FROM orchestrator_instances WHERE orchestrator_id = :org_id"),
            {"org_id": instance_data.org_id}
        )
        if existing.fetchone():
            raise HTTPException(400, f"Orchestrator instance {instance_data.org_id} already exists")

        # Create new orchestrator instance
        insert_query = text("""
            INSERT INTO orchestrator_instances (
                orchestrator_id, organization_name, location, status, health_status,
                features, session_config, is_independent, privacy_mode,
                monitoring_enabled, created_at, updated_at
            ) VALUES (
                :org_id, :name, :location, 'inactive', 'unknown',
                :features, :session_config, :is_independent, :privacy_mode,
                :monitoring_enabled, NOW(), NOW()
            )
        """)
        
        await db.execute(insert_query, {
            "org_id": instance_data.org_id,
            "name": instance_data.name,
            "location": instance_data.location,
            "features": instance_data.features or {},
            "session_config": {},
            "is_independent": False,  # Default to managed by controller
            "privacy_mode": False,    # Default to visible to controller
            "monitoring_enabled": True
        })
        
        await db.commit()
        
        return APIResponse(
            success=True,
            data={
                "orchestrator_id": instance_data.org_id,
                "organization_name": instance_data.name,
                "location": instance_data.location,
                "status": "inactive",
                "is_independent": False,
                "privacy_mode": False
            },
            message=f"Orchestrator instance {instance_data.org_id} created successfully"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Failed to create orchestrator instance: {e}")
        raise HTTPException(500, f"Failed to create orchestrator instance: {str(e)}")

@router.delete("/orchestrator-instances/{orchestrator_id}")
async def delete_orchestrator_instance(orchestrator_id: str, db: AsyncSession = Depends(get_db)):
    """
    Delete orchestrator instance - aligned with orchestrator's approach.
    """
    try:
        # Check if instance exists
        existing = await db.execute(
            text("SELECT organization_name FROM orchestrator_instances WHERE orchestrator_id = :org_id"),
            {"org_id": orchestrator_id}
        )
        instance = existing.fetchone()
        if not instance:
            raise HTTPException(404, f"Orchestrator instance {orchestrator_id} not found")

        # Delete the instance
        delete_query = text("DELETE FROM orchestrator_instances WHERE orchestrator_id = :org_id")
        await db.execute(delete_query, {"org_id": orchestrator_id})
        await db.commit()
        
        return APIResponse(
            success=True,
            data={"orchestrator_id": orchestrator_id, "organization_name": instance[0]},
            message=f"Orchestrator instance {orchestrator_id} deleted successfully"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Failed to delete orchestrator instance: {e}")
        raise HTTPException(500, f"Failed to delete orchestrator instance: {str(e)}")

@router.put("/organizations/{org_id}/features")
async def update_organization_features(org_id: str, update: FeatureUpdate, db: AsyncSession = Depends(get_db)):
    # 1) Update config (legacy compatibility)
    cfg = controller_config.get_config()
    orgs = cfg.setdefault("organizations", {})
    if org_id not in orgs:
        raise HTTPException(404, "Organization not found in config")
    org = orgs[org_id]
    if "features" not in org or not isinstance(org["features"], dict):
        org["features"] = {}
    org["features"].update(update.features or {})
    controller_config.update_config(cfg)

    # 2) Dual-write to DB (non-fatal)
    try:
        merge = text("""
          UPDATE organizations
             SET settings = jsonb_set(
                  COALESCE(settings, '{}'::jsonb),
                  '{features}',
                  COALESCE(settings->'features', '{}'::jsonb) || :features::jsonb,
                  true
                )
           WHERE organization_id = :oid;
        """)
        await db.execute(merge, {"oid": org_id, "features": update.features or {}})
        await db.commit()
    except Exception as e:  # pragma: no cover
        logger.warning("DB dual-write (update features) failed: %s", e)

    return APIResponse(success=True, data={"organization_id": org_id, "features": orgs[org_id]["features"]}, message=f"Features updated for organization {org_id}")
