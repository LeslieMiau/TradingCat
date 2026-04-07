"""Tests for API key authentication middleware."""
from __future__ import annotations

import os

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.responses import JSONResponse

from tradingcat.api.auth import ApiKeyMiddleware


def _make_app(api_key: str | None = None) -> FastAPI:
    app = FastAPI()
    app.add_middleware(ApiKeyMiddleware, api_key=api_key)

    @app.get("/dashboard")
    def dashboard():
        return JSONResponse({"page": "dashboard"})

    @app.get("/dashboard/summary")
    def dashboard_summary():
        return JSONResponse({"summary": True})

    @app.get("/preflight/startup")
    def preflight():
        return JSONResponse({"ok": True})

    @app.get("/orders")
    def orders():
        return JSONResponse({"orders": []})

    @app.get("/static/dashboard.css")
    def static_css():
        return JSONResponse({"css": True})

    return app


class TestNoKeyConfigured:
    """When no API key is set, everything is open (localhost trust mode)."""

    def test_all_endpoints_accessible(self):
        client = TestClient(_make_app(api_key=None))
        assert client.get("/orders").status_code == 200
        assert client.get("/dashboard").status_code == 200
        assert client.get("/dashboard/summary").status_code == 200

    def test_empty_string_key_is_no_op(self):
        client = TestClient(_make_app(api_key=""))
        assert client.get("/orders").status_code == 200


class TestWithKeyConfigured:
    """When API key is set, protected endpoints require it."""

    KEY = "test-secret-key-12345"

    def test_protected_endpoint_rejects_without_key(self):
        client = TestClient(_make_app(api_key=self.KEY))
        resp = client.get("/orders")
        assert resp.status_code == 401
        assert "API key" in resp.json()["detail"]

    def test_protected_endpoint_accepts_header(self):
        client = TestClient(_make_app(api_key=self.KEY))
        resp = client.get("/orders", headers={"X-API-Key": self.KEY})
        assert resp.status_code == 200

    def test_protected_endpoint_accepts_query_param(self):
        client = TestClient(_make_app(api_key=self.KEY))
        resp = client.get("/orders", params={"api_key": self.KEY})
        assert resp.status_code == 200

    def test_wrong_key_rejected(self):
        client = TestClient(_make_app(api_key=self.KEY))
        resp = client.get("/orders", headers={"X-API-Key": "wrong"})
        assert resp.status_code == 401

    def test_public_paths_always_accessible(self):
        client = TestClient(_make_app(api_key=self.KEY))
        # Dashboard HTML page
        assert client.get("/dashboard").status_code == 200
        # Preflight health check
        assert client.get("/preflight/startup").status_code == 200
        # Static assets
        assert client.get("/static/dashboard.css").status_code == 200

    def test_dashboard_summary_is_protected(self):
        """Dashboard JSON summary (API endpoint) should require auth."""
        client = TestClient(_make_app(api_key=self.KEY))
        assert client.get("/dashboard/summary").status_code == 401
        resp = client.get("/dashboard/summary", headers={"X-API-Key": self.KEY})
        assert resp.status_code == 200
