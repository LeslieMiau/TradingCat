"""Optional API-key authentication middleware.

When TRADINGCAT_API_KEY is set (non-empty), all HTTP requests must include
either:
  - Header: X-API-Key: <key>
  - Query parameter: ?api_key=<key>

When unset or empty, the middleware is a no-op (single-operator localhost mode).
Dashboard HTML pages are exempt so browsers can load the UI without a key.
Health/preflight endpoints are also exempt for monitoring tools.
"""
from __future__ import annotations

import hmac
import os
from collections.abc import Callable, Awaitable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

# Paths that never require auth (health checks, dashboard HTML pages)
_PUBLIC_PREFIXES = (
    "/preflight/",
    "/docs",
    "/openapi.json",
    "/static/",
)
_PUBLIC_EXACT = {
    "/dashboard",
    "/dashboard/",
}


def _is_public_path(path: str) -> bool:
    if path in _PUBLIC_EXACT:
        return True
    for prefix in _PUBLIC_PREFIXES:
        if path.startswith(prefix):
            return True
    # Dashboard sub-pages served as HTML (strategies, accounts, etc.)
    if path.startswith("/dashboard/") and not path.startswith("/dashboard/summary"):
        return True
    return False


class ApiKeyMiddleware(BaseHTTPMiddleware):
    """Reject requests without a valid API key (when configured)."""

    def __init__(self, app: Callable, api_key: str | None = None) -> None:
        super().__init__(app)
        self._api_key = api_key or os.getenv("TRADINGCAT_API_KEY", "")

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        # No key configured → pass through (localhost trust mode)
        if not self._api_key:
            return await call_next(request)

        # Public paths are always accessible
        if _is_public_path(request.url.path):
            return await call_next(request)

        # Check header or query param
        provided = request.headers.get("X-API-Key") or request.query_params.get("api_key") or ""
        if not provided or not hmac.compare_digest(provided, self._api_key):
            return JSONResponse(
                status_code=401,
                content={"detail": "Invalid or missing API key"},
            )

        return await call_next(request)
