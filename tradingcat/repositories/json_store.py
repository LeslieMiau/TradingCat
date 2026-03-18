from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class JsonStore:
    def __init__(self, path: Path) -> None:
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def load(self, default: Any) -> Any:
        if not self._path.exists():
            return default
        raw = self._path.read_text(encoding="utf-8").strip()
        if not raw:
            return default
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return default

    def save(self, payload: Any) -> None:
        self._path.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")
