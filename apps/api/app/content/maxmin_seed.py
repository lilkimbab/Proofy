from __future__ import annotations

from itertools import product

from sympy import integrate, simplify
from sympy.abc import x


def _display_expression(expression: str) -> str:
    return (
        expression.replace("**3", "³")
        .replace("**2", "²")
        .replace("*x", "x")
        .replace("*", "")
        .replace("+-", "-")
        .replace("(+", "(")
        .replace("(-", "(-")
    )


def _build_function_expression(scale: int, left_root: int, right_root: int, intercept: int) -> str:
    derivative = f"{scale}*(x-({left_root}))*(x-({right_root}))"
    integral = simplify(integrate(derivative, x) + intercept)
    return str(integral)

def _problem(function_expression: str, left_root: int, right_root: int, index: int) -> dict:
    function = simplify(function_expression)
    max_y = int(function.subs(x, left_root))
    min_y = int(function.subs(x, right_root))
    return {
        "id": f"problem-maxmin-{index:03d}",
        "title": f"극대극소 기본형 {index}",
        "statement": (
            f"함수 f(x) = {_display_expression(str(function))}의 극대점과 극소점을 구하시오."
        ),
        "coachHint": "도함수, 극값 후보, 부호 변화, 극대점/극소점 좌표 순서로 적으세요.",
        "expectedOutline": [
            "도함수 구하기",
            "f'(x)=0의 해 찾기",
            "부호 변화로 극대/극소 판정",
            "극대점과 극소점 좌표 정리",
        ],
        "functionSpec": {"expression": str(function)},
        "evaluationType": "maxmin-points",
        "stepGuide": [
            {"label": "Step 1. 도함수", "placeholder": "예: f'(x) = 6x² - 18x + 12"},
            {"label": "Step 2. 극값 후보", "placeholder": "예: f'(x)=0 → x=1, 2"},
            {"label": "Step 3. 부호 변화 판정", "placeholder": "예: x=1은 극대, x=2는 극소"},
        ],
        "finalPrompt": "예: 극대점 (1, 8), 극소점 (2, 7)",
        "answerShape": {
            "maxPoint": [left_root, max_y],
            "minPoint": [right_root, min_y],
        },
    }


def _generate_problems(target_count: int = 220) -> list[dict]:
    problems: list[dict] = []
    index = 1
    for scale, left_root, gap, intercept in product(
        [6, 12, -6, -12],
        [-4, -3, -2, -1, 0, 1, 2],
        [1, 2, 3, 4],
        [-12, -8, -4, 0, 4, 8, 12],
    ):
        right_root = left_root + gap
        if right_root > 5:
            continue
        expression = _build_function_expression(scale, left_root, right_root, intercept)
        function = simplify(expression)
        max_root = left_root if scale < 0 else right_root
        min_root = right_root if scale < 0 else left_root
        max_y = function.subs(x, max_root)
        min_y = function.subs(x, min_root)
        if abs(max_y) > 60 or abs(min_y) > 60:
            continue
        normalized_expression = str(function)
        problem = _problem(normalized_expression, max_root, min_root, index)
        problem["id"] = f"problem-maxmin-{index:03d}"
        problem["title"] = f"극대극소 기본형 {index}"
        problems.append(problem)
        index += 1
        if len(problems) >= target_count:
            break
    return problems


