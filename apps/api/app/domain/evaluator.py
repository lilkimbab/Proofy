from __future__ import annotations

import re
from dataclasses import dataclass
from fractions import Fraction
from typing import Protocol

from sympy import Eq, Rational, Symbol, diff, simplify, solve, sympify
from sympy.core.expr import Expr
from sympy.parsing.sympy_parser import (
    convert_xor,
    implicit_multiplication_application,
    parse_expr,
    standard_transformations,
)
from sympy.abc import x, y

from app.domain.models import PracticeStepFeedback


TRANSFORMATIONS = standard_transformations + (
    implicit_multiplication_application,
    convert_xor,
)
SYMBOL_MAP = {
    "x": x,
    "y": y,
    "n": Symbol("n"),
    "k": Symbol("k"),
    "a": Symbol("a"),
    "b": Symbol("b"),
    "c": Symbol("c"),
    "p": Symbol("p"),
    "q": Symbol("q"),
    "r": Symbol("r"),
    "t": Symbol("t"),
}


@dataclass(frozen=True)
class TangentProblemSpec:
    function_expression: str
    point_x: int


@dataclass(frozen=True)
class MaxMinProblemSpec:
    function_expression: str


@dataclass(frozen=True)
class StructuredStepSpec:
    label: str
    mode: str
    expected: list[str]
    hint: str
    success_reason: str
    error_type: str | None = None
    expected_display: str | None = None


@dataclass(frozen=True)
class StructuredProblemSpec:
    steps: list[StructuredStepSpec]
    final: StructuredStepSpec


class PracticeEvaluator(Protocol):
    def evaluate(self, submission: dict[str, str]) -> list[PracticeStepFeedback]: ...


def _normalize_text(value: str) -> str:
    return (
        (value or "")
        .replace("−", "-")
        .replace("—", "-")
        .replace("×", "*")
        .replace("÷", "/")
        .replace("^", "**")
    )


def _split_segments(value: str) -> list[str]:
    return [segment.strip() for segment in re.split(r"[\n;,]", value) if segment.strip()]


def _is_answer_only_submission(submission: dict[str, str]) -> bool:
    final_answer = (submission.get("finalAnswer") or "").strip()
    if not final_answer:
        return False
    return not any((submission.get(key) or "").strip() for key in ("stepOne", "stepTwo", "stepThree"))


def _expr_candidates(value: str) -> list[str]:
    candidates: list[str] = []
    for segment in _split_segments(_normalize_text(value)):
        if "=" in segment:
            parts = [part.strip() for part in segment.split("=") if part.strip()]
            candidates.extend(parts[1:] or parts)
        else:
            candidates.append(segment)
    return candidates


