# services/controller/app/main.py
from __future__ import annotations

import os
import logging
import asyncio
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse

# ──────────────────────────────────────────────────────────────────────────────
# .env loading
# ──────────────────────────────────────────────────────────────────────────────
try:
    from dotenv import load_dotenv

    here = os.path.dirname(__file__)
    # services/controller/.env
    load_dotenv(os.path.join(os.path.dirname(here), ".env"))
    # services/controller/app/.env
    load_dotenv(os.path.join(here, ".env"))
    # services/.env
    load_dotenv(os.path.join(os.path.dirname(os.path.dirname(here)), ".env"))
except Exception:
    pass

# ──────────────────────────────────────────────────────────────────────────────
# DB
# ──────────────────────────────────────────────────────────────────────────────
try:
    from .db.database import db_manager, init_db  # type: ignore
    _HAVE_DB = True
except Exception:
    class _DummyDB:
        async def test_connection(self) -> bool:
            return False

        async def close(self) -> None:
            return None

    async def init_db() -> None:
        return None

    db_manager = _DummyDB()  # type: ignore
    _HAVE_DB = False

# ──────────────────────────────────────────────────────────────────────────────
# Config singleton
# ──────────────────────────────────────────────────────────────────────────────
from .controller_config import controller_config

# ──────────────────────────────────────────────────────────────────────────────
# Heartbeat poker (WS → DB sync) — background task
# ──────────────────────────────────────────────────────────────────────────────
# The poker reads its own env (CONTROLLER_OCS_HTTP_HOST/PORT, CONTROLLER_SELF_BASE,
# HEARTBEAT_POKE_INTERVAL_SEC). We only need to start/stop it.
try:
    from .cron.heartbeat_poker import run_heartbeat_poker  # type: ignore
    _HAVE_POKER = True
except Exception:  # pragma: no cover
    run_heartbeat_poker = None  # type: ignore
    _HAVE_POKER = False

# ──────────────────────────────────────────────────────────────────────────────
# Settings
# ──────────────────────────────────────────────────────────────────────────────
class Settings:
    app_name = "MoolAI Controller Service"
    app_version = "1.0.0"
    description = "Central Management and Analytics for MoolAI Platform"

    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8765"))
    debug = os.getenv("DEBUG", "false").lower() == "true"
    reload = os.getenv("RELOAD", "false").lower() == "true"
    log_level = os.getenv("LOG_LEVEL", "INFO")

    allowed_origins = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", "http://localhost:8080,http://localhost:4173,http://127.0.0.1:8080,http://127.0.0.1:4173,*").split(",")]
    allowed_hosts = [h.strip() for h in os.getenv("ALLOWED_HOSTS", "*").split(",")]

    # Toggle the background heartbeat poker (enabled by default)
    heartbeat_poker_enabled = os.getenv("HEARTBEAT_POKER_ENABLED", "true").lower() != "false"

    # Helpful for logs
    ocs_host = os.getenv("CONTROLLER_OCS_HTTP_HOST", "localhost")
    ocs_port = os.getenv("CONTROLLER_OCS_HTTP_PORT", "8010")
    self_base = os.getenv("CONTROLLER_SELF_BASE", f"http://127.0.0.1:{os.getenv('PORT', '8765')}")
    poke_interval = os.getenv("HEARTBEAT_POKE_INTERVAL_SEC", "60")


settings = Settings()

# ──────────────────────────────────────────────────────────────────────────────
# Logging
# ──────────────────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="[%(asctime)s] %(levelname)s in %(module)s: %(message)s",
)
logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────────────
# FastAPI app
# ──────────────────────────────────────────────────────────────────────────────
app = FastAPI(
    title=settings.app_name,
    description=settings.description,
    version=settings.app_version,
    debug=settings.debug,
    docs_url="/docs",
    redoc_url="/redoc",
)

# ──────────────────────────────────────────────────────────────────────────────
# Middleware
# ──────────────────────────────────────────────────────────────────────────────
print(f"🔧 CORS Configuration:")
print(f"   Allowed Origins: {settings.allowed_origins}")
print(f"   Allowed Hosts: {settings.allowed_hosts}")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# Temporarily disable TrustedHostMiddleware to fix CORS issues
# if settings.allowed_hosts != ["*"]:
#     app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.allowed_hosts)

