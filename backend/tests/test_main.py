"""Tests for backend/app/main.py (application assembly).

Responsibility under test: composition. We do NOT re-test the endpoints
themselves - only that routers are mounted on the composed app, health
works, CORS is wired for the frontend origin, and repeated create_app()
calls do not share mutable route state.

Label: these tests were NOT executed against the real api/architecture.py
or api/tasks.py in this session (those files were not attached). They are
reasoned against the contracts in the implementation record. Run locally
with: cd backend && python -m pytest tests/test_main.py -v
"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.main import FRONTEND_ORIGINS, create_app


def _routes_by_path(app: FastAPI) -> dict[str, set[str]]:
    """Collect {path: {HTTP methods}} from the composed app's OpenAPI schema.

    Recent FastAPI versions defer flattening of included routers into
    app.routes via fastapi.routing._IncludedRouter markers. Those markers
    expose neither .path nor .methods, so a direct walk of app.routes
    silently misses every route from an included router - even though the
    app serves them correctly at request time. app.openapi() resolves the
    full composed surface and is stable across FastAPI versions here.
    """
    paths = app.openapi().get("paths", {})
    return {
        path: {method.upper() for method in methods}
        for path, methods in paths.items()
    }


# ---------------------------------------------------------------------------
# Composition: routers mounted
# ---------------------------------------------------------------------------


def test_create_app_returns_fastapi_instance():
    assert isinstance(create_app(), FastAPI)


def test_architecture_router_is_mounted():
    routes = _routes_by_path(create_app())
    assert "/api/architecture" in routes
    assert "GET" in routes["/api/architecture"]
    assert "POST" in routes["/api/architecture"]


def test_tasks_router_is_mounted():
    routes = _routes_by_path(create_app())
    # The tasks router exposes GET "" and POST "/schedule" plus
    # POST "/{task_id}/execute". Presence of the prefix is enough here;
    # endpoint behaviour is covered by tests/test_tasks_api.py.
    assert "/api/tasks" in routes
    assert "GET" in routes["/api/tasks"]


def test_health_route_is_mounted():
    routes = _routes_by_path(create_app())
    assert "/health" in routes
    assert "GET" in routes["/health"]


def test_root_route_is_mounted():
    routes = _routes_by_path(create_app())
    assert "/" in routes
    assert "GET" in routes["/"]


# ---------------------------------------------------------------------------
# Reachability through the composed app
# ---------------------------------------------------------------------------


def test_health_returns_200_and_status_ok():
    client = TestClient(create_app())
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert "version" in body


def test_root_returns_200():
    client = TestClient(create_app())
    response = client.get("/")
    assert response.status_code == 200
    body = response.json()
    # Discovery keys we control in main.py
    assert body["health"] == "/health"
    assert body["docs"] == "/docs"


# ---------------------------------------------------------------------------
# CORS wiring for the React frontend
# ---------------------------------------------------------------------------


def test_cors_allows_configured_frontend_origin():
    client = TestClient(create_app())
    origin = FRONTEND_ORIGINS[0]
    response = client.get("/health", headers={"Origin": origin})
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == origin


def test_cors_does_not_allow_unknown_origin():
    client = TestClient(create_app())
    response = client.get(
        "/health", headers={"Origin": "http://not-the-frontend.example"}
    )
    header_names = {name.lower() for name in response.headers}
    assert "access-control-allow-origin" not in header_names


# ---------------------------------------------------------------------------
# create_app is a factory (no shared mutable state between calls)
# ---------------------------------------------------------------------------


def test_create_app_returns_independent_instances():
    a = create_app()
    b = create_app()
    assert a is not b
    client_a = TestClient(a)
    client_b = TestClient(b)
    assert client_a.get("/health").status_code == 200
    assert client_b.get("/health").status_code == 200


def test_module_level_app_is_a_fastapi_instance():
    # uvicorn entrypoint references "app.main:app"
    from backend.app.main import app as module_app

    assert isinstance(module_app, FastAPI)