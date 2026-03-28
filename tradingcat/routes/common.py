from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from fastapi import Request
from fastapi.responses import HTMLResponse


if TYPE_CHECKING:
    from tradingcat.app import TradingCatApplication


ROOT_DIR = Path(__file__).resolve().parents[2]
TEMPLATE_DIR = ROOT_DIR / "templates"
STATIC_DIR = ROOT_DIR / "static"


def get_app_state(request: Request) -> "TradingCatApplication":
    return request.app.state.app_state


def read_template(name: str) -> HTMLResponse:
    return HTMLResponse((TEMPLATE_DIR / name).read_text(encoding="utf-8"))


def split_csv_param(raw: str | None) -> list[str] | None:
    if not raw:
        return None
    return [item.strip() for item in raw.split(",") if item.strip()]

