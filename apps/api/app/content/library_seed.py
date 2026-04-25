from __future__ import annotations

from itertools import product

from sympy import diff
from sympy.abc import x
from sympy.parsing.sympy_parser import (
    convert_xor,
    implicit_multiplication_application,
    parse_expr,
    standard_transformations,
)


TRANSFORMATIONS = standard_transformations + (
    implicit_multiplication_application,
    convert_xor,
)


GROUPS = [
    {
        "concept_id": "derivative-accuracy-plus",
        "title": "도함수 정확도 확장",
        "lesson_pack_id": "lesson-derivative-accuracy-plus",
        "problem_set_id": "set-derivative-accuracy-plus",
        "teacher_name": "하늘 선생님",
        "unit_title": "미분 - 도함수 정확도 확장",
        "question_starters": ["도함수 계산이 왜 이렇게 흔들려?", "계수 많은 식은 어떻게 봐?", "다시 한 번 구조를 잡아줘"],
        "baseline_score": 63,
        "risk": "높음",
        "target_count": 220,
        "a_values": [2, 3, 4, 5, 6, 7, 8, 9, 10, 11],
        "b_values": [-15, -13, -11, -9, -7, -5, -3, 3, 5, 7, 9, 11],
        "c_values": [-7, -5, -3, -1, 1, 3, 5, 7],
        "x_values": [-2, -1, 0, 1, 2, 3, 4],
        "representative": {"expression": "4*x**2 - 7*x + 1", "point_x": 2},
    },
    {
        "concept_id": "slope-substitution-plus",
        "title": "기울기 대입 보강",
        "lesson_pack_id": "lesson-slope-substitution-plus",
        "problem_set_id": "set-slope-substitution-plus",
        "teacher_name": "하늘 선생님",
        "unit_title": "미분 - 기울기 대입 보강",
        "question_starters": ["기울기 대입에서 자꾸 막혀", "어느 줄에서 m이 확정돼?", "x값을 넣는 위치를 다시 보여줘"],
        "baseline_score": 59,
        "risk": "높음",
        "target_count": 220,
        "a_values": [1, 2, 3, 4, 5, 6, 7, 8],
        "b_values": [-20, -18, -16, -14, -12, -10, 8, 10, 12],
        "c_values": [-8, -6, -4, -2, 2, 4, 6, 8],
        "x_values": [-3, -2, -1, 0, 1, 2, 3, 4],
        "representative": {"expression": "x**2 - 8*x + 9", "point_x": 4},
    },
    {
        "concept_id": "point-recovery-plus",
        "title": "접점 복구 심화",
        "lesson_pack_id": "lesson-point-recovery-plus",
        "problem_set_id": "set-point-recovery-plus",
        "teacher_name": "하늘 선생님",
        "unit_title": "미분 - 접점 복구 심화",
        "question_starters": ["접점 y값을 자꾸 빼먹어", "원함수 대입을 빠르게 하는 법은?", "좌표 복구 흐름을 다시 보여줘"],
        "baseline_score": 56,
        "risk": "매우 높음",
        "target_count": 220,
        "a_values": [1, 2, 3, 4, 5],
        "b_values": [-8, -6, -4, -2, 2, 4, 6, 8],
        "c_values": [-10, -8, -6, -4, -2, 2, 4, 6, 8, 10],
        "x_values": [-4, -3, -2, -1, 1, 2, 3, 4],
        "representative": {"expression": "x**2 - 2*x - 3", "point_x": 3},
    },
    {
        "concept_id": "equation-finish-plus",
        "title": "직선식 마무리 확장",
        "lesson_pack_id": "lesson-equation-finish-plus",
        "problem_set_id": "set-equation-finish-plus",
        "teacher_name": "하늘 선생님",
        "unit_title": "미분 - 직선식 마무리 확장",
        "question_starters": ["점기울기식 정리에서 자꾸 틀려", "최종식을 깔끔하게 끝내는 법은?", "마지막 줄만 다시 보여줘"],
        "baseline_score": 61,
        "risk": "높음",
        "target_count": 220,
        "a_values": [1, 2, 3, 4, 5, 6],
        "b_values": [-10, -9, -7, -5, -3, 3, 5, 7, 9],
        "c_values": [-9, -6, -3, -1, 1, 3, 6, 9],
        "x_values": [-3, -2, -1, 0, 1, 2, 3, 4, 5],
        "representative": {"expression": "2*x**2 - 5*x + 2", "point_x": 2},
    },
    {
        "concept_id": "sign-discipline-plus",
        "title": "부호 통제 강화",
        "lesson_pack_id": "lesson-sign-discipline-plus",
        "problem_set_id": "set-sign-discipline-plus",
        "teacher_name": "하늘 선생님",
        "unit_title": "미분 - 부호 통제 강화",
        "question_starters": ["음수 항이 많으면 어떻게 검산해?", "부호 실수를 줄이는 흐름이 필요해", "음수 접점을 다시 설명해줘"],
        "baseline_score": 51,
        "risk": "매우 높음",
        "target_count": 220,
        "a_values": [-8, -7, -6, -5, -4, -3, -2, -1],
        "b_values": [-12, -10, -8, -6, -4, 4, 6, 8, 10],
        "c_values": [-8, -6, -4, -2, 2, 4, 6, 8],
        "x_values": [-3, -2, -1, 0, 1, 2, 3, 4],
        "representative": {"expression": "-2*x**2 + 5*x - 3", "point_x": 1},
    },
    {
        "concept_id": "graph-sense-plus",
        "title": "그래프 감각 확장",
        "lesson_pack_id": "lesson-graph-sense-plus",
        "problem_set_id": "set-graph-sense-plus",
        "teacher_name": "하늘 선생님",
        "unit_title": "미분 - 그래프 감각 확장",
        "question_starters": ["기울기 부호를 그림으로 확인하고 싶어", "상승/하강을 같이 봐줘", "그래프 직관을 다시 설명해줘"],
        "baseline_score": 66,
        "risk": "중간",
        "target_count": 220,
        "a_values": [1, 2, 3, 4, 5],
        "b_values": [-14, -12, -10, -8, -6, -4, 4, 6, 8, 10, 12],
        "c_values": [-10, -7, -4, -1, 1, 4, 7, 10],
        "x_values": [-4, -3, -2, -1, 0, 1, 2, 3, 4],
        "representative": {"expression": "x**2 - 6*x + 5", "point_x": 1},
    },
]