# ──────────────────────────────────────────────────────────────────────────────
# Routers
# ──────────────────────────────────────────────────────────────────────────────
# 1) Mount NEW v1 routers first (authoritative)
from .api.v1.controller import router as v1_controller_router
from .api.v1.internal import router as v1_internal_router

app.include_router(v1_controller_router, prefix="/api/v1")
app.include_router(v1_internal_router, prefix="/api/v1")

# 2) Mount legacy routers under /api/v1/legacy so they don't shadow new paths
try:
    from .api.routes_orgs import router as legacy_orgs_router  # type: ignore
    app.include_router(legacy_orgs_router, prefix="/api/v1/legacy")
except Exception:
    pass

try:
    from .api.routes_users import router as legacy_users_router  # type: ignore
    app.include_router(legacy_users_router, prefix="/api/v1/legacy")
except Exception:
    pass

try:
    from .api.routes_analytics import router as legacy_analytics_router  # type: ignore
    app.include_router(legacy_analytics_router, prefix="/api/v1/legacy")
except Exception:
    pass

# ──────────────────────────────────────────────────────────────────────────────
# Lifespan (startup/shutdown)
# ──────────────────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(_: FastAPI):
    logger.info("Starting %s v%s", settings.app_name, settings.app_version)

    # DB init (non-fatal in dev)
    try:
        ok = await db_manager.test_connection()  # type: ignore[attr-defined]
        if not ok:
            logger.warning("Database not available; continuing without DB.")
        await init_db()
    except Exception as e:
        logger.warning("DB init skipped/failed (dev-ok): %s", e)

    # Log registered paths to help debug 404s
    try:
        paths: List[str] = []
        for r in app.routes:
            p = getattr(r, "path", None)
            if p:
                paths.append(p)
        paths = sorted(set(paths))
        logger.info("Registered paths (%d): %s", len(paths), ", ".join(paths))
    except Exception:
        pass

    # ── Start heartbeat poker task (if available & enabled)
    app.state._hb_stop_evt = asyncio.Event()
    app.state._hb_task = None
    if settings.heartbeat_poker_enabled and _HAVE_POKER and run_heartbeat_poker:
        logger.info(
            "Launching heartbeat poker: OCS http://%s:%s -> SELF %s (interval=%ss)",
            settings.ocs_host, settings.ocs_port, settings.self_base, settings.poke_interval
        )
        app.state._hb_task = asyncio.create_task(run_heartbeat_poker(app.state._hb_stop_evt))
    else:
        logger.info(
            "Heartbeat poker disabled or unavailable "
            "(HEARTBEAT_POKER_ENABLED=%s, HAVE_POKER=%s)",
            settings.heartbeat_poker_enabled, _HAVE_POKER
        )

    # Hand control back to FastAPI
    yield

    # ── Shutdown: stop heartbeat poker
    try:
        if getattr(app.state, "_hb_stop_evt", None):
            app.state._hb_stop_evt.set()
        if getattr(app.state, "_hb_task", None):
            await app.state._hb_task  # wait for clean stop
    except Exception:
        pass

    # Close DB
    try:
        await db_manager.close()  # type: ignore[attr-defined]
    except Exception:
        pass

    logger.info("Shutdown complete")


# Attach lifespan AFTER definition (so FastAPI uses it)
app.router.lifespan_context = lifespan  # type: ignore[attr-defined]

# ──────────────────────────────────────────────────────────────────────────────
# Error handler
# ──────────────────────────────────────────────────────────────────────────────
@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    logger.error("Unhandled exception: %s", exc, exc_info=True)
    return JSONResponse(status_code=500, content={"success": False, "message": "Internal server error"})

# ──────────────────────────────────────────────────────────────────────────────
# Basics
# ──────────────────────────────────────────────────────────────────────────────
@app.get("/")
async def root() -> Dict[str, Any]:
    return {
        "service": settings.app_name,
        "version": settings.app_version,
        "status": "running",
        "docs": "/docs",
        "health": "/health",
        "api": "/api/v1",
    }


@app.get("/health")
async def health_check() -> Dict[str, Any]:
    status: Dict[str, Any] = {
        "status": "healthy",
        "service": settings.app_name,
        "version": settings.app_version,
        "components": {},
    }
    try:
        db_ok = await db_manager.test_connection()  # type: ignore[attr-defined]
        status["components"]["database"] = "connected" if db_ok else "disconnected"
        if not db_ok:
            status["status"] = "degraded"
    except Exception:
        status["components"]["database"] = "error"
        status["status"] = "degraded"
    try:
        cfg = controller_config.get_config()
        status["components"]["configuration"] = {
            "organizations": len((cfg or {}).get("organizations", {}))
        }
    except Exception:
        status["components"]["configuration"] = "error"
        status["status"] = "degraded"
    return status

