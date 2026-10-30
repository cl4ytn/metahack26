"""HTTP endpoints for architecture generation, retrieval, and approval."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator

from backend.app.models.graph import ArchitectureGraph, GraphStatus
from backend.app.services.muse_spark import (
    FixtureMuseSpark,
    MuseSparkAdapter,
    MuseSparkError,
    MuseSparkUnavailableError,
)
from backend.app.services.validator import ValidationReport, validate_graph
from backend.app.storage.yaml_store import (
    GraphFileNotFoundError,
    GraphStoreError,
    InvalidGraphError,
    load_graph,
    save_graph,
)

DEFAULT_ARCHITECTURE_PATH = Path(__file__).resolve().parents[2] / "architecture.yaml"

router = APIRouter(prefix="/api/architecture", tags=["architecture"])


class ArchitectureRequest(BaseModel):
    requirement: str = Field(
        min_length=1,
        description="Natural-language architecture requirement.",
    )

    @field_validator("requirement")
    @classmethod
    def _reject_blank_requirement(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("requirement must not be blank")
        return value


class AdapterMetadata(BaseModel):
    name: str
    is_fixture: bool


class ValidationIssuePayload(BaseModel):
    code: str
    message: str
    entity_type: str
    entity_id: str | None = None
    field: str | None = None
    ref_id: str | None = None


class ValidationReportPayload(BaseModel):
    is_valid: bool
    errors: list[ValidationIssuePayload]


class ArchitectureGenerationResponse(BaseModel):
    graph: ArchitectureGraph
    validation: ValidationReportPayload
    adapter: AdapterMetadata


class ArchitectureApproveResponse(BaseModel):
    graph: ArchitectureGraph
    validation: ValidationReportPayload
    saved: bool
    saved_path: str


def get_muse_spark() -> MuseSparkAdapter:
    return FixtureMuseSpark()


def get_architecture_path() -> Path:
    return DEFAULT_ARCHITECTURE_PATH


def _validation_payload(report: ValidationReport) -> ValidationReportPayload:
    return ValidationReportPayload(
        is_valid=report.is_valid,
        errors=[
            ValidationIssuePayload(
                code=issue.code,
                message=issue.message,
                entity_type=issue.entity_type,
                entity_id=issue.entity_id,
                field=issue.field,
                ref_id=issue.ref_id,
            )
            for issue in report.errors
        ],
    )


@router.post("", response_model=ArchitectureGenerationResponse)
def generate_architecture(
    request: ArchitectureRequest,
    adapter: MuseSparkAdapter = Depends(get_muse_spark),
) -> ArchitectureGenerationResponse:
    try:
        graph = adapter.generate_graph(request.requirement)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except MuseSparkUnavailableError as exc:
        raise HTTPException(status_code=503, detail="Muse Spark is unavailable") from exc
    except MuseSparkError as exc:
        raise HTTPException(status_code=502, detail="Muse Spark failed to produce a graph") from exc

    report = validate_graph(graph)
    return ArchitectureGenerationResponse(
        graph=graph,
        validation=_validation_payload(report),
        adapter=AdapterMetadata(name=adapter.name(), is_fixture=adapter.is_fixture()),
    )


@router.get("", response_model=ArchitectureGraph)
def get_architecture(path: Path = Depends(get_architecture_path)) -> ArchitectureGraph:
    try:
        return load_graph(path)
    except GraphFileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="No stored architecture") from exc
    except GraphStoreError as exc:
        raise HTTPException(status_code=500, detail="Stored architecture is unreadable") from exc


@router.post("/approve", response_model=ArchitectureApproveResponse)
def approve_architecture(
    graph: ArchitectureGraph,
    path: Path = Depends(get_architecture_path),
) -> ArchitectureApproveResponse:
    report = validate_graph(graph)
    if not report.is_valid:
        raise HTTPException(status_code=422, detail=report.messages())

    graph.status = GraphStatus.APPROVED
    graph.approved_at = datetime.now(timezone.utc)

    try:
        save_graph(graph, path)
    except InvalidGraphError as exc:
        raise HTTPException(
            status_code=409,
            detail=f"Architecture could not be saved: {exc}",
        ) from exc
    except GraphStoreError as exc:
        raise HTTPException(
            status_code=500,
            detail="Architecture could not be persisted",
        ) from exc

    return ArchitectureApproveResponse(
        graph=graph,
        validation=_validation_payload(report),
        saved=True,
        saved_path=str(path),
    )