from __future__ import annotations

import socket
import time
from contextlib import suppress
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from typing import Callable, TypeVar

from tradingcat.adapters.broker import ManualExecutionAdapter, SimulatedBrokerAdapter
from tradingcat.adapters.market import StaticMarketDataAdapter
from tradingcat.adapters.futu import FutuAdapterUnavailable, FutuBrokerAdapter, FutuMarketDataAdapter
from tradingcat.config import AppConfig


T = TypeVar("T")


class AdapterFactory:
    _DIAGNOSTIC_CACHE_TTL_SECONDS = 2.0
    _FUTU_PROBE_TIMEOUT_SECONDS = 0.2

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
                timeout=self._FUTU_PROBE_TIMEOUT_SECONDS,
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

    def _create_with_timeout(self, factory: Callable[[], T], timeout: float = 3.0) -> T:
        executor = ThreadPoolExecutor(max_workers=1)
        future = executor.submit(factory)
        try:
            return future.result(timeout=timeout)
        except FutureTimeoutError as exc:
            future.cancel()
            executor.shutdown(wait=False, cancel_futures=True)
            raise FutuAdapterUnavailable(f"Futu adapter initialization timed out after {timeout:.1f}s") from exc
        except Exception:
            executor.shutdown(wait=True, cancel_futures=True)
            raise
        else:
            executor.shutdown(wait=True, cancel_futures=True)

    def create_market_data_adapter(self):
        if not self._config.futu.enabled:
            return StaticMarketDataAdapter()
        try:
            self._ensure_futu_endpoint()
            return self._create_with_timeout(lambda: FutuMarketDataAdapter(self._config.futu))
        except FutuAdapterUnavailable:
            return StaticMarketDataAdapter()

    def create_live_broker_adapter(self):
        if not self._config.futu.enabled:
            return SimulatedBrokerAdapter()
        try:
            self._ensure_futu_endpoint()
            return self._create_with_timeout(lambda: FutuBrokerAdapter(self._config.futu))
        except FutuAdapterUnavailable:
            return SimulatedBrokerAdapter()

    def create_manual_broker_adapter(self):
        return ManualExecutionAdapter()

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
