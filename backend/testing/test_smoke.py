import os

os.environ.setdefault("ALLOW_ALL_ORIGINS", "1")

import importlib
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


# Ensure the backend package is importable when pytest runs from repo root.
BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


def _load_app() -> TestClient:
    """
    Import the FastAPI app with lightweight settings so LLM backends are skipped.
    Reloading ensures env overrides are respected for every test run.
    """
    os.environ["SKIP_LLM_SETUP"] = "1"
    os.environ["FORCE_RETRIEVER_BUILD"] = "0"
    os.environ.setdefault("FRONTEND_ORIGINS", "http://test.local")
    module = importlib.import_module("main")
    module = importlib.reload(module)
    return TestClient(module.app)


@pytest.fixture(scope="session")
def client() -> TestClient:
    return _load_app()


def test_health_endpoint(client: TestClient):
    res = client.get("/api/health")
    assert res.status_code == 200
    data = res.json()
    assert data["ok"] is True
    assert "time" in data


def test_session_reset(client: TestClient):
    res = client.post("/api/session/reset")
    assert res.status_code == 200
    body = res.json()
    assert body["ok"] is True
    assert "message" in body


def test_cors_preflight(client: TestClient):
    res = client.options(
        "/api/health",
        headers={
            "Origin": "http://test.local",
            "Access-Control-Request-Method": "GET",
        },
    )
    # Starlette returns 204 for successful preflight responses.
    assert res.status_code in (200, 204)
    assert res.headers.get("access-control-allow-origin") == "http://test.local"
