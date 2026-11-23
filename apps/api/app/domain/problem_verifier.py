"""Check an LLM-written problem against SymPy.

Next to the statement, the generator returns a verification spec: the
function its conditions determine, helper definitions, one check per
condition and an expression for the answer. This module evaluates that spec
with SymPy, so a problem whose stated answer does not follow from its own
conditions never reaches review.

The spec comes from a model, so it is evaluated in a restricted namespace
(whitelisted syntax, no builtins, no private attributes) inside a child
process with a time and memory limit, because SymPy can hang on bad input.

What this does NOT prove: that the conditions determine f uniquely. That is
left to the blind solvers and to human review.
"""
from __future__ import annotations

import ast
import json
import os
import re
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable

from sympy import (
    Abs,
    Max,
    Min,
    N,
    Piecewise,
    Poly,
    Rational,
    S,
    Symbol,
    ceiling,
    diff,
    expand,
    factor,
    floor,
    integrate,
    nsimplify,
    oo,
    pi,
    roots,
    simplify,
    solveset,
    sqf_list,
    sqrt,
    sympify,
)
from sympy.core.relational import Relational
from sympy.logic.boolalg import BooleanFalse, BooleanTrue
from sympy.sets import FiniteSet, Interval, Reals

x = Symbol("x", real=True)
t = Symbol("t", real=True)
_s_var = Symbol("s", real=True)

MAX_RANGE = 2000
DEFAULT_TIMEOUT_SECONDS = 60


# --------------------------------------------------------------------------
# helpers exposed to the spec
# --------------------------------------------------------------------------


def _s(value: Any):
    if isinstance(value, bool):
        return S.true if value else S.false
    if isinstance(value, float):
        return nsimplify(Rational(str(value)))
    return sympify(value)


def at(expr: Any, value: Any):
    """expr with x = value."""
    return simplify(_s(expr).subs(x, _s(value)))


def with_t(expr: Any, value: Any):
    """expr with t = value."""
    return simplify(_s(expr).subs(t, _s(value)))


def d(expr: Any, order: int = 1):
    return diff(_s(expr), x, order)


def _as_poly(expr: Any) -> Poly | None:
    try:
        poly = Poly(expand(_s(expr)), x)
    except Exception:
        return None
    if any(symbol != x for symbol in poly.free_symbols):
        return None
    return poly


def _num(value: Any, digits: int = 60):
    """High-precision real value (drops the ~0 imaginary part Cardano forms leave behind)."""
    return N(value, digits).as_real_imag()[0]


def _sort_key(value: Any) -> float:
    return float(_num(value, 30))


def _unique_sorted(values: list[Any]) -> list[Any]:
    unique: list[Any] = []
    for value in sorted(values, key=_sort_key):
        if not any(same(value, existing) for existing in unique):
            unique.append(value)
    return unique


def real_roots(expr: Any) -> list[Any]:
    """Distinct real solutions of expr = 0 in x, ascending."""
    poly = _as_poly(expr)
    if poly is not None:
        if poly.is_zero:
            raise ValueError("real_roots: expression is identically zero")
        try:
            return _unique_sorted([simplify(root) for root in poly.real_roots()])
        except NotImplementedError:
            # Irrational coefficients (e.g. a parameter like 1 - 8/3^(3/4)). Split off repeated
            # factors first so a triple root stays one exact root; linear factors give exact
            # roots, the rest become 60-digit numbers (Cardano forms cannot be compared with <).
            found: list[Any] = []
            for factor_expr, _multiplicity in sqf_list(poly.as_expr(), x)[1]:
                factor_poly = Poly(factor_expr, x)
                if factor_poly.degree() == 1:
                    coeffs = factor_poly.all_coeffs()
                    found.append(simplify(-coeffs[1] / coeffs[0]))
                    continue
                for root in roots(factor_expr, x):
                    value = N(root, 60)
                    if abs(value.as_real_imag()[1]) < 1e-40:
                        found.append(value.as_real_imag()[0])
            return _unique_sorted(found)
    solutions = solveset(_s(expr), x, Reals)
    if isinstance(solutions, FiniteSet):
        return _unique_sorted(list(solutions))
    raise ValueError(f"real_roots: cannot list the solutions of {expr} = 0")


