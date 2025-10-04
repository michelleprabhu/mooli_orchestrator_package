# services/controller/app/cron/heartbeat_poker.py
from __future__ import annotations
import os
import asyncio
import logging
from typing import Dict, Any

import httpx

log = logging.getLogger(__name__)

OCS_HOST = os.getenv("CONTROLLER_OCS_HTTP_HOST", "localhost")
OCS_PORT = os.getenv("CONTROLLER_OCS_HTTP_PORT", "8010")
OCS_BASE = f"http://{OCS_HOST}:{OCS_PORT}"

# Where this controller is listening (loopback)
SELF_BASE = os.getenv("CONTROLLER_SELF_BASE", "http://127.0.0.1:8765")

# How often to sync heartbeats from WS → DB
POKE_INTERVAL_SEC = int(os.getenv("HEARTBEAT_POKE_INTERVAL_SEC", "60"))

async def _fetch_live_map(client: httpx.AsyncClient) -> Dict[str, Any]:
    """
    Calls WS HTTP to discover currently connected orchestrators.
    Supports both dict and list shapes, returns dict[str, payload].
    """
    try:
        r = await client.get(f"{OCS_BASE}/ocx/orchestrators", timeout=3.0)
        r.raise_for_status()
        raw = r.json() or {}
        if isinstance(raw, dict):
            return raw
        if isinstance(raw, list):
            out: Dict[str, Any] = {}
            for x in raw:
                oid = x.get("orchestrator_id")
                if oid:
                    out[oid] = x
            return out
    except Exception as e:
        log.warning("heartbeat_poker: fetch /ocx/orchestrators failed: %s", e)
    return {}

async def _post_heartbeat(client: httpx.AsyncClient, orch_id: str, org_id: str | None = None) -> None:
    try:
        payload = {"orchestrator_id": orch_id}
        if org_id:
            payload["organization_id"] = org_id
        r = await client.post(
            f"{SELF_BASE}/api/v1/internal/orchestrators/heartbeat",
            json=payload,
            timeout=3.0,
        )
        # 2xx only; log non-2xx
        if r.status_code // 100 != 2:
            log.warning("heartbeat_poker: POST heartbeat %s -> http_%s body=%s",
                        orch_id, r.status_code, r.text[:200])
    except Exception as e:
        log.warning("heartbeat_poker: POST heartbeat %s failed: %s", orch_id, e)

async def run_heartbeat_poker(stop_evt: asyncio.Event) -> None:
    """
    Periodically:
      - fetch live orchestrators via WS HTTP
      - for each ID, POST internal heartbeat (which writes to DB)
    """
    log.info("heartbeat_poker: starting; OCS_BASE=%s SELF_BASE=%s interval=%ss",
             OCS_BASE, SELF_BASE, POKE_INTERVAL_SEC)
    async with httpx.AsyncClient() as client:
        while not stop_evt.is_set():
            live = await _fetch_live_map(client)
            if live:
                for orch_id, payload in live.items():
                    org_id = None
                    # Try to infer org id field names commonly used:
                    org_id = payload.get("organization_id") or payload.get("org_id") or None
                    await _post_heartbeat(client, orch_id, org_id)
            else:
                log.debug("heartbeat_poker: no live orchestrators reported by WS")

            try:
                await asyncio.wait_for(stop_evt.wait(), timeout=POKE_INTERVAL_SEC)
            except asyncio.TimeoutError:
                # normal tick
                pass

    log.info("heartbeat_poker: stopped")
