from __future__ import annotations

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from tradingcat.api.auth import ApiKeyMiddleware
from tradingcat.api.error_handlers import register_error_handlers
from tradingcat.app import TradingCatApplication, lifespan
from tradingcat.routes import ROUTERS
from tradingcat.routes.common import STATIC_DIR


app_state = TradingCatApplication()

app = FastAPI(title="TradingCat V1 Control Panel", lifespan=lifespan)
app.state.app_state = app_state
app.add_middleware(ApiKeyMiddleware)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
register_error_handlers(app)

for router in ROUTERS:
    app.include_router(router)