def root_count(expr: Any) -> int:
    """Number of distinct real solutions of expr = 0."""
    return len(real_roots(expr))


def multiplicity(expr: Any, root: Any) -> int:
    poly = _as_poly(expr)
    if poly is None or poly.is_zero:
        raise ValueError("multiplicity: non-zero polynomial in x required")
    current = poly.as_expr()
    count = 0
    while same(current.subs(x, _s(root)), 0):
        count += 1
        current = diff(current, x)
    return count


def _sign_between(poly_expr: Any, left: Any, right: Any) -> int:
    if left is None and right is None:
        probe = S(0)
    elif left is None:
        probe = _s(right) - 1
    elif right is None:
        probe = _s(left) + 1
    else:
        probe = (_s(left) + _s(right)) / 2
    value = _num(_s(poly_expr).subs(x, probe), 50)
    if value > 0:
        return 1
    if value < 0:
        return -1
    return 0


def _piecewise_extrema(expr: Any) -> list[tuple[Any, Any, str]]:
    """Strict local extrema of a continuous expression built from polynomials, Abs, Piecewise, Max, Min.

    Candidates are the kinks plus the critical points of whichever polynomial
    branch is active on each smooth stretch; each candidate is classified by
    comparing it with points closer than any other candidate. Plateaus (constant
    stretches) are not reported.
    """
    expr = _s(expr)
    kinks = _breakpoints(expr)
    numeric_kinks = [_num(point) for point in kinks]
    edges = [None, *numeric_kinks, None]
    candidates: list[Any] = list(kinks)
    for left, right in zip(edges, edges[1:]):
        if left is None and right is None:
            probe = S(0)
        elif left is None:
            probe = right - 1
        elif right is None:
            probe = left + 1
        else:
            probe = (left + right) / 2
        branch = _resolve_branch(expr, probe)
        derivative = diff(branch, x)
        if _as_poly(derivative) is None or Poly(derivative, x).is_zero:
            continue
        for point in real_roots(derivative):
            numeric = _num(point)
            if (left is None or numeric > left) and (right is None or numeric < right):
                candidates.append(point)
    candidates = _unique_sorted(candidates)
    numeric_candidates = [_num(point) for point in candidates]
    gaps = [b - a for a, b in zip(numeric_candidates, numeric_candidates[1:])]
    delta = min([S(1) / 1000, *[gap / 1000 for gap in gaps]])
    found: list[tuple[Any, Any, str]] = []
    for point, numeric in zip(candidates, numeric_candidates):
        value = N(expr.subs(x, point), 60)
        before = N(expr.subs(x, numeric - delta), 60)
        after = N(expr.subs(x, numeric + delta), 60)
        if value > before and value > after:
            found.append((point, simplify(expr.subs(x, point)), "max"))
        elif value < before and value < after:
            found.append((point, simplify(expr.subs(x, point)), "min"))
    return found


def _extrema(expr: Any) -> list[tuple[Any, Any, str]]:
    poly = _as_poly(expr)
    if poly is None:
        return _piecewise_extrema(expr)
    derivative = diff(poly.as_expr(), x)
    if _as_poly(derivative) is None or Poly(derivative, x).is_zero:
        return []
    critical = real_roots(derivative)
    found: list[tuple[Any, Any, str]] = []
    for index, point in enumerate(critical):
        left = critical[index - 1] if index > 0 else None
        right = critical[index + 1] if index + 1 < len(critical) else None
        before = _sign_between(derivative, left, point)
        after = _sign_between(derivative, point, right)
        value = simplify(poly.as_expr().subs(x, point))
        if before > 0 and after < 0:
            found.append((point, value, "max"))
        elif before < 0 and after > 0:
            found.append((point, value, "min"))
    return found


def local_max(expr: Any) -> list[tuple[Any, Any]]:
    """[(x0, f(x0))] for each local maximum (polynomial, or continuous with |.|/Piecewise/Max/Min)."""
    return [(point, value) for point, value, kind in _extrema(expr) if kind == "max"]


def local_min(expr: Any) -> list[tuple[Any, Any]]:
    return [(point, value) for point, value, kind in _extrema(expr) if kind == "min"]


def local_max_values(expr: Any) -> list[Any]:
    return [value for _, value in local_max(expr)]