def _clean_fragment(fragment: str, *, keep_y: bool = False) -> str:
    cleaned = re.sub(r"[가-힣,:]", " ", fragment)
    cleaned = re.sub(r"[^0-9A-Za-z\+\-\*/\(\)\.\s_]", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def _parse_expr(fragment: str) -> Expr | None:
    cleaned = _clean_fragment(fragment)
    if not cleaned:
        return None
    try:
        return parse_expr(
            cleaned,
            transformations=TRANSFORMATIONS,
            evaluate=True,
            local_dict=SYMBOL_MAP,
        )
    except Exception:
        return None


def _parse_equation(fragment: str) -> Eq | None:
    normalized = _normalize_text(fragment)
    if "=" not in normalized:
        return None
    left_text, right_text = normalized.split("=", 1)
    left = _parse_expr(_clean_fragment(left_text, keep_y=True))
    right = _parse_expr(_clean_fragment(right_text, keep_y=True))
    if left is None or right is None:
        return None
    return Eq(left, right)


def _parse_point(value: str) -> tuple[Expr, Expr] | None:
    match = re.search(r"\(\s*([\-0-9\.\/]+)\s*,\s*([\-0-9\.\/]+)\s*\)", _normalize_text(value))
    if not match:
        return None
    try:
        return sympify(match.group(1)), sympify(match.group(2))
    except Exception:
        return None


def _parse_all_points(value: str) -> list[tuple[Expr, Expr]]:
    matches = re.findall(r"\(\s*([\-0-9\.\/]+)\s*,\s*([\-0-9\.\/]+)\s*\)", _normalize_text(value))
    points: list[tuple[Expr, Expr]] = []
    for left, right in matches:
        try:
            points.append((sympify(left), sympify(right)))
        except Exception:
            continue
    return points


def _parse_number_tokens(value: str) -> list[Expr]:
    tokens = re.findall(r"(?<![a-zA-Z])\-?\d+(?:/\d+)?(?:\.\d+)?", _normalize_text(value))
    values: list[Expr] = []
    for token in tokens:
        try:
            if "/" in token:
                values.append(sympify(Fraction(token)))
            else:
                values.append(sympify(token))
        except Exception:
            continue
    return values


def _sorted_real_roots(expr: Expr) -> list[Expr]:
    roots = solve(Eq(expr, 0), x)
    real_roots = [simplify(root) for root in roots if getattr(root, "is_real", True) is not False]
    unique: list[Expr] = []
    for root in real_roots:
        if not any(simplify(root - existing) == 0 for existing in unique):
            unique.append(root)
    return sorted(unique, key=lambda item: float(item))


def _normalize_exact_text(value: str) -> str:
    normalized = _normalize_text(value or "").lower()
    normalized = re.sub(r"\s+", "", normalized)
    return normalized


def _parse_expected_expr(value: str) -> Expr | None:
    equation = _parse_equation(value)
    if equation is not None:
        return simplify(equation.lhs - equation.rhs)
    return _parse_expr(value)


def _matches_expression(value: str, expected_values: list[str]) -> bool:
    expected_exprs = [
        parsed
        for parsed in (_parse_expected_expr(item) for item in expected_values)
        if parsed is not None
    ]
    if not expected_exprs:
        return False
    equations = [_parse_equation(segment) for segment in _split_segments(value)]
    for equation in equations:
        if equation is None:
            continue
        candidate = simplify(equation.lhs - equation.rhs)
        if any(simplify(candidate - expected) == 0 for expected in expected_exprs):
            return True
    for candidate_text in _expr_candidates(value):
        candidate = _parse_expected_expr(candidate_text)
        if candidate is None:
            continue
        if any(simplify(candidate - expected) == 0 for expected in expected_exprs):
            return True
    return False


def _matches_numeric(value: str, expected_values: list[str]) -> bool:
    tokens = _parse_number_tokens(value)
    if not tokens:
        return False
    expected = [sympify(item) for item in expected_values]
    return all(any(simplify(token - item) == 0 for token in tokens) for item in expected)


def _matches_solution_set(value: str, expected_values: list[str]) -> bool:
    expected = [simplify(sympify(item)) for item in expected_values]
    found = _parse_number_tokens(value)
    if not found:
        return False
    unique_found: list[Expr] = []
    for item in found:
        simplified = simplify(item)
        if not any(simplify(simplified - existing) == 0 for existing in unique_found):
            unique_found.append(simplified)
    if len(unique_found) != len(expected):
        return False
    return all(any(simplify(item - existing) == 0 for existing in unique_found) for item in expected)


def _matches_exact(value: str, expected_values: list[str]) -> bool:
    normalized = _normalize_exact_text(value)
    return any(_normalize_exact_text(expected) == normalized for expected in expected_values)


def _expected_display(spec: StructuredStepSpec) -> str:
    if spec.expected_display:
        return spec.expected_display
    if spec.mode == "solution-set":
        return ", ".join(spec.expected)
    if spec.mode == "exact-match":
        return " / ".join(spec.expected)
    return spec.expected[0] if spec.expected else ""


def _matches_mode(mode: str, value: str, expected_values: list[str]) -> bool:
    if mode == "numeric":
        return _matches_numeric(value, expected_values)
    if mode == "solution-set":
        return _matches_solution_set(value, expected_values)
    if mode == "exact-match":
        return _matches_exact(value, expected_values)
    return _matches_expression(value, expected_values)


class StructuredPracticeEvaluator:
    def __init__(self, spec: StructuredProblemSpec):
        self.spec = spec

    def evaluate(self, submission: dict[str, str]) -> list[PracticeStepFeedback]:
        if _is_answer_only_submission(submission):
            return [
                self._grade(
                    feedback_id="final",
                    value=submission.get("finalAnswer", ""),
                    spec=self.spec.final,
                )
            ]
        feedback: list[PracticeStepFeedback] = []
        step_values = [
            submission.get("stepOne", ""),
            submission.get("stepTwo", ""),
            submission.get("stepThree", ""),
        ]
        for index, step_spec in enumerate(self.spec.steps):
            feedback.append(
                self._grade(
                    feedback_id=f"step-{index + 1}",
                    value=step_values[index] if index < len(step_values) else "",
                    spec=step_spec,
                )
            )
        feedback.append(
            self._grade(
                feedback_id="final",
                value=submission.get("finalAnswer", ""),
                spec=self.spec.final,
            )
        )
        return feedback

    def _grade(
        self,
        *,
        feedback_id: str,
        value: str,
        spec: StructuredStepSpec,
    ) -> PracticeStepFeedback:
        if not (value or "").strip():
            return PracticeStepFeedback(
                id=feedback_id,
                label=spec.label,
                accepted=False,
                reason=spec.hint,
                expected=_expected_display(spec),
                error_type=spec.error_type or "missing-step",
            )
        if _matches_mode(spec.mode, value, spec.expected):
            return PracticeStepFeedback(
                id=feedback_id,
                label=spec.label,
                accepted=True,
                reason=spec.success_reason,
                expected=_expected_display(spec),
            )
        return PracticeStepFeedback(
            id=feedback_id,
            label=spec.label,
            accepted=False,
            reason=spec.hint,
            expected=_expected_display(spec),
            error_type=spec.error_type or "concept",
        )


class SymPyTangentEvaluator:
    def __init__(self, spec: TangentProblemSpec):
        self.spec = spec
        self.function = parse_expr(spec.function_expression, transformations=TRANSFORMATIONS)
        self.derivative = simplify(diff(self.function, x))
        self.point_x = sympify(spec.point_x)
        self.slope = simplify(self.derivative.subs(x, self.point_x))
        self.point_y = simplify(self.function.subs(x, self.point_x))
        self.line = Eq(y, simplify(self.slope * (x - self.point_x) + self.point_y))

    def evaluate(self, submission: dict[str, str]) -> list[PracticeStepFeedback]:
        if _is_answer_only_submission(submission):
            return [self._grade_final(submission.get("finalAnswer", ""))]
        return [
            self._grade_step_one(submission.get("stepOne", "")),
            self._grade_step_two(submission.get("stepTwo", "")),
            self._grade_step_three(submission.get("stepThree", "")),
            self._grade_final(submission.get("finalAnswer", "")),
        ]

    def _grade_step_one(self, value: str) -> PracticeStepFeedback:
        if not value.strip():
            return PracticeStepFeedback(
                id="step-1",
                label="도함수 계산",
                accepted=False,
                reason="도함수를 먼저 적어야 접선 기울기를 구할 수 있습니다.",
                expected=f"f'(x) = {self.derivative}",
                error_type="missing-step",
            )
        wrong_sign = simplify(diff(parse_expr("x**2 + 4*x + 3"), x))
        for candidate in _expr_candidates(value):
            expr = _parse_expr(candidate)
            if expr is None:
                continue
            if simplify(expr - self.derivative) == 0:
                return PracticeStepFeedback(
                    id="step-1",
                    label="도함수 계산",
                    accepted=True,
                    reason="SymPy 기준으로 도함수를 정확히 계산했습니다.",
                    expected=f"f'(x) = {self.derivative}",
                )
            if simplify(expr - wrong_sign) == 0:
                return PracticeStepFeedback(
                    id="step-1",
                    label="도함수 계산",
                    accepted=False,
                    reason="-4x를 미분한 결과의 부호가 뒤집혔습니다.",
                    expected=f"f'(x) = {self.derivative}",
                    error_type="sign-error",
                )
        return PracticeStepFeedback(
            id="step-1",
            label="도함수 계산",
            accepted=False,
            reason="도함수 형태가 맞지 않습니다. 항별 미분을 다시 확인해 보세요.",
            expected=f"f'(x) = {self.derivative}",
            error_type="concept",
        )

    def _grade_step_two(self, value: str) -> PracticeStepFeedback:
        if not value.strip():
            return PracticeStepFeedback(
                id="step-2",
                label="기울기 계산",
                accepted=False,
                reason="도함수에 x값을 넣어 접선 기울기를 구해야 합니다.",
                expected=f"f'({self.point_x}) = {self.slope}",
                error_type="missing-step",
            )
        for candidate in _expr_candidates(value):
            expr = _parse_expr(candidate)
            if expr is None:
                continue
            if simplify(expr - self.slope) == 0:
                return PracticeStepFeedback(
                    id="step-2",
                    label="기울기 계산",
                    accepted=True,
                    reason="SymPy 기준으로 접선의 기울기를 정확히 찾았습니다.",
                    expected=f"f'({self.point_x}) = {self.slope}",
                )
            if simplify(expr - abs(self.slope)) == 0:
                return PracticeStepFeedback(
                    id="step-2",
                    label="기울기 계산",
                    accepted=False,
                    reason="대입 후 정리에서 부호가 한 번 더 뒤집힌 것으로 보입니다.",
                    expected=f"f'({self.point_x}) = {self.slope}",
                    error_type="arithmetic",
                )
        return PracticeStepFeedback(
            id="step-2",
            label="기울기 계산",
            accepted=False,
            reason="기울기 단계는 도함수값 하나로 끝납니다. 대입과 정리를 다시 점검해 보세요.",
            expected=f"f'({self.point_x}) = {self.slope}",
            error_type="concept",
        )

    def _grade_step_three(self, value: str) -> PracticeStepFeedback:
        if not value.strip():
            return PracticeStepFeedback(
                id="step-3",
                label="접점 계산",
                accepted=False,
                reason="같은 x값을 원함수에 넣어 접점을 구해야 합니다.",
                expected=f"({self.point_x}, {self.point_y})",
                error_type="missing-step",
            )
        point = _parse_point(value)
        if point is not None and simplify(point[0] - self.point_x) == 0 and simplify(point[1] - self.point_y) == 0:
            return PracticeStepFeedback(
                id="step-3",
                label="접점 계산",
                accepted=True,
                reason="접점 좌표를 정확히 찾았습니다.",
                expected=f"({self.point_x}, {self.point_y})",
            )
        for candidate in _expr_candidates(value):
            expr = _parse_expr(candidate)
            if expr is None:
                continue
            if simplify(expr - self.point_y) == 0:
                return PracticeStepFeedback(
                    id="step-3",
                    label="접점 계산",
                    accepted=True,
                    reason="원함수 대입값이 맞습니다. 접점 좌표로 이어질 수 있습니다.",
                    expected=f"({self.point_x}, {self.point_y})",
                )
        return PracticeStepFeedback(
            id="step-3",
            label="접점 계산",
            accepted=False,
            reason="접점이 빠졌거나 좌표가 다릅니다. 원함수에 x값을 대입해 y값을 다시 구하세요.",
            expected=f"({self.point_x}, {self.point_y})",
            error_type="missing-point",
        )

    def _grade_final(self, value: str) -> PracticeStepFeedback:
        expected_line = f"y = {solve(self.line, y)[0]}"
        if not value.strip():
            return PracticeStepFeedback(
                id="final",
                label="최종 답",
                accepted=False,
                reason="최종 직선식을 적어야 풀이가 완성됩니다.",
                expected=expected_line,
                error_type="missing-step",
            )
        equations = [_parse_equation(segment) for segment in _split_segments(value)]
        equations = [equation for equation in equations if equation is not None]
        for equation in equations:
            solutions = solve(equation, y)
            expected_solutions = solve(self.line, y)
            if solutions and expected_solutions and simplify(solutions[0] - expected_solutions[0]) == 0:
                return PracticeStepFeedback(
                    id="final",
                    label="최종 답",
                    accepted=True,
                    reason="최종 접선의 방정식이 SymPy 기준으로 동치입니다.",
                    expected=expected_line,
                )
        for candidate in _expr_candidates(value):
            expr = _parse_expr(candidate)
            if expr is not None and simplify(expr - solve(self.line, y)[0]) == 0:
                return PracticeStepFeedback(
                    id="final",
                    label="최종 답",
                    accepted=True,
                    reason="최종 접선의 방정식이 SymPy 기준으로 동치입니다.",
                    expected=expected_line,
                )
        return PracticeStepFeedback(
            id="final",
            label="최종 답",
            accepted=False,
            reason="직선식의 정리 결과가 다릅니다. 기울기와 접점을 다시 대입해 보세요.",
            expected=expected_line,
            error_type="equation-build",
        )


class SymPyMaxMinEvaluator:
    def __init__(self, spec: MaxMinProblemSpec):
        self.spec = spec
        self.function = parse_expr(spec.function_expression, transformations=TRANSFORMATIONS)
        self.derivative = simplify(diff(self.function, x))
        self.critical_points = _sorted_real_roots(self.derivative)
        self.max_point, self.min_point = self._classify_points()

    def _classify_points(self) -> tuple[tuple[Expr, Expr], tuple[Expr, Expr]]:
        max_point: tuple[Expr, Expr] | None = None
        min_point: tuple[Expr, Expr] | None = None
        for root in self.critical_points:
            left_value = simplify(self.derivative.subs(x, root - Rational(1, 2)))
            right_value = simplify(self.derivative.subs(x, root + Rational(1, 2)))
            function_value = simplify(self.function.subs(x, root))
            if left_value > 0 and right_value < 0:
                max_point = (root, function_value)
            elif left_value < 0 and right_value > 0:
                min_point = (root, function_value)
        if max_point is None or min_point is None:
            raise ValueError("max/min evaluator requires one local maximum and one local minimum.")
        return max_point, min_point

    def evaluate(self, submission: dict[str, str]) -> list[PracticeStepFeedback]:
        if _is_answer_only_submission(submission):
            return [self._grade_final(submission.get("finalAnswer", ""))]
        return [
            self._grade_step_one(submission.get("stepOne", "")),
            self._grade_step_two(submission.get("stepTwo", "")),
            self._grade_step_three(submission.get("stepThree", "")),
            self._grade_final(submission.get("finalAnswer", "")),
        ]

    def _grade_step_one(self, value: str) -> PracticeStepFeedback:
        if not value.strip():
            return PracticeStepFeedback(
                id="step-1",
                label="도함수 정리",
                accepted=False,
                reason="극대극소 문제는 먼저 도함수부터 정리해야 합니다.",
                expected=f"f'(x) = {self.derivative}",
                error_type="missing-step",
            )
        for candidate in _expr_candidates(value):
            expr = _parse_expr(candidate)
            if expr is not None and simplify(expr - self.derivative) == 0:
                return PracticeStepFeedback(
                    id="step-1",
                    label="도함수 정리",
                    accepted=True,
                    reason="도함수를 정확히 정리했습니다.",
                    expected=f"f'(x) = {self.derivative}",
                )
        return PracticeStepFeedback(
            id="step-1",
            label="도함수 정리",
            accepted=False,
            reason="도함수 형태가 맞지 않습니다. 항별 미분을 다시 보세요.",
            expected=f"f'(x) = {self.derivative}",
            error_type="concept",
        )

    def _grade_step_two(self, value: str) -> PracticeStepFeedback:
        expected_points = ", ".join(f"x={point}" for point in self.critical_points)
        if not value.strip():
            return PracticeStepFeedback(
                id="step-2",
                label="극값 후보 찾기",
                accepted=False,
                reason="f'(x)=0을 풀어 극값 후보를 찾아야 합니다.",
                expected=expected_points,
                error_type="missing-step",
            )
        numbers = _parse_number_tokens(value)
        if numbers and all(any(simplify(number - point) == 0 for number in numbers) for point in self.critical_points):
            return PracticeStepFeedback(
                id="step-2",
                label="극값 후보 찾기",
                accepted=True,
                reason="도함수가 0이 되는 극값 후보를 정확히 찾았습니다.",
                expected=expected_points,
            )
        return PracticeStepFeedback(
            id="step-2",
            label="극값 후보 찾기",
            accepted=False,
            reason="도함수가 0이 되는 x값을 정확히 다시 구해 보세요.",
            expected=expected_points,
            error_type="critical-point",
        )

    def _grade_step_three(self, value: str) -> PracticeStepFeedback:
        expected = (
            f"x={self.max_point[0]}는 극대, x={self.min_point[0]}는 극소"
        )
        if not value.strip():
            return PracticeStepFeedback(
                id="step-3",
                label="부호 변화 판정",
                accepted=False,
                reason="도함수의 부호 변화를 적어 극대/극소를 판정해야 합니다.",
                expected=expected,
                error_type="missing-step",
            )
        normalized = _normalize_text(value)
        max_ok = str(self.max_point[0]) in normalized and "극대" in normalized
        min_ok = str(self.min_point[0]) in normalized and "극소" in normalized
        if max_ok and min_ok:
            return PracticeStepFeedback(
                id="step-3",
                label="부호 변화 판정",
                accepted=True,
                reason="극대와 극소 판정을 정확히 적었습니다.",
                expected=expected,
            )
        return PracticeStepFeedback(
            id="step-3",
            label="부호 변화 판정",
            accepted=False,
            reason="어느 점이 극대이고 어느 점이 극소인지 다시 판정해 보세요.",
            expected=expected,
            error_type="classification",
        )

    def _grade_final(self, value: str) -> PracticeStepFeedback:
        expected = (
            f"극대점 ({self.max_point[0]}, {self.max_point[1]}), "
            f"극소점 ({self.min_point[0]}, {self.min_point[1]})"
        )
        if not value.strip():
            return PracticeStepFeedback(
                id="final",
                label="최종 답",
                accepted=False,
                reason="극대점과 극소점을 좌표까지 적어야 풀이가 완성됩니다.",
                expected=expected,
                error_type="missing-step",
            )
        points = _parse_all_points(value)
        has_max = any(simplify(px - self.max_point[0]) == 0 and simplify(py - self.max_point[1]) == 0 for px, py in points)
        has_min = any(simplify(px - self.min_point[0]) == 0 and simplify(py - self.min_point[1]) == 0 for px, py in points)
        if has_max and has_min:
            return PracticeStepFeedback(
                id="final",
                label="최종 답",
                accepted=True,
                reason="극대점과 극소점을 좌표까지 정확히 적었습니다.",
                expected=expected,
            )
        normalized = _normalize_text(value)
        if (
            str(self.max_point[0]) in normalized
            and str(self.max_point[1]) in normalized
            and str(self.min_point[0]) in normalized
            and str(self.min_point[1]) in normalized
        ):
            return PracticeStepFeedback(
                id="final",
                label="최종 답",
                accepted=True,
                reason="핵심 좌표 정보가 모두 맞습니다.",
                expected=expected,
            )
        return PracticeStepFeedback(
            id="final",
            label="최종 답",
            accepted=False,
            reason="극대점과 극소점을 좌표로 다시 정리해 보세요.",
            expected=expected,
            error_type="final-structure",
        )


class HeuristicOpenEvaluator:
    def __init__(self, problem: dict[str, object]):
        self.problem = problem

    def evaluate(self, submission: dict[str, str]) -> list[PracticeStepFeedback]:
        if _is_answer_only_submission(submission):
            return [
                self._feedback(
                    "final",
                    "최종 답",
                    submission.get("finalAnswer", ""),
                    "결론을 한 문장으로 정리해 보세요.",
                    final=True,
                )
            ]
        return [
            self._feedback("step-1", "핵심 식 정리", submission.get("stepOne", ""), "핵심 식이나 조건을 먼저 적어 보세요."),
            self._feedback("step-2", "문제 접근", submission.get("stepTwo", ""), "풀이의 중간 논리를 한 줄 더 적어 보세요."),
            self._feedback("step-3", "판정 근거", submission.get("stepThree", ""), "왜 그런 결론이 나오는지 근거를 적어 보세요."),
            self._feedback("final", "최종 답", submission.get("finalAnswer", ""), "결론을 한 문장으로 정리해 보세요.", final=True),
        ]

    def _feedback(
        self,
        feedback_id: str,
        label: str,
        value: str | None,
        hint: str,
        *,
        final: bool = False,
    ) -> PracticeStepFeedback:
        text = (value or "").strip()
        accepted = bool(text) and (len(text) >= 4 if final else len(text) >= 3)
        return PracticeStepFeedback(
            id=feedback_id,
            label=label,
            accepted=accepted,
            reason="구조가 보입니다. 다음 단계로 이어질 수 있습니다." if accepted else hint,
            expected="핵심 식/조건/결론이 보이도록 적기",
            error_type=None if accepted else "missing-step",
        )


def _structured_step_from_dict(default_label: str, payload: dict[str, object]) -> StructuredStepSpec:
    expected = [str(item) for item in payload.get("expected", []) if str(item).strip()]
    return StructuredStepSpec(
        label=str(payload.get("label") or default_label),
        mode=str(payload.get("mode") or "expression"),
        expected=expected,
        hint=str(payload.get("hint") or f"{default_label} 단계의 핵심 답을 다시 정리해 보세요."),
        success_reason=str(payload.get("successReason") or payload.get("success_reason") or "핵심 구조를 정확히 적었습니다."),
        error_type=str(payload.get("errorType") or payload.get("error_type") or "concept"),
        expected_display=str(payload.get("expectedDisplay") or payload.get("expected_display") or ""),
    )


def _structured_spec_from_problem(problem: dict[str, object]) -> StructuredProblemSpec:
    grading_spec = problem.get("gradingSpec")
    if not isinstance(grading_spec, dict):
        raise ValueError("structured evaluator requires gradingSpec")
    steps_payload = grading_spec.get("steps", [])
    steps = [
        _structured_step_from_dict(f"Step {index + 1}", item)
        for index, item in enumerate(steps_payload)
        if isinstance(item, dict)
    ]
    final_payload = grading_spec.get("final", {})
    if not isinstance(final_payload, dict):
        raise ValueError("structured evaluator requires final grading rule")
    final = _structured_step_from_dict("최종 답", final_payload)
    return StructuredProblemSpec(steps=steps, final=final)


def is_auto_scorable_problem(problem: dict[str, object]) -> bool:
    evaluation_type = str(problem.get("evaluationType") or "tangent-line")
    if evaluation_type == "reflection-open":
        return False
    if evaluation_type in {"tangent-line", "maxmin-points"}:
        return True
    grading_spec = problem.get("gradingSpec")
    return isinstance(grading_spec, dict) and isinstance(grading_spec.get("final"), dict)


def canonical_submission_for_problem(problem: dict[str, object]) -> dict[str, str] | None:
    evaluation_type = str(problem.get("evaluationType") or "tangent-line")
    function_spec = problem.get("functionSpec", {})
    if evaluation_type == "maxmin-points":
        evaluator = SymPyMaxMinEvaluator(
            MaxMinProblemSpec(function_expression=str(function_spec["expression"]))
        )
        expected_points = ", ".join(f"x={point}" for point in evaluator.critical_points)
        return {
            "stepOne": f"f'(x) = {evaluator.derivative}",
            "stepTwo": expected_points,
            "stepThree": f"x={evaluator.max_point[0]}는 극대, x={evaluator.min_point[0]}는 극소",
            "finalAnswer": (
                f"극대점 ({evaluator.max_point[0]}, {evaluator.max_point[1]}), "
                f"극소점 ({evaluator.min_point[0]}, {evaluator.min_point[1]})"
            ),
        }
    if evaluation_type == "tangent-line":
        evaluator = SymPyTangentEvaluator(
            TangentProblemSpec(
                function_expression=str(function_spec["expression"]),
                point_x=int(function_spec["pointX"]),
            )
        )
        return {
            "stepOne": f"f'(x) = {evaluator.derivative}",
            "stepTwo": f"f'({evaluator.point_x}) = {evaluator.slope}",
            "stepThree": str(evaluator.point_y),
            "finalAnswer": f"y = {solve(evaluator.line, y)[0]}",
        }
    if not is_auto_scorable_problem(problem):
        return None
    structured = _structured_spec_from_problem(problem)
    step_values = []
    for step in structured.steps:
        if not step.expected:
            step_values.append("")
        elif step.mode == "solution-set":
            step_values.append(", ".join(step.expected))
        else:
            step_values.append(step.expected[0])
    final_value = ""
    if structured.final.expected:
        final_value = (
            ", ".join(structured.final.expected)
            if structured.final.mode == "solution-set"
            else structured.final.expected[0]
        )
    return {
        "stepOne": step_values[0] if len(step_values) > 0 else "",
        "stepTwo": step_values[1] if len(step_values) > 1 else "",
        "stepThree": step_values[2] if len(step_values) > 2 else "",
        "finalAnswer": final_value,
    }


def build_evaluator(problem: dict[str, object]) -> PracticeEvaluator:
    evaluation_type = str(problem.get("evaluationType") or "tangent-line")
    function_spec = problem.get("functionSpec", {})
    if evaluation_type == "maxmin-points":
        return SymPyMaxMinEvaluator(
            MaxMinProblemSpec(function_expression=str(function_spec["expression"]))
        )
    if evaluation_type == "reflection-open":
        return HeuristicOpenEvaluator(problem)
    if evaluation_type == "tangent-line":
        return SymPyTangentEvaluator(
            TangentProblemSpec(
                function_expression=str(function_spec["expression"]),
                point_x=int(function_spec["pointX"]),
            )
        )
    if is_auto_scorable_problem(problem):
        return StructuredPracticeEvaluator(_structured_spec_from_problem(problem))
    return SymPyTangentEvaluator(
        TangentProblemSpec(
            function_expression=str(function_spec["expression"]),
            point_x=int(function_spec["pointX"]),
        )
    )
