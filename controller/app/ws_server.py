# app/ws_server.py
from __future__ import annotations

# --- logging ---
import logging
logging.basicConfig(level=logging.INFO, format="[C-OCS] %(asctime)s %(levelname)s: %(message)s")
logger = logging.getLogger("c_ocs")

import ssl
import asyncio
import websockets
import json
import os
import copy
import time
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, Optional

# .env BEFORE any getenv usage
try:
    from dotenv import load_dotenv  # pip install python-dotenv
    load_dotenv()  # CWD
    _APP_ENV = Path(__file__).resolve().parent / ".env"
    if _APP_ENV.exists():
        load_dotenv(_APP_ENV, override=False)
    _ROOT_ENV = Path(__file__).resolve().parents[1] / ".env"
    if _ROOT_ENV.exists():
        load_dotenv(_ROOT_ENV, override=False)
except Exception:
    pass

# HTTP (optional internal API)
try:
    from fastapi import FastAPI
    import uvicorn
    _FASTAPI_OK = True
except Exception:
    _FASTAPI_OK = False

# -----------------------------------------------------------------------------
# Imports for config + utils
# -----------------------------------------------------------------------------
try:
    from app.controller_config import controller_config
    from app.utils.controller_state import remove_orchestrator, list_orchestrators
    from app.utils.dispatch import handle_handshake, dispatch_incoming
    from app.utils.buffer_manager import controller_buffers
    from app.utils.provisioning import send_provisioning_to
except Exception:
    from .controller_config import controller_config  # type: ignore
    from .utils.controller_state import remove_orchestrator, list_orchestrators  # type: ignore
    from .utils.dispatch import handle_handshake, dispatch_incoming  # type: ignore
    from .utils.buffer_manager import controller_buffers  # type: ignore
    from .utils.provisioning import send_provisioning_to  # type: ignore

# -----------------------------------------------------------------------------
# Env/config
# -----------------------------------------------------------------------------
def env_bool(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).lower() in ("1", "true", "yes", "on")

HOST = os.getenv("CONTROLLER_HOST", os.getenv("HOST", "0.0.0.0"))
PORT = int(os.getenv("CONTROLLER_PORT", os.getenv("PORT", "8765")))
OCS_HTTP_PORT = int(os.getenv("CONTROLLER_OCS_HTTP_PORT", "8010"))

# Limits / timeouts
MAX_MSG_SIZE = int(os.getenv("MAX_MSG_SIZE", str(2 * 1024 * 1024)))  # 2MB
MAX_QUEUE = int(os.getenv("MAX_QUEUE", "64"))
PING_INTERVAL = int(os.getenv("PING_INTERVAL", "20"))  # server control pings

# TLS 
BASE_DIR = Path(__file__).resolve().parent
DEFAULT_CERT_DIR = BASE_DIR / "certificates"

CERT_PATH = os.getenv("CERT_PATH")
if CERT_PATH:
    CERT_FILE = os.path.join(CERT_PATH, "server_cert.pem")
    KEY_FILE = os.path.join(CERT_PATH, "server_key.pem")
    CA_FILE  = os.path.join(CERT_PATH, "ca_cert.pem")
else:
    CERT_FILE = os.getenv("SSL_CERTFILE", str(DEFAULT_CERT_DIR / "server_cert.pem"))
    KEY_FILE  = os.getenv("SSL_KEYFILE", str(DEFAULT_CERT_DIR / "server_key.pem"))
    CA_FILE   = os.getenv("SSL_CAFILE",  str(DEFAULT_CERT_DIR / "ca.pem"))

SSL_DISABLED = env_bool("SSL_DISABLED", "true")

_last_sent_features: Dict[str, dict] = {}
_provisioning_guard: Dict[str, float] = {}

def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def build_ssl_context():
    if SSL_DISABLED:
        logger.info("[C-OCS] SSL disabled; serving ws:// (use a reverse proxy for TLS)")
        return None
    if not (os.path.exists(CERT_FILE) and os.path.exists(KEY_FILE)):
        logger.warning("[C-OCS] SSL certs missing; serving ws://")
        return None
    try:
        ctx = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
        ctx.load_cert_chain(certfile=CERT_FILE, keyfile=KEY_FILE)
        if os.path.exists(CA_FILE):
            ctx.load_verify_locations(CA_FILE)
            ctx.verify_mode = ssl.CERT_OPTIONAL
            logger.info("[C-OCS] CA loaded; client certs optional")
        else:
            ctx.verify_mode = ssl.CERT_NONE
        return ctx
    except Exception as e:
        logger.error(f"[C-OCS] Failed to create SSL context: {e}")
        return None