def local_min_values(expr: Any) -> list[Any]:
    return [value for _, value in local_min(expr)]


def _breakpoints(expr: Any) -> list[Any]:
    """Points where a piecewise / absolute-value expression may switch form."""
    expr = _s(expr)
    candidates: list[Any] = []
    for node in expr.atoms(Abs):
        candidates.extend(real_roots(node.args[0]))
    for node in expr.atoms(Max, Min):
        args = list(node.args)
        for index, left in enumerate(args):
            for right in args[index + 1:]:
                candidates.extend(real_roots(left - right))
    for node in expr.atoms(Piecewise):
        for _, condition in node.args:
            for relation in (condition.atoms(Relational) if not isinstance(condition, Relational) else {condition}):
                difference = relation.lhs - relation.rhs
                if x in difference.free_symbols:
                    candidates.extend(real_roots(difference))
    return _unique_sorted(candidates)


def _resolve_branch(expr: Any, probe: Any):
    """The smooth formula expr follows at x = probe: |u| -> ±u, Piecewise/Max/Min -> active branch."""
    if expr.is_Atom:
        return expr
    if isinstance(expr, Piecewise):
        for pair in expr.args:
            if bool(pair.cond.subs(x, probe)):
                return _resolve_branch(pair.expr, probe)
        raise ValueError(f"Piecewise has no branch at x = {probe}")
    args = [_resolve_branch(arg, probe) for arg in expr.args]
    if isinstance(expr, Abs):
        inner = args[0]
        return inner if N(inner.subs(x, probe), 60) >= 0 else -inner
    if isinstance(expr, (Max, Min)):
        values = [N(arg.subs(x, probe), 60) for arg in args]
        pick = values.index(max(values)) if isinstance(expr, Max) else values.index(min(values))
        return args[pick]
    return expr.func(*args)


def _side_branches(expr: Any) -> list[tuple[Any, Any, Any]]:
    """For each breakpoint: (point, formula just left of it, formula just right of it).

    The probe is closer to the point than any other breakpoint, so no |u| or
    Piecewise condition changes between the point and the probe. Using exact
    branch formulas instead of sympy.limit keeps this working at irrational
    points such as roots of an irreducible cubic.
    """
    points = _breakpoints(expr)
    numeric = [_num(point) for point in points]
    gaps = [b - a for a, b in zip(numeric, numeric[1:])]
    delta = min([S(1) / 1000, *[gap / 1000 for gap in gaps]])
    return [
        (point, _resolve_branch(expr, at_point - delta), _resolve_branch(expr, at_point + delta))
        for point, at_point in zip(points, numeric)
    ]


def discontinuities(expr: Any) -> list[Any]:
    """x where expr is not continuous (expr built from polynomials, Abs, Piecewise, Max, Min)."""
    expr = _s(expr)
    found: list[Any] = []
    for point, left_branch, right_branch in _side_branches(expr):
        value = expr.subs(x, point)
        if not (same(left_branch.subs(x, point), value) and same(right_branch.subs(x, point), value)):
            found.append(point)
    return found


def nondiff_points(expr: Any) -> list[Any]:
    """x where expr is not differentiable (includes discontinuities)."""
    expr = _s(expr)
    found: list[Any] = []
    for point, left_branch, right_branch in _side_branches(expr):
        value = expr.subs(x, point)
        if not (same(left_branch.subs(x, point), value) and same(right_branch.subs(x, point), value)):
            found.append(point)
            continue
        left_slope = diff(left_branch, x).subs(x, point)
        right_slope = diff(right_branch, x).subs(x, point)
        if not same(left_slope, right_slope):
            found.append(point)
    return found


def is_differentiable(expr: Any) -> bool:
    return not nondiff_points(expr)


def _candidates_on(expr: Any, left: Any, right: Any) -> list[Any]:
    expr = _s(expr)
    points = [_s(left), _s(right)]
    inner = [point for point in _breakpoints(expr) if _s(left) < point < _s(right)]
    points.extend(inner)
    pieces: list[Any] = []
    poly = _as_poly(expr)
    if poly is not None:
        pieces.append(poly.as_expr())
    else:
        for node in expr.atoms(Abs):
            pieces.append(node.args[0])
        for node in expr.atoms(Piecewise):
            pieces.extend(piece for piece, _ in node.args)
        if not pieces:
            raise ValueError("max_on/min_on: unsupported expression")
    for piece in pieces:
        derivative = diff(piece, x)
        if _as_poly(derivative) is None or Poly(derivative, x).is_zero:
            continue
        points.extend(point for point in real_roots(derivative) if _s(left) < point < _s(right))
    return points


