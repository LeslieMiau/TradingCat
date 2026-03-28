from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from tradingcat.services.risk import RiskViolation


logger = logging.getLogger(__name__)


async def _risk_violation_handler(_request: Request, exc: RiskViolation) -> JSONResponse:
    return JSONResponse(status_code=422, content={"ok": False, "error": str(exc), "code": "risk_violation"})


async def _value_error_handler(_request: Request, exc: ValueError) -> JSONResponse:
    return JSONResponse(status_code=400, content={"ok": False, "error": str(exc), "code": "bad_request"})


async def _generic_error_handler(_request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled application error")
    return JSONResponse(status_code=500, content={"ok": False, "error": str(exc), "code": "internal_error"})


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(RiskViolation, _risk_violation_handler)
    app.add_exception_handler(ValueError, _value_error_handler)
    app.add_exception_handler(Exception, _generic_error_handler)
