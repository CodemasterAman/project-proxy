"""Request and response schemas for the susgrade API."""

from __future__ import annotations

from pydantic import BaseModel, Field


class AnalyzeRequest(BaseModel):
    source: str = Field(..., description="Python source code to analyze.")


class FunctionResult(BaseModel):
    name: str
    lineno: int
    end_lineno: int
    complexity: int
    rank: str


class ComplexityResponse(BaseModel):
    functions: list[FunctionResult]
    total_complexity: int
    average_complexity: float
    max_complexity: int


class MutationRequest(BaseModel):
    source: str = Field(..., description="Python source code under test.")
    tests: str = Field(
        ...,
        description="Pytest test code. Import the code under test from `subject`, "
        "e.g. `from subject import my_function`.",
    )


class SurvivingMutant(BaseModel):
    operator: str
    description: str
    lineno: int


class MutationResponse(BaseModel):
    total_generated: int
    total_run: int
    killed: int
    survived: int
    timed_out: int
    mutation_score: float
    baseline_passed: bool
    survivors: list[SurvivingMutant]