# ──────────────────────────────────────────────────────────────────────────────
# WebSocket endpoint for orchestrator connections
# ──────────────────────────────────────────────────────────────────────────────
async def websocket_handler(websocket: WebSocket):
    """WebSocket endpoint for orchestrator connections (C-OCS)."""
    import json
    import time
    import copy
    from datetime import datetime, timezone
    from .models.organization import Organization, OrchestratorInstance
    
    # Import utilities - lazy import to avoid circular dependencies
    try:
        from .utils.controller_state import mark_handshake, mark_keepalive, remove_orchestrator, list_orchestrators
        from .utils.buffer_manager import controller_buffers
    except ImportError:
        # Fallback for development
        mark_handshake = mark_keepalive = remove_orchestrator = list_orchestrators = lambda *args, **kwargs: None
        controller_buffers = type('obj', (object,), {'add_activity': lambda *args, **kwargs: None})()
    
    def now_iso():
        return datetime.now(timezone.utc).isoformat()
    
    orch_id: Optional[str] = None
    keep_task: Optional[asyncio.Task] = None
    _last_sent_features: Dict[str, dict] = {}
    _provisioning_guard: Dict[str, float] = {}
    
    try:
        await websocket.accept()
        logger.info("[C-OCS] WebSocket connection accepted")
        
        # Wait for handshake
        try:
            raw = await asyncio.wait_for(websocket.receive_text(), timeout=15)
            handshake = json.loads(raw)
        except asyncio.TimeoutError:
            await websocket.close(code=1008, reason="handshake_timeout")
            return
        except Exception as e:
            logger.error("[C-OCS] Handshake error: %s", e)
            await websocket.close(code=1008, reason="handshake_error")
            return
        
        # Validate handshake
        if handshake.get("type") != "handshake":
            await websocket.close(code=1008, reason="invalid_handshake")
            return
        
        data = handshake.get("data") or {}
        orch_id = data.get("orchestrator_id")
        metadata = data.get("metadata") or {}
        
        if not orch_id:
            await websocket.close(code=1008, reason="missing_orchestrator_id")
            return
        
        # Register orchestrator in memory
        mark_handshake(orch_id, websocket, metadata)
        try:
            controller_config.register_orchestrator(
                orch_id,
                {
                    "name": metadata.get("name") or f"Organization {orch_id}",
                    "location": metadata.get("location") or "unknown",
                    "metadata": metadata,
                },
            )
        except Exception as e:
            logger.warning("[C-OCS] register_orchestrator error: %s", e)
        
        # Register in database (both orchestrator_instances AND organizations tables)
        try:
            from sqlalchemy import text
            org_name = metadata.get("name") or f"Organization {orch_id}"
            location = metadata.get("location") or "unknown"
            features = metadata.get("features", {})
            
            async with db_manager.get_session() as db:
                # 1. Insert/update orchestrator_instances
                from sqlalchemy.dialects.postgresql import insert
                stmt = insert(OrchestratorInstance).values(
                    orchestrator_id=orch_id,
                    organization_name=org_name,
                    location=location,
                    status='active',
                    health_status='healthy',
                    last_seen=datetime.utcnow(),
                    features=features,
                    created_at=datetime.utcnow(),
                    updated_at=datetime.utcnow()
                ).on_conflict_do_update(
                    index_elements=['orchestrator_id'],
                    set_=dict(
                        organization_name=org_name,
                        location=location,
                        status='active',
                        health_status='healthy',
                        last_seen=datetime.utcnow(),
                        features=features,
                        updated_at=datetime.utcnow()
                    )
                )
                await db.execute(stmt)
                
                # 2. Insert/update organizations table (for frontend Organizations page)
                settings = {
                    "location": location,
                    "features": features,
                    "metadata": metadata
                }
                stmt2 = insert(Organization).values(
                    organization_id=orch_id,
                    name=org_name,
                    location=location,
                    is_active=True,
                    settings=settings,
                    created_at=datetime.utcnow(),
                    updated_at=datetime.utcnow()
                ).on_conflict_do_update(
                    index_elements=['organization_id'],
                    set_=dict(
                        name=org_name,
                        location=location,
                        is_active=True,
                        settings=settings,
                        updated_at=datetime.utcnow()
                    )
                )
                await db.execute(stmt2)
                
                await db.commit()
                logger.info("[C-OCS] DB: Registered %s in both tables", orch_id)
        except Exception as e:
            logger.warning("[C-OCS] DB registration failed: %s", e)
            import traceback
            logger.error(traceback.format_exc())
        
        logger.info("[C-OCS] Orchestrator %s connected", orch_id)
        controller_buffers.add_activity("handshake", {"orch_id": orch_id})
        
        # Send handshake_ack
        try:
            await websocket.send_text(json.dumps({"type": "handshake_ack", "orch_id": orch_id, "ts": now_iso()}))
            logger.info("[C-OCS] handshake_ack sent to %s", orch_id)
        except Exception as e:
            logger.warning("[C-OCS] Failed sending handshake_ack: %s", e)
            await websocket.close(code=1011, reason="handshake_ack_failed")
            return
        
        # Send initial provisioning
        _provisioning_guard[orch_id] = time.time()
        try:
            cfg = controller_config.get_config()
            orgs = cfg.get("organizations", {})
            org = orgs.get(orch_id)
            if org:
                msg = {
                    "type": "provisioning",
                    "data": {
                        "orchestrator_id": orch_id,
                        "features": org.get("features", {}),
                        "metadata": org.get("metadata", {}),
                        "name": org.get("name"),
                        "location": org.get("location"),
                    }
                }
                await websocket.send_text(json.dumps(msg))
                features = org.get("features", {}) or {}
                _last_sent_features[orch_id] = copy.deepcopy(features)
                logger.info("[C-OCS] Initial provisioning sent to %s", orch_id)
        except Exception as e:
            logger.warning("[C-OCS] provisioning push failed: %s", e)
        finally:
            _provisioning_guard[orch_id] = time.time()
        
        # Start keepalive task
        async def controller_keepalive():
            try:
                while True:
                    await asyncio.sleep(20)
                    frame = {"type": "controller_heartbeat", "orch_id": orch_id, "ts": now_iso()}
                    await websocket.send_text(json.dumps(frame))
                    logger.debug("[C-OCS] controller_heartbeat sent to %s", orch_id)
            except asyncio.CancelledError:
                pass
            except Exception as e:
                logger.warning("[C-OCS] keepalive error: %s", e)
        
        keep_task = asyncio.create_task(controller_keepalive())
        
        # Message loop
        try:
            while True:
                raw = await websocket.receive_text()
                try:
                    msg = json.loads(raw)
                except json.JSONDecodeError:
                    logger.warning("[C-OCS] Invalid JSON received")
                    continue
                
                mtype = msg.get("type")
                
                # Update presence on keepalives
                if mtype == "i_am_alive":
                    # Check if orchestrator is marked as independent
                    is_independent = False
                    try:
                        from sqlalchemy import text
                        async with db_manager.get_session() as db:
                            # Check independence status
                            independence_query = text("""
                                SELECT is_independent FROM orchestrator_instances 
                                WHERE orchestrator_id = :orch_id
                            """)
                            result = await db.execute(independence_query, {"orch_id": orch_id})
                            row = result.fetchone()
                            
                            if row and row[0]:  # is_independent = True
                                is_independent = True
                                logger.info("[C-OCS] Ignoring heartbeat from independent orchestrator %s", orch_id)
                                # Just ignore the heartbeat - don't update anything
                                continue
                    except Exception as e:
                        logger.debug("[C-OCS] Independence check failed: %s", e)
                    
                    # If we get here, the orchestrator is NOT independent - process the heartbeat
                    if not is_independent:
                        logger.info("[C-OCS] Processing heartbeat from orchestrator %s", orch_id)
                    
                    mark_keepalive(orch_id)
                    live_internal = list_orchestrators(public=False)
                    if orch_id in live_internal:
                        live_internal[orch_id]["last_seen"] = now_iso()
                    controller_buffers.add_activity("keepalive", {"orch_id": orch_id})
                    
                    # Update database heartbeat
                    try:
                        from sqlalchemy import text
                        async with db_manager.get_session() as db:
                            query = text("""
                                UPDATE orchestrator_instances 
                                SET last_seen = NOW(), 
                                    status = 'active',
                                    health_status = 'healthy',
                                    updated_at = NOW()
                                WHERE orchestrator_id = :orch_id
                            """)
                            await db.execute(query, {"orch_id": orch_id})
                            await db.commit()
                    except Exception as e:
                        logger.debug("[C-OCS] DB heartbeat update failed: %s", e)
                    
                    logger.debug("[C-OCS] keepalive from %s", orch_id)
                    continue
                
                # Handle other message types
                if mtype == "provisioning_request":
                    try:
                        cfg = controller_config.get_config()
                        orgs = cfg.get("organizations", {})
                        org = orgs.get(orch_id)
                        if org:
                            msg = {
                                "type": "provisioning",
                                "data": {
                                    "orchestrator_id": orch_id,
                                    "features": org.get("features", {}),
                                    "metadata": org.get("metadata", {}),
                                    "name": org.get("name"),
                                    "location": org.get("location"),
                                }
                            }
                            await websocket.send_text(json.dumps(msg))
                            logger.info("[C-OCS] Provisioning sent to %s (on request)", orch_id)
                    except Exception as e:
                        logger.warning("[C-OCS] provisioning_request failed: %s", e)
                
                elif mtype == "o_config_snapshot":
                    try:
                        cfg = controller_config.get_config()
                        orgs = cfg.setdefault("organizations", {})
                        org = orgs.setdefault(orch_id, {})
                        org["o_config_snapshot"] = {
                            "received_at": now_iso(),
                            "data": msg.get("data", {}) or {},
                        }
                        controller_config.update_config(cfg)
                        logger.info("[C-OCS] o_config_snapshot stored for %s", orch_id)
                    except Exception as e:
                        logger.warning("[C-OCS] o_config_snapshot store failed: %s", e)
                
                else:
                    logger.debug("[C-OCS] Message type %s from %s", mtype, orch_id)
                    controller_buffers.add_activity("message_rx", {"orch_id": orch_id, "type": mtype})
        
        except WebSocketDisconnect:
            logger.info("[C-OCS] Orchestrator %s disconnected", orch_id)
        except Exception as e:
            logger.error("[C-OCS] WebSocket error: %s", e)
        
    finally:
        if keep_task:
            keep_task.cancel()
            try:
                await keep_task
            except asyncio.CancelledError:
                pass
        if orch_id:
            remove_orchestrator(orch_id)
            _last_sent_features.pop(orch_id, None)
            _provisioning_guard.pop(orch_id, None)
            
            # Mark as inactive in database
            try:
                from sqlalchemy import text
                async with db_manager.get_session() as db:
                    query = text("""
                        UPDATE orchestrator_instances 
                        SET status = 'inactive', 
                            updated_at = NOW()
                        WHERE orchestrator_id = :orch_id
                    """)
                    await db.execute(query, {"orch_id": orch_id})
                    await db.commit()
            except Exception as e:
                logger.debug("[C-OCS] DB disconnect update failed: %s", e)
            
            logger.info("[C-OCS] Cleaned up connection for %s", orch_id)
            controller_buffers.add_activity("disconnect", {"orch_id": orch_id})

# Register WebSocket at both root and /ws paths for compatibility
@app.websocket("/")
async def websocket_root(websocket: WebSocket):
    await websocket_handler(websocket)

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket_handler(websocket)

# ──────────────────────────────────────────────────────────────────────────────
# Internal HTTP endpoint for heartbeat poker (replaces old ws_server endpoint)
# ──────────────────────────────────────────────────────────────────────────────
@app.get("/ocx/orchestrators")
async def ocx_orchestrators():
    """Return currently connected orchestrators for heartbeat poker."""
    from .utils.controller_state import list_orchestrators
    try:
        live = list_orchestrators(public=True)
        # Return in same format as old ws_server
        out = {}
        for orch_id, info in live.items():
            out[orch_id] = {
                "last_seen": info.get("last_seen"),
                "metadata": info.get("metadata", {}),
                "status": "active"
            }
        return out
    except Exception as e:
        logger.error(f"[OCX] Error fetching orchestrators: {e}")
        return {}

# ──────────────────────────────────────────────────────────────────────────────
# Local run helper
# ──────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "controller.app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.reload,
        log_level=settings.log_level.lower(),
    )
