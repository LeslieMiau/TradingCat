from tradingcat.services.service_health import probe_core_endpoints, probe_endpoint


def test_probe_endpoint_marks_json_200_as_healthy():
    def fetcher(_url: str, _timeout: float):
        return 200, {"ready": False, "blockers": []}

    result = probe_endpoint(
        base_url="http://127.0.0.1:8000",
        path="/ops/readiness",
        timeout=3.0,
        fetcher=fetcher,
    )

    assert result["healthy"] is True
    assert result["status_code"] == 200
    assert result["path"] == "/ops/readiness"


def test_probe_core_endpoints_reports_failed_paths():
    def fetcher(url: str, _timeout: float):
        if url.endswith("/ops/go-live"):
            raise TimeoutError("timed out")
        return 200, {"ok": True}

    summary = probe_core_endpoints(
        base_url="http://127.0.0.1:8000",
        timeout=3.0,
        paths=("/preflight/startup", "/ops/go-live"),
        fetcher=fetcher,
    )

    assert summary["healthy"] is False
    assert summary["failed_paths"] == ["/ops/go-live"]
    assert len(summary["results"]) == 2