def max_on(expr: Any, left: Any, right: Any):
    """Maximum of a continuous expr on the closed interval [left, right]."""
    values = [simplify(_s(expr).subs(x, point)) for point in _candidates_on(expr, left, right)]
    return max(values, key=_sort_key)


def min_on(expr: Any, left: Any, right: Any):
    values = [simplify(_s(expr).subs(x, point)) for point in _candidates_on(expr, left, right)]
    return min(values, key=_sort_key)


def definite(expr: Any, left: Any, right: Any):
    """Definite integral of expr in x from left to right (splits at kinks of |.|)."""
    expr = _s(expr)
    left, right = _s(left), _s(right)
    sign = 1
    if _sort_key(left) > _sort_key(right):
        left, right, sign = right, left, -1
    cuts = [point for point in _breakpoints(expr) if left < point < right]
    edges = [left, *cuts, right]
    total = S(0)
    for start, end in zip(edges, edges[1:]):
        middle = (start + end) / 2
        piece = expr
        for node in expr.atoms(Abs):
            inner = node.args[0]
            piece = piece.subs(node, inner if N(inner.subs(x, middle)) >= 0 else -inner)
        if piece.has(Piecewise):
            piece = piecewise_fold_at(piece, middle)
        total += integrate(piece, (x, start, end))
    return simplify(sign * total)


def piecewise_fold_at(expr: Any, point: Any):
    """Replace every Piecewise in expr by the branch active at x = point."""
    for node in expr.atoms(Piecewise):
        for branch, condition in node.args:
            if bool(condition.subs(x, point)):
                expr = expr.subs(node, branch)
                break
    return expr


def area_between(upper: Any, lower: Any, left: Any, right: Any):
    """Area enclosed between two curves on [left, right]."""
    return definite(Abs(_s(upper) - _s(lower)), left, right)


def prim(expr: Any, lower: Any):
    """The function x -> integral of expr from lower to x."""
    return simplify(integrate(_s(expr).subs(x, _s_var), (_s_var, _s(lower), x)))


def level_jumps(expr: Any) -> list[Any]:
    """t where the number of distinct real roots of expr = t changes (polynomial expr)."""
    poly = _as_poly(expr)
    if poly is None:
        raise ValueError("level_jumps: polynomial in x required")
    derivative = diff(poly.as_expr(), x)
    critical_values = _unique_sorted([simplify(poly.as_expr().subs(x, point)) for point in real_roots(derivative)]) if _as_poly(derivative) is not None and not Poly(derivative, x).is_zero else []
    jumps: list[Any] = []
    for index, value in enumerate(critical_values):
        below = critical_values[index - 1] if index > 0 else value - 2
        above = critical_values[index + 1] if index + 1 < len(critical_values) else value + 2
        count_at = root_count(poly.as_expr() - value)
        count_below = root_count(poly.as_expr() - (below + value) / 2)
        count_above = root_count(poly.as_expr() - (above + value) / 2)
        if count_at != count_below or count_at != count_above:
            jumps.append(value)
    return jumps


def tangent_count(expr: Any, px: Any, py: Any) -> int:
    """Number of distinct tangent lines to y = expr passing through (px, py)."""
    expr = _s(expr)
    a = Symbol("a", real=True)
    fa = expr.subs(x, a)
    slope = diff(expr, x).subs(x, a)
    condition = expand(fa + slope * (_s(px) - a) - _s(py))
    points = real_roots(condition.subs(a, x))
    lines = {(simplify(slope.subs(a, point)), simplify((fa - slope * a).subs(a, point))) for point in points}
    unique: list[tuple[Any, Any]] = []
    for line in lines:
        if not any(same(line[0], other[0]) and same(line[1], other[1]) for other in unique):
            unique.append(line)
    return len(unique)


