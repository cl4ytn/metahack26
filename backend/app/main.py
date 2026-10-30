"""GraphPilot FastAPI application assembly (backend/app/main.py).

Composition only:
- build the FastAPI app,
- mount the existing architecture and tasks routers,
- add CORS for the React dev server,
- expose /health and / as lightweight liveness / discovery,
- provide the uvicorn entrypoint.

No business logic. No dependency seams re-declared here. The seams
(get_muse_spark, get_architecture_path, get_coding_agent,
get_verification_command_builder) live in app.api.* where they belong.
"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.app.api.architecture import router as architecture_router
from backend.app.api.tasks import router as tasks_router

APP_NAME = "GraphPilot"
APP_VERSION = "0.1.0"

# React dev server defaults. Vite uses 5173; CRA uses 3000. Extend as needed.
FRONTEND_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]


def create_app() -> FastAPI:
    """Build the composed FastAPI application.

    A fresh instance is returned per call so tests and uvicorn import
    cannot share mutable route state.
    """
    app = FastAPI(title=APP_NAME, version=APP_VERSION)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=FRONTEND_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(architecture_router)
    app.include_router(tasks_router)

    @app.get("/health", tags=["health"])
    def health() -> dict[str, str]:
        return {"status": "ok", "service": APP_NAME.lower(), "version": APP_VERSION}

    @app.get("/", tags=["health"])
    def root() -> dict[str, str]:
        return {
            "service": APP_NAME,
            "version": APP_VERSION,
            "docs": "/docs",
            "health": "/health",
        }

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=True)