def _board_expression(expression: str) -> str:
    return (
        expression.replace("**2", "²")
        .replace("**3", "³")
        .replace("*x", "x")
        .replace("*", "")
    )


def _derivative_expression(expression: str) -> str:
    expr = parse_expr(expression, transformations=TRANSFORMATIONS)
    return str(diff(expr, x))


def _point_y(expression: str, point_x: int) -> int:
    expr = parse_expr(expression, transformations=TRANSFORMATIONS)
    return int(expr.subs(x, point_x))


def _lesson_pack(group: dict) -> dict:
    expression = group["representative"]["expression"]
    point_x = int(group["representative"]["point_x"])
    derivative = _board_expression(_derivative_expression(expression))
    point_y = _point_y(expression, point_x)
    return {
        "id": group["lesson_pack_id"],
        "title": group["title"],
        "unitTitle": group["unit_title"],
        "teacherName": group["teacher_name"],
        "conceptIds": [group["concept_id"]],
        "questionStarters": group["question_starters"],
        "scenes": [
            {
                "id": f"{group['lesson_pack_id']}-intro",
                "title": f"{group['title']}의 대표 풀이 흐름",
                "narration": "대표 문제 한 개로 풀이 흐름을 먼저 잡은 뒤, 같은 구조를 여러 문제로 확장합니다.",
                "objects": [
                    {
                        "id": f"{group['lesson_pack_id']}-title",
                        "type": "heading",
                        "x": 6,
                        "y": 8,
                        "w": 44,
                        "content": group["title"],
                    },
                    {
                        "id": f"{group['lesson_pack_id']}-function",
                        "type": "equation",
                        "x": 8,
                        "y": 24,
                        "w": 42,
                        "content": f"f(x) = {_board_expression(expression)}",
                        "delayMs": 280,
                    },
                    {
                        "id": f"{group['lesson_pack_id']}-graph",
                        "type": "graph",
                        "x": 58,
                        "y": 16,
                        "w": 36,
                        "h": 60,
                        "graphSpec": {
                            "function": expression,
                            "xMin": point_x - 3,
                            "xMax": point_x + 3,
                            "yMin": point_y - 8,
                            "yMax": point_y + 8,
                            "tangentAt": point_x,
                            "markLabel": f"({point_x}, {point_y})",
                        },
                    },
                ],
            },
            {
                "id": f"{group['lesson_pack_id']}-derivative",
                "title": "도함수와 기울기를 고정합니다",
                "narration": "도함수에서 기울기를 구한 뒤 같은 x값을 원함수에 다시 넣어 접점을 복구합니다.",
                "objects": [
                    {
                        "id": f"{group['lesson_pack_id']}-eq1",
                        "type": "equation",
                        "x": 8,
                        "y": 16,
                        "w": 42,
                        "content": f"f'(x) = {_board_expression(derivative)}",
                    },
                    {
                        "id": f"{group['lesson_pack_id']}-eq2",
                        "type": "equation",
                        "x": 8,
                        "y": 34,
                        "w": 42,
                        "content": f"m = f'({point_x})",
                        "delayMs": 420,
                    },
                    {
                        "id": f"{group['lesson_pack_id']}-callout",
                        "type": "callout",
                        "x": 8,
                        "y": 52,
                        "w": 42,
                        "content": "기울기와 접점을 분리해서 적으면 계산 실수가 줄어듭니다.",
                        "delayMs": 880,
                    },
                ],
            },
            {
                "id": f"{group['lesson_pack_id']}-finish",
                "title": "점기울기식으로 마무리합니다",
                "narration": "대표 문제를 점기울기식으로 끝낸 뒤 바로 변형 문제 묶음으로 넘어갑니다.",
                "objects": [
                    {
                        "id": f"{group['lesson_pack_id']}-point",
                        "type": "equation",
                        "x": 8,
                        "y": 18,
                        "w": 42,
                        "content": f"접점 = ({point_x}, {point_y})",
                    },
                    {
                        "id": f"{group['lesson_pack_id']}-form",
                        "type": "equation",
                        "x": 8,
                        "y": 36,
                        "w": 42,
                        "content": "y - y₁ = m(x - x₁)",
                        "delayMs": 420,
                    },
                    {
                        "id": f"{group['lesson_pack_id']}-badge",
                        "type": "badge",
                        "x": 8,
                        "y": 56,
                        "content": "대표 풀이 흐름 정리 완료",
                        "delayMs": 840,
                    },
                ],
            },
        ],
    }