def same(left: Any, right: Any) -> bool:
    """Exact equality for numbers/expressions; element-wise for lists and tuples."""
    if isinstance(left, (list, tuple)) or isinstance(right, (list, tuple)):
        if not isinstance(left, (list, tuple)) or not isinstance(right, (list, tuple)):
            return False
        return len(left) == len(right) and all(same(a, b) for a, b in zip(left, right))
    left, right = _s(left), _s(right)
    if left.has(oo, -oo) or right.has(oo, -oo):
        return left == right
    difference = left - right
    if difference == 0:
        return True
    # Numbers first: 60 significant digits settle almost every case quickly, while
    # simplify() on radicals (e.g. a counterexample with t = 1 - 8/3^(3/4)) can take minutes.
    if not difference.free_symbols:
        try:
            magnitude = abs(complex(N(difference, 60)))
            scale = max(1.0, abs(complex(N(left, 30))), abs(complex(N(right, 30))))
            return magnitude <= 1e-40 * scale
        except Exception:
            pass
    return simplify(difference) == 0


def _capped_range(*args: int) -> range:
    values = range(*args)
    if len(values) > MAX_RANGE:
        raise ValueError(f"range larger than {MAX_RANGE}")
    return values


HELPERS: dict[str, Callable[..., Any]] = {
    "at": at,
    "with_t": with_t,
    "d": d,
    "real_roots": real_roots,
    "root_count": root_count,
    "multiplicity": multiplicity,
    "local_max": local_max,
    "local_min": local_min,
    "local_max_values": local_max_values,
    "local_min_values": local_min_values,
    "nondiff_points": nondiff_points,
    "discontinuities": discontinuities,
    "is_differentiable": is_differentiable,
    "max_on": max_on,
    "min_on": min_on,
    "definite": definite,
    "area_between": area_between,
    "prim": prim,
    "level_jumps": level_jumps,
    "tangent_count": tangent_count,
    "same": same,
}

SYMPY_NAMES: dict[str, Any] = {
    "x": x,
    "t": t,
    "Abs": Abs,
    "Piecewise": Piecewise,
    "Max": Max,
    "Min": Min,
    "Rational": Rational,
    "sqrt": sqrt,
    "pi": pi,
    "oo": oo,
    "expand": expand,
    "factor": factor,
    "simplify": simplify,
    "floor": floor,
    "ceiling": ceiling,
    "True": True,
    "False": False,
    "None": None,
}

PYTHON_NAMES: dict[str, Any] = {
    "len": len,
    "sum": sum,
    "all": all,
    "any": any,
    "sorted": sorted,
    "abs": abs,
    "min": min,
    "max": max,
    "int": int,
    "range": _capped_range,
}

ALLOWED_ATTRIBUTES = {"subs", "diff", "expand", "factor", "simplify", "is_real", "is_integer", "is_positive", "is_negative", "is_zero"}

ALLOWED_NODES = (
    ast.Expression, ast.BoolOp, ast.And, ast.Or, ast.BinOp, ast.Add, ast.Sub, ast.Mult, ast.Div,
    ast.Pow, ast.Mod, ast.FloorDiv, ast.UnaryOp, ast.USub, ast.UAdd, ast.Not, ast.Compare, ast.Eq,
    ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE, ast.In, ast.NotIn, ast.Call, ast.keyword, ast.Name,
    ast.Load, ast.Store, ast.Constant, ast.List, ast.Tuple, ast.Subscript, ast.Slice, ast.Attribute,
    ast.ListComp, ast.GeneratorExp, ast.comprehension, ast.IfExp,
)

NAME_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,30}$")


class UnsafeExpression(ValueError):
    pass


def _check_syntax(source: str) -> ast.Expression:
    if len(source) > 2000:
        raise UnsafeExpression("expression too long")
    tree = ast.parse(source, mode="eval")
    for node in ast.walk(tree):
        if not isinstance(node, ALLOWED_NODES):
            raise UnsafeExpression(f"syntax not allowed: {type(node).__name__}")
        if isinstance(node, ast.Name) and node.id.startswith("_"):
            raise UnsafeExpression(f"name not allowed: {node.id}")
        if isinstance(node, ast.Attribute) and node.attr not in ALLOWED_ATTRIBUTES:
            raise UnsafeExpression(f"attribute not allowed: {node.attr}")
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and len(node.value) > 2:
            raise UnsafeExpression("string constants are not allowed")
    return tree


