"""
Mutation testing for Python source code.

Mutation testing measures TEST EFFECTIVENESS. It makes many small, deliberate
changes ("mutants") to the code under test and re-runs the existing test suite
against each one:

    * A mutant that makes a test FAIL is "killed"  -> the tests caught the bug.
    * A mutant that leaves every test PASSING "survived" -> a real defect just
      like it could slip through the tests undetected.

The headline number is the mutation score:

    mutation_score = killed / total_mutants

Surviving mutants are the actionable output: each one names a line and a change
the current tests do not detect. Together with cyclomatic complexity, this is
what powers susgrade's risk model  ``risk = complexity * (1 - mutation_score)``.

This module has two halves:

    * GENERATION  - AST-based operators produce exactly one change per mutant.
    * EXECUTION   - each mutant is written to disk and the supplied test suite
                    is run against it in an isolated subprocess with a timeout.

Mutation operators (one change per mutant):

    AOR  Arithmetic operator replacement   + - * / // % **
    ROR  Relational operator replacement   < <= > >= == !=
    LOR  Logical operator replacement       and / or
    UOR  Unary operator replacement         -x / +x
    BCR  Boolean constant replacement       True / False
    NCR  Numeric constant replacement       n -> n+1, n -> 0

CONVENTION: the code under test is exposed to the tests as a module named
``subject``. Tests should import from it, e.g. ``from subject import my_func``.

SECURITY: executing mutants runs the supplied code and tests. Run this service
in a trusted/local environment; the only sandbox is a per-run timeout.
"""

from __future__ import annotations

import ast
import copy
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from typing import Any


# ---------------------------------------------------------------------------
# Operator tables
# ---------------------------------------------------------------------------

_BINOP_SYM = {
    ast.Add: "+", ast.Sub: "-", ast.Mult: "*",
    ast.Div: "/", ast.FloorDiv: "//", ast.Mod: "%", ast.Pow: "**",
}
_BINOP_SWAPS = {
    ast.Add: [ast.Sub], ast.Sub: [ast.Add],
    ast.Mult: [ast.Div], ast.Div: [ast.Mult],
    ast.FloorDiv: [ast.Div], ast.Mod: [ast.Mult], ast.Pow: [ast.Mult],
}

_CMP_SYM = {
    ast.Lt: "<", ast.LtE: "<=", ast.Gt: ">",
    ast.GtE: ">=", ast.Eq: "==", ast.NotEq: "!=",
    ast.Is: "is", ast.IsNot: "is not", ast.In: "in", ast.NotIn: "not in",
}
_CMP_SWAPS = {
    ast.Lt: [ast.LtE, ast.Gt], ast.Gt: [ast.GtE, ast.Lt],
    ast.LtE: [ast.Lt, ast.GtE], ast.GtE: [ast.Gt, ast.LtE],
    ast.Eq: [ast.NotEq], ast.NotEq: [ast.Eq],
    ast.Is: [ast.IsNot], ast.IsNot: [ast.Is],
    ast.In: [ast.NotIn], ast.NotIn: [ast.In],
}

_BOOL_SYM = {ast.And: "and", ast.Or: "or"}
_BOOL_SWAP = {ast.And: ast.Or, ast.Or: ast.And}

_UNARY_SYM = {ast.USub: "-", ast.UAdd: "+"}
_UNARY_SWAP = {ast.USub: ast.UAdd, ast.UAdd: ast.USub}


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class Mutant:
    """A single mutated version of the source module."""
    id: int
    operator: str        # AOR / ROR / LOR / UOR / BCR / NCR
    description: str      # human-readable, e.g. "'<' -> '<='"
    lineno: int
    source: str          # full mutated module source


@dataclass
class MutationResult:
    total_generated: int
    total_run: int
    killed: int
    survived: int
    timed_out: int
    mutation_score: float
    baseline_passed: bool
    survivors: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_generated": self.total_generated,
            "total_run": self.total_run,
            "killed": self.killed,
            "survived": self.survived,
            "timed_out": self.timed_out,
            "mutation_score": self.mutation_score,
            "baseline_passed": self.baseline_passed,
            "survivors": self.survivors,
        }


# ---------------------------------------------------------------------------
# Mutant generation
# ---------------------------------------------------------------------------