# -----------------------------------------------------------------------------
# Server heartbeat (app-level) 
# -----------------------------------------------------------------------------
async def controller_keepalive(ws, orch_id: str):
    try:
        while True:
            await asyncio.sleep(PING_INTERVAL)
            frame = {"type": "controller_heartbeat", "orch_id": orch_id, "ts": now_iso()}
            await ws.send(json.dumps(frame))
            logger.info(f"[C-OCS] controller_heartbeat → {orch_id}")
    except asyncio.CancelledError:
        pass
    except Exception as e:
        logger.warning(f"[C-OCS] controller_heartbeat error for {orch_id}: {e}")

# -----------------------------------------------------------------------------
# Dispatcher-driven handler
# -----------------------------------------------------------------------------
async def handler(ws):
    orch_id: Optional[str] = None
    keep_task: Optional[asyncio.Task] = None
    try:
        raw = await asyncio.wait_for(ws.recv(), timeout=15)
        handshake = json.loads(raw)
    except asyncio.TimeoutError:
        await ws.close(code=4000, reason="handshake_timeout"); return
    except Exception:
        await ws.close(code=4001, reason="handshake_recv_error"); return

    # Validate & register
    orch_id = await handle_handshake(ws, handshake, _last_sent_features)
    if not orch_id:
        return

    # Watcher won't race initial provisioning
    _provisioning_guard[orch_id] = time.time()

    # 1) ACK the handshake
    try:
        await ws.send(json.dumps({"type": "handshake_ack", "orch_id": orch_id, "ts": now_iso()}))
        logger.info(f"[C-OCS] handshake_ack → {orch_id}")
    except Exception as e:
        logger.warning(f"[C-OCS] failed sending handshake_ack to {orch_id}: {e}")
        await ws.close(code=4002, reason="handshake_ack_failed")
        return

    # 2) Initial provisioning 
    try:
        await send_provisioning_to(ws, orch_id, controller_config)
        cfg = controller_config.get_config()
        features = (cfg.get("orchestrator_instances", {}).get(orch_id, {}) or {}).get("features", {}) or {}
        _last_sent_features[orch_id] = copy.deepcopy(features)
        logger.info(f"[C-OCS] provisioning sent after handshake → {orch_id}")
    except Exception as e:
        logger.warning(f"[C-OCS] provisioning push failed for {orch_id}: {e}")
    finally:
        _provisioning_guard[orch_id] = time.time()

    # 3)  app-level heartbeat
    keep_task = asyncio.create_task(controller_keepalive(ws, orch_id))

    # 4) Normal message loop  (PATCH: bump last_seen on i_am_alive)
    try:
        async for raw in ws:
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                await ws.send(json.dumps({"type": "error", "reason": "invalid_json_in_stream"}))
                continue

            # NEW: update presence on keepalives so /ocx/orchestrators stays fresh
            try:
                if msg.get("type") == "i_am_alive" and orch_id:
                    # mutate the same internal map that list_orchestrators(public=True) reads
                    live_internal = list_orchestrators(public=False)
                    if orch_id in live_internal:
                        live_internal[orch_id]["last_seen"] = now_iso()
                    controller_buffers.add_activity("keepalive", {"orch_id": orch_id})
                    # no response needed for keepalive
                    continue
            except Exception as e:
                logger.warning(f"[C-OCS] keepalive update failed for {orch_id}: {e}")

            # default path: let dispatcher handle everything else
            await dispatch_incoming(ws, orch_id, msg, _last_sent_features)
    except asyncio.CancelledError:
        pass
    finally:
        if keep_task:
            keep_task.cancel()
        if orch_id:
            remove_orchestrator(orch_id)
            _last_sent_features.pop(orch_id, None)
            try:
                controller_config.unregister_orchestrator(orch_id)  # optional
            except Exception:
                pass
            logger.info(f"[C-OCS] Disconnected: {orch_id}")
            controller_buffers.add_activity("disconnect", {"orch_id": orch_id})