def safe_eval(source: str, names: dict[str, Any]) -> Any:
    tree = _check_syntax(source)
    namespace = {"__builtins__": {}}
    namespace.update(PYTHON_NAMES)
    namespace.update(SYMPY_NAMES)
    namespace.update(HELPERS)
    namespace.update(names)
    code = compile(tree, "<spec>", "eval")
    value = eval(code, namespace)  # noqa: S307 - syntax is whitelisted above, builtins removed
    if isinstance(value, float):
        value = _s(value)
    return value


# --------------------------------------------------------------------------
# spec evaluation
# --------------------------------------------------------------------------


@dataclass
class CheckResult:
    condition: str
    expr: str
    ok: bool
    value: str = ""
    error: str = ""


@dataclass
class VerificationReport:
    ok: bool
    answer_value: str = ""
    answer_matches: bool = False
    answer_is_natural: bool = False
    checks: list[CheckResult] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def failure_summary(self) -> list[str]:
        lines = list(self.errors)
        for check in self.checks:
            if not check.ok:
                detail = check.error or f"결과 {check.value}"
                lines.append(f"{check.condition}: `{check.expr}` → {detail}")
        if self.answer_value and not self.answer_matches:
            lines.append(f"answerExpr 계산값 {self.answer_value} 이(가) 적어 낸 정답과 다름")
        if self.answer_value and not self.answer_is_natural:
            lines.append(f"정답 {self.answer_value} 이(가) 1 이상 999 이하의 자연수가 아님")
        return lines


def _truthy(value: Any) -> bool:
    if isinstance(value, (BooleanTrue, BooleanFalse)):
        return bool(value)
    if isinstance(value, bool):
        return value
    if isinstance(value, Relational):
        result = simplify(value)
        if isinstance(result, (BooleanTrue, BooleanFalse)):
            return bool(result)
        raise ValueError(f"comparison could not be decided: {value}")
    raise ValueError(f"check must evaluate to True/False, got {value!r}")


def _short(value: Any) -> str:
    text = str(value)
    return text if len(text) <= 200 else text[:197] + "..."


def evaluate_spec(spec: dict[str, Any], declared_answer: Any) -> VerificationReport:
    report = VerificationReport(ok=False)
    names: dict[str, Any] = {}

    function_source = str(spec.get("f") or "").strip()
    if not function_source:
        report.errors.append("verify.f 가 비어 있음")
        return report
    try:
        names["f"] = _s(safe_eval(function_source, {}))
    except Exception as exc:
        report.errors.append(f"verify.f 를 해석하지 못함: {exc}")
        return report

    for item in spec.get("define") or []:
        if not (isinstance(item, (list, tuple)) and len(item) == 2):
            report.errors.append(f"define 항목 형식 오류: {item!r}")
            return report
        name, source = str(item[0]).strip(), str(item[1])
        if not NAME_PATTERN.match(name) or name in HELPERS or name in SYMPY_NAMES or name in PYTHON_NAMES:
            report.errors.append(f"define 이름을 쓸 수 없음: {name}")
            return report
        try:
            names[name] = safe_eval(source, names)
        except Exception as exc:
            report.errors.append(f"define {name} 실패: {exc}")
            return report

    checks = spec.get("checks") or []
    if not checks:
        report.errors.append("verify.checks 가 비어 있음")
    for item in checks:
        condition = str(item.get("condition") or "") if isinstance(item, dict) else ""
        source = str(item.get("expr") or "") if isinstance(item, dict) else str(item)
        try:
            value = safe_eval(source, names)
            ok = _truthy(value)
            report.checks.append(CheckResult(condition=condition, expr=source, ok=ok, value=_short(value)))
        except Exception as exc:
            report.checks.append(CheckResult(condition=condition, expr=source, ok=False, error=_short(f"{type(exc).__name__}: {exc}")))

    answer_source = str(spec.get("answer") or "").strip()
    if not answer_source:
        report.errors.append("verify.answer 가 비어 있음")
    else:
        try:
            answer_value = simplify(_s(safe_eval(answer_source, names)))
            report.answer_value = _short(answer_value)
            report.answer_is_natural = bool(answer_value.is_integer) and 1 <= int(answer_value) <= 999
            try:
                report.answer_matches = same(answer_value, _s(declared_answer))
            except Exception:
                report.answer_matches = False
        except Exception as exc:
            report.errors.append(f"verify.answer 계산 실패: {type(exc).__name__}: {exc}")

    report.ok = (
        not report.errors
        and bool(report.checks)
        and all(check.ok for check in report.checks)
        and report.answer_matches
        and report.answer_is_natural
    )
    return report