def _apply(node: ast.AST, kind: str, sub: int | None, new: Any) -> None:
    """Apply a single in-place mutation to *node*."""
    if kind == "binop":
        node.op = new()          # type: ignore[attr-defined]
    elif kind == "compare":
        node.ops[sub] = new()    # type: ignore[attr-defined]
    elif kind == "boolop":
        node.op = new()          # type: ignore[attr-defined]
    elif kind == "unaryop":
        node.op = new()          # type: ignore[attr-defined]
    elif kind == "const":
        node.value = new         # type: ignore[attr-defined]


# Per-node recipes. Each helper takes one AST node and returns every mutation
# that applies to it as a tuple ``(kind, sub_index, replacement, operator,
# description)`` -- one change per tuple. Keeping the dispatch split this way
# means every function stays small and independently testable; the walker in
# ``generate_mutants`` just collects whatever these return.
_Recipe = tuple[str, "int | None", Any, str, str]


def _binop_recipes(node: ast.BinOp) -> list[_Recipe]:
    if type(node.op) not in _BINOP_SWAPS:
        return []
    sym = _BINOP_SYM[type(node.op)]
    return [("binop", None, rep, "AOR", f"'{sym}' -> '{_BINOP_SYM[rep]}'")
            for rep in _BINOP_SWAPS[type(node.op)]]


def _augassign_recipes(node: ast.AugAssign) -> list[_Recipe]:
    if type(node.op) not in _BINOP_SWAPS:
        return []
    sym = _BINOP_SYM[type(node.op)]
    return [("binop", None, rep, "AOR", f"'{sym}=' -> '{_BINOP_SYM[rep]}='")
            for rep in _BINOP_SWAPS[type(node.op)]]


def _compare_recipes(node: ast.Compare) -> list[_Recipe]:
    out: list[_Recipe] = []
    for k, op in enumerate(node.ops):
        if type(op) in _CMP_SWAPS:
            sym = _CMP_SYM[type(op)]
            for rep in _CMP_SWAPS[type(op)]:
                out.append(("compare", k, rep, "ROR", f"'{sym}' -> '{_CMP_SYM[rep]}'"))
    return out


def _boolop_recipes(node: ast.BoolOp) -> list[_Recipe]:
    if type(node.op) not in _BOOL_SWAP:
        return []
    rep = _BOOL_SWAP[type(node.op)]
    return [("boolop", None, rep, "LOR",
             f"'{_BOOL_SYM[type(node.op)]}' -> '{_BOOL_SYM[rep]}'")]


def _unaryop_recipes(node: ast.UnaryOp) -> list[_Recipe]:
    if type(node.op) not in _UNARY_SWAP:
        return []
    rep = _UNARY_SWAP[type(node.op)]
    return [("unaryop", None, rep, "UOR",
             f"unary '{_UNARY_SYM[type(node.op)]}' -> '{_UNARY_SYM[rep]}'")]


def _const_recipes(node: ast.Constant) -> list[_Recipe]:
    v = node.value
    if isinstance(v, bool):                       # bool before int!
        return [("const", None, (not v), "BCR", f"{v} -> {not v}")]
    if isinstance(v, (int, float)):
        out: list[_Recipe] = [("const", None, v + 1, "NCR", f"{v} -> {v + 1}")]
        if v != 0:
            out.append(("const", None, 0, "NCR", f"{v} -> 0"))
        return out
    return []


# Dispatch table, checked in order (AST types are mutually exclusive, but the
# order is kept stable so mutant ids never shift between runs).
_NODE_RECIPES = [
    (ast.BinOp, _binop_recipes),
    (ast.AugAssign, _augassign_recipes),
    (ast.Compare, _compare_recipes),
    (ast.BoolOp, _boolop_recipes),
    (ast.UnaryOp, _unaryop_recipes),
    (ast.Constant, _const_recipes),
]


def _recipes_for_node(node: ast.AST) -> list[_Recipe]:
    """Return every mutation recipe that applies to *node* (possibly none)."""
    for node_type, builder in _NODE_RECIPES:
        if isinstance(node, node_type):
            return builder(node)  # type: ignore[arg-type]
    return []