# -----------------------------------------------------------------------------
# Provisioning delta watcher
# -----------------------------------------------------------------------------
async def provisioning_watcher(interval_seconds: int = 2):
    SKIP_WINDOW_SEC = 10
    while True:
        try:
            try:
                controller_config.reload_config()  # type: ignore[attr-defined]
            except Exception:
                pass

            cfg = controller_config.get_config()
            instances = cfg.get("orchestrator_instances", {})

            for instance_id, info in list(list_orchestrators(public=False).items()):
                ws = info.get("ws")
                if ws is None:
                    continue

                # avoiding double send
                ts = _provisioning_guard.get(instance_id)
                if ts and (time.time() - ts) < SKIP_WINDOW_SEC:
                    continue

                instance_cfg = instances.get(instance_id, {})
                current_features = instance_cfg.get("features", {})
                last_features = _last_sent_features.get(instance_id)

                if last_features is None or current_features != last_features:
                    logger.info(f"[C-OCS] Feature delta for {instance_id} -> pushing provisioning")
                    try:
                        await send_provisioning_to(ws, instance_id, controller_config)
                        _last_sent_features[instance_id] = copy.deepcopy(current_features)
                        controller_buffers.add_activity(
                            "provisioning_sent",
                            {"instance_id": instance_id, "features": _last_sent_features[instance_id]},
                        )
                        _provisioning_guard[instance_id] = time.time()
                    except Exception as e:
                        logger.warning(f"[C-OCS] watcher provisioning failed for {instance_id}: {e}")
                        controller_buffers.add_activity("provisioning_error", {"instance_id": instance_id, "error": str(e)})
        except Exception as e:
            logger.warning(f"[C-OCS] watcher error: {e}")
        await asyncio.sleep(interval_seconds)

# -----------------------------------------------------------------------------
# Internal HTTP (for controller proxy)
# -----------------------------------------------------------------------------
if _FASTAPI_OK:
    http_app = FastAPI(title="C-OCS Internal")

    @http_app.get("/ocx/health")
    def ocx_health():
        return {"status": "ok", "now": now_iso()}

    @http_app.get("/ocx/activities")
    def ocx_activities(limit: int = 50, offset: int = 0):
        return controller_buffers.get_recent_activities(limit=limit, offset=offset)

    @http_app.get("/ocx/buffer_stats")
    def ocx_buffer_stats():
        return controller_buffers.get_stats()

    @http_app.get("/ocx/orchestrator-instances")
    def ocx_orchestrator_instances():
        live = list_orchestrators(public=True)
        cfg_instances = controller_config.get_config().get("orchestrator_instances", {})
        out = {}
        for instance_id, info in live.items():
            md = dict(info.get("metadata", {}))
            current = cfg_instances.get(instance_id, {}).get("features", {})
            if current:
                md["features"] = current
            out[instance_id] = {
                "last_seen": info.get("last_seen"),
                "metadata": md,
            }
        return out

    @http_app.post("/ocx/provision/{instance_id}")
    async def ocx_force_provision(instance_id: str):
        live = list_orchestrators(public=False)
        info = live.get(instance_id)
        if not info or "ws" not in info or info["ws"] is None:
            return {"ok": False, "error": "orchestrator instance not connected"}
        try:
            await send_provisioning_to(info["ws"], instance_id, controller_config)
            controller_buffers.add_activity("provisioning_forced_http", {"instance_id": instance_id})
            return {"ok": True}
        except Exception as e:
            controller_buffers.add_activity("provisioning_error_http", {"instance_id": instance_id, "error": str(e)})
            return {"ok": False, "error": str(e)}

    @http_app.get("/ocx/o_config/{instance_id}")
    def ocx_o_config(instance_id: str):
        try:
            controller_config.reload_config()  # type: ignore[attr-defined]
        except Exception:
            pass
        cfg = controller_config.get_config()
        instance = (cfg.get("orchestrator_instances") or {}).get(instance_id)
        if not instance:
            return {"error": "unknown instance_id"}
        snap = instance.get("o_config_snapshot")
        if not snap:
            return {"error": "no snapshot for this instance"}
        return snap

    async def start_http_server():
        config = uvicorn.Config(http_app, host="0.0.0.0", port=OCS_HTTP_PORT,
                                log_level="info", loop="asyncio")
        server = uvicorn.Server(config)
        await server.serve()
else:
    async def start_http_server():
        logger.info("[C-OCS] FastAPI not installed; HTTP metrics disabled.")

# -----------------------------------------------------------------------------
# Entrypoint
# -----------------------------------------------------------------------------
async def main():
    asyncio.create_task(start_http_server())
    logger.info(f"[C-OCS] HTTP metrics on http://localhost:{OCS_HTTP_PORT}")

    ctx = build_ssl_context()
    protocol = "wss" if ctx else "ws"
    logger.info(f"[C-OCS] Starting WebSocket server on {protocol}://{HOST}:{PORT}")
    async with websockets.serve(
        handler,
        HOST,
        PORT,
        ssl=ctx,
        max_size=MAX_MSG_SIZE,
        max_queue=MAX_QUEUE,
        ping_interval=PING_INTERVAL,   # control pings (server → client)
        ping_timeout=PING_INTERVAL,
    ):
        asyncio.create_task(provisioning_watcher(2))
        await asyncio.Future()

if __name__ == "__main__":
    asyncio.run(main())