def _limit_child_memory() -> None:
    try:
        import resource

        limit_bytes = 2 * 1024 * 1024 * 1024
        resource.setrlimit(resource.RLIMIT_AS, (limit_bytes, limit_bytes))
    except Exception:
        pass


def verify_problem(spec: dict[str, Any], declared_answer: Any, *, timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS) -> VerificationReport:
    """Evaluate a verification spec in a child process with a time and memory limit."""
    api_root = Path(__file__).resolve().parents[2]
    env = {**os.environ, "PYTHONPATH": str(api_root)}
    try:
        completed = subprocess.run(
            [sys.executable, "-m", "app.domain.problem_verifier"],
            input=json.dumps({"spec": spec, "answer": declared_answer}, ensure_ascii=False),
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            cwd=api_root,
            env=env,
            preexec_fn=_limit_child_memory,
        )
    except subprocess.TimeoutExpired:
        return VerificationReport(ok=False, errors=[f"SymPy 검산이 {timeout_seconds}초 안에 끝나지 않음"])
    try:
        payload = json.loads(completed.stdout.strip().splitlines()[-1])
    except Exception:
        tail = (completed.stderr or "").strip().splitlines()[-1:] or ["no output"]
        return VerificationReport(ok=False, errors=[f"SymPy 검산 프로세스 오류: {tail[0][:200]}"])
    checks = [CheckResult(**item) for item in payload.pop("checks", [])]
    return VerificationReport(checks=checks, **payload)


def _main() -> None:
    request = json.loads(sys.stdin.read())
    try:
        report = evaluate_spec(request.get("spec") or {}, request.get("answer"))
    except Exception as exc:  # defensive: always answer with a report
        report = VerificationReport(ok=False, errors=[f"{type(exc).__name__}: {exc}"])
    print(json.dumps(report.to_dict(), ensure_ascii=False))



HELPER_GUIDE = """사용 가능한 이름 (SymPy, x와 t는 실수 기호)
- f: verify.f 로 적은 함수. define 으로 g, h, k 같은 이름을 차례로 만들 수 있다.
- at(e, v): e에 x=v 대입 / with_t(e, v): e에 t=v 대입 / d(e), d(e, 2): x에 대한 도함수
- real_roots(e): e=0의 서로 다른 실근 (오름차순 리스트) / root_count(e): 그 개수 / multiplicity(p, r): 다항식 p에서 근 r의 중복도
- local_max(e), local_min(e): 극대점·극소점 [(x좌표, 함숫값), ...] (다항식, 또는 Abs·Piecewise·Max·Min으로 만든 연속함수) / local_max_values(e), local_min_values(e): 극댓값·극솟값 리스트
- nondiff_points(e): e가 미분가능하지 않은 x 리스트 (다항식·Abs·Piecewise·Max·Min 조합) / discontinuities(e): 불연속인 x / is_differentiable(e)
- max_on(e, a, b), min_on(e, a, b): 닫힌구간 [a, b]에서 연속함수 e의 최댓값·최솟값
- definite(e, a, b): x에 대한 정적분 / area_between(u, l, a, b): 두 곡선 사이 넓이 / prim(e, a): x에 대한 함수 ∫_a^x e
- level_jumps(p): 실수 t에 대하여 방정식 p(x)=t의 서로 다른 실근 개수가 바뀌는 t 리스트
- tangent_count(p, a, b): 점 (a, b)를 지나는 곡선 y=p(x)의 접선 개수
- same(u, v): 수·식·리스트가 같은지 (== 대신 이것을 쓸 것)
- Abs, Piecewise((식, 조건), ...), Max, Min, Rational(p, q), sqrt, pi, expand, factor, simplify, floor, ceiling
- len, sum, all, any, sorted, min, max, abs, int, range, 리스트 컴프리헨션
- 쓸 수 없는 것: import, lambda, 문자열, 밑줄로 시작하는 이름, 위에 없는 메서드"""


if __name__ == "__main__":
    _main()
