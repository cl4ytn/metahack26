from __future__ import annotations

import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.app.api.architecture import router as architecture_router
from backend.app.api.requirements import router as requirements_router
from backend.app.api.tasks import router as tasks_router

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("graphpilot")

app = FastAPI(
    title="GraphPilot Backend",
    description="Deterministic AI Architecture & Verification Engine",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(requirements_router)
app.include_router(architecture_router)
app.include_router(tasks_router)


@app.get("/")
def health_check() -> dict[str, str]:
    return {
        "status": "online",
        "service": "GraphPilot Engine",
        "tagline": "Less Talking, More Doing",
        "version": "1.0.0",
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=True)
