"""susgrade API — test-effectiveness analysis for Python code.

Sprint 1 exposes the cyclomatic complexity engine. Later sprints add the
mutation-testing engine and the combined risk report on top of the same app.
"""

from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.analysis.complexity import analyze_source
from app.analysis.mutation import run_mutation_testing
from app.models import (
    AnalyzeRequest,
    ComplexityResponse,
    MutationRequest,
    MutationResponse,
)

app = FastAPI(
    title="susgrade",
    description="Combined cyclomatic complexity + mutation testing for Python.",
    version="0.1.0",
)

# The React frontend will run on a different origin during development.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten to the deployed frontend origin later
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/analyze/complexity", response_model=ComplexityResponse)
def analyze_complexity(req: AnalyzeRequest) -> ComplexityResponse:
    """Return per-function cyclomatic complexity for a Python snippet."""
    try:
        result = analyze_source(req.source)
    except SyntaxError as exc:
        raise HTTPException(
            status_code=422,
            detail=f"Could not parse Python source: {exc.msg} (line {exc.lineno})",
        )
    return ComplexityResponse(**result.to_dict())


@app.post("/analyze/mutation", response_model=MutationResponse)
def analyze_mutation(req: MutationRequest) -> MutationResponse:
    """Run mutation testing: mutate the source and score how many mutants the
    supplied test suite kills. The code under test is exposed as module
    ``subject`` (tests should import from it)."""
    try:
        result = run_mutation_testing(req.source, req.tests)
    except SyntaxError as exc:
        raise HTTPException(
            status_code=422,
            detail=f"Could not parse Python source: {exc.msg} (line {exc.lineno})",
        )
    return MutationResponse(**result.to_dict())