def _problem(group: dict, expression: str, point_x: int, index: int) -> dict:
    return {
        "id": f"{group['problem_set_id']}-problem-{index:03d}",
        "title": f"{group['title']} {index}",
        "statement": f"함수 f(x) = {_board_expression(expression)}의 그래프 위의 점 x = {point_x}에서의 접선의 방정식을 구하시오.",
        "coachHint": "도함수, 기울기, 접점, 점기울기식 순서로 적고 마지막에만 정리하세요.",
        "expectedOutline": [
            "도함수 구하기",
            "기울기 구하기",
            "접점 좌표 구하기",
            "최종 직선식 정리",
        ],
        "functionSpec": {"expression": expression, "pointX": point_x},
    }


def _generate_variants(group: dict) -> list[tuple[str, int]]:
    target_count = int(group.get("target_count", 220))
    variants: list[tuple[str, int]] = []
    seen: set[tuple[str, int]] = set()
    for a, b, c, point_x in product(
        group["a_values"],
        group["b_values"],
        group["c_values"],
        group["x_values"],
    ):
        expression = f"{a}*x**2 + ({b})*x + ({c})"
        if (expression, point_x) in seen:
            continue
        slope = int(diff(parse_expr(expression, transformations=TRANSFORMATIONS), x).subs(x, point_x))
        y_value = _point_y(expression, point_x)
        if abs(slope) > 30 or abs(y_value) > 45:
            continue
        seen.add((expression, point_x))
        variants.append((expression, point_x))
        if len(variants) >= target_count:
            break
    representative = (
        group["representative"]["expression"],
        int(group["representative"]["point_x"]),
    )
    if representative not in seen:
        variants.insert(0, representative)
    return variants[:target_count]


def _problem_set(group: dict) -> dict:
    variants = _generate_variants(group)
    return {
        "id": group["problem_set_id"],
        "title": f"{group['title']} 문제 묶음",
        "lessonPackId": group["lesson_pack_id"],
        "conceptIds": [group["concept_id"]],
        "problems": [
            _problem(group, expression, int(point_x), index + 1)
            for index, (expression, point_x) in enumerate(variants)
        ],
    }


