from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from fastapi import Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates


if TYPE_CHECKING:
    from tradingcat.app import TradingCatApplication


ROOT_DIR = Path(__file__).resolve().parents[2]
TEMPLATE_DIR = ROOT_DIR / "templates"
STATIC_DIR = ROOT_DIR / "static"
templates = Jinja2Templates(directory=str(TEMPLATE_DIR))


def get_app_state(request: Request) -> "TradingCatApplication":
    return request.app.state.app_state


def render_template(request: Request, name: str, **context: object) -> HTMLResponse:
    return templates.TemplateResponse(request, name, context)


def split_csv_param(raw: str | None) -> list[str] | None:
    if not raw:
        return None
    return [item.strip() for item in raw.split(",") if item.strip()]
