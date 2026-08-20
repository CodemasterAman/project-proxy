<div align="center">

# /susgrade

### See what's *actually* worth testing.

**susgrade** is a test-effectiveness analysis tool for Python. It brings together **structural complexity** and **test quality** into a single, plain-language risk report — so you always know where your testing effort will pay off next.

[![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![Pydantic](https://img.shields.io/badge/Pydantic-2.10-E92063?logo=pydantic&logoColor=white)](https://docs.pydantic.dev/)
![Tests](https://img.shields.io/badge/tests-13%20passing-brightgreen)
![License](https://img.shields.io/badge/license-MIT-blue)
![Status](https://img.shields.io/badge/status-active-success)

</div>

![susgrade — the landing experience and live analyzer](docs/screenshots/hero.png)

---

## Table of Contents

- [Why susgrade](#why-susgrade)
- [The Core Idea](#the-core-idea)
- [Features](#features)
- [Architecture](#architecture)
- [Tech Stack](#tech-stack)
- [Getting Started](#getting-started)
- [Using the Analyzer](#using-the-analyzer)
- [API Reference](#api-reference)
- [How the Complexity Engine Works](#how-the-complexity-engine-works)
- [Testing & Validation](#testing--validation)
- [Roadmap & Vision](#roadmap--vision)
- [The Frontend](#the-frontend)
- [Team](#team)
- [Acknowledgments](#acknowledgments)
- [License](#license)

---

## Why susgrade

Writing tests is easy. Knowing *which* code deserves them is hard — especially for developers early in their careers.

Two questions decide where testing effort actually pays off:

1. **Where is the risk?** Complex, branch-heavy functions have many execution paths, and every path is a place a bug can hide.
2. **Is that risk actually tested?** Line coverage tells you a line *ran* — not that a test would *catch a bug* in it.

Most tools answer these questions separately. Coverage reports show what executed; complexity tools show what's tangled. Neither points you to the overlap — **the code that is both complex *and* weakly tested**. That overlap is exactly where real bugs survive.

susgrade exists to surface that overlap, and to make it approachable enough that a single developer with limited testing experience can act on it without a dedicated QA background. The metrics stay standard and defensible; the presentation stays human.

---

## The Core Idea

susgrade is built on two established, well-understood software-quality signals.

### 1. Cyclomatic Complexity — *how much there is to test*

Cyclomatic complexity (McCabe, 1976) measures the number of linearly independent paths through a function. In practice, it is the number of decision points plus one. A function with a complexity of `1` is a straight line; a function with a complexity of `20` has twenty independent ways to flow through it — twenty behaviours a thorough test suite has to account for. Higher complexity means more places for defects to hide and more effort required to test responsibly.

### 2. Mutation Score — *how good the tests actually are*

Mutation testing deliberately introduces small faults ("mutants") into the code — flipping a `>` to `>=`, a `+` to `-`, a `True` to `False` — and re-runs the existing test suite against each variant. If a test fails, it "killed" the mutant (good — the tests would have caught that bug). If every test still passes, a real defect just slipped through undetected. The **mutation score** is the fraction of mutants killed, and it measures test *effectiveness* in a way that line coverage never can.

> susgrade now ships a working mutation engine — operators for arithmetic, relational, logical, unary, boolean-constant and numeric-constant changes — exposed through both the API and the web UI. The remaining piece of the vision, automatically **fusing** complexity and mutation score into one ranked risk report, is next; see [Roadmap & Vision](#roadmap--vision).

### Fusing them into one signal

Complexity tells you how much *could* go wrong. Mutation score tells you how much your tests would actually *catch*. susgrade's guiding formula combines the two:

```
risk = complexity × (1 − mutation_score)
```

A function that is **complex and poorly tested** rises to the top of the list. A trivial function — or a complex one that is already well tested — sinks to the bottom. The output is a ranked, plain-language answer to one question: **what should I test next?**

---

## Features

| | Capability | Status |
|:---:|---|:---:|
| ✅ | **Cyclomatic complexity engine** — per-function McCabe complexity computed from Python's `ast` | **Implemented** |
| ✅ | **Risk banding** — every function classified from *simple* to *very complex* | **Implemented** |
| ✅ | **REST API** — `POST /analyze/complexity`, `POST /analyze/mutation`, `GET /health`, built on FastAPI + Pydantic | **Implemented** |
| ✅ | **Interactive web UI** — live in-browser analyzer, ready-made sample snippets, light/dark theme, fully responsive | **Implemented** |
| ✅ | **Validated metrics** — 13 unit tests, cross-checked against `radon` | **Implemented** |
| ✅ | **Mutation-testing engine** — inject mutants, run your suite against each, and score kills vs. survivors | **Implemented** |
| ✅ | **Interactive mutation UI** — paste code and tests, run against the backend, see the score and every surviving mutant | **Implemented** |
| ◆ | **Fused risk report** — rank functions by `complexity × (1 − mutation score)` | Planned |
| ◆ | **Multi-language support** — analysis beyond Python via Tree-sitter | Planned |
| ◆ | **CI integration & exportable reports** — run in a pipeline, download results | Planned |

---

## Architecture

susgrade is intentionally split into a metrics **engine + API** and a self-contained **web client**, so the analysis logic can be reused (CLI, CI, other frontends) without being tied to any single interface.

```
susgrade/
├── backend/                        FastAPI service — the analysis engine and API
│   ├── app/
│   │   ├── main.py                 API application and route definitions
│   │   ├── models.py               Pydantic request/response schemas
│   │   └── analysis/
│   │       └── complexity.py       Cyclomatic complexity engine (ast-based)
│   ├── tests/
│   │   └── test_complexity.py      pytest suite (13 tests, radon-validated)
│   └── requirements.txt            Pinned Python dependencies
│
├── frontend/
│   └── index.html                  Interactive analyzer UI — single, self-contained file
│
├── docs/
│   ├── susgrade_SRS.docx           Software Requirements Specification (IEEE-830)
│   └── screenshots/                Images used in this README
│
└── README.md
```

**Data flow.** Python source enters through the API (or the in-browser estimator), is parsed into an abstract syntax tree, walked to count decision points per function, scored, banded, and returned as structured JSON. The frontend renders that result and mirrors the same logic client-side for instant feedback.

---

## Tech Stack

| Layer | Technology |
|---|---|
| **Language** | Python 3.10+ |
| **API framework** | FastAPI |
| **Data validation** | Pydantic v2 |
| **ASGI server** | Uvicorn |
| **Static analysis** | Python standard-library `ast` (McCabe decision-point method) |
| **Testing** | pytest — cross-validated against `radon` |
| **Frontend** | Vanilla HTML, CSS, and JavaScript — no build step, no framework |
| **Specification** | IEEE-830 Software Requirements Specification |

---

## Getting Started

### Prerequisites

- **Python 3.10 or newer**
- No database, API keys, or external services are required.

### 1. Run the backend

```bash
cd backend

# Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate         # Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Start the API (auto-reloads on change)
uvicorn app.main:app --reload
```

The API is now live at **http://127.0.0.1:8000**, with interactive Swagger documentation at **http://127.0.0.1:8000/docs**.

### 2. Open the frontend

The frontend is a single self-contained file with no build step. Simply open it in a browser:

```bash
# From the project root
open frontend/index.html          # macOS
# or: xdg-open frontend/index.html (Linux)  |  start frontend/index.html (Windows)
```

The live analyzer estimates complexity entirely in the browser, so it works standalone. Run the backend as well to exercise the full API-backed analysis.

---

## Using the Analyzer

Paste any Python into the analyzer (or pick one of the built-in samples) and susgrade reports the cyclomatic complexity of every function, along with a risk band that tells you how much attention it warrants:

| Complexity | Band | What it means |
|:---:|---|---|
| **1 – 5** | `simple` | Low risk. Straightforward logic that is easy to test. |
| **6 – 10** | `moderate` | Reasonable, but worth a deliberate set of tests. |
| **11 – 20** | `complex` | High risk. Many paths — test thoroughly and consider refactoring. |
| **21+** | `very complex` | Very high risk. A strong candidate for refactoring before it grows further. |

These thresholds follow common McCabe risk guidance, so the numbers are directly comparable to what a reviewer, grader, or established tool would expect.

---

## API Reference

Base URL (development): `http://127.0.0.1:8000`

### `GET /health`

A liveness check.

**Response** — `200 OK`

```json
{ "status": "ok" }
```

### `POST /analyze/complexity`

Compute the cyclomatic complexity of every function in a Python snippet.

**Request body**

```json
{
  "source": "def classify(n):\n    if n < 0:\n        return 'neg'\n    elif n == 0:\n        return 'zero'\n    return 'pos'"
}
```

**Response** — `200 OK`

```json
{
  "functions": [
    {
      "name": "classify",
      "lineno": 1,
      "end_lineno": 6,
      "complexity": 3,
      "rank": "simple"
    }
  ],
  "total_complexity": 3,
  "average_complexity": 3.0,
  "max_complexity": 3
}
```

| Field | Type | Description |
|---|---|---|
| `functions[].name` | string | Function name; methods use a dotted path, e.g. `MyClass.method`. |
| `functions[].lineno` / `end_lineno` | int | The function's start and end line numbers. |
| `functions[].complexity` | int | Cyclomatic complexity for that function. |
| `functions[].rank` | string | Risk band: `simple`, `moderate`, `complex`, or `very complex`. |
| `total_complexity` | int | Sum of all function complexities. |
| `average_complexity` | float | Mean complexity across functions. |
| `max_complexity` | int | The single highest complexity found. |

**Error** — `422 Unprocessable Entity` (source could not be parsed)

```json
{ "detail": "Could not parse Python source: invalid syntax (line 2)" }
```

### `POST /analyze/mutation`

Run mutation testing: mutate the code under test and score how many mutants the supplied test suite kills. The code is exposed to the tests as a module named `subject`, so tests import from it.

**Request body**

```json
{
  "source": "def grade(score):\n    if score >= 60:\n        return 'pass'\n    return 'fail'\n",
  "tests": "from subject import grade\n\ndef test_pass():\n    assert grade(90) == 'pass'\n"
}
```

**Response** — `200 OK`

```json
{
  "total_generated": 4,
  "total_run": 4,
  "killed": 1,
  "survived": 3,
  "timed_out": 0,
  "mutation_score": 0.25,
  "baseline_passed": true,
  "survivors": [
    { "operator": "ROR", "description": "'>=' -> '>'", "lineno": 2 },
    { "operator": "NCR", "description": "60 -> 61", "lineno": 2 }
  ]
}
```

| Field | Type | Description |
|---|---|---|
| `total_generated` | int | Total mutants produced from the source. |
| `total_run` | int | Mutants actually executed (capped for large inputs). |
| `killed` / `survived` | int | Mutants the tests caught vs. missed. |
| `timed_out` | int | Mutants that hung (e.g. an introduced infinite loop); counted as killed. |
| `mutation_score` | float | `killed / total_run` — higher means more effective tests. |
| `baseline_passed` | bool | Whether the tests pass on the **unmodified** code. If `false`, no mutants are run. |
| `survivors[]` | list | Each surviving mutant's operator, human-readable change, and line number — your test gaps. |

Mutation operators applied: arithmetic (`AOR`), relational (`ROR`), logical (`LOR`), unary (`UOR`), boolean-constant (`BCR`), and numeric-constant (`NCR`).

> **Note:** this endpoint executes the submitted code and tests, so run the service in a trusted/local environment. Each run is bounded by a per-mutant timeout.

---

## How the Complexity Engine Works

The engine (`backend/app/analysis/complexity.py`) parses source with Python's standard-library `ast` module and computes complexity using the **McCabe decision-point method**: every function starts at a base of **1**, and each control-flow branch point adds **1**. This is the same convention used by tools like `radon`, which keeps susgrade's numbers comparable and verifiable.

**Constructs that add a decision point:**

- `if` / `elif` — each branch
- `for` / `async for`
- `while`
- `except` — each handler
- **Boolean operators** — each extra operand (`a and b and c` adds `2`)
- **Conditional expressions** — the ternary `x if c else y`
- **Comprehension filters** — each `if` clause inside a comprehension
- **`match` cases** — each `case`, excluding a bare wildcard default

**Deliberate design choices:**

- **Per-function scoring.** Nested functions are scored as their own units rather than inflating the enclosing function.
- **Dotted names.** Methods and nested definitions are reported with a qualified name (e.g. `RequestRouter.dispatch`) so results are unambiguous.
- **No false inflation.** Constructs that don't represent runtime branches — such as decorators, or a ternary used only in a default argument value — are excluded, so scores reflect genuine control flow.

---

## Testing & Validation

The complexity engine is covered by **13 unit tests** in `backend/tests/test_complexity.py`, each with a hand-verified expected score spanning every risk band and language construct listed above. As an independent check, the engine's output was **cross-validated against [`radon`](https://radon.readthedocs.io/)** and matches on a per-function basis.

```bash
cd backend
pytest -q
```

```
.............                                                             [100%]
13 passed
```

---

## Roadmap & Vision

The complexity and mutation engines are both in place, each with its own API and web UI. The path ahead completes the test-effectiveness vision described in [The Core Idea](#the-core-idea):

- **The fused risk report** — combine complexity and mutation score into a single ranked list (`risk = complexity × (1 − mutation_score)`) that answers *"what should I test next?"* directly.
- **Multi-language analysis** — extend beyond Python using Tree-sitter grammars, so the same risk model applies to other codebases.
- **Automation** — a CLI and CI integration, plus exportable reports, so susgrade can run as a quality gate inside a pipeline.

This roadmap reflects the product's intended direction; the specification for these stages lives alongside the code in [`docs/susgrade_SRS.docx`](docs/susgrade_SRS.docx).

---

## The Frontend

The interface in `frontend/index.html` is a single, dependency-free file — no build tooling, no framework, and nothing to install. It presents susgrade as a complete product experience and includes:

- A **live complexity analyzer** that mirrors the engine's logic in the browser for instant, offline feedback.
- A **mutation testing panel** — paste your code and its tests, run them against the backend, and see the mutation score plus every surviving mutant with its line and change.
- **Built-in sample snippets** across the full range of risk bands, so the tool is useful on first open.
- A **light/dark theme** that remembers your preference, motion-aware animations, a custom scalable SVG wordmark, and a **fully responsive layout** from mobile to ultrawide.

The mutation panel runs live against the backend. Capabilities still on the [roadmap](#roadmap--vision) — the fused risk report and multi-language support — are surfaced in the UI as clearly-labelled "coming soon" states, so the interface communicates the full vision without overstating what ships today.

---

## Team

Built as a Software Verification and Testing project (course **CSE4149**) at **Manipal University Jaipur**.

| Name | Registration |
|---|---|
| **Aman Behera** | 23FE10CSE00697 |
| **Bhomik Jain** | 23FE10CSE00707 |

---

## Acknowledgments

- **Thomas J. McCabe** — for the cyclomatic complexity metric that anchors the engine.
- **[radon](https://radon.readthedocs.io/)** — used to independently validate our complexity scores.
- **[FastAPI](https://fastapi.tiangolo.com/)**, **[Pydantic](https://docs.pydantic.dev/)**, and Python's **[`ast`](https://docs.python.org/3/library/ast.html)** module — the foundations of the service.

---

## License

Released under the **MIT License**. See [`LICENSE`](LICENSE) for the full text.
