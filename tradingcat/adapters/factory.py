from __future__ import annotations

import logging
import socket
import time
from contextlib import suppress
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from typing import Callable, TypeVar

logger = logging.getLogger(__name__)

from tradingcat.adapters.broker import ManualExecutionAdapter, SimulatedBrokerAdapter
from tradingcat.adapters.cn.akshare import AKSHARE_AVAILABLE, AkshareMarketDataAdapter, AkshareUnavailable
from tradingcat.adapters.cn.baostock import BAOSTOCK_AVAILABLE, BaostockMarketDataAdapter, BaostockUnavailable
from tradingcat.adapters.cn.tushare import TUSHARE_AVAILABLE, TushareMarketDataAdapter, TushareUnavailable
from tradingcat.adapters.composite import CompositeMarketDataAdapter
from tradingcat.adapters.market import StaticMarketDataAdapter
from tradingcat.adapters.futu import FutuAdapterUnavailable, FutuBrokerAdapter, FutuMarketDataAdapter
from tradingcat.adapters.yfinance_adapter import YFinanceMarketDataAdapter
from tradingcat.config import AppConfig


T = TypeVar("T")


class AdapterFactory:
    _DIAGNOSTIC_CACHE_TTL_SECONDS = 2.0

    def __init__(self, config: AppConfig) -> None:
        self._config = config
        self._diagnostic_cache: dict[str, tuple[float, dict[str, object]]] = {}

    def _cached_diagnostic(self, cache_key: str, loader: Callable[[], dict[str, object]]) -> dict[str, object]:
        now = time.monotonic()
        cached = self._diagnostic_cache.get(cache_key)
        if cached is not None and now - cached[0] <= self._DIAGNOSTIC_CACHE_TTL_SECONDS:
            return cached[1]
        result = loader()
        self._diagnostic_cache[cache_key] = (now, result)
        return result

    def _futu_endpoint_issue(self) -> str | None:
        try:
            with socket.create_connection(
                (self._config.futu.host, self._config.futu.port),
                timeout=self._config.futu.probe_timeout_seconds,
            ):
                return None
        except OSError as exc:
            detail = exc.strerror or str(exc)
            return (
                "Futu OpenD is not reachable at "
                f"{self._config.futu.host}:{self._config.futu.port} ({detail})"
            )

    def _ensure_futu_endpoint(self) -> None:
        issue = self._futu_endpoint_issue()
        if issue is not None:
            raise FutuAdapterUnavailable(issue)

    def _simulated_broker_diagnostics(self, detail: str) -> dict[str, object]:
        return {"backend": "simulated", "healthy": True, "detail": detail}

    def _skipped_validation(self, detail: str) -> dict[str, object]:
        return {
            "backend": "futu",
            "healthy": True,
            "detail": "Futu validation skipped",
            "checks": {
                "quote": {"status": "skipped", "detail": detail},
                "trade": {"status": "skipped", "detail": detail},
            },
        }

    def _create_with_timeout(self, factory: Callable[[], T], timeout: float | None = None) -> T:
        if timeout is None:
            timeout = self._config.futu.adapter_init_timeout_seconds
        executor = ThreadPoolExecutor(max_workers=1)
        future = executor.submit(factory)
        try:
            return future.result(timeout=timeout)
        except FutureTimeoutError as exc:
            future.cancel()
            executor.shutdown(wait=False, cancel_futures=True)
            logger.exception("Futu adapter initialization timed out")
            raise FutuAdapterUnavailable(f"Futu adapter initialization timed out after {timeout:.1f}s") from exc
        except Exception:
            executor.shutdown(wait=True, cancel_futures=True)
            logger.exception("Futu adapter initialization failed")
            raise
        else:
            executor.shutdown(wait=True, cancel_futures=True)

    def create_market_data_adapter(self):
        adapter = None
        backend_name = "static"
        if self._config.futu.enabled:
            try:
                self._ensure_futu_endpoint()
                adapter = self._create_with_timeout(lambda: FutuMarketDataAdapter(self._config.futu))
                logger.info("Using Futu market data adapter")
                backend_name = "futu"
            except FutuAdapterUnavailable as exc:
                logger.warning("Futu market data unavailable, falling back: %s", exc)
        if adapter is None and self._config.yfinance.enabled:
            logger.info("Using YFinance market data adapter")
            adapter = YFinanceMarketDataAdapter()
            backend_name = "yfinance"
        if adapter is None:
            logger.info("Using Static (fallback) market data adapter")
            adapter = StaticMarketDataAdapter()

        cn_adapter = None
        cn_name: str | None = None

        # Priority: TuShare → AKShare → BaoStock
        if self._config.tushare.enabled and self._config.tushare.token:
            if not TUSHARE_AVAILABLE:
                logger.warning("TuShare enabled but SDK unavailable (pip install tushare)")
            else:
                try:
                    cn_adapter = TushareMarketDataAdapter(
                        token=self._config.tushare.token,
                        adj=self._config.tushare.adj,
                    )
                    cn_name = "TuShare"
                except TushareUnavailable as exc:
                    logger.warning("TuShare unavailable during initialization: %s", exc)

        if cn_adapter is None and self._config.akshare.enabled:
            if not AKSHARE_AVAILABLE:
                logger.warning("AKShare enabled but SDK is unavailable")
            else:
                try:
                    cn_adapter = AkshareMarketDataAdapter(
                        adjust=self._config.akshare.adjust,
                        spot_cache_ttl_seconds=self._config.akshare.spot_cache_ttl_seconds,
                    )
                    cn_name = "AKShare"
                except AkshareUnavailable as exc:
                    logger.warning("AKShare unavailable during initialization: %s", exc)

        if cn_adapter is None and self._config.baostock.enabled:
            if not BAOSTOCK_AVAILABLE:
                logger.warning("BaoStock enabled but SDK is unavailable")
            else:
                try:
                    cn_adapter = BaostockMarketDataAdapter(
                        adjustflag=self._config.baostock.adjustflag,
                    )
                    cn_name = "BaoStock"
                except BaostockUnavailable as exc:
                    logger.warning("BaoStock unavailable during initialization: %s", exc)

        if cn_adapter is not None:
            logger.info("Using composite market data adapter: CN->%s, US/HK->%s", cn_name, backend_name)
            return CompositeMarketDataAdapter(cn_inner=cn_adapter, us_hk_inner=adapter)
        return adapter

    def create_live_broker_adapter(self):
        if not self._config.futu.enabled:
            logger.info("Using Simulated broker (Futu disabled)")
            return SimulatedBrokerAdapter(self._config)
        try:
            self._ensure_futu_endpoint()
            adapter = self._create_with_timeout(lambda: FutuBrokerAdapter(self._config.futu))
            logger.info("Using Futu live broker adapter")
            return adapter
        except FutuAdapterUnavailable as exc:
            logger.warning("Futu broker unavailable, falling back to simulated: %s", exc)
            return SimulatedBrokerAdapter(self._config)

    def create_manual_broker_adapter(self):
        return ManualExecutionAdapter(self._config)

    def broker_backend_name(self) -> str:
        return self.broker_diagnostics()["backend"]

    def broker_diagnostics(self) -> dict[str, object]:
        if not self._config.futu.enabled:
            return self._simulated_broker_diagnostics("Futu integration disabled in config")

        def load() -> dict[str, object]:
            adapter = None
            try:
                self._ensure_futu_endpoint()
                adapter = self._create_with_timeout(lambda: FutuBrokerAdapter(self._config.futu))
                diagnostics = adapter.health_check()
                return {"backend": "futu", "healthy": diagnostics["healthy"], "detail": diagnostics["detail"]}
            except FutuAdapterUnavailable as exc:
                return self._simulated_broker_diagnostics(str(exc))
            except Exception as exc:
                logger.exception("Broker diagnostics failed")
                return {"backend": "futu", "healthy": False, "detail": str(exc)}
            finally:
                if adapter is not None:
                    with suppress(Exception):
                        adapter.close()

        return self._cached_diagnostic("broker_diagnostics", load)

    def validate_futu_connection(self) -> dict[str, object]:
        if not self._config.futu.enabled:
            return {
                "backend": "simulated",
                "healthy": True,
                "detail": "Futu integration disabled in config",
                "checks": {
                    "quote": {"status": "skipped", "detail": "Futu integration disabled in config"},
                    "trade": {"status": "skipped", "detail": "Futu integration disabled in config"},
                },
            }

        def load() -> dict[str, object]:
            endpoint_issue = self._futu_endpoint_issue()
            if endpoint_issue is not None:
                return self._skipped_validation(endpoint_issue)

            quote_adapter = None
            trade_adapter = None
            checks: dict[str, dict[str, object]] = {}
            try:
                quote_adapter = self._create_with_timeout(lambda: FutuMarketDataAdapter(self._config.futu))
                quote_health = quote_adapter.health_check()
                checks["quote"] = {
                    "status": "ok" if quote_health["healthy"] else "failed",
                    "detail": quote_health["detail"],
                }
            except FutuAdapterUnavailable as exc:
                checks["quote"] = {"status": "skipped", "detail": str(exc)}
            except Exception as exc:
                logger.exception("Quote adapter validation failed")
                checks["quote"] = {"status": "failed", "detail": str(exc)}
            finally:
                if quote_adapter is not None:
                    with suppress(Exception):
                        quote_adapter.close()

            try:
                trade_adapter = self._create_with_timeout(lambda: FutuBrokerAdapter(self._config.futu))
                trade_health = trade_adapter.health_check()
                checks["trade"] = {
                    "status": "ok" if trade_health["healthy"] else "failed",
                    "detail": trade_health["detail"],
                }
            except FutuAdapterUnavailable as exc:
                checks["trade"] = {"status": "skipped", "detail": str(exc)}
            except Exception as exc:
                logger.exception("Trade adapter validation failed")
                checks["trade"] = {"status": "failed", "detail": str(exc)}
            finally:
                if trade_adapter is not None:
                    with suppress(Exception):
                        trade_adapter.close()

            healthy = all(check["status"] in {"ok", "skipped"} for check in checks.values())
            if all(check["status"] == "skipped" for check in checks.values()):
                detail = "Futu validation skipped"
            else:
                detail = "Futu validation passed" if healthy else "Futu validation failed"
            return {
                "backend": "futu",
                "healthy": healthy,
                "detail": detail,
                "checks": checks,
            }

        return self._cached_diagnostic("futu_validation", load)
