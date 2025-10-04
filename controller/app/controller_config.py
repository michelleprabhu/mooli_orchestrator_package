from __future__ import annotations
import json, os, threading
from pathlib import Path
from copy import deepcopy
from typing import Dict, Any

# Default: app/db/controller_config.json (override via CONTROLLER_CONFIG_PATH in .env)
_DEFAULT_DIR = Path(__file__).resolve().parent / "db"
_DEFAULT_DIR.mkdir(exist_ok=True)
_DEFAULT_PATH = _DEFAULT_DIR / "controller_config.json"
_CONFIG_PATH = Path(os.getenv("CONTROLLER_CONFIG_PATH", str(_DEFAULT_PATH)))

class _ControllerConfig:
    def __init__(self, path: Path):
        self._path = path
        self._lock = threading.RLock()
        if not self._path.exists():
            self._write({"organizations": {}})

    def _read(self) -> Dict[str, Any]:
        if not self._path.exists():
            return {"organizations": {}}
        with self._path.open("r", encoding="utf-8") as f:
            return json.load(f)

    def _write(self, cfg: Dict[str, Any]) -> None:
        tmp = self._path.with_suffix(".tmp")
        with tmp.open("w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
        tmp.replace(self._path)

    # --- Public API used by dispatch.py ---
    def get_config(self) -> Dict[str, Any]:
        with self._lock:
            return deepcopy(self._read())

    def update_config(self, cfg: Dict[str, Any]) -> None:
        with self._lock:
            self._write(cfg)

    def register_orchestrator(self, orch_id: str, org_info: Dict[str, Any]) -> None:
        with self._lock:
            cfg = self._read()
            orgs = cfg.setdefault("organizations", {})
            existing = orgs.get(orch_id, {})
            existing.update(org_info or {})
            orgs[orch_id] = existing
            self._write(cfg)

controller_config = _ControllerConfig(_CONFIG_PATH)
