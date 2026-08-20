"""
susgrade command-line interface — the quality gate that runs in CI.

The website is the friendly, in-browser face of susgrade; this module is the
same analysis wired up to exit codes so a build can *fail* when code gets too
risky. Three subcommands mirror the three things the site measures:

    susgrade check   PATHS...            cyclomatic complexity gate (no tests
                                         needed — runs over a whole repo)
    susgrade mutation --source --tests   mutation-score gate for one module
    susgrade risk     --source --tests   fused risk gate (complexity x mutation)

Exit codes:
    0   every gate passed (or no threshold was given — report only)
    1   a threshold was exceeded — fail the build
    2   bad usage / a file could not be read or parsed

Run it directly with ``python -m app.cli ...`` from the backend/ folder, or,
after ``pip install -e .``, as just ``susgrade ...``.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from app.analysis.complexity import FunctionComplexity, analyze_source
from app.analysis.mutation import generate_mutants, run_mutation_testing

# Exit codes as named constants so every command speaks the same language.
EXIT_OK = 0
EXIT_GATE_FAILED = 1
EXIT_USAGE = 2


# ---------------------------------------------------------------------------
# Small shared helpers
# ---------------------------------------------------------------------------

def _read(path_str: str) -> str:
    """Read a file, exiting cleanly with a message if it cannot be read."""
    try:
        return Path(path_str).read_text(encoding="utf-8")
    except OSError as exc:
        print(f"susgrade: cannot read {path_str}: {exc}", file=sys.stderr)
        raise SystemExit(EXIT_USAGE)


def _iter_python_files(paths: list[str]) -> list[Path]:
    """Expand the given paths into a sorted, de-duplicated list of .py files."""
    found: set[Path] = set()
    for raw in paths:
        p = Path(raw)
        if p.is_dir():
            found.update(p.rglob("*.py"))
        elif p.suffix == ".py":
            found.add(p)
        elif p.exists():
            continue  # a non-python file passed explicitly is just skipped
        else:
            print(f"susgrade: no such file or directory: {raw}", file=sys.stderr)
            raise SystemExit(EXIT_USAGE)
    return sorted(found)


def _attribute_line(line: int, functions: list[FunctionComplexity]) -> FunctionComplexity | None:
    """Return the innermost function whose line span contains *line* (or None)."""
    best: FunctionComplexity | None = None
    for fn in functions:
        if fn.lineno <= line <= fn.end_lineno:
            if best is None or fn.lineno > best.lineno:
                best = fn
    return best


def _emit(payload: dict[str, Any], fmt: str, render) -> None:
    """Print JSON when asked, otherwise call *render* for human output."""
    if fmt == "json":
        print(json.dumps(payload, indent=2))
    else:
        render()


# ---------------------------------------------------------------------------
# `check` — cyclomatic complexity gate
# ---------------------------------------------------------------------------

def _analyse_paths(files: list[Path]) -> list[dict[str, Any]]:
    """Analyse every file, returning one flat record per function."""
    rows: list[dict[str, Any]] = []
    for f in files:
        try:
            module = analyze_source(_read(str(f)))
        except SyntaxError as exc:
            print(f"susgrade: could not parse {f}: {exc.msg} (line {exc.lineno})",
                  file=sys.stderr)
            raise SystemExit(EXIT_USAGE)
        for fn in module.functions:
            rows.append({
                "file": str(f), "name": fn.name, "lineno": fn.lineno,
                "complexity": fn.complexity, "rank": fn.rank,
            })
    return rows


def cmd_check(args: argparse.Namespace) -> int:
    files = _iter_python_files(args.paths)
    rows = _analyse_paths(files)
    limit = args.max_complexity
    offenders = [r for r in rows if limit is not None and r["complexity"] > limit]
    worst = max((r["complexity"] for r in rows), default=0)
    passed = not offenders

    payload = {
        "command": "check", "files": len(files), "functions": len(rows),
        "max_complexity": worst, "threshold": limit,
        "offenders": offenders, "passed": passed,
    }

    def render() -> None:
        shown = sorted(rows, key=lambda r: -r["complexity"])
        print(f"susgrade check — {len(rows)} functions across {len(files)} file(s)\n")
        for r in shown[:15]:
            flag = "  <-- over limit" if r in offenders else ""
            print(f"  {r['complexity']:>3}  {r['rank']:<12} "
                  f"{r['name']}  ({r['file']}:{r['lineno']}){flag}")
        if len(shown) > 15:
            print(f"  ... and {len(shown) - 15} more")
        print()
        if limit is None:
            print(f"No threshold set — report only. Highest complexity: {worst}.")
        elif passed:
            print(f"PASS — highest complexity {worst} is within the limit of {limit}.")
        else:
            print(f"FAIL — {len(offenders)} function(s) above the limit of {limit}.")

    _emit(payload, args.format, render)
    return EXIT_OK if passed else EXIT_GATE_FAILED


# ---------------------------------------------------------------------------
# `mutation` — mutation-score gate
# ---------------------------------------------------------------------------

def cmd_mutation(args: argparse.Namespace) -> int:
    source, tests = _read(args.source), _read(args.tests)
    try:
        result = run_mutation_testing(source, tests)
    except SyntaxError as exc:
        print(f"susgrade: could not parse source: {exc.msg} (line {exc.lineno})",
              file=sys.stderr)
        return EXIT_USAGE

    minimum = args.min_score
    passed = result.baseline_passed and (minimum is None or result.mutation_score >= minimum)
    payload = {"command": "mutation", "threshold": minimum, **result.to_dict(), "passed": passed}

    def render() -> None:
        if not result.baseline_passed:
            print("FAIL — the test suite does not pass on the original code.")
            print("       Fix the tests before mutation testing can mean anything.")
            return
        pct = round(result.mutation_score * 100)
        print(f"susgrade mutation — score {pct}%  "
              f"({result.killed} killed / {result.survived} survived "
              f"of {result.total_run} run)\n")
        for s in result.survivors[:12]:
            print(f"  survived  line {s['lineno']:>3}  {s['operator']}  {s['description']}")
        if len(result.survivors) > 12:
            print(f"  ... and {len(result.survivors) - 12} more survivors")
        print()
        if minimum is None:
            print(f"No threshold set — report only. Mutation score: {pct}%.")
        elif passed:
            print(f"PASS — {pct}% meets the minimum of {round(minimum * 100)}%.")
        else:
            print(f"FAIL — {pct}% is below the minimum of {round(minimum * 100)}%.")

    _emit(payload, args.format, render)
    return EXIT_OK if passed else EXIT_GATE_FAILED


# ---------------------------------------------------------------------------
# `risk` — fused complexity x mutation gate
# ---------------------------------------------------------------------------

def _per_function_risk(source: str, tests: str) -> tuple[list[dict[str, Any]], bool]:
    """Compute risk = complexity x (1 - mutation_score) for every function.

    Uses only the public engine API: complexity for the ranking + spans,
    generate_mutants for per-function totals, and run_mutation_testing for the
    survivors. Mutants are attributed to the innermost enclosing function by
    line, mirroring the in-browser report.
    """
    functions = analyze_source(source).functions
    result = run_mutation_testing(source, tests)
    if not result.baseline_passed:
        return [], False

    totals: dict[str | None, int] = {}
    survived: dict[str | None, int] = {}
    for m in generate_mutants(source):
        fn = _attribute_line(m.lineno, functions)
        key = fn.name if fn else None
        totals[key] = totals.get(key, 0) + 1
    for s in result.survivors:
        fn = _attribute_line(s["lineno"], functions)
        key = fn.name if fn else None
        survived[key] = survived.get(key, 0) + 1

    rows: list[dict[str, Any]] = []
    for fn in functions:
        total = totals.get(fn.name, 0)
        surv = survived.get(fn.name, 0)
        mut_score = (total - surv) / total if total else 1.0
        rows.append({
            "name": fn.name, "lineno": fn.lineno, "complexity": fn.complexity,
            "mutation_score": round(mut_score, 3),
            "risk": round(fn.complexity * (1 - mut_score), 2),
            "mutants": total,
        })
    rows.sort(key=lambda r: -r["risk"])
    return rows, True


def cmd_risk(args: argparse.Namespace) -> int:
    source, tests = _read(args.source), _read(args.tests)
    try:
        rows, ok = _per_function_risk(source, tests)
    except SyntaxError as exc:
        print(f"susgrade: could not parse source: {exc.msg} (line {exc.lineno})",
              file=sys.stderr)
        return EXIT_USAGE

    if not ok:
        print("FAIL — the test suite does not pass on the original code.", file=sys.stderr)
        payload = {"command": "risk", "baseline_passed": False, "passed": False}
        if args.format == "json":
            print(json.dumps(payload, indent=2))
        return EXIT_GATE_FAILED

    ceiling = args.max_risk
    offenders = [r for r in rows if ceiling is not None and r["risk"] > ceiling]
    worst = max((r["risk"] for r in rows), default=0.0)
    passed = not offenders
    payload = {"command": "risk", "threshold": ceiling, "max_risk": worst,
               "functions": rows, "offenders": offenders, "passed": passed}

    def render() -> None:
        print(f"susgrade risk — complexity x (1 - mutation score), per function\n")
        for r in rows[:15]:
            flag = "  <-- over limit" if r in offenders else ""
            print(f"  risk {r['risk']:>6}  cx {r['complexity']:>2}  "
                  f"mut {round(r['mutation_score'] * 100):>3}%  {r['name']}{flag}")
        print()
        if ceiling is None:
            print(f"No threshold set — report only. Highest risk: {worst}.")
        elif passed:
            print(f"PASS — highest risk {worst} is within the limit of {ceiling}.")
        else:
            print(f"FAIL — {len(offenders)} function(s) above the risk limit of {ceiling}.")

    _emit(payload, args.format, render)
    return EXIT_OK if passed else EXIT_GATE_FAILED


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="susgrade",
        description="Test-effectiveness quality gates for CI: complexity, "
                    "mutation score, and fused risk.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_check = sub.add_parser("check", help="cyclomatic complexity gate over files/dirs")
    p_check.add_argument("paths", nargs="+", help="files or directories to scan")
    p_check.add_argument("--max-complexity", type=int, default=None,
                         help="fail if any function exceeds this complexity")
    p_check.add_argument("--format", choices=["text", "json"], default="text")
    p_check.set_defaults(func=cmd_check)

    p_mut = sub.add_parser("mutation", help="mutation-score gate for one module")
    p_mut.add_argument("--source", required=True, help="module under test")
    p_mut.add_argument("--tests", required=True, help="pytest file importing `subject`")
    p_mut.add_argument("--min-score", type=float, default=None,
                       help="fail if the mutation score is below this (0.0-1.0)")
    p_mut.add_argument("--format", choices=["text", "json"], default="text")
    p_mut.set_defaults(func=cmd_mutation)

    p_risk = sub.add_parser("risk", help="fused complexity x mutation gate")
    p_risk.add_argument("--source", required=True, help="module under test")
    p_risk.add_argument("--tests", required=True, help="pytest file importing `subject`")
    p_risk.add_argument("--max-risk", type=float, default=None,
                        help="fail if any function's risk exceeds this")
    p_risk.add_argument("--format", choices=["text", "json"], default="text")
    p_risk.set_defaults(func=cmd_risk)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
