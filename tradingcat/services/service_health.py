from __future__ import annotations

import argparse
import http.client
import json
from time import monotonic
from typing import Any
from urllib.parse import urlsplit


DEFAULT_CORE_PATHS = (
    "/preflight/startup",
    "/ops/readiness",
    "/ops/go-live",
    "/ops/live-acceptance",
)


def _fetch_json(url: str, timeout: float) -> tuple[int, Any]:
    parsed = urlsplit(url)
    connection_cls = http.client.HTTPSConnection if parsed.scheme == "https" else http.client.HTTPConnection
    path = parsed.path or "/"
    if parsed.query:
        path = f"{path}?{parsed.query}"
    connection = connection_cls(parsed.hostname, parsed.port, timeout=timeout)
    try:
        connection.request("GET", path, headers={"Connection": "close", "User-Agent": "TradingCatHealth/1.0"})
        response = connection.getresponse()
        status = response.status or 200
        payload = json.loads(response.read().decode("utf-8"))
    finally:
        connection.close()
    return status, payload


def probe_endpoint(
    *,
    base_url: str,
    path: str,
    timeout: float = 5.0,
    fetcher=_fetch_json,
) -> dict[str, object]:
    started = monotonic()
    url = f"{base_url.rstrip('/')}{path}"
    try:
        status, payload = fetcher(url, timeout)
        elapsed_ms = round((monotonic() - started) * 1000, 2)
        healthy = status == 200 and isinstance(payload, dict)
        detail = "ok" if healthy else f"Unexpected response type: {type(payload).__name__}"
        return {
            "path": path,
            "url": url,
            "healthy": healthy,
            "status_code": status,
            "elapsed_ms": elapsed_ms,
            "detail": detail,
        }
    except (TimeoutError, http.client.HTTPException, json.JSONDecodeError, OSError, ValueError) as exc:
        elapsed_ms = round((monotonic() - started) * 1000, 2)
        return {
            "path": path,
            "url": url,
            "healthy": False,
            "status_code": None,
            "elapsed_ms": elapsed_ms,
            "detail": str(exc),
        }


def probe_core_endpoints(
    *,
    base_url: str,
    timeout: float = 5.0,
    paths: tuple[str, ...] = DEFAULT_CORE_PATHS,
    fetcher=_fetch_json,
) -> dict[str, object]:
    results = [
        probe_endpoint(base_url=base_url, path=path, timeout=timeout, fetcher=fetcher)
        for path in paths
    ]
    failed_paths = [str(item["path"]) for item in results if not bool(item["healthy"])]
    return {
        "healthy": len(failed_paths) == 0,
        "base_url": base_url.rstrip("/"),
        "timeout_seconds": timeout,
        "paths": list(paths),
        "failed_paths": failed_paths,
        "results": results,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Probe TradingCat core health endpoints.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--timeout", type=float, default=5.0)
    args = parser.parse_args(argv)

    summary = probe_core_endpoints(base_url=args.base_url, timeout=args.timeout)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if bool(summary["healthy"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
