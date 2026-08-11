"""Tests for the mutation testing engine and its API endpoint.

These tests spawn short pytest subprocesses (that's how mutants are scored), so
the subjects here are kept tiny to stay fast.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.analysis.mutation import generate_mutants, run_mutation_testing
from app.main import app

client = TestClient(app)


# ---------------------------------------------------------------------------
# Mutant generation
# ---------------------------------------------------------------------------

def test_generates_relational_and_arithmetic_mutants():
    src = "def f(a, b):\n    if a < b:\n        return a + b\n    return 0\n"
    ops = {m.operator for m in generate_mutants(src)}
    assert "ROR" in ops        # a < b
    assert "AOR" in ops        # a + b
    assert "NCR" in ops        # the 0


def test_boolean_constant_mutation():
    mutants = generate_mutants("flag = True\n")
    assert any(m.operator == "BCR" and "False" in m.description for m in mutants)


def test_logical_operator_mutation():
    mutants = generate_mutants("def f(a, b):\n    return a and b\n")
    assert any(m.operator == "LOR" for m in mutants)


def test_each_mutant_changes_exactly_one_thing():
    src = "def f(a, b):\n    return a + b\n"
    mutants = generate_mutants(src)
    # + has one swap (-), and there are no other mutable nodes here
    assert len(mutants) == 1
    assert "'-'" in mutants[0].source or "- b" in mutants[0].source


def test_generate_mutants_rejects_bad_syntax():
    with pytest.raises(SyntaxError):
        generate_mutants("def f(:\n")


# ---------------------------------------------------------------------------
# Execution / scoring
# ---------------------------------------------------------------------------

SUBJECT = (
    "def sign(n):\n"
    "    if n > 0:\n"
    "        return 1\n"
    "    if n < 0:\n"
    "        return -1\n"
    "    return 0\n"
)


def test_strong_suite_kills_all_mutants():
    tests = (
        "from subject import sign\n"
        "def test_pos(): assert sign(5) == 1\n"
        "def test_pos_edge(): assert sign(1) == 1\n"
        "def test_neg(): assert sign(-5) == -1\n"
        "def test_neg_edge(): assert sign(-1) == -1\n"
        "def test_zero(): assert sign(0) == 0\n"
    )
    r = run_mutation_testing(SUBJECT, tests)
    assert r.baseline_passed is True
    assert r.total_run > 0
    assert r.mutation_score == 1.0
    assert r.survived == 0


def test_weak_suite_leaves_survivors():
    tests = "from subject import sign\ndef test_only_pos(): assert sign(5) == 1\n"
    r = run_mutation_testing(SUBJECT, tests)
    assert r.baseline_passed is True
    assert r.survived > 0
    assert r.mutation_score < 1.0
    assert r.killed + r.survived + 0 <= r.total_run  # timeouts fold into killed


def test_baseline_failure_is_reported():
    bad = "from subject import sign\ndef test_wrong(): assert sign(5) == 999\n"
    r = run_mutation_testing(SUBJECT, bad)
    assert r.baseline_passed is False
    assert r.mutation_score == 0.0


# ---------------------------------------------------------------------------
# API endpoint
# ---------------------------------------------------------------------------

def test_api_mutation_endpoint():
    payload = {
        "source": SUBJECT,
        "tests": (
            "from subject import sign\n"
            "def test_pos(): assert sign(5) == 1\n"
            "def test_neg(): assert sign(-5) == -1\n"
            "def test_zero(): assert sign(0) == 0\n"
        ),
    }
    resp = client.post("/analyze/mutation", json=payload)
    assert resp.status_code == 200
    body = resp.json()
    assert body["baseline_passed"] is True
    assert 0.0 <= body["mutation_score"] <= 1.0
    assert body["total_run"] == body["killed"] + body["survived"]


def test_api_mutation_rejects_bad_source():
    resp = client.post("/analyze/mutation", json={"source": "def f(:", "tests": "x=1"})
    assert resp.status_code == 422