def build_maxmin_bundle() -> dict:
    problems = _generate_problems()
    return {
        "bundleId": "suneung-math-maxmin-core-v1",
        "title": "2028 수능 수학 극대극소 기본 묶음",
        "version": "2026.04",
        "domain": "suneung-math",
        "concepts": [
            {
                "id": "maxmin-critical-points",
                "title": "극값 후보 찾기",
                "lessonPackId": "lesson-maxmin-core",
                "problemSetId": "set-maxmin-core",
                "baselineScore": 58,
                "baselineTrend": "+3",
                "baselineRisk": "높음",
            },
            {
                "id": "maxmin-sign-analysis",
                "title": "부호 변화 판정",
                "lessonPackId": "lesson-maxmin-core",
                "problemSetId": "set-maxmin-core",
                "baselineScore": 55,
                "baselineTrend": "+1",
                "baselineRisk": "높음",
            },
            {
                "id": "maxmin-point-writing",
                "title": "극대점/극소점 좌표화",
                "lessonPackId": "lesson-maxmin-core",
                "problemSetId": "set-maxmin-core",
                "baselineScore": 61,
                "baselineTrend": "+2",
                "baselineRisk": "중간",
            },
        ],
        "diagnosticQuestions": [
            {
                "id": "diag-maxmin-1",
                "prompt": "극값 후보를 찾는 첫 단계는 무엇인가?",
                "options": ["f'(x)=0의 해를 구한다", "f(x)=0의 해를 구한다", "x축 절편을 찾는다", "적분한다"],
                "answer": 0,
                "concept": "maxmin-critical-points",
            },
            {
                "id": "diag-maxmin-2",
                "prompt": "도함수 부호가 (+)에서 (-)로 바뀌면 어떻게 판정하는가?",
                "options": ["극대", "극소", "변곡점", "판정 불가"],
                "answer": 0,
                "concept": "maxmin-sign-analysis",
            },
            {
                "id": "diag-maxmin-3",
                "prompt": "극대점은 무엇으로 적는가?",
                "options": ["x좌표만", "함수식만", "좌표 (x, f(x))", "도함수값만"],
                "answer": 2,
                "concept": "maxmin-point-writing",
            },
            {
                "id": "diag-maxmin-4",
                "prompt": "도함수 부호가 (-)에서 (+)로 바뀌면 어떻게 판정하는가?",
                "options": ["극대", "극소", "항상 0", "감소"],
                "answer": 1,
                "concept": "maxmin-sign-analysis",
            },
            {
                "id": "diag-maxmin-5",
                "prompt": "극값 후보 두 개가 나왔다면 다음 단계는 무엇인가?",
                "options": ["부호 변화 조사", "문제 종료", "적분", "계수 비교"],
                "answer": 0,
                "concept": "maxmin-critical-points",
            },
            {
                "id": "diag-maxmin-6",
                "prompt": "최종 답에서 빠지면 안 되는 것은?",
                "options": ["좌표", "문제 번호", "증명 전체", "그래프 색상"],
                "answer": 0,
                "concept": "maxmin-point-writing",
            },
        ],
        "microScenes": {
            "slope": {
                "id": "micro-maxmin-sign",
                "title": "질문 답변: 부호 변화 판정",
                "narration": "극대극소는 도함수의 부호가 바뀌는 방향을 보면 됩니다. (+)에서 (-)면 극대, (-)에서 (+)면 극소입니다.",
                "resumeLabel": "이어서 같이 볼게요",
                "objects": [
                    {"id": "mm-sign-1", "type": "heading", "x": 8, "y": 14, "w": 42, "content": "부호 변화가 판정의 핵심"},
                    {"id": "mm-sign-2", "type": "bullet", "x": 8, "y": 34, "w": 42, "content": "(+)→(-) : 극대", "delayMs": 260},
                    {"id": "mm-sign-3", "type": "bullet", "x": 8, "y": 46, "w": 42, "content": "(-)→(+) : 극소", "delayMs": 620},
                ],
            },
            "point": {
                "id": "micro-maxmin-point",
                "title": "질문 답변: 왜 좌표까지 써야 하나?",
                "narration": "극값 판정만으로는 부족하고, 실제 답은 극대점과 극소점을 좌표로 정리해야 합니다.",
                "resumeLabel": "이어서 같이 볼게요",
                "objects": [
                    {"id": "mm-point-1", "type": "heading", "x": 8, "y": 14, "w": 42, "content": "최종 답은 좌표"},
                    {"id": "mm-point-2", "type": "equation", "x": 8, "y": 36, "w": 42, "content": "(x, f(x)) 형태로 마무리", "delayMs": 360},
                ],
            },
            "recap": {
                "id": "micro-maxmin-recap",
                "title": "질문 답변: 극대극소 기본 흐름",
                "narration": "도함수, 극값 후보, 부호 변화, 좌표 정리의 네 단계로 끝냅니다.",
                "resumeLabel": "이어서 같이 볼게요",
                "objects": [
                    {"id": "mm-recap-1", "type": "bullet", "x": 8, "y": 18, "w": 42, "content": "1. 도함수"},
                    {"id": "mm-recap-2", "type": "bullet", "x": 8, "y": 30, "w": 42, "content": "2. 극값 후보"},
                    {"id": "mm-recap-3", "type": "bullet", "x": 8, "y": 42, "w": 42, "content": "3. 부호 변화"},
                    {"id": "mm-recap-4", "type": "bullet", "x": 8, "y": 54, "w": 42, "content": "4. 좌표 정리"},
                ],
            },
        },
        "lessonPacks": [
            {
                "id": "lesson-maxmin-core",
                "title": "극대극소 기본 흐름",
                "unitTitle": "미분 - 극대극소",
                "teacherName": "하늘 선생님",
                "conceptIds": [
                    "maxmin-critical-points",
                    "maxmin-sign-analysis",
                    "maxmin-point-writing",
                ],
                "questionStarters": [
                    "왜 부호 변화가 핵심이야?",
                    "극값 후보를 찾고 나서 뭘 해야 해?",
                    "좌표까지 왜 써야 하는지 다시 설명해줘",
                ],
                "scenes": [
                    {
                        "id": "scene-maxmin-1",
                        "title": "극대극소 문제는 네 줄 구조로 봅니다",
                        "narration": "극대극소는 도함수, 후보점, 부호 변화, 좌표 정리의 네 단계 흐름으로 풀면 흔들리지 않습니다.",
                        "objects": [
                            {"id": "mm-title", "type": "heading", "x": 6, "y": 10, "w": 44, "content": "극대극소 = 후보점 + 부호 변화"},
                            {"id": "mm-badge", "type": "badge", "x": 8, "y": 28, "content": "STEP 1 도함수", "delayMs": 220},
                            {"id": "mm-badge2", "type": "badge", "x": 8, "y": 40, "content": "STEP 2 후보점", "delayMs": 500},
                            {"id": "mm-badge3", "type": "badge", "x": 8, "y": 52, "content": "STEP 3 부호 변화", "delayMs": 780},
                            {"id": "mm-badge4", "type": "badge", "x": 8, "y": 64, "content": "STEP 4 좌표 정리", "delayMs": 1040},
                        ],
                    },
                    {
                        "id": "scene-maxmin-2",
                        "title": "도함수의 해가 극값 후보입니다",
                        "narration": "먼저 도함수를 구하고, f'(x)=0의 해를 찾습니다. 이 값들이 극대극소 후보가 됩니다.",
                        "objects": [
                            {"id": "mm-eq1", "type": "equation", "x": 8, "y": 16, "w": 42, "content": "예: f'(x)=6x²-18x+12"},
                            {"id": "mm-eq2", "type": "equation", "x": 8, "y": 34, "w": 42, "content": "f'(x)=0 → x=1, 2", "delayMs": 380},
                            {"id": "mm-note", "type": "note", "x": 8, "y": 52, "w": 42, "content": "후보를 찾았다고 끝이 아니라, 이제 부호 변화를 봐야 합니다.", "delayMs": 760},
                        ],
                    },
                    {
                        "id": "scene-maxmin-3",
                        "title": "부호 변화로 극대와 극소를 가릅니다",
                        "narration": "도함수 부호가 바뀌는 방향으로 극대와 극소를 판정합니다.",
                        "objects": [
                            {"id": "mm-callout", "type": "callout", "x": 8, "y": 16, "w": 42, "content": "(+)→(-)는 극대, (-)→(+)는 극소", "delayMs": 300},
                            {"id": "mm-b1", "type": "bullet", "x": 8, "y": 40, "w": 42, "content": "x=1 : 극대", "delayMs": 560},
                            {"id": "mm-b2", "type": "bullet", "x": 8, "y": 54, "w": 42, "content": "x=2 : 극소", "delayMs": 860},
                        ],
                    },
                    {
                        "id": "scene-maxmin-4",
                        "title": "마지막은 좌표로 닫습니다",
                        "narration": "최종 답은 x좌표가 아니라 극대점과 극소점을 좌표 형태로 정리하는 것입니다.",
                        "objects": [
                            {"id": "mm-final-1", "type": "equation", "x": 8, "y": 18, "w": 42, "content": "극대점 = (1, f(1))"},
                            {"id": "mm-final-2", "type": "equation", "x": 8, "y": 36, "w": 42, "content": "극소점 = (2, f(2))", "delayMs": 380},
                            {"id": "mm-final-3", "type": "badge", "x": 8, "y": 58, "content": "좌표까지 써야 답 완성", "delayMs": 760},
                        ],
                    },
                ],
            }
        ],
        "problemSets": [
            {
                "id": "set-maxmin-core",
                "title": "극대극소 기본 문제 묶음",
                "lessonPackId": "lesson-maxmin-core",
                "conceptIds": [
                    "maxmin-critical-points",
                    "maxmin-sign-analysis",
                    "maxmin-point-writing",
                ],
                "problems": problems,
            }
        ],
    }
