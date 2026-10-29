from __future__ import annotations

"""Natural Language Requirements Decomposition API.

Converts high-level engineering prompts into structured, validated
Architecture DAG specifications via the Muse Spark decomposition engine.
"""

from typing import Any
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.app.models.graph import ArchitectureGraph
from backend.app.services.muse_spark import FixtureMuseSpark, MuseSparkError
from backend.app.services.validator import validate_graph

router = APIRouter(prefix="/api/requirements", tags=["requirements"])


class DecomposeRequest(BaseModel):
    """Input payload containing the natural language requirement."""
    requirement: str = Field(
        ...,
        min_length=1,
        description="High-level system requirement, architecture prompt, or feature request",
    )


class DecomposeResponse(BaseModel):
    """Decomposition result containing the initial ArchitectureGraph and validation report."""
    graph: ArchitectureGraph
    is_valid: bool
    issues: list[dict[str, Any]]
    is_fixture: bool = True
    provenance: str = "Fixed Bookmarks Service fixture; requirement text is recorded, no model is called."
    adapter_name: str


@router.post("/decompose", response_model=DecomposeResponse)
def decompose_requirement(payload: DecomposeRequest) -> DecomposeResponse:
    """Decompose a natural language prompt into an ArchitectureGraph.

    Steps:
      1. Invoke Muse Spark decomposition engine.
      2. Run validator to verify 0 cycles and valid entity references.
      3. Return the draft graph and validation issues.
    """
    adapter = FixtureMuseSpark()
    try:
        graph = adapter.generate_graph(payload.requirement)
    except MuseSparkError as err:
        raise HTTPException(status_code=500, detail=str(err)) from err
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err)) from err

    report = validate_graph(graph)
    issues_list = [
        {
            "code": err.code,
            "message": err.message,
            "entity_type": err.entity_type,
            "entity_id": err.entity_id,
            "field": err.field,
        }
        for err in report.errors
    ]

    from backend.app.api.architecture import set_current_graph, get_current_graph
    graph = graph.model_copy(update={"revision": get_current_graph().revision + 1})
    set_current_graph(graph)
    return DecomposeResponse(
        graph=graph,
        is_valid=report.is_valid,
        issues=issues_list,
        adapter_name=adapter.name(),
    )