def build_library_bundle() -> dict:
    return {
        "bundleId": "suneung-math-library-v1",
        "title": "2028 수능 수학 확장 라이브러리",
        "version": "2026.04",
        "domain": "suneung-math",
        "concepts": [
            {
                "id": group["concept_id"],
                "title": group["title"],
                "lessonPackId": group["lesson_pack_id"],
                "problemSetId": group["problem_set_id"],
                "baselineScore": group["baseline_score"],
                "baselineTrend": "+0",
                "baselineRisk": group["risk"],
            }
            for group in GROUPS
        ],
        "diagnosticQuestions": [
            {
                "id": "lib-diag-1",
                "prompt": "접선의 방정식을 세울 때 반드시 필요한 두 요소는 무엇인가?",
                "options": ["기울기와 한 점", "넓이와 둘레", "접선 두 개", "미분값과 적분값"],
                "answer": 0,
                "concept": "equation-finish-plus",
            },
            {
                "id": "lib-diag-2",
                "prompt": "접점의 x값이 주어졌을 때 원함수에도 다시 넣는 이유는 무엇인가?",
                "options": ["기울기를 구하려고", "y좌표를 복구하려고", "도함수를 없애려고", "x축 절편을 구하려고"],
                "answer": 1,
                "concept": "point-recovery-plus",
            },
            {
                "id": "lib-diag-3",
                "prompt": "기울기 m = f'(a)라는 해석과 가장 가까운 것은?",
                "options": ["a에서의 순간 변화율", "a에서의 함수값", "모든 점의 평균 변화율", "x축과의 거리"],
                "answer": 0,
                "concept": "slope-substitution-plus",
            },
            {
                "id": "lib-diag-4",
                "prompt": "음수 이차항이 있는 함수에서 먼저 의심해야 할 오류는 무엇인가?",
                "options": ["부호 실수", "적분 상수", "정의역 누락", "합성함수 착각"],
                "answer": 0,
                "concept": "sign-discipline-plus",
            },
            {
                "id": "lib-diag-5",
                "prompt": "기울기가 음수라는 말의 의미로 가장 가까운 것은?",
                "options": ["오른쪽으로 갈수록 하강", "오른쪽으로 갈수록 상승", "항상 x축과 평행", "접점이 원점"],
                "answer": 0,
                "concept": "graph-sense-plus",
            },
            {
                "id": "lib-diag-6",
                "prompt": "4x² - 7x + 1의 도함수는 무엇인가?",
                "options": ["8x - 7", "4x - 7", "8x + 1", "4x² - 7"],
                "answer": 0,
                "concept": "derivative-accuracy-plus",
            },
        ],
        "microScenes": {
            "slope": {
                "id": "lib-micro-slope",
                "title": "확장 답변: 기울기와 도함수",
                "narration": "접선 기울기는 해당 점에서의 순간 변화율이므로 도함수값과 연결됩니다.",
                "resumeLabel": "이어서 같이 볼게요",
                "objects": [
                    {"id": "lib-micro-1", "type": "heading", "x": 8, "y": 12, "w": 42, "content": "기울기 = 순간 변화율"},
                    {"id": "lib-micro-2", "type": "equation", "x": 8, "y": 32, "w": 42, "content": "m = f'(a)", "delayMs": 360},
                ],
            },
            "point": {
                "id": "lib-micro-point",
                "title": "확장 답변: 접점 복구",
                "narration": "원함수에 다시 넣는 이유는 접선이 지나는 실제 점의 y좌표를 찾기 위해서입니다.",
                "resumeLabel": "이어서 같이 볼게요",
                "objects": [
                    {"id": "lib-micro-3", "type": "heading", "x": 8, "y": 12, "w": 42, "content": "원함수 대입 = y좌표 복구"},
                    {"id": "lib-micro-4", "type": "equation", "x": 8, "y": 32, "w": 42, "content": "(a, f(a))", "delayMs": 360},
                ],
            },
            "recap": {
                "id": "lib-micro-recap",
                "title": "확장 답변: 기본 풀이 흐름 요약",
                "narration": "도함수, 기울기, 접점, 점기울기식의 네 단계 흐름을 유지하면 대부분의 기본형이 정리됩니다.",
                "resumeLabel": "이어서 같이 볼게요",
                "objects": [
                    {"id": "lib-micro-5", "type": "bullet", "x": 8, "y": 18, "w": 42, "content": "1. 도함수"},
                    {"id": "lib-micro-6", "type": "bullet", "x": 8, "y": 32, "w": 42, "content": "2. 기울기"},
                    {"id": "lib-micro-7", "type": "bullet", "x": 8, "y": 46, "w": 42, "content": "3. 접점"},
                    {"id": "lib-micro-8", "type": "bullet", "x": 8, "y": 60, "w": 42, "content": "4. 점기울기식"},
                ],
            },
        },
        "lessonPacks": [_lesson_pack(group) for group in GROUPS],
        "problemSets": [_problem_set(group) for group in GROUPS],
    }