def generate_mutants(source: str) -> list[Mutant]:
    """Parse *source* and return one Mutant per possible single mutation.

    Raises SyntaxError if the source cannot be parsed.
    """
    tree = ast.parse(source)

    # Walk once, collecting the recipes each node yields. We remember the walk
    # index and line so the node can be located and labelled when we build the
    # mutated tree below.
    recipes: list[tuple[int, str, int | None, Any, str, str, int]] = []
    for wi, node in enumerate(ast.walk(tree)):
        ln = getattr(node, "lineno", 0)
        for kind, sub, new, operator, desc in _recipes_for_node(node):
            recipes.append((wi, kind, sub, new, operator, desc, ln))

    mutants: list[Mutant] = []
    for i, (wi, kind, sub, new, operator, desc, ln) in enumerate(recipes):
        mtree = copy.deepcopy(tree)
        for j, node in enumerate(ast.walk(mtree)):
            if j == wi:
                _apply(node, kind, sub, new)
                break
        ast.fix_missing_locations(mtree)
        mutants.append(Mutant(id=i, operator=operator, description=desc,
                              lineno=ln, source=ast.unparse(mtree)))
    return mutants


# ---------------------------------------------------------------------------
# Execution
# ---------------------------------------------------------------------------

_PYTEST_ARGS = ["-q", "-x", "-p", "no:cacheprovider", "-o", "addopts=", "test_subject.py"]


def _run_suite(workdir: str, timeout: float) -> int:
    """Run the test suite in *workdir*. Returns pytest's exit code.

    Exit code 0 means every test passed; anything else means a failure/error.
    Raises subprocess.TimeoutExpired if it exceeds *timeout*.

    ``-B`` / PYTHONDONTWRITEBYTECODE is essential: mutants overwrite subject.py
    many times per second, and Python's timestamp-based .pyc cache has only
    whole-second resolution. Without this, a fresh subprocess could import a
    stale, previously-cached mutant instead of the current source and
    misclassify the result.
    """
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
    proc = subprocess.run(
        [sys.executable, "-B", "-m", "pytest", *_PYTEST_ARGS],
        cwd=workdir, capture_output=True, text=True, timeout=timeout, env=env,
    )
    return proc.returncode


def run_mutation_testing(
    source: str,
    test_source: str,
    per_test_timeout: float = 12.0,
    max_mutants: int = 80,
) -> MutationResult:
    """Generate mutants for *source* and run *test_source* against each.

    The code under test is written as module ``subject``; tests import from it.
    Returns a MutationResult. Raises SyntaxError if either input won't parse.
    """
    ast.parse(source)          # surface syntax errors to the caller
    ast.parse(test_source)

    mutants = generate_mutants(source)
    run_list = mutants[:max_mutants]

    with tempfile.TemporaryDirectory() as tmp:
        subject_path = os.path.join(tmp, "subject.py")
        with open(os.path.join(tmp, "test_subject.py"), "w") as fh:
            fh.write(test_source)

        # 1) Baseline: the tests MUST pass on the original code, otherwise the
        #    whole exercise is meaningless.
        with open(subject_path, "w") as fh:
            fh.write(source)
        try:
            if _run_suite(tmp, per_test_timeout) != 0:
                return MutationResult(
                    total_generated=len(mutants), total_run=0, killed=0,
                    survived=0, timed_out=0, mutation_score=0.0,
                    baseline_passed=False, survivors=[],
                )
        except subprocess.TimeoutExpired:
            return MutationResult(
                total_generated=len(mutants), total_run=0, killed=0,
                survived=0, timed_out=0, mutation_score=0.0,
                baseline_passed=False, survivors=[],
            )

        # 2) Run each mutant.
        killed = survived = timed_out = 0
        survivors: list[dict[str, Any]] = []
        for m in run_list:
            with open(subject_path, "w") as fh:
                fh.write(m.source)
            try:
                rc = _run_suite(tmp, per_test_timeout)
            except subprocess.TimeoutExpired:
                timed_out += 1
                killed += 1                      # a hang is a detected change
                continue
            if rc == 0:
                survived += 1
                survivors.append({
                    "operator": m.operator,
                    "description": m.description,
                    "lineno": m.lineno,
                })
            else:
                killed += 1

    total_run = len(run_list)
    score = round(killed / total_run, 3) if total_run else 1.0
    return MutationResult(
        total_generated=len(mutants), total_run=total_run, killed=killed,
        survived=survived, timed_out=timed_out, mutation_score=score,
        baseline_passed=True, survivors=survivors,
    )
