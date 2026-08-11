"""Tests for the cyclomatic complexity engine.

Each expected value is worked out by hand from the McCabe decision-point
rules so we know the engine agrees with the definition, not just with itself.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.analysis.complexity import analyze_source


def _score(source: str, name: str) -> int:
    result = analyze_source(source)
    for fn in result.functions:
        if fn.name == name:
            return fn.complexity
    raise AssertionError(f"function {name!r} not found in {[f.name for f in result.functions]}")


def test_trivial_function_is_one():
    src = "def f():\n    return 1\n"
    assert _score(src, "f") == 1


def test_single_if_adds_one():
    src = (
        "def f(x):\n"
        "    if x:\n"
        "        return 1\n"
        "    return 0\n"
    )
    assert _score(src, "f") == 2


def test_if_elif_else():
    # base 1 + if 1 + elif 1 = 3 (else adds nothing)
    src = (
        "def f(x):\n"
        "    if x == 1:\n"
        "        return 'a'\n"
        "    elif x == 2:\n"
        "        return 'b'\n"
        "    else:\n"
        "        return 'c'\n"
    )
    assert _score(src, "f") == 3


def test_boolean_operators():
    # base 1 + (a and b and c -> 2)
    src = (
        "def f(a, b, c):\n"
        "    return a and b and c\n"
    )
    assert _score(src, "f") == 3


def test_loop_with_nested_if_and_except():
    # base 1 + for 1 + if 1 + except 1 = 4
    src = (
        "def f(items):\n"
        "    for i in items:\n"
        "        if i:\n"
        "            try:\n"
        "                do(i)\n"
        "            except Exception:\n"
        "                pass\n"
    )
    assert _score(src, "f") == 4


def test_comprehension_filter():
    # base 1 + one 'if' filter = 2
    src = (
        "def f(xs):\n"
        "    return [x for x in xs if x > 0]\n"
    )
    assert _score(src, "f") == 2


def test_ternary():
    src = (
        "def f(x):\n"
        "    return 1 if x else 0\n"
    )
    assert _score(src, "f") == 2


def test_match_statement():
    # base 1 + two real cases (+2); wildcard default adds nothing = 3
    src = (
        "def f(x):\n"
        "    match x:\n"
        "        case 1:\n"
        "            return 'a'\n"
        "        case 2:\n"
        "            return 'b'\n"
        "        case _:\n"
        "            return 'z'\n"
    )
    assert _score(src, "f") == 3


def test_method_gets_dotted_name():
    src = (
        "class C:\n"
        "    def m(self, x):\n"
        "        if x:\n"
        "            return 1\n"
        "        return 0\n"
    )
    assert _score(src, "C.m") == 2


def test_nested_function_measured_separately():
    src = (
        "def outer(x):\n"
        "    def inner(y):\n"
        "        if y:\n"
        "            return 1\n"
        "        return 0\n"
        "    if x:\n"
        "        return inner(x)\n"
        "    return 0\n"
    )
    # outer should NOT absorb inner's branch
    assert _score(src, "outer") == 2
    assert _score(src, "outer.inner") == 2


def test_decorator_ternary_not_counted():
    # A ternary in a decorator belongs to the enclosing scope, not the body.
    src = (
        "@deco('a' if DEBUG else 'b')\n"
        "def f():\n"
        "    return 1\n"
    )
    assert _score(src, "f") == 1


def test_default_arg_ternary_not_counted():
    # A ternary in a default value is evaluated at def time, not in the body.
    src = (
        "def f(x=1 if A else 2):\n"
        "    return x\n"
    )
    assert _score(src, "f") == 1


def test_module_summary():
    src = (
        "def a():\n"
        "    return 1\n"
        "def b(x):\n"
        "    if x:\n"
        "        return 1\n"
        "    return 0\n"
    )
    result = analyze_source(src)
    assert result.total_complexity == 3  # 1 + 2
    assert result.max_complexity == 2
    assert result.average_complexity == 1.5
