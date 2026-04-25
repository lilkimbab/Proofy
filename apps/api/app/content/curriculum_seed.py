from __future__ import annotations

from copy import deepcopy
from fractions import Fraction
from math import comb, factorial
import re


PDF_SOURCE_PATH = "[별책8] 수학과 교육과정.pdf"


def expr_step(label: str, expected: str, hint: str, *, display: str | None = None) -> dict:
    return {
        "label": label,
        "mode": "expression",
        "expected": [expected],
        "hint": hint,
        "successReason": "핵심 식을 정확히 정리했습니다.",
        "errorType": "concept",
        "expectedDisplay": display or expected,
    }


def numeric_step(label: str, expected: str, hint: str) -> dict:
    return {
        "label": label,
        "mode": "numeric",
        "expected": [expected],
        "hint": hint,
        "successReason": "수치 계산이 정확합니다.",
        "errorType": "arithmetic",
        "expectedDisplay": expected,
    }


def solution_step(label: str, expected: list[str], hint: str) -> dict:
    return {
        "label": label,
        "mode": "solution-set",
        "expected": expected,
        "hint": hint,
        "successReason": "해를 빠짐없이 정리했습니다.",
        "errorType": "solution-set",
        "expectedDisplay": ", ".join(expected),
    }


def exact_step(label: str, expected: str, hint: str) -> dict:
    return {
        "label": label,
        "mode": "exact-match",
        "expected": [expected],
        "hint": hint,
        "successReason": "정답 형식과 내용이 정확합니다.",
        "errorType": "exact-match",
        "expectedDisplay": expected,
    }


def structured_problem(
    *,
    problem_id: str,
    title: str,
    statement: str,
    unit_title: str,
    course_title: str,
    achievement_codes: list[str],
    steps: list[dict],
    final: dict,
    coach_hint: str,
    expected_outline: list[str],
    final_prompt: str,
    difficulty: str = "core",
    problem_type: str | None = None,
    is_killer: bool = False,
) -> dict:
    return {
        "id": problem_id,
        "title": title,
        "statement": statement,
        "coachHint": coach_hint,
        "expectedOutline": expected_outline,
        "functionSpec": {},
        "evaluationType": "structured-generic",
        "stepGuide": [{"label": step["label"], "placeholder": step["expectedDisplay"]} for step in steps],
        "finalPrompt": final_prompt,
        "difficulty": difficulty,
        "problemType": problem_type or title,
        "isKiller": is_killer,
        "gradingSpec": {
            "steps": deepcopy(steps),
            "final": deepcopy(final),
        },
        "curriculumLinks": {
            "courseTitle": course_title,
            "unitTitle": unit_title,
            "achievementCodes": achievement_codes,
            "sourcePdf": PDF_SOURCE_PATH,
        },
    }


def tangent_problem(
    *,
    problem_id: str,
    title: str,
    statement: str,
    course_title: str,
    unit_title: str,
    achievement_codes: list[str],
    expression: str,
    point_x: int,
    difficulty: str = "core",
    problem_type: str | None = None,
    is_killer: bool = False,
) -> dict:
    return {
        "id": problem_id,
        "title": title,
        "statement": statement,
        "coachHint": "도함수, 기울기, 접점, 직선식 순서로 네 줄을 채우세요.",
        "expectedOutline": ["도함수 계산", "기울기 계산", "접점 복구", "접선의 방정식 정리"],
        "functionSpec": {"expression": expression, "pointX": point_x},
        "evaluationType": "tangent-line",
        "difficulty": difficulty,
        "problemType": problem_type or title,
        "isKiller": is_killer,
        "stepGuide": [
            {"label": "Step 1. 도함수", "placeholder": "예: f'(x) = 2*x - 1"},
            {"label": "Step 2. 기울기", "placeholder": f"예: f'({point_x}) = ..."},
            {"label": "Step 3. 접점", "placeholder": f"예: ({point_x}, f({point_x}))"},
        ],
        "finalPrompt": "예: y = mx + n",
        "curriculumLinks": {
            "courseTitle": course_title,
            "unitTitle": unit_title,
            "achievementCodes": achievement_codes,
            "sourcePdf": PDF_SOURCE_PATH,
        },
    }


CONDITION_LABELS = ("(가)", "(나)", "(다)", "(라)", "(마)", "(바)")


def _condition_statement(intro: str, conditions: list[str], question: str) -> str:
    rows: list[str] = []
    for index, condition in enumerate(conditions):
        label = CONDITION_LABELS[index] if index < len(CONDITION_LABELS) else f"({index + 1})"
        rows.append(f"{label} {condition}")
    return f"{intro} 다음 조건을 만족한다. {' '.join(rows)} {question}".strip()


UNIT_SPECS = [
    {
        "id": "common1-polynomial",
        "courseId": "common-math-1",
        "courseTitle": "공통수학1",
        "domainTitle": "다항식",
        "pdfPages": "59-60",
        "coreIdea": "식의 사칙연산, 나머지정리, 인수분해를 연결해 다항식을 구조적으로 다루는 단원입니다.",
        "contentElements": ["다항식의 연산", "나머지정리", "인수분해"],
        "achievementCodes": ["10공수1-01-01", "10공수1-01-02", "10공수1-01-03"],
        "questionStarters": ["나머지정리 핵심만 다시 설명해줘", "인수분해 풀이 흐름을 보여줘", "전개와 인수분해를 연결해줘"],
        "diagnostic": {"prompt": "다음 중 공통수학1의 다항식 단원 핵심 내용은?", "answer": "나머지정리"},
        "problems": [
            structured_problem(
                problem_id="curr-poly-001",
                title="다항식 곱셈 기본형",
                statement="(x + 2)(x - 3)을 전개하시오.",
                unit_title="공통수학1 - 다항식",
                course_title="공통수학1",
                achievement_codes=["10공수1-01-01"],
                steps=[
                    expr_step("Step 1. 첫째항 곱하기", "x**2 - 3*x", "먼저 x를 분배해 첫 줄을 적으세요."),
                    expr_step("Step 2. 둘째항 곱하기", "2*x - 6", "그다음 2를 분배한 식을 적으세요."),
                    expr_step("Step 3. 동류항 정리", "-x - 6", "x항과 상수항을 모아 정리하세요."),
                ],
                final=expr_step("최종 답", "x**2 - x - 6", "전개식을 최종적으로 한 줄로 정리하세요."),
                coach_hint="분배 후 동류항을 모으는 기본 풀이 흐름을 고정하세요.",
                expected_outline=["분배", "분배", "동류항 정리", "최종 전개식"],
                final_prompt="예: x**2 - x - 6",
            ),
            structured_problem(
                problem_id="curr-poly-002",
                title="나머지정리 적용",
                statement="다항식 P(x)=x^3-2x+5를 x-2로 나눌 때의 나머지를 구하시오.",
                unit_title="공통수학1 - 다항식",
                course_title="공통수학1",
                achievement_codes=["10공수1-01-02"],
                steps=[
                    expr_step("Step 1. 나머지정리 연결", "P(2)", "x-2로 나눌 때 나머지는 P(2)로 연결합니다.", display="P(2)"),
                    numeric_step("Step 2. 값 대입", "9", "2를 대입한 값을 계산하세요."),
                    exact_step("Step 3. 나머지 해석", "나머지=9", "계산 결과를 나머지로 해석하세요."),
                ],
                final=numeric_step("최종 답", "9", "나머지를 숫자로 적으세요."),
                coach_hint="x-a로 나누는 문제는 P(a) 한 줄로 바로 연결하세요.",
                expected_outline=["P(a) 연결", "대입 계산", "나머지 해석", "최종 수치"],
                final_prompt="예: 9",
            ),
            structured_problem(
                problem_id="curr-poly-003",
                title="인수분해 기본형",
                statement="x^2+5x+6을 인수분해하시오.",
                unit_title="공통수학1 - 다항식",
                course_title="공통수학1",
                achievement_codes=["10공수1-01-03"],
                steps=[
                    numeric_step("Step 1. 곱이 6인 수", "6", "상수항 6을 기준으로 후보를 먼저 보세요."),
                    numeric_step("Step 2. 합이 5인 수", "5", "두 수의 합이 5가 되도록 맞추세요."),
                    exact_step("Step 3. 묶음 완성", "(x+2)(x+3)", "두 인수를 곱 형태로 적으세요."),
                ],
                final=expr_step("최종 답", "(x+2)*(x+3)", "인수분해 결과를 적으세요.", display="(x+2)(x+3)"),
                coach_hint="곱과 합을 동시에 만족하는 두 수를 찾는 풀이 흐름으로 접근하세요.",
                expected_outline=["곱 찾기", "합 확인", "인수 묶기", "최종 인수분해"],
                final_prompt="예: (x+2)(x+3)",
            ),
        ],
    },
    {
        "id": "common1-equation",
        "courseId": "common-math-1",
        "courseTitle": "공통수학1",
        "domainTitle": "방정식과 부등식",
        "pdfPages": "61-62",
        "coreIdea": "이차방정식과 이차함수, 여러 가지 방정식과 부등식을 절차적으로 해결하는 단원입니다.",
        "contentElements": ["복소수와 이차방정식", "이차방정식과 이차함수", "여러 가지 방정식과 부등식"],
        "achievementCodes": ["10공수1-02-01", "10공수1-02-11"],
        "questionStarters": ["판별식부터 봐야 해?", "근과 계수 관계를 정리해줘", "이차부등식 해석을 다시 보여줘"],
        "diagnostic": {"prompt": "다음 중 공통수학1의 방정식과 부등식 단원에서 직접 다루는 것은?", "answer": "이차방정식의 판별식"},
        "problems": [
            structured_problem(
                problem_id="curr-eq-001",
                title="이차방정식 해 구하기",
                statement="x^2-5x+6=0의 해를 구하시오.",
                unit_title="공통수학1 - 방정식과 부등식",
                course_title="공통수학1",
                achievement_codes=["10공수1-02-02"],
                steps=[
                    expr_step("Step 1. 인수분해", "(x-2)*(x-3)", "좌변을 먼저 인수분해하세요.", display="(x-2)(x-3)"),
                    exact_step("Step 2. 각 인수의 영점", "x=2 또는 x=3", "각 인수를 0으로 두어 해를 찾으세요."),
                    solution_step("Step 3. 해 정리", ["2", "3"], "해를 집합처럼 빠짐없이 정리하세요."),
                ],
                final=solution_step("최종 답", ["2", "3"], "최종 해를 적으세요."),
                coach_hint="인수분해가 보이면 바로 두 직선 문제처럼 나눠서 해를 읽으세요.",
                expected_outline=["인수분해", "각 인수=0", "해 정리", "최종 해"],
                final_prompt="예: x=2, 3",
            ),
            structured_problem(
                problem_id="curr-eq-002",
                title="판별식 판정",
                statement="x^2-4x+5=0의 근의 종류를 판별하시오.",
                unit_title="공통수학1 - 방정식과 부등식",
                course_title="공통수학1",
                achievement_codes=["10공수1-02-02"],
                steps=[
                    expr_step("Step 1. 판별식 세우기", "(-4)**2 - 4*1*5", "b^2-4ac를 먼저 세우세요.", display="16-20"),
                    numeric_step("Step 2. 판별식 계산", "-4", "판별식 값을 계산하세요."),
                    exact_step("Step 3. 근의 종류 해석", "허근 2개", "판별식 부호에 따라 근의 종류를 해석하세요."),
                ],
                final=exact_step("최종 답", "허근 2개", "근의 종류를 최종적으로 적으세요."),
                coach_hint="판별식 부호 해석만 정확하면 유형을 빠르게 정리할 수 있습니다.",
                expected_outline=["판별식", "수치 계산", "해석", "최종 판정"],
                final_prompt="예: 허근 2개",
            ),
            structured_problem(
                problem_id="curr-eq-003",
                title="이차부등식 해석",
                statement="x^2-4x+3>0의 해를 구하시오.",
                unit_title="공통수학1 - 방정식과 부등식",
                course_title="공통수학1",
                achievement_codes=["10공수1-02-11"],
                steps=[
                    expr_step("Step 1. 인수분해", "(x-1)*(x-3)", "부등식의 좌변을 인수분해하세요.", display="(x-1)(x-3)"),
                    solution_step("Step 2. 경계점", ["1", "3"], "부호가 바뀌는 경계점을 찾으세요."),
                    exact_step("Step 3. 해 구간", "x<1 또는 x>3", "부호 표를 바탕으로 양수 구간을 적으세요."),
                ],
                final=exact_step("최종 답", "x<1 또는 x>3", "이차부등식의 해를 적으세요."),
                coach_hint="경계점 두 개를 찾은 뒤 바깥쪽/안쪽 부호를 판단하세요.",
                expected_outline=["인수분해", "경계점", "부호 판단", "최종 해"],
                final_prompt="예: x<1 또는 x>3",
            ),
        ],
    },
    {
        "id": "common1-counting",
        "courseId": "common-math-1",
        "courseTitle": "공통수학1",
        "domainTitle": "경우의 수",
        "pdfPages": "62-63",
        "coreIdea": "합의 법칙과 곱의 법칙, 순열과 조합으로 경우를 체계적으로 세는 단원입니다.",
        "contentElements": ["합의 법칙과 곱의 법칙", "순열과 조합"],
        "achievementCodes": ["10공수1-03-01", "10공수1-03-03"],
        "questionStarters": ["합의 법칙과 곱의 법칙 차이를 알려줘", "순열과 조합 판단법이 헷갈려", "경우의 수를 표로 정리해줘"],
        "diagnostic": {"prompt": "다음 중 공통수학1의 경우의 수 단원 핵심 내용은?", "answer": "순열과 조합"},
        "problems": [
            structured_problem(
                problem_id="curr-count-001",
                title="곱의 법칙",
                statement="셔츠 3벌과 바지 2벌이 있을 때 가능한 옷차림의 수를 구하시오.",
                unit_title="공통수학1 - 경우의 수",
                course_title="공통수학1",
                achievement_codes=["10공수1-03-01"],
                steps=[
                    numeric_step("Step 1. 셔츠 선택 수", "3", "셔츠 선택 수를 먼저 적으세요."),
                    numeric_step("Step 2. 바지 선택 수", "2", "바지 선택 수를 적으세요."),
                    expr_step("Step 3. 곱의 법칙 적용", "3*2", "독립 선택이므로 곱의 법칙을 적용하세요.", display="3×2"),
                ],
                final=numeric_step("최종 답", "6", "가능한 옷차림 수를 적으세요."),
                coach_hint="단계가 이어지면 곱의 법칙, 갈래가 나뉘면 합의 법칙입니다.",
                expected_outline=["첫 선택", "둘째 선택", "곱의 법칙", "최종 수"],
                final_prompt="예: 6",
            ),
            structured_problem(
                problem_id="curr-count-002",
                title="순열",
                statement="서로 다른 4명 중 2명을 일렬로 세우는 방법의 수를 구하시오.",
                unit_title="공통수학1 - 경우의 수",
                course_title="공통수학1",
                achievement_codes=["10공수1-03-02"],
                steps=[
                    expr_step("Step 1. 첫 자리 선택", "4", "첫 자리에 올 수 있는 사람 수를 적으세요."),
                    expr_step("Step 2. 둘째 자리 선택", "3", "둘째 자리에 올 수 있는 사람 수를 적으세요."),
                    expr_step("Step 3. 곱으로 정리", "4*3", "순서를 고려해 곱으로 정리하세요.", display="4×3"),
                ],
                final=numeric_step("최종 답", "12", "순열의 수를 적으세요."),
                coach_hint="순서를 고려하면 자리를 먼저 보고 곱셈으로 세세요.",
                expected_outline=["첫 자리", "둘째 자리", "곱셈", "최종 수"],
                final_prompt="예: 12",
            ),
            structured_problem(
                problem_id="curr-count-003",
                title="조합",
                statement="서로 다른 5명 중 2명을 뽑는 방법의 수를 구하시오.",
                unit_title="공통수학1 - 경우의 수",
                course_title="공통수학1",
                achievement_codes=["10공수1-03-03"],
                steps=[
                    expr_step("Step 1. 조합식", "5*4/2", "5C2를 곱과 나눗셈으로 정리하세요.", display="5×4÷2"),
                    numeric_step("Step 2. 계산", "10", "조합의 수를 계산하세요."),
                    exact_step("Step 3. 해석", "순서 무관 10가지", "조합은 순서를 보지 않는다는 해석을 덧붙이세요."),
                ],
                final=numeric_step("최종 답", "10", "조합의 수를 적으세요."),
                coach_hint="순서를 버리는 순간 같은 묶음을 중복 계산하지 않도록 나눕니다.",
                expected_outline=["조합식", "계산", "의미 확인", "최종 수"],
                final_prompt="예: 10",
            ),
        ],
    },
    {
        "id": "common1-matrix",
        "courseId": "common-math-1",
        "courseTitle": "공통수학1",
        "domainTitle": "행렬",
        "pdfPages": "63",
        "coreIdea": "자료를 행렬로 표현하고 기본 연산으로 처리하는 단원입니다.",
        "contentElements": ["행렬과 그 연산"],
        "achievementCodes": ["10공수1-04-01", "10공수1-04-02"],
        "questionStarters": ["행렬 덧셈과 곱셈 차이를 설명해줘", "행과 열을 자꾸 바꿔 써", "실생활 자료를 행렬로 바꾸는 법이 궁금해"],
        "diagnostic": {"prompt": "다음 중 공통수학1의 행렬 단원에서 직접 다루는 것은?", "answer": "행렬의 덧셈과 곱셈"},
        "problems": [
            structured_problem(
                problem_id="curr-matrix-001",
                title="행렬 덧셈",
                statement="A=[[1,2],[3,4]], B=[[5,6],[7,8]]일 때 A+B를 구하시오.",
                unit_title="공통수학1 - 행렬",
                course_title="공통수학1",
                achievement_codes=["10공수1-04-02"],
                steps=[
                    exact_step("Step 1. (1,1) 성분", "6", "(1,1) 성분을 먼저 계산하세요."),
                    exact_step("Step 2. (2,2) 성분", "12", "(2,2) 성분을 계산하세요."),
                    exact_step("Step 3. 행렬 완성", "[[6,8],[10,12]]", "성분을 모아 합행렬을 적으세요."),
                ],
                final=exact_step("최종 답", "[[6,8],[10,12]]", "합행렬을 적으세요."),
                coach_hint="행렬 덧셈은 같은 위치의 성분끼리만 계산합니다.",
                expected_outline=["성분 계산", "성분 계산", "행렬 조립", "최종 행렬"],
                final_prompt="예: [[6,8],[10,12]]",
            ),
            structured_problem(
                problem_id="curr-matrix-002",
                title="실수배",
                statement="A=[[2,-1],[0,3]]일 때 2A를 구하시오.",
                unit_title="공통수학1 - 행렬",
                course_title="공통수학1",
                achievement_codes=["10공수1-04-02"],
                steps=[
                    exact_step("Step 1. 첫째 행", "[4,-2]", "첫째 행의 각 성분에 2를 곱하세요."),
                    exact_step("Step 2. 둘째 행", "[0,6]", "둘째 행의 각 성분에 2를 곱하세요."),
                    exact_step("Step 3. 행렬 완성", "[[4,-2],[0,6]]", "실수배 행렬을 적으세요."),
                ],
                final=exact_step("최종 답", "[[4,-2],[0,6]]", "실수배 결과를 적으세요."),
                coach_hint="실수배는 행 전체가 아니라 모든 성분에 같은 수를 곱합니다.",
                expected_outline=["첫째 행", "둘째 행", "행렬 조립", "최종 행렬"],
                final_prompt="예: [[4,-2],[0,6]]",
            ),
            structured_problem(
                problem_id="curr-matrix-003",
                title="행렬 곱셈",
                statement="A=[[1,2],[3,4]], B=[[2,0],[1,2]]일 때 AB를 구하시오.",
                unit_title="공통수학1 - 행렬",
                course_title="공통수학1",
                achievement_codes=["10공수1-04-02"],
                steps=[
                    exact_step("Step 1. 첫째 행 첫째 열", "4", "1*2+2*1을 계산하세요."),
                    exact_step("Step 2. 첫째 행 둘째 열", "4", "1*0+2*2를 계산하세요."),
                    exact_step("Step 3. 행렬 완성", "[[4,4],[10,8]]", "나머지 성분까지 계산해 곱행렬을 적으세요."),
                ],
                final=exact_step("최종 답", "[[4,4],[10,8]]", "행렬 곱 AB를 적으세요."),
                coach_hint="행렬 곱은 행과 열의 내적으로 계산합니다.",
                expected_outline=["한 성분 계산", "한 성분 계산", "전체 행렬 완성", "최종 행렬"],
                final_prompt="예: [[4,4],[10,8]]",
            ),
        ],
    },
    {
        "id": "common2-coordinate",
        "courseId": "common-math-2",
        "courseTitle": "공통수학2",
        "domainTitle": "도형의 방정식",
        "pdfPages": "64-65",
        "coreIdea": "평면도형을 식으로 표현해 위치 관계와 이동을 해석하는 단원입니다.",
        "contentElements": ["평면좌표", "직선의 방정식", "원의 방정식", "도형의 이동"],
        "achievementCodes": ["10공수2-01-01", "10공수2-01-07"],
        "questionStarters": ["내분점 공식이 왜 그렇게 되는지 알려줘", "원과 직선 위치 관계를 판단하고 싶어", "대칭이동을 좌표로 정리해줘"],
        "diagnostic": {"prompt": "다음 중 공통수학2의 도형의 방정식 단원 핵심 내용은?", "answer": "원의 방정식"},
        "problems": [
            structured_problem(
                problem_id="curr-geom2-001",
                title="내분점",
                statement="점 A(1,2), B(7,8)을 1:2로 내분하는 점의 좌표를 구하시오.",
                unit_title="공통수학2 - 도형의 방정식",
                course_title="공통수학2",
                achievement_codes=["10공수2-01-01"],
                steps=[
                    numeric_step("Step 1. x좌표", "3", "x좌표를 내분 공식으로 계산하세요."),
                    numeric_step("Step 2. y좌표", "4", "y좌표를 내분 공식으로 계산하세요."),
                    exact_step("Step 3. 좌표 완성", "(3,4)", "내분점 좌표를 정리하세요."),
                ],
                final=exact_step("최종 답", "(3,4)", "내분점 좌표를 적으세요."),
                coach_hint="내분은 가까운 점의 가중치를 반대로 곱해 평균내는 구조입니다.",
                expected_outline=["x좌표", "y좌표", "좌표 완성", "최종 답"],
                final_prompt="예: (3,4)",
            ),
            structured_problem(
                problem_id="curr-geom2-002",
                title="직선의 방정식",
                statement="점 (1,1)을 지나고 기울기가 2인 직선의 방정식을 구하시오.",
                unit_title="공통수학2 - 도형의 방정식",
                course_title="공통수학2",
                achievement_codes=["10공수2-01-02"],
                steps=[
                    expr_step("Step 1. 점기울기식", "y-1-2*(x-1)", "점기울기식 형태를 먼저 쓰세요.", display="y-1 = 2(x-1)"),
                    expr_step("Step 2. 정리", "2*x-1", "우변을 y= 꼴로 정리하세요.", display="2x-1"),
                    exact_step("Step 3. 직선식 해석", "y=2x-1", "직선식을 완성하세요."),
                ],
                final=exact_step("최종 답", "y=2x-1", "직선의 방정식을 적으세요."),
                coach_hint="기울기와 한 점이 있으면 점기울기식으로 바로 출발하세요.",
                expected_outline=["점기울기식", "정리", "직선식", "최종 답"],
                final_prompt="예: y=2x-1",
            ),
            structured_problem(
                problem_id="curr-geom2-003",
                title="원의 방정식",
                statement="중심이 (2,-1)이고 반지름이 3인 원의 방정식을 구하시오.",
                unit_title="공통수학2 - 도형의 방정식",
                course_title="공통수학2",
                achievement_codes=["10공수2-01-04"],
                steps=[
                    exact_step("Step 1. 기본형", "(x-2)^2+(y+1)^2=3^2", "중심과 반지름을 기본형에 대입하세요."),
                    exact_step("Step 2. 반지름 제곱", "(x-2)^2+(y+1)^2=9", "r^2 값을 계산하세요."),
                    exact_step("Step 3. 최종 정리", "(x-2)^2+(y+1)^2=9", "원의 방정식을 최종적으로 적으세요."),
                ],
                final=exact_step("최종 답", "(x-2)^2+(y+1)^2=9", "원의 방정식을 적으세요."),
                coach_hint="원의 기본형은 중심과 반지름이 보이면 바로 완성됩니다.",
                expected_outline=["기본형 대입", "r^2 계산", "최종 정리", "최종 답"],
                final_prompt="예: (x-2)^2+(y+1)^2=9",
            ),
        ],
    },
    {
        "id": "common2-set",
        "courseId": "common-math-2",
        "courseTitle": "공통수학2",
        "domainTitle": "집합과 명제",
        "pdfPages": "66",
        "coreIdea": "집합으로 대상을 표현하고 명제로 추론 구조를 다루는 단원입니다.",
        "contentElements": ["집합", "명제"],
        "achievementCodes": ["10공수2-02-01", "10공수2-02-08"],
        "questionStarters": ["필요조건과 충분조건을 구분해줘", "드모르간 법칙이 헷갈려", "대우 증명 구조를 짚어줘"],
        "diagnostic": {"prompt": "다음 중 공통수학2의 집합과 명제 단원 핵심 내용은?", "answer": "대우와 귀류법"},
        "problems": [
            structured_problem(
                problem_id="curr-set-001",
                title="집합 연산",
                statement="A={1,2,3}, B={2,3,4}일 때 A∩B를 구하시오.",
                unit_title="공통수학2 - 집합과 명제",
                course_title="공통수학2",
                achievement_codes=["10공수2-02-03"],
                steps=[
                    exact_step("Step 1. A의 원소", "{1,2,3}", "A의 원소를 확인하세요."),
                    exact_step("Step 2. B의 원소", "{2,3,4}", "B의 원소를 확인하세요."),
                    exact_step("Step 3. 공통 원소", "{2,3}", "공통인 원소만 모으세요."),
                ],
                final=exact_step("최종 답", "{2,3}", "교집합을 적으세요."),
                coach_hint="교집합은 두 집합에 동시에 들어 있는 원소만 남깁니다.",
                expected_outline=["A 확인", "B 확인", "공통 원소", "최종 답"],
                final_prompt="예: {2,3}",
            ),
            structured_problem(
                problem_id="curr-set-002",
                title="명제의 대우",
                statement="명제 'p→q'의 대우를 고르시오. 답은 기호로 쓰시오.",
                unit_title="공통수학2 - 집합과 명제",
                course_title="공통수학2",
                achievement_codes=["10공수2-02-05", "10공수2-02-07"],
                steps=[
                    exact_step("Step 1. 원래 명제", "p->q", "원래 명제를 적으세요."),
                    exact_step("Step 2. 부정 만들기", "~q와~p", "결론과 가정을 각각 부정하세요."),
                    exact_step("Step 3. 순서 바꾸기", "~q->~p", "부정한 결론을 가정 위치로 옮기세요."),
                ],
                final=exact_step("최종 답", "~q->~p", "대우를 적으세요."),
                coach_hint="대우는 부정 + 순서 바꾸기입니다.",
                expected_outline=["원래 명제", "부정", "대우 작성", "최종 답"],
                final_prompt="예: ~q->~p",
            ),
            structured_problem(
                problem_id="curr-set-003",
                title="필요충분조건 판단",
                statement="'x=2이면 x^2=4이다.'에서 x=2는 x^2=4의 어떤 조건인지 적으시오.",
                unit_title="공통수학2 - 집합과 명제",
                course_title="공통수학2",
                achievement_codes=["10공수2-02-06"],
                steps=[
                    exact_step("Step 1. 가정", "x=2", "가정을 적으세요."),
                    exact_step("Step 2. 결론", "x^2=4", "결론을 적으세요."),
                    exact_step("Step 3. 조건 해석", "충분조건", "가정이 결론을 보장하는지 판단하세요."),
                ],
                final=exact_step("최종 답", "충분조건", "조건의 종류를 적으세요."),
                coach_hint="가정이 결론을 보장하면 충분조건입니다.",
                expected_outline=["가정", "결론", "관계 판단", "최종 답"],
                final_prompt="예: 충분조건",
            ),
        ],
    },
    {
        "id": "common2-function",
        "courseId": "common-math-2",
        "courseTitle": "공통수학2",
        "domainTitle": "함수와 그래프",
        "pdfPages": "67",
        "coreIdea": "함수의 대응, 합성, 역함수, 유리함수와 무리함수의 그래프를 다루는 단원입니다.",
        "contentElements": ["함수", "유리함수와 무리함수"],
        "achievementCodes": ["10공수2-03-01", "10공수2-03-05"],
        "questionStarters": ["합성함수와 역함수 차이를 알려줘", "유리함수 그래프 성질만 빠르게 보고 싶어", "무리함수 그래프 이동을 설명해줘"],
        "diagnostic": {"prompt": "다음 중 공통수학2의 함수와 그래프 단원 핵심 내용은?", "answer": "합성함수와 역함수"},
        "problems": [
            structured_problem(
                problem_id="curr-func-001",
                title="합성함수",
                statement="f(x)=2x+1, g(x)=x^2일 때 (g∘f)(x)를 구하시오.",
                unit_title="공통수학2 - 함수와 그래프",
                course_title="공통수학2",
                achievement_codes=["10공수2-03-02"],
                steps=[
                    expr_step("Step 1. 안쪽 함수 대입", "(2*x+1)**2", "g(f(x)) 꼴로 먼저 쓰세요.", display="(2x+1)^2"),
                    expr_step("Step 2. 전개", "4*x**2+4*x+1", "필요하면 전개해 정리하세요."),
                    exact_step("Step 3. 합성함수 이름", "(g∘f)(x)=4*x**2+4*x+1", "합성함수를 완성하세요."),
                ],
                final=expr_step("최종 답", "4*x**2+4*x+1", "합성함수 결과를 적으세요.", display="4x^2+4x+1"),
                coach_hint="합성은 바깥 함수에 안쪽 함수 전체를 통째로 넣는 것입니다.",
                expected_outline=["대입", "전개", "합성함수 표기", "최종 답"],
                final_prompt="예: 4*x**2+4*x+1",
            ),
            structured_problem(
                problem_id="curr-func-002",
                title="역함수",
                statement="f(x)=3x-2의 역함수를 구하시오.",
                unit_title="공통수학2 - 함수와 그래프",
                course_title="공통수학2",
                achievement_codes=["10공수2-03-03"],
                steps=[
                    exact_step("Step 1. y로 두기", "y=3*x-2", "먼저 y로 두고 식을 적으세요."),
                    expr_step("Step 2. x에 대해 풀기", "(y+2)/3", "x에 대해 풀어 보세요.", display="(y+2)/3"),
                    exact_step("Step 3. 변수 교환", "f^-1(x)=(x+2)/3", "x와 y를 바꿔 역함수를 완성하세요."),
                ],
                final=expr_step("최종 답", "(x+2)/3", "역함수의 식을 적으세요.", display="(x+2)/3"),
                coach_hint="역함수는 y로 두고 x에 대해 푼 뒤 x와 y를 바꾸는 절차입니다.",
                expected_outline=["y로 두기", "x에 대해 풀기", "변수 교환", "최종 답"],
                final_prompt="예: (x+2)/3",
            ),
            structured_problem(
                problem_id="curr-func-003",
                title="유리함수 값",
                statement="y=(2x+1)/(x-1)에서 x=2일 때 함수값을 구하시오.",
                unit_title="공통수학2 - 함수와 그래프",
                course_title="공통수학2",
                achievement_codes=["10공수2-03-04"],
                steps=[
                    expr_step("Step 1. 대입식", "(2*2+1)/(2-1)", "x=2를 그대로 대입하세요.", display="(2·2+1)/(2-1)"),
                    numeric_step("Step 2. 분자 계산", "5", "분자를 계산하세요."),
                    numeric_step("Step 3. 함수값", "5", "분모까지 계산해 함수값을 구하세요."),
                ],
                final=numeric_step("최종 답", "5", "함수값을 적으세요."),
                coach_hint="유리함수는 먼저 정의역을 점검하고, 허용되는 x면 그대로 대입합니다.",
                expected_outline=["대입", "분자", "함수값", "최종 답"],
                final_prompt="예: 5",
            ),
        ],
    },
    {
        "id": "algebra-exp-log",
        "courseId": "algebra",
        "courseTitle": "대수",
        "domainTitle": "지수함수와 로그함수",
        "pdfPages": "99-100",
        "coreIdea": "지수와 로그, 지수함수와 로그함수로 급격한 변화 현상을 표현하는 단원입니다.",
        "contentElements": ["지수와 로그", "지수함수와 로그함수"],
        "achievementCodes": ["12대수01-01", "12대수01-08"],
        "questionStarters": ["상용로그를 왜 배우는지 궁금해", "지수함수와 로그함수 그래프 관계를 알려줘", "로그 성질을 빠르게 정리해줘"],
        "diagnostic": {"prompt": "다음 중 대수의 지수함수와 로그함수 단원 핵심 내용은?", "answer": "지수법칙과 로그의 성질"},
        "problems": [
            structured_problem(
                problem_id="curr-alg-001",
                title="지수법칙",
                statement="2^3 · 2^4를 계산하시오.",
                unit_title="대수 - 지수함수와 로그함수",
                course_title="대수",
                achievement_codes=["12대수01-03"],
                steps=[
                    expr_step("Step 1. 지수 더하기", "2**(3+4)", "같은 밑의 곱은 지수를 더하세요.", display="2^(3+4)"),
                    expr_step("Step 2. 단순화", "2**7", "지수끼리 더해 한 거듭제곱으로 만드세요."),
                    numeric_step("Step 3. 계산", "128", "거듭제곱 값을 계산하세요."),
                ],
                final=numeric_step("최종 답", "128", "계산 결과를 적으세요."),
                coach_hint="같은 밑의 곱은 지수 더하기로 한 줄 처리합니다.",
                expected_outline=["지수법칙", "정리", "계산", "최종 답"],
                final_prompt="예: 128",
            ),
            structured_problem(
                problem_id="curr-alg-002",
                title="로그값 계산",
                statement="log2(8)의 값을 구하시오.",
                unit_title="대수 - 지수함수와 로그함수",
                course_title="대수",
                achievement_codes=["12대수01-04"],
                steps=[
                    exact_step("Step 1. 정의 연결", "2^x=8", "로그 정의를 지수형으로 바꾸세요."),
                    numeric_step("Step 2. 지수 찾기", "3", "2의 몇 제곱이 8인지 찾으세요."),
                    exact_step("Step 3. 로그값 해석", "log2(8)=3", "로그값을 정리하세요."),
                ],
                final=numeric_step("최종 답", "3", "로그값을 적으세요."),
                coach_hint="로그는 '몇 제곱인가'를 묻는 질문으로 바꾸면 빨라집니다.",
                expected_outline=["정의", "지수 찾기", "해석", "최종 답"],
                final_prompt="예: 3",
            ),
            structured_problem(
                problem_id="curr-alg-003",
                title="지수방정식",
                statement="2^x=16을 만족하는 x를 구하시오.",
                unit_title="대수 - 지수함수와 로그함수",
                course_title="대수",
                achievement_codes=["12대수01-08"],
                steps=[
                    exact_step("Step 1. 같은 밑으로 바꾸기", "16=2^4", "16을 2의 거듭제곱으로 바꾸세요."),
                    exact_step("Step 2. 지수 비교", "x=4", "같은 밑이면 지수를 비교하세요."),
                    solution_step("Step 3. 해 정리", ["4"], "해를 정리하세요."),
                ],
                final=numeric_step("최종 답", "4", "x의 값을 적으세요."),
                coach_hint="지수방정식은 같은 밑으로 통일한 뒤 지수만 비교합니다.",
                expected_outline=["같은 밑", "지수 비교", "해 정리", "최종 답"],
                final_prompt="예: 4",
            ),
        ],
    },
    {
        "id": "algebra-trig",
        "courseId": "algebra",
        "courseTitle": "대수",
        "domainTitle": "삼각함수",
        "pdfPages": "101",
        "coreIdea": "주기적 현상을 삼각함수로 표현하고 사인법칙, 코사인법칙으로 문제를 해결하는 단원입니다.",
        "contentElements": ["삼각함수", "사인법칙과 코사인법칙"],
        "achievementCodes": ["12대수02-01", "12대수02-03"],
        "questionStarters": ["호도법을 직관적으로 설명해줘", "삼각함수 그래프 성질만 요약해줘", "코사인법칙 적용 순서를 알려줘"],
        "diagnostic": {"prompt": "다음 중 대수의 삼각함수 단원 핵심 내용은?", "answer": "사인법칙과 코사인법칙"},
        "problems": [
            structured_problem(
                problem_id="curr-trig-001",
                title="삼각함수 값",
                statement="sin 30°의 값을 구하시오.",
                unit_title="대수 - 삼각함수",
                course_title="대수",
                achievement_codes=["12대수02-02"],
                steps=[
                    exact_step("Step 1. 기본각 인식", "30도", "기본각이라는 점을 먼저 확인하세요."),
                    exact_step("Step 2. 표준값 회상", "1/2", "sin 30°의 표준값을 적으세요."),
                    exact_step("Step 3. 함수값 해석", "sin30=1/2", "삼각함수값을 정리하세요."),
                ],
                final=exact_step("최종 답", "1/2", "삼각함수값을 적으세요."),
                coach_hint="기본각의 사인, 코사인 값은 즉시 호출할 수 있어야 합니다.",
                expected_outline=["기본각", "표준값", "정리", "최종 답"],
                final_prompt="예: 1/2",
            ),
            structured_problem(
                problem_id="curr-trig-002",
                title="코사인법칙",
                statement="변의 길이가 3, 4이고 끼인각이 90도인 삼각형의 나머지 한 변의 길이를 구하시오.",
                unit_title="대수 - 삼각함수",
                course_title="대수",
                achievement_codes=["12대수02-03"],
                steps=[
                    expr_step("Step 1. 코사인법칙", "3**2+4**2-2*3*4*0", "cos90°=0을 넣어 코사인법칙을 세우세요.", display="3^2+4^2-2·3·4·0"),
                    numeric_step("Step 2. 제곱 계산", "25", "변의 제곱을 계산하세요."),
                    exact_step("Step 3. 길이 해석", "5", "길이를 구해 정리하세요."),
                ],
                final=numeric_step("최종 답", "5", "남은 변의 길이를 적으세요."),
                coach_hint="직각이라도 삼각법 단원에서는 코사인법칙으로 연결해 볼 수 있어야 합니다.",
                expected_outline=["코사인법칙", "계산", "길이 해석", "최종 답"],
                final_prompt="예: 5",
            ),
            structured_problem(
                problem_id="curr-trig-003",
                title="사인법칙",
                statement="삼각형에서 a/sinA = 6, sinA = 1/2일 때 a의 값을 구하시오.",
                unit_title="대수 - 삼각함수",
                course_title="대수",
                achievement_codes=["12대수02-03"],
                steps=[
                    expr_step("Step 1. 식 세우기", "a/((1)/(2)) - 6", "a/sinA=6에 sinA 값을 대입하세요.", display="a/(1/2)=6"),
                    expr_step("Step 2. a 구하기", "a-3", "양변을 정리해 a를 구하세요.", display="a=3"),
                    exact_step("Step 3. 길이 해석", "a=3", "최종 길이를 정리하세요."),
                ],
                final=numeric_step("최종 답", "3", "a의 값을 적으세요."),
                coach_hint="사인법칙은 비율 하나를 알면 바로 한 변을 복원할 수 있습니다.",
                expected_outline=["대입", "정리", "길이 해석", "최종 답"],
                final_prompt="예: 3",
            ),
        ],
    },
    {
        "id": "algebra-sequence",
        "courseId": "algebra",
        "courseTitle": "대수",
        "domainTitle": "수열",
        "pdfPages": "102",
        "coreIdea": "등차수열, 등비수열, 수열의 합, 수학적 귀납법을 다루는 단원입니다.",
        "contentElements": ["등차수열과 등비수열", "수열의 합", "수학적 귀납법"],
        "achievementCodes": ["12대수03-01", "12대수03-07"],
        "questionStarters": ["등차와 등비를 어떻게 빨리 구분해?", "시그마가 나올 때 접근법이 궁금해", "귀납법 구조를 설명해줘"],
        "diagnostic": {"prompt": "다음 중 대수의 수열 단원 핵심 내용은?", "answer": "등차수열과 등비수열"},
        "problems": [
            structured_problem(
                problem_id="curr-seq-001",
                title="등차수열 일반항",
                statement="첫째항이 2, 공차가 3인 등차수열의 제n항을 구하시오.",
                unit_title="대수 - 수열",
                course_title="대수",
                achievement_codes=["12대수03-02"],
                steps=[
                    exact_step("Step 1. 일반항 공식", "a_n=a_1+(n-1)d", "등차수열 일반항 공식을 먼저 적으세요."),
                    expr_step("Step 2. 값 대입", "2+(n-1)*3", "a1과 d를 공식에 넣으세요.", display="2+3(n-1)"),
                    expr_step("Step 3. 정리", "3*n-1", "일반항을 정리하세요.", display="3n-1"),
                ],
                final=expr_step("최종 답", "3*n-1", "제n항을 적으세요.", display="3n-1"),
                coach_hint="등차수열은 '첫째항 + (n-1)번 이동'으로 기억하세요.",
                expected_outline=["공식", "대입", "정리", "최종 답"],
                final_prompt="예: 3*n-1",
            ),
            structured_problem(
                problem_id="curr-seq-002",
                title="등비수열의 합",
                statement="첫째항이 3, 공비가 2인 등비수열의 첫째항부터 넷째항까지의 합을 구하시오.",
                unit_title="대수 - 수열",
                course_title="대수",
                achievement_codes=["12대수03-03"],
                steps=[
                    expr_step("Step 1. 합 공식", "3*(2**4-1)/(2-1)", "등비수열의 합 공식을 적용하세요.", display="3(2^4-1)/(2-1)"),
                    numeric_step("Step 2. 지수 계산", "45", "합을 계산하세요."),
                    exact_step("Step 3. 결과 확인", "S4=45", "합을 기호와 함께 정리하세요."),
                ],
                final=numeric_step("최종 답", "45", "합을 적으세요."),
                coach_hint="등비수열의 합은 첫째항과 공비, 항 수를 바로 공식에 넣으세요.",
                expected_outline=["합 공식", "계산", "정리", "최종 답"],
                final_prompt="예: 45",
            ),
            structured_problem(
                problem_id="curr-seq-003",
                title="시그마 계산",
                statement="1부터 5까지의 자연수의 합을 구하시오.",
                unit_title="대수 - 수열",
                course_title="대수",
                achievement_codes=["12대수03-04", "12대수03-05"],
                steps=[
                    expr_step("Step 1. 시그마 해석", "1+2+3+4+5", "시그마를 덧셈으로 펼치세요."),
                    numeric_step("Step 2. 합 계산", "15", "합을 계산하세요."),
                    exact_step("Step 3. 결과 정리", "15", "결과를 정리하세요."),
                ],
                final=numeric_step("최종 답", "15", "합을 적으세요."),
                coach_hint="작은 n의 시그마는 직접 전개해 의미를 먼저 붙이면 흔들리지 않습니다.",
                expected_outline=["시그마 전개", "계산", "정리", "최종 답"],
                final_prompt="예: 15",
            ),
        ],
    },
    {
        "id": "calc1-limit",
        "courseId": "calculus-1",
        "courseTitle": "미적분Ⅰ",
        "domainTitle": "함수의 극한과 연속",
        "pdfPages": "113-114",
        "coreIdea": "함수의 극한과 연속을 통해 국소적 성질과 연속함수의 성질을 다루는 단원입니다.",
        "contentElements": ["함수의 극한", "함수의 연속"],
        "achievementCodes": ["12미적Ⅰ-01-01", "12미적Ⅰ-01-04"],
        "questionStarters": ["좌극한과 우극한을 같이 보고 싶어", "연속 판정 순서를 설명해줘", "사잇값정리가 왜 중요한지 궁금해"],
        "diagnostic": {"prompt": "다음 중 미적분Ⅰ의 함수의 극한과 연속 단원 핵심 내용은?", "answer": "함수의 극한"},
        "problems": [
            structured_problem(
                problem_id="curr-limit-001",
                title="다항함수 극한",
                statement="lim(x→2) (x^2+1)의 값을 구하시오.",
                unit_title="미적분Ⅰ - 함수의 극한과 연속",
                course_title="미적분Ⅰ",
                achievement_codes=["12미적Ⅰ-01-02"],
                steps=[
                    expr_step("Step 1. 직접 대입", "2**2+1", "다항함수이므로 x=2를 직접 대입하세요.", display="2^2+1"),
                    numeric_step("Step 2. 계산", "5", "극한값을 계산하세요."),
                    exact_step("Step 3. 극한값 정리", "5", "극한값을 정리하세요."),
                ],
                final=numeric_step("최종 답", "5", "극한값을 적으세요."),
                coach_hint="다항함수 극한은 먼저 직접 대입 가능한지 보는 습관이 중요합니다.",
                expected_outline=["직접 대입", "계산", "정리", "최종 답"],
                final_prompt="예: 5",
            ),
            structured_problem(
                problem_id="curr-limit-002",
                title="극한의 성질",
                statement="lim(x→1) (3x-2)의 값을 구하시오.",
                unit_title="미적분Ⅰ - 함수의 극한과 연속",
                course_title="미적분Ⅰ",
                achievement_codes=["12미적Ⅰ-01-02"],
                steps=[
                    expr_step("Step 1. 대입식", "3*1-2", "직접 대입식을 적으세요.", display="3·1-2"),
                    numeric_step("Step 2. 계산", "1", "값을 계산하세요."),
                    exact_step("Step 3. 극한값 정리", "1", "극한값을 적으세요."),
                ],
                final=numeric_step("최종 답", "1", "극한값을 적으세요."),
                coach_hint="일차함수도 직접 대입으로 바로 처리할 수 있습니다.",
                expected_outline=["대입식", "계산", "정리", "최종 답"],
                final_prompt="예: 1",
            ),
            structured_problem(
                problem_id="curr-limit-003",
                title="연속성 판정",
                statement="f(x)=x^2+1은 x=3에서 연속인지 판단하시오. 답은 '연속' 또는 '불연속'으로 쓰시오.",
                unit_title="미적분Ⅰ - 함수의 극한과 연속",
                course_title="미적분Ⅰ",
                achievement_codes=["12미적Ⅰ-01-03"],
                steps=[
                    numeric_step("Step 1. 함수값", "10", "f(3)을 계산하세요."),
                    numeric_step("Step 2. 극한값", "10", "x→3일 때 극한값을 계산하세요."),
                    exact_step("Step 3. 비교", "연속", "함수값과 극한값이 같은지 판단하세요."),
                ],
                final=exact_step("최종 답", "연속", "연속 여부를 적으세요."),
                coach_hint="연속 판정은 함수값과 극한값을 같은 자리에서 비교하는 문제입니다.",
                expected_outline=["함수값", "극한값", "비교", "최종 판단"],
                final_prompt="예: 연속",
            ),
        ],
    },
    {
        "id": "calc1-diff",
        "courseId": "calculus-1",
        "courseTitle": "미적분Ⅰ",
        "domainTitle": "미분",
        "pdfPages": "115",
        "coreIdea": "미분계수, 도함수, 접선, 증가감소와 극값을 다루는 핵심 단원입니다.",
        "contentElements": ["미분계수", "도함수", "도함수의 활용"],
        "achievementCodes": ["12미적Ⅰ-02-01", "12미적Ⅰ-02-10"],
        "questionStarters": ["접선의 의미를 다시 짚어줘", "증가와 감소 판정이 헷갈려", "도함수 활용 흐름을 보여줘"],
        "diagnostic": {"prompt": "다음 중 미적분Ⅰ의 미분 단원 핵심 내용은?", "answer": "접선의 방정식"},
        "problems": [
            structured_problem(
                problem_id="curr-diff-001",
                title="다항함수의 도함수",
                statement="f(x)=x^3-2x^2+1의 도함수를 구하시오.",
                unit_title="미적분Ⅰ - 미분",
                course_title="미적분Ⅰ",
                achievement_codes=["12미적Ⅰ-02-03", "12미적Ⅰ-02-04"],
                steps=[
                    expr_step("Step 1. x^3 미분", "3*x**2", "x^3의 도함수를 적으세요."),
                    expr_step("Step 2. -2x^2 미분", "-4*x", "-2x^2의 도함수를 적으세요."),
                    expr_step("Step 3. 합치기", "3*x**2-4*x", "각 항의 도함수를 합치세요.", display="3x^2-4x"),
                ],
                final=expr_step("최종 답", "3*x**2-4*x", "도함수를 적으세요.", display="3x^2-4x"),
                coach_hint="다항함수 미분은 항별 미분 후 합치는 흐름을 고정하세요.",
                expected_outline=["항별 미분", "항별 미분", "합치기", "최종 답"],
                final_prompt="예: 3*x**2-4*x",
            ),
            tangent_problem(
                problem_id="curr-diff-002",
                title="접선의 방정식",
                statement="함수 f(x)=x^2-3x+2의 x=1에서의 접선의 방정식을 구하시오.",
                course_title="미적분Ⅰ",
                unit_title="미적분Ⅰ - 미분",
                achievement_codes=["12미적Ⅰ-02-05"],
                expression="x**2-3*x+2",
                point_x=1,
                problem_type="접선 기본형",
            ),
            structured_problem(
                problem_id="curr-diff-003",
                title="증가와 감소 판정",
                statement="f'(x)=2x-4일 때 x=3에서 함수가 증가 중인지 감소 중인지 판단하시오.",
                unit_title="미적분Ⅰ - 미분",
                course_title="미적분Ⅰ",
                achievement_codes=["12미적Ⅰ-02-07"],
                steps=[
                    expr_step("Step 1. 도함수값", "2*3-4", "x=3을 도함수에 대입하세요.", display="2·3-4"),
                    numeric_step("Step 2. 부호 판단", "2", "도함수값의 부호를 계산하세요."),
                    exact_step("Step 3. 증가/감소 판정", "증가", "도함수값이 양수인지 음수인지 해석하세요."),
                ],
                final=exact_step("최종 답", "증가", "판정 결과를 적으세요."),
                coach_hint="도함수값의 부호를 읽으면 증가/감소가 바로 결정됩니다.",
                expected_outline=["대입", "부호 계산", "해석", "최종 판단"],
                final_prompt="예: 증가",
                problem_type="증가·감소 판정형",
            ),
            structured_problem(
                problem_id="curr-diff-029",
                title="극값을 잇는 직선 킬러 문제",
                statement="함수 f(x)=x^3-6x^2+9x+4의 극대점과 극소점을 지나는 직선의 방정식을 구하시오.",
                unit_title="미적분Ⅰ - 미분",
                course_title="미적분Ⅰ",
                achievement_codes=["12미적Ⅰ-02-07", "12미적Ⅰ-02-10"],
                steps=[
                    expr_step("Step 1. 도함수 인수분해", "3*(x-1)*(x-3)", "도함수를 구한 뒤 극값 후보가 보이도록 인수분해하세요.", display="3(x-1)(x-3)"),
                    exact_step("Step 2. 극값 좌표", "(1,8),(3,4)", "극대점과 극소점의 좌표를 둘 다 구하세요."),
                    exact_step("Step 3. 두 점을 잇는 기울기", "-2", "두 점의 y변화량과 x변화량으로 직선의 기울기를 구하세요."),
                ],
                final=exact_step("최종 답", "y=-2x+10", "극값을 지나는 직선의 방정식을 적으세요."),
                coach_hint="킬러 문제는 도함수로 극값 좌표를 만들고, 마지막에 직선 한 줄로 구조를 전환해야 합니다.",
                expected_outline=["도함수 인수분해", "극값 좌표", "기울기", "직선식"],
                final_prompt="예: y=-2x+10",
                difficulty="killer",
                problem_type="킬러 문제 · 극값-직선 결합",
                is_killer=True,
            ),
        ],
    },
    {
        "id": "calc1-integral",
        "courseId": "calculus-1",
        "courseTitle": "미적분Ⅰ",
        "domainTitle": "적분",
        "pdfPages": "116",
        "coreIdea": "부정적분, 정적분, 도형의 넓이와 거리로 이어지는 적분의 기본 단원입니다.",
        "contentElements": ["부정적분", "정적분", "정적분의 활용"],
        "achievementCodes": ["12미적Ⅰ-03-01", "12미적Ⅰ-03-06"],
        "questionStarters": ["부정적분과 정적분 관계를 알려줘", "넓이 문제를 적분으로 바꾸는 법이 궁금해", "미적분의 기본정리를 설명해줘"],
        "diagnostic": {"prompt": "다음 중 미적분Ⅰ의 적분 단원 핵심 내용은?", "answer": "부정적분과 정적분"},
        "problems": [
            structured_problem(
                problem_id="curr-int-001",
                title="부정적분",
                statement="∫(2x+1)dx를 구하시오.",
                unit_title="미적분Ⅰ - 적분",
                course_title="미적분Ⅰ",
                achievement_codes=["12미적Ⅰ-03-01", "12미적Ⅰ-03-02"],
                steps=[
                    expr_step("Step 1. 2x 적분", "x**2", "2x의 부정적분을 적으세요."),
                    expr_step("Step 2. 1 적분", "x", "1의 부정적분을 적으세요."),
                    expr_step("Step 3. 합치기", "x**2+x", "두 적분 결과를 합치세요.", display="x^2+x"),
                ],
                final=expr_step("최종 답", "x**2+x", "부정적분 결과를 적으세요.", display="x^2+x"),
                coach_hint="부정적분도 항별로 처리한 뒤 적분상수는 맨 마지막에 챙기면 됩니다.",
                expected_outline=["항별 적분", "항별 적분", "합치기", "최종 답"],
                final_prompt="예: x**2+x+C",
            ),
            structured_problem(
                problem_id="curr-int-002",
                title="정적분",
                statement="∫(0→2) x dx의 값을 구하시오.",
                unit_title="미적분Ⅰ - 적분",
                course_title="미적분Ⅰ",
                achievement_codes=["12미적Ⅰ-03-03", "12미적Ⅰ-03-04"],
                steps=[
                    expr_step("Step 1. 원시함수", "x**2/2", "x의 부정적분을 먼저 구하세요.", display="x^2/2"),
                    expr_step("Step 2. 상한 대입", "(2**2)/2 - (0**2)/2", "상한과 하한을 대입하세요.", display="2^2/2 - 0"),
                    numeric_step("Step 3. 계산", "2", "정적분 값을 계산하세요."),
                ],
                final=numeric_step("최종 답", "2", "정적분 값을 적으세요."),
                coach_hint="정적분은 원시함수를 구한 뒤 상한-하한 순서로 넣습니다.",
                expected_outline=["원시함수", "대입", "계산", "최종 답"],
                final_prompt="예: 2",
            ),
            structured_problem(
                problem_id="curr-int-003",
                title="도형의 넓이",
                statement="y=x, x=0, x=2, x축으로 둘러싸인 도형의 넓이를 구하시오.",
                unit_title="미적분Ⅰ - 적분",
                course_title="미적분Ⅰ",
                achievement_codes=["12미적Ⅰ-03-05"],
                steps=[
                    exact_step("Step 1. 넓이 적분식", "∫0→2 x dx", "넓이는 ∫0→2 x dx 로 연결됩니다."),
                    expr_step("Step 2. 원시함수", "x**2/2", "원시함수를 구하세요.", display="x^2/2"),
                    numeric_step("Step 3. 넓이 계산", "2", "넓이를 계산하세요."),
                ],
                final=numeric_step("최종 답", "2", "도형의 넓이를 적으세요."),
                coach_hint="넓이 문제는 함수-축-구간을 먼저 적분식으로 바꾸는 것이 핵심입니다.",
                expected_outline=["적분식", "원시함수", "계산", "최종 넓이"],
                final_prompt="예: 2",
            ),
        ],
    },
    {
        "id": "probstat-counting",
        "courseId": "probability-statistics",
        "courseTitle": "확률과 통계",
        "domainTitle": "경우의 수",
        "pdfPages": "127-128",
        "coreIdea": "중복순열, 중복조합, 이항정리로 경우를 세는 확률과 통계의 기초 단원입니다.",
        "contentElements": ["순열과 조합", "이항정리"],
        "achievementCodes": ["12확통01-01", "12확통01-03"],
        "questionStarters": ["중복순열과 순열 차이를 알려줘", "이항정리 전개를 빠르게 하고 싶어", "조합과 중복조합 구분법이 궁금해"],
        "diagnostic": {"prompt": "다음 중 확률과 통계의 경우의 수 단원 핵심 내용은?", "answer": "중복순열과 이항정리"},
        "problems": [
            structured_problem(
                problem_id="curr-pcount-001",
                title="중복순열",
                statement="숫자 1,2,3을 중복을 허락하여 두 자리 수를 만드는 방법의 수를 구하시오.",
                unit_title="확률과 통계 - 경우의 수",
                course_title="확률과 통계",
                achievement_codes=["12확통01-01"],
                steps=[
                    numeric_step("Step 1. 첫째 자리", "3", "첫째 자리에 올 수 있는 숫자 수를 적으세요."),
                    numeric_step("Step 2. 둘째 자리", "3", "둘째 자리도 중복 허용이므로 같은 수를 적으세요."),
                    expr_step("Step 3. 곱셈", "3*3", "곱의 법칙으로 정리하세요.", display="3×3"),
                ],
                final=numeric_step("최종 답", "9", "방법의 수를 적으세요."),
                coach_hint="중복 허용이면 각 자리의 선택 수가 줄지 않습니다.",
                expected_outline=["첫 자리", "둘째 자리", "곱셈", "최종 수"],
                final_prompt="예: 9",
            ),
            structured_problem(
                problem_id="curr-pcount-002",
                title="중복조합",
                statement="서로 다른 3종류의 사탕 중 2개를 고르는 방법의 수를 구하시오.",
                unit_title="확률과 통계 - 경우의 수",
                course_title="확률과 통계",
                achievement_codes=["12확통01-02"],
                steps=[
                    exact_step("Step 1. 중복조합식", "3H2", "중복조합 기호로 먼저 적으세요."),
                    expr_step("Step 2. 조합으로 변환", "4*3/2", "3H2 = 4C2 로 바꾸어 계산하세요.", display="4C2"),
                    numeric_step("Step 3. 계산", "6", "방법의 수를 계산하세요."),
                ],
                final=numeric_step("최종 답", "6", "방법의 수를 적으세요."),
                coach_hint="중복조합은 '칸막이' 또는 변환 공식을 이용해 조합으로 바꾸면 됩니다.",
                expected_outline=["기호화", "조합 변환", "계산", "최종 수"],
                final_prompt="예: 6",
            ),
            structured_problem(
                problem_id="curr-pcount-003",
                title="이항계수",
                statement="(x+1)^2를 전개하시오.",
                unit_title="확률과 통계 - 경우의 수",
                course_title="확률과 통계",
                achievement_codes=["12확통01-03"],
                steps=[
                    expr_step("Step 1. 이항정리 구조", "x**2+2*x+1", "기본 전개 구조를 적으세요.", display="x^2+2x+1"),
                    expr_step("Step 2. 중간항 확인", "2*x", "가운데 항의 계수를 확인하세요."),
                    expr_step("Step 3. 전개 정리", "x**2+2*x+1", "최종 전개식을 정리하세요.", display="x^2+2x+1"),
                ],
                final=expr_step("최종 답", "x**2+2*x+1", "전개식을 적으세요.", display="x^2+2x+1"),
                coach_hint="이항정리는 작은 지수부터 계수 패턴을 몸에 붙이는 게 중요합니다.",
                expected_outline=["전개 구조", "중간항", "정리", "최종 답"],
                final_prompt="예: x**2+2*x+1",
            ),
        ],
    },
    {
        "id": "probstat-probability",
        "courseId": "probability-statistics",
        "courseTitle": "확률과 통계",
        "domainTitle": "확률",
        "pdfPages": "129",
        "coreIdea": "확률의 성질, 조건부확률, 독립과 종속을 다루는 단원입니다.",
        "contentElements": ["확률의 개념과 활용", "조건부확률"],
        "achievementCodes": ["12확통02-01", "12확통02-06"],
        "questionStarters": ["조건부확률을 직관적으로 설명해줘", "독립과 종속을 어떻게 판단해?", "덧셈정리와 곱셈정리 차이를 알려줘"],
        "diagnostic": {"prompt": "다음 중 확률과 통계의 확률 단원 핵심 내용은?", "answer": "조건부확률"},
        "problems": [
            structured_problem(
                problem_id="curr-prob-001",
                title="기본확률",
                statement="공정한 주사위를 한 번 던질 때 짝수가 나올 확률을 구하시오.",
                unit_title="확률과 통계 - 확률",
                course_title="확률과 통계",
                achievement_codes=["12확통02-01"],
                steps=[
                    numeric_step("Step 1. 전체 경우", "6", "전체 경우의 수를 적으세요."),
                    numeric_step("Step 2. 유리한 경우", "3", "짝수는 몇 개인지 적으세요."),
                    expr_step("Step 3. 확률식", "3/6", "확률을 유리한 경우/전체 경우로 적으세요.", display="3/6"),
                ],
                final=expr_step("최종 답", "1/2", "기약분수로 확률을 적으세요.", display="1/2"),
                coach_hint="확률은 유리한 경우를 전체 경우로 나누는 기본 정의에서 출발합니다.",
                expected_outline=["전체 경우", "유리한 경우", "확률식", "최종 답"],
                final_prompt="예: 1/2",
            ),
            structured_problem(
                problem_id="curr-prob-002",
                title="조건 사건의 확률",
                statement="주사위를 던졌을 때 4 이하가 나왔다는 조건에서 짝수일 확률을 구하시오.",
                unit_title="확률과 통계 - 확률",
                course_title="확률과 통계",
                achievement_codes=["12확통02-04"],
                steps=[
                    numeric_step("Step 1. 조건 집합 크기", "4", "4 이하가 나오는 경우의 수를 적으세요."),
                    numeric_step("Step 2. 조건 안의 짝수", "2", "그중 짝수인 경우의 수를 적으세요."),
                    expr_step("Step 3. 조건부확률식", "2/4", "조건 안에서 확률을 적으세요.", display="2/4"),
                ],
                final=expr_step("최종 답", "1/2", "조건부확률을 적으세요.", display="1/2"),
                coach_hint="조건이 주어지면 표본공간 자체가 먼저 바뀝니다.",
                expected_outline=["조건 표본공간", "유리한 경우", "확률식", "최종 답"],
                final_prompt="예: 1/2",
            ),
            structured_problem(
                problem_id="curr-prob-003",
                title="독립 판정",
                statement="동전을 두 번 던질 때 첫 번째가 앞면인 사건 A와 두 번째가 앞면인 사건 B는 독립인지 종속인지 적으시오.",
                unit_title="확률과 통계 - 확률",
                course_title="확률과 통계",
                achievement_codes=["12확통02-05"],
                steps=[
                    exact_step("Step 1. A의 확률", "1/2", "첫 번째 앞면 사건의 확률을 적으세요."),
                    exact_step("Step 2. B의 확률", "1/2", "두 번째 앞면 사건의 확률을 적으세요."),
                    exact_step("Step 3. 관계 판정", "독립", "두 시행이 서로 영향을 주는지 판단하세요."),
                ],
                final=exact_step("최종 답", "독립", "독립/종속 중 하나를 적으세요."),
                coach_hint="서로 다른 시행의 정보가 영향을 주지 않으면 독립입니다.",
                expected_outline=["P(A)", "P(B)", "관계 판단", "최종 답"],
                final_prompt="예: 독립",
            ),
        ],
    },
    {
        "id": "probstat-statistics",
        "courseId": "probability-statistics",
        "courseTitle": "확률과 통계",
        "domainTitle": "통계",
        "pdfPages": "130-131",
        "coreIdea": "확률분포, 이항분포, 정규분포, 통계적 추정을 다루는 단원입니다.",
        "contentElements": ["확률분포", "통계적 추정"],
        "achievementCodes": ["12확통03-01", "12확통03-07"],
        "questionStarters": ["기댓값과 분산 차이를 알려줘", "정규분포와 이항분포 관계가 궁금해", "표본평균이 왜 중요한지 설명해줘"],
        "diagnostic": {"prompt": "다음 중 확률과 통계의 통계 단원 핵심 내용은?", "answer": "확률변수와 확률분포"},
        "problems": [
            structured_problem(
                problem_id="curr-stat-001",
                title="확률변수의 기댓값",
                statement="확률변수 X가 1,2,3의 값을 각각 1/3의 확률로 가질 때 E(X)를 구하시오.",
                unit_title="확률과 통계 - 통계",
                course_title="확률과 통계",
                achievement_codes=["12확통03-01", "12확통03-02"],
                steps=[
                    expr_step("Step 1. 기댓값 식", "1*(1/3)+2*(1/3)+3*(1/3)", "가치×확률의 합으로 식을 세우세요.", display="1·1/3 + 2·1/3 + 3·1/3"),
                    numeric_step("Step 2. 합 계산", "2", "기댓값을 계산하세요."),
                    exact_step("Step 3. 해석", "E(X)=2", "기댓값을 기호와 함께 적으세요."),
                ],
                final=numeric_step("최종 답", "2", "기댓값을 적으세요."),
                coach_hint="기댓값은 값과 확률의 가중평균입니다.",
                expected_outline=["기댓값 식", "계산", "해석", "최종 답"],
                final_prompt="예: 2",
            ),
            structured_problem(
                problem_id="curr-stat-002",
                title="이항분포 평균",
                statement="X~B(4, 1/2)일 때 평균을 구하시오.",
                unit_title="확률과 통계 - 통계",
                course_title="확률과 통계",
                achievement_codes=["12확통03-03"],
                steps=[
                    expr_step("Step 1. 평균 공식", "4*(1/2)", "이항분포의 평균 np를 적용하세요.", display="4×1/2"),
                    numeric_step("Step 2. 계산", "2", "평균을 계산하세요."),
                    exact_step("Step 3. 정리", "평균=2", "결과를 정리하세요."),
                ],
                final=numeric_step("최종 답", "2", "평균을 적으세요."),
                coach_hint="이항분포 평균은 np, 분산은 np(1-p)로 묶어 기억하세요.",
                expected_outline=["공식", "계산", "정리", "최종 답"],
                final_prompt="예: 2",
            ),
            structured_problem(
                problem_id="curr-stat-003",
                title="표본비율",
                statement="20명 중 8명이 찬성했을 때 표본비율을 구하시오.",
                unit_title="확률과 통계 - 통계",
                course_title="확률과 통계",
                achievement_codes=["12확통03-06", "12확통03-07"],
                steps=[
                    expr_step("Step 1. 비율식", "8/20", "표본비율을 찬성 수/전체 수로 적으세요.", display="8/20"),
                    expr_step("Step 2. 기약분수", "2/5", "분수를 기약형으로 정리하세요.", display="2/5"),
                    exact_step("Step 3. 소수 해석", "0.4", "표본비율을 소수로도 해석하세요."),
                ],
                final=expr_step("최종 답", "2/5", "표본비율을 적으세요.", display="2/5"),
                coach_hint="표본비율은 조사된 표본에서의 비율입니다.",
                expected_outline=["비율식", "정리", "해석", "최종 답"],
                final_prompt="예: 2/5",
            ),
        ],
    },
    {
        "id": "calc2-seq-limit",
        "courseId": "calculus-2",
        "courseTitle": "미적분Ⅱ",
        "domainTitle": "수열의 극한",
        "pdfPages": "143-144",
        "coreIdea": "수열의 수렴과 발산, 급수, 등비급수를 다루는 단원입니다.",
        "contentElements": ["수열의 극한", "급수"],
        "achievementCodes": ["12미적Ⅱ-01-01", "12미적Ⅱ-01-05"],
        "questionStarters": ["수열 수렴 판정이 헷갈려", "급수와 부분합 관계를 설명해줘", "등비급수 합 공식을 다시 보고 싶어"],
        "diagnostic": {"prompt": "다음 중 미적분Ⅱ의 수열의 극한 단원 핵심 내용은?", "answer": "급수와 등비급수"},
        "problems": [
            structured_problem(
                problem_id="curr-c2seq-001",
                title="수열의 극한",
                statement="수열 a_n = 1/n 의 극한값을 구하시오.",
                unit_title="미적분Ⅱ - 수열의 극한",
                course_title="미적분Ⅱ",
                achievement_codes=["12미적Ⅱ-01-01", "12미적Ⅱ-01-02"],
                steps=[
                    exact_step("Step 1. 큰 n에서 형태", "1/n", "수열의 일반항을 확인하세요."),
                    exact_step("Step 2. 극한 직관", "0", "분모가 커질수록 값이 어디로 가는지 보세요."),
                    exact_step("Step 3. 수렴 판정", "수렴", "극한값이 존재하는지 판정하세요."),
                ],
                final=numeric_step("최종 답", "0", "극한값을 적으세요."),
                coach_hint="분모만 커지는 기본형은 0으로 가는 수열인지 먼저 점검합니다.",
                expected_outline=["일반항", "극한 직관", "판정", "최종 답"],
                final_prompt="예: 0",
            ),
            structured_problem(
                problem_id="curr-c2seq-002",
                title="등비수열 극한",
                statement="등비수열 1, 1/2, 1/4, ... 의 극한값을 구하시오.",
                unit_title="미적분Ⅱ - 수열의 극한",
                course_title="미적분Ⅱ",
                achievement_codes=["12미적Ⅱ-01-03"],
                steps=[
                    numeric_step("Step 1. 공비", "1/2", "등비수열의 공비를 적으세요."),
                    exact_step("Step 2. 수렴 조건", "|r|<1", "등비수열 수렴 조건을 적으세요."),
                    numeric_step("Step 3. 극한값", "0", "공비의 절댓값이 1보다 작을 때 극한값을 적으세요."),
                ],
                final=numeric_step("최종 답", "0", "극한값을 적으세요."),
                coach_hint="등비수열은 공비 하나로 수렴/발산이 거의 결정됩니다.",
                expected_outline=["공비", "조건", "극한값", "최종 답"],
                final_prompt="예: 0",
            ),
            structured_problem(
                problem_id="curr-c2seq-003",
                title="등비급수의 합",
                statement="1 + 1/2 + 1/4 + ... 의 합을 구하시오.",
                unit_title="미적분Ⅱ - 수열의 극한",
                course_title="미적분Ⅱ",
                achievement_codes=["12미적Ⅱ-01-05"],
                steps=[
                    numeric_step("Step 1. 첫째항", "1", "첫째항 a를 적으세요."),
                    numeric_step("Step 2. 공비", "1/2", "공비 r을 적으세요."),
                    expr_step("Step 3. 합 공식", "1/(1-1/2)", "무한등비급수의 합 공식을 적용하세요.", display="1/(1-1/2)"),
                ],
                final=numeric_step("최종 답", "2", "등비급수의 합을 적으세요."),
                coach_hint="무한등비급수는 첫째항과 공비 두 개로 합이 결정됩니다.",
                expected_outline=["첫째항", "공비", "공식", "최종 답"],
                final_prompt="예: 2",
            ),
        ],
    },
    {
        "id": "calc2-diff",
        "courseId": "calculus-2",
        "courseTitle": "미적분Ⅱ",
        "domainTitle": "미분법",
        "pdfPages": "145",
        "coreIdea": "지수, 로그, 삼각함수, 합성함수 등 다양한 함수의 미분과 그래프 개형을 다루는 단원입니다.",
        "contentElements": ["여러 가지 함수의 미분", "여러 가지 미분법", "도함수의 활용"],
        "achievementCodes": ["12미적Ⅱ-02-01", "12미적Ⅱ-02-11"],
        "questionStarters": ["합성함수 미분을 다시 설명해줘", "이계도함수와 변곡점 연결이 궁금해", "지수함수 미분 흐름을 보여줘"],
        "diagnostic": {"prompt": "다음 중 미적분Ⅱ의 미분법 단원 핵심 내용은?", "answer": "합성함수와 여러 가지 미분법"},
        "problems": [
            structured_problem(
                problem_id="curr-c2diff-001",
                title="지수함수 미분",
                statement="f(x)=e^x의 도함수를 구하시오.",
                unit_title="미적분Ⅱ - 미분법",
                course_title="미적분Ⅱ",
                achievement_codes=["12미적Ⅱ-02-01"],
                steps=[
                    exact_step("Step 1. 기본 도함수", "e^x", "e^x의 기본 도함수를 떠올리세요."),
                    exact_step("Step 2. 확인", "미분해도같다", "지수함수 e^x의 특징을 확인하세요."),
                    exact_step("Step 3. 정리", "e^x", "도함수를 정리하세요."),
                ],
                final=exact_step("최종 답", "e^x", "도함수를 적으세요."),
                coach_hint="e^x는 미분해도 자기 자신이 되는 대표 함수입니다.",
                expected_outline=["기본 도함수", "특징 확인", "정리", "최종 답"],
                final_prompt="예: e^x",
            ),
            structured_problem(
                problem_id="curr-c2diff-002",
                title="합성함수 미분",
                statement="f(x)=(x^2+1)^3의 도함수를 구하시오.",
                unit_title="미적분Ⅱ - 미분법",
                course_title="미적분Ⅱ",
                achievement_codes=["12미적Ⅱ-02-05"],
                steps=[
                    expr_step("Step 1. 바깥 미분", "3*(x**2+1)**2", "바깥 함수 u^3의 미분을 적으세요.", display="3(x^2+1)^2"),
                    expr_step("Step 2. 안쪽 미분", "2*x", "안쪽 함수 x^2+1의 미분을 적으세요."),
                    expr_step("Step 3. 곱하기", "6*x*(x**2+1)**2", "연쇄법칙으로 두 결과를 곱하세요.", display="6x(x^2+1)^2"),
                ],
                final=expr_step("최종 답", "6*x*(x**2+1)**2", "도함수를 적으세요.", display="6x(x^2+1)^2"),
                coach_hint="합성함수는 바깥 미분 × 안쪽 미분 순서로 끝냅니다.",
                expected_outline=["바깥 미분", "안쪽 미분", "연쇄법칙", "최종 답"],
                final_prompt="예: 6*x*(x**2+1)^2",
                problem_type="합성함수 연쇄형",
            ),
            structured_problem(
                problem_id="curr-c2diff-003",
                title="함수값과 오목볼록",
                statement="f''(x)=6x, x=1에서 그래프가 위로 볼록인지 아래로 볼록인지 적으시오.",
                unit_title="미적분Ⅱ - 미분법",
                course_title="미적분Ⅱ",
                achievement_codes=["12미적Ⅱ-02-09"],
                steps=[
                    expr_step("Step 1. 이계도함수 대입", "6*1", "x=1을 이계도함수에 대입하세요."),
                    numeric_step("Step 2. 부호 확인", "6", "이계도함수값의 부호를 계산하세요."),
                    exact_step("Step 3. 오목볼록 해석", "위로볼록", "f''(1)>0인지 해석하세요."),
                ],
                final=exact_step("최종 답", "위로볼록", "판정 결과를 적으세요."),
                coach_hint="이계도함수의 부호는 오목/볼록 판정으로 바로 이어집니다.",
                expected_outline=["대입", "부호", "해석", "최종 판단"],
                final_prompt="예: 위로볼록",
                problem_type="이계도함수 판정형",
            ),
            structured_problem(
                problem_id="curr-c2diff-030",
                title="지수함수 최대값 킬러 문제",
                statement="함수 f(x)=x^2*e^(-x)가 x>0에서 가질 수 있는 최댓값을 구하시오.",
                unit_title="미적분Ⅱ - 미분법",
                course_title="미적분Ⅱ",
                achievement_codes=["12미적Ⅱ-02-05", "12미적Ⅱ-02-11"],
                steps=[
                    expr_step("Step 1. 도함수 정리", "x*(2-x)*exp(-x)", "곱의 미분법으로 도함수를 정리하세요.", display="x(2-x)e^{-x}"),
                    exact_step("Step 2. 극값 후보", "x=2", "x>0에서 내부 임계점을 찾으세요."),
                    exact_step("Step 3. 함수값 계산", "4/e^2", "x=2에서의 함수값을 계산하세요."),
                ],
                final=exact_step("최종 답", "4/e^2", "최댓값을 적으세요."),
                coach_hint="킬러 문제는 복잡한 함수도 도함수의 구조를 인수분해해 최대가 나는 지점을 먼저 찾아야 합니다.",
                expected_outline=["곱의 미분", "임계점 판정", "최댓값 계산", "최종 답"],
                final_prompt="예: 4/e^2",
                difficulty="killer",
                problem_type="킬러 문제 · 지수함수 최대값",
                is_killer=True,
            ),
        ],
    },
    {
        "id": "calc2-integral",
        "courseId": "calculus-2",
        "courseTitle": "미적분Ⅱ",
        "domainTitle": "적분법",
        "pdfPages": "146",
        "coreIdea": "치환적분, 부분적분, 넓이와 부피 등 다양한 적분법을 다루는 단원입니다.",
        "contentElements": ["여러 가지 함수의 적분법", "정적분의 활용"],
        "achievementCodes": ["12미적Ⅱ-03-01", "12미적Ⅱ-03-07"],
        "questionStarters": ["치환적분과 부분적분 차이를 알려줘", "부피 적분 세우는 법이 궁금해", "정적분과 급수의 합 연결이 어려워"],
        "diagnostic": {"prompt": "다음 중 미적분Ⅱ의 적분법 단원 핵심 내용은?", "answer": "치환적분법과 부분적분법"},
        "problems": [
            structured_problem(
                problem_id="curr-c2int-001",
                title="지수함수 적분",
                statement="∫e^x dx를 구하시오.",
                unit_title="미적분Ⅱ - 적분법",
                course_title="미적분Ⅱ",
                achievement_codes=["12미적Ⅱ-03-01"],
                steps=[
                    exact_step("Step 1. 기본 적분형", "e^x", "e^x의 부정적분 기본형을 적으세요."),
                    exact_step("Step 2. 확인", "미분해도같다", "미분과의 역관계를 확인하세요."),
                    exact_step("Step 3. 정리", "e^x", "부정적분 결과를 정리하세요."),
                ],
                final=exact_step("최종 답", "e^x", "부정적분 결과를 적으세요."),
                coach_hint="e^x는 적분해도 자기 자신이라는 점이 핵심입니다.",
                expected_outline=["기본 적분형", "역관계 확인", "정리", "최종 답"],
                final_prompt="예: e^x + C",
            ),
            structured_problem(
                problem_id="curr-c2int-002",
                title="치환적분 기본형",
                statement="∫2x(x^2+1)^3 dx를 구하시오.",
                unit_title="미적분Ⅱ - 적분법",
                course_title="미적분Ⅱ",
                achievement_codes=["12미적Ⅱ-03-02"],
                steps=[
                    exact_step("Step 1. 치환", "u=x^2+1", "안쪽 함수를 u로 두세요."),
                    exact_step("Step 2. du 연결", "du=2x dx", "미분으로 du를 연결하세요."),
                    expr_step("Step 3. 적분 결과", "(x**2+1)**4/4", "u^3 적분 결과를 원래 변수로 되돌리세요.", display="(x^2+1)^4/4"),
                ],
                final=expr_step("최종 답", "(x**2+1)**4/4", "치환적분 결과를 적으세요.", display="(x^2+1)^4/4"),
                coach_hint="안쪽 미분이 보이면 치환적분부터 의심하는 습관이 좋습니다.",
                expected_outline=["치환", "du 연결", "적분 후 복원", "최종 답"],
                final_prompt="예: (x**2+1)^4/4 + C",
            ),
            structured_problem(
                problem_id="curr-c2int-003",
                title="부피 계산",
                statement="반지름이 2인 구의 부피를 구하시오.",
                unit_title="미적분Ⅱ - 적분법",
                course_title="미적분Ⅱ",
                achievement_codes=["12미적Ⅱ-03-06"],
                steps=[
                    exact_step("Step 1. 공식 선택", "4/3*pi*r^3", "구의 부피 공식을 적으세요."),
                    expr_step("Step 2. 반지름 대입", "(4/3)*pi*(2**3)", "r=2를 대입하세요.", display="4/3·π·2^3"),
                    exact_step("Step 3. 정리", "32/3*pi", "부피를 정리하세요."),
                ],
                final=exact_step("최종 답", "32/3*pi", "구의 부피를 적으세요."),
                coach_hint="회전체와 입체도형은 이미 알고 있는 공식을 먼저 떠올리는 것도 좋은 전략입니다.",
                expected_outline=["공식", "대입", "정리", "최종 답"],
                final_prompt="예: 32/3*pi",
            ),
        ],
    },
    {
        "id": "geometry-conic",
        "courseId": "geometry",
        "courseTitle": "기하",
        "domainTitle": "이차곡선",
        "pdfPages": "157-158",
        "coreIdea": "포물선, 타원, 쌍곡선을 방정식으로 표현하고 접선의 방정식을 다루는 단원입니다.",
        "contentElements": ["이차곡선"],
        "achievementCodes": ["12기하01-01", "12기하01-04"],
        "questionStarters": ["포물선과 타원 방정식 차이를 알려줘", "이차곡선 접선의 방정식이 궁금해", "기하 단원에서 꼭 기억할 표준형을 정리해줘"],
        "diagnostic": {"prompt": "다음 중 기하의 이차곡선 단원 핵심 내용은?", "answer": "포물선, 타원, 쌍곡선"},
        "problems": [
            structured_problem(
                problem_id="curr-conic-001",
                title="포물선 표준형",
                statement="꼭짓점이 원점이고 초점이 (1,0)인 포물선의 방정식을 구하시오.",
                unit_title="기하 - 이차곡선",
                course_title="기하",
                achievement_codes=["12기하01-01"],
                steps=[
                    exact_step("Step 1. p 값", "1", "초점 좌표로부터 p를 읽으세요."),
                    exact_step("Step 2. 표준형", "y^2=4px", "포물선의 표준형을 적으세요."),
                    exact_step("Step 3. 대입", "y^2=4x", "p=1을 대입해 방정식을 완성하세요."),
                ],
                final=exact_step("최종 답", "y^2=4x", "포물선의 방정식을 적으세요."),
                coach_hint="포물선은 꼭짓점과 초점의 상대 위치로 표준형이 즉시 정해집니다.",
                expected_outline=["p 값", "표준형", "대입", "최종 답"],
                final_prompt="예: y^2=4x",
            ),
            structured_problem(
                problem_id="curr-conic-002",
                title="타원 방정식",
                statement="중심이 원점이고 장축이 x축, a=3, b=2인 타원의 방정식을 구하시오.",
                unit_title="기하 - 이차곡선",
                course_title="기하",
                achievement_codes=["12기하01-02"],
                steps=[
                    exact_step("Step 1. 표준형", "x^2/a^2+y^2/b^2=1", "장축이 x축인 타원 표준형을 적으세요."),
                    exact_step("Step 2. 값 대입", "x^2/9+y^2/4=1", "a=3, b=2를 대입하세요."),
                    exact_step("Step 3. 방정식 정리", "x^2/9+y^2/4=1", "타원의 방정식을 정리하세요."),
                ],
                final=exact_step("최종 답", "x^2/9+y^2/4=1", "타원의 방정식을 적으세요."),
                coach_hint="타원은 장축 방향을 먼저 정한 뒤 a,b를 자리에 넣으면 됩니다.",
                expected_outline=["표준형", "대입", "정리", "최종 답"],
                final_prompt="예: x^2/9+y^2/4=1",
            ),
            structured_problem(
                problem_id="curr-conic-003",
                title="쌍곡선 방정식",
                statement="중심이 원점이고 실축이 x축, a=2, b=3인 쌍곡선의 방정식을 구하시오.",
                unit_title="기하 - 이차곡선",
                course_title="기하",
                achievement_codes=["12기하01-03"],
                steps=[
                    exact_step("Step 1. 표준형", "x^2/a^2-y^2/b^2=1", "실축이 x축인 쌍곡선 표준형을 적으세요."),
                    exact_step("Step 2. 값 대입", "x^2/4-y^2/9=1", "a=2, b=3을 대입하세요."),
                    exact_step("Step 3. 방정식 정리", "x^2/4-y^2/9=1", "쌍곡선의 방정식을 정리하세요."),
                ],
                final=exact_step("최종 답", "x^2/4-y^2/9=1", "쌍곡선의 방정식을 적으세요."),
                coach_hint="쌍곡선은 빼는 위치가 축 방향을 결정합니다.",
                expected_outline=["표준형", "대입", "정리", "최종 답"],
                final_prompt="예: x^2/4-y^2/9=1",
            ),
        ],
    },
    {
        "id": "geometry-space",
        "courseId": "geometry",
        "courseTitle": "기하",
        "domainTitle": "공간도형과 공간좌표",
        "pdfPages": "159",
        "coreIdea": "공간에서 거리, 내분점, 구의 방정식을 다루는 단원입니다.",
        "contentElements": ["공간도형", "공간좌표"],
        "achievementCodes": ["12기하02-01", "12기하02-05"],
        "questionStarters": ["공간좌표 공식을 평면과 연결해줘", "구의 방정식을 세우는 법이 궁금해", "정사영과 삼수선 정리 흐름을 설명해줘"],
        "diagnostic": {"prompt": "다음 중 기하의 공간도형과 공간좌표 단원 핵심 내용은?", "answer": "구의 방정식"},
        "problems": [
            structured_problem(
                problem_id="curr-space-001",
                title="두 점 사이 거리",
                statement="좌표공간의 두 점 A(1,2,3), B(4,6,3) 사이의 거리를 구하시오.",
                unit_title="기하 - 공간도형과 공간좌표",
                course_title="기하",
                achievement_codes=["12기하02-04"],
                steps=[
                    expr_step("Step 1. 차이 벡터", "(4-1)**2+(6-2)**2+(3-3)**2", "좌표 차의 제곱합을 적으세요.", display="(4-1)^2+(6-2)^2+(3-3)^2"),
                    numeric_step("Step 2. 제곱합", "25", "제곱합을 계산하세요."),
                    exact_step("Step 3. 거리", "5", "제곱근을 취해 거리를 구하세요."),
                ],
                final=numeric_step("최종 답", "5", "거리를 적으세요."),
                coach_hint="공간 거리 공식도 평면 거리 공식을 한 차원 확장한 형태입니다.",
                expected_outline=["제곱합", "계산", "거리", "최종 답"],
                final_prompt="예: 5",
            ),
            structured_problem(
                problem_id="curr-space-002",
                title="공간 내분점",
                statement="A(0,0,0), B(2,4,6)을 1:1로 내분하는 점의 좌표를 구하시오.",
                unit_title="기하 - 공간도형과 공간좌표",
                course_title="기하",
                achievement_codes=["12기하02-04"],
                steps=[
                    numeric_step("Step 1. x좌표", "1", "x좌표를 평균으로 계산하세요."),
                    numeric_step("Step 2. y좌표", "2", "y좌표를 평균으로 계산하세요."),
                    exact_step("Step 3. 좌표 완성", "(1,2,3)", "z좌표까지 포함해 좌표를 적으세요."),
                ],
                final=exact_step("최종 답", "(1,2,3)", "내분점 좌표를 적으세요."),
                coach_hint="1:1 내분은 중점이므로 좌표 평균으로 바로 계산할 수 있습니다.",
                expected_outline=["x좌표", "y좌표", "좌표 완성", "최종 답"],
                final_prompt="예: (1,2,3)",
            ),
            structured_problem(
                problem_id="curr-space-003",
                title="구의 방정식",
                statement="중심이 (1,-2,3)이고 반지름이 2인 구의 방정식을 구하시오.",
                unit_title="기하 - 공간도형과 공간좌표",
                course_title="기하",
                achievement_codes=["12기하02-05"],
                steps=[
                    exact_step("Step 1. 기본형", "(x-1)^2+(y+2)^2+(z-3)^2=r^2", "구의 기본형을 적으세요."),
                    exact_step("Step 2. 반지름 대입", "(x-1)^2+(y+2)^2+(z-3)^2=4", "r=2를 대입하세요."),
                    exact_step("Step 3. 방정식 정리", "(x-1)^2+(y+2)^2+(z-3)^2=4", "구의 방정식을 정리하세요."),
                ],
                final=exact_step("최종 답", "(x-1)^2+(y+2)^2+(z-3)^2=4", "구의 방정식을 적으세요."),
                coach_hint="구의 방정식은 원의 방정식을 z축까지 확장한 형태입니다.",
                expected_outline=["기본형", "대입", "정리", "최종 답"],
                final_prompt="예: (x-1)^2+(y+2)^2+(z-3)^2=4",
            ),
        ],
    },
    {
        "id": "geometry-vector",
        "courseId": "geometry",
        "courseTitle": "기하",
        "domainTitle": "벡터",
        "pdfPages": "157-160",
        "coreIdea": "벡터의 연산, 내적, 도형의 방정식을 다루는 단원입니다.",
        "contentElements": ["벡터의 연산", "벡터의 성분과 내적", "도형의 방정식"],
        "achievementCodes": ["12기하03-01", "12기하03-05"],
        "questionStarters": ["벡터 내적 의미를 알려줘", "위치벡터와 좌표를 연결해줘", "직선의 벡터방정식을 보고 싶어"],
        "diagnostic": {"prompt": "다음 중 기하의 벡터 단원 핵심 내용은?", "answer": "벡터의 내적"},
        "problems": [
            structured_problem(
                problem_id="curr-vector-001",
                title="벡터 덧셈",
                statement="벡터 a=(1,2), b=(3,4)일 때 a+b를 구하시오.",
                unit_title="기하 - 벡터",
                course_title="기하",
                achievement_codes=["12기하03-01"],
                steps=[
                    numeric_step("Step 1. x성분", "4", "x성분끼리 더하세요."),
                    numeric_step("Step 2. y성분", "6", "y성분끼리 더하세요."),
                    exact_step("Step 3. 벡터 완성", "(4,6)", "결과 벡터를 적으세요."),
                ],
                final=exact_step("최종 답", "(4,6)", "벡터의 합을 적으세요."),
                coach_hint="벡터 연산은 성분별 연산으로 처리합니다.",
                expected_outline=["x성분", "y성분", "벡터 완성", "최종 답"],
                final_prompt="예: (4,6)",
            ),
            structured_problem(
                problem_id="curr-vector-002",
                title="벡터 내적",
                statement="a=(1,2), b=(3,4)일 때 a·b를 구하시오.",
                unit_title="기하 - 벡터",
                course_title="기하",
                achievement_codes=["12기하03-03"],
                steps=[
                    expr_step("Step 1. 내적식", "1*3+2*4", "성분 곱의 합으로 내적식을 세우세요.", display="1·3+2·4"),
                    numeric_step("Step 2. 계산", "11", "내적값을 계산하세요."),
                    exact_step("Step 3. 정리", "11", "내적 결과를 적으세요."),
                ],
                final=numeric_step("최종 답", "11", "내적값을 적으세요."),
                coach_hint="내적은 대응 성분을 곱해서 더하는 구조입니다.",
                expected_outline=["내적식", "계산", "정리", "최종 답"],
                final_prompt="예: 11",
            ),
            structured_problem(
                problem_id="curr-vector-003",
                title="직선의 방정식",
                statement="점 (1,2)를 지나고 방향벡터가 (2,1)인 직선의 점벡터식 한 가지를 쓰시오.",
                unit_title="기하 - 벡터",
                course_title="기하",
                achievement_codes=["12기하03-04"],
                steps=[
                    exact_step("Step 1. 기준점", "(1,2)", "기준점 위치벡터를 적으세요."),
                    exact_step("Step 2. 방향벡터", "(2,1)", "방향벡터를 적으세요."),
                    exact_step("Step 3. 점벡터식", "(x,y)=(1,2)+t(2,1)", "점벡터식을 완성하세요."),
                ],
                final=exact_step("최종 답", "(x,y)=(1,2)+t(2,1)", "직선의 점벡터식을 적으세요."),
                coach_hint="직선의 벡터방정식은 기준점 + t×방향벡터입니다.",
                expected_outline=["기준점", "방향벡터", "점벡터식", "최종 답"],
                final_prompt="예: (x,y)=(1,2)+t(2,1)",
            ),
        ],
    },
]


def _unit_concept(unit: dict, index: int) -> dict:
    return {
        "id": unit["id"],
        "title": f"{unit['courseTitle']} - {unit['domainTitle']}",
        "lessonPackId": f"lesson-{unit['id']}",
        "problemSetId": f"set-{unit['id']}",
        "baselineScore": 58 + (index % 5) * 4,
        "baselineTrend": f"+{index % 4}",
        "baselineRisk": "높음" if index % 3 == 0 else "중간",
        "courseId": unit["courseId"],
        "courseTitle": unit["courseTitle"],
        "pdfPages": unit["pdfPages"],
        "achievementCodes": unit["achievementCodes"],
    }


def _lesson_agenda(unit: dict) -> list[str]:
    agenda = list(unit["contentElements"][:3])
    if len(agenda) < 3:
        agenda.extend(["대표 예제", "실수 교정"][: 3 - len(agenda)])
    return agenda[:3]


def _lesson_pitfalls(unit: dict) -> list[str]:
    first = unit["contentElements"][0] if unit["contentElements"] else unit["domainTitle"]
    last = unit["contentElements"][-1] if unit["contentElements"] else unit["domainTitle"]
    return [
        f"{first}에서 정의를 건너뛰고 계산부터 시작하지 않기",
        f"{last} 문제는 마지막 한 줄에서 부호와 조건을 다시 확인하기",
        "풀이를 길게 쓰기보다 기준 식과 판정 근거를 먼저 고정하기",
    ]


def _problem_step_rows(problem: dict) -> list[list[str]]:
    structured_steps = problem.get("gradingSpec", {}).get("steps", [])
    if structured_steps:
        rows: list[list[str]] = []
        for step in structured_steps[:3]:
            label = str(step.get("label", "핵심 단계"))
            short_label = label.split(". ", 1)[-1] if ". " in label else label
            rows.append(
                [
                    short_label,
                    str(step.get("expectedDisplay") or ", ".join(step.get("expected", [])) or "핵심 식"),
                    str(step.get("hint") or "조건과 기준 식을 먼저 고정하세요."),
                ]
            )
        return rows

    outline = list(problem.get("expectedOutline", [])[:3])
    return [
        [item, item, "문제를 읽자마자 이 순서를 먼저 떠올리세요."]
        for item in outline
    ] or [
        ["기준 식", "기준 식", "문제에서 제일 먼저 세울 식을 찾으세요."],
        ["판정 근거", "판정 근거", "왜 그 식을 쓰는지 조건을 확인하세요."],
        ["최종 정리", "최종 정리", "마지막 한 줄의 형식을 점검하세요."],
    ]


def _problem_focus_checks(problem: dict) -> list[str]:
    checks = [
        "문제를 보자마자 기준 식을 먼저 적을 수 있는가",
        "중간 계산 전에 조건과 판정 근거를 말로 설명할 수 있는가",
        "마지막 한 줄을 답 형식까지 맞춰 정리했는가",
    ]
    if problem.get("evaluationType") == "tangent-line":
        return [
            "도함수 → 기울기 → 접점 → 직선식 순서를 유지했는가",
            "접점 좌표와 기울기를 헷갈리지 않았는가",
            "최종 답을 y=mx+n 형태까지 정리했는가",
        ]
    return checks


def _problem_difficulty_badge(problem: dict) -> str:
    if str(problem.get("difficulty") or "").lower() == "apex":
        return "APEX"
    if problem.get("isKiller"):
        return "KILLER"
    difficulty = str(problem.get("difficulty") or "core").lower()
    if difficulty == "advanced":
        return "ADVANCED"
    return "CORE TYPE"


def _soften_teacher_text(text: str) -> str:
    softened = text
    replacements = [
        ("정리합니다.", "정리해볼게요."),
        ("정리합니다", "정리해볼게요"),
        ("이해합니다.", "이해해볼게요."),
        ("이해합니다", "이해해볼게요"),
        ("읽습니다.", "읽어볼게요."),
        ("읽습니다", "읽어볼게요"),
        ("봅니다.", "볼게요."),
        ("봅니다", "볼게요"),
        ("잡습니다.", "잡아볼게요."),
        ("잡습니다", "잡아볼게요"),
        ("교정합니다.", "바로잡아볼게요."),
        ("교정합니다", "바로잡아볼게요"),
        ("연결합니다.", "연결해볼게요."),
        ("연결합니다", "연결해볼게요"),
        ("익힙니다.", "익혀볼게요."),
        ("익힙니다", "익혀볼게요"),
        ("훈련합니다.", "연습해볼게요."),
        ("훈련합니다", "연습해볼게요"),
        ("분리합니다.", "나눠서 볼게요."),
        ("분리합니다", "나눠서 볼게요"),
        ("완성합니다.", "완성해볼게요."),
        ("완성합니다", "완성해볼게요"),
        ("확인합니다.", "확인해볼게요."),
        ("확인합니다", "확인해볼게요"),
        ("비교합니다.", "비교해볼게요."),
        ("비교합니다", "비교해볼게요"),
        ("고정합니다.", "먼저 잡아볼게요."),
        ("고정합니다", "먼저 잡아볼게요"),
        ("설명합니다.", "설명해볼게요."),
        ("설명합니다", "설명해볼게요"),
    ]
    for before, after in replacements:
        softened = softened.replace(before, after)
    softened = softened.replace("먼저 먼저", "먼저")
    return softened


def _soften_scene(scene: dict) -> dict:
    softened = deepcopy(scene)
    for field in ["narration", "teachingGoal", "takeaway", "examCue", "practiceBridge"]:
        value = softened.get(field)
        if isinstance(value, str):
            softened[field] = _soften_teacher_text(value)
    for obj in softened.get("objects", []):
        if obj.get("type") in {"callout", "badge"} and isinstance(obj.get("content"), str):
            obj["content"] = _soften_teacher_text(obj["content"])
        if obj.get("type") == "checklist":
            if isinstance(obj.get("label"), str):
                obj["label"] = _soften_teacher_text(obj["label"])
            if isinstance(obj.get("items"), list):
                obj["items"] = [
                    _soften_teacher_text(item) if isinstance(item, str) else item
                    for item in obj["items"]
                ]
    return softened


def _outline_preview(problem: dict, limit: int = 4) -> list[str]:
    outline = [str(item) for item in list(problem.get("expectedOutline", [])[:limit]) if item]
    if outline:
        return outline
    structured_steps = problem.get("gradingSpec", {}).get("steps", [])
    derived = []
    for step in structured_steps[:limit]:
        label = str(step.get("label") or "핵심 단계")
        derived.append(label.split(". ", 1)[-1] if ". " in label else label)
    return derived or ["기준 식", "판정", "정리"]


def _lecture_explanation_rows(element: str, kit: dict, anchor_problem: dict) -> list[list[str]]:
    outline = _outline_preview(anchor_problem, 3)
    return [
        ["왜 이 개념을 먼저 보나", kit["teacher_line"], kit["why_it_matters"]],
        ["첫 줄에서 적는 것", kit["first_line"], "첫 줄이 잡히면 긴 문제도 같은 기준으로 읽을 수 있습니다"],
        ["대표 문제에서 쓰는 흐름", " → ".join(outline), f"{anchor_problem['title']} 같은 문제에서 바로 쓰는 실제 순서입니다"],
    ]


def _board_reason_rows(kit: dict) -> list[list[str]]:
    return [
        [kit["board_lines"][0], "조건을 읽는 순간 빈칸 없이 첫 줄을 만들기 위해서입니다"],
        [kit["board_lines"][1], "중간 전환이 어디서 생기는지 눈으로 보이게 하려는 줄입니다"],
        [kit["board_lines"][2], "계산을 다 끝낸 뒤가 아니라, 끝내는 방식까지 미리 고정하기 위해서입니다"],
    ]


def _killer_skill_rows(kit: dict, anchor_problem: dict, challenge_problem: dict) -> list[list[str]]:
    outline = _outline_preview(anchor_problem, 3)
    challenge_outline = _outline_preview(challenge_problem, 3)
    advanced_moves = list(kit.get("advanced_moves", []))
    while len(advanced_moves) < 3:
        advanced_moves.append("조건을 다시 읽고 이미 나온 식을 다른 방식으로 연결하기")
    return [
        ["첫 줄 고정", outline[0], "문장이 길어져도 첫 줄은 바뀌지 않는 경우가 많습니다"],
        ["중간 전환 복원", advanced_moves[0], f"{challenge_problem['title']} 같은 심화 문제에서 구조를 바꾸는 지점입니다"],
        ["검산 포인트 확보", challenge_outline[-1], "고난도일수록 마지막 줄을 미리 의식해야 버려지는 해와 형식 실수를 줄입니다"],
    ]


def _application_bridge_rows(kit: dict, anchor_problem: dict, challenge_problem: dict) -> list[list[str]]:
    return [
        ["기본형", anchor_problem["title"], "대표 예제처럼 기준 식과 조건을 곧바로 묶습니다"],
        ["응용형", challenge_problem["title"], "조건 하나가 더 붙어도 첫 줄은 그대로 유지합니다"],
        ["고난도형", kit["advanced_moves"][-1], "새 공식을 찾기보다 이미 만든 식을 되돌려 읽습니다"],
    ]


def _element_lecture_kit(element: str, unit: dict, problem: dict) -> dict:
    unit_title = f"{unit['courseTitle']} · {unit['domainTitle']}"
    kit = {
        "teacher_line": f"{element}은(는) 문제를 읽고 첫 줄을 정하는 감각을 키우는 요소입니다.",
        "first_line": f"{element}의 기준 식과 조건을 먼저 적는다.",
        "why_it_matters": f"{unit_title} 문제에서 {element}는 풀이의 출발점이 됩니다.",
        "checks": ["정의와 조건", "기준 식", "마지막 답 형식"],
        "board_lines": [
            f"{element} 핵심 문장부터 적기",
            "조건을 식으로 번역하기",
            "최종 답 형식까지 끝내기",
        ],
        "intuition_rows": [
            ["처음 볼 때", f"{element}가 어디에 쓰이는지 찾기", "정의와 조건을 먼저 본다"],
            ["풀이 시작", "기준 식 한 줄 쓰기", "첫 줄을 늦추지 않는다"],
            ["마무리", "답 형식과 범위 확인", "부호와 조건을 다시 본다"],
        ],
        "misconceptions": [
            [f"{element}은 공식을 외우는 단원이다", "문제 조건과 연결될 때 점수가 난다", "문제에서 조건을 먼저 표시한다"],
            ["계산부터 빨리 시작해야 한다", "첫 줄을 먼저 고정하는 편이 더 안정적이다", "기준 식부터 적는다"],
            ["마지막 답은 대충 적어도 된다", "답 형식이 점수를 결정하는 경우가 많다", "한 줄 정리를 끝까지 한다"],
        ],
        "advanced_moves": [
            "기본 문제와 심화 문제의 첫 줄이 어떻게 같은지 비교하기",
            "중간 전환이 생기는 지점을 따로 표시하기",
            "마지막 검산 포인트를 문제마다 고정하기",
        ],
        "extension_rows": [
            ["기본", "정의와 기준 식 확인", "첫 줄을 안정적으로 적는다"],
            ["응용", "중간 전환 한 번 추가", "조건을 더 세밀하게 묶는다"],
            ["고난도", "구조를 복원하며 읽기", "계산보다 흐름을 먼저 정한다"],
        ],
    }

    if any(keyword in element for keyword in ["미분", "도함수", "미분계수"]):
        kit.update(
            {
                "teacher_line": "미분은 숫자를 구하는 단원이 아니라 함수의 움직임을 읽는 언어입니다.",
                "first_line": "도함수 식 또는 변화율 해석을 먼저 고정한다.",
                "why_it_matters": "증가·감소, 극값, 접선, 킬러 구조까지 대부분 미분의 해석에서 갈립니다.",
                "checks": ["미분 가능 여부", "도함수 부호", "극값 후보와 접선 정보"],
                "board_lines": ["f'(x)를 먼저 정리", "부호표 또는 기울기 해석", "극값·접선·최종 답 연결"],
                "intuition_rows": [
                    ["기울기", "순간 변화의 방향을 본다", "증가·감소를 먼저 읽는다"],
                    ["도함수", "원함수의 움직임을 식으로 적는다", "부호가 바뀌는 지점을 찾는다"],
                    ["활용", "극값·접선·최댓값 문제로 연결", "조건을 함수의 성질로 번역한다"],
                ],
                "misconceptions": [
                    ["도함수는 계산만 맞으면 된다", "도함수의 부호 해석이 핵심이다", "증가·감소를 말로 먼저 설명한다"],
                    ["f'(a)=0이면 무조건 극값이다", "부호 변화까지 봐야 한다", "좌우 부호를 비교한다"],
                    ["접선 문제는 공식 대입 문제다", "기울기와 접점을 동시에 복원해야 한다", "접점 좌표를 따로 확인한다"],
                ],
                "advanced_moves": [
                    "도함수의 근을 찾은 뒤 부호 변화까지 묶어 해석하기",
                    "접선 조건을 원함수의 계수 조건으로 되돌리기",
                    "극값과 직선, 적분, 합성함수 조건을 연결해 구조를 복원하기",
                ],
                "extension_rows": [
                    ["기본", "도함수 계산", "기울기와 증가·감소를 읽는다"],
                    ["응용", "극값·접선 조건 연결", "부호표와 좌표를 동시에 본다"],
                    ["고난도", "조건으로 함수 전체를 복원", "도함수 해석을 역으로 사용한다"],
                ],
            }
        )
    elif "적분" in element:
        kit.update(
            {
                "teacher_line": "적분은 넓이 계산을 넘어 누적량과 구간 해석을 다루는 도구입니다.",
                "first_line": "적분 구간과 어떤 양을 누적하는지 먼저 확인한다.",
                "why_it_matters": "정적분의 부호, 넓이, 부피, 함수 복원까지 적분 해석이 점수 차이를 만듭니다.",
                "checks": ["적분 구간", "부호와 넓이 해석", "기본정리 적용 지점"],
                "board_lines": ["적분 구간 확인", "부호·넓이·누적량 해석", "기본정리 또는 치환 정리"],
                "intuition_rows": [
                    ["누적", "작은 변화를 모아 큰 양을 본다", "구간의 시작과 끝을 먼저 본다"],
                    ["정적분", "넓이 또는 부호 있는 넓이를 해석한다", "축과의 관계를 확인한다"],
                    ["활용", "넓이·부피·함수 복원으로 연결", "구간이 바뀌면 해석도 바뀐다"],
                ],
                "misconceptions": [
                    ["정적분은 무조건 넓이이다", "부호 있는 넓이일 수 있다", "그래프 위치를 먼저 본다"],
                    ["부정적분과 정적분은 다른 공식이다", "기본정리로 연결된다", "원시함수와 구간을 같이 본다"],
                    ["치환만 하면 끝난다", "변수와 구간도 함께 바꿔야 한다", "마지막 구간을 검산한다"],
                ],
                "advanced_moves": [
                    "그래프 부호에 따라 구간을 나눠 정적분을 해석하기",
                    "적분값 조건으로 함수의 계수나 넓이를 역추적하기",
                    "적분과 수열, 미분, 절댓값 조건을 함께 묶어 구조를 복원하기",
                ],
            }
        )
    elif any(keyword in element for keyword in ["극한", "연속"]):
        kit.update(
            {
                "teacher_line": "극한과 연속은 값 자체보다, 값이 다가가는 방식과 끊기는 이유를 읽는 단원입니다.",
                "first_line": "좌극한·우극한·함숫값 중 무엇이 주어졌는지 먼저 나눈다.",
                "why_it_matters": "함수의 형태를 복원하거나 미분·적분으로 넘어가기 전 가장 중요한 연결 단원입니다.",
                "checks": ["좌극한과 우극한", "함숫값", "끊기는 이유"],
                "board_lines": ["좌극한/우극한 구분", "함숫값과 연속 판정", "조건으로 식을 조정"],
                "advanced_moves": [
                    "식이 다른 구간을 각각 해석하고 경계점에서 연결하기",
                    "연속 조건을 계수 조건으로 바꿔 미지수를 정하기",
                    "절댓값, 분수식, 조각함수의 경계 해석을 훈련하기",
                ],
            }
        )
    elif any(keyword in element for keyword in ["수열", "급수", "귀납법"]):
        kit.update(
            {
                "teacher_line": "수열은 n번째 항만 보는 단원이 아니라, 규칙과 누적 구조를 복원하는 단원입니다.",
                "first_line": "일반항인지, 점화식인지, 부분합인지 먼저 구분한다.",
                "why_it_matters": "규칙을 읽는 힘이 있어야 고난도 수열과 급수도 흔들리지 않습니다.",
                "checks": ["항의 구조", "부분합 또는 차이", "마지막 일반항 정리"],
                "board_lines": ["주어진 정보의 형태 구분", "부분합·차이·비교", "일반항 또는 합 정리"],
                "advanced_moves": [
                    "부분합을 먼저 놓고 일반항을 되돌리기",
                    "귀납 구조를 한 줄 템플릿으로 고정하기",
                    "수열 극한과 급수 조건을 동시에 묶어 서사를 읽기",
                ],
            }
        )
    elif any(keyword in element for keyword in ["확률", "조건부확률", "분포", "통계", "추정"]):
        kit.update(
            {
                "teacher_line": "확률과 통계는 공식을 고르는 단원이 아니라 표본공간과 사건을 정확히 나누는 단원입니다.",
                "first_line": "전체 경우와 원하는 경우를 먼저 분리한다.",
                "why_it_matters": "식은 단순해 보여도 분류를 잘못하면 끝까지 틀리기 쉬운 단원입니다.",
                "checks": ["전체 경우", "사건 분리", "조건의 방향"],
                "board_lines": ["표본공간 정리", "사건 분리 또는 분포 모형", "기댓값·확률·추정 결과 정리"],
                "advanced_moves": [
                    "조건부확률에서 기준 사건을 먼저 고정하기",
                    "분포의 평균과 분산을 변환 관점으로 정리하기",
                    "서로 다른 확률 모델을 표와 식으로 동시에 비교하기",
                ],
            }
        )
    elif any(keyword in element for keyword in ["순열", "조합", "이항정리", "경우의 수"]):
        kit.update(
            {
                "teacher_line": "경우의 수는 계산보다 분류가 먼저인 단원입니다.",
                "first_line": "순서가 있는지, 중복이 있는지, 선택인지 배열인지 먼저 확인한다.",
                "why_it_matters": "문제 문장을 잘 쪼개면 계산 자체는 훨씬 짧아집니다.",
                "checks": ["순서 여부", "중복 여부", "분류 기준"],
                "board_lines": ["조건 분류", "합/곱 원리 선택", "순열·조합·이항 전개 정리"],
            }
        )
    elif any(keyword in element for keyword in ["벡터", "내적", "공간", "공간좌표", "도형", "이차곡선", "직선", "원"]):
        kit.update(
            {
                "teacher_line": "기하 단원은 그림을 보고 끝내는 게 아니라, 좌표와 관계식을 언어처럼 읽는 단원입니다.",
                "first_line": "도형의 핵심 점과 관계식을 좌표 또는 벡터로 먼저 적는다.",
                "why_it_matters": "길이, 각, 위치 관계를 식으로 옮기는 속도가 점수를 좌우합니다.",
                "checks": ["핵심 점과 선", "좌표 또는 벡터 표현", "길이·각·내적 관계"],
                "board_lines": ["도형 정보 표시", "좌표/벡터 식 세우기", "거리·각·위치 관계 정리"],
            }
        )
    elif any(keyword in element for keyword in ["지수", "로그"]):
        kit.update(
            {
                "teacher_line": "지수와 로그는 식을 줄이는 기술이 아니라, 서로 다른 표현을 같은 언어로 맞추는 단원입니다.",
                "first_line": "지수식은 밑을 맞추고, 로그식은 진수 조건과 밑의 조건을 먼저 적는다.",
                "why_it_matters": "밑 통일과 정의역 확인이 첫 줄에서 안 되면 뒤 계산이 맞아도 버려지는 경우가 많은 단원입니다.",
                "checks": ["밑을 통일할 수 있는가", "진수와 밑의 조건을 만족하는가", "정리한 뒤 같은 식으로 모였는가"],
                "board_lines": ["밑 통일 또는 진수 조건 표시", "성질 적용 전후를 비교", "정의역과 해를 함께 검산"],
                "intuition_rows": [
                    ["지수식", "같은 밑으로 맞춘다", "지수끼리 직접 비교할 수 있습니다"],
                    ["로그식", "진수 조건부터 적는다", "정의역을 놓쳐 버려지는 해를 막습니다"],
                    ["혼합형", "지수와 로그를 같은 식으로 번역한다", "그래프보다 식 정리가 먼저입니다"],
                ],
                "misconceptions": [
                    ["로그는 성질부터 쓰면 된다", "진수 조건과 밑의 조건이 먼저입니다", "정의역을 첫 줄에 적습니다"],
                    ["지수식은 바로 계산한다", "같은 밑으로 맞춘 뒤 비교합니다", "밑 통일 여부를 먼저 봅니다"],
                    ["해가 나오면 끝이다", "원래 식에 다시 넣어 조건까지 검산해야 합니다", "버려지는 해를 마지막에 체크합니다"],
                ],
                "advanced_moves": [
                    "밑이 다른 지수식을 하나의 밑으로 통일해 구조를 단순화하기",
                    "로그합을 한 개의 로그로 묶은 뒤 정의역을 끝까지 유지하기",
                    "지수와 로그가 함께 있는 문제를 대수 해석과 그래프 해석으로 동시에 읽기",
                ],
                "extension_rows": [
                    ["기본", "밑 통일 또는 진수 조건", "정의역을 먼저 적는다"],
                    ["응용", "성질 적용 후 한 식으로 묶기", "버려지는 해를 마지막에 검산한다"],
                    ["고난도", "지수와 로그를 같은 구조로 번역", "그래프 해석까지 함께 본다"],
                ],
            }
        )
    elif any(keyword in element for keyword in ["함수", "유리함수", "무리함수", "역함수", "합성함수"]):
        kit.update(
            {
                "teacher_line": "함수는 식만 보는 단원이 아니라 대응 규칙과 그래프 움직임을 함께 읽는 단원입니다.",
                "first_line": "정의역과 대응 규칙을 먼저 본다.",
                "checks": ["정의역", "대응 규칙", "그래프 이동과 해석"],
                "board_lines": ["정의역·치역 확인", "식의 구조 보기", "그래프와 성질 연결"],
            }
        )
    elif any(keyword in element for keyword in ["방정식", "부등식", "복소수", "이차함수"]):
        kit.update(
            {
                "teacher_line": "방정식과 부등식은 해를 구하는 절차보다, 어떤 해석을 먼저 할지 결정하는 단원입니다.",
                "first_line": "인수분해, 판별식, 그래프 해석 중 어느 길인지 먼저 정한다.",
                "checks": ["해의 구조", "판별식 또는 그래프", "범위와 부호"],
                "board_lines": ["문제 유형 판정", "해석 도구 선택", "해 또는 구간 정리"],
            }
        )
    elif any(keyword in element for keyword in ["집합", "명제"]):
        kit.update(
            {
                "teacher_line": "집합과 명제는 기호만 읽는 단원이 아니라, 말과 논리를 정리하는 단원입니다.",
                "first_line": "조건의 포함 관계와 명제 방향을 먼저 본다.",
                "checks": ["포함 관계", "필요·충분", "대우와 부정"],
                "board_lines": ["기호를 말로 번역", "포함 또는 명제 방향 확인", "반례·대우 검토"],
            }
        )

    if problem.get("isKiller"):
        kit["advanced_moves"] = list(kit["advanced_moves"]) + [
            "조건을 한 번 더 해석해 숨은 구조를 복원하기",
        ]
    return kit


def _problem_branch_scene(unit: dict, problem: dict, index: int) -> dict:
    problem_label = str(problem.get("problemType") or problem.get("title") or f"유형 {index}")
    objects: list[dict] = [
        {
            "id": f"{unit['id']}-branch-{index}-title",
            "type": "heading",
            "x": 6,
            "y": 8,
            "w": 40,
            "content": f"유형 분기 {index} · {problem_label}",
        },
        {
            "id": f"{unit['id']}-branch-{index}-badge",
            "type": "badge",
            "x": 70,
            "y": 8,
            "w": 18,
            "content": _problem_difficulty_badge(problem),
            "delayMs": 120,
        },
        {
            "id": f"{unit['id']}-branch-{index}-statement",
            "type": "callout",
            "x": 8,
            "y": 20,
            "w": 36,
            "h": 24,
            "content": str(problem.get("statement") or "문제 유형 설명"),
            "delayMs": 180,
        },
        {
            "id": f"{unit['id']}-branch-{index}-route",
            "type": "table",
            "x": 46,
            "y": 20,
            "w": 44,
            "h": 38,
            "table": {
                "headers": ["첫 판단", "써야 할 식", "검산 포인트"],
                "rows": _problem_step_rows(problem),
            },
            "delayMs": 260,
        },
        {
            "id": f"{unit['id']}-branch-{index}-check",
            "type": "checklist",
            "x": 8,
            "y": 50,
            "w": 34,
            "h": 24,
            "label": "이 유형에서 봐야 할 것",
            "items": _problem_focus_checks(problem),
            "delayMs": 360,
        },
    ]
    if problem.get("evaluationType") == "tangent-line":
        expression = str(problem.get("functionSpec", {}).get("expression") or "f(x)")
        point_x = problem.get("functionSpec", {}).get("pointX")
        objects.extend(
            [
                {
                    "id": f"{unit['id']}-branch-{index}-eq",
                    "type": "equation",
                    "x": 46,
                    "y": 62,
                    "w": 28,
                    "content": f"f(x) = {expression}",
                    "delayMs": 430,
                },
                {
                    "id": f"{unit['id']}-branch-{index}-graph",
                    "type": "graph",
                    "x": 58,
                    "y": 56,
                    "w": 32,
                    "h": 20,
                    "graphSpec": {
                        "function": expression,
                        "xMin": float(point_x) - 3 if point_x is not None else -3,
                        "xMax": float(point_x) + 3 if point_x is not None else 3,
                        "yMin": -8,
                        "yMax": 12,
                        "tangentAt": point_x,
                        "markLabel": f"x={point_x}" if point_x is not None else "접점",
                    },
                    "delayMs": 500,
                },
            ]
        )
    else:
        objects.append(
            {
                "id": f"{unit['id']}-branch-{index}-outline",
                "type": "badge",
                "x": 46,
                "y": 62,
                "w": 38,
                "content": " → ".join(list(problem.get("expectedOutline", [])[:4]) or ["기준 식", "판정", "정리"]),
                "delayMs": 430,
            }
        )
    if problem.get("isKiller"):
        objects.append(
            {
                "id": f"{unit['id']}-branch-{index}-killer-tip",
                "type": "callout",
                "x": 8,
                "y": 76,
                "w": 54,
                "content": "킬러 문제는 계산보다 구조 전환이 먼저입니다. 중간에 새로운 식을 만들기보다 이미 구한 극값·조건을 다른 형태로 연결하세요.",
                "delayMs": 560,
            }
        )
    return {
        "id": f"scene-{unit['id']}-branch-{index}",
        "title": f"{problem_label} 분기 보드",
        "narration": (
            f"'{problem.get('title')}' 유형은 {problem_label}로 묶입니다. "
            "문제를 읽으면 지금 장면의 표에서 첫 판단을 잡고, 체크리스트 순서대로 시선을 옮겨보면 됩니다."
        ),
        "teachingGoal": f"{problem_label} 문제를 처음 15초 동안 어떻게 읽으면 좋을지 같이 잡아볼까요?",
        "takeaway": f"{problem_label}은(는) 계산보다 먼저 확인할 포인트가 분명한 유형입니다.",
        "examCue": "질문이 나오면 지금 선택한 객체를 기준으로 다시 설명해볼 수 있어야 합니다.",
        "practiceBridge": f"바로 이어서 '{problem.get('title')}'이나 같은 유형 문제에 써볼 수 있습니다.",
        "autoAdvanceSeconds": 22 if problem.get("isKiller") else 18,
        "sceneGroup": "problem-branch",
        "branchKey": str(problem.get("id") or f"branch-{index}"),
        "branchLabel": problem_label,
        "problemId": str(problem.get("id") or ""),
        "source": f"{PDF_SOURCE_PATH} p.{unit['pdfPages']}",
        "objects": objects,
    }


def _problem_branch_scenes(unit: dict) -> list[dict]:
    branch_candidates = unit["problems"][:6]
    return [
        _problem_branch_scene(unit, problem, index)
        for index, problem in enumerate(branch_candidates, start=1)
    ]


DRILL_TARGET_PER_UNIT = 30


def _pretty_math(raw: str) -> str:
    return (
        raw.replace("**2", "^2")
        .replace("**3", "^3")
        .replace("*x", "x")
        .replace("*", "")
        .replace("+-", "-")
    )


def _signed(value: int) -> str:
    return f"+{value}" if value >= 0 else str(value)


def _clean_problem_title(title: str) -> str:
    normalized = re.sub(r"\s+\d+$", "", title).strip()
    normalized = re.sub(r"\s+킬러$", "", normalized).strip()
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized or title


def _difficulty_profile(index: int, *, killer_allowed: bool = False) -> tuple[str, bool]:
    if killer_allowed:
        if index >= DRILL_TARGET_PER_UNIT - 4:
            return ("apex", True)
        if index >= DRILL_TARGET_PER_UNIT - 8:
            return ("killer", True)
        return ("advanced", False)
    if index >= DRILL_TARGET_PER_UNIT - 4:
        return ("killer", True)
    return ("advanced", False)


def _difficulty_title_prefix(difficulty: str) -> str:
    if difficulty == "apex":
        return "최종 apex"
    if difficulty == "killer":
        return "킬러"
    return "초고난도"


def _drill_problem(
    *,
    unit: dict,
    index: int,
    title: str,
    statement: str,
    steps: list[dict],
    final: dict,
    coach_hint: str,
    expected_outline: list[str],
    final_prompt: str,
    problem_type: str,
    killer_allowed: bool = False,
) -> dict:
    difficulty, is_killer = _difficulty_profile(index, killer_allowed=killer_allowed)
    prefix = _difficulty_title_prefix(difficulty)
    return structured_problem(
        problem_id=f"curr-{unit['id']}-drill-{index:03d}",
        title=f"{prefix} · {_clean_problem_title(title)}",
        statement=statement,
        unit_title=f"{unit['courseTitle']} - {unit['domainTitle']}",
        course_title=unit["courseTitle"],
        achievement_codes=unit["achievementCodes"],
        steps=steps,
        final=final,
        coach_hint=f"{coach_hint} 이 문제 묶음은 쉬운 반복이 아니라 구조 판단을 먼저 잡는 초고난도 한계돌파입니다.",
        expected_outline=expected_outline,
        final_prompt=final_prompt,
        difficulty=difficulty,
        problem_type=problem_type,
        is_killer=is_killer,
    )


def _drill_tangent_problem(
    *,
    unit: dict,
    index: int,
    expression: str,
    point_x: int,
    title: str,
    problem_type: str,
    killer_allowed: bool = True,
) -> dict:
    difficulty, is_killer = _difficulty_profile(index, killer_allowed=killer_allowed)
    prefix = _difficulty_title_prefix(difficulty)
    return tangent_problem(
        problem_id=f"curr-{unit['id']}-drill-{index:03d}",
        title=f"{prefix} {title}",
        statement=f"함수 f(x)={_pretty_math(expression)}의 x={point_x}에서의 접선의 방정식을 구하시오.",
        course_title=unit["courseTitle"],
        unit_title=f"{unit['courseTitle']} - {unit['domainTitle']}",
        achievement_codes=unit["achievementCodes"],
        expression=expression,
        point_x=point_x,
        difficulty=difficulty,
        problem_type=problem_type,
        is_killer=is_killer,
    )


def _hard_common1_polynomial_openers(unit: dict) -> list[dict]:
    return [
        _drill_problem(
            unit=unit,
            index=1,
            title="나머지정리 삼중 판정 1",
            statement="다항식 P(x)=(x-1)(x+2)(x-4)+5일 때 P(1)+P(-2)+P(4)를 구하시오.",
            steps=[
                exact_step("Step 1. P(1)", "5", "x=1을 대입하면 곱 전체가 0이 되어 상수항만 남습니다."),
                exact_step("Step 2. P(-2), P(4)", "5, 5", "다른 근에서도 같은 구조가 반복됩니다."),
                numeric_step("Step 3. 합", "15", "세 값을 더하세요."),
            ],
            final=numeric_step("최종 답", "15", "세 값의 합을 적으세요."),
            coach_hint="나머지정리는 계산보다 '근을 넣으면 곱이 0이 된다'는 구조 판단이 먼저입니다.",
            expected_outline=["대입 근 확인", "곱 0 판단", "값 합치기", "최종 답"],
            final_prompt="예: 15",
            problem_type="나머지정리 삼중 적용",
            killer_allowed=True,
        ),
        _drill_problem(
            unit=unit,
            index=2,
            title="나머지정리 삼중 판정 2",
            statement="다항식 P(x)=(x+3)(x-2)(x-5)-7일 때 P(-3)+P(2)+P(5)를 구하시오.",
            steps=[
                exact_step("Step 1. P(-3)", "-7", "근을 대입하면 상수항만 남습니다."),
                exact_step("Step 2. P(2), P(5)", "-7, -7", "나머지정리 구조를 두 번 더 반복하세요."),
                numeric_step("Step 3. 합", "-21", "세 값을 더하세요."),
            ],
            final=numeric_step("최종 답", "-21", "세 값의 합을 적으세요."),
            coach_hint="한 번 본 나머지정리 구조를 끝까지 밀어붙이면 계산량이 거의 사라집니다.",
            expected_outline=["근 대입", "구조 반복", "값 합치기", "최종 답"],
            final_prompt="예: -21",
            problem_type="나머지정리 삼중 적용",
            killer_allowed=True,
        ),
        _drill_problem(
            unit=unit,
            index=3,
            title="사차식 구조 계수 판정",
            statement="(x^2+4x+3)(x^2-4x+5)를 전개할 때 x^2의 계수를 구하시오.",
            steps=[
                expr_step("Step 1. x^2항 후보", "5*x**2 - 16*x**2 + 3*x**2", "앞식의 상수·뒷식의 x^2, 양쪽 x항의 곱, 앞식의 x^2·뒷식의 상수만 보세요.", display="5x^2-16x^2+3x^2"),
                expr_step("Step 2. 계수 합", "-8*x**2", "x^2항만 모으세요.", display="-8x^2"),
                numeric_step("Step 3. 계수", "-8", "x^2의 계수를 읽으세요."),
            ],
            final=numeric_step("최종 답", "-8", "x^2의 계수를 적으세요."),
            coach_hint="전개 전체를 하지 말고 필요한 차수의 항만 골라내는 것이 고난도 다항식의 핵심입니다.",
            expected_outline=["필요한 항만 추출", "계수 합치기", "계수 읽기", "최종 답"],
            final_prompt="예: -8",
            problem_type="필요 차수 추출형",
            killer_allowed=True,
        ),
        _drill_problem(
            unit=unit,
            index=4,
            title="고난도 사차식 인수분해",
            statement="x^4-13x^2+36을 인수분해하시오.",
            steps=[
                expr_step("Step 1. 치환", "u**2 - 13*u + 36", "u=x^2로 치환해 이차식으로 보세요.", display="u^2-13u+36"),
                expr_step("Step 2. 인수분해", "(u-4)*(u-9)", "치환된 식을 인수분해하세요.", display="(u-4)(u-9)"),
                expr_step("Step 3. 원래 문자 복귀", "(x**2-4)*(x**2-9)", "u=x^2를 다시 대입하세요.", display="(x^2-4)(x^2-9)"),
            ],
            final=expr_step("최종 답", "(x-2)*(x+2)*(x-3)*(x+3)", "차의 제곱을 끝까지 인수분해하세요.", display="(x-2)(x+2)(x-3)(x+3)"),
            coach_hint="고난도 인수분해는 x가 아니라 x^2를 새 문자로 보는 순간 시작됩니다.",
            expected_outline=["치환", "이차식 인수분해", "복귀", "끝 인수분해"],
            final_prompt="예: (x-2)(x+2)(x-3)(x+3)",
            problem_type="치환 인수분해",
            killer_allowed=True,
        ),
    ]


def _hard_common1_equation_openers(unit: dict) -> list[dict]:
    return [
        _drill_problem(
            unit=unit,
            index=1,
            title="이차부등식 정수해 판정 1",
            statement="(x-1)(x-7)≤0을 만족하는 정수 x 중 x≠4인 것의 개수를 구하시오.",
            steps=[
                exact_step("Step 1. 부등식 구간", "1<=x<=7", "이차부등식의 해 구간을 먼저 잡으세요."),
                exact_step("Step 2. 제외 조건 반영", "1,2,3,5,6,7", "x=4를 제외하고 남는 정수를 쓰세요."),
                numeric_step("Step 3. 개수", "6", "남은 정수의 개수를 세세요."),
            ],
            final=numeric_step("최종 답", "6", "정수해의 개수를 적으세요."),
            coach_hint="고난도 부등식은 해구간 자체보다 추가 조건을 누락하지 않는지가 점수를 가릅니다.",
            expected_outline=["해구간 판정", "추가 조건 반영", "개수 세기", "최종 답"],
            final_prompt="예: 6",
            problem_type="이차부등식 정수해",
            killer_allowed=True,
        ),
        _drill_problem(
            unit=unit,
            index=2,
            title="판별식 역추론",
            statement="이차방정식 x^2-8x+k=0이 중근을 가질 때 k의 값을 구하시오.",
            steps=[
                expr_step("Step 1. 판별식", "(-8)**2 - 4*k", "중근 조건이므로 판별식을 세우세요.", display="64-4k"),
                exact_step("Step 2. 중근 조건", "64-4k=0", "중근이면 판별식이 0입니다."),
                numeric_step("Step 3. k", "16", "방정식을 풀어 k를 구하세요."),
            ],
            final=numeric_step("최종 답", "16", "k의 값을 적으세요."),
            coach_hint="문제는 근을 묻지만 출발은 항상 판별식이라는 사실을 놓치지 마세요.",
            expected_outline=["판별식", "중근 조건", "매개변수 계산", "최종 답"],
            final_prompt="예: 16",
            problem_type="판별식 역추론",
            killer_allowed=True,
        ),
        _drill_problem(
            unit=unit,
            index=3,
            title="절댓값 부등식 정수해",
            statement="|2x-5|<7을 만족하는 정수 x의 개수를 구하시오.",
            steps=[
                exact_step("Step 1. 양쪽 부등식", "-7<2x-5<7", "절댓값 부등식을 이중부등식으로 바꾸세요."),
                exact_step("Step 2. x의 범위", "-1<x<6", "양변 정리를 통해 x의 범위를 구하세요."),
                numeric_step("Step 3. 정수 개수", "6", "정수해의 개수를 세세요."),
            ],
            final=numeric_step("최종 답", "6", "정수해의 개수를 적으세요."),
            coach_hint="절댓값 부등식은 식을 푸는 것이 아니라 범위를 정확히 여는 문제입니다.",
            expected_outline=["이중부등식", "범위 정리", "개수 세기", "최종 답"],
            final_prompt="예: 6",
            problem_type="절댓값 부등식",
            killer_allowed=True,
        ),
        _drill_problem(
            unit=unit,
            index=4,
            title="근과 계수 구조 문제",
            statement="x^2-9x+14=0의 두 근을 α, β라 할 때 α^2+β^2를 구하시오.",
            steps=[
                exact_step("Step 1. 근의 합과 곱", "α+β=9, αβ=14", "근과 계수의 관계로 α+β와 αβ를 읽으세요."),
                expr_step("Step 2. 제곱합 식", "(9)**2 - 2*14", "α^2+β^2=(α+β)^2-2αβ를 쓰세요.", display="9^2-2·14"),
                numeric_step("Step 3. 계산", "53", "값을 계산하세요."),
            ],
            final=numeric_step("최종 답", "53", "α^2+β^2를 적으세요."),
            coach_hint="직접 근을 구하는 것보다 근과 계수 관계를 변형하는 쪽이 더 빠른 문제입니다.",
            expected_outline=["합·곱 읽기", "변형식 세우기", "계산", "최종 답"],
            final_prompt="예: 53",
            problem_type="근과 계수 응용",
            killer_allowed=True,
        ),
    ]


def _hard_common1_counting_openers(unit: dict) -> list[dict]:
    return [
        _drill_problem(
            unit=unit,
            index=1,
            title="연속 배치 고난도 1",
            statement="서로 다른 6명의 학생을 한 줄로 세울 때 A, B, C가 서로 이웃하도록 배열하는 방법의 수를 구하시오.",
            steps=[
                numeric_step("Step 1. 묶음 수", "4", "ABC를 한 묶음으로 보면 전체 대상은 4개입니다."),
                numeric_step("Step 2. 묶음 배열", "24", "4개의 대상을 배열하세요."),
                numeric_step("Step 3. 내부 배열 반영", "144", "ABC 내부 순서를 곱하세요."),
            ],
            final=numeric_step("최종 답", "144", "배열하는 방법의 수를 적으세요."),
            coach_hint="경우의 수 킬러는 묶을 대상과 풀어줄 대상을 먼저 구분하는 데서 시작합니다.",
            expected_outline=["묶음화", "외부 배열", "내부 배열", "최종 답"],
            final_prompt="예: 144",
            problem_type="연속 배치",
            killer_allowed=True,
        ),
        _drill_problem(
            unit=unit,
            index=2,
            title="위원회 구성 고난도 2",
            statement="남학생 5명, 여학생 4명 중에서 4명의 대표를 뽑을 때 여학생이 적어도 2명 포함되도록 하는 방법의 수를 구하시오.",
            steps=[
                exact_step("Step 1. 경우 분리", "4C2·5C2 + 4C3·5C1 + 4C4", "여학생 수를 2,3,4명으로 나누세요."),
                numeric_step("Step 2. 각 경우 합", "76", "세 경우를 더하세요."),
                exact_step("Step 3. 해석", "76가지", "경우의 수로 해석하세요."),
            ],
            final=numeric_step("최종 답", "76", "방법의 수를 적으세요."),
            coach_hint="고난도 조합은 '적어도'를 보자마자 경우 분리로 들어가는 습관이 중요합니다.",
            expected_outline=["경우 분리", "조합 계산", "합치기", "최종 답"],
            final_prompt="예: 76",
            problem_type="조건부 조합",
            killer_allowed=True,
        ),
        _drill_problem(
            unit=unit,
            index=3,
            title="원순열 조건 고난도 3",
            statement="서로 다른 5명을 원탁에 앉힐 때 A와 B가 이웃하도록 앉히는 방법의 수를 구하시오.",
            steps=[
                numeric_step("Step 1. 묶음 처리", "4", "A와 B를 한 묶음으로 보면 대상은 4개입니다."),
                numeric_step("Step 2. 원순열", "6", "4개의 대상을 원탁에 배열하세요."),
                numeric_step("Step 3. 내부 순서", "12", "AB, BA 두 경우를 반영하세요."),
            ],
            final=numeric_step("최종 답", "12", "방법의 수를 적으세요."),
            coach_hint="원순열은 한 자리를 고정한다는 사실을 놓치면 바로 계산이 무너집니다.",
            expected_outline=["묶음화", "원순열", "내부 순서", "최종 답"],
            final_prompt="예: 12",
            problem_type="원순열",
            killer_allowed=True,
        ),
        _drill_problem(
            unit=unit,
            index=4,
            title="자릿수 조건 고난도 4",
            statement="숫자 0,1,2,3,4,5,6을 한 번씩만 사용하여 만들 수 있는 네 자리 수 중 5의 배수의 개수를 구하시오.",
            steps=[
                exact_step("Step 1. 일의 자리 분리", "0 또는 5", "5의 배수 조건으로 일의 자리를 나누세요."),
                numeric_step("Step 2. 마지막 자리가 0", "120", "천의 자리 6가지, 나머지 두 자리 5P2입니다."),
                numeric_step("Step 3. 마지막 자리가 5까지 포함한 총합", "220", "마지막 자리가 5인 경우까지 더하세요."),
            ],
            final=numeric_step("최종 답", "220", "조건을 만족하는 수의 개수를 적으세요."),
            coach_hint="자릿수 경우의 수는 끝자리 조건을 먼저 자르는 순간 훨씬 빨라집니다.",
            expected_outline=["끝자리 조건", "경우 나누기", "합치기", "최종 답"],
            final_prompt="예: 220",
            problem_type="자릿수 조건 분리",
            killer_allowed=True,
        ),
    ]


def _hard_common1_matrix_openers(unit: dict) -> list[dict]:
    configs = [
        (2, [[3, 1], [2, -1], [4, 0], [1, 5]]),
        (3, [[2, 4], [1, -2], [5, 1], [3, 0]]),
        (-1, [[4, 2], [3, 1], [2, -3], [1, 6]]),
        (4, [[1, 3], [2, 5], [0, -1], [4, 2]]),
    ]
    problems: list[dict] = []
    for index, (a, rows) in enumerate(configs, start=1):
        x, y = rows[0]
        z, w = rows[1]
        b11 = x + a * z
        b12 = y + a * w
        total = x + y + z + w
        problems.append(
            _drill_problem(
                unit=unit,
                index=index,
                title=f"행렬방정식 역추론 {index}",
                statement=f"A=[[1,{a}],[0,1]], X=[[x,y],[z,w]]이고 AX=[[{b11},{b12}],[{z},{w}]]일 때 x+y+z+w의 값을 구하시오.",
                steps=[
                    exact_step("Step 1. 둘째 행 복구", f"z={z}, w={w}", "AX의 둘째 행은 그대로 z, w입니다."),
                    exact_step("Step 2. 첫째 행 복구", f"x={x}, y={y}", "첫째 행에서 a·z, a·w를 빼 x, y를 구하세요."),
                    numeric_step("Step 3. 합", str(total), "네 값을 더하세요."),
                ],
                final=numeric_step("최종 답", str(total), "x+y+z+w를 적으세요."),
                coach_hint="행렬방정식은 모양이 복잡해 보여도 행 단위로 복구하면 계산이 단순해집니다.",
                expected_outline=["둘째 행 복구", "첫째 행 복구", "합 계산", "최종 답"],
                final_prompt=f"예: {total}",
                problem_type="행렬방정식 역추론",
                killer_allowed=True,
            )
        )
    return problems


def _hard_common2_coordinate_openers(unit: dict) -> list[dict]:
    configs = [
        ((-1, 2), (5, 8), -2),
        ((2, -1), (8, 5), 1),
        ((-3, 5), (3, -1), 2),
        ((1, 7), (7, 1), -1),
    ]
    problems: list[dict] = []
    for index, (point_a, point_b, slope) in enumerate(configs, start=1):
        mx = (point_a[0] + point_b[0]) // 2
        my = (point_a[1] + point_b[1]) // 2
        intercept = my - slope * mx
        problems.append(
            _drill_problem(
                unit=unit,
                index=index,
                title=f"중점-직선 구조 문제 {index}",
                statement=f"A{point_a}, B{point_b}의 중점을 지나는 기울기 {slope}인 직선의 y절편을 구하시오.",
                steps=[
                    exact_step("Step 1. 중점", f"({mx},{my})", "두 점의 중점을 구하세요."),
                    expr_step("Step 2. 직선식", f"({slope})*x + ({intercept})", "기울기와 한 점을 이용해 직선식을 세우세요.", display=f"y={slope}x{_signed(intercept)}"),
                    numeric_step("Step 3. y절편", str(intercept), "직선식에서 y절편을 읽으세요."),
                ],
                final=numeric_step("최종 답", str(intercept), "y절편을 적으세요."),
                coach_hint="좌표 고난도 문제는 도형을 그리기 전에 좌표 연산으로 중간 지점을 먼저 확보해야 합니다.",
                expected_outline=["중점", "직선식", "절편 읽기", "최종 답"],
                final_prompt=f"예: {intercept}",
                problem_type="중점-직선 결합",
                killer_allowed=True,
            )
        )
    return problems


def _hard_common2_set_openers(unit: dict) -> list[dict]:
    configs = [
        (20, 12, 11, 5),
        (24, 15, 14, 8),
        (18, 10, 9, 4),
        (30, 17, 13, 6),
    ]
    problems: list[dict] = []
    for index, (universe, a_count, b_count, inter) in enumerate(configs, start=1):
        outside = universe - (a_count + b_count - inter)
        only_a = a_count - inter
        problems.append(
            _drill_problem(
                unit=unit,
                index=index,
                title=f"집합 정보 복구 {index}",
                statement=f"전체집합 U의 원소 수가 {universe}, n(A)={a_count}, n(B)={b_count}, n(A∩B)={inter}일 때 n(A-B)+n((A∪B)^c)를 구하시오.",
                steps=[
                    numeric_step("Step 1. A-B", str(only_a), "A-B의 원소 수는 n(A)-n(A∩B)입니다."),
                    numeric_step("Step 2. 합집합의 바깥", str(outside), "n((A∪B)^c)=n(U)-n(A∪B)입니다."),
                    numeric_step("Step 3. 합", str(only_a + outside), "두 값을 더하세요."),
                ],
                final=numeric_step("최종 답", str(only_a + outside), "요구한 값을 적으세요."),
                coach_hint="집합 고난도 문제는 합집합과 차집합을 각각 숫자로 복구하는 순서가 중요합니다.",
                expected_outline=["A-B", "합집합 바깥", "합치기", "최종 답"],
                final_prompt=f"예: {only_a + outside}",
                problem_type="집합 원소 수 복구",
                killer_allowed=True,
            )
        )
    return problems


def _hard_common2_function_openers(unit: dict) -> list[dict]:
    configs = [
        (2, -3, -1, 5, 2),
        (3, 1, 2, -4, -1),
        (-2, 6, 1, 3, 1),
        (4, -5, -2, 7, 0),
    ]
    problems: list[dict] = []
    for index, (a, b, c, d, t) in enumerate(configs, start=1):
        fg = a * (c * t + d) + b
        gf = c * (a * t + b) + d
        total = fg + gf
        problems.append(
            _drill_problem(
                unit=unit,
                index=index,
                title=f"합성함수 상호작용 {index}",
                statement=f"f(x)={a}x{_signed(b)}, g(x)={c}x{_signed(d)}일 때 f(g({t})) + g(f({t}))의 값을 구하시오.",
                steps=[
                    numeric_step("Step 1. f(g(t))", str(fg), "g(t)를 먼저 구한 뒤 f에 넣으세요."),
                    numeric_step("Step 2. g(f(t))", str(gf), "f(t)를 먼저 구한 뒤 g에 넣으세요."),
                    numeric_step("Step 3. 합", str(total), "두 값을 더하세요."),
                ],
                final=numeric_step("최종 답", str(total), "값을 적으세요."),
                coach_hint="합성함수 고난도 문제는 어떤 함수가 먼저 작동하는지의 순서를 끝까지 지켜야 합니다.",
                expected_outline=["안쪽 먼저", "반대 순서", "합치기", "최종 답"],
                final_prompt=f"예: {total}",
                problem_type="합성함수 상호작용",
                killer_allowed=True,
            )
        )
    return problems


def _hard_algebra_exp_log_openers(unit: dict) -> list[dict]:
    return [
        _drill_problem(
            unit=unit,
            index=1,
            title="지수 치환 킬러 1",
            statement="3^(2x)-10·3^x+9=0을 만족하는 모든 실수 x의 합을 구하시오.",
            steps=[
                exact_step("Step 1. 치환", "t=3^x", "지수방정식을 이차방정식으로 바꾸기 위해 치환하세요."),
                solution_step("Step 2. t의 값", ["1", "9"], "t에 대한 이차방정식을 푸세요."),
                numeric_step("Step 3. x의 합", "2", "3^x=1, 9를 각각 풀어 x의 합을 구하세요."),
            ],
            final=numeric_step("최종 답", "2", "모든 해의 합을 적으세요."),
            coach_hint="지수 킬러는 지수 자체를 보지 말고 새로운 문자로 내려놓는 순간부터 풀립니다.",
            expected_outline=["치환", "이차방정식", "원래 문자 복귀", "최종 답"],
            final_prompt="예: 2",
            problem_type="지수 치환형",
            killer_allowed=True,
        ),
        _drill_problem(
            unit=unit,
            index=2,
            title="로그 방정식 킬러 2",
            statement="log_2(x-1)+log_2(x-3)=3을 만족하는 x의 값을 구하시오.",
            steps=[
                expr_step("Step 1. 하나의 로그식", "(x-1)*(x-3)=8", "로그의 합을 곱으로 바꾸세요.", display="(x-1)(x-3)=8"),
                solution_step("Step 2. 이차방정식 해", ["-1", "5"], "이차방정식을 풀어 후보를 구하세요."),
                numeric_step("Step 3. 정의역 판정", "5", "x>3 조건을 만족하는 해만 남기세요."),
            ],
            final=numeric_step("최종 답", "5", "x의 값을 적으세요."),
            coach_hint="로그 킬러는 식 정리보다 정의역 검토에서 최종 정답이 갈립니다.",
            expected_outline=["로그 결합", "방정식 풀이", "정의역 판정", "최종 답"],
            final_prompt="예: 5",
            problem_type="로그 정의역 판정형",
            killer_allowed=True,
        ),
        _drill_problem(
            unit=unit,
            index=3,
            title="지수 연립 구조 3",
            statement="2^(x-1)+2^x=12를 만족하는 x의 값을 구하시오.",
            steps=[
                expr_step("Step 1. 공통항 묶기", "2**(x-1) + 2*2**(x-1)", "2^x=2·2^(x-1)로 바꾸세요.", display="2^(x-1)+2·2^(x-1)"),
                expr_step("Step 2. 일차식", "3*2**(x-1)=12", "공통항으로 묶어 일차형으로 만드세요.", display="3·2^(x-1)=12"),
                numeric_step("Step 3. x", "3", "2^(x-1)=4를 이용해 x를 구하세요."),
            ],
            final=numeric_step("최종 답", "3", "x의 값을 적으세요."),
            coach_hint="지수식은 밑을 맞춘 뒤 공통항으로 묶는 순간 난도가 크게 떨어집니다.",
            expected_outline=["밑 맞추기", "공통항 묶기", "역산", "최종 답"],
            final_prompt="예: 3",
            problem_type="지수식 공통항 묶기",
            killer_allowed=True,
        ),
        _drill_problem(
            unit=unit,
            index=4,
            title="로그 치환 구조 4",
            statement="log_3(x)+log_3(x-2)=2를 만족하는 x의 값을 구하시오.",
            steps=[
                expr_step("Step 1. 로그 결합", "x*(x-2)=9", "로그의 합을 곱으로 묶으세요.", display="x(x-2)=9"),
                exact_step("Step 2. 후보", "1-sqrt(10), 1+sqrt(10)", "이차방정식을 풀어 후보를 구하세요."),
                exact_step("Step 3. 정의역", "1+sqrt(10)", "x>2 조건을 반영해 해를 고르세요."),
            ],
            final=expr_step("최종 답", "1+sqrt(10)", "x의 값을 적으세요.", display="1+√10"),
            coach_hint="로그 방정식에서 후보를 구한 뒤 정의역을 마지막에 다시 보는 습관이 중요합니다.",
            expected_outline=["로그 결합", "후보 계산", "정의역 판정", "최종 답"],
            final_prompt="예: 1+sqrt(10)",
            problem_type="로그 치환형",
            killer_allowed=True,
        ),
    ]


def _hard_algebra_trig_openers(unit: dict) -> list[dict]:
    return [
        _drill_problem(
            unit=unit,
            index=1,
            title="사인방정식 해 개수",
            statement="0≤x<2π에서 2sin^2x-3sinx+1=0의 해의 개수를 구하시오.",
            steps=[
                expr_step("Step 1. 인수분해", "(2*sin(x)-1)*(sin(x)-1)=0", "sin x에 대한 이차방정식으로 보고 인수분해하세요.", display="(2sinx-1)(sinx-1)=0"),
                exact_step("Step 2. 가능한 sin값", "sinx=1/2 또는 sinx=1", "삼각방정식으로 분리하세요."),
                numeric_step("Step 3. 해 개수", "3", "구간에서 해의 개수를 세세요."),
            ],
            final=numeric_step("최종 답", "3", "해의 개수를 적으세요."),
            coach_hint="삼각 킬러는 식을 먼저 삼각함수 하나에 대한 방정식으로 낮추는 것이 핵심입니다.",
            expected_outline=["삼각식 이차화", "값 분리", "구간 개수", "최종 답"],
            final_prompt="예: 3",
            problem_type="사인방정식 해 개수",
            killer_allowed=True,
        ),
        _drill_problem(
            unit=unit,
            index=2,
            title="코사인방정식 해 개수",
            statement="0≤x<2π에서 2cos^2x-cosx-1=0의 해의 개수를 구하시오.",
            steps=[
                expr_step("Step 1. 인수분해", "(2*cos(x)+1)*(cos(x)-1)=0", "cos x에 대한 이차방정식으로 보세요.", display="(2cosx+1)(cosx-1)=0"),
                exact_step("Step 2. 가능한 cos값", "cosx=-1/2 또는 cosx=1", "가능한 값을 분리하세요."),
                numeric_step("Step 3. 해 개수", "3", "구간에서 해의 개수를 세세요."),
            ],
            final=numeric_step("최종 답", "3", "해의 개수를 적으세요."),
            coach_hint="cos형 문제도 구조는 같고, 마지막에는 단위원 위 해의 개수만 세면 됩니다.",
            expected_outline=["이차식", "값 분리", "개수 세기", "최종 답"],
            final_prompt="예: 3",
            problem_type="코사인방정식 해 개수",
            killer_allowed=True,
        ),
        _drill_problem(
            unit=unit,
            index=3,
            title="배각 구조 문제 3",
            statement="0≤x<2π에서 sin2x=sinx를 만족하는 x의 개수를 구하시오.",
            steps=[
                expr_step("Step 1. 배각 공식", "2*sin(x)*cos(x)=sin(x)", "sin2x를 배각공식으로 바꾸세요.", display="2sinx cosx = sinx"),
                expr_step("Step 2. 인수분해", "sin(x)*(2*cos(x)-1)=0", "한쪽으로 이항해 묶으세요.", display="sinx(2cosx-1)=0"),
                numeric_step("Step 3. 해 개수", "4", "sinx=0과 cosx=1/2의 해 개수를 합치세요."),
            ],
            final=numeric_step("최종 답", "4", "해의 개수를 적으세요."),
            coach_hint="배각공식을 써서 한 함수의 곱 형태로 만들면 해 개수 문제는 훨씬 단순해집니다.",
            expected_outline=["배각 공식", "곱 구조", "개수 세기", "최종 답"],
            final_prompt="예: 4",
            problem_type="배각공식 개수",
            killer_allowed=True,
        ),
        _drill_problem(
            unit=unit,
            index=4,
            title="탄젠트 구간 문제 4",
            statement="0≤x<2π에서 √3·tanx=1을 만족하는 x의 개수를 구하시오.",
            steps=[
                exact_step("Step 1. tan 값", "tanx=sqrt(3)/3", "양변을 √3으로 나누세요."),
                exact_step("Step 2. 기준각", "pi/6", "tan이 √3/3인 기준각을 찾으세요."),
                numeric_step("Step 3. 해 개수", "2", "주기 π를 이용해 구간 내 해를 세세요."),
            ],
            final=numeric_step("최종 답", "2", "해의 개수를 적으세요."),
            coach_hint="탄젠트 문제는 기준각과 주기를 동시에 떠올리는 순간 바로 정리됩니다.",
            expected_outline=["tan값 정리", "기준각", "주기 적용", "최종 답"],
            final_prompt="예: 2",
            problem_type="탄젠트 해 개수",
            killer_allowed=True,
        ),
    ]


def _hard_algebra_sequence_openers(unit: dict) -> list[dict]:
    return [
        _drill_problem(
            unit=unit,
            index=1,
            title="등차수열 역추론 1",
            statement="등차수열에서 a3=11, a8=31일 때 첫째항부터 제8항까지의 합을 구하시오.",
            steps=[
                numeric_step("Step 1. 공차", "4", "a8-a3=5d를 이용해 공차를 구하세요."),
                numeric_step("Step 2. 첫째항", "3", "a3=a1+2d로 첫째항을 구하세요."),
                numeric_step("Step 3. 합", "136", "S8=8(a1+a8)/2를 계산하세요."),
            ],
            final=numeric_step("최종 답", "136", "합을 적으세요."),
            coach_hint="수열 고난도는 식을 많이 세우는 것이 아니라 필요한 두 식만 정확히 고르는 문제입니다.",
            expected_outline=["공차 역추론", "첫째항 복구", "합 공식", "최종 답"],
            final_prompt="예: 136",
            problem_type="등차수열 역추론",
            killer_allowed=True,
        ),
        _drill_problem(
            unit=unit,
            index=2,
            title="등비수열 합 조건 2",
            statement="등비수열에서 a1=3, a4=24일 때 첫째항부터 제4항까지의 합을 구하시오. 공비는 양수이다.",
            steps=[
                numeric_step("Step 1. 공비", "2", "a4=a1r^3을 이용해 r을 구하세요."),
                expr_step("Step 2. 합 공식", "3*(2**4-1)/(2-1)", "등비수열의 합 공식을 적용하세요.", display="3(2^4-1)/(2-1)"),
                numeric_step("Step 3. 합", "45", "값을 계산하세요."),
            ],
            final=numeric_step("최종 답", "45", "합을 적으세요."),
            coach_hint="등비수열은 공비를 먼저 확정하고, 합 공식은 그 다음에 넣는 순서가 중요합니다.",
            expected_outline=["공비", "합 공식", "계산", "최종 답"],
            final_prompt="예: 45",
            problem_type="등비수열 합",
            killer_allowed=True,
        ),
        _drill_problem(
            unit=unit,
            index=3,
            title="등차-등비 결합 3",
            statement="등차수열의 첫째항이 5, 공차가 3일 때 제4항과 제7항의 곱을 구하시오.",
            steps=[
                numeric_step("Step 1. 제4항", "14", "a4=a1+3d를 계산하세요."),
                numeric_step("Step 2. 제7항", "23", "a7=a1+6d를 계산하세요."),
                numeric_step("Step 3. 곱", "322", "두 항을 곱하세요."),
            ],
            final=numeric_step("최종 답", "322", "곱을 적으세요."),
            coach_hint="수열 계산형 킬러는 일반항을 한 번만 써도 되는지 먼저 보는 것이 중요합니다.",
            expected_outline=["제4항", "제7항", "곱 계산", "최종 답"],
            final_prompt="예: 322",
            problem_type="수열 항 결합",
            killer_allowed=True,
        ),
        _drill_problem(
            unit=unit,
            index=4,
            title="부분합 역추론 4",
            statement="등차수열의 첫째항이 2, 공차가 4일 때 S10-S6의 값을 구하시오.",
            steps=[
                numeric_step("Step 1. S10", "200", "첫 10항의 합을 구하세요."),
                numeric_step("Step 2. S6", "72", "첫 6항의 합을 구하세요."),
                numeric_step("Step 3. 차", "128", "두 부분합의 차를 구하세요."),
            ],
            final=numeric_step("최종 답", "128", "값을 적으세요."),
            coach_hint="부분합 차이는 결국 뒤쪽 몇 항의 합이라는 사실을 떠올리면 훨씬 빨라집니다.",
            expected_outline=["S10", "S6", "차 계산", "최종 답"],
            final_prompt="예: 128",
            problem_type="부분합 차",
            killer_allowed=True,
        ),
    ]


def _hard_calc1_limit_openers(unit: dict) -> list[dict]:
    return [
        _drill_problem(
            unit=unit,
            index=1,
            title="인수분해 극한 1",
            statement="lim(x→3) (x^2-9)/(x-3)의 값을 구하시오.",
            steps=[
                expr_step("Step 1. 인수분해", "(x-3)*(x+3)/(x-3)", "분자를 인수분해하세요.", display="(x-3)(x+3)/(x-3)"),
                expr_step("Step 2. 약분", "x+3", "공통인수를 약분하세요."),
                numeric_step("Step 3. 대입", "6", "x=3을 대입하세요."),
            ],
            final=numeric_step("최종 답", "6", "극한값을 적으세요."),
            coach_hint="0/0형 극한은 계산이 아니라 구조를 바꾸는 순간부터 풀립니다.",
            expected_outline=["인수분해", "약분", "대입", "최종 답"],
            final_prompt="예: 6",
            problem_type="인수분해 극한",
            killer_allowed=True,
        ),
        _drill_problem(
            unit=unit,
            index=2,
            title="유리화 극한 2",
            statement="lim(x→0) (√(x+4)-2)/x의 값을 구하시오.",
            steps=[
                expr_step("Step 1. 유리화", "((x+4)-4)/(x*(sqrt(x+4)+2))", "분자와 분모에 켤레를 곱하세요.", display="((x+4)-4)/(x(√(x+4)+2))"),
                expr_step("Step 2. 약분", "1/(sqrt(x+4)+2)", "x를 약분하세요.", display="1/(√(x+4)+2)"),
                expr_step("Step 3. 대입", "1/4", "x=0을 대입하세요.", display="1/4"),
            ],
            final=expr_step("최종 답", "1/4", "극한값을 적으세요.", display="1/4"),
            coach_hint="루트 극한은 유리화로 식을 바꾸지 않으면 끝까지 진전이 없습니다.",
            expected_outline=["유리화", "약분", "대입", "최종 답"],
            final_prompt="예: 1/4",
            problem_type="유리화 극한",
            killer_allowed=True,
        ),
        _drill_problem(
            unit=unit,
            index=3,
            title="연속 조건 역추론 3",
            statement="f(x)={(x^2-1)/(x-1) (x≠1), k (x=1)}가 x=1에서 연속일 때 k의 값을 구하시오.",
            steps=[
                expr_step("Step 1. 극한식 정리", "x+1", "x≠1에서 식을 약분하세요.", display="x+1"),
                numeric_step("Step 2. 극한값", "2", "x→1의 극한값을 구하세요."),
                numeric_step("Step 3. 연속 조건", "2", "연속이면 함수값 k가 극한값과 같아야 합니다."),
            ],
            final=numeric_step("최종 답", "2", "k의 값을 적으세요."),
            coach_hint="연속 조건 문제는 식을 다루는 것보다 '극한값 = 함수값' 구조를 기억하는 것이 핵심입니다.",
            expected_outline=["약분", "극한값", "연속 조건", "최종 답"],
            final_prompt="예: 2",
            problem_type="연속 조건 역추론",
            killer_allowed=True,
        ),
        _drill_problem(
            unit=unit,
            index=4,
            title="다항식 극한 결합 4",
            statement="lim(x→2) ((x^3-8)/(x-2) - x^2)의 값을 구하시오.",
            steps=[
                expr_step("Step 1. 몫 정리", "x**2 + 2*x + 4 - x**2", "x^3-8=(x-2)(x^2+2x+4)를 이용하세요.", display="x^2+2x+4-x^2"),
                expr_step("Step 2. 정리", "2*x+4", "동류항을 정리하세요."),
                numeric_step("Step 3. 대입", "8", "x=2를 대입하세요."),
            ],
            final=numeric_step("최종 답", "8", "극한값을 적으세요."),
            coach_hint="극한 계산 뒤에 남는 식을 끝까지 정리하는 한 줄이 실제 점수를 결정합니다.",
            expected_outline=["인수분해 몫", "정리", "대입", "최종 답"],
            final_prompt="예: 8",
            problem_type="극한 결합형",
            killer_allowed=True,
        ),
    ]


def _hard_calc1_integral_openers(unit: dict) -> list[dict]:
    return [
        _drill_problem(
            unit=unit,
            index=1,
            title="도형 넓이 킬러 1",
            statement="y=x와 y=x^2로 둘러싸인 도형의 넓이를 구하시오.",
            steps=[
                exact_step("Step 1. 교점", "x=0,1", "두 그래프의 교점을 먼저 구하세요."),
                exact_step("Step 2. 넓이 적분식", "∫0→1 (x-x^2) dx", "위 함수-아래 함수를 적으세요."),
                expr_step("Step 3. 계산", "1/6", "정적분 값을 계산하세요.", display="1/6"),
            ],
            final=expr_step("최종 답", "1/6", "넓이를 적으세요.", display="1/6"),
            coach_hint="정적분 킬러는 적분보다 먼저 위아래 관계와 교점을 잡는 문제입니다.",
            expected_outline=["교점", "적분식", "계산", "최종 답"],
            final_prompt="예: 1/6",
            problem_type="도형 넓이",
            killer_allowed=True,
        ),
        _drill_problem(
            unit=unit,
            index=2,
            title="정적분 계산 2",
            statement="∫(0→2) (3x^2-4x+2) dx의 값을 구하시오.",
            steps=[
                expr_step("Step 1. 원시함수", "x**3 - 2*x**2 + 2*x", "항별로 적분하세요.", display="x^3-2x^2+2x"),
                expr_step("Step 2. 상한-하한", "(2**3 - 2*(2**2) + 2*2) - 0", "상한과 하한을 대입하세요.", display="(8-8+4)-0"),
                numeric_step("Step 3. 계산", "4", "값을 계산하세요."),
            ],
            final=numeric_step("최종 답", "4", "정적분 값을 적으세요."),
            coach_hint="정적분 계산형도 끝까지 원시함수를 정확히 쓰는 한 줄이 가장 중요합니다.",
            expected_outline=["원시함수", "대입", "계산", "최종 답"],
            final_prompt="예: 4",
            problem_type="정적분 계산",
            killer_allowed=True,
        ),
        _drill_problem(
            unit=unit,
            index=3,
            title="교점 넓이 3",
            statement="y=2x와 y=x^2로 둘러싸인 도형의 넓이를 구하시오.",
            steps=[
                exact_step("Step 1. 교점", "x=0,2", "두 그래프의 교점을 구하세요."),
                exact_step("Step 2. 적분식", "∫0→2 (2*x-x**2) dx", "위 함수-아래 함수를 적으세요."),
                expr_step("Step 3. 계산", "4/3", "정적분 값을 계산하세요.", display="4/3"),
            ],
            final=expr_step("최종 답", "4/3", "넓이를 적으세요.", display="4/3"),
            coach_hint="그래프 넓이 문제는 식 계산보다 어느 함수가 위에 있는지 판정하는 데서 점수가 갈립니다.",
            expected_outline=["교점", "적분식", "계산", "최종 답"],
            final_prompt="예: 4/3",
            problem_type="교점 넓이",
            killer_allowed=True,
        ),
        _drill_problem(
            unit=unit,
            index=4,
            title="구간 평균 구조 4",
            statement="함수 f(x)=x^2+2x의 [0,2]에서의 평균값을 구하시오.",
            steps=[
                expr_step("Step 1. 평균값 식", "(1/2)*((2**3)/3 + 2**2)", "1/(b-a)·∫a→b f(x)dx 구조를 쓰세요.", display="1/2·(8/3+4)"),
                expr_step("Step 2. 정리", "(1/2)*(20/3)", "괄호 안을 정리하세요.", display="1/2·20/3"),
                expr_step("Step 3. 평균값", "10/3", "값을 정리하세요.", display="10/3"),
            ],
            final=expr_step("최종 답", "10/3", "평균값을 적으세요.", display="10/3"),
            coach_hint="평균값 문제는 적분 계산보다 앞의 1/(b-a)를 빠뜨리지 않는지가 중요합니다.",
            expected_outline=["평균값 공식", "정리", "계산", "최종 답"],
            final_prompt="예: 10/3",
            problem_type="함수 평균값",
            killer_allowed=True,
        ),
    ]


def _hard_probstat_counting_openers(unit: dict) -> list[dict]:
    return [
        _drill_problem(
            unit=unit,
            index=1,
            title="조건부 조합 킬러 1",
            statement="남학생 4명, 여학생 3명 중에서 4명의 대표를 뽑을 때 여학생이 적어도 2명 포함되도록 하는 방법의 수를 구하시오.",
            steps=[
                exact_step("Step 1. 경우 분리", "3C2·4C2 + 3C3·4C1", "여학생 수를 2명과 3명으로 나누세요."),
                numeric_step("Step 2. 계산", "22", "각 경우를 더하세요."),
                exact_step("Step 3. 해석", "22가지", "경우의 수로 해석하세요."),
            ],
            final=numeric_step("최종 답", "22", "방법의 수를 적으세요."),
            coach_hint="조합 킬러는 '적어도' 조건을 보면 즉시 경우 분리부터 해야 합니다.",
            expected_outline=["경우 분리", "조합 계산", "합치기", "최종 답"],
            final_prompt="예: 22",
            problem_type="조건부 조합",
            killer_allowed=True,
        ),
        _drill_problem(
            unit=unit,
            index=2,
            title="중복 문자 배열 2",
            statement="BANANA의 문자를 모두 배열하는 서로 다른 방법의 수를 구하시오.",
            steps=[
                numeric_step("Step 1. 전체 배열", "720", "문자 6개의 전체 배열은 6!입니다."),
                expr_step("Step 2. 중복 보정", "720/(3*2)", "A 3개와 N 2개의 중복을 나누세요.", display="6!/(3!2!)"),
                numeric_step("Step 3. 계산", "60", "값을 계산하세요."),
            ],
            final=numeric_step("최종 답", "60", "배열 방법의 수를 적으세요."),
            coach_hint="중복 순열은 전체 배열을 먼저 세고, 같은 글자 반복을 나중에 나누는 것이 가장 안정적입니다.",
            expected_outline=["전체 배열", "중복 보정", "계산", "최종 답"],
            final_prompt="예: 60",
            problem_type="중복 순열",
            killer_allowed=True,
        ),
        _drill_problem(
            unit=unit,
            index=3,
            title="원순열 조건 3",
            statement="서로 다른 5명을 원탁에 앉힐 때 A와 B가 서로 이웃하지 않도록 앉히는 방법의 수를 구하시오.",
            steps=[
                numeric_step("Step 1. 전체 원순열", "24", "전체 원순열은 (5-1)!입니다."),
                numeric_step("Step 2. 이웃하는 경우", "12", "A와 B가 이웃하는 경우를 묶어서 세세요."),
                numeric_step("Step 3. 차", "12", "전체에서 이웃하는 경우를 빼세요."),
            ],
            final=numeric_step("최종 답", "12", "방법의 수를 적으세요."),
            coach_hint="제한이 '않도록'일 때는 전체에서 금지 경우를 빼는 보완 전략이 가장 빠릅니다.",
            expected_outline=["전체", "금지 경우", "보완", "최종 답"],
            final_prompt="예: 12",
            problem_type="원순열 보완",
            killer_allowed=True,
        ),
        _drill_problem(
            unit=unit,
            index=4,
            title="자릿수 조합 4",
            statement="숫자 1,2,3,4,5 중에서 중복 없이 세 개를 뽑아 만들 수 있는 세 자리 수 중 짝수의 개수를 구하시오.",
            steps=[
                numeric_step("Step 1. 일의 자리", "2", "짝수가 되려면 일의 자리는 2 또는 4입니다."),
                numeric_step("Step 2. 나머지 자리", "12", "각 경우마다 백의 자리와 십의 자리는 4P2입니다."),
                numeric_step("Step 3. 총개수", "24", "두 경우를 더하세요."),
            ],
            final=numeric_step("최종 답", "24", "개수를 적으세요."),
            coach_hint="자릿수 조건 문제는 가장 제한이 강한 자리를 먼저 자르는 것이 핵심입니다.",
            expected_outline=["끝자리 판정", "나머지 자리", "합치기", "최종 답"],
            final_prompt="예: 24",
            problem_type="자릿수 조건",
            killer_allowed=True,
        ),
    ]


def _hard_probability_openers(unit: dict) -> list[dict]:
    return [
        _drill_problem(
            unit=unit,
            index=1,
            title="조건부확률 킬러 1",
            statement="빨간 공 3개, 파란 공 2개가 들어 있는 주머니에서 두 개를 차례로 꺼낼 때 첫째가 빨간 공일 조건에서 둘째도 빨간 공일 확률을 구하시오.",
            steps=[
                exact_step("Step 1. 조건 후 표본공간", "남은 공 4개 중 빨간 공 2개", "첫째가 빨간 공이라는 조건을 먼저 반영하세요."),
                expr_step("Step 2. 확률식", "2/4", "조건 안에서 둘째도 빨간 공일 확률을 쓰세요.", display="2/4"),
                expr_step("Step 3. 기약분수", "1/2", "확률을 기약분수로 정리하세요.", display="1/2"),
            ],
            final=expr_step("최종 답", "1/2", "확률을 적으세요.", display="1/2"),
            coach_hint="조건부확률은 원래 표본공간을 지우고 새 표본공간부터 다시 세는 문제입니다.",
            expected_outline=["조건 반영", "확률식", "기약분수", "최종 답"],
            final_prompt="예: 1/2",
            problem_type="조건부확률",
            killer_allowed=True,
        ),
        _drill_problem(
            unit=unit,
            index=2,
            title="카드 확률 구조 2",
            statement="1부터 10까지 적힌 카드 10장 중 2장을 동시에 뽑을 때 두 수의 합이 10 이상일 확률을 구하시오.",
            steps=[
                numeric_step("Step 1. 전체 경우", "45", "동시에 2장을 뽑는 전체 경우는 10C2입니다."),
                numeric_step("Step 2. 유리한 경우", "24", "합이 10 이상이 되는 쌍의 개수를 세세요."),
                expr_step("Step 3. 확률", "8/15", "유리한 경우/전체 경우를 기약분수로 정리하세요.", display="24/45=8/15"),
            ],
            final=expr_step("최종 답", "8/15", "확률을 적으세요.", display="8/15"),
            coach_hint="확률 킬러는 유리한 경우를 직접 세기 어렵다면 합이 작은 경우를 먼저 제외해도 됩니다.",
            expected_outline=["전체 경우", "유리한 경우", "기약분수", "최종 답"],
            final_prompt="예: 8/15",
            problem_type="조합 확률",
            killer_allowed=True,
        ),
        _drill_problem(
            unit=unit,
            index=3,
            title="사건 교집합 3",
            statement="공정한 동전을 두 번 던질 때 A='두 번 모두 같은 면', B='첫째가 앞면'이라 하자. P(A∩B)를 구하시오.",
            steps=[
                numeric_step("Step 1. 전체 경우", "4", "전체 경우는 4가지입니다."),
                numeric_step("Step 2. A∩B 경우", "1", "조건을 동시에 만족하는 경우는 HH뿐입니다."),
                expr_step("Step 3. 확률", "1/4", "확률을 정리하세요.", display="1/4"),
            ],
            final=expr_step("최종 답", "1/4", "확률을 적으세요.", display="1/4"),
            coach_hint="독립 여부를 따지기 전에 교집합 사건을 정확히 쓰는 습관이 먼저입니다.",
            expected_outline=["전체 경우", "교집합 사건", "확률 정리", "최종 답"],
            final_prompt="예: 1/4",
            problem_type="사건 교집합",
            killer_allowed=True,
        ),
        _drill_problem(
            unit=unit,
            index=4,
            title="주사위 조건부확률 4",
            statement="공정한 주사위를 두 번 던질 때 합이 8이라는 조건에서 첫째 수가 3일 확률을 구하시오.",
            steps=[
                exact_step("Step 1. 조건 사건", "(2,6),(3,5),(4,4),(5,3),(6,2)", "합이 8인 경우를 모두 쓰세요."),
                numeric_step("Step 2. 유리한 경우", "1", "그중 첫째 수가 3인 경우는 1개입니다."),
                expr_step("Step 3. 확률", "1/5", "조건부확률을 적으세요.", display="1/5"),
            ],
            final=expr_step("최종 답", "1/5", "확률을 적으세요.", display="1/5"),
            coach_hint="조건이 주어졌을 때는 전체 36가지가 아니라 조건을 만족하는 경우만 다시 보는 것이 핵심입니다.",
            expected_outline=["조건 사건", "유리한 경우", "확률 정리", "최종 답"],
            final_prompt="예: 1/5",
            problem_type="조건부확률 사건 나열",
            killer_allowed=True,
        ),
    ]


def _hard_statistics_openers(unit: dict) -> list[dict]:
    return [
        _drill_problem(
            unit=unit,
            index=1,
            title="평균 공식 대입 1",
            statement="확률변수 X~B(6,1/3)일 때 E(X)를 구하시오.",
            steps=[
                exact_step("Step 1. 공식", "np", "이항분포의 평균 공식을 쓰세요."),
                expr_step("Step 2. 대입", "6*(1/3)", "n과 p를 대입하세요.", display="6·1/3"),
                numeric_step("Step 3. 계산", "2", "값을 계산하세요."),
            ],
            final=numeric_step("최종 답", "2", "평균을 적으세요."),
            coach_hint="통계 킬러는 어떤 분포에서 어떤 공식을 꺼내야 하는지 정확히 아는 문제가 많습니다.",
            expected_outline=["공식 선택", "대입", "계산", "최종 답"],
            final_prompt="예: 2",
            problem_type="이항분포 평균 공식 대입",
            killer_allowed=True,
        ),
        _drill_problem(
            unit=unit,
            index=2,
            title="분산 공식 대입 2",
            statement="확률변수 X~B(5,1/2)일 때 V(X)를 구하시오.",
            steps=[
                exact_step("Step 1. 공식", "np(1-p)", "이항분포의 분산 공식을 쓰세요."),
                expr_step("Step 2. 대입", "5*(1/2)*(1/2)", "공식에 값을 넣으세요.", display="5·1/2·1/2"),
                expr_step("Step 3. 계산", "5/4", "값을 계산하세요.", display="5/4"),
            ],
            final=expr_step("최종 답", "5/4", "분산을 적으세요.", display="5/4"),
            coach_hint="평균과 분산 공식을 섞지 않도록 마지막에 (1-p)가 들어갔는지 꼭 확인하세요.",
            expected_outline=["공식 선택", "대입", "계산", "최종 답"],
            final_prompt="예: 5/4",
            problem_type="이항분포 분산 공식 대입",
            killer_allowed=True,
        ),
        _drill_problem(
            unit=unit,
            index=3,
            title="기댓값 가중합 3",
            statement="확률변수 X가 0,2,4의 값을 각각 1/4, 1/2, 1/4의 확률로 가질 때 E(X)를 구하시오.",
            steps=[
                expr_step("Step 1. 기댓값 식", "0*(1/4) + 2*(1/2) + 4*(1/4)", "값×확률의 합으로 식을 세우세요.", display="0·1/4 + 2·1/2 + 4·1/4"),
                numeric_step("Step 2. 계산", "2", "기댓값을 계산하세요."),
                exact_step("Step 3. 정리", "E(X)=2", "기호와 함께 정리하세요."),
            ],
            final=numeric_step("최종 답", "2", "기댓값을 적으세요."),
            coach_hint="분포표 문제는 값과 확률을 정확히 짝지어 더하는 가중평균 구조가 핵심입니다.",
            expected_outline=["기댓값 식", "계산", "정리", "최종 답"],
            final_prompt="예: 2",
            problem_type="확률분포 기댓값",
            killer_allowed=True,
        ),
        _drill_problem(
            unit=unit,
            index=4,
            title="표본비율 추론 4",
            statement="어떤 조사에서 80명 중 28명이 찬성하였다. 표본비율을 구하시오.",
            steps=[
                expr_step("Step 1. 비율식", "28/80", "표본비율은 찬성 수/전체 수입니다.", display="28/80"),
                expr_step("Step 2. 기약분수", "7/20", "분수를 기약형으로 정리하세요.", display="7/20"),
                exact_step("Step 3. 소수 해석", "0.35", "필요하면 소수로도 해석하세요."),
            ],
            final=expr_step("최종 답", "7/20", "표본비율을 적으세요.", display="7/20"),
            coach_hint="표본비율은 통계 추론의 시작점이므로 분수형과 소수형을 모두 읽을 수 있어야 합니다.",
            expected_outline=["비율식", "기약분수", "해석", "최종 답"],
            final_prompt="예: 7/20",
            problem_type="표본비율",
            killer_allowed=True,
        ),
    ]


def _hard_calc2_seq_limit_openers(unit: dict) -> list[dict]:
    return [
        _drill_problem(
            unit=unit,
            index=1,
            title="유리식 수열 극한 1",
            statement="수열 a_n=(3n^2-2n+1)/(n^2+4)의 극한값을 구하시오.",
            steps=[
                exact_step("Step 1. 최고차항 비교", "3/1", "분자와 분모의 최고차항 계수를 비교하세요."),
                exact_step("Step 2. 극한 연결", "3", "차수가 같으므로 계수의 비로 갑니다."),
                exact_step("Step 3. 정리", "3", "극한값을 정리하세요."),
            ],
            final=numeric_step("최종 답", "3", "극한값을 적으세요."),
            coach_hint="수열의 극한 킬러는 항 하나하나를 보지 말고 가장 큰 차수만 보는 훈련이 중요합니다.",
            expected_outline=["최고차항", "계수의 비", "정리", "최종 답"],
            final_prompt="예: 3",
            problem_type="유리식 수열 극한",
            killer_allowed=True,
        ),
        _drill_problem(
            unit=unit,
            index=2,
            title="무한등비급수 2",
            statement="3-1+1/3-1/9+... 의 합을 구하시오.",
            steps=[
                numeric_step("Step 1. 첫째항", "3", "첫째항을 읽으세요."),
                expr_step("Step 2. 공비", "-1/3", "앞항과 뒷항의 비를 구하세요.", display="-1/3"),
                expr_step("Step 3. 합", "9/4", "S=a/(1-r)을 계산하세요.", display="9/4"),
            ],
            final=expr_step("최종 답", "9/4", "급수의 합을 적으세요.", display="9/4"),
            coach_hint="부호가 번갈아 나오는 등비급수는 공비의 부호까지 끝까지 지켜야 합니다.",
            expected_outline=["첫째항", "공비", "합 공식", "최종 답"],
            final_prompt="예: 9/4",
            problem_type="무한등비급수",
            killer_allowed=True,
        ),
        _drill_problem(
            unit=unit,
            index=3,
            title="점화수열 수렴값 3",
            statement="수열 a1=0, a_(n+1)=a_n/2+1이 수렴한다고 할 때 그 극한값을 구하시오.",
            steps=[
                exact_step("Step 1. 극한 가정", "L=L/2+1", "수렴값을 L이라 두고 점화식을 그대로 쓰세요."),
                expr_step("Step 2. 정리", "L/2=1", "양변을 정리하세요."),
                numeric_step("Step 3. 극한값", "2", "L을 구하세요."),
            ],
            final=numeric_step("최종 답", "2", "극한값을 적으세요."),
            coach_hint="점화수열 극한은 끝없이 계산하지 않고 수렴값 방정식을 세우는 순간 결정됩니다.",
            expected_outline=["L 도입", "방정식 정리", "해 구하기", "최종 답"],
            final_prompt="예: 2",
            problem_type="점화수열 극한",
            killer_allowed=True,
        ),
        _drill_problem(
            unit=unit,
            index=4,
            title="텔레스코핑 구조 4",
            statement="급수 Σ(k=1→∞) (1/k - 1/(k+1))의 합을 구하시오.",
            steps=[
                exact_step("Step 1. 부분합 전개", "1-1/(n+1)", "부분합을 쓰면 중간항이 소거됩니다."),
                exact_step("Step 2. n→∞", "1-0", "1/(n+1)이 0으로 갑니다."),
                numeric_step("Step 3. 합", "1", "무한급수의 합을 구하세요."),
            ],
            final=numeric_step("최종 답", "1", "합을 적으세요."),
            coach_hint="급수 킬러는 더하는 것이 아니라 소거되는 구조를 먼저 보는 문제입니다.",
            expected_outline=["부분합", "극한", "정리", "최종 답"],
            final_prompt="예: 1",
            problem_type="텔레스코핑 급수",
            killer_allowed=True,
        ),
    ]


def _hard_calc2_integral_openers(unit: dict) -> list[dict]:
    return [
        _drill_problem(
            unit=unit,
            index=1,
            title="치환 적분 킬러 1",
            statement="∫ x·e^(x^2) dx를 구하시오.",
            steps=[
                expr_step("Step 1. 치환 준비", "u=x**2", "x^2를 새로운 문자로 보세요.", display="u=x^2"),
                expr_step("Step 2. 적분 변환", "exp(x**2)/2", "du=2x dx를 이용해 1/2를 꺼내세요.", display="e^(x^2)/2"),
                expr_step("Step 3. 정리", "exp(x**2)/2", "결과를 정리하세요.", display="e^(x^2)/2"),
            ],
            final=expr_step("최종 답", "exp(x**2)/2", "부정적분 결과를 적으세요.", display="e^(x^2)/2"),
            coach_hint="적분 킬러는 겉모양이 아니라 미분해서 안쪽이 나오는 구조를 먼저 보는 문제입니다.",
            expected_outline=["치환", "du 반영", "정리", "최종 답"],
            final_prompt="예: exp(x^2)/2 + C",
            problem_type="치환 적분",
            killer_allowed=True,
        ),
        _drill_problem(
            unit=unit,
            index=2,
            title="지수 정적분 2",
            statement="∫(0→log(2)) e^x dx의 값을 구하시오.",
            steps=[
                expr_step("Step 1. 원시함수", "exp(x)", "e^x의 원시함수는 자기 자신입니다.", display="e^x"),
                expr_step("Step 2. 상한-하한", "2-1", "x=log(2), 0을 대입하세요.", display="2-1"),
                numeric_step("Step 3. 계산", "1", "값을 계산하세요."),
            ],
            final=numeric_step("최종 답", "1", "정적분 값을 적으세요."),
            coach_hint="지수 정적분은 원시함수보다 상한 대입값을 정확히 읽는 것이 더 중요합니다.",
            expected_outline=["원시함수", "대입", "계산", "최종 답"],
            final_prompt="예: 1",
            problem_type="지수 정적분",
            killer_allowed=True,
        ),
        _drill_problem(
            unit=unit,
            index=3,
            title="도형 넓이 지수 3",
            statement="y=e^x와 y=1, x=0, x=log(2)로 둘러싸인 도형의 넓이를 구하시오.",
            steps=[
                exact_step("Step 1. 적분식", "∫0→log(2) (exp(x)-1) dx", "위 함수-아래 함수를 적으세요."),
                expr_step("Step 2. 계산", "1-log(2)", "정적분 값을 계산하세요.", display="1-log(2)"),
                expr_step("Step 3. 정리", "1-log(2)", "넓이를 정리하세요.", display="1-log(2)"),
            ],
            final=expr_step("최종 답", "1-log(2)", "넓이를 적으세요.", display="1-log(2)"),
            coach_hint="지수함수 넓이 문제는 구간과 위아래 관계를 먼저 고정하는 것이 중요합니다.",
            expected_outline=["적분식", "정적분", "정리", "최종 답"],
            final_prompt="예: 1-log(2)",
            problem_type="지수함수 넓이",
            killer_allowed=True,
        ),
        _drill_problem(
            unit=unit,
            index=4,
            title="거듭제곱 치환 4",
            statement="∫ (2x+1)^5 dx를 구하시오.",
            steps=[
                expr_step("Step 1. 치환", "u=2*x+1", "안쪽 일차식을 치환하세요.", display="u=2x+1"),
                expr_step("Step 2. 적분 결과", "(2*x+1)**6/12", "du=2dx를 반영해 적분하세요.", display="(2x+1)^6/12"),
                expr_step("Step 3. 정리", "(2*x+1)**6/12", "최종 결과를 정리하세요.", display="(2x+1)^6/12"),
            ],
            final=expr_step("최종 답", "(2*x+1)**6/12", "부정적분 결과를 적으세요.", display="(2x+1)^6/12"),
            coach_hint="안쪽이 일차식인 거듭제곱 적분은 치환과 계수 보정 두 줄이면 끝납니다.",
            expected_outline=["치환", "계수 보정", "정리", "최종 답"],
            final_prompt="예: (2*x+1)^6/12 + C",
            problem_type="거듭제곱 치환 적분",
            killer_allowed=True,
        ),
    ]


def _hard_geometry_conic_openers(unit: dict) -> list[dict]:
    return [
        _drill_problem(
            unit=unit,
            index=1,
            title="포물선 초점 역추론 1",
            statement="포물선 y^2=4px가 점 (4,4)를 지날 때 p의 값을 구하시오.",
            steps=[
                expr_step("Step 1. 점 대입", "4**2 = 4*p*4", "점의 좌표를 식에 대입하세요.", display="16=16p"),
                numeric_step("Step 2. p", "1", "p를 구하세요."),
                numeric_step("Step 3. 정리", "1", "값을 정리하세요."),
            ],
            final=numeric_step("최종 답", "1", "p의 값을 적으세요."),
            coach_hint="포물선 문제는 표준형에 점을 바로 대입해 매개변수를 복구하는 문제가 많습니다.",
            expected_outline=["대입", "매개변수 계산", "정리", "최종 답"],
            final_prompt="예: 1",
            problem_type="포물선 역추론",
            killer_allowed=True,
        ),
        _drill_problem(
            unit=unit,
            index=2,
            title="타원 두 초점 거리",
            statement="타원 x^2/25 + y^2/9 = 1의 초점과 중심 사이의 거리를 구하시오.",
            steps=[
                expr_step("Step 1. a^2-b^2", "25-9", "c^2=a^2-b^2를 적용하세요.", display="25-9"),
                numeric_step("Step 2. c^2", "16", "값을 계산하세요."),
                numeric_step("Step 3. c", "4", "초점거리 c를 구하세요."),
            ],
            final=numeric_step("최종 답", "4", "거리를 적으세요."),
            coach_hint="타원 킬러는 식을 다루기보다 표준형에서 a와 b를 먼저 정확히 읽는 문제입니다.",
            expected_outline=["공식", "c^2", "c 계산", "최종 답"],
            final_prompt="예: 4",
            problem_type="타원 두 초점 거리",
            killer_allowed=True,
        ),
        _drill_problem(
            unit=unit,
            index=3,
            title="쌍곡선 점근선 기울기",
            statement="쌍곡선 x^2/9 - y^2/16 = 1의 점근선의 기울기 중 양수인 값을 구하시오.",
            steps=[
                expr_step("Step 1. 점근선 공식", "4/3", "점근선 기울기는 ±b/a입니다.", display="4/3"),
                expr_step("Step 2. 양수 선택", "4/3", "양수인 기울기를 고르세요.", display="4/3"),
                exact_step("Step 3. 정리", "4/3", "값을 정리하세요."),
            ],
            final=expr_step("최종 답", "4/3", "기울기를 적으세요.", display="4/3"),
            coach_hint="쌍곡선 점근선 문제는 식 전체를 보지 말고 a, b만 바로 읽는 연습이 중요합니다.",
            expected_outline=["공식", "양수 선택", "정리", "최종 답"],
            final_prompt="예: 4/3",
            problem_type="쌍곡선 점근선 기울기",
            killer_allowed=True,
        ),
        _drill_problem(
            unit=unit,
            index=4,
            title="포물선 표준형 비교 4",
            statement="포물선 y^2=8x의 초점거리를 p라 할 때 4p의 값을 구하시오.",
            steps=[
                expr_step("Step 1. 표준형 비교", "4*p=8", "y^2=4px와 비교하세요.", display="4p=8"),
                numeric_step("Step 2. p", "2", "p를 구하세요."),
                numeric_step("Step 3. 4p", "8", "요구한 값을 계산하세요."),
            ],
            final=numeric_step("최종 답", "8", "4p의 값을 적으세요."),
            coach_hint="준선과 초점 문제도 결국 표준형 비교 한 줄에서 출발합니다.",
            expected_outline=["표준형 비교", "p 계산", "요구값", "최종 답"],
            final_prompt="예: 8",
            problem_type="포물선 표준형 비교",
            killer_allowed=True,
        ),
    ]


def _hard_geometry_space_openers(unit: dict) -> list[dict]:
    return [
        _drill_problem(
            unit=unit,
            index=1,
            title="공간 대각선 1",
            statement="직육면체의 세 모서리 길이가 3, 4, 12일 때 공간대각선의 길이를 구하시오.",
            steps=[
                expr_step("Step 1. 거리 공식", "sqrt(3**2 + 4**2 + 12**2)", "직육면체의 공간대각선 공식을 쓰세요.", display="√(3^2+4^2+12^2)"),
                numeric_step("Step 2. 제곱합", "169", "제곱합을 계산하세요."),
                numeric_step("Step 3. 길이", "13", "제곱근을 취하세요."),
            ],
            final=numeric_step("최종 답", "13", "길이를 적으세요."),
            coach_hint="공간도형 킬러도 결국 피타고라스 구조를 두 번 겹쳐 보는 문제인 경우가 많습니다.",
            expected_outline=["공식", "제곱합", "제곱근", "최종 답"],
            final_prompt="예: 13",
            problem_type="공간대각선",
            killer_allowed=True,
        ),
        _drill_problem(
            unit=unit,
            index=2,
            title="공간 중점 거리 2",
            statement="A(0,0,0), B(4,2,6)의 중점을 M이라 할 때 OM의 길이를 구하시오.",
            steps=[
                exact_step("Step 1. 중점", "(2,1,3)", "중점 좌표를 구하세요."),
                expr_step("Step 2. 거리 공식", "sqrt(2**2 + 1**2 + 3**2)", "원점에서의 거리를 구하세요.", display="√(2^2+1^2+3^2)"),
                expr_step("Step 3. 길이", "sqrt(14)", "값을 정리하세요.", display="√14"),
            ],
            final=expr_step("최종 답", "sqrt(14)", "길이를 적으세요.", display="√14"),
            coach_hint="공간 좌표 문제는 좌표를 복구하고 난 뒤에는 평면과 똑같은 거리 구조로 돌아옵니다.",
            expected_outline=["중점", "거리 공식", "정리", "최종 답"],
            final_prompt="예: sqrt(14)",
            problem_type="공간 중점 거리",
            killer_allowed=True,
        ),
        _drill_problem(
            unit=unit,
            index=3,
            title="공간 두 점 거리 3",
            statement="A(1,2,3), B(4,6,3) 사이의 거리를 구하시오.",
            steps=[
                expr_step("Step 1. 좌표 차", "sqrt(3**2 + 4**2 + 0**2)", "좌표 차를 구해 거리 공식을 쓰세요.", display="√(3^2+4^2+0^2)"),
                numeric_step("Step 2. 제곱합", "25", "제곱합을 계산하세요."),
                numeric_step("Step 3. 거리", "5", "길이를 구하세요."),
            ],
            final=numeric_step("최종 답", "5", "거리를 적으세요."),
            coach_hint="z좌표가 같을 때도 공간좌표 공식을 그대로 쓰되 0차항을 놓치지 않는 습관이 중요합니다.",
            expected_outline=["좌표 차", "제곱합", "거리", "최종 답"],
            final_prompt="예: 5",
            problem_type="공간 두 점 거리",
            killer_allowed=True,
        ),
        _drill_problem(
            unit=unit,
            index=4,
            title="공간 내분점 4",
            statement="A(0,0,0), B(6,3,9)를 1:2로 내분하는 점의 좌표의 합을 구하시오.",
            steps=[
                exact_step("Step 1. 내분점", "(2,1,3)", "1:2 내분점 좌표를 구하세요."),
                numeric_step("Step 2. 좌표의 합", "6", "세 좌표를 더하세요."),
                exact_step("Step 3. 정리", "6", "값을 정리하세요."),
            ],
            final=numeric_step("최종 답", "6", "좌표의 합을 적으세요."),
            coach_hint="공간 내분도 평면과 같은 공식이므로 좌표를 하나씩 분리해 계산하면 됩니다.",
            expected_outline=["내분점", "좌표 합", "정리", "최종 답"],
            final_prompt="예: 6",
            problem_type="공간 내분점",
            killer_allowed=True,
        ),
    ]


def _hard_geometry_vector_openers(unit: dict) -> list[dict]:
    return [
        _drill_problem(
            unit=unit,
            index=1,
            title="성분 내적 계산 1",
            statement="벡터 a=(2,-1), b=(3,4)에 대하여 a·b의 값을 구하시오.",
            steps=[
                expr_step("Step 1. 성분 곱", "2*3 + (-1)*4", "대응 성분끼리 곱한 뒤 더하세요.", display="2·3+(-1)·4"),
                numeric_step("Step 2. 계산", "2", "내적을 계산하세요."),
                exact_step("Step 3. 정리", "2", "값을 정리하세요."),
            ],
            final=numeric_step("최종 답", "2", "내적을 적으세요."),
            coach_hint="벡터 킬러는 도형을 그리기 전에 성분 계산으로 바로 갈 수 있는지부터 판단하는 문제입니다.",
            expected_outline=["성분 곱", "합", "정리", "최종 답"],
            final_prompt="예: 2",
            problem_type="성분 내적 계산",
            killer_allowed=True,
        ),
        _drill_problem(
            unit=unit,
            index=2,
            title="수직 조건 2",
            statement="벡터 (k,2)와 (3,-6)이 서로 수직일 때 k의 값을 구하시오.",
            steps=[
                expr_step("Step 1. 수직 조건", "3*k + 2*(-6)", "수직이면 내적이 0입니다.", display="3k-12"),
                exact_step("Step 2. 방정식", "3*k-12=0", "내적=0 방정식을 세우세요."),
                numeric_step("Step 3. k", "4", "k를 구하세요."),
            ],
            final=numeric_step("최종 답", "4", "k의 값을 적으세요."),
            coach_hint="벡터 수직 조건은 도형보다 내적 0 한 줄을 얼마나 빨리 쓰느냐가 핵심입니다.",
            expected_outline=["내적 0", "방정식", "해", "최종 답"],
            final_prompt="예: 4",
            problem_type="벡터 수직 조건",
            killer_allowed=True,
        ),
        _drill_problem(
            unit=unit,
            index=3,
            title="벡터 면적 3",
            statement="점 O(0,0), A(4,1), B(1,5)가 이루는 삼각형 OAB의 넓이를 구하시오.",
            steps=[
                expr_step("Step 1. 행렬식", "abs(4*5 - 1*1)", "평행사변형 넓이를 행렬식으로 구하세요.", display="|4·5-1·1|"),
                numeric_step("Step 2. 평행사변형 넓이", "19", "값을 계산하세요."),
                expr_step("Step 3. 삼각형 넓이", "19/2", "삼각형 넓이는 절반입니다.", display="19/2"),
            ],
            final=expr_step("최종 답", "19/2", "넓이를 적으세요.", display="19/2"),
            coach_hint="벡터 면적형은 좌표를 바로 행렬식으로 넣는 습관이 있으면 계산이 빨라집니다.",
            expected_outline=["행렬식", "평행사변형", "절반", "최종 답"],
            final_prompt="예: 19/2",
            problem_type="벡터 면적",
            killer_allowed=True,
        ),
        _drill_problem(
            unit=unit,
            index=4,
            title="벡터 결합 4",
            statement="a=(1,2), b=(3,-1)일 때 2a-b의 좌표의 합을 구하시오.",
            steps=[
                exact_step("Step 1. 2a", "(2,4)", "벡터 a를 2배 하세요."),
                exact_step("Step 2. 2a-b", "(-1,5)", "성분별로 빼세요."),
                numeric_step("Step 3. 좌표 합", "4", "두 좌표를 더하세요."),
            ],
            final=numeric_step("최종 답", "4", "좌표의 합을 적으세요."),
            coach_hint="벡터 결합 문제는 스칼라배와 뺄셈을 순서대로 성분 계산으로 밀어붙이면 됩니다.",
            expected_outline=["스칼라배", "벡터 결합", "좌표 합", "최종 답"],
            final_prompt="예: 4",
            problem_type="벡터 결합",
            killer_allowed=True,
        ),
    ]


def _hard_breakthrough_openers(unit: dict) -> list[dict]:
    unit_id = unit["id"]
    if unit_id == "common1-polynomial":
        return _hard_common1_polynomial_openers(unit)
    if unit_id == "common1-equation":
        return _hard_common1_equation_openers(unit)
    if unit_id == "common1-counting":
        return _hard_common1_counting_openers(unit)
    if unit_id == "common1-matrix":
        return _hard_common1_matrix_openers(unit)
    if unit_id == "common2-coordinate":
        return _hard_common2_coordinate_openers(unit)
    if unit_id == "common2-set":
        return _hard_common2_set_openers(unit)
    if unit_id == "common2-function":
        return _hard_common2_function_openers(unit)
    if unit_id == "algebra-exp-log":
        return _hard_algebra_exp_log_openers(unit)
    if unit_id == "algebra-trig":
        return _hard_algebra_trig_openers(unit)
    if unit_id == "algebra-sequence":
        return _hard_algebra_sequence_openers(unit)
    if unit_id == "calc1-limit":
        return _hard_calc1_limit_openers(unit)
    if unit_id == "calc1-integral":
        return _hard_calc1_integral_openers(unit)
    if unit_id == "probstat-counting":
        return _hard_probstat_counting_openers(unit)
    if unit_id == "probstat-probability":
        return _hard_probability_openers(unit)
    if unit_id == "probstat-statistics":
        return _hard_statistics_openers(unit)
    if unit_id == "calc2-seq-limit":
        return _hard_calc2_seq_limit_openers(unit)
    if unit_id == "calc2-integral":
        return _hard_calc2_integral_openers(unit)
    if unit_id == "geometry-conic":
        return _hard_geometry_conic_openers(unit)
    if unit_id == "geometry-space":
        return _hard_geometry_space_openers(unit)
    if unit_id == "geometry-vector":
        return _hard_geometry_vector_openers(unit)
    return []


def _algebra_sequence_story_problems(unit: dict) -> list[dict]:
    return [
        _drill_problem(
            unit=unit,
            index=5,
            title="부분합 두 줄 복원",
            statement="어떤 등차수열 {a_n}에 대하여 S_5=35, S_11=143이다. a_12의 값을 구하시오.",
            steps=[
                numeric_step("Step 1. 공차", "2", "두 부분합 식을 소거해 공차를 먼저 복구하세요."),
                numeric_step("Step 2. 첫째항", "3", "S_5=5(a_1+2d)를 이용해 첫째항을 구하세요."),
                numeric_step("Step 3. a_12", "25", "a_12=a_1+11d를 계산하세요."),
            ],
            final=numeric_step("최종 답", "25", "최종 값을 적으세요."),
            coach_hint="부분합 두 개가 주어지면 합 공식을 두 줄 세운 뒤 공차부터 먼저 소거하는 것이 가장 안정적입니다.",
            expected_outline=["공차 복원", "첫째항 복원", "일반항 계산", "최종 답"],
            final_prompt="예: 25",
            problem_type="부분합 두 줄 복원",
            killer_allowed=True,
        ),
        _drill_problem(
            unit=unit,
            index=6,
            title="합과 중간항 연결",
            statement="어떤 등차수열 {a_n}에 대하여 a_3+a_7=28, S_7=91이다. S_12의 값을 구하시오.",
            steps=[
                exact_step("Step 1. 관계식", "a_1+4d=14", "a_3+a_7을 첫째항과 공차로 정리하세요."),
                exact_step("Step 2. 수열 복원", "a_1=10, d=1", "S_7=7(a_1+3d)와 함께 두 식을 풀어 복원하세요."),
                numeric_step("Step 3. S_12", "186", "복원한 등차수열의 합 공식을 적용하세요."),
            ],
            final=numeric_step("최종 답", "186", "최종 값을 적으세요."),
            coach_hint="중간항 둘의 합은 평균을 주는 정보라서, 부분합과 묶이면 첫째항과 공차를 아주 짧게 복원할 수 있습니다.",
            expected_outline=["중간항 관계식", "수열 복원", "부분합 계산", "최종 답"],
            final_prompt="예: 186",
            problem_type="중간항 합과 부분합",
            killer_allowed=True,
        ),
        _drill_problem(
            unit=unit,
            index=7,
            title="음수 부분합에서 일반항 복원",
            statement="어떤 등차수열 {a_n}에 대하여 S_4=-6, S_8=4이다. a_10의 값을 구하시오.",
            steps=[
                numeric_step("Step 1. 공차", "1", "S_8-2S_4를 이용해 공차를 먼저 구하세요."),
                numeric_step("Step 2. 첫째항", "-3", "S_4=4a_1+6d를 이용해 첫째항을 구하세요."),
                numeric_step("Step 3. a_10", "6", "a_10=a_1+9d를 계산하세요."),
            ],
            final=numeric_step("최종 답", "6", "최종 값을 적으세요."),
            coach_hint="합이 음수에서 양수로 바뀌는 문제는 공차의 부호와 크기를 먼저 복원하는 것이 핵심입니다.",
            expected_outline=["공차 복원", "첫째항 복원", "일반항 계산", "최종 답"],
            final_prompt="예: 6",
            problem_type="부호가 바뀌는 부분합 복원",
            killer_allowed=True,
        ),
        _drill_problem(
            unit=unit,
            index=8,
            title="두 항의 합과 총합",
            statement="어떤 등차수열 {a_n}에 대하여 a_2+a_6=26, S_6=69이다. a_15의 값을 구하시오.",
            steps=[
                exact_step("Step 1. 관계식", "a_1+3d=13", "a_2+a_6을 첫째항과 공차로 정리하세요."),
                exact_step("Step 2. 수열 복원", "a_1=4, d=3", "S_6=3(2a_1+5d)와 함께 두 식을 풀어보세요."),
                numeric_step("Step 3. a_15", "46", "a_15=a_1+14d를 계산하세요."),
            ],
            final=numeric_step("최종 답", "46", "최종 값을 적으세요."),
            coach_hint="등차수열 문제는 항 두 개의 합이 주어지면 평균이 몇 번째 항인지 먼저 보는 습관이 좋습니다.",
            expected_outline=["항의 합 정리", "수열 복원", "일반항 계산", "최종 답"],
            final_prompt="예: 46",
            problem_type="두 항의 합과 총합",
            killer_allowed=True,
        ),
        _drill_problem(
            unit=unit,
            index=9,
            title="홀수번째 항의 누적 판정",
            statement="등차수열 2, 5, 8, 11, ... 에서 a_1+a_3+...+a_{2m-1}의 값이 140 이하가 되도록 하는 모든 자연수 m의 값의 합을 구하시오.",
            steps=[
                expr_step("Step 1. 부분합 식", "m*(3*m-1)", "홀수번째 항만 모으면 첫째항이 2, 공차가 6인 새 등차수열의 합이 됩니다.", display="m(3m-1)"),
                numeric_step("Step 2. 가능한 m", "7", "m(3m-1)≤140을 만족하는 최댓값을 구하세요."),
                numeric_step("Step 3. m의 합", "28", "1부터 7까지의 합을 구하세요."),
            ],
            final=numeric_step("최종 답", "28", "최종 값을 적으세요."),
            coach_hint="홀수번째 항만 보이면 원래 수열을 그대로 쓰지 말고, 새로운 등차수열 하나로 다시 보는 것이 핵심입니다.",
            expected_outline=["새 등차수열로 재해석", "부등식 판정", "자연수 합", "최종 답"],
            final_prompt="예: 28",
            problem_type="홀수번째 항 누적 판정",
            killer_allowed=True,
        ),
        _drill_problem(
            unit=unit,
            index=10,
            title="짝수번째 항의 누적 판정",
            statement="등차수열 1, 3, 5, 7, ... 에서 a_2+a_4+...+a_{2m}의 값이 90 미만이 되도록 하는 모든 자연수 m의 값의 합을 구하시오.",
            steps=[
                expr_step("Step 1. 부분합 식", "m*(2*m+1)", "짝수번째 항만 모으면 첫째항이 3, 공차가 4인 새 등차수열의 합이 됩니다.", display="m(2m+1)"),
                numeric_step("Step 2. 가능한 m", "6", "m(2m+1)<90을 만족하는 최댓값을 구하세요."),
                numeric_step("Step 3. m의 합", "21", "1부터 6까지의 합을 구하세요."),
            ],
            final=numeric_step("최종 답", "21", "최종 값을 적으세요."),
            coach_hint="짝수번째 항의 합도 그대로 세지 말고, 첫째항과 공차가 바뀐 새 등차수열로 바꾸면 부등식 하나로 닫힙니다.",
            expected_outline=["짝수항 재해석", "부등식 판정", "자연수 합", "최종 답"],
            final_prompt="예: 21",
            problem_type="짝수번째 항 누적 판정",
            killer_allowed=True,
        ),
        _drill_problem(
            unit=unit,
            index=11,
            title="등비 부분합 복원",
            statement="양의 등비수열 {a_n}에 대하여 S_2=8, S_3=26이다. a_4+a_5의 값을 구하시오.",
            steps=[
                numeric_step("Step 1. 공비", "3", "S_3-S_2=a_3를 이용해 공비를 먼저 찾아보세요."),
                numeric_step("Step 2. 첫째항", "2", "S_2=a_1(1+r)에서 첫째항을 복구하세요."),
                numeric_step("Step 3. a_4+a_5", "216", "복원한 등비수열로 a_4와 a_5를 계산하세요."),
            ],
            final=numeric_step("최종 답", "216", "최종 값을 적으세요."),
            coach_hint="등비수열은 부분합의 차가 곧 항이 된다는 점을 가장 먼저 써야 합니다.",
            expected_outline=["a_3 읽기", "공비 복원", "첫째항 복원", "최종 계산"],
            final_prompt="예: 216",
            problem_type="등비 부분합 복원",
            killer_allowed=True,
        ),
        _drill_problem(
            unit=unit,
            index=12,
            title="두 항 조건으로 등비수열 복원",
            statement="양의 등비수열 {a_n}에 대하여 a_2+a_4=30, a_5=81이다. S_5의 값을 구하시오.",
            steps=[
                numeric_step("Step 1. 공비", "3", "a_5와 a_2+a_4를 비교해 공비를 먼저 결정하세요."),
                numeric_step("Step 2. 첫째항", "1", "a_5=a_1r^4를 이용해 첫째항을 구하세요."),
                numeric_step("Step 3. S_5", "121", "등비수열의 합 공식을 적용하세요."),
            ],
            final=numeric_step("최종 답", "121", "최종 값을 적으세요."),
            coach_hint="등비수열은 항의 합보다 거듭제곱 구조가 더 중요합니다. 가장 높은 항을 기준으로 공비를 먼저 읽어내세요.",
            expected_outline=["공비 판정", "첫째항 복원", "부분합 계산", "최종 답"],
            final_prompt="예: 121",
            problem_type="두 항 조건 등비 복원",
            killer_allowed=True,
        ),
        _drill_problem(
            unit=unit,
            index=13,
            title="무한등비수열과 둘째항",
            statement="양의 무한등비급수의 합이 12이고 둘째항이 3일 때, 첫째항부터 다섯째항까지의 합을 구하시오.",
            steps=[
                exact_step("Step 1. 첫째항과 공비", "a_1=4, r=3/4", "a_2=a_1r, S=a_1/(1-r)를 함께 써서 복원하세요."),
                expr_step("Step 2. 유한합 식", "4*(1-(3/4)**5)/(1-3/4)", "복원한 값을 유한 등비합 공식에 넣으세요.", display="4(1-(3/4)^5)/(1-3/4)"),
                numeric_step("Step 3. S_5", "781/64", "기약분수로 정리하세요."),
            ],
            final=numeric_step("최종 답", "781/64", "최종 값을 적으세요."),
            coach_hint="무한합 정보가 나오면 끝까지 무한급수에 머물지 말고, 첫째항과 공비를 먼저 닫은 뒤 유한합으로 다시 내려오면 됩니다.",
            expected_outline=["무한합 조건 해석", "등비수열 복원", "유한합 계산", "최종 답"],
            final_prompt="예: 781/64",
            problem_type="무한등비에서 유한합",
            killer_allowed=True,
        ),
        _drill_problem(
            unit=unit,
            index=14,
            title="홀수 위치만 모은 등비합",
            statement="등비수열 3, 6, 12, 24, ... 에서 a_1+a_3+a_5+a_7의 값을 구하시오.",
            steps=[
                exact_step("Step 1. 새 등비수열", "3, 12, 48, 192", "홀수번째 항만 모으면 공비가 4인 새로운 등비수열이 됩니다."),
                expr_step("Step 2. 합 공식", "3*(4**4-1)/(4-1)", "새 등비수열의 합 공식을 적용하세요.", display="3(4^4-1)/(4-1)"),
                numeric_step("Step 3. 값", "255", "최종 값을 계산하세요."),
            ],
            final=numeric_step("최종 답", "255", "최종 값을 적으세요."),
            coach_hint="등비수열의 홀수항 문제는 원래 수열을 붙들지 말고 공비가 제곱된 새 수열로 보는 것이 핵심입니다.",
            expected_outline=["부분수열 재구성", "새 공비 확인", "합 공식", "최종 답"],
            final_prompt="예: 255",
            problem_type="홀수 위치 등비합",
            killer_allowed=True,
        ),
        _drill_problem(
            unit=unit,
            index=15,
            title="로그합의 자연수 판정",
            statement="수열 {a_n}의 일반항이 a_n=log_2((n+2)/(n+1))일 때, Σ(k=1~m) a_k의 값이 2 이하의 자연수가 되도록 하는 모든 자연수 m의 값의 합을 구하시오.",
            steps=[
                exact_step("Step 1. 망원합", "Σa_k = log_2((m+2)/2)", "로그의 합을 한 개의 로그로 묶으세요."),
                exact_step("Step 2. 가능한 m", "2, 6", "합이 1 또는 2가 되는 경우를 찾으세요."),
                numeric_step("Step 3. m의 합", "8", "자연수 m의 값을 모두 더하세요."),
            ],
            final=numeric_step("최종 답", "8", "최종 값을 적으세요."),
            coach_hint="로그 수열의 합은 더하는 문제가 아니라 곱하는 문제입니다. 먼저 로그를 하나로 묶어야 자연수 조건이 보입니다.",
            expected_outline=["로그 망원합", "자연수 조건", "가능한 m", "최종 답"],
            final_prompt="예: 8",
            problem_type="로그합 자연수 판정",
            killer_allowed=True,
        ),
        _drill_problem(
            unit=unit,
            index=16,
            title="로그합의 정수 판정",
            statement="수열 {a_n}의 일반항이 a_n=log_3((n+1)/n)일 때, Σ(k=1~m) a_k의 값이 3 이하의 자연수가 되도록 하는 모든 자연수 m의 값의 합을 구하시오.",
            steps=[
                exact_step("Step 1. 망원합", "Σa_k = log_3(m+1)", "로그의 합을 한 개의 로그로 정리하세요."),
                exact_step("Step 2. 가능한 m", "2, 8, 26", "합이 1, 2, 3이 되는 m을 찾으세요."),
                numeric_step("Step 3. m의 합", "36", "세 값을 더하세요."),
            ],
            final=numeric_step("최종 답", "36", "최종 값을 적으세요."),
            coach_hint="밑이 3인 로그합은 마지막에 m+1이 3의 거듭제곱이 되는지를 보는 구조로 끝납니다.",
            expected_outline=["로그 망원합", "거듭제곱 조건", "가능한 m", "최종 답"],
            final_prompt="예: 36",
            problem_type="로그합 정수 판정",
            killer_allowed=True,
        ),
        _drill_problem(
            unit=unit,
            index=17,
            title="유리식 망원합",
            statement="Σ(k=1~10) 2/((k+1)(k+3))의 값을 구하시오.",
            steps=[
                expr_step("Step 1. 부분분수", "1/(k+1) - 1/(k+3)", "각 항을 두 분수의 차로 바꾸세요.", display="1/(k+1)-1/(k+3)"),
                numeric_step("Step 2. 망원합", "35/52", "중간항이 소거되는 구조로 정리하세요."),
                exact_step("Step 3. 기약분수", "35/52", "기약분수로 확인하세요."),
            ],
            final=numeric_step("최종 답", "35/52", "최종 값을 적으세요."),
            coach_hint="유리식 수열의 합은 식을 길게 더하는 문제가 아니라, 부분분수로 찢은 뒤 사라지는 항을 보는 문제입니다.",
            expected_outline=["부분분수 분해", "망원합", "기약분수", "최종 답"],
            final_prompt="예: 35/52",
            problem_type="유리식 망원합",
            killer_allowed=True,
        ),
        _drill_problem(
            unit=unit,
            index=18,
            title="이동된 분모 망원합",
            statement="Σ(k=1~12) 4/(k^2+5k+6)의 값을 구하시오.",
            steps=[
                expr_step("Step 1. 분모 인수분해", "(k+2)(k+3)", "분모를 먼저 인수분해한 뒤 망원합 구조를 찾으세요.", display="(k+2)(k+3)"),
                expr_step("Step 2. 부분분수", "4/(k+2) - 4/(k+3)", "인수분해한 식을 두 분수의 차로 분해하세요.", display="4/(k+2)-4/(k+3)"),
                numeric_step("Step 3. 망원합", "16/15", "남는 처음 항과 마지막 항만 계산하세요."),
            ],
            final=numeric_step("최종 답", "16/15", "최종 값을 적으세요."),
            coach_hint="망원합은 시작 분모가 이동하면 남는 첫 항도 같이 이동한다는 점을 끝까지 챙겨야 합니다.",
            expected_outline=["분모 인수분해", "부분분수 분해", "망원합", "최종 답"],
            final_prompt="예: 16/15",
            problem_type="이동된 분모 망원합",
            killer_allowed=True,
        ),
        _drill_problem(
            unit=unit,
            index=19,
            title="기본 망원합의 끝값 읽기",
            statement="Σ(k=1~15) 1/(k(k+1))의 값을 구하시오.",
            steps=[
                expr_step("Step 1. 부분분수", "1/k - 1/(k+1)", "기본형 망원합으로 분해하세요.", display="1/k-1/(k+1)"),
                numeric_step("Step 2. 망원합", "15/16", "첫 항과 마지막 항만 남기는 구조로 계산하세요."),
                exact_step("Step 3. 기약분수", "15/16", "최종 값을 확인하세요."),
            ],
            final=numeric_step("최종 답", "15/16", "최종 값을 적으세요."),
            coach_hint="망원합 기본형은 중간항을 하나씩 적기보다 처음과 끝에 무엇이 남는지만 빠르게 보는 습관이 중요합니다.",
            expected_outline=["부분분수 분해", "처음·끝 확인", "기약분수", "최종 답"],
            final_prompt="예: 15/16",
            problem_type="기본 망원합",
            killer_allowed=True,
        ),
        _drill_problem(
            unit=unit,
            index=20,
            title="홀수 분모 망원합",
            statement="Σ(k=1~8) 1/((2k-1)(2k+1))의 값을 구하시오.",
            steps=[
                expr_step("Step 1. 부분분수", "1/2*(1/(2*k-1) - 1/(2*k+1))", "홀수 분모 두 칸 차이 구조를 부분분수로 바꾸세요.", display="1/2(1/(2k-1)-1/(2k+1))"),
                numeric_step("Step 2. 망원합", "8/17", "첫 항과 마지막 항만 남도록 정리하세요."),
                exact_step("Step 3. 기약분수", "8/17", "최종 값을 확인하세요."),
            ],
            final=numeric_step("최종 답", "8/17", "최종 값을 적으세요."),
            coach_hint="홀수 분모가 나오면 한 칸이 아니라 두 칸 차이 망원합이라는 점을 먼저 떠올리면 훨씬 빨라집니다.",
            expected_outline=["부분분수 분해", "홀수 구조 소거", "기약분수", "최종 답"],
            final_prompt="예: 8/17",
            problem_type="홀수 분모 망원합",
            killer_allowed=True,
        ),
        _drill_problem(
            unit=unit,
            index=21,
            title="부분합 관계에서 일반항 찾기",
            statement="수열 {a_n}의 첫째항부터 제n항까지의 합을 S_n이라 할 때, 모든 자연수 n에 대하여 S_n=2a_n-n이 성립한다. a_8의 값을 구하시오.",
            steps=[
                numeric_step("Step 1. 첫째항", "1", "n=1을 대입해 a_1을 먼저 구하세요."),
                exact_step("Step 2. 점화식", "a_n = 2*a_(n-1) + 1", "S_n-S_(n-1)=a_n을 이용해 점화식으로 바꾸세요."),
                numeric_step("Step 3. a_8", "255", "점화식을 반복하거나 일반항을 찾아 계산하세요."),
            ],
            final=numeric_step("최종 답", "255", "최종 값을 적으세요."),
            coach_hint="부분합과 일반항의 관계는 바로 빼서 점화식으로 바꾸는 순간부터 풀립니다. S_n에 오래 머무르면 오히려 복잡해집니다.",
            expected_outline=["초기값", "점화식 변환", "일반항 또는 반복", "최종 답"],
            final_prompt="예: 255",
            problem_type="부분합 관계 점화식",
            killer_allowed=True,
        ),
        _drill_problem(
            unit=unit,
            index=22,
            title="부분합 관계와 역수합",
            statement="수열 {a_n}의 첫째항부터 제n항까지의 합을 S_n이라 할 때, 모든 자연수 n에 대하여 S_n=2a_n-n이 성립한다. Σ(k=1~5) 1/(a_k+1)의 값을 구하시오.",
            steps=[
                exact_step("Step 1. 일반항", "a_n=2**n-1", "앞 문제처럼 점화식으로 바꾸어 일반항을 먼저 찾으세요."),
                expr_step("Step 2. 새 합", "1/2 + 1/4 + 1/8 + 1/16 + 1/32", "a_k+1=2^k이므로 등비급수로 바꾸세요.", display="1/2+1/4+1/8+1/16+1/32"),
                numeric_step("Step 3. 값", "31/32", "합을 기약분수로 정리하세요."),
            ],
            final=numeric_step("최종 답", "31/32", "최종 값을 적으세요."),
            coach_hint="부분합 관계 문제는 일반항을 찾은 뒤 원래 합을 다른 수열의 합으로 다시 번역하는 두 번째 전환이 필요합니다.",
            expected_outline=["일반항 복원", "새 등비급수로 번역", "합 계산", "최종 답"],
            final_prompt="예: 31/32",
            problem_type="부분합 관계와 역수합",
            killer_allowed=True,
        ),
        _drill_problem(
            unit=unit,
            index=23,
            title="차가 홀수인 점화식",
            statement="수열 {a_n}이 a_1=2, a_(n+1)=a_n+2n+1 을 만족할 때, S_10의 값을 구하시오.",
            steps=[
                exact_step("Step 1. 일반항", "a_n=n**2+1", "연속한 항의 차가 홀수이므로 제곱수 구조로 일반항을 찾아보세요."),
                expr_step("Step 2. 합 분해", "Σk**2 + 10", "S_10은 제곱수의 합과 상수항의 합으로 분해하세요.", display="1^2+...+10^2+10"),
                numeric_step("Step 3. S_10", "395", "합을 계산하세요."),
            ],
            final=numeric_step("최종 답", "395", "최종 값을 적으세요."),
            coach_hint="차가 1,3,5,...처럼 보이면 바로 제곱수 구조를 떠올리는 감각이 수열 고난도에서 아주 중요합니다.",
            expected_outline=["일반항 추론", "합 분해", "계산", "최종 답"],
            final_prompt="예: 395",
            problem_type="홀수 차 점화식",
            killer_allowed=True,
        ),
        _drill_problem(
            unit=unit,
            index=24,
            title="선형 점화식의 누적합",
            statement="수열 {a_n}이 a_1=2, a_(n+1)=3a_n-2 를 만족할 때, S_6의 값을 구하시오.",
            steps=[
                exact_step("Step 1. 일반항", "a_n=1+3**(n-1)", "상수해를 먼저 보고 등비형으로 바꾸어 일반항을 찾으세요."),
                expr_step("Step 2. 합 분해", "6 + Σ3**(k-1)", "부분합을 상수항 합과 등비수열의 합으로 나누세요.", display="6+(1+3+...+3^5)"),
                numeric_step("Step 3. S_6", "370", "등비수열의 합을 계산해 더하세요."),
            ],
            final=numeric_step("최종 답", "370", "최종 값을 적으세요."),
            coach_hint="선형 점화식은 바로 몇 항을 쓰지 말고, 먼저 상수해를 제거해 등비수열로 바꾸면 훨씬 짧습니다.",
            expected_outline=["상수해 제거", "일반항 복원", "부분합 계산", "최종 답"],
            final_prompt="예: 370",
            problem_type="선형 점화식 누적합",
            killer_allowed=True,
        ),
        _drill_problem(
            unit=unit,
            index=25,
            title="기하형 점화식의 일반항",
            statement="수열 {a_n}이 a_1=1, a_(n+1)=2a_n+1 을 만족할 때, a_8의 값을 구하시오.",
            steps=[
                exact_step("Step 1. 형태 보기", "a_n+1", "양변에 1을 더해 등비형으로 바꾸어 보세요."),
                exact_step("Step 2. 일반항", "a_n=2**n-1", "a_n+1이 공비 2인 등비수열이 됨을 이용하세요."),
                numeric_step("Step 3. a_8", "255", "n=8을 대입하세요."),
            ],
            final=numeric_step("최종 답", "255", "최종 값을 적으세요."),
            coach_hint="점화식이 a_(n+1)=2a_n+1 꼴이면 그대로 반복하지 말고, 상수를 더해 등비수열로 바꾸는 발상이 핵심입니다.",
            expected_outline=["상수 이동", "등비형 변환", "일반항 대입", "최종 답"],
            final_prompt="예: 255",
            problem_type="기하형 점화식 일반항",
            killer_allowed=True,
        ),
        _drill_problem(
            unit=unit,
            index=26,
            title="변형된 점화식의 누적합",
            statement="수열 {a_n}이 a_1=4, a_(n+1)=2a_n-3 을 만족할 때, S_6의 값을 구하시오.",
            steps=[
                exact_step("Step 1. 형태 보기", "a_n-3", "양변에서 3을 빼 등비형으로 바꾸어 보세요."),
                exact_step("Step 2. 일반항", "a_n=3+2**(n-1)", "a_n-3이 공비 2인 등비수열이 됨을 이용하세요."),
                numeric_step("Step 3. S_6", "81", "상수항의 합과 등비수열의 합을 함께 계산하세요."),
            ],
            final=numeric_step("최종 답", "81", "최종 값을 적으세요."),
            coach_hint="점화식 수열은 어느 상수를 더하거나 빼면 등비형이 되는지 먼저 보는 것이 훨씬 강합니다.",
            expected_outline=["상수 이동", "일반항 복원", "부분합 계산", "최종 답"],
            final_prompt="예: 81",
            problem_type="변형 점화식 누적합",
            killer_allowed=True,
        ),
        _drill_problem(
            unit=unit,
            index=27,
            title="부분합이 제곱합인 수열",
            statement="수열 {a_n}의 첫째항부터 제n항까지의 합이 S_n=n(n+1)(2n+1)/6 이다. a_3+a_6+a_9의 값을 구하시오.",
            steps=[
                exact_step("Step 1. 일반항", "a_n=n**2", "S_n-S_(n-1)을 이용해 일반항을 구하세요."),
                exact_step("Step 2. 필요한 항", "9, 36, 81", "a_3, a_6, a_9를 각각 계산하세요."),
                numeric_step("Step 3. 합", "126", "세 값을 더하세요."),
            ],
            final=numeric_step("최종 답", "126", "최종 값을 적으세요."),
            coach_hint="부분합 공식이 바로 주어지면, 합 공식에 머물지 말고 차를 취해 일반항으로 되돌리는 것이 먼저입니다.",
            expected_outline=["일반항 복원", "필요 항 계산", "합 정리", "최종 답"],
            final_prompt="예: 126",
            problem_type="부분합에서 일반항 복원",
            killer_allowed=True,
        ),
        _drill_problem(
            unit=unit,
            index=28,
            title="부분합에서 홀수항만 다시 묶기",
            statement="수열 {a_n}의 첫째항부터 제n항까지의 합이 S_n=n(n+1)(n+2)/3 이다. a_1+a_3+a_5+a_7+a_9의 값을 구하시오.",
            steps=[
                exact_step("Step 1. 일반항", "a_n=n*(n+1)", "S_n-S_(n-1)을 계산해 일반항을 복원하세요."),
                exact_step("Step 2. 홀수항", "2, 12, 30, 56, 90", "필요한 홀수번째 항들을 차례대로 구하세요."),
                numeric_step("Step 3. 합", "190", "다섯 항을 모두 더하세요."),
            ],
            final=numeric_step("최종 답", "190", "최종 값을 적으세요."),
            coach_hint="부분합에서 홀수항만 묻는 문제는 두 번 바꿔야 합니다. 먼저 일반항으로 되돌리고, 그다음 필요한 홀수항만 다시 모으세요.",
            expected_outline=["일반항 복원", "필요 항 계산", "홀수항 합", "최종 답"],
            final_prompt="예: 190",
            problem_type="부분합에서 홀수항 합",
            killer_allowed=True,
        ),
        _drill_problem(
            unit=unit,
            index=29,
            title="등비합의 자연수 판정",
            statement="양의 등비수열 2, 6, 18, ... 의 첫째항부터 제m항까지의 합 S_m이 80 이하가 되도록 하는 모든 자연수 m의 값의 합을 구하시오.",
            steps=[
                exact_step("Step 1. 합 공식", "S_m=3**m-1", "첫째항이 2, 공비가 3인 등비수열의 합을 정리하세요."),
                numeric_step("Step 2. 가능한 m", "4", "3^m-1≤80을 만족하는 최댓값을 구하세요."),
                numeric_step("Step 3. m의 합", "10", "1부터 4까지의 합을 구하세요."),
            ],
            final=numeric_step("최종 답", "10", "최종 값을 적으세요."),
            coach_hint="등비수열의 부등식 판정형은 합 공식까지 정리한 뒤, 결국 거듭제곱의 범위를 읽는 문제로 바뀝니다.",
            expected_outline=["합 공식", "거듭제곱 범위 판정", "자연수 합", "최종 답"],
            final_prompt="예: 10",
            problem_type="등비합 자연수 판정",
            killer_allowed=True,
        ),
        _drill_problem(
            unit=unit,
            index=30,
            title="점화식과 비율 합",
            statement="수열 {a_n}이 a_1=1, a_(n+1)=2a_n+1 을 만족한다. Σ(k=1~7) (a_k+1)/(a_(k+1)+1)의 값을 구하시오.",
            steps=[
                exact_step("Step 1. 일반항", "a_n=2**n-1", "점화식을 등비형으로 바꾸어 일반항을 먼저 구하세요."),
                expr_step("Step 2. 각 항 정리", "1/2", "(a_k+1)/(a_(k+1)+1)을 일반항으로 바꾸면 일정한 값이 됩니다.", display="2^k/2^(k+1)=1/2"),
                numeric_step("Step 3. 합", "7/2", "같은 값이 7번 더해지는 구조로 계산하세요."),
            ],
            final=numeric_step("최종 답", "7/2", "최종 값을 적으세요."),
            coach_hint="점화식 수열의 비율 문제는 일반항을 찾은 뒤 나눗셈 구조가 상수로 접히는지 보는 두 번째 전환이 중요합니다.",
            expected_outline=["일반항 복원", "비율 구조 단순화", "합 계산", "최종 답"],
            final_prompt="예: 7/2",
            problem_type="점화식과 비율 합",
            killer_allowed=True,
        ),
    ]


def _matrix_text(matrix: list[list[int]]) -> str:
    rows = ["[" + ", ".join(str(item) for item in row) + "]" for row in matrix]
    return "[" + ", ".join(rows) + "]"


def _set_text(items: list[int]) -> str:
    return "{" + ",".join(str(item) for item in sorted(items)) + "}"


def _fraction_text(value: Fraction | int) -> str:
    fraction = value if isinstance(value, Fraction) else Fraction(value, 1)
    if fraction.denominator == 1:
        return str(fraction.numerator)
    return f"{fraction.numerator}/{fraction.denominator}"


def _legacy_drill_problems_for_unit(unit: dict) -> list[dict]:
    unit_id = unit["id"]
    problems: list[dict] = list(_hard_breakthrough_openers(unit))

    if unit_id == "common1-polynomial":
        index = len(problems) + 1
        for a in range(1, 7):
            for b in range(-7, 8):
                if b == 0:
                    continue
                coeff_x2 = 2 * b + 1 - a * a
                problems.append(
                    _drill_problem(
                        unit=unit,
                        index=index,
                        title=f"다항식 구조 계수 킬러 {index}",
                        statement=f"(x^2{_signed(a)}x{_signed(b)})(x^2{_signed(-a)}x{_signed(b+1)})를 전개할 때 x^2의 계수를 구하시오.",
                        steps=[
                            expr_step("Step 1. x^2항 후보", f"({b+1})*x**2 + ({b})*x**2 + ({a})*x*(-{a})*x", "x^2를 만드는 항만 고르세요.", display=f"{b+1}x^2{_signed(b)}x^2-a^2x^2"),
                            expr_step("Step 2. 계수 정리", f"({coeff_x2})*x**2", "x^2항 계수만 모으세요.", display=f"{coeff_x2}x^2"),
                            numeric_step("Step 3. 계수", str(coeff_x2), "x^2의 계수를 읽으세요."),
                        ],
                        final=numeric_step("최종 답", str(coeff_x2), "x^2의 계수를 적으세요."),
                        coach_hint="전개 전체를 하지 말고 필요한 차수만 추출하는 것이 뒤쪽 한계돌파의 기본 전략입니다.",
                        expected_outline=["필요 차수 추출", "계수 정리", "계수 읽기", "최종 답"],
                        final_prompt=f"예: {coeff_x2}",
                        problem_type="계수 추출형",
                    )
                )
                index += 1
                if len(problems) >= DRILL_TARGET_PER_UNIT:
                    return problems

    if unit_id == "common1-equation":
        index = len(problems) + 1
        for p in range(-5, 6):
            for q in range(-5, 6):
                if p == 0 or q == 0 or p == q:
                    continue
                sum_roots = p + q
                product_roots = p * q
                answer = p * p + q * q + product_roots
                problems.append(
                    _drill_problem(
                        unit=unit,
                        index=index,
                        title=f"이차방정식 구조 킬러 {index}",
                        statement=f"x^2{_signed(-sum_roots)}x{_signed(product_roots)}=0의 두 근을 α, β라 할 때 α^2+β^2+αβ를 구하시오.",
                        steps=[
                            exact_step("Step 1. 합과 곱", f"α+β={sum_roots}, αβ={product_roots}", "근과 계수의 관계를 먼저 읽으세요."),
                            expr_step("Step 2. 제곱합", f"({sum_roots})**2 - 2*({product_roots})", "α^2+β^2=(α+β)^2-2αβ를 쓰세요."),
                            numeric_step("Step 3. 요구값", str(answer), "α^2+β^2+αβ를 계산하세요."),
                        ],
                        final=numeric_step("최종 답", str(answer), "요구한 값을 적으세요."),
                        coach_hint="이차방정식 뒤쪽 문제는 해를 직접 구하기보다 합과 곱으로 식을 변형하는 문제가 많습니다.",
                        expected_outline=["합·곱 읽기", "제곱합 변형", "요구값 계산", "최종 답"],
                        final_prompt=f"예: {answer}",
                        problem_type="근과 계수 응용",
                    )
                )
                index += 1
                if len(problems) >= DRILL_TARGET_PER_UNIT:
                    return problems

    if unit_id == "common1-counting":
        index = len(problems) + 1
        for a in range(2, 8):
            for b in range(2, 7):
                for c in range(2, 5):
                    total = comb(a, 2) * b * c
                    problems.append(
                        _drill_problem(
                            unit=unit,
                            index=index,
                            title=f"경우의 수 조건 분리 킬러 {index}",
                            statement=f"남학생 {a}명, 여학생 {b}명, 멘토 {c}명 중에서 남학생 2명, 여학생 1명, 멘토 1명을 뽑는 방법의 수를 구하시오.",
                            steps=[
                                exact_step("Step 1. 남학생 선택", f"{a}C2", "남학생 2명을 먼저 고르세요."),
                                numeric_step("Step 2. 여학생·멘토 반영", str(total), "여학생 1명과 멘토 1명 선택까지 곱하세요."),
                                exact_step("Step 3. 해석", f"{total}가지", "경우의 수로 해석하세요."),
                            ],
                            final=numeric_step("최종 답", str(total), "가능한 경우의 수를 적으세요."),
                            coach_hint="뒤쪽 경우의 수는 곱의 법칙만이 아니라 먼저 조합으로 자를 대상을 정확히 고르는 것이 핵심입니다.",
                            expected_outline=["조합 선택", "곱의 법칙", "해석", "최종 답"],
                            final_prompt=f"예: {total}",
                            problem_type="조합-곱 결합",
                            killer_allowed=True,
                        )
                    )
                    index += 1
                    if len(problems) >= DRILL_TARGET_PER_UNIT:
                        return problems

    if unit_id == "common1-matrix":
        index = len(problems) + 1
        for a in range(-3, 4):
            for b in range(-3, 4):
                if a == 0 and b == 0:
                    continue
                trace_value = 2 + 3 * a - b
                problems.append(
                    _drill_problem(
                        unit=unit,
                        index=index,
                        title=f"행렬 곱셈 구조 킬러 {index}",
                        statement=f"A=[[1,{a}],[{b},2]], B=[[2,-1],[1,{a}]]일 때 trace(AB)의 값을 구하시오.",
                        steps=[
                            expr_step("Step 1. (1,1) 성분", f"2 + ({a})", "A의 첫째 행과 B의 첫째 열을 곱하세요.", display=f"2{_signed(a)}"),
                            expr_step("Step 2. (2,2) 성분", f"-({b}) + 2*({a})", "A의 둘째 행과 B의 둘째 열을 곱하세요.", display=f"{-b}{_signed(2*a)}"),
                            numeric_step("Step 3. trace", str(trace_value), "대각성분의 합을 구하세요."),
                        ],
                        final=numeric_step("최종 답", str(trace_value), "trace(AB)를 적으세요."),
                        coach_hint="행렬 한계돌파는 전체 행렬을 다 구하기보다 필요한 성분만 남기는 판단이 중요합니다.",
                        expected_outline=["(1,1) 성분", "(2,2) 성분", "trace", "최종 답"],
                        final_prompt=f"예: {trace_value}",
                        problem_type="행렬 곱 trace",
                    )
                )
                index += 1
                if len(problems) >= DRILL_TARGET_PER_UNIT:
                    return problems

    if unit_id == "common2-coordinate":
        index = len(problems) + 1
        ratios = [(1, 1), (1, 2), (2, 1), (2, 3), (3, 2)]
        for x1 in range(-4, 5, 2):
            for y1 in range(-2, 7, 2):
                x2, y2 = x1 + 6, y1 + 6
                for m, n in ratios:
                    px = (n * x1 + m * x2) // (m + n)
                    py = (n * y1 + m * y2) // (m + n)
                    if (n * x1 + m * x2) % (m + n) or (n * y1 + m * y2) % (m + n):
                        continue
                    slope = m - n
                    intercept = py - slope * px
                    problems.append(
                        _drill_problem(
                            unit=unit,
                            index=index,
                            title=f"좌표-직선 결합 킬러 {index}",
                            statement=f"A({x1},{y1}), B({x2},{y2})를 {m}:{n}으로 내분하는 점을 지나고 기울기가 {slope}인 직선의 y절편을 구하시오.",
                            steps=[
                                exact_step("Step 1. 내분점", f"({px},{py})", "내분점 좌표를 먼저 구하세요."),
                                expr_step("Step 2. 직선식", f"({slope})*x + ({intercept})", "기울기와 한 점으로 직선식을 세우세요.", display=f"y={slope}x{_signed(intercept)}"),
                                numeric_step("Step 3. y절편", str(intercept), "직선의 y절편을 읽으세요."),
                            ],
                            final=numeric_step("최종 답", str(intercept), "y절편을 적으세요."),
                            coach_hint="좌표 킬러는 점을 구한 다음 직선으로 한 번 더 구조를 넘기는 문제가 많습니다.",
                            expected_outline=["내분점", "직선식", "y절편", "최종 답"],
                            final_prompt=f"예: {intercept}",
                            problem_type="내분점-직선 결합",
                        )
                    )
                    index += 1
                    if len(problems) >= DRILL_TARGET_PER_UNIT:
                        return problems

    if unit_id == "common2-set":
        index = len(problems) + 1
        for a_start in range(1, 16):
            a_items = [a_start, a_start + 1, a_start + 2, a_start + 4]
            b_items = [a_start + 1, a_start + 2, a_start + 3, a_start + 5]
            sym_count = len(set(a_items).symmetric_difference(b_items))
            outside = 9 - len(set(a_items).union(b_items))
            for title, statement, answer, kind in [
                (f"집합 대칭차 킬러 {index}", f"U={_set_text(list(range(a_start, a_start + 9)))}, A={_set_text(a_items)}, B={_set_text(b_items)}일 때 n(A△B)를 구하시오.", str(sym_count), "대칭차"),
                (f"집합 여집합 킬러 {index+1}", f"U={_set_text(list(range(a_start, a_start + 9)))}, A={_set_text(a_items)}, B={_set_text(b_items)}일 때 n((A∪B)^c)를 구하시오.", str(outside), "합집합의 여집합"),
            ]:
                problems.append(
                    _drill_problem(
                        unit=unit,
                        index=index,
                        title=title,
                        statement=statement,
                        steps=[
                            exact_step("Step 1. 원소 구조", answer, "겹치는 원소와 빠지는 원소를 먼저 확인하세요."),
                            exact_step("Step 2. 집합 수 세기", answer, "조건에 맞는 원소 수를 세세요."),
                            exact_step("Step 3. 정리", answer, "최종 원소 수를 정리하세요."),
                        ],
                        final=numeric_step("최종 답", answer, "원소 수를 적으세요."),
                        coach_hint="집합 뒤쪽 문제는 집합 자체를 다 쓰기보다 합집합, 교집합, 대칭차의 개수 구조를 보는 편이 빠릅니다.",
                        expected_outline=["원소 구조", "개수 세기", "정리", "최종 답"],
                        final_prompt=f"예: {answer}",
                        problem_type=kind,
                    )
                )
                index += 1
                if len(problems) >= DRILL_TARGET_PER_UNIT:
                    return problems

    if unit_id == "common2-function":
        index = len(problems) + 1
        for a in range(1, 6):
            for b in range(-3, 4):
                for c in range(1, 4):
                    d = a - c
                    t = a - b
                    answer = a * (c * t + d) + b + c * (a * t + b) + d
                    problems.append(
                        _drill_problem(
                            unit=unit,
                            index=index,
                            title=f"합성함수 상호작용 킬러 {index}",
                            statement=f"f(x)={_pretty_math(f'{a}*x+({b})')}, g(x)={_pretty_math(f'{c}*x+({d})')}일 때 f(g({t})) + g(f({t}))의 값을 구하시오.",
                            steps=[
                                numeric_step("Step 1. f(g(t))", str(a * (c * t + d) + b), "g(t)를 먼저 구한 뒤 f에 넣으세요."),
                                numeric_step("Step 2. g(f(t))", str(c * (a * t + b) + d), "f(t)를 먼저 구한 뒤 g에 넣으세요."),
                                numeric_step("Step 3. 합", str(answer), "두 값을 더하세요."),
                            ],
                            final=numeric_step("최종 답", str(answer), "값을 적으세요."),
                            coach_hint="합성함수 뒤쪽 문제는 식 자체보다 어느 함수가 먼저 작동하는지 순서를 끝까지 지키는 것이 핵심입니다.",
                            expected_outline=["f(g(t))", "g(f(t))", "합", "최종 답"],
                            final_prompt=f"예: {answer}",
                            problem_type="합성함수 상호작용",
                        )
                    )
                    index += 1
                    if len(problems) >= DRILL_TARGET_PER_UNIT:
                        return problems

    if unit_id == "algebra-exp-log":
        index = len(problems) + 1
        for base in [2, 3, 5]:
            for r1 in range(0, 4):
                for r2 in range(r1 + 1, r1 + 5):
                    u1 = base**r1
                    u2 = base**r2
                    coefficient = u1 + u2
                    constant = u1 * u2
                    problems.append(
                        _drill_problem(
                            unit=unit,
                            index=index,
                            title=f"지수 치환 킬러 {index}",
                            statement=f"{base}^(2x) - {coefficient}·{base}^x + {constant} = 0을 만족하는 모든 실수 x의 값을 구하시오.",
                            steps=[
                                exact_step("Step 1. 치환", f"u={base}^x", "지수방정식은 먼저 u 치환으로 이차방정식 구조를 만드세요."),
                                solution_step("Step 2. u의 값", [str(u1), str(u2)], "u에 대한 이차방정식을 인수분해해 두 해를 구하세요."),
                                solution_step("Step 3. x의 값", [str(r1), str(r2)], "u={base}^x에서 밑이 같은 거듭제곱을 비교하세요."),
                            ],
                            final=solution_step("최종 답", [str(r1), str(r2)], "x의 값을 빠짐없이 적으세요."),
                            coach_hint="한계돌파 지수 문제는 지수법칙이 아니라 치환 후 이차구조를 먼저 보는 시선이 핵심입니다.",
                            expected_outline=["치환", "u 해 구하기", "x 복원", "최종 답"],
                            final_prompt=f"예: {r1}, {r2}",
                            problem_type="지수 치환 구조",
                            killer_allowed=True,
                        )
                    )
                    index += 1
                    if len(problems) >= DRILL_TARGET_PER_UNIT:
                        return problems

    if unit_id == "algebra-trig":
        index = len(problems) + 1
        triples = [(3, 4, 5), (5, 12, 13), (8, 15, 17), (7, 24, 25), (20, 21, 29)]
        for sin_num, cos_num_abs, hyp in triples:
            for quadrant in [1, 2]:
                cos_num = cos_num_abs if quadrant == 1 else -cos_num_abs
                cos_value = Fraction(cos_num, hyp)
                tan_value = Fraction(sin_num, cos_num)
                answer = tan_value + cos_value
                problems.append(
                    _drill_problem(
                        unit=unit,
                        index=index,
                        title=f"삼각비 구조 킬러 {index}",
                        statement=f"sinθ = {sin_num}/{hyp}이고 θ가 제{quadrant}사분면에 있을 때, tanθ + cosθ의 값을 구하시오.",
                        steps=[
                            numeric_step("Step 1. cosθ", _fraction_text(cos_value), "사분면 조건으로 cosθ의 부호를 먼저 결정하세요."),
                            numeric_step("Step 2. tanθ", _fraction_text(tan_value), "tanθ = sinθ/cosθ 로 연결하세요."),
                            numeric_step("Step 3. 합", _fraction_text(answer), "두 값을 더해 구조를 마무리하세요."),
                        ],
                        final=numeric_step("최종 답", _fraction_text(answer), "최종 값을 적으세요."),
                        coach_hint="삼각함수 킬러는 값을 외우는 것이 아니라 사분면, 부호, 비의 구조를 동시에 고정하는 문제입니다.",
                        expected_outline=["cos 부호 결정", "tan 계산", "합 정리", "최종 답"],
                        final_prompt=f"예: {_fraction_text(answer)}",
                        problem_type="삼각비 부호 구조",
                        killer_allowed=True,
                    )
                )
                index += 1
                if len(problems) >= DRILL_TARGET_PER_UNIT:
                    return problems
        for sin_num_abs, cos_num, hyp in triples:
            for quadrant in [1, 4]:
                sin_num = sin_num_abs if quadrant == 1 else -sin_num_abs
                sin_value = Fraction(sin_num, hyp)
                tan_value = Fraction(sin_num, cos_num)
                answer = sin_value - tan_value
                problems.append(
                    _drill_problem(
                        unit=unit,
                        index=index,
                        title=f"삼각식 결합 킬러 {index}",
                        statement=f"cosθ = {cos_num}/{hyp}이고 θ가 제{quadrant}사분면에 있을 때, sinθ - tanθ의 값을 구하시오.",
                        steps=[
                            numeric_step("Step 1. sinθ", _fraction_text(sin_value), "사분면 조건으로 sinθ의 부호를 결정하세요."),
                            numeric_step("Step 2. tanθ", _fraction_text(tan_value), "tanθ = sinθ/cosθ 를 유지하세요."),
                            numeric_step("Step 3. 차", _fraction_text(answer), "두 값을 빼서 정리하세요."),
                        ],
                        final=numeric_step("최종 답", _fraction_text(answer), "최종 값을 적으세요."),
                        coach_hint="같은 삼각비라도 사분면이 달라지면 부호 전체가 흔들립니다. 첫 줄에서 부호를 고정하세요.",
                        expected_outline=["sin 부호 결정", "tan 계산", "차 정리", "최종 답"],
                        final_prompt=f"예: {_fraction_text(answer)}",
                        problem_type="삼각식 결합",
                        killer_allowed=True,
                    )
                )
                index += 1
                if len(problems) >= DRILL_TARGET_PER_UNIT:
                    return problems
        for sin_num_abs, cos_num_abs, hyp in triples[:3]:
            for quadrant in [1, 3]:
                sign = 1 if quadrant == 1 else -1
                tan_value = Fraction(sign * sin_num_abs, cos_num_abs)
                answer = Fraction(sign * (sin_num_abs + cos_num_abs), hyp)
                problems.append(
                    _drill_problem(
                        unit=unit,
                        index=index,
                        title=f"삼각식 압축 킬러 {index}",
                        statement=f"tanθ = {sign * sin_num_abs}/{cos_num_abs}이고 θ가 제{quadrant}사분면에 있을 때, sinθ + cosθ의 값을 구하시오.",
                        steps=[
                            numeric_step("Step 1. sinθ", _fraction_text(Fraction(sign * sin_num_abs, hyp)), "삼각비 표준삼각형을 복구해 sinθ를 잡으세요."),
                            numeric_step("Step 2. cosθ", _fraction_text(Fraction(sign * cos_num_abs, hyp)), "같은 삼각형에서 cosθ도 같은 부호로 정리하세요."),
                            numeric_step("Step 3. 합", _fraction_text(answer), "sinθ와 cosθ를 더해 마무리하세요."),
                        ],
                        final=numeric_step("최종 답", _fraction_text(answer), "최종 값을 적으세요."),
                        coach_hint="tanθ 하나로 끝내지 말고, 직각삼각형 전체를 복구해 sinθ와 cosθ를 동시에 다시 세우세요.",
                        expected_outline=["sin 복구", "cos 복구", "합 정리", "최종 답"],
                        final_prompt=f"예: {_fraction_text(answer)}",
                        problem_type="삼각식 압축",
                        killer_allowed=True,
                    )
                )
                index += 1
                if len(problems) >= DRILL_TARGET_PER_UNIT:
                    return problems

    if unit_id == "algebra-sequence":
        problems.extend(_algebra_sequence_story_problems(unit))
        return problems[:DRILL_TARGET_PER_UNIT]

    if unit_id == "calc1-limit":
        index = len(problems) + 1
        for a in range(-4, 5):
            if a == 0:
                continue
            for k in range(1, 8):
                answer = 3 * a * a - k * a
                factorized = f"x**2 + ({a})*x + ({a*a})"
                problems.append(
                    _drill_problem(
                        unit=unit,
                        index=index,
                        title=f"유리화 없이 구조 보는 극한 킬러 {index}",
                        statement=f"lim(x→{a}) (((x^3-{a**3})/(x-{a})) - {k}x)의 값을 구하시오.",
                        steps=[
                            expr_step("Step 1. 인수분해 구조", factorized, "x^3-a^3은 (x-a)(x^2+ax+a^2)로 바뀝니다.", display=_pretty_math(factorized)),
                            numeric_step("Step 2. 첫 항 극한", str(3 * a * a), "약분 후 x=a를 대입해 첫 항의 극한을 구하세요."),
                            numeric_step("Step 3. 차 정리", str(answer), "남은 -kx까지 함께 계산하세요."),
                        ],
                        final=numeric_step("최종 답", str(answer), "극한값을 적으세요."),
                        coach_hint="킬러 극한은 직접 대입보다 먼저 약분 가능한 구조를 보는 속도가 더 중요합니다.",
                        expected_outline=["인수분해", "약분 후 대입", "나머지 항 정리", "최종 답"],
                        final_prompt=f"예: {answer}",
                        problem_type="인수분해형 극한",
                        killer_allowed=True,
                    )
                )
                index += 1
                if len(problems) >= DRILL_TARGET_PER_UNIT:
                    return problems

    if unit_id == "calc1-diff":
        tangent_variants = [
            ("x**4 - 4*x**3 + 2*x**2 + 8*x - 3", 1, "고난도 접선 1"),
            ("2*x**4 - 7*x**3 + 3*x**2 + 12*x - 5", 2, "고난도 접선 2"),
            ("x**5 - 5*x**4 + 5*x**3 + 5*x**2 - 6*x + 1", 1, "고난도 접선 3"),
            ("3*x**4 - 8*x**3 - 6*x**2 + 24*x - 7", -1, "고난도 접선 4"),
            ("x**4 - 2*x**3 - 11*x**2 + 12*x + 4", 2, "고난도 접선 5"),
            ("2*x**5 - 5*x**4 - 10*x**3 + 25*x**2 + 6*x - 3", 1, "고난도 접선 6"),
            ("x**4 - 8*x**2 + 12*x - 2", 1, "고난도 접선 7"),
            ("4*x**4 - 4*x**3 - 15*x**2 + 6*x + 8", 2, "고난도 접선 8"),
            ("x**5 - 10*x**3 + 15*x + 4", -1, "고난도 접선 9"),
            ("2*x**4 + x**3 - 12*x**2 + 3*x + 9", 1, "고난도 접선 10"),
            ("x**5 - 3*x**4 - 7*x**3 + 15*x**2 + 2*x - 8", 2, "킬러 접선 11"),
            ("3*x**5 - 5*x**4 - 20*x**3 + 12*x**2 + 18*x - 6", 1, "킬러 접선 12"),
            ("x**6 - 6*x**5 + 9*x**4 + 4*x**3 - 12*x + 3", 1, "킬러 접선 13"),
            ("2*x**6 - 3*x**5 - 15*x**4 + 20*x**3 + 9*x**2 - 12*x + 1", -1, "킬러 접선 14"),
            ("x**5 - 5*x**4 + 2*x**3 + 20*x**2 - 8*x - 11", 3, "킬러 접선 15"),
            ("x**6 - 9*x**4 + 18*x**2 - 5*x + 7", 1, "킬러 접선 16"),
            ("2*x**5 - 8*x**4 - 3*x**3 + 28*x**2 - 10*x + 2", 2, "킬러 접선 17"),
            ("x**6 - 4*x**5 - 14*x**4 + 16*x**3 + 24*x**2 - 9*x + 5", 1, "킬러 접선 18"),
            ("3*x**5 - 15*x**4 + 20*x**3 + 10*x**2 - 18*x + 4", 2, "킬러 접선 19"),
            ("x**6 - 6*x**5 + x**4 + 24*x**3 - 10*x**2 - 16*x + 9", -1, "킬러 접선 20"),
            ("2*x**6 - 12*x**5 + 9*x**4 + 28*x**3 - 30*x**2 + 6*x - 4", 1, "킬러 접선 21"),
            ("x**7 - 7*x**6 + 14*x**5 + 7*x**4 - 35*x**3 + 8*x - 2", 1, "킬러 접선 22"),
            ("3*x**6 - 9*x**5 - 24*x**4 + 44*x**3 + 6*x**2 - 18*x + 5", 2, "킬러 접선 23"),
            ("x**7 - 5*x**6 - 9*x**5 + 45*x**4 - 10*x**3 - 24*x**2 + 9*x + 1", 1, "킬러 접선 24"),
            ("2*x**7 - 7*x**6 - 28*x**5 + 63*x**4 + 8*x**3 - 44*x**2 + 12*x - 5", -1, "킬러 접선 25"),
            ("x**8 - 8*x**7 + 14*x**6 + 28*x**5 - 70*x**4 + 16*x**3 + 24*x**2 - 12*x + 3", 1, "apex 접선 26"),
            ("2*x**8 - 11*x**7 - 12*x**6 + 91*x**5 - 30*x**4 - 84*x**3 + 24*x**2 + 18*x - 7", 2, "apex 접선 27"),
            ("x**9 - 9*x**8 + 18*x**7 + 30*x**6 - 126*x**5 + 20*x**4 + 72*x**3 - 18*x**2 - 10*x + 4", 1, "apex 접선 28"),
            ("2*x**9 - 13*x**8 - 16*x**7 + 140*x**6 - 42*x**5 - 168*x**4 + 40*x**3 + 60*x**2 - 18*x + 5", -1, "apex 접선 29"),
            ("x**10 - 10*x**9 + 25*x**8 + 40*x**7 - 210*x**6 + 35*x**5 + 240*x**4 - 50*x**3 - 90*x**2 + 20*x - 6", 1, "apex 최종 킬러 30"),
        ]
        for expression, point_x, title in tangent_variants:
            problems.append(
                _drill_tangent_problem(
                    unit=unit,
                    index=len(problems) + 1,
                    expression=expression,
                    point_x=point_x,
                    title=title,
                    problem_type="초고난도 접선",
                    killer_allowed=True,
                )
            )
            if len(problems) >= DRILL_TARGET_PER_UNIT:
                return problems[:DRILL_TARGET_PER_UNIT]
        return problems[:DRILL_TARGET_PER_UNIT]

    if unit_id == "calc1-integral":
        index = len(problems) + 1
        for a in range(1, 6):
            for b in range(-3, 5):
                for c in range(1, 4):
                    linear_coeff = b - a * c
                    constant_term = -b * c
                    expanded = f"({a})*x**2 + ({linear_coeff})*x + ({constant_term})"
                    primitive = f"({a}/3)*x**3 + ({linear_coeff}/2)*x**2 + ({constant_term})*x"
                    answer = Fraction(a, 3) + Fraction(linear_coeff, 2) + constant_term
                    problems.append(
                        _drill_problem(
                            unit=unit,
                            index=index,
                            title=f"정적분 구조 킬러 {index}",
                            statement=f"∫_0^1 ({_pretty_math(f'{a}*x+({b})')})({_pretty_math(f'x-({c})')}) dx의 값을 구하시오.",
                            steps=[
                                expr_step("Step 1. 전개", expanded, "먼저 곱을 전개해 항별 적분 구조로 바꾸세요.", display=_pretty_math(expanded)),
                                expr_step("Step 2. 원시함수", primitive, "항별로 적분해 원시함수를 만드세요.", display=_pretty_math(primitive)),
                                numeric_step("Step 3. 구간 대입", _fraction_text(answer), "0과 1을 대입해 값을 계산하세요."),
                            ],
                            final=numeric_step("최종 답", _fraction_text(answer), "정적분 값을 적으세요."),
                            coach_hint="적분 킬러는 적분 자체보다 전개와 정리에서 계산 실수가 많이 나옵니다. 첫 줄 전개를 가장 신중하게 쓰세요.",
                            expected_outline=["전개", "원시함수", "구간 대입", "최종 답"],
                            final_prompt=f"예: {_fraction_text(answer)}",
                            problem_type="정적분 전개형",
                            killer_allowed=True,
                        )
                    )
                    index += 1
                    if len(problems) >= DRILL_TARGET_PER_UNIT:
                        return problems

    if unit_id == "probstat-counting":
        index = len(problems) + 1
        for boys in range(4, 10):
            for girls in range(3, 8):
                case_two_girls = comb(girls, 2) * comb(boys, 2) * 4
                case_three_girls = comb(girls, 3) * boys * 4 if girls >= 3 else 0
                case_four_girls = comb(girls, 4) * 4 if girls >= 4 else 0
                total = case_two_girls + case_three_girls + case_four_girls
                problems.append(
                    _drill_problem(
                        unit=unit,
                        index=index,
                        title=f"경우의 수 분할 킬러 {index}",
                        statement=f"남학생 {boys}명, 여학생 {girls}명 중 4명의 발표팀을 만들되 여학생이 적어도 2명 포함되게 하고, 팀장을 1명 정하는 경우의 수를 구하시오.",
                        steps=[
                            numeric_step("Step 1. 여학생 2명인 경우", str(case_two_girls), "여학생을 정확히 2명 뽑는 경우부터 고정하세요."),
                            numeric_step("Step 2. 여학생 3명 이상인 경우", str(case_three_girls + case_four_girls), "여학생 3명, 4명인 경우를 합치세요."),
                            numeric_step("Step 3. 전체 경우", str(total), "두 경우를 합쳐 최종 경우의 수를 만드세요."),
                        ],
                        final=numeric_step("최종 답", str(total), "경우의 수를 적으세요."),
                        coach_hint="경우의 수 킬러는 공식을 바로 꽂는 문제가 아니라 조건을 케이스로 쪼개는 훈련입니다.",
                        expected_outline=["케이스 1", "케이스 2", "합산", "최종 답"],
                        final_prompt=f"예: {total}",
                        problem_type="조건부 조합 분할",
                        killer_allowed=True,
                    )
                )
                index += 1
                if len(problems) >= DRILL_TARGET_PER_UNIT:
                    return problems

    if unit_id == "probstat-probability":
        index = len(problems) + 1
        for red in range(3, 9):
            for blue in range(2, 8):
                total_cases = comb(red + blue, 3)
                favorable = comb(red, 2) * blue
                value = Fraction(favorable, total_cases)
                problems.append(
                    _drill_problem(
                        unit=unit,
                        index=index,
                        title=f"확률 분자 분모 킬러 {index}",
                        statement=f"빨간 공 {red}개, 파란 공 {blue}개가 들어 있는 주머니에서 공 3개를 동시에 꺼낼 때, 정확히 2개가 빨간 공일 확률을 구하시오.",
                        steps=[
                            numeric_step("Step 1. 전체 경우", str(total_cases), "전체 경우의 수는 조합으로 세세요."),
                            numeric_step("Step 2. 유리한 경우", str(favorable), "빨간 공 2개, 파란 공 1개를 뽑는 경우를 세세요."),
                            numeric_step("Step 3. 확률", _fraction_text(value), "유리한 경우/전체 경우를 기약분수로 정리하세요."),
                        ],
                        final=numeric_step("최종 답", _fraction_text(value), "확률을 적으세요."),
                        coach_hint="고난도 확률은 분자와 분모를 동시에 조합으로 세는 순간 절반이 끝납니다.",
                        expected_outline=["전체 경우", "유리한 경우", "분수 정리", "최종 답"],
                        final_prompt=f"예: {_fraction_text(value)}",
                        problem_type="조합 확률",
                        killer_allowed=True,
                    )
                )
                index += 1
                if len(problems) >= DRILL_TARGET_PER_UNIT:
                    return problems

    if unit_id == "probstat-statistics":
        index = len(problems) + 1
        probs = [(1, 2), (1, 3), (1, 4), (2, 3), (2, 5)]
        for x1 in range(0, 6):
            for x2 in range(6, 13):
                for p_num, p_den in probs:
                    probability = Fraction(p_num, p_den)
                    complement = 1 - probability
                    expectation = Fraction(x1) * probability + Fraction(x2) * complement
                    square_expectation = Fraction(x1 * x1) * probability + Fraction(x2 * x2) * complement
                    variance_x = square_expectation - expectation * expectation
                    variance_y = 4 * variance_x
                    problems.append(
                        _drill_problem(
                            unit=unit,
                            index=index,
                            title=f"분산 변환 킬러 {index}",
                            statement=f"확률변수 X가 {x1}을 확률 {p_num}/{p_den}, {x2}를 확률 {p_den - p_num}/{p_den}로 가진다. Y=2X-1일 때 V(Y)를 구하시오.",
                            steps=[
                                numeric_step("Step 1. E(X)", _fraction_text(expectation), "먼저 확률변수 X의 기댓값을 계산하세요."),
                                numeric_step("Step 2. V(X)", _fraction_text(variance_x), "E(X^2)-[E(X)]^2로 분산을 구하세요."),
                                numeric_step("Step 3. V(Y)", _fraction_text(variance_y), "Y=2X-1이면 분산은 4배가 됩니다."),
                            ],
                            final=numeric_step("최종 답", _fraction_text(variance_y), "분산을 적으세요."),
                            coach_hint="통계 킬러는 평균을 구하고 끝내지 않습니다. E(X), E(X^2), 분산 변환까지 한 번에 이어야 합니다.",
                            expected_outline=["기댓값", "원래 분산", "변환 후 분산", "최종 답"],
                            final_prompt=f"예: {_fraction_text(variance_y)}",
                            problem_type="분산 변환",
                            killer_allowed=True,
                        )
                    )
                    index += 1
                    if len(problems) >= DRILL_TARGET_PER_UNIT:
                        return problems

    if unit_id == "calc2-seq-limit":
        index = len(problems) + 1
        for a in range(1, 10):
            for b in range(-4, 5):
                answer = Fraction(a, 2)
                problems.append(
                    _drill_problem(
                        unit=unit,
                        index=index,
                        title=f"루트 수열 극한 킬러 {index}",
                        statement=f"lim(n→∞) n(√(n^2 + {a}n{_signed(b)}) - n)의 값을 구하시오.",
                        steps=[
                            expr_step("Step 1. 유리화", f"n*(({a})*n + ({b}))/(sqrt(n**2 + ({a})*n + ({b})) + n)", "켤레를 곱해 루트 차를 유리화하세요."),
                            exact_step("Step 2. 분모의 성장", "2n", "분모는 n으로 묶으면 결국 2n에 가까워집니다."),
                            numeric_step("Step 3. 극한값", _fraction_text(answer), "최고차항만 남기면 a/2 구조가 남습니다."),
                        ],
                        final=numeric_step("최종 답", _fraction_text(answer), "극한값을 적으세요."),
                        coach_hint="수열 극한 킬러는 공식이 아니라 유리화 뒤에 분모의 성장률을 읽는 문제가 많습니다.",
                        expected_outline=["유리화", "분모 성장 판단", "계수 비교", "최종 답"],
                        final_prompt=f"예: {_fraction_text(answer)}",
                        problem_type="유리화형 수열 극한",
                        killer_allowed=True,
                    )
                )
                index += 1
                if len(problems) >= DRILL_TARGET_PER_UNIT:
                    return problems

    if unit_id == "calc2-diff":
        tangent_variants = [
            ("exp(x) + x**3 - 2*x", 0, "고난도 지수 접선 1"),
            ("exp(2*x-1) + x**4 - 3*x", 1, "고난도 지수 접선 2"),
            ("exp(x+1) + 2*x**4 - 4*x**2 + 1", 0, "고난도 지수 접선 3"),
            ("exp(3*x) - x**5 + 5*x", 1, "고난도 지수 접선 4"),
            ("exp(2*x+1) + x**5 - 5*x**3 + 4*x", 0, "고난도 지수 접선 5"),
            ("exp(x) + x**6 - 3*x**4 + x", 1, "고난도 지수 접선 6"),
            ("exp(2*x) + 2*x**5 - 5*x**2 + 3", 0, "고난도 지수 접선 7"),
            ("exp(3*x-2) + x**6 - 6*x**3 + 2", 1, "고난도 지수 접선 8"),
            ("exp(x-1) + x**7 - 7*x**2 + 5", 0, "고난도 지수 접선 9"),
            ("exp(2*x) + 3*x**6 - 4*x**4 + 2*x", 1, "고난도 지수 접선 10"),
            ("exp(3*x) + x**7 - 7*x**5 + 8*x**2 - 3", 0, "킬러 지수 접선 11"),
            ("exp(2*x+1) + 2*x**7 - 5*x**6 - 3*x**3 + 9*x", 1, "킬러 지수 접선 12"),
            ("exp(4*x-1) + x**8 - 8*x**4 + 6*x - 2", 0, "킬러 지수 접선 13"),
            ("exp(3*x) + 3*x**7 - 12*x**5 + 7*x**2 + 4", 1, "킬러 지수 접선 14"),
            ("exp(2*x) + x**8 - 4*x**7 - 6*x**4 + 10*x**2 - 5", 0, "킬러 지수 접선 15"),
            ("exp(5*x-2) + 2*x**8 - 9*x**6 + 3*x**3 + x - 1", 1, "킬러 지수 접선 16"),
            ("exp(4*x) + x**9 - 9*x**5 + 4*x**3 - 6*x", 0, "킬러 지수 접선 17"),
            ("exp(3*x+1) + 3*x**8 - 6*x**7 - 12*x**4 + 9*x**2 + 2", 1, "킬러 지수 접선 18"),
            ("exp(2*x-3) + x**9 - 3*x**8 - 10*x**5 + 18*x**2 - 7", 0, "킬러 지수 접선 19"),
            ("exp(4*x) + 2*x**9 - 8*x**7 - 5*x**4 + 14*x - 3", 1, "킬러 지수 접선 20"),
            ("exp(5*x) + x**10 - 10*x**6 + 5*x**4 - 8*x + 2", 0, "킬러 지수 접선 21"),
            ("exp(4*x-2) + 2*x**10 - 11*x**8 - 6*x**5 + 15*x**3 - 4", 1, "킬러 지수 접선 22"),
            ("exp(3*x+2) + x**11 - 12*x**7 + 6*x**5 + 10*x**2 - 5", 0, "킬러 지수 접선 23"),
            ("exp(5*x-1) + 3*x**10 - 5*x**9 - 14*x**6 + 18*x**4 - 6*x", 1, "킬러 지수 접선 24"),
            ("exp(6*x) + x**11 - 4*x**10 - 15*x**7 + 24*x**5 - 8*x**2 + 3", 0, "킬러 지수 접선 25"),
            ("exp(5*x+1) + 2*x**12 - 13*x**9 - 8*x**6 + 30*x**4 - 10*x + 1", 1, "apex 지수 접선 26"),
            ("exp(6*x-2) + x**12 - 6*x**11 - 18*x**8 + 42*x**6 - 12*x**3 + 4", 0, "apex 지수 접선 27"),
            ("exp(4*x+3) + 3*x**12 - 7*x**10 - 21*x**7 + 45*x**5 - 15*x**2 + 2", 1, "apex 지수 접선 28"),
            ("exp(6*x) + 2*x**13 - 15*x**11 - 10*x**8 + 60*x**6 - 18*x**3 + 5", 0, "apex 지수 접선 29"),
            ("exp(7*x-1) + x**14 - 14*x**12 + 28*x**9 + 21*x**6 - 70*x**4 + 20*x - 4", 1, "apex 최종 킬러 30"),
        ]
        for expression, point_x, title in tangent_variants:
            problems.append(
                _drill_tangent_problem(
                    unit=unit,
                    index=len(problems) + 1,
                    expression=expression,
                    point_x=point_x,
                    title=title,
                    problem_type="초고난도 지수 접선",
                    killer_allowed=True,
                )
            )
            if len(problems) >= DRILL_TARGET_PER_UNIT:
                return problems

    if unit_id == "calc2-integral":
        index = len(problems) + 1
        for a in range(1, 6):
            for b in range(1, 7):
                final = f"exp({a + b}) - 1"
                problems.append(
                    _drill_problem(
                        unit=unit,
                        index=index,
                        title=f"치환 적분 킬러 {index}",
                        statement=f"∫_0^1 ({2 * a}x+{b})e^({_pretty_math(f'{a}*x**2+{b}*x')}) dx의 값을 구하시오.",
                        steps=[
                            exact_step("Step 1. 치환", f"u={a}x^2+{b}x", "지수 안을 u로 두면 미분이 앞의 계수와 맞물립니다."),
                            exact_step("Step 2. 구간 변환", f"0→{a + b}", "x=0,1을 대입해 u의 구간을 바꾸세요."),
                            expr_step("Step 3. 적분값", final, "∫e^u du = e^u 를 적용해 정리하세요.", display=final),
                        ],
                        final=expr_step("최종 답", final, "적분값을 적으세요.", display=final),
                        coach_hint="적분 킬러에서는 치환 자체보다 구간이 함께 바뀐다는 사실을 놓치면 바로 무너집니다.",
                        expected_outline=["치환", "구간 변환", "지수 적분 정리", "최종 답"],
                        final_prompt=f"예: {final}",
                        problem_type="치환 정적분",
                        killer_allowed=True,
                    )
                )
                index += 1
                if len(problems) >= DRILL_TARGET_PER_UNIT:
                    return problems

    if unit_id == "geometry-conic":
        index = len(problems) + 1
        ellipse_pairs = [(5, 3), (5, 4), (10, 6), (10, 8), (13, 5), (13, 12), (17, 8), (17, 15), (25, 7), (25, 24), (15, 9), (15, 12), (26, 10)]
        hyperbola_pairs = [(3, 5), (4, 5), (5, 13), (8, 17), (7, 25), (12, 13), (9, 15), (15, 17), (20, 29), (11, 61), (24, 25), (6, 10), (10, 26)]
        for a, c in ellipse_pairs:
            b_sq = a * a - c * c
            problems.append(
                _drill_problem(
                    unit=unit,
                    index=index,
                    title=f"타원 구조 복원 킬러 {index}",
                    statement=f"장축의 꼭짓점이 (±{a},0), 초점이 (±{c},0)인 타원에 대하여 짧은축의 제곱 b^2의 값을 구하시오.",
                    steps=[
                        numeric_step("Step 1. a^2", str(a * a), "장축의 꼭짓점으로부터 a를 먼저 읽으세요."),
                        numeric_step("Step 2. c^2", str(c * c), "초점으로부터 c를 읽으세요."),
                        numeric_step("Step 3. b^2", str(b_sq), "타원에서는 b^2=a^2-c^2 입니다."),
                    ],
                    final=numeric_step("최종 답", str(b_sq), "b^2의 값을 적으세요."),
                    coach_hint="이차곡선 킬러는 방정식을 바로 쓰기보다 a, b, c의 관계를 먼저 판정하는 문제입니다.",
                    expected_outline=["a 추출", "c 추출", "관계식 적용", "최종 답"],
                    final_prompt=f"예: {b_sq}",
                    problem_type="타원 구조 복원",
                    killer_allowed=True,
                )
            )
            index += 1
            if len(problems) >= DRILL_TARGET_PER_UNIT:
                return problems
        for a, c in hyperbola_pairs:
            b_sq = c * c - a * a
            problems.append(
                _drill_problem(
                    unit=unit,
                    index=index,
                    title=f"쌍곡선 구조 복원 킬러 {index}",
                    statement=f"실축의 꼭짓점이 (±{a},0), 초점이 (±{c},0)인 쌍곡선에 대하여 b^2의 값을 구하시오.",
                    steps=[
                        numeric_step("Step 1. a^2", str(a * a), "꼭짓점에서 a를 읽으세요."),
                        numeric_step("Step 2. c^2", str(c * c), "초점에서 c를 읽으세요."),
                        numeric_step("Step 3. b^2", str(b_sq), "쌍곡선에서는 c^2=a^2+b^2 입니다."),
                    ],
                    final=numeric_step("최종 답", str(b_sq), "b^2의 값을 적으세요."),
                    coach_hint="타원과 쌍곡선은 c^2 관계의 부호가 바뀝니다. 문제를 읽자마자 곡선 종류를 먼저 고정하세요.",
                    expected_outline=["a 추출", "c 추출", "관계식 적용", "최종 답"],
                    final_prompt=f"예: {b_sq}",
                    problem_type="쌍곡선 구조 복원",
                    killer_allowed=True,
                )
            )
            index += 1
            if len(problems) >= DRILL_TARGET_PER_UNIT:
                return problems

    if unit_id == "geometry-space":
        index = len(problems) + 1
        for a in range(2, 9):
            for b in range(3, 9):
                for c in range(4, 10):
                    answer = Fraction(a * b * c, 6)
                    problems.append(
                        _drill_problem(
                            unit=unit,
                            index=index,
                            title=f"사면체 부피 킬러 {index}",
                            statement=f"O(0,0,0), A({a},0,0), B(0,{b},0), C(0,0,{c})가 이룬 사면체 OABC의 부피를 구하시오.",
                            steps=[
                                numeric_step("Step 1. 밑면 넓이", _fraction_text(Fraction(a * b, 2)), "△OAB의 넓이를 먼저 구하세요."),
                                numeric_step("Step 2. 높이", str(c), "점 C의 z좌표가 밑면 OAB에 대한 높이입니다."),
                                numeric_step("Step 3. 부피", _fraction_text(answer), "사면체 부피 = 밑면넓이×높이/3 입니다."),
                            ],
                            final=numeric_step("최종 답", _fraction_text(answer), "사면체의 부피를 적으세요."),
                            coach_hint="공간도형 킬러는 거리보다 부피와 단면으로 구조를 바꾸는 문제가 훨씬 많습니다.",
                            expected_outline=["밑면 넓이", "높이", "부피", "최종 답"],
                            final_prompt=f"예: {_fraction_text(answer)}",
                            problem_type="공간도형 부피",
                            killer_allowed=True,
                        )
                    )
                    index += 1
                    if len(problems) >= DRILL_TARGET_PER_UNIT:
                        return problems

    if unit_id == "geometry-vector":
        index = len(problems) + 1
        for a in range(-3, 5):
            for b in range(-3, 5):
                for c in range(-2, 5):
                    d = c + 2
                    first_x = 2 * a - c
                    first_y = 2 * b - d
                    second_x = a + c
                    second_y = b + d
                    result = first_x * second_x + first_y * second_y
                    problems.append(
                        _drill_problem(
                            unit=unit,
                            index=index,
                            title=f"벡터 내적 킬러 {index}",
                            statement=f"벡터 a=({a},{b}), b=({c},{d})에 대하여 (2a-b)·(a+b)의 값을 구하시오.",
                            steps=[
                                exact_step("Step 1. 2a-b", f"({first_x},{first_y})", "먼저 2a-b의 성분을 구하세요."),
                                exact_step("Step 2. a+b", f"({second_x},{second_y})", "다음으로 a+b의 성분을 구하세요."),
                                numeric_step("Step 3. 내적", str(result), "대응 성분끼리 곱해 더하세요."),
                            ],
                            final=numeric_step("최종 답", str(result), "내적 값을 적으세요."),
                            coach_hint="벡터 킬러는 덧셈 자체보다 여러 벡터식을 먼저 정리한 뒤 마지막에 내적으로 접는 경우가 많습니다.",
                            expected_outline=["2a-b 계산", "a+b 계산", "내적 정리", "최종 답"],
                            final_prompt=f"예: {result}",
                            problem_type="벡터식 내적",
                            killer_allowed=True,
                        )
                    )
                    index += 1
                    if len(problems) >= DRILL_TARGET_PER_UNIT:
                        return problems

    return problems


def _common1_polynomial_killer_bank(unit: dict, start_index: int) -> list[dict]:
    problems: list[dict] = []
    index = start_index

    remainder_sum = 4
    remainder_at_two = 11
    a = remainder_at_two - remainder_sum
    b = remainder_sum - a
    answer = a - b
    problems.append(
        _drill_problem(
            unit=unit,
            index=index,
            title="이차식 나머지 복원",
            statement="다항식 P(x)를 x^2-3x+2로 나눈 나머지가 ax+b이고, P(1)=4, P(2)=11일 때 a-b의 값을 구하시오.",
            steps=[
                exact_step("Step 1. 나머지 조건", "a+b=4, 2a+b=11", "나머지는 x=1, 2에서 P(x)와 같은 값을 가집니다."),
                exact_step("Step 2. a, b 복원", "a=7, b=-3", "연립방정식을 풀어 a와 b를 구하세요."),
                numeric_step("Step 3. a-b", str(answer), "복원한 값을 이용해 차를 계산하세요."),
            ],
            final=numeric_step("최종 답", str(answer), "최종 값을 적으세요."),
            coach_hint="나머지가 일차식이면 두 점의 함수값만으로 바로 복원할 수 있습니다.",
            expected_outline=["나머지 조건 읽기", "연립해서 복원", "요구값 계산", "최종 답"],
            final_prompt="",
            problem_type="이차식 나머지 복원",
            killer_allowed=True,
        )
    )
    index += 1

    pal_a = 11
    pal_b = -24
    pal_answer = pal_a + pal_b
    problems.append(
        _drill_problem(
            unit=unit,
            index=index,
            title="대칭계수 조건 복원",
            statement="다항식 P(x)=x^4+ax^3+bx^2+ax+1이 x-1을 인수로 가지고 P(2)=31일 때 a+b의 값을 구하시오.",
            steps=[
                exact_step("Step 1. 인수 조건", "2a+b=-2", "P(1)=0을 이용해 첫 번째 관계식을 만드세요."),
                exact_step("Step 2. 대입 조건", "5a+2b=7", "P(2)=31을 이용해 두 번째 관계식을 만드세요."),
                exact_step("Step 3. a+b", str(pal_answer), "두 식을 풀어 a+b를 구하세요."),
            ],
            final=numeric_step("최종 답", str(pal_answer), "최종 값을 적으세요."),
            coach_hint="대칭계수형 다항식은 P(1), P(-1), P(2) 같은 특정 값이 계수 복원으로 곧바로 이어집니다.",
            expected_outline=["P(1) 조건", "P(2) 조건", "계수합 계산", "최종 답"],
            final_prompt="",
            problem_type="대칭계수 복원",
            killer_allowed=True,
        )
    )
    index += 1

    identity_answer = 1
    problems.append(
        _drill_problem(
            unit=unit,
            index=index,
            title="항등식 계수 비교",
            statement="(x^2+ax+b)(x-1)=x^3+2x^2-5x+2가 항상 성립할 때 a+b의 값을 구하시오.",
            steps=[
                exact_step("Step 1. 전개 구조", "x^3+(a-1)x^2+(b-a)x-b", "좌변을 x의 차수별로 정리하세요."),
                exact_step("Step 2. 계수 비교", "a=3, b=-2", "같은 차수의 계수를 비교해 a, b를 구하세요."),
                numeric_step("Step 3. a+b", str(identity_answer), "계수의 합을 계산하세요."),
            ],
            final=numeric_step("최종 답", str(identity_answer), "최종 값을 적으세요."),
            coach_hint="항등식은 식을 많이 쓰는 문제가 아니라, 차수별 계수를 정확히 정리하는 문제입니다.",
            expected_outline=["전개", "계수 비교", "계수합", "최종 답"],
            final_prompt="",
            problem_type="항등식 계수 비교",
            killer_allowed=True,
        )
    )
    index += 1

    product_a = -12
    product_b = 12
    product_answer = product_a * product_a + product_b
    problems.append(
        _drill_problem(
            unit=unit,
            index=index,
            title="곱다항식의 이차식 나머지",
            statement="P(x)=x^2+3x-4, Q(x)=x^2-x-6일 때 P(x)Q(x)를 x^2-1로 나눈 나머지가 ax+b라 하자. a^2+b의 값을 구하시오.",
            steps=[
                exact_step("Step 1. x=±1 값", "R(1)=0, R(-1)=24", "x^2-1의 나머지는 x=1, -1에서 원래 식과 같은 값을 가집니다."),
                exact_step("Step 2. 나머지 복원", "a=-12, b=12", "a+b=0, -a+b=24를 풀어 나머지를 복원하세요."),
                numeric_step("Step 3. a^2+b", str(product_answer), "복원한 나머지의 계수로 계산하세요."),
            ],
            final=numeric_step("최종 답", str(product_answer), "최종 값을 적으세요."),
            coach_hint="곱다항식도 나머지 자체를 계산하려 들지 말고, 먼저 나머지식의 값을 잡는 것이 빠릅니다.",
            expected_outline=["특정값 계산", "나머지 복원", "계수식 계산", "최종 답"],
            final_prompt="",
            problem_type="곱다항식 나머지",
            killer_allowed=True,
        )
    )
    index += 1

    factor_a = -1
    factor_b = 5
    factor_answer = factor_a + factor_b
    problems.append(
        _drill_problem(
            unit=unit,
            index=index,
            title="이차인수 조건 계수 복원",
            statement="다항식 x^4-3x^3+ax^2+bx+2가 x^2-x-2로 나누어떨어질 때 a+b의 값을 구하시오.",
            steps=[
                exact_step("Step 1. 인수 조건", "2a+b=3, a-b=-6", "x^2-x-2=(x-2)(x+1)이므로 x=2, -1을 대입하세요."),
                exact_step("Step 2. a, b 복원", "a=-1, b=5", "두 식을 연립해 계수를 복원하세요."),
                numeric_step("Step 3. a+b", str(factor_answer), "복원한 계수의 합을 구하세요."),
            ],
            final=numeric_step("최종 답", str(factor_answer), "최종 값을 적으세요."),
            coach_hint="이차인수가 보이면 곧바로 두 근을 읽어 대입하는 식으로 바뀝니다.",
            expected_outline=["근 대입", "계수 복원", "합 계산", "최종 답"],
            final_prompt="",
            problem_type="이차인수 계수 복원",
            killer_allowed=True,
        )
    )
    index += 1

    shift_a = 4
    shift_b = 1
    shift_answer = 2 * shift_a + shift_b
    problems.append(
        _drill_problem(
            unit=unit,
            index=index,
            title="이동된 다항식의 나머지",
            statement="다항식 P(x)를 x-1로 나눈 나머지가 1, x-2로 나눈 나머지가 5이다. Q(x)=P(x+1)을 x(x-1)으로 나눈 나머지가 ax+b일 때 2a+b의 값을 구하시오.",
            steps=[
                exact_step("Step 1. 변환된 값", "Q(0)=1, Q(1)=5", "Q(0)=P(1), Q(1)=P(2)를 이용하세요."),
                exact_step("Step 2. 나머지 복원", "a=4, b=1", "나머지 ax+b가 두 점을 지나도록 복원하세요."),
                numeric_step("Step 3. 2a+b", str(shift_answer), "요구한 식의 값을 계산하세요."),
            ],
            final=numeric_step("최종 답", str(shift_answer), "최종 값을 적으세요."),
            coach_hint="합성된 다항식은 대입점이 어디로 이동하는지 먼저 적는 순간부터 풀립니다.",
            expected_outline=["변환 대입", "나머지 복원", "계수식 계산", "최종 답"],
            final_prompt="",
            problem_type="이동 다항식 나머지",
            killer_allowed=True,
        )
    )
    index += 1

    coeff_answer = 1
    problems.append(
        _drill_problem(
            unit=unit,
            index=index,
            title="다항식 세제곱 결합의 계수",
            statement="(x-1)^2(x+2)^3을 전개할 때 x^3의 계수를 구하시오.",
            steps=[
                expr_step("Step 1. 두 다항식 전개", "(x**2-2*x+1)*(x**3+6*x**2+12*x+8)", "필요한 두 인수를 먼저 전개하세요.", display="(x^2-2x+1)(x^3+6x^2+12x+8)"),
                exact_step("Step 2. x^3항 후보", "12-12+1", "x^3을 만드는 항만 골라 계수를 더하세요."),
                numeric_step("Step 3. 계수", str(coeff_answer), "x^3의 계수를 읽으세요."),
            ],
            final=numeric_step("최종 답", str(coeff_answer), "최종 값을 적으세요."),
            coach_hint="전개 전체를 하지 말고 필요한 차수만 남기는 판단이 뒤쪽 다항식 킬러의 핵심입니다.",
            expected_outline=["전개 구조", "필요 차수 추출", "계수 합", "최종 답"],
            final_prompt="",
            problem_type="세제곱 결합 계수",
            killer_allowed=True,
        )
    )
    index += 1

    quotient_answer = 3
    problems.append(
        _drill_problem(
            unit=unit,
            index=index,
            title="몫과 나머지의 역추론",
            statement="다항식 P(x)를 x-2로 나누면 몫이 x^2+ax+b, 나머지가 3이다. 또한 P(1)=1, P(0)=-1일 때 a^2+b의 값을 구하시오.",
            steps=[
                exact_step("Step 1. 나눗셈식", "P(x)=(x-2)(x^2+ax+b)+3", "몫과 나머지를 이용해 P(x)를 다시 쓰세요."),
                exact_step("Step 2. a, b 복원", "a=-1, b=2", "P(1)=1, P(0)=-1을 대입해 연립하세요."),
                numeric_step("Step 3. a^2+b", str(quotient_answer), "요구한 값을 계산하세요."),
            ],
            final=numeric_step("최종 답", str(quotient_answer), "최종 값을 적으세요."),
            coach_hint="몫이 주어지면 원래 다항식을 다시 세운 뒤 특정 값을 넣어 복원하는 흐름이 중요합니다.",
            expected_outline=["원래 식 복원", "조건 대입", "요구값 계산", "최종 답"],
            final_prompt="",
            problem_type="몫과 나머지 역추론",
            killer_allowed=True,
        )
    )
    index += 1

    cubic_a = 2
    cubic_b = -9
    cubic_answer = cubic_a - cubic_b
    problems.append(
        _drill_problem(
            unit=unit,
            index=index,
            title="두 인수와 상수항으로 삼차식 복원",
            statement="다항식 x^3+ax^2+bx-18이 x-3, x+2를 인수로 가질 때 a-b의 값을 구하시오.",
            steps=[
                exact_step("Step 1. 세 번째 근", "x+3", "근의 곱이 18이 되도록 남은 근을 복원하세요."),
                exact_step("Step 2. 계수 읽기", "a=2, b=-9", "세 근의 합과 쌍곱합으로 a, b를 구하세요."),
                numeric_step("Step 3. a-b", str(cubic_answer), "요구한 값을 계산하세요."),
            ],
            final=numeric_step("최종 답", str(cubic_answer), "최종 값을 적으세요."),
            coach_hint="인수 두 개와 상수항이 함께 나오면 남은 한 근을 먼저 복원하는 것이 가장 빠릅니다.",
            expected_outline=["남은 근 복원", "비에타 적용", "요구값 계산", "최종 답"],
            final_prompt="",
            problem_type="삼차식 근 복원",
            killer_allowed=True,
        )
    )
    return problems


def _common1_equation_killer_bank(unit: dict, start_index: int) -> list[dict]:
    problems: list[dict] = []
    index = start_index

    problems.append(
        _drill_problem(
            unit=unit,
            index=index,
            title="근의 역수 합",
            statement="이차방정식 x^2-7x+10=0의 두 근을 α, β라 할 때 1/α + 1/β의 값을 구하시오.",
            steps=[
                exact_step("Step 1. 합과 곱", "α+β=7, αβ=10", "근과 계수의 관계를 먼저 읽으세요."),
                exact_step("Step 2. 역수의 합", "(α+β)/(αβ)", "역수의 합을 합과 곱으로 바꾸세요."),
                numeric_step("Step 3. 값", "7/10", "읽은 값을 대입해 계산하세요."),
            ],
            final=numeric_step("최종 답", "7/10", "최종 값을 적으세요."),
            coach_hint="근을 직접 구하기보다 합과 곱으로 끝낼 수 있는지 먼저 확인하세요.",
            expected_outline=["합·곱 읽기", "식 변형", "값 계산", "최종 답"],
            final_prompt="",
            problem_type="근의 역수 합",
            killer_allowed=True,
        )
    )
    index += 1

    problems.append(
        _drill_problem(
            unit=unit,
            index=index,
            title="근의 차 조건으로 계수 결정",
            statement="이차방정식 x^2-6x+k=0의 두 근의 차가 4일 때 k의 값을 구하시오.",
            steps=[
                exact_step("Step 1. 두 근", "3-2, 3+2", "두 근의 합이 6이고 차가 4이므로 두 근을 먼저 복원하세요."),
                exact_step("Step 2. 근의 곱", "1*5", "복원한 두 근의 곱을 구하세요."),
                numeric_step("Step 3. k", "5", "상수항 k는 두 근의 곱입니다."),
            ],
            final=numeric_step("최종 답", "5", "최종 값을 적으세요."),
            coach_hint="근의 합과 차가 함께 있으면 두 근을 바로 복원하는 편이 더 빠릅니다.",
            expected_outline=["근 복원", "곱 계산", "상수항 결정", "최종 답"],
            final_prompt="",
            problem_type="근의 차 조건",
            killer_allowed=True,
        )
    )
    index += 1

    problems.append(
        _drill_problem(
            unit=unit,
            index=index,
            title="공통근 역추적",
            statement="이차방정식 x^2-5x+a=0과 x^2+x-6=0이 양의 공통근을 가질 때 a의 값을 구하시오.",
            steps=[
                solution_step("Step 1. 두 번째 방정식의 근", ["2", "-3"], "x^2+x-6=0을 먼저 풀어 양의 근을 찾으세요."),
                exact_step("Step 2. 공통근 대입", "4-10+a=0", "양의 공통근 2를 첫 번째 방정식에 대입하세요."),
                numeric_step("Step 3. a", "6", "a의 값을 계산하세요."),
            ],
            final=numeric_step("최종 답", "6", "최종 값을 적으세요."),
            coach_hint="공통근 문제는 더 쉬운 식을 먼저 풀어 후보를 줄인 뒤 대입하면 됩니다.",
            expected_outline=["쉬운 식 해 구하기", "공통근 대입", "계수 결정", "최종 답"],
            final_prompt="",
            problem_type="공통근 역추적",
            killer_allowed=True,
        )
    )
    index += 1

    problems.append(
        _drill_problem(
            unit=unit,
            index=index,
            title="역수 조건의 매개변수",
            statement="이차방정식 x^2-(m+3)x+2m=0의 두 근이 서로 역수일 때 m의 값을 구하시오.",
            steps=[
                exact_step("Step 1. 역수 조건", "αβ=1", "서로 역수이면 두 근의 곱이 1입니다."),
                exact_step("Step 2. 상수항 비교", "2m=1", "이차방정식의 두 근의 곱과 상수항을 비교하세요."),
                numeric_step("Step 3. m", "1/2", "m의 값을 구하세요."),
            ],
            final=numeric_step("최종 답", "1/2", "최종 값을 적으세요."),
            coach_hint="역수 조건은 곱이 1이라는 한 줄로 닫히는 경우가 많습니다.",
            expected_outline=["역수 해석", "근과 계수", "매개변수 계산", "최종 답"],
            final_prompt="",
            problem_type="역수 근 조건",
            killer_allowed=True,
        )
    )
    index += 1

    problems.append(
        _drill_problem(
            unit=unit,
            index=index,
            title="사차식의 양의 근 합",
            statement="방정식 x^4-13x^2+36=0의 양의 실근의 합을 구하시오.",
            steps=[
                exact_step("Step 1. 치환", "t=x^2", "x^4와 x^2가 함께 있으므로 t=x^2로 치환하세요."),
                solution_step("Step 2. t의 값", ["4", "9"], "t^2-13t+36=0을 풀어 t의 값을 구하세요."),
                numeric_step("Step 3. 양의 실근의 합", "5", "x의 양의 값 2와 3을 더하세요."),
            ],
            final=numeric_step("최종 답", "5", "최종 값을 적으세요."),
            coach_hint="사차식이라도 x^2만 보이면 이차방정식으로 바꾸는 전환이 우선입니다.",
            expected_outline=["치환", "이차방정식 해", "양의 근 선택", "최종 답"],
            final_prompt="",
            problem_type="사차식 치환",
            killer_allowed=True,
        )
    )
    index += 1

    problems.append(
        _drill_problem(
            unit=unit,
            index=index,
            title="근의 평행이동",
            statement="이차방정식 x^2-6x+5=0의 두 근을 α, β라 할 때 α+1, β+1을 두 근으로 하는 이차방정식의 상수항을 구하시오.",
            steps=[
                solution_step("Step 1. 원래 근", ["1", "5"], "원래 이차방정식의 두 근을 구하세요."),
                exact_step("Step 2. 이동된 근", "2, 6", "각 근에 1을 더해 새 근을 만드세요."),
                numeric_step("Step 3. 상수항", "12", "새 이차방정식의 상수항은 두 근의 곱입니다."),
            ],
            final=numeric_step("최종 답", "12", "최종 값을 적으세요."),
            coach_hint="근을 평행이동한 문제는 식을 바로 만들기보다 근 자체를 먼저 이동시키면 빠릅니다.",
            expected_outline=["원래 근 구하기", "근 이동", "새 방정식 읽기", "최종 답"],
            final_prompt="",
            problem_type="근의 평행이동",
            killer_allowed=True,
        )
    )
    index += 1

    problems.append(
        _drill_problem(
            unit=unit,
            index=index,
            title="이차부등식의 자연수 해 개수",
            statement="부등식 x^2-7x+10≤0을 만족하는 자연수 x의 개수를 구하시오.",
            steps=[
                exact_step("Step 1. 인수분해", "(x-2)(x-5)≤0", "좌변을 인수분해하세요."),
                exact_step("Step 2. 해 구간", "2≤x≤5", "부호표를 이용해 해의 구간을 정리하세요."),
                numeric_step("Step 3. 자연수 개수", "4", "2, 3, 4, 5의 개수를 세세요."),
            ],
            final=numeric_step("최종 답", "4", "최종 값을 적으세요."),
            coach_hint="부등식은 근을 찾는 문제가 아니라, 근 사이의 부호를 읽는 문제입니다.",
            expected_outline=["인수분해", "구간 판정", "개수 세기", "최종 답"],
            final_prompt="",
            problem_type="이차부등식 개수 판정",
            killer_allowed=True,
        )
    )
    index += 1

    problems.append(
        _drill_problem(
            unit=unit,
            index=index,
            title="절댓값과 이차식의 만남",
            statement="방정식 |x-3| = x^2-5x+6의 모든 실근의 합을 구하시오.",
            steps=[
                exact_step("Step 1. x≥3인 경우", "(x-3)^2=0", "x≥3에서는 |x-3|=x-3으로 바꾸세요."),
                exact_step("Step 2. x<3인 경우", "x^2-4x+3=0", "x<3에서는 |x-3|=3-x로 바꾸세요."),
                numeric_step("Step 3. 실근의 합", "4", "조건을 만족하는 실근 1, 3의 합을 구하세요."),
            ],
            final=numeric_step("최종 답", "4", "최종 값을 적으세요."),
            coach_hint="절댓값 방정식은 반드시 경우를 나누고, 각 경우에서 나온 해가 조건을 만족하는지 다시 확인해야 합니다.",
            expected_outline=["첫 경우", "둘째 경우", "조건 검사", "최종 답"],
            final_prompt="",
            problem_type="절댓값 이차방정식",
            killer_allowed=True,
        )
    )
    index += 1

    problems.append(
        _drill_problem(
            unit=unit,
            index=index,
            title="제곱된 근의 방정식",
            statement="이차방정식 x^2-6x+8=0의 두 근을 α, β라 할 때 α^2, β^2를 두 근으로 하는 이차방정식의 두 계수의 합을 구하시오.",
            steps=[
                solution_step("Step 1. 원래 근", ["2", "4"], "원래 이차방정식의 두 근을 구하세요."),
                exact_step("Step 2. 제곱한 근", "4, 16", "각 근을 제곱하세요."),
                numeric_step("Step 3. 계수의 합", "44", "새 방정식 x^2-20x+64=0의 두 계수 합을 구하세요."),
            ],
            final=numeric_step("최종 답", "44", "최종 값을 적으세요."),
            coach_hint="변형된 근의 방정식은 원래 근을 먼저 구한 뒤 새 합과 새 곱을 만드는 편이 가장 안전합니다.",
            expected_outline=["원래 근", "새 근", "새 합·곱", "최종 답"],
            final_prompt="",
            problem_type="변형근 방정식",
            killer_allowed=True,
        )
    )
    return problems


def _common1_counting_killer_bank(unit: dict, start_index: int) -> list[dict]:
    problems: list[dict] = []
    index = start_index

    values = [
        (
            "세 책을 한 묶음으로 보는 배치",
            "서로 다른 책 6권을 일렬로 놓을 때, 수학책 A, B, C가 서로 이웃하도록 놓는 방법의 수를 구하시오.",
            factorial(4) * factorial(3),
            "ABC를 한 묶음으로 보면 4개의 객체를 배열하는 문제가 됩니다.",
            "책 블록 배열",
        ),
        (
            "이웃하지 않는 자리배치",
            "서로 다른 7명을 일렬로 세울 때, A와 B가 서로 이웃하지 않도록 하는 방법의 수를 구하시오.",
            factorial(7) - 2 * factorial(6),
            "전체 배열에서 A와 B를 한 묶음으로 본 인접 배열을 빼세요.",
            "비인접 자리배치",
        ),
        (
            "원순열의 마주보기 조건",
            "서로 다른 6명이 원탁에 둘러앉을 때, A와 B가 서로 마주 보도록 앉는 방법의 수를 구하시오.",
            factorial(4),
            "A의 자리를 고정하면 B의 자리는 하나로 정해집니다.",
            "원순열 마주보기",
        ),
        (
            "0을 포함한 네 자리 수",
            "숫자 0,1,2,3,4,5,6 중 서로 다른 4개를 사용하여 만들 수 있는 네 자리 자연수 중 5의 배수의 개수를 구하시오.",
            220,
            "끝자리가 0인 경우와 5인 경우를 나누어 세세요.",
            "0 포함 배수 판정",
        ),
        (
            "조건부 모둠 구성과 대표 선출",
            "남학생 6명, 여학생 5명 중 4명의 발표조를 만들되 여학생이 적어도 2명 포함되게 하고, 발표조 안에서 대표 1명을 정하는 방법의 수를 구하시오.",
            comb(5, 2) * comb(6, 2) * 4 + comb(5, 3) * comb(6, 1) * 4 + comb(5, 4) * 4,
            "여학생 수를 2명, 3명, 4명인 경우로 나눈 뒤 대표 선출까지 곱하세요.",
            "모둠 구성과 대표",
        ),
        (
            "짝수·홀수 개수 조건",
            "숫자 1,2,3,4,5,6,7 중 서로 다른 5개를 사용하여 만들 수 있는 다섯 자리 자연수 중 짝수 숫자가 정확히 2개인 경우의 수를 구하시오.",
            comb(3, 2) * comb(4, 3) * factorial(5),
            "짝수 3개 중 2개, 홀수 4개 중 3개를 고른 뒤 다섯 자리를 배열하세요.",
            "짝홀 개수 조건 배열",
        ),
        (
            "세 사람의 연속 원순열",
            "서로 다른 8명이 원탁에 둘러앉을 때, A, B, C가 연속으로 앉는 방법의 수를 구하시오.",
            factorial(5) * factorial(3),
            "A, B, C를 한 묶음으로 보면 6개의 객체가 원탁에 앉는 문제입니다.",
            "연속 블록 원순열",
        ),
        (
            "서로 다른 성별의 임원 선출",
            "남학생 5명, 여학생 5명 중에서 회장 1명과 부회장 1명을 뽑을 때 두 사람이 서로 다른 성별이 되도록 뽑는 방법의 수를 구하시오.",
            5 * 5 * 2,
            "남학생 회장-여학생 부회장, 여학생 회장-남학생 부회장 두 경우를 더하세요.",
            "이성별 임원 선출",
        ),
        (
            "두 묶음이 동시에 붙는 배열",
            "서로 다른 책 7권을 일렬로 놓을 때 A, B가 서로 이웃하고 C, D도 서로 이웃하도록 놓는 방법의 수를 구하시오.",
            factorial(5) * 2 * 2,
            "AB, CD를 각각 한 묶음으로 보면 5개의 객체를 배열하는 문제입니다.",
            "이중 블록 배열",
        ),
    ]

    for title, statement, answer, hint, problem_type in values:
        problems.append(
            _drill_problem(
                unit=unit,
                index=index,
                title=title,
                statement=statement,
                steps=[
                    exact_step("Step 1. 구조 분해", hint, "문제를 먼저 어떤 경우로 나눌지 정리하세요."),
                    exact_step("Step 2. 경우의 수 식", str(answer), "필요한 조합·순열 식을 세워 계산하세요."),
                    numeric_step("Step 3. 값", str(answer), "최종 경우의 수를 정리하세요."),
                ],
                final=numeric_step("최종 답", str(answer), "최종 값을 적으세요."),
                coach_hint="경우의 수 킬러는 공식이 아니라, 묶기·나누기·보수세기 중 무엇을 먼저 쓸지 판단하는 문제입니다.",
                expected_outline=["구조 분해", "식 세우기", "계산", "최종 답"],
                final_prompt="",
                problem_type=problem_type,
                killer_allowed=True,
            )
        )
        index += 1

    return problems


def _common1_matrix_killer_bank(unit: dict, start_index: int) -> list[dict]:
    problems: list[dict] = []
    index = start_index

    specs = [
        (
            "합행렬의 성분합",
            "A=[[2,-1],[3,4]], B=[[-3,5],[1,2]]일 때 A+B의 모든 성분의 합을 구하시오.",
            "[[-1,4],[4,6]]",
            "13",
            "합행렬 성분합",
        ),
        (
            "실수배와 차행렬의 trace",
            "A=[[1,2],[0,-1]], B=[[3,-2],[4,5]]일 때 trace(2A-B)의 값을 구하시오.",
            "[[-1,6],[-4,-7]]",
            "-8",
            "실수배 차행렬 trace",
        ),
        (
            "곱행렬의 trace",
            "A=[[1,2],[3,1]], B=[[2,-1],[4,0]]일 때 trace(AB)의 값을 구하시오.",
            "[[10,-1],[10,-3]]",
            "7",
            "곱행렬 trace",
        ),
        (
            "미지 행렬의 성분합",
            "A=[[1,-2],[3,0]], B=[[4,1],[-1,5]]이고 A+X=B일 때 행렬 X의 모든 성분의 합을 구하시오.",
            "[[3,3],[-4,5]]",
            "7",
            "합으로 미지 행렬 복원",
        ),
        (
            "차행렬로 미지 행렬 복원",
            "A=[[2,1],[-1,3]], B=[[1,-4],[5,2]]이고 2A-X=B일 때 행렬 X의 모든 성분의 합을 구하시오.",
            "[[3,6],[-7,4]]",
            "6",
            "차로 미지 행렬 복원",
        ),
        (
            "AX=B 역추론",
            "A=[[1,2],[0,1]], X=[[x,y],[z,w]], B=[[5,8],[2,3]]일 때 x+y+z+w의 값을 구하시오.",
            "[[1,2],[2,3]]",
            "8",
            "왼쪽 곱 미지 행렬",
        ),
        (
            "XA와 보정행렬 역추론",
            "A=[[1,1],[0,1]], X=[[x,y],[z,w]], B=[[1,0],[0,1]], C=[[4,5],[2,3]]일 때 XA+B=C를 만족시키는 x+y+z+w의 값을 구하시오.",
            "[[3,2],[2,0]]",
            "7",
            "보정행렬이 있는 오른쪽 곱 미지 행렬",
        ),
        (
            "제곱행렬의 trace",
            "A=[[1,2],[2,1]]일 때 trace(A^2)의 값을 구하시오.",
            "[[5,4],[4,5]]",
            "10",
            "제곱행렬 trace",
        ),
        (
            "매개변수 행렬방정식",
            "A=[[1,2],[0,-1]], B=[[3,1],[4,2]], C=[[8,11],[4,-3]]에 대하여 kA+B=C를 만족하는 실수 k의 값을 구하시오.",
            "k=5",
            "5",
            "매개변수 행렬식",
        ),
    ]

    for title, statement, display_value, answer, problem_type in specs:
        problems.append(
            _drill_problem(
                unit=unit,
                index=index,
                title=title,
                statement=statement,
                steps=[
                    exact_step("Step 1. 필요한 식", display_value, "조건을 이용해 먼저 필요한 행렬 또는 식을 복원하세요."),
                    exact_step("Step 2. 읽기", answer, "복원한 결과에서 요구한 값을 읽으세요."),
                    numeric_step("Step 3. 값", answer, "최종 값을 정리하세요."),
                ],
                final=numeric_step("최종 답", answer, "최종 값을 적으세요."),
                coach_hint="행렬 킬러는 전체를 다 계산하는 문제가 아니라, 필요한 행렬만 남기는 판단이 중요합니다.",
                expected_outline=["필요한 행렬 복원", "요구값 읽기", "정리", "최종 답"],
                final_prompt="",
                problem_type=problem_type,
                killer_allowed=True,
            )
        )
        index += 1

    return problems


def _common2_coordinate_killer_bank(unit: dict, start_index: int) -> list[dict]:
    problems: list[dict] = []
    index = start_index

    specs = [
        (
            "외분점과 직선의 y절편",
            "점 A(1,3), B(7,-3)을 2:1로 외분하는 점을 지나고 기울기가 -1인 직선의 y절편을 구하시오.",
            "(13,-9)",
            "4",
            "외분점 직선 결합",
        ),
        (
            "수직이등분선의 방정식",
            "점 A(1,2), B(5,6)을 이은 선분의 수직이등분선의 방정식을 구하시오.",
            "(3,4), 기울기 -1",
            "y=-x+7",
            "수직이등분선 복원",
        ),
        (
            "접선 조건의 반지름",
            "중심이 (2,0)인 원이 직선 x+y-6=0에 접할 때 이 원의 방정식을 구하시오.",
            "반지름^2 = 8",
            "(x-2)^2+y^2=8",
            "직선과 원의 접점 거리",
        ),
        (
            "도형의 이동 후 원의 방정식",
            "원 x^2+y^2-4x+6y-12=0을 x축 방향으로 2만큼, y축 방향으로 -3만큼 평행이동한 원의 방정식을 구하시오.",
            "중심 (4,-6), 반지름^2=25",
            "(x-4)^2+(y+6)^2=25",
            "평행이동 원 복원",
        ),
        (
            "직선의 접선 매개변수",
            "직선 y=2x+k가 원 x^2+y^2=5에 접할 때 k>0인 경우 k의 값을 구하시오.",
            "거리 공식 |k|/√5 = √5",
            "5",
            "접선 매개변수",
        ),
        (
            "교점 중심 원의 방정식",
            "직선 x+y=4와 2x-y=5의 교점을 중심으로 하고 반지름이 2인 원의 방정식을 구하시오.",
            "중심 (3,1)",
            "(x-3)^2+(y-1)^2=4",
            "교점 중심 원",
        ),
        (
            "대칭점과 직선",
            "점 P(4,-1)을 x축에 대하여 대칭이동한 점 Q를 생각하자. 선분 PQ의 중점을 지나고 기울기가 1인 직선의 방정식을 구하시오.",
            "중점 (4,0)",
            "y=x-4",
            "대칭점 직선",
        ),
        (
            "중심 제약이 있는 원",
            "중심이 y축 위에 있는 원이 점 A(3,1), B(1,5)를 지난다. 이 원의 방정식을 구하시오.",
            "중심 (0,2), 반지름^2=10",
            "x^2+(y-2)^2=10",
            "중심 제약 원 복원",
        ),
        (
            "점과 직선의 거리 매개변수",
            "점 (2,-1)에서 직선 3x-4y+k=0까지의 거리가 5일 때 가능한 모든 k의 값의 합을 구하시오.",
            "|k+10|=25",
            "-20",
            "거리 매개변수",
        ),
    ]

    for title, statement, display_value, answer, problem_type in specs:
        final_step = exact_step("최종 답", answer, "최종 값을 적으세요.") if any(ch in answer for ch in "=()xy") else numeric_step("최종 답", answer, "최종 값을 적으세요.")
        problems.append(
            _drill_problem(
                unit=unit,
                index=index,
                title=title,
                statement=statement,
                steps=[
                    exact_step("Step 1. 핵심 복원", display_value, "좌표나 중심, 거리 조건을 먼저 복원하세요."),
                    exact_step("Step 2. 식 세우기", answer, "복원한 조건으로 직선식 또는 원의 방정식을 세우세요."),
                    exact_step("Step 3. 정리", answer, "요구한 식 또는 값을 정리하세요."),
                ],
                final=final_step,
                coach_hint="도형의 방정식 킬러는 그림을 오래 그리기보다, 중심·기울기·거리 중 무엇이 먼저 고정되는지 보는 문제가 많습니다.",
                expected_outline=["핵심 조건 복원", "식 세우기", "정리", "최종 답"],
                final_prompt="",
                problem_type=problem_type,
                killer_allowed=True,
            )
        )
        index += 1

    return problems


def _common2_function_killer_bank(unit: dict, start_index: int) -> list[dict]:
    problems: list[dict] = []
    index = start_index

    specs = [
        (
            "합성함수 값 복원",
            "f(x)=2x-1, g(x)=x^2+3일 때 (f∘g)(2) + (g∘f)(1)의 값을 구하시오.",
            "13, 4",
            "17",
            "합성함수 값 계산",
        ),
        (
            "역함수의 특정값",
            "함수 f(x)=3x+5의 역함수를 f^-1(x)라 할 때 f^-1(20)의 값을 구하시오.",
            "f^-1(x)=(x-5)/3",
            "5",
            "역함수 특정값",
        ),
        (
            "유리함수의 정의역 판정",
            "함수 y=(x+2)/(x^2-5x+6)의 정의역에서 제외되는 모든 실수의 합을 구하시오.",
            "x=2, 3 제외",
            "5",
            "유리함수 정의역",
        ),
        (
            "무리함수의 정의역",
            "함수 y=√((x+1)/(x-2))의 정의역을 구하시오.",
            "(x+1)/(x-2)≥0",
            "x≤-1 또는 x>2",
            "무리함수 정의역",
        ),
        (
            "평행이동된 유리함수",
            "함수 y=1/x의 그래프를 x축 방향으로 2만큼, y축 방향으로 -3만큼 평행이동한 그래프의 방정식을 구하시오.",
            "y=1/(x-2)-3",
            "y=1/(x-2)-3",
            "유리함수 평행이동",
        ),
        (
            "합성 후 방정식 개수",
            "f(x)=x^2-1, g(x)=2x+3일 때 f(g(x))=0을 만족하는 실수 x의 개수를 구하시오.",
            "(2x+3)^2-1=0",
            "2",
            "합성함수 방정식",
        ),
        (
            "역함수와 원함수의 만남",
            "f(x)=2x+7일 때 f(3)+f^-1(15)의 값을 구하시오.",
            "f(3)=13, f^-1(15)=4",
            "17",
            "역함수와 원함수 결합",
        ),
        (
            "무리함수 그래프의 절편",
            "함수 y=√(x-1)+2의 그래프가 y축과 만나는지 판정하고, x축과 만난다면 그 x좌표를 구하시오.",
            "정의역 x≥1",
            "만나지 않는다",
            "무리함수 절편 판정",
        ),
        (
            "유리함수와 직선의 교점 수",
            "함수 y=1/(x-1)와 직선 y=x-1의 교점의 개수를 구하시오.",
            "1/(x-1)=x-1 → (x-1)^2=1",
            "2",
            "유리함수 직선 교점",
        ),
    ]

    for title, statement, display_value, answer, problem_type in specs:
        final_step = exact_step("최종 답", answer, "최종 값을 적으세요.") if any(ch in answer for ch in "=<>x또는만") else numeric_step("최종 답", answer, "최종 값을 적으세요.")
        problems.append(
            _drill_problem(
                unit=unit,
                index=index,
                title=title,
                statement=statement,
                steps=[
                    exact_step("Step 1. 핵심 식", display_value, "합성, 역함수, 정의역 중 먼저 필요한 식을 세우세요."),
                    exact_step("Step 2. 정리", answer, "계산 또는 해석을 끝까지 진행하세요."),
                    exact_step("Step 3. 최종 확인", answer, "요구한 값 또는 식을 정리하세요."),
                ],
                final=final_step,
                coach_hint="함수와 그래프 킬러는 식을 오래 만지는 것보다, 합성·역함수·정의역 중 무엇을 먼저 잡을지 정하는 판단이 중요합니다.",
                expected_outline=["핵심 식", "정리", "최종 확인", "최종 답"],
                final_prompt="",
                problem_type=problem_type,
                killer_allowed=True,
            )
        )
        index += 1

    return problems


def _probstat_probability_killer_bank(unit: dict, start_index: int) -> list[dict]:
    problems: list[dict] = []
    index = start_index

    specs = [
        (
            "정확히 두 개의 특정 색",
            "빨간 공 5개, 파란 공 4개가 들어 있는 주머니에서 공 3개를 동시에 꺼낼 때 정확히 2개가 빨간 공일 확률을 구하시오.",
            "10/21",
            "정확히 두 빨간 공",
        ),
        (
            "여사건으로 푸는 확률",
            "빨간 공 3개, 파란 공 5개가 들어 있는 주머니에서 공 2개를 동시에 꺼낼 때 적어도 1개가 파란 공일 확률을 구하시오.",
            "25/28",
            "여사건 확률",
        ),
        (
            "조건부확률 역추적",
            "빨간 공 4개, 파란 공 3개가 들어 있는 주머니에서 공 2개를 동시에 꺼냈다. 적어도 1개가 빨간 공이라는 조건 아래 두 공이 모두 빨간 공일 확률을 구하시오.",
            "1/3",
            "조건부확률 역추적",
        ),
        (
            "반복 시행의 정확한 성공 횟수",
            "앞면이 나올 확률이 1/2인 동전을 5번 던질 때, 앞면이 정확히 2번 나올 확률을 구하시오.",
            "5/16",
            "반복시행 성공횟수",
        ),
        (
            "조건이 붙은 주사위 확률",
            "두 개의 주사위를 동시에 던졌을 때 첫 번째 주사위의 눈이 짝수라는 조건 아래 눈의 합이 8보다 클 확률을 구하시오.",
            "1/3",
            "조건부 주사위 확률",
        ),
        (
            "같은 색이 나올 확률",
            "빨간 공 2개, 파란 공 3개, 초록 공 4개가 들어 있는 주머니에서 공 2개를 동시에 꺼낼 때 두 공의 색이 같을 확률을 구하시오.",
            "5/18",
            "같은 색 확률",
        ),
        (
            "성별 조합의 확률",
            "남학생 4명, 여학생 3명 중에서 2명을 임의로 뽑을 때 두 사람이 서로 다른 성별일 확률을 구하시오.",
            "4/7",
            "서로 다른 집단 확률",
        ),
        (
            "성공확률이 2/3인 시행",
            "성공확률이 2/3인 시행을 3번 반복할 때 적어도 2번 성공할 확률을 구하시오.",
            "20/27",
            "적어도 두 번 성공",
        ),
        (
            "합의 짝홀성 확률",
            "1부터 10까지 적힌 카드 10장 중에서 2장을 동시에 뽑을 때 두 수의 합이 짝수가 될 확률을 구하시오.",
            "4/9",
            "합의 짝홀성",
        ),
    ]

    for title, statement, answer, problem_type in specs:
        problems.append(
            _drill_problem(
                unit=unit,
                index=index,
                title=title,
                statement=statement,
                steps=[
                    exact_step("Step 1. 구조 분해", answer, "전체 경우와 유리한 경우를 어떻게 셀지 먼저 결정하세요."),
                    exact_step("Step 2. 확률식", answer, "조합, 조건부확률, 여사건 중 맞는 식으로 정리하세요."),
                    numeric_step("Step 3. 값", answer, "기약분수로 확률을 정리하세요."),
                ],
                final=numeric_step("최종 답", answer, "최종 값을 적으세요."),
                coach_hint="확률 킬러는 분자와 분모를 세는 방식이 문제마다 달라집니다. 먼저 어떤 경우를 세는지 언어로 정리하세요.",
                expected_outline=["경우 분해", "확률식", "기약분수", "최종 답"],
                final_prompt="",
                problem_type=problem_type,
                killer_allowed=True,
            )
        )
        index += 1

    return problems


def _uses_exact_final(answer: str, mode: str) -> bool:
    if mode == "exact":
        return True
    markers = ("x", "y", "(", ")", "=", "<", ">", "{", "}", "또는", "만나지", "충분", "필요", "역", "~", "ln", "log", "π", "√")
    return any(marker in answer for marker in markers)


def _generic_curated_problem_bank(
    unit: dict,
    start_index: int,
    specs: list[tuple[str, str, str, str, str, str]],
    *,
    coach_hint: str,
    killer_allowed: bool,
) -> list[dict]:
    problems: list[dict] = []
    index = start_index
    for title, statement, focus, answer, problem_type, mode in specs:
        exact_final = _uses_exact_final(answer, mode)
        final = (
            exact_step("최종 답", answer, "최종 값을 적으세요.")
            if exact_final
            else numeric_step("최종 답", answer, "최종 값을 적으세요.")
        )
        third_step = (
            exact_step("Step 3. 정리", answer, "요구한 값 또는 식을 정리하세요.")
            if exact_final
            else numeric_step("Step 3. 값", answer, "최종 값을 정리하세요.")
        )
        problems.append(
            _drill_problem(
                unit=unit,
                index=index,
                title=title,
                statement=statement,
                steps=[
                    exact_step("Step 1. 핵심 복원", focus, "문제의 핵심 구조를 먼저 복원하세요."),
                    exact_step("Step 2. 계산 또는 판정", answer, "복원한 구조를 끝까지 계산하거나 판정하세요."),
                    third_step,
                ],
                final=final,
                coach_hint=coach_hint,
                expected_outline=["핵심 구조 복원", "계산 또는 판정", "정리", "최종 답"],
                final_prompt="",
                problem_type=problem_type,
                killer_allowed=killer_allowed,
            )
        )
        index += 1
    return problems


GENERIC_CURATED_ADVANCED_SPECS: dict[str, list[tuple[str, str, str, str, str, str]]] = {
    "common1-polynomial": [
        ("세 점 나머지 합 역산", "다항식 P(x)=x^3+ax^2+bx+1에 대하여 P(1)=4, P(2)=9, P(3)=16일 때 a+b의 값을 구하시오.", "P(1), P(2)로 두 식을 세우고 P(3)으로 검산합니다.", "0", "세 점 나머지 합 역산", "numeric"),
        ("이차식 몫과 나머지", "다항식 P(x)=x^3-2x^2+ax+b를 x^2-3x+2로 나누었을 때의 나머지가 x+1이다. a+b의 값을 구하시오.", "P(1)=2, P(2)=3", "1", "이차식 몫과 나머지", "numeric"),
        ("다항식 항등식 두 상수", "모든 실수 x에 대하여 x^3+ax+b=(x-1)(x^2+2x+3)+5 가 성립한다. a+b의 값을 구하시오.", "우변을 전개해 계수를 비교합니다.", "3", "다항식 항등식 두 상수", "numeric"),
        ("대칭대입 계수판정", "다항식 P(x)=x^3+ax^2+bx+7에 대하여 P(1)+P(-1)=12, P(1)-P(-1)=10일 때 a+b의 값을 구하시오.", "짝수차와 홀수차를 분리합니다.", "-2", "대칭대입 계수판정", "numeric"),
        ("나머지정리 역추적", "다항식 P(x)=x^3-2x^2+ax+5를 x-2로 나누었을 때의 나머지가 7이다. 상수 a의 값을 구하시오.", "P(2)=7", "1", "나머지정리 역추적", "numeric"),
        ("두 점값으로 계수 복원", "다항식 P(x)=x^3+ax^2+bx+1이 P(1)=6, P(-1)=2를 만족할 때 a+b의 값을 구하시오.", "a+b=4, a-b=2", "3", "두 점값 계수 복원", "numeric"),
        ("인수와 나머지 동시 조건", "다항식 P(x)=x^3+ax^2+bx-6이 x-2로 나누어떨어지고, x+1로 나누었을 때의 나머지가 6이다. a+b의 값을 구하시오.", "P(2)=0, P(-1)=6", "-2", "인수와 나머지 동시 조건", "numeric"),
        ("x^2-1 나머지 복원", "다항식 P(x)=x^4-3x^3+ax^2+bx+5를 x^2-1로 나누었을 때의 나머지가 4x+2이다. a+b의 값을 구하시오.", "P(1)=6, P(-1)=-2", "4", "이차식 나머지 계수 복원", "numeric"),
        ("곱의 나머지 판정", "다항식 P(x)=x^2-3x+2, Q(x)=x^2+ax+b에 대하여 P(x)Q(x)를 x-1로 나누었을 때의 나머지가 0, x-2로 나누었을 때의 나머지가 6이다. a+b의 값을 구하시오.", "P(1)=0, P(2)=0이 아닌 구조를 먼저 확인합니다.", "5", "곱의 나머지 판정", "numeric"),
        ("시프트 차이식", "다항식 P(x)=x^3+ax^2+bx+c가 P(x+1)-P(x)=3x^2+7x+5를 만족한다. a+b의 값을 구하시오.", "차이식의 최고차항과 계수를 비교합니다.", "1", "시프트 차이식", "numeric"),
        ("계수비교형 항등식", "모든 실수 x에 대하여 (x^2+ax+b)(x-1)=x^3-2x^2-5x+6 이다. a+b의 값을 구하시오.", "전개 후 계수 비교", "-6", "계수비교형 항등식", "numeric"),
        ("세 점 통과 인수분해", "다항식 P(x)=x^3+ax^2+bx+c가 P(1)=0, P(2)=0, P(3)=0을 만족할 때 c의 값을 구하시오.", "P(x)=(x-1)(x-2)(x-3)", "-6", "세 점 통과 인수분해", "numeric"),
        ("나머지식의 계수판정", "다항식 P(x)=x^3+ax+b를 x^2-x로 나누었을 때의 나머지가 2x+3이다. a+b의 값을 구하시오.", "P(0)=3, P(1)=5", "2", "나머지식의 계수판정", "numeric"),
        ("대칭값 합", "다항식 P(x)=x^4+ax^2+b에 대하여 P(1)=3, P(2)=18일 때 a+b의 값을 구하시오.", "a+b=2, 4a+b=2", "2", "대칭값 합", "numeric"),
        ("인수정리와 몫의 값", "다항식 P(x)=x^3+ax^2+bx+6이 x+2로 나누어떨어지고, P(1)=0일 때 a-b의 값을 구하시오.", "P(-2)=0, P(1)=0", "7", "인수정리와 몫의 값", "numeric"),
        ("합성 대입 계수", "다항식 P(x)=x^2+ax+b에 대하여 P(1)=3, P(P(1))=13일 때 a+b의 값을 구하시오.", "P(1)=3이므로 P(3)=13", "1", "합성 대입 계수", "numeric"),
        ("제곱근 대칭 구조", "다항식 P(x)=x^2+ax+b에 대하여 P(1)+P(-1)=10, P(1)-P(-1)=4일 때 a+b의 값을 구하시오.", "합과 차로 a, 1+b를 분리합니다.", "4", "제곱근 대칭 구조", "numeric"),
        ("몫과 나머지 동시복원", "다항식 P(x)를 x-1로 나누었을 때의 나머지가 2, x+1로 나누었을 때의 나머지가 -4이다. P(x)를 x^2-1로 나누었을 때의 나머지를 구하시오.", "나머지를 ax+b라 두고 두 점 조건을 씁니다.", "3x-1", "몫과 나머지 동시복원", "exact"),
        ("이중근 조건", "다항식 P(x)=x^3+ax^2+bx+4가 x+2를 인수로 가지고, P'(x)가 x=-2에서 0이다. a+b의 값을 구하시오.", "P(-2)=0, P'(-2)=0", "-8", "이중근 조건", "numeric"),
        ("계수의 합과 교대합", "다항식 P(x)=x^4+ax^3+bx^2+cx+5에 대하여 P(1)=12, P(-1)=4, P(0)=5일 때 a+c의 값을 구하시오.", "P(1), P(-1)로 홀수차와 짝수차를 분리합니다.", "4", "계수의 합과 교대합", "numeric"),
        ("조건식으로 함수값 복원", "다항식 P(x)가 모든 실수 x에 대하여 P(x)-P(x-1)=3x^2-3x+1이고 P(0)=2를 만족한다. P(2)의 값을 구하시오.", "P(2)=P(0)+{P(1)-P(0)}+{P(2)-P(1)}", "12", "차분으로 함수값 복원", "numeric"),
    ],
    "common1-equation": [
        ("상수항과 근의 곱", "이차방정식 x^2-4x+k=0의 두 근 α, β가 αβ=3을 만족할 때 k의 값을 구하시오.", "상수항이 곱입니다.", "3", "상수항과 근의 곱", "numeric"),
        ("근의 역수 방정식", "이차방정식 3x^2-8x+4=0의 두 근 α, β의 역수 1/α, 1/β를 근으로 하는 이차방정식을 구하시오.", "x를 1/t로 바꾸고 정리합니다.", "4x^2-8x+3=0", "근의 역수 방정식", "exact"),
        ("절댓값 방정식 해 개수", "|x^2-5x+4|=0을 만족하는 실수 x의 개수를 구하시오.", "절댓값이 0이면 안쪽이 0입니다.", "2", "절댓값 방정식 해 개수", "numeric"),
        ("근과 계수의 차", "이차방정식 x^2-6x+5=0의 두 근을 α, β라 할 때 (α-β)^2의 값을 구하시오.", "(α+β)^2-4αβ", "16", "근과 계수의 차", "numeric"),
        ("근의 합과 제곱합", "이차방정식 x^2-5x+6=0의 두 근을 α, β라 할 때 α^2+β^2의 값을 구하시오.", "(α+β)^2-2αβ", "13", "근의 합과 제곱합", "numeric"),
        ("역수의 합", "이차방정식 2x^2-5x+2=0의 두 근을 α, β라 할 때 1/α + 1/β의 값을 구하시오.", "(α+β)/(αβ)", "5/2", "역수의 합", "numeric"),
        ("근의 차로 계수 제곱 복원", "이차방정식 x^2+kx+4=0의 두 근의 차가 3일 때 k^2의 값을 구하시오.", "두 근을 1, 4 또는 -1, -4로 복원합니다.", "25", "근의 차로 계수 제곱 복원", "numeric"),
        ("공통근 매개변수 역추적", "방정식 x^2-5x+6=0과 x^2+ax+6=0이 공통인 근을 하나 가질 때 a의 값을 모두 구하시오.", "공통근은 2 또는 3입니다.", "a=-5 또는 a=-4", "공통근 매개변수 복원", "exact"),
        ("판별식으로 실근 개수", "이차방정식 x^2-4x+k=0이 서로 다른 두 실근을 갖도록 하는 정수 k의 개수를 구하시오.", "판별식 16-4k>0", "4", "판별식 정수 개수", "numeric"),
        ("절댓값과 이차식 결합", "|x-1|=3-x 를 만족하는 실수 x의 값을 모두 구하시오.", "x≥1과 x<1로 나눕니다.", "1 또는 2", "절댓값과 일차식 결합", "exact"),
        ("이차부등식 해집합 길이", "부등식 x^2-6x+5<0의 해집합에서 정수의 개수를 구하시오.", "(x-1)(x-5)<0", "3", "이차부등식 정수 개수", "numeric"),
        ("근의 이동", "방정식 x^2-4x+1=0의 두 근을 α, β라 할 때 (α+1)(β+1)의 값을 구하시오.", "αβ+α+β+1", "-2", "근의 이동", "numeric"),
        ("새 방정식 만들기", "이차방정식 x^2-3x-4=0의 두 근을 각각 2씩 더한 수를 근으로 하는 이차방정식을 구하시오.", "y=x+2로 치환합니다.", "x^2-7x+6=0", "새 방정식 만들기", "exact"),
        ("부등식과 매개변수", "부등식 x^2+kx+4>0이 모든 실수 x에 대하여 성립하도록 하는 정수 k의 개수를 구하시오.", "판별식이 음수이고 최고차항 계수는 양수입니다.", "3", "부등식과 매개변수", "numeric"),
        ("근과 계수의 선형결합", "이차방정식 x^2-6x+8=0의 두 근을 α, β라 할 때 α/β + β/α의 값을 구하시오.", "(α^2+β^2)/(αβ)", "5/2", "근과 계수의 선형결합", "numeric"),
        ("삼차식 인수조건", "삼차방정식 x^3-6x^2+11x-k=0이 x=1을 근으로 가질 때 k의 값을 구하시오.", "1-6+11-k=0", "6", "삼차식 인수조건", "numeric"),
        ("중근 판정", "방정식 x^2+2ax+a=0이 중근을 가질 때 a의 값을 구하시오.", "판별식 4a^2-4a=0", "0 또는 1", "중근 판정", "exact"),
        ("이차방정식과 최대최소", "이차함수 y=x^2-4x+k의 최솟값이 3일 때 k의 값을 구하시오.", "(x-2)^2+k-4", "7", "이차식 최솟값 연결", "numeric"),
        ("실근 조건의 역수정리", "방정식 x+1/x=5를 만족하는 모든 실수 x의 값을 구하시오.", "x^2-5x+1=0", "(5+√21)/2 또는 (5-√21)/2", "역수정리 연결", "exact"),
        ("근의 절댓값 조건", "이차방정식 x^2-2x-3=0의 두 근 α, β에 대하여 |α|+|β|의 값을 구하시오.", "근을 구해 부호를 확인합니다.", "4", "근의 절댓값 조건", "numeric"),
        ("부등식 해집합과 매개변수", "부등식 x^2-(a+1)x+a<0의 해집합이 1<x<3일 때 a의 값을 구하시오.", "근이 1과 3입니다.", "3", "부등식 해집합 역추적", "numeric"),
    ],
    "common1-counting": [
        ("두 자리수 조건 분할", "숫자 1,2,3,4,5,6 중 서로 다른 3개를 골라 세 자리 수를 만들 때 백의 자리가 짝수인 수의 개수를 구하시오.", "백의 자리부터 고릅니다.", "60", "두 자리수 조건 분할", "numeric"),
        ("서로 다른 두 블록", "서로 다른 7명 중 A, B는 이웃하고 C, D도 이웃하도록 일렬로 세우는 방법의 수를 구하시오.", "AB, CD 두 묶음", "480", "서로 다른 두 블록", "numeric"),
        ("위원회와 순서", "8명 중 3명의 대표를 뽑고 발표 순서를 정하는 방법의 수를 구하시오.", "8P3", "336", "위원회와 순서", "numeric"),
        ("자연수해와 제한", "자연수 x, y, z가 x+y+z=10을 만족하고 x≥2일 때 순서쌍 (x,y,z)의 개수를 구하시오.", "x'=x-1로 치환합니다.", "28", "자연수해와 제한", "numeric"),
        ("블록과 자리배치", "서로 다른 7명 중 A, B, C가 서로 이웃하도록 일렬로 세우는 방법의 수를 구하시오.", "ABC를 한 묶음으로 봅니다.", "720", "블록과 자리배치", "numeric"),
        ("양끝 제약 배열", "서로 다른 6권의 책을 일렬로 놓을 때 수학책과 영어책이 양끝에 오도록 하는 방법의 수를 구하시오.", "양끝 배치 후 가운데를 배열합니다.", "48", "양끝 제약 배열", "numeric"),
        ("적어도 한 번 포함", "남학생 5명, 여학생 4명 중 4명을 뽑을 때 여학생이 적어도 1명 포함되도록 하는 방법의 수를 구하시오.", "전체에서 여학생이 0명인 경우를 뺍니다.", "121", "적어도 한 번 포함", "numeric"),
        ("인접 금지 배열", "서로 다른 5명 A, B, C, D, E를 일렬로 세울 때 A와 B가 서로 이웃하지 않도록 하는 방법의 수를 구하시오.", "전체에서 이웃하는 경우를 뺍니다.", "72", "인접 금지 배열", "numeric"),
        ("짝수 다섯 자리 수", "숫자 0,1,2,3,4,5를 한 번씩만 사용하여 만들 수 있는 다섯 자리 짝수의 개수를 구하시오.", "끝자리가 0인 경우와 2,4인 경우를 나눕니다.", "216", "짝수 다섯 자리 수", "numeric"),
        ("원순열 분리 조건", "서로 다른 6명이 원탁에 둘러앉을 때 A와 B가 서로 이웃하지 않도록 앉는 방법의 수를 구하시오.", "전체 원순열에서 이웃하는 경우를 뺍니다.", "72", "원순열 분리 조건", "numeric"),
        ("정수해 분배", "자연수 x, y, z가 x+y+z=9를 만족할 때 순서쌍 (x,y,z)의 개수를 구하시오.", "자연수해 개수 공식", "28", "정수해 분배", "numeric"),
        ("중복문자 배열", "MISSISSIPPI에서 문자 I의 개수는 4, S의 개수는 4, P의 개수는 2이다. 서로 다른 배열의 수를 구하시오.", "11!/(4!4!2!)", "34650", "중복문자 배열 고난도", "numeric"),
        ("격자경로 금지점", "좌표평면에서 (0,0)에서 (5,4)까지 오른쪽 또는 위쪽으로만 이동할 때 점 (2,2)를 지나지 않는 최단경로의 수를 구하시오.", "전체에서 금지점을 지나는 경우를 뺍니다.", "66", "격자경로 금지점", "numeric"),
        ("팀장 포함 위원회", "남학생 6명, 여학생 5명 중 4명의 위원회를 만들고 그중 1명을 팀장으로 정할 때 남학생과 여학생이 모두 포함되도록 하는 방법의 수를 구하시오.", "위원회 구성 뒤 팀장을 정합니다.", "1240", "팀장 포함 위원회", "numeric"),
        ("번갈아 앉기", "남학생 4명, 여학생 3명을 일렬로 세울 때 남학생끼리 서로 이웃하지 않도록 세우는 방법의 수를 구하시오.", "남학생 사이 빈칸에 여학생을 배치합니다.", "144", "번갈아 앉기", "numeric"),
        ("세 사람 블록과 두 사람 블록", "서로 다른 8명 중 A, B, C는 서로 이웃하고 D, E도 서로 이웃하도록 일렬로 세우는 방법의 수를 구하시오.", "ABC와 DE를 각각 묶음으로 보고 나머지 3명과 함께 배열합니다.", "1440", "세 사람 블록과 두 사람 블록", "numeric"),
        ("거듭제곱 수열의 선택", "1,2,4,8,16,32 중 3개를 골라 곱이 64가 되도록 하는 방법의 수를 구하시오.", "지수합이 6이 되도록 고릅니다.", "1", "거듭제곱 수열의 선택", "numeric"),
        ("자리수와 합 조건", "서로 다른 숫자 1,2,3,4,5 중 3개를 골라 세 자리 수를 만들 때 각 자리 숫자의 합이 9가 되는 수의 개수를 구하시오.", "가능한 숫자 조합을 먼저 고릅니다.", "12", "자리수와 합 조건", "numeric"),
        ("연속칸 배치", "길이가 7인 자리에서 서로 다른 3명이 연속한 3칸에 앉고, 나머지 2명도 서로 이웃하지 않게 앉는 방법의 수를 구하시오.", "3칸 블록과 나머지 빈칸 구조를 먼저 봅니다.", "216", "연속칸 배치", "numeric"),
        ("회장과 부회장", "10명 중 4명의 대표단을 만들고 회장과 부회장을 정할 때 특정 두 사람 A, B가 동시에 포함되지 않도록 하는 방법의 수를 구하시오.", "전체에서 A,B 동시 포함을 뺍니다.", "1120", "회장과 부회장 제약", "numeric"),
        ("원순열 맞은편 조건", "서로 다른 8명이 원탁에 앉을 때 A와 B가 서로 맞은편에 앉도록 하는 방법의 수를 구하시오.", "A를 고정하고 B의 위치를 정한 뒤 나머지를 배열합니다.", "720", "원순열 맞은편 조건", "numeric"),
    ],
    "common1-matrix": [
        ("행렬 차의 합", "A=[[4,1],[2,3]], B=[[1,-2],[0,5]]일 때 A-B의 모든 성분의 합을 구하시오.", "성분별로 뺀 뒤 합칩니다.", "6", "행렬 차의 합", "numeric"),
        ("배수행렬 판정", "A=[[1,2],[-1,3]]에 대하여 3A의 (2,2)성분을 구하시오.", "각 성분에 3을 곱합니다.", "9", "배수행렬 판정", "numeric"),
        ("행렬곱 첫 행 합", "A=[[2,1],[1,0]], B=[[3,-1],[4,2]]일 때 AB의 첫째 행 성분의 합을 구하시오.", "첫째 행은 (10,0)입니다.", "10", "행렬곱 첫 행 합", "numeric"),
        ("미지수행렬 복원", "X+[[1,2],[3,4]]=[[5,0],[1,7]]일 때 행렬 X의 모든 성분의 합을 구하시오.", "성분별 차를 구합니다.", "3", "미지수행렬 복원", "numeric"),
        ("행렬합의 미지수", "A=[[1,2],[3,4]], B=[[x,1],[2,y]]이고 A+B=[[4,3],[5,8]]일 때 x+y의 값을 구하시오.", "성분별로 비교합니다.", "6", "행렬합의 미지수", "numeric"),
        ("스칼라배와 합", "2A-B=[[1,3],[-1,5]], A=[[2,1],[0,3]]일 때 행렬 B의 모든 성분의 합을 구하시오.", "B=2A-주어진 행렬", "8", "스칼라배와 합", "numeric"),
        ("곱의 한 성분", "A=[[1,-1],[2,3]], B=[[4,2],[-1,5]]일 때 AB의 (2,1)성분을 구하시오.", "둘째 행과 첫째 열의 곱", "5", "곱의 한 성분", "numeric"),
        ("곱의 대각합", "A=[[2,1],[-1,3]], B=[[1,4],[2,-2]]일 때 AB의 대각성분의 합을 구하시오.", "(1,1), (2,2) 성분만 계산합니다.", "1", "곱의 대각합", "numeric"),
        ("행렬방정식 첫 줄", "A=[[1,2],[0,1]], X=[[x,y],[z,w]]이고 AX=[[5,1],[2,3]]일 때 x+y의 값을 구하시오.", "둘째 행에서 z,w를 먼저 읽습니다.", "2", "행렬방정식 첫 줄", "numeric"),
        ("가환 조건 역추적", "A=[[1,1],[0,1]], B=[[a,b],[0,a]]일 때 AB=BA이다. a+b=5일 때 b의 값을 구하시오.", "이 구조에서는 항상 가환합니다.", "5-a", "가환 조건 역추적", "exact"),
        ("제곱행렬 읽기", "A=[[1,1],[0,1]]일 때 A^2의 (1,2)성분을 구하시오.", "상삼각 구조를 곱합니다.", "2", "제곱행렬 읽기", "numeric"),
        ("행렬곱 역산", "A=[[2,0],[1,1]], B=[[x,1],[3,y]]이고 AB=[[4,2],[5,3]]일 때 x+y의 값을 구하시오.", "첫째 행으로 x, 둘째 행으로 y를 구합니다.", "3", "행렬곱 역산", "numeric"),
        ("열벡터 해석", "A=[[1,2],[-1,3]]가 벡터 (x,y)를 (5,7)로 보낸다. x+y의 값을 구하시오.", "연립방정식으로 봅니다.", "3", "열벡터 해석", "numeric"),
        ("행렬식 대신 면적비", "A=[[1,2],[3,4]]가 벡터 (1,0), (0,1)을 보내 얻는 두 벡터의 평행사변형 넓이를 구하시오.", "열벡터 (1,3), (2,4)의 넓이", "2", "행렬변환 면적비", "numeric"),
        ("대칭행렬 조건", "A=[[1,a],[b,4]]가 대칭행렬이고 a+b=6일 때 a의 값을 구하시오.", "대칭행렬은 a=b", "3", "대칭행렬 조건", "numeric"),
        ("영행렬 만들기", "A=[[2,-1],[1,3]], X=[[x,0],[0,y]]이고 AX의 각 행의 합이 모두 0일 때 x+y의 값을 구하시오.", "행의 합 조건을 두 식으로 세웁니다.", "0", "영행렬 만들기", "numeric"),
        ("곱의 열 해석", "A=[[1,0],[2,1]], B=[[3,1],[4,-2]]일 때 AB의 둘째 열의 성분의 합을 구하시오.", "둘째 열만 계산합니다.", "-1", "곱의 열 해석", "numeric"),
        ("교환자 구조", "A=[[1,1],[0,1]], B=[[0,1],[0,0]]일 때 AB-BA의 (1,2)성분을 구하시오.", "두 곱을 각각 계산합니다.", "0", "교환자 구조", "numeric"),
        ("행렬식 대신 고정점", "A=[[1,1],[0,1]]가 벡터 (x,y)를 자기 자신으로 보내도록 하는 모든 (x,y)를 구하시오.", "A(x,y)=(x,y)", "y=0", "행렬의 고정점", "exact"),
        ("세 행렬의 곱 한 성분", "A=[[1,2],[0,1]], B=[[1,0],[3,1]], C=[[2,-1],[1,0]]일 때 ABC의 (1,1)성분을 구하시오.", "BC를 먼저 구한 뒤 A를 곱합니다.", "10", "세 행렬의 곱 한 성분", "numeric"),
        ("행렬 방정식과 합", "X+A=B, A=[[1,-2],[3,0]], B=[[4,1],[-1,5]]일 때 행렬 X의 모든 성분의 합을 구하시오.", "X=B-A", "8", "행렬 방정식과 합", "numeric"),
    ],
    "common2-coordinate": [
        ("평행이동한 원", "원 x^2+y^2=4를 x축의 방향으로 3, y축의 방향으로 -2만큼 평행이동한 원의 방정식을 구하시오.", "중심이 (3,-2)로 갑니다.", "(x-3)^2+(y+2)^2=4", "평행이동한 원", "exact"),
        ("중점과 거리", "점 A(-1,2), B(5,6)의 중점 M과 원점 O 사이의 거리를 구하시오.", "M=(2,4)", "2√5", "중점과 거리", "exact"),
        ("직선의 x절편", "점 (2,-1)을 지나고 기울기가 3인 직선의 x절편을 구하시오.", "y=3x-7", "7/3", "직선의 x절편", "numeric"),
        ("수직이등분선과 축", "점 A(1,4), B(5,0)를 잇는 선분의 수직이등분선이 y축과 만나는 점의 y좌표를 구하시오.", "중점은 (3,2), 기울기는 1", "-1", "수직이등분선과 축", "numeric"),
        ("두 점을 지나는 직선", "점 A(1,3), B(5,11)을 지나는 직선의 방정식을 구하시오.", "기울기는 2입니다.", "y=2x+1", "두 점을 지나는 직선", "exact"),
        ("수직선의 절편", "직선 2x-y+3=0에 수직이고 점 (1,-2)를 지나는 직선의 y절편을 구하시오.", "기울기 2의 역수 부호를 바꿉니다.", "-3/2", "수직선의 절편", "numeric"),
        ("중점과 직선 결합", "점 A(-1,4), B(5,0)의 중점을 지나고 x축과 만나는 직선이 y=x+b일 때 b의 값을 구하시오.", "중점을 y=x+b에 대입합니다.", "0", "중점과 직선 결합", "numeric"),
        ("원과 접선", "중심이 (2,-1), 반지름이 5인 원의 방정식을 구하시오.", "(x-2)^2+(y+1)^2=25", "(x-2)^2+(y+1)^2=25", "원의 표준형 복원", "exact"),
        ("점과 직선 거리", "점 (3,-1)에서 직선 3x+4y-5=0까지의 거리를 구하시오.", "|9-4-5|/5", "0", "점과 직선 거리", "numeric"),
        ("두 직선의 교점", "직선 x+y=5와 2x-y=1의 교점의 좌표를 구하시오.", "연립방정식을 풉니다.", "(2,3)", "두 직선의 교점", "exact"),
        ("내분점 좌표", "점 A(-2,1), B(7,10)을 2:1로 내분하는 점의 좌표를 구하시오.", "내분공식", "(4,7)", "내분점 좌표", "exact"),
        ("삼각형 넓이", "세 점 A(0,0), B(4,1), C(2,5)가 이루는 삼각형의 넓이를 구하시오.", "밑변과 높이 또는 행렬식", "9", "삼각형 넓이 좌표형", "numeric"),
        ("평행선 판정", "점 A(1,2), B(4,8), C(-2,0), D(1,6)에 대하여 직선 AB와 CD의 관계를 판정하시오.", "기울기를 비교합니다.", "평행", "평행선 판정", "exact"),
        ("원 위의 점 조건", "원 x^2+y^2-4x+6y-12=0의 중심을 구하시오.", "완전제곱식", "(2,-3)", "원 위의 점 조건", "exact"),
        ("현의 수직이등분선", "원 x^2+y^2=25 위의 두 점 A(3,4), B(3,-4)를 잇는 현 AB의 수직이등분선의 방정식을 구하시오.", "AB는 수직선입니다.", "y=0", "현의 수직이등분선", "exact"),
        ("이등변삼각형 조건", "점 A(-2,0), B(2,0), P(0,k)에 대하여 삼각형 PAB의 넓이가 12일 때 k의 값을 모두 구하시오.", "밑변은 4, 높이는 |k|", "k=6 또는 k=-6", "이등변삼각형 조건", "exact"),
        ("원과 직선의 접점 거리", "원 x^2+y^2=13과 직선 2x+3y=1의 관계를 판정하시오.", "중심에서 직선까지 거리와 반지름 비교", "만난다", "원과 직선의 위치관계", "exact"),
        ("좌표 대칭 이동", "점 (4,-3)을 x축에 대하여 대칭이동한 점을 P, y축에 대하여 대칭이동한 점을 Q라 할 때 PQ의 길이를 구하시오.", "P=(4,3), Q=(-4,-3)", "10", "좌표 대칭 이동", "numeric"),
        ("사각형 넓이", "점 A(0,0), B(4,0), C(5,3), D(1,3)이 이루는 사각형의 넓이를 구하시오.", "평행사변형 구조를 봅니다.", "12", "사각형 넓이", "numeric"),
        ("직선과 축의 교점", "직선 3x-2y+6=0이 x축, y축과 만나는 점을 각각 A, B라 할 때 삼각형 OAB의 넓이를 구하시오.", "절편을 구해 넓이 계산", "3", "직선과 축의 교점", "numeric"),
        ("두 원의 중심거리", "두 원 x^2+y^2=9, (x-6)^2+y^2=16의 중심거리와 반지름의 합을 비교하여 위치관계를 판정하시오.", "중심거리는 6, 반지름의 합은 7", "서로 만난다", "두 원의 위치관계", "exact"),
    ],
    "common2-set": [
        ("공집합 판정", "집합 A={x|x는 3의 배수이면서 3보다 작은 자연수}의 원소의 개수를 구하시오.", "조건을 만족하는 자연수를 찾습니다.", "0", "공집합 판정", "numeric"),
        ("명제의 역과 대우 구분", "명제 'x가 10의 배수이면 x는 5의 배수이다.'의 대우를 쓰시오.", "부정하고 순서를 바꿉니다.", "x가 5의 배수가 아니면 x는 10의 배수가 아니다", "명제의 역과 대우 구분", "exact"),
        ("합집합 원소 수", "n(A-B)=7, n(B-A)=5, n(A∩B)=4일 때 n(A∪B)의 값을 구하시오.", "서로 겹치지 않는 세 부분을 더합니다.", "16", "합집합 원소 수", "numeric"),
        ("필요충분조건 판정", "명제 'x가 4의 배수이면 x가 짝수이다.'에서 x가 짝수인 것은 x가 4의 배수인 것의 어떤 조건인지 쓰시오.", "결론 쪽 조건입니다.", "필요조건", "필요충분조건 판정", "exact"),
        ("집합 세 부분 복원", "전체집합 U의 원소 수가 50, n(A)=24, n(B)=19, n(A∩B)=8일 때 n((A-B)∪(B-A))의 값을 구하시오.", "대칭차의 원소 수입니다.", "27", "집합 세 부분 복원", "numeric"),
        ("포함배제로 역추적", "n(A∪B)=28, n(A)=17, n(B)=15일 때 n(A∩B)의 값을 구하시오.", "17+15-n(A∩B)=28", "4", "포함배제로 역추적", "numeric"),
        ("여집합과 교집합", "전체집합 U의 원소 수가 40, n(A)=18, n(B)=23, n(A∪B)=30일 때 n(A^c∩B^c)의 값을 구하시오.", "n((A∪B)^c)=40-30", "10", "여집합과 교집합", "numeric"),
        ("대칭차 역산", "집합 A, B에 대하여 n(A△B)=14, n(A)=11, n(B)=9일 때 n(A∩B)의 값을 구하시오.", "11+9-2n(A∩B)=14", "3", "대칭차 역산", "numeric"),
        ("드모르간 응용", "(A∩B)^c 와 같은 집합을 쓰시오.", "교집합의 여집합", "A^c∪B^c", "드모르간 응용", "exact"),
        ("짝수 명제의 대우", "명제 'x^2가 짝수이면 x는 짝수이다.'의 대우를 쓰시오.", "가정과 결론을 부정하고 순서를 바꿉니다.", "x가 홀수이면 x^2는 홀수이다", "짝수 명제의 대우", "exact"),
        ("필요조건 판정", "명제 'x가 6의 배수이면 x는 2의 배수이다.'에서 x가 2의 배수인 것은 x가 6의 배수인 것의 어떤 조건인지 쓰시오.", "결론 쪽 조건입니다.", "필요조건", "필요조건 판정", "exact"),
        ("진리값 조합", "명제 p→q가 참이고 p가 참일 때 q의 진리값을 쓰시오.", "참이면 q도 참이어야 합니다.", "참", "진리값 조합", "exact"),
        ("부분집합과 원소 수", "A⊂B, n(A)=7, n(B)=20일 때 n(B-A)의 값을 구하시오.", "20-7", "13", "부분집합과 원소 수", "numeric"),
        ("교집합 여집합 합", "전체집합 U의 원소 수가 36, n(A)=18, n(B)=14, n(A∩B)=5일 때 n(A^c∪B^c)의 값을 구하시오.", "(A∩B)^c", "31", "교집합 여집합 합", "numeric"),
        ("역의 진위 판정", "명제 'x가 4의 배수이면 x는 짝수이다.'의 역의 참, 거짓을 판정하시오.", "짝수라고 모두 4의 배수는 아닙니다.", "거짓", "역의 진위 판정", "exact"),
        ("명제와 집합 연결", "자연수 전체의 집합에서 A={x|x는 6의 배수}, B={x|x는 3의 배수}일 때 A⊂B 인지 판정하시오.", "6의 배수는 모두 3의 배수입니다.", "참", "명제와 집합 연결", "exact"),
        ("차집합 두 번", "n(A)=19, n(B)=12, n(A-B)=11일 때 n(B-A)의 값을 구하시오.", "교집합을 먼저 구합니다.", "4", "차집합 두 번", "numeric"),
        ("포함배제 세팅", "n(A∪B)=25, n(A-B)=9, n(B-A)=6일 때 n(A∩B)의 값을 구하시오.", "9+6+n(A∩B)=25", "10", "포함배제 세팅", "numeric"),
        ("명제의 충분조건 반례", "명제 'x가 소수이면 x는 홀수이다.'가 거짓임을 보이는 반례를 하나 쓰시오.", "2를 떠올립니다.", "2", "충분조건 반례", "exact"),
        ("부분집합 개수", "원소의 개수가 4인 집합의 부분집합의 개수를 구하시오.", "2^4", "16", "부분집합 개수", "numeric"),
        ("대칭차와 합집합 비교", "n(A∪B)=20, n(A△B)=14일 때 n(A∩B)의 값을 구하시오.", "n(A△B)=n(A∪B)-n(A∩B)", "6", "대칭차와 합집합 비교", "numeric"),
    ],
    "common2-function": [
        ("일차함수 기울기 복원", "일차함수 f(x)=ax+1이 f(4)=13을 만족할 때 a의 값을 구하시오.", "4a+1=13", "3", "일차함수 기울기 복원", "numeric"),
        ("절댓값 최소값", "함수 y=|x+2|+5의 최솟값을 구하시오.", "절댓값은 0 이상입니다.", "5", "절댓값 최소값", "numeric"),
        ("역함수와 원함수 합", "f(x)=x-4의 역함수를 g라 할 때 f(3)+g(3)의 값을 구하시오.", "g(3)=7", "6", "역함수와 원함수 합", "numeric"),
        ("그래프 이동과 절편", "함수 y=x^2를 x축의 방향으로 1만큼, y축의 방향으로 2만큼 평행이동한 그래프의 y절편을 구하시오.", "y=(x-1)^2+2", "3", "그래프 이동과 절편", "numeric"),
        ("역함수 값 복원", "일차함수 f(x)=2x-3의 역함수 f^(-1)(5)의 값을 구하시오.", "2x-3=5", "4", "역함수 값 복원", "numeric"),
        ("합성함수 해석", "f(x)=x+2, g(x)=x^2-1 일 때 g(f(3))의 값을 구하시오.", "f(3)=5", "24", "합성함수 해석", "numeric"),
        ("평행이동 그래프", "함수 y=x^2의 그래프를 x축의 방향으로 2만큼, y축의 방향으로 -3만큼 평행이동한 함수식을 구하시오.", "x→x-2, y→y-3", "y=(x-2)^2-3", "평행이동 그래프", "exact"),
        ("절댓값 그래프 판정", "함수 y=|x-2|+1의 꼭짓점 좌표를 구하시오.", "절댓값 안과 밖의 이동", "(2,1)", "절댓값 그래프 판정", "exact"),
        ("정의역으로 값 찾기", "함수 f(x)=1/(x-3)의 정의역을 구하시오.", "분모가 0이 아니어야 합니다.", "x≠3", "정의역으로 값 찾기", "exact"),
        ("치역 판정", "함수 y=(x-1)^2+4의 최솟값을 구하시오.", "제곱항은 0 이상입니다.", "4", "치역 판정", "numeric"),
        ("합성 후 역함수", "f(x)=3x+1, g(x)=x-2 일 때 (f∘g)(x)를 구하시오.", "g(x)를 먼저 넣습니다.", "3x-5", "합성 후 역함수", "exact"),
        ("함숫값 조건으로 상수 복원", "함수 f(x)=ax+4가 f(3)=10을 만족할 때 a의 값을 구하시오.", "3a+4=10", "2", "함숫값 조건 상수 복원", "numeric"),
        ("두 그래프 교점", "그래프 y=2x+1과 y=-x+7의 교점의 x좌표를 구하시오.", "2x+1=-x+7", "2", "두 그래프 교점", "numeric"),
        ("구간별 함수값", "함수 f(x)=x+1 (x<0), x^2 (x≥0)에 대하여 f(-2)+f(3)의 값을 구하시오.", "각 구간에 맞게 계산합니다.", "8", "구간별 함수값", "numeric"),
        ("대칭축 읽기", "이차함수 y=x^2-6x+8의 대칭축을 구하시오.", "완전제곱식 또는 -b/2a", "x=3", "대칭축 읽기", "exact"),
        ("그래프와 축 교점", "함수 y=x^2-5x+6의 x절편의 합을 구하시오.", "(x-2)(x-3)=0", "5", "그래프와 축 교점", "numeric"),
        ("함수값의 차", "함수 f(x)=x^2-2x에 대하여 f(3)-f(1)의 값을 구하시오.", "각 값을 대입합니다.", "4", "함수값의 차", "numeric"),
        ("역함수 방정식", "함수 f(x)=x+4의 역함수를 g라 할 때 g(1)의 값을 구하시오.", "x+4=1", "-3", "역함수 방정식", "numeric"),
        ("절댓값 부등식 그래프", "부등식 |x-2|<3의 해집합을 구하시오.", "-3<x-2<3", "-1<x<5", "절댓값 부등식 그래프", "exact"),
        ("합성조건 상수 찾기", "f(x)=x+a, g(x)=2x-1에 대하여 f(g(2))=8일 때 a의 값을 구하시오.", "g(2)=3", "5", "합성조건 상수 찾기", "numeric"),
        ("최댓값·최솟값 구간형", "함수 y=-x^2+4x-1의 최댓값을 구하시오.", "꼭짓점 x=2", "3", "최댓값 최솟값 구간형", "numeric"),
    ],
    "algebra-exp-log": [
        ("지수식 차수 맞추기", "3^(2x-1)=27을 만족하는 실수 x의 값을 구하시오.", "3^(2x-1)=3^3", "2", "지수식 차수 맞추기", "numeric"),
        ("로그와 지수 동시조건", "log_2(x-1)=3을 만족하는 x의 값을 구하시오.", "x-1=2^3", "9", "로그와 지수 동시조건", "numeric"),
        ("지수합 묶기", "3^x+3^(x+1)=36을 만족하는 실수 x의 값을 구하시오.", "3^x(1+3)=36", "2", "지수합 묶기", "numeric"),
        ("로그 곱셈방정식", "log_3 x + log_3(x-2)=2를 만족하는 실수 x의 값을 구하시오.", "x(x-2)=9", "1+√10", "로그 곱셈방정식", "exact"),
        ("지수와 역수의 결합", "2^x + 2^(-x)=5/2를 만족하는 모든 실수 x의 값을 구하시오.", "t=2^x로 두고 t+1/t=5/2를 풉니다.", "x=1 또는 x=-1", "지수와 역수의 결합", "exact"),
        ("밑변환 비교", "log_4(x+3)=2를 만족하는 실수 x의 값을 구하시오.", "(x+3)=4^2", "13", "밑변환 비교", "numeric"),
        ("로그 정의역 포함", "log_5(2x-1)=1을 만족하는 x의 값을 구하시오.", "2x-1=5, x>1/2", "3", "로그 정의역 포함", "numeric"),
        ("지수와 역수 결합", "5^x=1/25를 만족하는 실수 x의 값을 구하시오.", "1/25=5^-2", "-2", "지수와 역수 결합", "numeric"),
        ("상용로그 차", "log_10 1000 - log_10 0.1의 값을 구하시오.", "3-(-1)", "4", "상용로그 차", "numeric"),
        ("로그 부등식 시작", "log_2(x-3)>1을 만족하는 정수 x의 최솟값을 구하시오.", "x-3>2", "6", "로그 부등식 시작", "numeric"),
        ("지수방정식의 역이동", "27^(x-1)=9를 만족하는 실수 x의 값을 구하시오.", "3^(3x-3)=3^2", "5/3", "지수방정식의 역이동", "numeric"),
        ("로그합의 값", "log_2 8 + log_2 4 - log_2 2의 값을 구하시오.", "3+2-1", "4", "로그합의 값", "numeric"),
        ("치환 후 역치환", "3^(2x)-10·3^x+9=0을 만족하는 모든 실수 x의 값을 구하시오.", "t=3^x", "x=0 또는 x=2", "치환 후 역치환", "exact"),
        ("지수와 로그의 교차", "log_3(x+1)=2x-2 를 만족하는 자연수 x의 값을 구하시오.", "작은 자연수 후보를 대입합니다.", "1", "지수와 로그의 교차", "numeric"),
        ("로그식 정리", "log_2 32 - log_2 4 + log_2 8의 값을 구하시오.", "5-2+3", "6", "로그식 정리", "numeric"),
        ("지수등식 비교", "4^x=8^(x-1)를 만족하는 실수 x의 값을 구하시오.", "2^(2x)=2^(3x-3)", "3", "지수등식 비교", "numeric"),
        ("로그 정의역 끝판정", "함수 y=log_3(2x+4)의 정의역을 구하시오.", "2x+4>0", "x>-2", "로그 정의역 끝판정", "exact"),
    ],
    "calc1-limit": [
        ("인수분해 후 대입", "lim(x→2) (x^3-8)/(x^2-4)의 값을 구하시오.", "(x^3-8)=(x-2)(x^2+2x+4), x^2-4=(x-2)(x+2)", "3", "이차분모와 세제곱 약분", "numeric"),
        ("세제곱과 이차분모", "lim(x→2) (x^3-8)/(x^2+x-6)의 값을 구하시오.", "(x-2)(x^2+2x+4), (x^2+x-6)=(x-2)(x+3)", "12/5", "세제곱과 이차분모", "numeric"),
        ("루트 유리화 기본", "lim(x→0) (√(9+x)-3)/x의 값을 구하시오.", "켤레를 곱해 유리화합니다.", "1/6", "상수항이 큰 루트 유리화", "numeric"),
        ("무한대 최고차 비교", "lim(x→∞) (5x^2-3x+1)/(2x^2+x-4)의 값을 구하시오.", "최고차항 계수", "5/2", "무한대 최고차 비교", "numeric"),
        ("연속조건 상수", "함수 f(x)=((√(x+5)-3)/(x-4)) (x≠4), k (x=4)가 x=4에서 연속일 때 k의 값을 구하시오.", "유리화 후 분모를 약분합니다.", "1/6", "루트형 연속조건 상수", "numeric"),
        ("좌우극한 일치", "함수 f(x)=2x+1 (x<1), ax-2 (x≥1)가 x=1에서 연속일 때 a의 값을 구하시오.", "3=a-2", "5", "좌우극한 일치", "numeric"),
        ("변화율 극한", "lim(x→0) ((3+x)^2-9)/x의 값을 구하시오.", "분자 전개", "6", "변화율 극한", "numeric"),
        ("분모분자 동차", "lim(x→∞) (3x^3+1)/(x^3-2x+5)의 값을 구하시오.", "동차꼴 계수", "3", "분모분자 동차", "numeric"),
        ("근 주위 약분", "lim(x→-1) (x^2-1)/(x+1)의 값을 구하시오.", "(x-1)(x+1)", "-2", "근 주위 약분", "numeric"),
        ("서로 다른 루트의 차", "lim(x→0) (√(1+x)-√(1-x))/x의 값을 구하시오.", "켤레를 곱해 두 근호를 한 번에 정리합니다.", "1", "서로 다른 루트의 차", "numeric"),
        ("조각함수 점값 복원", "함수 f(x)=x^2+ax (x<2), 3x-2 (x≥2)가 x=2에서 연속일 때 a의 값을 구하시오.", "4+2a=4", "0", "조각함수 점값 복원", "numeric"),
        ("0/0형 분해", "lim(x→2) (x^2+x-6)/(x-2)의 값을 구하시오.", "(x-2)(x+3)", "5", "영영형 분해", "numeric"),
        ("매개변수 포함 극한", "lim(x→2) (x^2+ax-6)/(x-2)가 유한한 값을 가지도록 하는 a의 값을 구하시오.", "분자가 x=2에서 0", "1", "매개변수 포함 극한", "numeric"),
        ("역함수 없이 연속", "함수 f(x)=1/(x-1)의 x=2에서의 함수값과 극한값의 합을 구하시오.", "둘 다 1", "2", "역함수 없이 연속", "numeric"),
        ("계수 비교형 극한", "lim(x→∞) (7x-2)/(3x+5)의 값을 구하시오.", "1차식 계수비", "7/3", "계수 비교형 극한", "numeric"),
        ("연속과 정의역", "함수 y=√(x-2)의 정의역의 시작점을 구하시오.", "x-2≥0", "2", "연속과 정의역", "numeric"),
        ("기울기 해석형", "함수 f(x)=x^2의 x=1에서의 순간변화율을 극한으로 계산한 값을 구하시오.", "[(1+h)^2-1]/h", "2", "기울기 해석형", "numeric"),
    ],
    "probstat-probability": [
        ("여사건으로 접기", "앞면이 나올 확률이 1/2인 동전을 4번 던질 때 적어도 1번 앞면이 나올 확률을 구하시오.", "모두 뒷면인 경우를 뺍니다.", "15/16", "여사건으로 접기", "numeric"),
        ("정확히 한 번 성공", "성공확률이 1/3인 시행을 3번 반복할 때 정확히 1번 성공할 확률을 구하시오.", "3C1(1/3)(2/3)^2", "4/9", "정확히 한 번 성공", "numeric"),
        ("주사위 합 조건", "두 개의 주사위를 동시에 던질 때 눈의 합이 9 이상일 확률을 구하시오.", "유리한 경우 10", "5/18", "주사위 합 조건", "numeric"),
        ("적어도 한 색", "빨간 공 4개, 파란 공 3개가 들어 있는 주머니에서 공 2개를 동시에 꺼낼 때 적어도 1개가 빨간 공일 확률을 구하시오.", "모두 파란 공인 경우를 뺍니다.", "6/7", "적어도 한 색", "numeric"),
        ("같은 홀짝", "1부터 8까지 적힌 카드 8장 중 2장을 동시에 뽑을 때 두 수의 홀짝이 같을 확률을 구하시오.", "짝짝 또는 홀홀", "3/7", "같은 홀짝", "numeric"),
        ("조건부 빨간공", "빨간 공 3개, 파란 공 2개, 초록 공 1개가 들어 있는 주머니에서 공 2개를 동시에 꺼냈다. 적어도 1개가 빨간 공일 때 두 공이 모두 빨간 공일 확률을 구하시오.", "조건부확률", "1/4", "조건부 빨간공", "numeric"),
        ("앞면이 정확히 두 번", "앞면이 나올 확률이 1/2인 동전을 5번 던질 때 정확히 2번 앞면이 나올 확률을 구하시오.", "5C2(1/2)^5", "5/16", "앞면이 정확히 두 번", "numeric"),
        ("색이 다른 두 공", "빨간 공 2개, 파란 공 3개, 노란 공 1개가 들어 있는 주머니에서 공 2개를 동시에 꺼낼 때 두 공의 색이 서로 다를 확률을 구하시오.", "전체에서 같은 색을 뺍니다.", "11/15", "색이 다른 두 공", "numeric"),
        ("순서 있는 주사위", "두 주사위를 순서 있게 던질 때 첫째 눈이 둘째 눈보다 클 확률을 구하시오.", "같지 않은 경우를 반으로 나눕니다.", "5/12", "순서 있는 주사위", "numeric"),
        ("구간 확률 해석", "0부터 9까지의 숫자가 적힌 카드 10장 중 1장을 뽑을 때 3의 배수일 확률을 구하시오.", "0,3,6,9", "2/5", "구간 확률 해석", "numeric"),
        ("복원추출 확률", "빨간 공 2개, 파란 공 3개가 들어 있는 주머니에서 한 번 꺼낸 뒤 다시 넣고 또 한 번 꺼낼 때 두 번 모두 빨간 공일 확률을 구하시오.", "독립시행", "4/25", "복원추출 확률", "numeric"),
        ("비복원추출 확률", "빨간 공 2개, 파란 공 3개가 들어 있는 주머니에서 연속 두 번 꺼낼 때 두 번째가 빨간 공일 확률을 구하시오.", "대칭성 또는 전체개수", "2/5", "비복원추출 확률", "numeric"),
        ("적어도 한 짝수", "한 개의 주사위를 세 번 던질 때 적어도 한 번 짝수가 나올 확률을 구하시오.", "모두 홀수인 경우를 뺍니다.", "7/8", "적어도 한 짝수", "numeric"),
        ("두 사건의 독립", "사건 A, B가 독립이고 P(A)=1/2, P(B)=2/3일 때 P(A∩B)를 구하시오.", "독립이면 곱합니다.", "1/3", "두 사건의 독립", "numeric"),
        ("조건부 주사위 합", "두 주사위를 동시에 던졌을 때 첫째 주사위가 홀수라는 조건 아래 눈의 합이 7일 확률을 구하시오.", "조건부 표본공간 18개", "1/6", "조건부 주사위 합", "numeric"),
        ("확률변수 없이 경우수", "서로 다른 5장의 카드 중 2장을 뽑을 때 특정 카드 A가 포함될 확률을 구하시오.", "A를 포함하는 경우 4개", "2/5", "특정 카드 포함", "numeric"),
        ("교대 시행 성공", "성공확률이 2/5인 시행을 2번 반복할 때 처음에는 실패하고 두 번째에는 성공할 확률을 구하시오.", "(3/5)(2/5)", "6/25", "교대 시행 성공", "numeric"),
    ],
    "calc2-integral": [
        ("지수 적분 시작", "∫_0^1 e^x dx의 값을 구하시오.", "원시함수는 e^x", "e-1", "지수 적분 시작", "exact"),
        ("삼각 적분 기본", "∫_0^(π/2) cos x dx의 값을 구하시오.", "원시함수는 sin x", "1", "삼각 적분 기본", "numeric"),
        ("치환 없는 다항 적분", "∫_1^3 (2x+1) dx의 값을 구하시오.", "x^2+x", "8", "치환 없는 다항 적분", "numeric"),
        ("도함수 분자 로그적분", "∫_0^1 (2x)/(x^2+1) dx의 값을 구하시오.", "u=x^2+1", "ln2", "도함수 분자 로그적분", "exact"),
        ("합성상한 미분", "F(x)=∫_0^(x^2) (t+1) dt 일 때 F'(1)의 값을 구하시오.", "미적분학의 기본정리와 합성함수 미분", "4", "합성상한 미분", "numeric"),
        ("짝함수 대칭 적분", "∫_-2^2 x^2 dx의 값을 구하시오.", "2∫_0^2 x^2 dx", "16/3", "짝함수 대칭 적분", "numeric"),
        ("한쪽으로 치우친 세제곱 적분", "∫_1^3 x^3 dx의 값을 구하시오.", "원시함수 x^4/4를 이용해 끝값을 비교합니다.", "20", "한쪽으로 치우친 세제곱 적분", "numeric"),
        ("역수형 적분", "∫_1^2 1/x dx의 값을 구하시오.", "원시함수는 ln x", "ln2", "역수형 적분", "exact"),
        ("정적분 평균값", "함수 y=x의 구간 [0,4]에서의 평균값을 구하시오.", "(1/4)∫_0^4 x dx", "2", "정적분 평균값", "numeric"),
        ("치환 정적분 간단형", "∫_0^1 2x(x^2+1)^3 dx의 값을 구하시오.", "u=x^2+1", "15/4", "치환 정적분 간단형", "numeric"),
        ("삼각과 상수 결합", "∫_0^π (sin x + 1) dx의 값을 구하시오.", "∫sin x + ∫1", "π+2", "삼각과 상수 결합", "exact"),
        ("미분과 적분의 연결", "f(x)=∫_1^x 3t^2 dt 일 때 f(2)의 값을 구하시오.", "t^3", "7", "미분과 적분의 연결", "numeric"),
        ("상한 복원", "a>0일 때 ∫_0^a (x+2) dx=8을 만족하는 a의 값을 구하시오.", "a^2/2+2a=8", "2", "상한 복원", "numeric"),
        ("선형분자 치환", "∫_0^1 (2x+1)/(x^2+x+1) dx의 값을 구하시오.", "u=x^2+x+1", "ln3", "선형분자 치환", "exact"),
        ("구간 넓이 해석", "구간 [0,2]에서 y=4-x^2와 x축으로 둘러싸인 부분의 넓이를 구하시오.", "∫_0^2 (4-x^2) dx", "16/3", "구간 넓이 해석", "numeric"),
        ("상하한 바꾸기", "∫_2^0 (x-1) dx의 값을 구하시오.", "-∫_0^2 (x-1)dx", "0", "상하한 바꾸기", "numeric"),
        ("적분값 차이", "∫_0^2 (3x^2-2x) dx의 값을 구하시오.", "x^3-x^2", "4", "적분값 차이", "numeric"),
    ],
    "geometry-space": [
        ("세 점 거리 비교", "점 A(1,2,3), B(4,6,3), C(1,2,7)에 대하여 AB+AC의 값을 구하시오.", "AB=5, AC=4", "9", "세 점 거리 비교", "numeric"),
        ("중점과 원점 거리", "점 A(2,0,4), B(6,2,0)의 중점을 M이라 할 때 OM의 길이의 제곱을 구하시오.", "M=(4,1,2)", "21", "중점과 원점 거리", "numeric"),
        ("삼각형 무게중심", "점 A(0,0,0), B(3,0,0), C(0,6,3)가 이루는 삼각형의 무게중심 좌표를 구하시오.", "좌표 평균", "(1,2,1)", "삼각형 무게중심", "exact"),
        ("축평행 사면체 부피", "O(0,0,0), A(4,0,0), B(0,3,0), C(0,0,2)가 이루는 사면체의 부피를 구하시오.", "abc/6", "4", "축평행 사면체 부피", "numeric"),
        ("구의 중심 반지름", "방정식 (x-1)^2+(y+2)^2+(z-3)^2=8이 나타내는 구의 중심을 구하시오.", "표준형에서 중심 좌표를 바로 읽습니다.", "(1,-2,3)", "표준형 구의 중심", "exact"),
        ("내분점 거리", "점 A(1,1,1), B(7,4,10)를 1:2로 내분하는 점 P의 좌표를 구하시오.", "내분공식", "(3,2,4)", "내분점 거리", "exact"),
        ("축까지의 거리", "점 P(2,-1,5)에서 x축까지의 거리의 제곱을 구하시오.", "y^2+z^2", "26", "축까지의 거리", "numeric"),
        ("두 직선 대신 두 점", "점 A(-1,2,0), B(3,2,4) 사이의 거리를 구하시오.", "차벡터 (4,0,4)", "4√2", "두 직선 대신 두 점", "exact"),
        ("구 위의 점 판정", "점 (3,0,4)가 구 x^2+y^2+z^2=25 위에 있는지 판정하시오.", "9+0+16=25", "있다", "구 위의 점 판정", "exact"),
        ("중점 세 개의 합", "점 A(1,2,3), B(3,4,5), C(5,6,7)에 대하여 선분 AB, BC의 중점을 각각 M, N이라 할 때 MN의 길이를 구하시오.", "M=(2,3,4), N=(4,5,6)", "2√3", "중점 세 개의 합", "exact"),
        ("사면체 높이감", "점 O(0,0,0), A(2,0,0), B(0,2,0), C(0,0,9)에 대하여 삼각형 OAB를 밑면으로 하는 사면체 OABC의 부피를 구하시오.", "밑면 넓이와 높이를 곱한 뒤 3으로 나눕니다.", "6", "밑면과 높이로 보는 사면체 부피", "numeric"),
        ("좌표평면 위 거리", "점 P(2,3,6)에서 평면 z=0까지의 거리를 구하시오.", "z좌표의 절댓값", "6", "좌표평면 위 거리", "numeric"),
        ("직육면체 대각선", "직육면체의 세 모서리 길이가 2,3,6일 때 공간대각선의 길이를 구하시오.", "√(2^2+3^2+6^2)", "7", "직육면체 대각선", "numeric"),
        ("두 점의 내분과 합", "점 A(0,0,0), B(6,3,9)를 2:1로 내분하는 점 P의 좌표의 합을 구하시오.", "P=(4,2,6)", "12", "두 점의 내분과 합", "numeric"),
        ("구의 반지름 복원", "방정식 (x-1)^2+(y+2)^2+(z-3)^2=r^2가 점 (4,2,3)을 지날 때 r의 값을 구하시오.", "거리공식", "5", "구의 반지름 복원", "numeric"),
        ("평행이동 거리 보존", "점 A(1,2,3)를 (2,-1,4)만큼 평행이동한 점 B를 구하시오.", "좌표별로 더합니다.", "(3,1,7)", "평행이동 거리 보존", "exact"),
        ("두 점과 원점 넓이 대신 길이", "점 A(2,0,0), B(0,3,4)에 대하여 OA^2+OB^2의 값을 구하시오.", "4+25", "29", "두 점과 원점 길이", "numeric"),
    ],
    "probstat-counting": [
        ("발표조 조건 분리", "남학생 5명, 여학생 4명 중 3명의 발표조를 만들 때 여학생이 적어도 1명 포함되도록 하는 방법의 수를 구하시오.", "전체에서 여학생 0명을 뺍니다.", "74", "발표조 조건 분리", "numeric"),
        ("연속 좌석 배치", "서로 다른 6명이 일렬로 앉을 때 A와 B가 이웃하도록 앉는 방법의 수를 구하시오.", "AB를 한 묶음으로 봅니다.", "240", "연속 좌석 배치", "numeric"),
        ("원탁 맞은편", "서로 다른 8명이 원탁에 앉을 때 A와 B가 서로 맞은편에 앉는 방법의 수를 구하시오.", "A를 고정합니다.", "720", "원탁 맞은편", "numeric"),
        ("세 자리 짝수", "숫자 0,1,2,3,4,5 중 서로 다른 3개를 골라 만들 수 있는 세 자리 짝수의 개수를 구하시오.", "끝자리를 먼저 자릅니다.", "52", "세 자리 짝수", "numeric"),
        ("문자 중복 배열", "LEVEL의 문자를 모두 일렬로 배열하는 방법의 수를 구하시오.", "L 2개, E 2개", "30", "문자 중복 배열", "numeric"),
        ("남녀 교대 좌석", "남학생 3명, 여학생 3명을 일렬로 세울 때 남녀가 번갈아 서는 방법의 수를 구하시오.", "시작 성별을 나눕니다.", "72", "남녀 교대 좌석", "numeric"),
        ("자연수해와 상한", "자연수 x, y, z가 x+y+z=8을 만족하고 x≤4일 때 순서쌍 (x,y,z)의 개수를 구하시오.", "전체 자연수해에서 x≥5를 뺍니다.", "18", "자연수해와 상한", "numeric"),
        ("팀장 포함 조합", "10명 중 4명의 운영진을 뽑고 그중 한 명을 팀장으로 정하는 방법의 수를 구하시오.", "10C4·4", "840", "팀장 포함 조합", "numeric"),
        ("최단경로 장애물", "좌표평면에서 (0,0)에서 (4,4)까지 오른쪽과 위쪽으로만 이동할 때 점 (2,2)를 지나지 않는 최단경로의 수를 구하시오.", "전체에서 (2,2)를 지나는 경우를 뺍니다.", "34", "최단경로 장애물", "numeric"),
        ("적어도 둘 포함", "A, B, C, D, E, F 중 3명을 뽑을 때 A와 B 중 적어도 한 명이 포함되도록 하는 방법의 수를 구하시오.", "여사건을 뺍니다.", "16", "적어도 둘 포함", "numeric"),
        ("같은 색 공 분배", "서로 같은 공 8개를 서로 다른 상자 3개에 1개 이상씩 넣는 방법의 수를 구하시오.", "자연수해 개수", "21", "같은 색 공 분배", "numeric"),
        ("네 자리 합 조건", "숫자 1,2,3,4,5 중 서로 다른 4개를 골라 네 자리 수를 만들 때 각 자리 숫자의 합이 12가 되는 수의 개수를 구하시오.", "가능한 숫자 조합을 먼저 고릅니다.", "24", "네 자리 합 조건", "numeric"),
        ("이웃 금지 원순열", "서로 다른 7명이 원탁에 앉을 때 A와 B가 서로 이웃하지 않도록 앉는 방법의 수를 구하시오.", "전체 원순열에서 이웃하는 경우를 뺍니다.", "480", "이웃 금지 원순열", "numeric"),
        ("두 블록 사이 거리", "서로 다른 8명 중 A, B는 이웃하고 C, D는 서로 이웃하지 않도록 일렬로 세우는 방법의 수를 구하시오.", "AB를 묶고 C,D는 여사건으로 뺍니다.", "2160", "두 블록 사이 거리", "numeric"),
        ("정수해와 짝수 제한", "자연수 x, y가 x+y=12를 만족하고 x가 짝수일 때 순서쌍 (x,y)의 개수를 구하시오.", "짝수 x 후보를 셉니다.", "5", "정수해와 짝수 제한", "numeric"),
        ("서로 다른 역할 배정", "6명 중 회장, 부회장, 총무를 서로 다르게 정하는 방법의 수를 구하시오.", "6P3", "120", "서로 다른 역할 배정", "numeric"),
        ("가로세로 문자열", "서로 다른 문자 A, B, C, D를 한 줄로 배열할 때 A가 B보다 앞에 오는 배열의 수를 구하시오.", "대칭성", "12", "가로세로 문자열", "numeric"),
    ],
    "probstat-statistics": [
        ("평균과 합 연결", "자료 3, 5, 7, x의 평균이 6일 때 x의 값을 구하시오.", "합이 24", "9", "평균과 합 연결", "numeric"),
        ("평균 이동", "자료 1, 3, 5, 7의 평균에 4를 더한 값을 구하시오.", "원평균은 4", "8", "평균 이동", "numeric"),
        ("분산 직접 계산", "자료 2, 4, 6의 분산을 구하시오.", "평균은 4", "8/3", "분산 직접 계산", "numeric"),
        ("표준편차 배율", "자료의 표준편차가 3일 때 모든 값에 2를 곱한 새 자료의 표준편차를 구하시오.", "배율만큼 변합니다.", "6", "표준편차 배율", "numeric"),
        ("평행이동 분산", "자료의 분산이 5일 때 모든 값에 7을 더한 새 자료의 분산을 구하시오.", "분산은 변하지 않습니다.", "5", "평행이동 분산", "numeric"),
        ("이항분포 기대값", "확률변수 X가 이항분포 B(6, 1/3)를 따를 때 E(X)를 구하시오.", "np", "2", "이항분포 기대값 심화", "numeric"),
        ("이항분포 흩어짐", "확률변수 X가 이항분포 B(6, 1/3)를 따를 때 V(X)를 구하시오.", "np(1-p)", "4/3", "이항분포 분산 심화", "numeric"),
        ("가중평균으로 평균", "값 1, 4, 7의 도수가 각각 2, 1, 3일 때 평균을 구하시오.", "가중평균", "9/2", "도수분포 가중평균", "numeric"),
        ("새 자료 평균", "자료의 평균이 5일 때 모든 값에 2를 곱하고 1을 더한 새 자료의 평균을 구하시오.", "2×5+1", "11", "새 자료 평균", "numeric"),
        ("새 자료 분산", "자료의 분산이 4일 때 모든 값에 -3을 곱한 새 자료의 분산을 구하시오.", "배율의 제곱 9", "36", "새 자료 분산", "numeric"),
        ("확률변수 평균", "확률변수 X가 0,1,2를 각각 확률 1/4, 1/2, 1/4로 가질 때 E(X)를 구하시오.", "Σxp", "1", "확률변수 평균", "numeric"),
        ("확률변수 분산", "확률변수 X가 1,3을 각각 확률 1/2, 1/2로 가질 때 V(X)를 구하시오.", "E(X)=2, E(X^2)=5", "1", "확률변수 분산", "numeric"),
        ("평균조건 미지수", "자료 2, 4, a, 10의 평균이 6일 때 a의 값을 구하시오.", "합이 24", "8", "평균조건 미지수", "numeric"),
        ("중심화 제곱합", "자료 1, 2, 3, 4의 평균에서의 편차 제곱의 합을 구하시오.", "평균은 2.5", "5", "중심화 제곱합", "numeric"),
        ("이항분포 최빈값 느낌", "확률변수 X가 이항분포 B(4,1/2)를 따를 때 P(X=2)의 값을 구하시오.", "4C2(1/2)^4", "3/8", "이항분포 가운데값", "numeric"),
        ("표준편차와 분산", "자료의 표준편차가 √5일 때 분산을 구하시오.", "제곱합니다.", "5", "표준편차와 분산", "numeric"),
        ("평균 조건 차이", "두 자료집합 A, B의 평균이 각각 4, 7이고 원소 수가 각각 3, 2일 때 전체 평균을 구하시오.", "가중평균", "26/5", "평균 조건 차이", "numeric"),
    ],
    "calc1-integral": [
        ("다항함수 정적분", "∫_0^3 (x^2+1) dx의 값을 구하시오.", "x^3/3+x", "12", "다항함수 정적분", "numeric"),
        ("절댓값 분할 적분", "∫_-1^2 |x| dx의 값을 구하시오.", "0에서 나눕니다.", "5/2", "절댓값 분할 적분", "numeric"),
        ("직선과 포물선 넓이", "구간 [0,2]에서 y=2x와 y=x^2로 둘러싸인 부분의 넓이를 구하시오.", "∫(2x-x^2)", "4/3", "직선과 포물선 넓이", "numeric"),
        ("원시함수 평가", "함수 F(x)=∫_1^x (3t-1) dt 일 때 F(3)의 값을 구하시오.", "3t^2/2-t", "8", "원시함수 평가", "numeric"),
        ("짝함수 넓이", "∫_-2^2 (x^2+3) dx의 값을 구하시오.", "2∫_0^2", "34/3", "짝함수 넓이", "numeric"),
        ("홀함수 취소", "∫_-3^3 (x^3-2x) dx의 값을 구하시오.", "홀함수", "0", "홀함수 취소", "numeric"),
        ("평균값 계산", "함수 y=2x+1의 구간 [1,3]에서의 평균값을 구하시오.", "(1/2)∫_1^3", "5", "평균값 계산 적분형", "numeric"),
        ("적분값으로 상수 찾기", "a>0일 때 ∫_0^a x dx=18을 만족하는 a의 값을 구하시오.", "a^2/2=18", "6", "적분값으로 상수 찾기", "numeric"),
        ("역함수형 분모", "∫_0^1 1/(x+2) dx의 값을 구하시오.", "ln(x+2)", "ln(3/2)", "역함수형 분모", "exact"),
        ("적분과 부호", "∫_1^3 (x-2) dx의 값을 구하시오.", "대칭성 또는 직접 계산", "0", "적분과 부호", "numeric"),
        ("넓이와 절편", "직선 y=4-x가 좌표축과 이루는 삼각형의 넓이를 정적분으로 구하시오.", "∫_0^4 (4-x)dx", "8", "넓이와 절편", "numeric"),
        ("두 적분의 차", "∫_0^2 (x^2+3x) dx - ∫_0^2 x dx의 값을 구하시오.", "적분을 합칩니다.", "20/3", "두 적분의 차", "numeric"),
        ("구간 뒤집기", "∫_3^1 (2x+1) dx의 값을 구하시오.", "-∫_1^3", "-10", "구간 뒤집기", "numeric"),
        ("부분 넓이 합", "구간 [0,3]에서 y=|x-1|와 x축으로 둘러싸인 부분의 넓이를 구하시오.", "1에서 나눕니다.", "5/2", "부분 넓이 합", "numeric"),
        ("미분가능 함수 적분", "f'(x)=2x+3이고 f(0)=1일 때 f(2)의 값을 구하시오.", "f(2)-f(0)=∫_0^2 f'(x)dx", "11", "미분가능 함수 적분", "numeric"),
        ("정적분 도형해석", "구간 [0,1]에서 y=1-x^2가 x축 위에 있다. 넓이를 구하시오.", "∫_0^1 (1-x^2)dx", "2/3", "정적분 도형해석", "numeric"),
        ("직선 평균 높이", "구간 [0,4]에서 직선 y=6-x의 평균 높이를 구하시오.", "(1/4)∫_0^4", "4", "직선 평균 높이", "numeric"),
    ],
    "calc2-seq-limit": [
        ("유리식 수열 기본", "lim(n→∞) (3n+1)/(n+2)의 값을 구하시오.", "최고차항 계수", "3", "유리식 수열 기본", "numeric"),
        ("제곱근 수열 유리화", "lim(n→∞) n(√(n^2+2n)-n)의 값을 구하시오.", "유리화합니다.", "1", "제곱근 수열 유리화", "numeric"),
        ("둘째항으로 첫째항 복원", "무한등비급수의 둘째항이 1이고 공비가 1/2일 때 그 합을 구하시오.", "첫째항을 먼저 복원한 뒤 합 공식을 적용합니다.", "4", "둘째항으로 첫째항 복원", "numeric"),
        ("부분합의 극한", "a_n=Σ(k=1~n) 1/3^k 일 때 lim a_n을 구하시오.", "등비급수 합", "1/2", "부분합의 극한 첫형", "numeric"),
        ("점화식 극한", "수열 {a_n}이 a_(n+1)=(a_n+4)/5 를 만족하고 수렴할 때 그 극한을 구하시오.", "L=(L+4)/5", "1", "점화식 극한 첫형", "numeric"),
        ("차수 비교 수열", "lim(n→∞) (5n^2-1)/(2n^2+3n)의 값을 구하시오.", "최고차항 비교", "5/2", "차수 비교 수열", "numeric"),
        ("망원합 수열", "a_n=Σ(k=1~n) 1/(k(k+2)) 일 때 lim a_n을 구하시오.", "부분분수로 분해합니다.", "3/4", "망원합 수열", "numeric"),
        ("둘째항이 음수인 급수", "무한등비급수의 둘째항이 -1이고 공비가 -1/3일 때 그 합을 구하시오.", "첫째항을 먼저 복원한 뒤 합 공식을 적용합니다.", "9/4", "둘째항이 음수인 급수", "numeric"),
        ("세제곱 분모 수열", "lim(n→∞) (2n^3+1)/(n^3-4n+2)의 값을 구하시오.", "최고차항", "2", "세제곱 분모 수열", "numeric"),
        ("루트차 상수형", "lim(n→∞) (√(n^2+5n)-n) 의 값을 구하시오.", "유리화 후 n으로 나눕니다.", "5/2", "루트차 상수형", "numeric"),
        ("등비합 조건", "무한등비급수의 첫째항이 6, 공비가 1/3일 때 그 합을 구하시오.", "6/(1-1/3)", "9", "등비합 조건", "numeric"),
        ("점화식 두번째", "수열 {a_n}이 a_(n+1)=(2a_n+3)/5 를 만족하고 수렴할 때 그 극한을 구하시오.", "L=(2L+3)/5", "1", "점화식 두번째", "numeric"),
        ("분수형 부분합", "a_n=Σ(k=1~n) 1/2^(k+1) 일 때 lim a_n을 구하시오.", "첫째항 1/4, 공비 1/2", "1/2", "분수형 부분합", "numeric"),
        ("제곱근 차와 n", "lim(n→∞) n(√(1+1/n)-1)을 구하시오.", "유리화합니다.", "1/2", "제곱근 차와 n", "numeric"),
        ("유리화된 분모", "lim(n→∞) (n+1)/(2n-3)의 값을 구하시오.", "계수비", "1/2", "유리화된 분모", "numeric"),
        ("합성 점화식", "수열 {a_n}이 a_1=2, a_(n+1)=1+1/a_n 을 만족할 때 수렴한다면 그 극한을 구하시오.", "L=1+1/L", "(1+√5)/2", "합성 점화식", "exact"),
        ("자연수 계차수열", "a_n=1-1/(n+1) 일 때 lim a_n을 구하시오.", "1에 수렴합니다.", "1", "자연수 계차수열", "numeric"),
    ],
    "algebra-trig": [
        ("사분면과 합", "sinθ=5/13이고 θ가 제2사분면에 있을 때 sinθ+cosθ의 값을 구하시오.", "제2사분면에서는 cosθ<0", "-7/13", "사분면과 합", "numeric"),
        ("사분면과 sec-tan", "cosθ=3/5이고 θ가 제4사분면에 있을 때 secθ-tanθ의 값을 구하시오.", "secθ=5/3, tanθ=-4/3", "3", "사분면과 sec-tan", "numeric"),
        ("탄젠트에서 사인복원", "tanθ=3/4이고 θ가 제1사분면에 있을 때 sinθ의 값을 구하시오.", "3-4-5 삼각형", "3/5", "탄젠트에서 사인복원", "numeric"),
        ("이중각 사인", "sinθ=3/5, cosθ=4/5일 때 sin2θ의 값을 구하시오.", "2sinθcosθ", "24/25", "이중각 사인", "numeric"),
        ("이중각 코사인", "sinθ=5/13이고 θ가 제1사분면에 있을 때 cos2θ의 값을 구하시오.", "cos^2θ-sin^2θ", "119/169", "이중각 코사인", "numeric"),
        ("삼각방정식 첫형", "0≤θ<2π에서 sinθ=√3/2를 만족하는 θ의 값을 모두 구하시오.", "기본각은 π/3", "π/3 또는 2π/3", "삼각방정식 첫형", "exact"),
        ("삼각방정식 둘째형", "0≤θ<2π에서 cosθ=-1/2를 만족하는 θ의 값을 모두 구하시오.", "기본각은 π/3", "2π/3 또는 4π/3", "삼각방정식 둘째형", "exact"),
        ("합으로 값 구하기", "sinθ=4/5, cosθ=3/5일 때 (sinθ+cosθ)^2의 값을 구하시오.", "제곱을 전개합니다.", "49/25", "합으로 값 구하기", "numeric"),
        ("차로 값 구하기", "sinθ=12/13, cosθ=5/13일 때 sinθ-cosθ의 값을 구하시오.", "바로 빼면 됩니다.", "7/13", "차로 값 구하기", "numeric"),
        ("세컨트와 코탄젠트", "0<θ<π/2에서 cosθ=8/17일 때 secθ+cotθ의 값을 구하시오.", "sinθ=15/17", "257/120", "세컨트와 코탄젠트", "numeric"),
        ("삼각식 곱", "0<θ<π/2에서 sinθ=5/13일 때 (1-sinθ)(1+sinθ)의 값을 구하시오.", "1-sin^2θ=cos^2θ", "144/169", "삼각식 곱", "numeric"),
        ("탄젠트 제곱 합", "tanθ=3/4일 때 1+tan^2θ의 값을 구하시오.", "1+tan^2θ=sec^2θ", "25/16", "탄젠트 제곱 합", "numeric"),
        ("사인 코사인 곱", "sinθ=8/17이고 θ가 제2사분면에 있을 때 sinθ·cosθ의 값을 구하시오.", "cosθ는 음수", "-120/289", "사인 코사인 곱", "numeric"),
        ("탄젠트와 합", "tanθ=-3/4이고 θ가 제4사분면에 있을 때 sinθ+cosθ의 값을 구하시오.", "sinθ=-3/5, cosθ=4/5", "1/5", "탄젠트와 합", "numeric"),
        ("반각 없이 제곱", "cosθ=-5/13이고 θ가 제2사분면에 있을 때 sin^2θ의 값을 구하시오.", "1-cos^2θ", "144/169", "반각 없이 제곱", "numeric"),
        ("직각삼각형 복원", "tanθ=12/5이고 θ가 제1사분면에 있을 때 cosθ의 값을 구하시오.", "5-12-13 삼각형", "5/13", "직각삼각형 복원", "numeric"),
        ("기본각 판정", "0≤θ<2π에서 tanθ=1을 만족하는 θ의 값을 모두 구하시오.", "기본각은 π/4", "π/4 또는 5π/4", "기본각 판정", "exact"),
    ],
    "geometry-conic": [
        ("포물선 초점 읽기", "포물선 y^2=12x의 초점을 구하시오.", "4p=12", "(3,0)", "포물선 초점 읽기", "exact"),
        ("포물선 준선 읽기", "포물선 x^2=16y의 준선의 방정식을 구하시오.", "4p=16", "y=-4", "포물선 준선 읽기", "exact"),
        ("타원 단축 복원", "타원 x^2/36 + y^2/b^2 = 1의 초점이 (±4,0)일 때 b^2의 값을 구하시오.", "c^2=a^2-b^2", "20", "타원 단축 복원", "numeric"),
        ("타원 이심률", "타원 x^2/49 + y^2/25 = 1의 이심률을 구하시오.", "c^2=24", "2√6/7", "타원 이심률", "exact"),
        ("쌍곡선 초점", "쌍곡선 x^2/16 - y^2/9 = 1의 초점을 구하시오.", "c^2=25", "(±5,0)", "쌍곡선 초점", "exact"),
        ("쌍곡선 점근선", "쌍곡선 x^2/9 - y^2/4 = 1의 점근선의 방정식을 구하시오.", "y=±(b/a)x", "y=±(2/3)x", "쌍곡선 점근선", "exact"),
        ("타원 장축 길이", "타원 x^2/25 + y^2/9 = 1의 장축의 길이를 구하시오.", "2a", "10", "타원 장축 길이", "numeric"),
        ("쌍곡선 실축 길이", "쌍곡선 x^2/36 - y^2/13 = 1의 실축의 길이를 구하시오.", "2a", "12", "쌍곡선 실축 길이", "numeric"),
        ("포물선 꼭짓점", "방정식 (y-1)^2=8(x-2)가 나타내는 포물선의 꼭짓점을 구하시오.", "표준형", "(2,1)", "포물선 꼭짓점", "exact"),
        ("포물선 초점 이동", "(x+1)^2=20(y-3)인 포물선의 초점을 구하시오.", "4p=20", "(-1,8)", "포물선 초점 이동", "exact"),
        ("타원 초점거리", "타원 x^2/16 + y^2/7 = 1의 두 초점 사이의 거리를 구하시오.", "c^2=9", "6", "타원 초점거리", "numeric"),
        ("쌍곡선 b^2 복원", "쌍곡선의 초점이 (±10,0), 꼭짓점이 (±6,0)일 때 b^2의 값을 구하시오.", "b^2=c^2-a^2", "64", "쌍곡선 b제곱 복원", "numeric"),
        ("타원 방정식 쓰기", "장축의 꼭짓점이 (±5,0), 단축의 꼭짓점이 (0,±3)인 타원의 방정식을 구하시오.", "a=5, b=3", "x^2/25+y^2/9=1", "타원 방정식 쓰기", "exact"),
        ("쌍곡선 방정식 쓰기", "실축의 꼭짓점이 (±4,0), 점근선의 기울기가 ±3/4인 쌍곡선의 방정식을 구하시오.", "a=4, b=3", "x^2/16-y^2/9=1", "쌍곡선 방정식 쓰기", "exact"),
        ("포물선 p값", "포물선 x^2=-24y에서 p의 값을 구하시오.", "4p=-24", "-6", "포물선 p값", "numeric"),
        ("타원 초점합", "타원의 초점이 (±2,0)이고 장축의 길이가 10일 때 b^2의 값을 구하시오.", "a=5, c=2", "21", "타원 초점합", "numeric"),
        ("쌍곡선 중심이동", "(x-1)^2/9 - (y+2)^2/16 = 1인 쌍곡선의 중심을 구하시오.", "표준형 중심", "(1,-2)", "쌍곡선 중심이동", "exact"),
    ],
    "calc1-diff": [
        ("도함수 값 계산", "함수 f(x)=x^3-2x의 도함수 f'(2)의 값을 구하시오.", "f'(x)=3x^2-2", "10", "도함수 값 계산", "numeric"),
        ("순간변화율 복원", "함수 f(x)=x^2+3x의 x=1에서의 순간변화율을 구하시오.", "f'(x)=2x+3", "5", "순간변화율 복원", "numeric"),
        ("접선의 기울기", "함수 y=x^2-4x+1의 x=3에서의 접선의 기울기를 구하시오.", "y'=2x-4", "2", "접선의 기울기", "numeric"),
        ("포물선 접선 방정식", "함수 y=x^2의 x=1에서의 접선의 방정식을 구하시오.", "기울기 2, 점 (1,1)", "y=2x-1", "포물선 접선 방정식", "exact"),
        ("미분계수 0 조건", "함수 y=x^3-3x^2의 미분계수가 0이 되는 x의 값을 모두 구하시오.", "y'=3x(x-2)", "x=0 또는 x=2", "미분계수 영조건", "exact"),
        ("증가구간 판정", "함수 y=x^2-2x+3이 증가하는 구간을 구하시오.", "y'=2x-2>0", "x>1", "증가구간 판정", "exact"),
        ("감소구간 판정", "함수 y=-x^2+4x가 감소하는 구간을 구하시오.", "y'=-2x+4<0", "x>2", "감소구간 판정", "exact"),
        ("극댓값 읽기", "함수 y=-x^2+6x-5의 최댓값을 구하시오.", "꼭짓점 x=3", "4", "극댓값 읽기", "numeric"),
        ("도함수로 상수 찾기", "함수 f(x)=x^3+ax^2+1이 x=1에서 극값을 가질 때 a의 값을 구하시오.", "f'(1)=0", "-3/2", "도함수로 상수 찾기", "numeric"),
        ("접선과 y절편", "함수 y=x^2+1의 x=2에서의 접선의 y절편을 구하시오.", "접선은 y=4x-3", "-3", "접선과 y절편", "numeric"),
        ("평행한 접선", "함수 y=x^2-2x의 접선이 직선 y=4x+1과 평행하도록 하는 x의 값을 구하시오.", "y'=2x-2=4", "3", "평행한 접선", "numeric"),
        ("수평접선 찾기", "함수 y=x^3-6x^2+9x의 수평접선이 생기는 x의 값을 모두 구하시오.", "y'=3(x-1)(x-3)", "x=1 또는 x=3", "수평접선 찾기", "exact"),
        ("도함수 부호 전환", "함수 y=x^3-3x의 극솟값을 구하시오.", "x=1에서 극솟값", "-2", "도함수 부호 전환", "numeric"),
        ("미분가능 함수값", "함수 f(x)=x^2-ax+4가 x=3에서 접선의 기울기가 1일 때 a의 값을 구하시오.", "f'(3)=6-a", "5", "미분가능 함수값", "numeric"),
        ("삼차식 접선 복원", "함수 y=x^3-x의 x=1에서의 접선의 방정식을 구하시오.", "기울기 2, 점 (1,0)", "y=2x-2", "삼차식 접선 복원", "exact"),
        ("도함수와 함수값 결합", "함수 y=x^2-5x+4의 x=1에서의 함수값과 도함수값의 합을 구하시오.", "f(1)=0, f'(1)=-3", "-3", "도함수와 함수값 결합", "numeric"),
        ("극값의 x좌표 합", "함수 y=x^3-6x^2+9x+1의 극값이 되는 x좌표의 합을 구하시오.", "y'=3(x-1)(x-3)", "4", "극값의 x좌표 합", "numeric"),
    ],
    "calc2-diff": [
        ("지수함수 도함수", "함수 y=e^x의 x=0에서의 도함수값을 구하시오.", "도함수는 e^x", "1", "지수함수 도함수", "numeric"),
        ("로그함수 도함수", "함수 y=ln x의 x=e에서의 도함수값을 구하시오.", "도함수는 1/x", "1/e", "로그함수 도함수", "exact"),
        ("지수 접선 기울기", "함수 y=e^x+2x의 x=0에서의 접선의 기울기를 구하시오.", "e^0+2", "3", "지수 접선 기울기", "numeric"),
        ("로그 접선 방정식", "함수 y=ln x의 x=1에서의 접선의 방정식을 구하시오.", "기울기 1, 점 (1,0)", "y=x-1", "로그 접선 방정식", "exact"),
        ("곱의 미분", "함수 y=xe^x의 도함수를 구하시오.", "곱의 미분법", "e^x(x+1)", "곱의 미분", "exact"),
        ("합성 지수 미분", "함수 y=e^(2x-1)의 도함수를 구하시오.", "합성함수 미분", "2e^(2x-1)", "합성 지수 미분", "exact"),
        ("합성 로그 미분", "함수 y=ln(3x+1)의 도함수를 구하시오.", "합성함수 미분", "3/(3x+1)", "합성 로그 미분", "exact"),
        ("지수와 로그 합", "함수 y=e^x+ln x의 x=1에서의 도함수값을 구하시오.", "e+1", "e+1", "지수와 로그 합", "exact"),
        ("극값 조건 지수형", "함수 y=e^x-2x가 극값을 갖는 x의 값을 구하시오.", "y'=e^x-2=0", "ln2", "극값 조건 지수형", "exact"),
        ("증가감소 지수형", "함수 y=e^x-x가 증가하는 구간을 구하시오.", "e^x-1>0", "x>0", "증가감소 지수형", "exact"),
        ("접선과 축 교점", "함수 y=e^x의 x=0에서의 접선이 y축과 만나는 점의 y좌표를 구하시오.", "접선은 y=x+1", "1", "접선과 축 교점", "numeric"),
        ("자연로그 값차", "함수 y=ln x의 x=e^2에서의 도함수값을 구하시오.", "1/e^2", "1/e^2", "자연로그 값차", "exact"),
        ("지수식 최솟값", "함수 y=e^x-x의 최솟값을 구하시오.", "x=0에서 최소", "1", "지수식 최솟값", "numeric"),
        ("로그식 감소구간", "함수 y=ln x - x가 감소하는 구간을 구하시오.", "1/x-1<0", "x>1", "로그식 감소구간", "exact"),
        ("지수와 다항 결합", "함수 y=x^2+e^x의 x=0에서의 접선의 기울기를 구하시오.", "0+1", "1", "지수와 다항 결합", "numeric"),
        ("로그와 직선 평행", "함수 y=ln x의 접선이 직선 y=(1/2)x와 평행하도록 하는 x의 값을 구하시오.", "1/x=1/2", "2", "로그와 직선 평행", "numeric"),
        ("도함수의 합 평가", "함수 y=e^(x+1)-ln x의 x=1에서의 도함수값을 구하시오.", "e^2-1", "e^2-1", "도함수의 합 평가", "exact"),
    ],
    "geometry-vector": [
        ("벡터 합의 길이", "벡터 a=(2,1), b=(1,2)에 대하여 |a+b|의 값을 구하시오.", "a+b=(3,3)", "3√2", "벡터 합의 길이", "exact"),
        ("벡터 차의 길이 제곱", "벡터 a=(4,1), b=(1,-1)에 대하여 |2a-b|^2의 값을 구하시오.", "2a-b=(7,3)", "58", "결합벡터 길이 제곱", "numeric"),
        ("내적 직각 조건", "벡터 a=(1,3), b=(2,-1)에 대하여 (a+kb)·b=0일 때 k의 값을 구하시오.", "a·b+k|b|^2=0", "1/5", "직교 선형결합", "numeric"),
        ("스칼라배 방향", "벡터 a=(2,-4), b=(-1,2)에 대하여 a+tb가 x축과 평행할 때 t의 값을 구하시오.", "y성분이 0이 되도록 맞춥니다.", "2", "축평행 선형결합", "numeric"),
        ("삼각형 넓이 벡터", "점 O(0,0), A(3,1), B(1,4)일 때 평행사변형 OAPB의 넓이를 구하시오.", "|det|", "11", "평행사변형 넓이", "numeric"),
        ("성분합 문제", "벡터 a=(1,3), b=(2,-1)에 대하여 3a-2b의 각 성분의 합을 구하시오.", "3a-2b=(-1,11)", "10", "성분합 문제", "numeric"),
        ("평행 조건", "벡터 a=(2,5), b=(4,k)가 서로 평행일 때 k의 값을 구하시오.", "성분비 2배", "10", "평행 조건", "numeric"),
        ("내적과 길이", "벡터 a, b에 대하여 |a|=2, |b|=5, a·b=6일 때 |a+b|^2의 값을 구하시오.", "4+25+12", "41", "내적과 합벡터 길이", "numeric"),
        ("벡터와 각의 종류", "벡터 a=(1,1), b=(-2,1)이 이루는 각의 종류를 판정하시오.", "내적 -1", "둔각", "벡터와 각의 종류", "exact"),
        ("중점벡터", "점 A(2,3), B(6,1)의 중점 M의 위치벡터를 구하시오.", "M=(4,2)", "(4,2)", "중점벡터", "exact"),
        ("합벡터와 내적", "벡터 a=(1,2), b=(2,1)에 대하여 (a+b)·a 의 값을 구하시오.", "(3,3)·(1,2)", "9", "자기벡터와 합벡터 내적", "numeric"),
        ("사영 없이 분해", "벡터 a=(3,4), b=(0,5)에 대하여 (a+b)·(a-b)의 값을 구하시오.", "(a+b)·(a-b)=|a|^2-|b|^2", "0", "합차 내적", "numeric"),
        ("길이가 같은 조건", "벡터 a=(x,2), b=(1,5)가 |a|=|b|를 만족할 때 x^2의 값을 구하시오.", "x^2+4=26", "22", "길이가 같은 조건", "numeric"),
        ("일차결합 0벡터", "벡터 a=(1,2), b=(2,-1)에 대하여 pa+qb=(0,0)를 만족하는 정수 p, q의 비 p:q를 구하시오.", "영벡터는 둘 다 0뿐입니다.", "0:0", "일차결합 영벡터", "exact"),
        ("벡터와 점의 이동", "점 P(1,2)를 벡터 (3,-4)만큼 평행이동한 점 Q의 좌표를 구하시오.", "좌표별로 더합니다.", "(4,-2)", "벡터와 점의 이동", "exact"),
        ("내분점 벡터", "점 A(1,1), B(7,4)를 2:1로 내분하는 점 P의 좌표를 구하시오.", "내분공식", "(5,3)", "내분점 벡터", "exact"),
        ("평행사변형 대각선", "벡터 a=(2,3), b=(4,1)가 이루는 평행사변형의 한 대각선 벡터 a+b의 길이를 구하시오.", "a+b=(6,4)", "2√13", "평행사변형 대각선", "exact"),
    ],
}


GENERIC_CURATED_KILLER_SPECS: dict[str, list[tuple[str, str, str, str, str, str]]] = {
    "common2-set": [
        ("포함배제와 여집합", "전체집합 U의 원소 수가 40, n(A)=18, n(B)=15, n(A∩B)=6일 때 n((A∪B)^c)의 값을 구하시오.", "n(A∪B)=27", "13", "포함배제와 여집합", "numeric"),
        ("대칭차의 원소 수", "집합 A, B에 대하여 n(A)=17, n(B)=12, n(A∩B)=5일 때 n(A△B)의 값을 구하시오.", "17+12-2×5", "19", "대칭차 원소 수", "numeric"),
        ("명제의 역 쓰기", "명제 'x가 6의 배수이면 x는 3의 배수이다.'의 역을 쓰시오.", "가정과 결론의 위치를 바꿉니다.", "x가 3의 배수이면 x는 6의 배수이다", "명제의 역", "exact"),
        ("충분조건 판정", "명제 'x=0이면 xy=0이다.'에서 x=0은 xy=0의 어떤 조건인지 적으시오.", "가정이 결론을 보장합니다.", "충분조건", "조건 판정", "exact"),
        ("드모르간 법칙", "집합 A, B에 대하여 (A∪B)^c와 같은 집합을 쓰시오.", "합집합의 여집합은 교집합의 여집합으로 바뀝니다.", "A^c∩B^c", "드모르간 법칙", "exact"),
        ("차집합 두 개의 합", "전체집합 U의 원소 수가 50, n(A)=24, n(B)=18, n(A∩B)=7일 때 n(A-B)+n(B-A)의 값을 구하시오.", "24-7과 18-7을 더합니다.", "28", "차집합 합", "numeric"),
        ("거짓 명제의 진리값", "명제 p→q가 거짓이고 p가 참일 때 q의 진리값을 구하시오.", "참→거짓일 때만 거짓 명제가 됩니다.", "거짓", "명제 진리값 역추적", "exact"),
        ("포함하는 부분집합 개수", "A⊂B, n(A)=8, n(B)=15일 때 A를 포함하는 B의 부분집합의 개수를 구하시오.", "B-A의 원소 7개를 선택 여부로 보면 됩니다.", "128", "포함하는 부분집합 개수", "numeric"),
        ("교집합 역추적", "n(A)=12, n(B)=9, n(A∪B)=16일 때 n(A∩B)의 값을 구하시오.", "12+9-n(A∩B)=16", "5", "포함배제 역추적", "numeric"),
    ],
    "algebra-exp-log": [
        ("지수방정식 직판", "2^(x+1)=16을 만족하는 실수 x의 값을 구하시오.", "16=2^4", "3", "지수방정식 직판", "numeric"),
        ("로그방정식 정의역", "log_3(x-1)=2를 만족하는 실수 x의 값을 구하시오.", "x-1=3^2", "10", "로그방정식 정의역", "numeric"),
        ("로그합 조건", "log_2 x + log_2(x-2)=3을 만족하는 실수 x의 값을 구하시오.", "x(x-2)=2^3", "4", "로그합 조건", "numeric"),
        ("치환형 지수방정식", "4^x-5·2^x+4=0을 만족하는 모든 실수 x의 값을 구하시오.", "t=2^x로 치환하면 t^2-5t+4=0", "x=0 또는 x=2", "치환형 지수방정식", "exact"),
        ("로그값 계산", "log_5 125 + log_5(1/5)의 값을 구하시오.", "3+(-1)", "2", "로그값 계산", "numeric"),
        ("밑이 다른 로그 비교", "log_2(x+1)=log_4 16을 만족하는 실수 x의 값을 구하시오.", "log_4 16=2", "3", "밑이 다른 로그 비교", "numeric"),
        ("지수형 역변환", "9^(x-1)=1/3을 만족하는 실수 x의 값을 구하시오.", "3^(2x-2)=3^-1", "1/2", "지수형 역변환", "numeric"),
        ("상용로그 합", "log_10 100 + log_10 0.01의 값을 구하시오.", "2+(-2)", "0", "상용로그 합", "numeric"),
        ("로그함수 정의역", "함수 y=log_2(x-3)의 정의역을 구하시오.", "x-3>0", "x>3", "로그함수 정의역", "exact"),
    ],
    "algebra-trig": [
        ("사분면에서 탄젠트 복원", "sinθ=3/5이고 θ가 제2사분면에 있을 때 tanθ의 값을 구하시오.", "제2사분면에서는 cosθ가 음수입니다.", "-3/4", "사분면에서 탄젠트 복원", "numeric"),
        ("사분면에서 선형결합", "cosθ=5/13이고 θ가 제4사분면에 있을 때 sinθ-cosθ의 값을 구하시오.", "sinθ=-12/13", "-17/13", "사분면에서 선형결합", "numeric"),
        ("tan에서 sin+cos", "tanθ=3/4이고 θ가 제3사분면에 있을 때 sinθ+cosθ의 값을 구하시오.", "sinθ=-3/5, cosθ=-4/5", "-7/5", "tan에서 sin+cos", "numeric"),
        ("이중각 첫 연결", "sinθ=4/5이고 θ가 제2사분면에 있을 때 sin2θ의 값을 구하시오.", "sin2θ=2sinθcosθ", "-24/25", "이중각 첫 연결", "numeric"),
        ("삼각항등식 활용", "cosθ=-12/13이고 θ가 제2사분면에 있을 때 1+tan^2θ의 값을 구하시오.", "1+tan^2θ=sec^2θ", "169/144", "삼각항등식 활용", "numeric"),
        ("각의 후보 복원", "0<θ<π에서 sinθ=1/2일 때 θ의 값을 모두 구하시오.", "기본각은 π/6입니다.", "π/6 또는 5π/6", "각의 후보 복원", "exact"),
        ("cos와 sin의 차", "tanθ=-5/12이고 θ가 제4사분면에 있을 때 cosθ-sinθ의 값을 구하시오.", "sinθ=-5/13, cosθ=12/13", "17/13", "cos와 sin의 차", "numeric"),
        ("sec와 cot 결합", "0<θ<π/2에서 cosθ=12/13일 때 secθ-cotθ의 값을 구하시오.", "secθ=13/12, cotθ=12/5", "-79/60", "sec와 cot 결합", "numeric"),
        ("곱으로 접기", "0<θ<π/2에서 cosθ=12/13일 때 (1-sinθ)(1+sinθ)의 값을 구하시오.", "1-sin^2θ=cos^2θ", "144/169", "sin 제곱으로 접기", "numeric"),
    ],
    "calc1-limit": [
        ("인수분해형 일차 약분", "lim(x→2) (x^2-5x+6)/(x-2)의 값을 구하시오.", "(x-2)(x-3)으로 인수분해합니다.", "-1", "인수분해형 일차 약분", "numeric"),
        ("세제곱 구조 읽기", "lim(x→-2) (x^3+8)/(x+2)의 값을 구하시오.", "x^3+8=(x+2)(x^2-2x+4)", "12", "세제곱 구조 읽기", "numeric"),
        ("유리화 기본형", "lim(x→0) (√(1+3x)-1)/x의 값을 구하시오.", "켤레를 곱해 유리화합니다.", "3/2", "유리화 기본형", "numeric"),
        ("연속 조건의 매개변수", "함수 f(x)=((x^2+x-6)/(x-2)) (x≠2), k (x=2)가 x=2에서 연속일 때 k의 값을 구하시오.", "(x-2)(x+3)으로 약분합니다.", "5", "연속 조건의 매개변수", "numeric"),
        ("무한대에서 차수 비교", "lim(x→∞) (2x^2-3x+1)/(x^2+4)의 값을 구하시오.", "최고차항의 계수를 비교합니다.", "2", "무한대 차수 비교", "numeric"),
        ("근 근처의 약분", "lim(x→-2) (x^2+5x+6)/(x+2)의 값을 구하시오.", "(x+2)(x+3)", "1", "근 근처의 약분", "numeric"),
        ("이차식끼리 약분", "lim(x→1) (x^2-4x+3)/(x^2-1)의 값을 구하시오.", "분자와 분모를 각각 인수분해한 뒤 약분합니다.", "-1", "이차식끼리 약분", "numeric"),
        ("조각함수 연속", "함수 f(x)=ax+1 (x<2), x^2-1 (x≥2)가 x=2에서 연속일 때 a의 값을 구하시오.", "2a+1=3", "1", "조각함수 연속", "numeric"),
        ("변화율 꼴 극한", "lim(x→0) (((1+x)^2)-1)/x의 값을 구하시오.", "분자를 전개해 x로 묶습니다.", "2", "변화율 꼴 극한", "numeric"),
    ],
    "calc1-integral": [
        ("일차함수 정적분", "∫_0^2 (x+1) dx의 값을 구하시오.", "x^2/2 + x", "4", "일차함수 정적분", "numeric"),
        ("홀함수 대칭성", "∫_-1^1 x^3 dx의 값을 구하시오.", "홀함수의 대칭구간 적분", "0", "홀함수 대칭성", "numeric"),
        ("절댓값 정적분", "∫_0^3 |x-1| dx의 값을 구하시오.", "x=1에서 구간을 나눕니다.", "5/2", "절댓값 정적분", "numeric"),
        ("적분함수 값 읽기", "F(x)=∫_0^x (2t+1) dt 일 때 F(2)의 값을 구하시오.", "0부터 2까지 정적분", "6", "적분함수 값 읽기", "numeric"),
        ("두 그래프 사이 넓이", "구간 [0,1]에서 y=x와 y=x^2로 둘러싸인 부분의 넓이를 구하시오.", "∫_0^1 (x-x^2) dx", "1/6", "두 그래프 사이 넓이", "numeric"),
        ("부호가 바뀌는 적분", "∫_0^1 (3x^2-4x+1) dx의 값을 구하시오.", "원시함수 x^3-2x^2+x", "0", "부호가 바뀌는 적분", "numeric"),
        ("평균값 해석", "함수 y=x^2의 구간 [0,2]에서의 평균값을 구하시오.", "(1/2)∫_0^2 x^2 dx", "4/3", "평균값 해석", "numeric"),
        ("역제곱 적분", "∫_0^1 1/(x+1)^2 dx의 값을 구하시오.", "-1/(x+1)", "1/2", "역제곱 적분", "numeric"),
        ("적분으로 상한 복원", "a>0일 때 ∫_0^a 2x dx=9를 만족하는 a의 값을 구하시오.", "a^2=9", "3", "적분으로 상한 복원", "numeric"),
    ],
    "probstat-counting": [
        ("적어도 두 명의 조건", "여학생 5명, 남학생 4명 중 3명을 뽑을 때 여학생이 적어도 2명 포함되도록 뽑는 방법의 수를 구하시오.", "여학생 2명, 3명인 경우로 나눕니다.", "50", "적어도 두 명의 조건", "numeric"),
        ("원순열 인접 조건", "서로 다른 6명이 원탁에 둘러앉을 때 A와 B가 서로 이웃하도록 앉는 방법의 수를 구하시오.", "AB를 한 묶음으로 봅니다.", "48", "원순열 인접 조건", "numeric"),
        ("짝수 네 자리 수", "숫자 0,1,2,3,4,5 중 서로 다른 4개로 만들 수 있는 네 자리 짝수의 개수를 구하시오.", "끝자리가 0인 경우와 2 또는 4인 경우를 나눕니다.", "156", "짝수 네 자리 수", "numeric"),
        ("연속 블록 배열", "서로 다른 책 5권을 일렬로 놓을 때 A, B, C가 서로 연속하도록 놓는 방법의 수를 구하시오.", "ABC를 한 묶음으로 봅니다.", "36", "연속 블록 배열", "numeric"),
        ("정확히 한 상자가 비는 분배", "서로 같은 공 8개를 서로 다른 상자 3개에 넣을 때 정확히 한 상자만 비도록 넣는 방법의 수를 구하시오.", "빈 상자를 고른 뒤 나머지 두 상자에 양수해로 분배합니다.", "21", "정확히 한 상자가 비는 분배", "numeric"),
        ("원탁 남녀 교대 배열", "남학생 4명, 여학생 4명이 원탁에 앉을 때 남녀가 번갈아 앉는 방법의 수를 구하시오.", "남학생 한 명을 고정한 뒤 여학생과 나머지 남학생을 배치합니다.", "144", "원탁 남녀 교대 배열", "numeric"),
        ("두 집단이 모두 포함된 위원회", "남학생 6명, 여학생 5명 중 4명의 위원회를 만들 때 남학생과 여학생이 모두 포함되도록 하는 방법의 수를 구하시오.", "전체에서 한 성별만 뽑는 경우를 뺍니다.", "310", "두 집단 포함 위원회", "numeric"),
        ("격자 최단경로", "좌표평면에서 (0,0)에서 (4,3)까지 오른쪽과 위쪽으로만 이동하는 최단경로의 수를 구하시오.", "오른쪽 4번, 위쪽 3번의 배열", "35", "격자 최단경로", "numeric"),
        ("중복문자 배열", "BANANA의 문자를 모두 일렬로 배열하는 방법의 수를 구하시오.", "A 3개, N 2개가 중복됩니다.", "60", "중복문자 배열", "numeric"),
    ],
    "probstat-statistics": [
        ("평균 계산", "자료 2, 4, 6, 8의 평균을 구하시오.", "합을 4로 나눕니다.", "5", "평균 계산", "numeric"),
        ("평균으로 미지수 복원", "자료 x, 3, 5의 평균이 6일 때 x의 값을 구하시오.", "x+3+5=18", "10", "평균으로 미지수 복원", "numeric"),
        ("기본 분산 계산", "자료 1, 3, 5, 7의 분산을 구하시오.", "평균은 4입니다.", "5", "기본 분산 계산", "numeric"),
        ("분산의 평행이동과 확대", "확률변수 X의 분산이 2일 때 Y=2X-1의 분산을 구하시오.", "분산은 평행이동에 불변, 배율의 제곱만큼 변합니다.", "8", "분산의 변환", "numeric"),
        ("성공횟수의 기대값", "확률변수 X가 이항분포 B(5, 2/3)를 따를 때 E(X)의 값을 구하시오.", "np", "10/3", "성공횟수의 기대값", "numeric"),
        ("이항분포의 분산", "확률변수 X가 이항분포 B(4, 1/2)를 따를 때 V(X)의 값을 구하시오.", "np(1-p)", "1", "이항분포의 분산", "numeric"),
        ("도수표 가중평균", "값이 1, 2, 5이고 각 도수가 2, 3, 1일 때 평균을 구하시오.", "(1×2+2×3+5×1)/6", "13/6", "도수표 가중평균", "numeric"),
        ("새 자료의 분산", "자료 1, 3, 5, 7의 각 값에 2를 곱한 새 자료의 분산을 구하시오.", "분산은 배율의 제곱만큼 변합니다.", "20", "새 자료의 분산", "numeric"),
        ("평균조건의 마지막 값", "자료 1, 2, 3, a의 평균이 4일 때 a의 값을 구하시오.", "1+2+3+a=16", "10", "평균조건의 마지막 값", "numeric"),
    ],
    "calc2-seq-limit": [
        ("등비급수 총합", "무한등비급수의 첫째항이 3이고 공비가 1/2일 때 그 합을 구하시오.", "a/(1-r)", "6", "등비급수 총합", "numeric"),
        ("점화식 수열의 극한", "수열 {a_n}이 a_1=1, a_(n+1)=(a_n+2)/3 을 만족할 때 lim a_n을 구하시오.", "극한을 L이라 두면 L=(L+2)/3", "1", "점화식 수열의 극한", "numeric"),
        ("유리식 수열의 극한", "lim(n→∞) (2n^2+1)/(n^2+3n)의 값을 구하시오.", "최고차항의 계수를 비교합니다.", "2", "이차 유리식 수열 극한", "numeric"),
        ("루트 수열의 차", "lim(n→∞) (√(n^2+3n)-n)의 값을 구하시오.", "유리화합니다.", "3/2", "루트 수열의 차", "numeric"),
        ("부분합 수열의 극한", "수열 a_n=Σ(k=1~n) 1/2^k 일 때 lim a_n을 구하시오.", "첫째항 1/2, 공비 1/2인 등비합", "1", "부분합 수열의 극한", "numeric"),
        ("차수 비교형 수열", "lim(n→∞) (n^2+1)/(2n^2-3)의 값을 구하시오.", "최고차항 계수 비교", "1/2", "차수 비교형 수열", "numeric"),
        ("또 다른 점화식 극한", "수열 {a_n}이 a_1=4, a_(n+1)=(a_n+6)/4 를 만족할 때 lim a_n을 구하시오.", "극한을 L이라 두면 L=(L+6)/4", "2", "또 다른 점화식 극한", "numeric"),
        ("망원합 수열의 극한", "수열 a_n=Σ(k=1~n) 1/(k(k+1)) 일 때 lim a_n을 구하시오.", "1-1/(n+1)", "1", "망원합 수열의 극한", "numeric"),
        ("부호가 바뀌는 등비급수", "무한등비급수의 첫째항이 5이고 공비가 -1/3일 때 그 합을 구하시오.", "a/(1-r)", "15/4", "부호가 바뀌는 등비급수", "numeric"),
    ],
    "calc2-integral": [
        ("지수 치환 적분", "∫_0^1 2x·e^(x^2) dx의 값을 구하시오.", "u=x^2로 치환합니다.", "e-1", "지수 치환 적분", "exact"),
        ("삼각함수 정적분", "∫_0^(π/2) sin x dx의 값을 구하시오.", "원시함수는 -cos x", "1", "삼각함수 정적분", "numeric"),
        ("로그 치환 적분", "∫_0^1 x/(x^2+1) dx의 값을 구하시오.", "u=x^2+1로 치환합니다.", "1/2 ln2", "로그 치환 적분", "exact"),
        ("적분함수 미분", "F(x)=∫_1^(x^2) t dt 일 때 F'(2)의 값을 구하시오.", "합성함수 미분과 적분함수 정리를 함께 씁니다.", "16", "적분함수 미분", "numeric"),
        ("대칭구간 적분", "∫_-1^1 (x^2+1) dx의 값을 구하시오.", "짝함수이므로 2∫_0^1", "8/3", "대칭구간 적분", "numeric"),
        ("역제곱 치환 적분", "∫_0^1 1/(x+2)^2 dx의 값을 구하시오.", "원시함수는 -1/(x+2)", "1/6", "역제곱 치환 적분", "numeric"),
        ("도함수 분자 적분", "∫_0^1 (2x+3)/(x^2+3x+1) dx의 값을 구하시오.", "분모의 도함수가 분자입니다.", "ln5", "도함수 분자 적분", "exact"),
        ("상한 복원 적분", "a>0일 때 ∫_0^a x dx=8을 만족하는 a의 값을 구하시오.", "a^2/2=8", "4", "상한 복원 적분", "numeric"),
        ("로그 기본적분", "∫_1^e 1/x dx의 값을 구하시오.", "원시함수는 ln x", "1", "로그 기본적분", "numeric"),
    ],
    "geometry-conic": [
        ("포물선의 p 읽기", "포물선 y^2=8x에서 p의 값을 구하시오.", "표준형 y^2=4px", "2", "포물선의 p 읽기", "numeric"),
        ("포물선의 초점", "포물선 x^2=12y의 초점을 구하시오.", "표준형 x^2=4py", "(0,3)", "포물선의 초점", "exact"),
        ("타원 짧은축 복원", "장축의 꼭짓점이 (±5,0), 초점이 (±3,0)인 타원의 b^2 값을 구하시오.", "b^2=a^2-c^2", "16", "타원 짧은축 복원", "numeric"),
        ("타원의 이심률", "장축의 길이가 10이고 두 초점 사이의 거리가 8인 타원의 이심률을 구하시오.", "a=5, c=4 이므로 e=c/a", "4/5", "장축과 초점거리 이심률", "numeric"),
        ("쌍곡선 초점거리", "쌍곡선 x^2/9 - y^2/16 = 1의 두 초점 사이의 거리를 구하시오.", "c^2=9+16", "10", "쌍곡선 초점거리", "numeric"),
        ("점근선 기울기와 c", "쌍곡선의 점근선 기울기가 ±3/4이고 a=4일 때 c^2의 값을 구하시오.", "b/a=3/4이므로 b=3", "25", "점근선 기울기와 c", "numeric"),
        ("준선에서 포물선 복원", "꼭짓점이 원점이고 준선이 x=-2인 포물선의 방정식을 구하시오.", "p=2", "y^2=8x", "준선에서 포물선 복원", "exact"),
        ("초점거리 합에서 타원 복원", "타원의 두 초점이 (-4,0), (4,0)이고 타원 위의 점 P에 대하여 PF1+PF2=10일 때 b^2의 값을 구하시오.", "2a=10, c=4", "9", "초점거리 합에서 타원 복원", "numeric"),
        ("쌍곡선의 b^2", "쌍곡선 x^2/25 - y^2/b^2 = 1 위의 점 (10,6)이 이 쌍곡선 위에 있을 때 b^2의 값을 구하시오.", "점을 대입해 b^2를 정리합니다.", "12", "쌍곡선 위의 점으로 b제곱 복원", "numeric"),
    ],
    "geometry-space": [
        ("두 점 사이 거리", "점 A(1,2,3), B(4,6,3) 사이의 거리를 구하시오.", "차벡터는 (3,4,0)", "5", "두 점 사이 거리", "numeric"),
        ("공간 중점", "점 A(1,-1,3), B(5,3,1)의 중점 좌표를 구하시오.", "좌표별 평균", "(3,1,2)", "공간 중점", "exact"),
        ("공간 좌표 내분점", "점 A(1,2,3), B(7,5,9)를 1:2로 내분하는 점의 좌표를 구하시오.", "좌표별 내분공식", "(3,3,5)", "공간 좌표 내분점", "exact"),
        ("축 위 사면체 부피", "O(0,0,0), A(2,0,0), B(0,3,0), C(0,0,6)이 이루는 사면체의 부피를 구하시오.", "abc/6", "6", "축 위 사면체 부피", "numeric"),
        ("축까지의 거리 제곱", "점 P(1,2,2)에서 z축까지의 거리의 제곱을 구하시오.", "x^2+y^2", "5", "축까지의 거리 제곱", "numeric"),
        ("삼각형의 무게중심", "점 A(1,0,2), B(4,3,5), C(-2,6,2)가 이루는 삼각형의 무게중심 좌표를 구하시오.", "세 좌표의 평균", "(1,3,3)", "삼각형의 무게중심", "exact"),
        ("구의 중심", "방정식 x^2+y^2+z^2-4x+2y-6z+6=0이 나타내는 구의 중심을 구하시오.", "완전제곱식으로 바꿉니다.", "(2,-1,3)", "구의 중심", "exact"),
        ("중점의 거리 제곱", "점 A(2,-1,4), B(6,3,0)의 중점을 P라 할 때 OP의 길이의 제곱을 구하시오.", "P=(4,1,2)", "21", "중점의 거리 제곱", "numeric"),
        ("또 다른 사면체 부피", "세 점 A(3,0,0), B(0,4,0), C(0,0,5)가 정하는 삼각형 ABC와 원점 O로 이루는 사면체 OABC의 부피를 구하시오.", "삼각형 ABC를 밑면으로 보아도 축절편 구조를 이용할 수 있습니다.", "10", "원점과 삼각형의 사면체 부피", "numeric"),
    ],
    "geometry-vector": [
        ("기본 내적", "벡터 a=(1,2), b=(3,4)에 대하여 a·(a+b)의 값을 구하시오.", "a·a+a·b", "16", "합벡터와 내적", "numeric"),
        ("수직 조건의 매개변수", "벡터 a=(k,2), b=(1,-3)에 대하여 a·b=4일 때 k의 값을 구하시오.", "k-6=4", "10", "내적값 매개변수", "numeric"),
        ("합벡터의 크기", "벡터 a=(1,2), b=(3,-2)에 대하여 |a+b|의 값을 구하시오.", "a+b=(4,0)", "4", "합벡터의 크기", "numeric"),
        ("삼각형 넓이", "점 O(0,0), A(2,1), B(1,3)일 때 삼각형 OAB의 무게중심 G의 좌표를 구하시오.", "세 꼭짓점 좌표의 평균", "(1,4/3)", "삼각형 무게중심", "exact"),
        ("스칼라배 역추적", "벡터 a=(2,-1), b=(-6,3)에 대하여 3a+b의 각 성분의 합을 구하시오.", "3a+b=(0,0)", "0", "일차결합 성분합", "numeric"),
        ("벡터식 정리", "벡터 a=(1,2), b=(3,-1)에 대하여 2a-b의 각 성분의 합을 구하시오.", "2a-b=(-1,5)", "4", "벡터식 정리", "numeric"),
        ("내적에서 거리 제곱", "벡터 a=(3,4), b=(1,-2)에 대하여 |a+b|^2의 값을 구하시오.", "|a+b|^2=(a+b)·(a+b)", "20", "내적에서 합벡터 제곱", "numeric"),
        ("벡터와 각의 판정", "벡터 a=(1,2), b=(2,-1)이 이루는 각의 종류를 판정하시오.", "a·b=0", "직각", "벡터와 각의 판정", "exact"),
        ("내적과 길이의 결합", "벡터 a, b에 대하여 |a|=3, |b|=4, a·b=6일 때 |2a-b|^2의 값을 구하시오.", "|2a-b|^2=4|a|^2+|b|^2-4a·b", "28", "내적과 결합벡터 길이", "numeric"),
    ],
}


CURATED_TANGENT_SPECS: dict[str, list[tuple[str, int, str, str]]] = {
    "calc1-diff": [
        ("x**7 - 7*x**6 + 14*x**5 + 7*x**4 - 35*x**3 + 8*x - 2", 1, "극값 구조 접선", "극값 구조 접선"),
        ("3*x**6 - 9*x**5 - 24*x**4 + 44*x**3 + 6*x**2 - 18*x + 5", 2, "부호 전환 접선", "부호 전환 접선"),
        ("x**7 - 5*x**6 - 9*x**5 + 45*x**4 - 10*x**3 - 24*x**2 + 9*x + 1", 1, "고차 다항 접선", "고차 다항 접선"),
        ("2*x**7 - 7*x**6 - 28*x**5 + 63*x**4 + 8*x**3 - 44*x**2 + 12*x - 5", -1, "음수 접점 접선", "음수 접점 접선"),
        ("x**8 - 8*x**7 + 14*x**6 + 28*x**5 - 70*x**4 + 16*x**3 + 24*x**2 - 12*x + 3", 1, "apex 다항 접선", "apex 다항 접선"),
        ("2*x**8 - 11*x**7 - 12*x**6 + 91*x**5 - 30*x**4 - 84*x**3 + 24*x**2 + 18*x - 7", 2, "연쇄 계수 접선", "연쇄 계수 접선"),
        ("x**9 - 9*x**8 + 18*x**7 + 30*x**6 - 126*x**5 + 20*x**4 + 72*x**3 - 18*x**2 - 10*x + 4", 1, "구조 전환 접선", "구조 전환 접선"),
        ("2*x**9 - 13*x**8 - 16*x**7 + 140*x**6 - 42*x**5 - 168*x**4 + 40*x**3 + 60*x**2 - 18*x + 5", -1, "최종 킬러 접선", "최종 킬러 접선"),
        ("x**10 - 10*x**9 + 25*x**8 + 40*x**7 - 210*x**6 + 35*x**5 + 240*x**4 - 50*x**3 - 90*x**2 + 20*x - 6", 1, "압축 apex 접선", "압축 apex 접선"),
    ],
    "calc2-diff": [
        ("exp(3*x) + x**7 - 7*x**5 + 8*x**2 - 3", 0, "지수와 다항 접선", "지수와 다항 접선"),
        ("exp(2*x+1) + 2*x**7 - 5*x**6 - 3*x**3 + 9*x", 1, "지수 치환 접선", "지수 치환 접선"),
        ("exp(4*x-1) + x**8 - 8*x**4 + 6*x - 2", 0, "고차 지수 접선", "고차 지수 접선"),
        ("exp(3*x) + 3*x**7 - 12*x**5 + 7*x**2 + 4", 1, "계수 비교 지수 접선", "계수 비교 지수 접선"),
        ("exp(2*x) + x**8 - 4*x**7 - 6*x**4 + 10*x**2 - 5", 0, "구간 판정 지수 접선", "구간 판정 지수 접선"),
        ("exp(5*x-2) + 2*x**8 - 9*x**6 + 3*x**3 + x - 1", 1, "합성 지수 접선", "합성 지수 접선"),
        ("exp(4*x) + x**9 - 9*x**5 + 4*x**3 - 6*x", 0, "apex 지수 접선", "apex 지수 접선"),
        ("exp(6*x) + 2*x**13 - 15*x**11 - 10*x**8 + 60*x**6 - 18*x**3 + 5", 0, "최종 킬러 지수 접선", "최종 킬러 지수 접선"),
        ("exp(7*x-1) + x**14 - 14*x**12 + 28*x**9 + 21*x**6 - 70*x**4 + 20*x - 4", 1, "압축 apex 지수 접선", "압축 apex 지수 접선"),
    ],
}


def _tangent_curated_killer_bank(unit: dict, start_index: int, specs: list[tuple[str, int, str, str]]) -> list[dict]:
    problems: list[dict] = []
    index = start_index
    for expression, point_x, title, problem_type in specs:
        problems.append(
            _drill_tangent_problem(
                unit=unit,
                index=index,
                expression=expression,
                point_x=point_x,
                title=title,
                problem_type=problem_type,
                killer_allowed=True,
            )
        )
        index += 1
    return problems


def _curated_killer_bank(unit: dict) -> list[dict]:
    start_index = DRILL_TARGET_PER_UNIT - 8
    unit_id = unit["id"]
    if unit_id == "common1-polynomial":
        return _common1_polynomial_killer_bank(unit, start_index)
    if unit_id == "common1-equation":
        return _common1_equation_killer_bank(unit, start_index)
    if unit_id == "common1-counting":
        return _common1_counting_killer_bank(unit, start_index)
    if unit_id == "common1-matrix":
        return _common1_matrix_killer_bank(unit, start_index)
    if unit_id == "common2-coordinate":
        return _common2_coordinate_killer_bank(unit, start_index)
    if unit_id == "common2-function":
        return _common2_function_killer_bank(unit, start_index)
    if unit_id == "probstat-probability":
        return _probstat_probability_killer_bank(unit, start_index)
    if unit_id in CURATED_TANGENT_SPECS:
        return _tangent_curated_killer_bank(unit, start_index, CURATED_TANGENT_SPECS[unit_id])
    if unit_id in GENERIC_CURATED_KILLER_SPECS:
        return _generic_curated_problem_bank(
            unit,
            start_index,
            GENERIC_CURATED_KILLER_SPECS[unit_id],
            coach_hint="한계돌파 뒤쪽 문제는 같은 계산을 반복하는 곳이 아니라, 서로 다른 골격을 빠르게 번역하는 훈련 구간입니다.",
            killer_allowed=True,
        )
    return []


def _curated_advanced_bank(unit: dict, start_index: int) -> list[dict]:
    unit_id = unit["id"]
    specs = GENERIC_CURATED_ADVANCED_SPECS.get(unit_id)
    if not specs:
        return []
    return _generic_curated_problem_bank(
        unit,
        start_index,
        specs,
        coach_hint="한계돌파 앞쪽 문제는 계산 반복보다 해석 골격을 세우는 연습 구간입니다.",
        killer_allowed=False,
    )


def _drill_problems_for_unit(unit: dict) -> list[dict]:
    problems = _legacy_drill_problems_for_unit(unit)
    openers = _hard_breakthrough_openers(unit)
    curated = _curated_killer_bank(unit)
    full_prefix_length = DRILL_TARGET_PER_UNIT - len(curated) if curated else DRILL_TARGET_PER_UNIT
    advanced_specs = GENERIC_CURATED_ADVANCED_SPECS.get(unit["id"], [])
    advanced_start_index = 1 if len(advanced_specs) >= full_prefix_length else len(openers) + 1
    advanced = _curated_advanced_bank(unit, advanced_start_index)
    if advanced and curated:
        prefix = advanced if advanced_start_index == 1 else openers + advanced
        return (prefix + curated)[:DRILL_TARGET_PER_UNIT]
    if not curated:
        return problems
    prefix = [problem for problem in problems if not problem.get("isKiller")]
    return (prefix + curated)[:DRILL_TARGET_PER_UNIT]


def _drill_lesson_pack(unit: dict, problems: list[dict]) -> dict:
    sample_problem = problems[0]
    return {
        "id": f"lesson-{unit['id']}-drill",
        "title": f"{unit['domainTitle']} 한계돌파",
        "unitTitle": f"{unit['courseTitle']} - {unit['domainTitle']} 한계돌파",
        "teacherName": "하늘 선생님",
        "conceptIds": [unit["id"]],
        "questionStarters": [
            f"{unit['domainTitle']} 한계돌파 문제는 첫 줄을 어떻게 잡아볼까요?",
            "이 문제 묶음에서 자주 흔들리는 포인트를 같이 짚어볼까요?",
            "킬러 문제로 갈수록 어디를 더 조심해서 봐야 할까요?",
        ],
        "curriculumMeta": {
            "courseId": unit["courseId"],
            "courseTitle": unit["courseTitle"],
            "pdfPages": unit["pdfPages"],
            "achievementCodes": unit["achievementCodes"],
            "mode": "drill",
        },
        "scenes": [
            {
                "id": f"scene-{unit['id']}-drill-1",
                "title": f"{unit['domainTitle']} 한계돌파 오프닝",
                "narration": "이 한계돌파 문제 묶음은 처음부터 난도가 높지만, 겁먹기보다 어떤 시선으로 읽어야 하는지 먼저 익히면 훨씬 풀기 편해집니다. 같은 구조를 기계적으로 반복하기보다, 단원 안에서 자주 나오는 전환을 차근차근 손에 붙여볼게요.",
                "teachingGoal": "한계돌파 문제 묶음을 어떤 시선으로 시작하면 좋을지 먼저 정리해볼까요?",
                "takeaway": "한계돌파에서는 계산력보다 문제를 읽는 첫 판단이 훨씬 중요합니다.",
                "examCue": "문제를 읽고 첫 줄이 바로 떠오르는지 먼저 확인해볼까요?",
                "practiceBridge": "이 장면이 끝나면 1번 문제부터 바로 들어가 볼게요.",
                "autoAdvanceSeconds": 16,
                "objects": [
                    {"id": f"{unit['id']}-drill-title", "type": "heading", "x": 6, "y": 10, "w": 44, "content": f"{unit['domainTitle']} 한계돌파"},
                    {"id": f"{unit['id']}-drill-badge", "type": "badge", "x": 58, "y": 12, "w": 24, "content": f"{len(problems)}문항 라이브러리", "delayMs": 160},
                    {"id": f"{unit['id']}-drill-callout", "type": "callout", "x": 8, "y": 24, "w": 48, "content": sample_problem["coachHint"], "delayMs": 260},
                ],
            },
            {
                "id": f"scene-{unit['id']}-drill-2",
                "title": "한계돌파 풀이 흐름",
                "narration": "여기서는 핵심 식, 구조 전환, 최종 답 형식을 같이 묶어 볼게요. 문제는 달라도 첫 판단의 뼈대가 같아지면 훨씬 덜 흔들립니다.",
                "teachingGoal": "한계돌파에서 반복할 체크포인트를 짧게 잡아볼까요?",
                "takeaway": "유형이 달라 보여도 먼저 확인할 기준은 반복됩니다.",
                "examCue": "문제를 읽는 10초 안에 어떤 유형인지 이름 붙여보면 좋아요.",
                "practiceBridge": "유형 이름이 붙으면 첫 문제 진입도 훨씬 빨라집니다.",
                "autoAdvanceSeconds": 16,
                "objects": [
                    {
                        "id": f"{unit['id']}-drill-check",
                        "type": "checklist",
                        "x": 8,
                        "y": 20,
                        "w": 42,
                        "h": 42,
                        "label": "초고난도 반복 체크",
                        "items": _problem_focus_checks(sample_problem) + ["중간 구조 전환이 필요한지 먼저 본다"],
                    },
                    {
                        "id": f"{unit['id']}-drill-table",
                        "type": "table",
                        "x": 54,
                        "y": 20,
                        "w": 36,
                        "h": 40,
                        "table": {"headers": ["유형", "난이도"], "rows": [[sample_problem["problemType"], sample_problem["difficulty"]], ["후반 ladder", "killer~apex"]]},
                        "delayMs": 180,
                    },
                ],
            },
            {
                "id": f"scene-{unit['id']}-drill-3",
                "title": "대표 한계돌파 문제",
                "narration": "대표 문제를 보면서 첫 줄, 중간 전환, 마지막 정리가 어떻게 이어지는지 같이 짚어볼게요.",
                "teachingGoal": "대표 문제에 들어가는 순서를 자연스럽게 잡아볼까요?",
                "takeaway": "첫 줄과 중간 전환이 보이면 문제는 이미 절반쯤 정리된 셈입니다.",
                "examCue": "문제 전체를 읽기 전에 어떤 식이 먼저 나올지 먼저 떠올려 보면 좋아요.",
                "practiceBridge": "곧바로 문제 묶음에서도 이 흐름을 그대로 써보면 됩니다.",
                "autoAdvanceSeconds": 18,
                "objects": [
                    {"id": f"{unit['id']}-drill-problem", "type": "callout", "x": 8, "y": 18, "w": 40, "content": sample_problem["statement"]},
                    {"id": f"{unit['id']}-drill-outline", "type": "checklist", "x": 54, "y": 18, "w": 34, "h": 42, "label": "대표 풀이 흐름", "items": sample_problem["expectedOutline"], "delayMs": 180},
                ],
            },
            {
                "id": f"scene-{unit['id']}-drill-4",
                "title": "난이도 상승",
                "narration": "같은 단원 안에서도 난도가 올라가면 어디서 한 번 더 꺾이는지만 보면 됩니다. 그 지점을 미리 보고 들어가면 훨씬 덜 당황합니다.",
                "teachingGoal": "초고난도에서 킬러로 갈 때 달라지는 지점을 같이 볼까요?",
                "takeaway": "킬러 문제도 출발점은 같지만, 중간 구조 전환과 검산이 한 번 더 필요합니다.",
                "examCue": "난도가 올라갈수록 무엇을 한 번 더 확인해야 하는지 떠올려 보세요.",
                "practiceBridge": "문제 묶음 뒤쪽에서 킬러 문제가 나와도 같은 흐름으로 이어가면 됩니다.",
                "autoAdvanceSeconds": 18,
                "objects": [
                    {
                        "id": f"{unit['id']}-drill-difficulty",
                        "type": "table",
                        "x": 8,
                        "y": 20,
                        "w": 54,
                        "h": 40,
                        "table": {
                            "headers": ["초고난도", "킬러 문제", "apex"],
                            "rows": [["기준 식 확인", "조건 판정 강화", "구조 전환 2회 이상"], ["빠른 계산", "검산 습관", "중간 연결식 생성"]],
                        },
                    },
                    {"id": f"{unit['id']}-drill-killer", "type": "callout", "x": 66, "y": 22, "w": 22, "content": "킬러 문제는 문제를 오래 읽는 게 아니라 구조를 먼저 잡아야 합니다.", "delayMs": 220},
                ],
            },
            {
                "id": f"scene-{unit['id']}-drill-5",
                "title": "문제 풀이 시작",
                "narration": "이제 문제 묶음으로 넘어가 볼까요? 맞히든 막히든 흐름이 끊기지 않게, 지금 잡은 풀이 흐름을 한 문제씩 확인해 가면 됩니다.",
                "teachingGoal": "강의에서 문제 묶음으로 부드럽게 넘어가 볼까요?",
                "takeaway": "한계돌파는 설명을 오래 보는 곳이 아니라 점수를 붙여 가는 훈련 공간입니다.",
                "examCue": "1번부터 바로 높은 난도라는 점만 잊지 않으면 됩니다.",
                "practiceBridge": "문제 묶음은 1번부터 이어지고, 필요하면 다음 문항으로 바로 넘어가도 됩니다.",
                "autoAdvanceSeconds": 14,
                "objects": [
                    {"id": f"{unit['id']}-drill-start", "type": "badge", "x": 8, "y": 20, "w": 42, "content": f"{len(problems)}문항 한계돌파 시작"},
                    {"id": f"{unit['id']}-drill-route", "type": "checklist", "x": 8, "y": 34, "w": 40, "h": 30, "label": "자동 순서", "items": ["1~10 초고난도", "11~25 킬러 문제", "26~30 apex"], "delayMs": 180},
                ],
            },
        ],
    }


def _drill_problem_set(unit: dict, problems: list[dict]) -> dict:
    return {
        "id": f"set-{unit['id']}-drill",
        "title": f"{unit['courseTitle']} · {unit['domainTitle']} 한계돌파",
        "lessonPackId": f"lesson-{unit['id']}-drill",
        "conceptIds": [unit["id"]],
        "mode": "drill",
        "problems": deepcopy(problems),
    }


KILLER_TRACK_SPECS = [
    {
        "trackId": "calculus",
        "title": "미적분",
        "packTitle": "미적분 최상위 킬러 시퀀스",
        "subtitle": "극한, 미분, 적분, 수열극한, 함수 복원",
        "description": "한 가지 유형에만 머무르지 않고, 극한부터 적분과 함수 복원까지 수능 최상위 문항 흐름으로 이어지는 미적분 전용 킬러 문제 묶음입니다.",
        "courseIds": ["calculus-1", "calculus-2"],
        "questionStarters": [
            "이 문제는 어떤 조건부터 잡아보면 좋을까요?",
            "지금은 극한형인지, 적분형인지, 함수 복원형인지 어떻게 구분할까요?",
            "마지막 계산 전에 꼭 다시 볼 조건은 뭐가 있을까요?",
        ],
        "narrativeStages": [
            "조건을 먼저 유형별 언어로 바꿔 본다",
            "기준 식을 세운 뒤 중간 구조 전환이 필요한지 확인한다",
            "마지막에는 답만 구하지 말고 조건까지 다시 맞춰 본다",
        ],
    },
    {
        "trackId": "probability-statistics",
        "title": "확률과 통계",
        "packTitle": "확통 최상위 킬러 시퀀스",
        "subtitle": "조건 분할, 경우 나누기, 기댓값, 분산 변환",
        "description": "케이스를 자르고 다시 합치는 감각을 키우는 확통 전용 킬러 문제 묶음입니다. 수 세기와 확률, 기대값을 한 문제 안에서 묶어 봅니다.",
        "courseIds": ["probability-statistics"],
        "questionStarters": [
            "이 문제는 케이스를 어떻게 나누는 게 제일 좋아?",
            "조건을 나눈 뒤 어떤 경우부터 세는 게 좋아?",
            "기댓값/분산 문제에서 가장 먼저 정의해야 할 변수는 뭐야?",
        ],
        "narrativeStages": [
            "표본공간을 먼저 잘게 자른다",
            "조건부 정보가 들어오면 분자와 분모를 다시 세운다",
            "확률변수를 정한 뒤 기대값과 분산으로 닫는다",
        ],
    },
    {
        "trackId": "geometry",
        "title": "기하",
        "packTitle": "기하 최상위 킬러 시퀀스",
        "subtitle": "이차곡선 복원, 벡터 조건, 공간 부피",
        "description": "좌표, 벡터, 공간도형을 식으로 다시 묶어내는 기하 전용 킬러 문제 묶음입니다. 그림보다 관계식을 먼저 보는 훈련에 맞춥니다.",
        "courseIds": ["geometry"],
        "questionStarters": [
            "이 기하 킬러는 그림보다 어떤 식을 먼저 세워야 해?",
            "벡터 조건을 좌표식으로 바꾸면 무엇이 남아?",
            "공간 부피 문제에서 기준면은 어디로 잡는 게 좋아?",
        ],
        "narrativeStages": [
            "그림의 조건을 a, b, c 관계식으로 바꾼다",
            "직교, 접선, 초점 같은 말을 식으로 다시 쓴다",
            "마지막에는 길이/면적/부피 한 값으로 닫는다",
        ],
    },
]


def _units_for_course_ids(course_ids: list[str]) -> list[dict]:
    return [unit for unit in UNIT_SPECS if unit["courseId"] in course_ids]


def _concept_ids_for_course_ids(course_ids: list[str]) -> list[str]:
    return [unit["id"] for unit in _units_for_course_ids(course_ids)]


def _achievement_codes_for_course_ids(course_ids: list[str]) -> list[str]:
    codes: list[str] = []
    for unit in _units_for_course_ids(course_ids):
        for code in unit["achievementCodes"]:
            if code not in codes:
                codes.append(code)
    return codes


def _killer_track_problem(
    *,
    track_title: str,
    track_id: str,
    index: int,
    title: str,
    statement: str,
    achievement_codes: list[str],
    steps: list[dict],
    final: dict,
    coach_hint: str,
    expected_outline: list[str],
    final_prompt: str,
    problem_type: str,
) -> dict:
    return structured_problem(
        problem_id=f"killer-{track_id}-{index:03d}",
        title=title,
        statement=statement,
        unit_title=f"{track_title} 킬러 시퀀스",
        course_title=track_title,
        achievement_codes=achievement_codes,
        steps=steps,
        final=final,
        coach_hint=coach_hint,
        expected_outline=expected_outline,
        final_prompt="",
        difficulty="apex",
        problem_type=problem_type,
        is_killer=True,
    )


def _calculus_killer_problems(spec: dict) -> list[dict]:
    codes = _achievement_codes_for_course_ids(spec["courseIds"])
    return [
        _killer_track_problem(
            track_title=spec["title"],
            track_id=spec["trackId"],
            index=1,
            title="합성함수 극값 복원",
            statement=_condition_statement(
                "최고차항의 계수가 1인 삼차함수 f(x)와 실수 전체에서 정의된 함수 g(x)=f(sin^2(πx))에 대하여",
                [
                    "구간 0<x<1에서 g(x)가 극댓값을 갖는 x는 1/6, 1/2, 5/6뿐이고, 세 점에서의 함수값은 모두 서로 같다.",
                    "구간 0<x<1에서 g(x)가 극솟값을 갖는 x는 1/3, 2/3뿐이며, 그 극솟값은 0이다.",
                    "함수 f는 0≤t≤1에서 서로 다른 두 임계점을 가지며, 그 두 점의 x좌표의 합은 1이다.",
                ],
                "f(2)의 값을 구하시오.",
            ),
            achievement_codes=codes,
            steps=[
                solution_step("Step 1. f'의 두 근", ["1/4", "3/4"], "sin^2(πx)가 1/4, 3/4가 되는 지점을 극값 조건과 연결하세요."),
                expr_step(
                    "Step 2. 함수 복원",
                    "x**3 - 3/2*x**2 + 9/16*x",
                    "f'(x)=3(x-1/4)(x-3/4)에서 적분하고, 최솟값 조건으로 상수를 정리하세요.",
                    display="x^3 - 3/2 x^2 + 9/16 x",
                ),
                numeric_step("Step 3. f(2)", "25/8", "복원한 함수에 x=2를 대입하세요."),
            ],
            final=numeric_step("최종 답", "25/8", "최종 값을 적으세요."),
            coach_hint="이 문제는 x축 위의 극값 개수를 바로 세지 말고, sin^2(πx)가 만드는 내부 변수 t의 임계점부터 복원해야 풀립니다.",
            expected_outline=["내부 변수 t로 압축", "f'의 근 복원", "함수 전체 복원", "f(2) 계산"],
            final_prompt="예: 25/8",
            problem_type="합성함수 극값 복원",
        ),
        _killer_track_problem(
            track_title=spec["title"],
            track_id=spec["trackId"],
            index=2,
            title="중근과 접선 교점",
            statement=_condition_statement(
                "최고차항의 계수가 1인 삼차함수 f(x)에 대하여",
                [
                    "f(x)는 x=1에서 중근을 가진다.",
                    "x=0에서의 접선과 x=2에서의 접선은 x축 위의 한 점 P에서 만나고, 점 P의 x좌표는 1보다 작다.",
                    "f(0)>0이다.",
                ],
                "f(3)=a+b√3일 때, a^2+b^2의 값을 구하시오. 단, a와 b는 유리수이다.",
            ),
            achievement_codes=codes,
            steps=[
                expr_step(
                    "Step 1. 함수식",
                    "(x-1)**2*(x-(1-sqrt(3)))",
                    "중근 조건으로 f(x)=(x-1)^2(x-t)로 두고, 두 접선의 교점 조건으로 t를 구하세요.",
                    display="(x-1)^2(x-(1-√3))",
                ),
                expr_step(
                    "Step 2. f(3)",
                    "8 + 4*sqrt(3)",
                    "구한 함수식에 x=3을 대입해 a+b√3 꼴로 정리하세요.",
                    display="8 + 4√3",
                ),
                numeric_step("Step 3. a^2+b^2", "80", "a=8, b=4를 대입해 계산하세요."),
            ],
            final=numeric_step("최종 답", "80", "최종 값을 적으세요."),
            coach_hint="접선 교점 조건은 계수를 직접 미지수로 두기보다 중근을 먼저 고정해 식을 줄인 뒤 한 번에 쓰는 것이 훨씬 빠릅니다.",
            expected_outline=["중근 구조", "접선 교점 조건", "무리수항 정리", "최종 계산"],
            final_prompt="예: 80",
            problem_type="중근과 접선 교점",
        ),
        _killer_track_problem(
            track_title=spec["title"],
            track_id=spec["trackId"],
            index=3,
            title="적분 조건으로 세 번째 근 복원",
            statement=_condition_statement(
                "최고차항의 계수가 1인 삼차함수 f(x)에 대하여",
                [
                    "f(x)는 x=1, x=3을 근으로 가진다.",
                    "곡선 y=f(x)와 x축으로 둘러싸인 구간 [1,3]의 부호 있는 넓이를 적분으로 나타내면 ∫_1^3 f(x)dx=-4 이다.",
                    "x=2는 두 근 1, 3의 정확한 중점이다.",
                ],
                "f(2)의 값을 구하시오.",
            ),
            achievement_codes=codes,
            steps=[
                solution_step("Step 1. 세 번째 근", ["-1"], "f(x)=(x-1)(x-3)(x-r)로 두고 적분 조건으로 r을 구하세요."),
                expr_step(
                    "Step 2. 함수식",
                    "(x-1)*(x-3)*(x+1)",
                    "구한 r값을 넣어 함수식을 정리하세요.",
                    display="(x-1)(x-3)(x+1)",
                ),
                numeric_step("Step 3. f(2)", "-3", "x=2를 대입하세요."),
            ],
            final=numeric_step("최종 답", "-3", "최종 값을 적으세요."),
            coach_hint="적분 조건은 계산용 장식이 아니라 세 번째 근을 찾아내는 핵심 식입니다. 먼저 인수형을 세우고 적분값을 넣으세요.",
            expected_outline=["인수형 설정", "적분으로 미지수 결정", "값 대입", "최종 계산"],
            final_prompt="예: -3",
            problem_type="적분 조건 복원",
        ),
        _killer_track_problem(
            track_title=spec["title"],
            track_id=spec["trackId"],
            index=4,
            title="도함수의 근과 접선 복원",
            statement=_condition_statement(
                "최고차항의 계수가 1인 삼차함수 f(x)에 대하여",
                [
                    "방정식 f'(x)=0의 두 실근의 합은 4이고 곱은 3이다.",
                    "x=2에서 곡선 y=f(x)에 그은 접선은 원점을 지난다.",
                    "f의 극댓값과 극솟값의 합은 -4이다.",
                ],
                "f(4)의 값을 구하시오.",
            ),
            achievement_codes=codes,
            steps=[
                solution_step("Step 1. f'의 근", ["1", "3"], "근의 합과 곱으로 f'(x)=3(x-1)(x-3) 구조를 먼저 복원하세요."),
                expr_step(
                    "Step 2. 함수 복원",
                    "x**3 - 6*x**2 + 9*x - 2",
                    "적분한 뒤 x=2에서의 접선이 원점을 지난다는 조건으로 상수를 결정하세요.",
                    display="x^3 - 6x^2 + 9x - 2",
                ),
                numeric_step("Step 3. f(4)", "2", "복원한 함수에 x=4를 대입하세요."),
            ],
            final=numeric_step("최종 답", "2", "최종 값을 적으세요."),
            coach_hint="조건을 하나씩 미지수에 넣기보다, 도함수의 근 -> 적분 -> 접선 조건 순서로 줄여 들어가면 구조가 훨씬 짧아집니다.",
            expected_outline=["도함수의 근 복원", "함수식 복원", "접선 조건 반영", "값 대입"],
            final_prompt="예: 2",
            problem_type="도함수와 접선 복원",
        ),
        _killer_track_problem(
            track_title=spec["title"],
            track_id=spec["trackId"],
            index=5,
            title="평균값 조건과 극값 복원",
            statement=_condition_statement(
                "최고차항의 계수가 1인 삼차함수 f(x)에 대하여",
                [
                    "f는 x=0에서 극댓값을, x=2에서 극솟값을 가진다.",
                    "구간 [0,2]에서의 함수값의 평균은 0이다.",
                    "f(0)>0이고 f(2)<0이다.",
                ],
                "f(3)의 값을 구하시오.",
            ),
            achievement_codes=codes,
            steps=[
                expr_step(
                    "Step 1. 도함수와 함수식",
                    "x**3 - 3*x**2 + C",
                    "극대와 극소의 x좌표를 이용해 f'(x)=3x(x-2)로 두고 적분하세요.",
                    display="x^3 - 3x^2 + C",
                ),
                numeric_step("Step 2. 상수 C", "2", "구간 [0,2]에서 평균값이 0이라는 조건으로 C를 구하세요."),
                numeric_step("Step 3. f(3)", "2", "복원한 함수에 x=3을 대입하세요."),
            ],
            final=numeric_step("최종 답", "2", "최종 값을 적으세요."),
            coach_hint="평균값 조건은 부가 문장이 아니라 적분으로 상수를 닫는 핵심 식입니다. 극값 x좌표를 먼저 쓰면 훨씬 짧게 풀립니다.",
            expected_outline=["도함수 구조", "함수식 적분", "평균값 조건", "값 대입"],
            final_prompt="예: 2",
            problem_type="평균값 조건 복원",
        ),
        _killer_track_problem(
            track_title=spec["title"],
            track_id=spec["trackId"],
            index=6,
            title="적분값과 극값의 거리",
            statement=_condition_statement(
                "최고차항의 계수가 1인 삼차함수 f(x)에 대하여",
                [
                    "f는 x=1에서 극댓값을, x=3에서 극솟값을 가진다.",
                    "구간 [1,3]에서의 부호 있는 넓이를 적분으로 나타내면 ∫_1^3 f(x)dx=2 이다.",
                    "두 극점의 x좌표 차는 2이다.",
                ],
                "f(4)의 값을 구하시오.",
            ),
            achievement_codes=codes,
            steps=[
                expr_step(
                    "Step 1. 함수식",
                    "x**3 - 6*x**2 + 9*x + C",
                    "극값의 x좌표를 이용해 f'(x)=3(x-1)(x-3)으로 두고 적분하세요.",
                    display="x^3 - 6x^2 + 9x + C",
                ),
                numeric_step("Step 2. 상수 C", "-1", "∫_1^3 f(x)dx = 2 조건을 이용해 C를 구하세요."),
                numeric_step("Step 3. f(4)", "3", "x=4를 대입하세요."),
            ],
            final=numeric_step("최종 답", "3", "최종 값을 적으세요."),
            coach_hint="적분값 조건은 평균값과 비슷해 보여도 바로 상수항을 닫는 식입니다. 극값 위치를 먼저 고정해 둬야 적분이 짧아집니다.",
            expected_outline=["도함수 구조", "함수식 적분", "적분값 조건", "값 대입"],
            final_prompt="예: 3",
            problem_type="적분값과 극값 복원",
        ),
        _killer_track_problem(
            track_title=spec["title"],
            track_id=spec["trackId"],
            index=7,
            title="지수함수와 적분 조건 복원",
            statement=_condition_statement(
                "실수 전체에서 정의된 함수 f(x)=e^x+x^3+ax^2+bx+c에 대하여",
                [
                    "x=0에서의 접선은 원점을 지난다.",
                    "x=0은 f의 정지점이다.",
                    "다항식 부분만 떼어 보면 ∫_0^1 (f'(x)-e^x)dx=-3 이다.",
                ],
                "f(1)의 값을 구하시오.",
            ),
            achievement_codes=codes,
            steps=[
                exact_step("Step 1. c, b", "c=-1, b=-1", "접선이 원점을 지나고 x=0이 정지점이라는 조건으로 c와 b를 먼저 구하세요."),
                numeric_step("Step 2. a", "-3", "∫_0^1 (3x^2+2ax+b)dx = -3을 이용해 a를 구하세요."),
                expr_step("Step 3. f(1)", "exp(1) - 4", "구한 계수를 넣어 f(1)을 정리하세요.", display="e-4"),
            ],
            final=expr_step("최종 답", "exp(1) - 4", "최종 값을 적으세요.", display="e-4"),
            coach_hint="지수함수가 섞였다고 바로 복잡해지는 문제는 아닙니다. e^x를 제외한 다항식 부분만 따로 떼어 조건을 읽으면 구조가 선명해집니다.",
            expected_outline=["초기 조건으로 계수 정리", "적분 조건으로 남은 계수 결정", "함수값 계산", "최종 답"],
            final_prompt="예: e-4",
            problem_type="지수함수 계수 복원",
        ),
        _killer_track_problem(
            track_title=spec["title"],
            track_id=spec["trackId"],
            index=8,
            title="치환 적분의 구조 전환",
            statement=_condition_statement(
                "함수 F(t)=∫_0^t (4x+2)(2x^2+2x+1)^3 dx에 대하여",
                [
                    "적분식 안의 괄호 2x^2+2x+1의 도함수는 바깥 계수 4x+2와 정확히 일치한다.",
                    "문제를 풀 때는 치환 뒤 적분구간도 함께 바꾸어 해석한다.",
                    "t=1일 때의 함수값을 구하려고 한다.",
                ],
                "F(1)의 값을 구하시오.",
            ),
            achievement_codes=codes,
            steps=[
                exact_step("Step 1. 치환", "u=2x^2+2x+1", "바깥 미분형이 그대로 보이면 괄호 전체를 새로운 문자로 두세요."),
                exact_step("Step 2. 구간 변환", "1→5", "x=0,1을 넣어 u의 구간도 함께 바꾸세요."),
                numeric_step("Step 3. 적분값", "156", "∫u^3 du로 바꾼 뒤 구간 대입으로 정리하세요."),
            ],
            final=numeric_step("최종 답", "156", "최종 값을 적으세요."),
            coach_hint="킬러 적분도 결국은 치환이 맞는지, 구간을 같이 바꾸는지 두 가지만 안 흔들리면 끝까지 갈 수 있습니다.",
            expected_outline=["치환", "구간 변환", "새 적분 계산", "최종 답"],
            final_prompt="예: 156",
            problem_type="치환 적분 구조 전환",
        ),
        _killer_track_problem(
            track_title=spec["title"],
            track_id=spec["trackId"],
            index=9,
            title="도함수 정보로 함수 전체 복원",
            statement=_condition_statement(
                "최고차항의 계수가 1인 삼차함수 f(x)에 대하여",
                [
                    "f'(x)의 두 실근의 합은 4이고 곱은 3이다.",
                    "f의 극댓값과 극솟값의 합은 -4이다.",
                    "함수 f는 서로 다른 두 극점을 갖는다.",
                ],
                "f(4)의 값을 구하시오.",
            ),
            achievement_codes=codes,
            steps=[
                solution_step("Step 1. f'의 두 근", ["1", "3"], "근의 합과 곱으로 도함수의 근을 먼저 복원해볼까요?"),
                expr_step(
                    "Step 2. 함수식",
                    "x**3 - 6*x**2 + 9*x - 2",
                    "f'(x)=3(x-1)(x-3)에서 적분한 뒤 극값 조건으로 상수를 정리하면 됩니다.",
                    display="x^3 - 6x^2 + 9x - 2",
                ),
                numeric_step("Step 3. f(4)", "2", "마지막으로 x=4를 넣어보면 됩니다."),
            ],
            final=numeric_step("최종 답", "2", "최종 값을 적어볼까요?"),
            coach_hint="이 문제는 극값 조건을 길게 붙잡기보다, 도함수의 근부터 정확히 복원하면 훨씬 매끄럽게 풀립니다.",
            expected_outline=["극점 복원", "적분상수 결정", "값 대입", "최종 답"],
            final_prompt="예: 2",
            problem_type="도함수 정보 복원",
        ),
        _killer_track_problem(
            track_title=spec["title"],
            track_id=spec["trackId"],
            index=10,
            title="접선 한 줄로 상수 닫기",
            statement=_condition_statement(
                "최고차항의 계수가 1인 삼차함수 f(x)에 대하여",
                [
                    "f는 x=1에서 극댓값을, x=3에서 극솟값을 가진다.",
                    "x=2에서 곡선 y=f(x)에 그은 접선의 방정식은 y=-3x+6이다.",
                    "접선의 기울기와 접점을 동시에 이용해 상수항을 결정할 수 있다.",
                ],
                "f(5)의 값을 구하시오.",
            ),
            achievement_codes=codes,
            steps=[
                expr_step(
                    "Step 1. 함수식",
                    "x**3 - 6*x**2 + 9*x + C",
                    "극대와 극소의 위치에서 f'(x)=3(x-1)(x-3)임을 먼저 복원하세요.",
                    display="x^3 - 6x^2 + 9x + C",
                ),
                numeric_step("Step 2. 상수 C", "4", "x=2에서의 접선이 y=-3x+6이라는 조건으로 C를 결정하세요."),
                numeric_step("Step 3. f(5)", "24", "복원한 함수에 x=5를 대입하세요."),
            ],
            final=numeric_step("최종 답", "24", "최종 값을 적으세요."),
            coach_hint="접선 한 줄은 기울기와 점을 동시에 담고 있습니다. 삼차함수 복원형에서는 이 한 줄이 상수를 닫는 마지막 열쇠가 됩니다.",
            expected_outline=["도함수 구조", "접선 조건 반영", "함수값 계산", "최종 답"],
            final_prompt="예: 24",
            problem_type="접선 조건 함수 복원",
        ),
    ]


def _probability_statistics_killer_problems(spec: dict) -> list[dict]:
    codes = _achievement_codes_for_course_ids(spec["courseIds"])
    return [
        _killer_track_problem(
            track_title=spec["title"],
            track_id=spec["trackId"],
            index=1,
            title="간격 조건과 양끝 합",
            statement=_condition_statement(
                "1부터 12까지의 자연수가 하나씩 적힌 카드 12장 중 서로 다른 4장을 택해 작은 수부터 차례로 a,b,c,d라 하자.",
                [
                    "a<b<c<d 이다.",
                    "인접한 두 수의 차 b-a, c-b, d-c는 모두 2 이상이다.",
                    "가장 작은 수와 가장 큰 수의 합은 13이다.",
                ],
                "이러한 네 수의 선택 방법의 수를 구하시오.",
            ),
            achievement_codes=codes,
            steps=[
                numeric_step("Step 1. a=1인 경우", "21", "a+d=13에서 (a,d)=(1,12)인 경우를 먼저 세세요."),
                numeric_step("Step 2. 나머지 경우", "13", "(a,d)=(2,11), (3,10)인 경우를 더하세요."),
                numeric_step("Step 3. 전체 개수", "34", "케이스를 합치세요."),
            ],
            final=numeric_step("최종 답", "34", "최종 개수를 적으세요."),
            coach_hint="확통 킬러의 첫 줄은 공식을 찾는 게 아니라 조건을 만드는 핵심 쌍부터 고정하는 것입니다.",
            expected_outline=["양끝 고정", "중간 값 분리", "케이스 합산", "최종 개수"],
            final_prompt="예: 34",
            problem_type="간격 조건 조합",
        ),
        _killer_track_problem(
            track_title=spec["title"],
            track_id=spec["trackId"],
            index=2,
            title="색 조건 분할",
            statement=_condition_statement(
                "서로 구별하지 않는 빨간 공 4개, 파란 공 3개, 초록 공 2개가 들어 있는 주머니에서 공 4개를 동시에 꺼낸다.",
                [
                    "꺼낸 4개의 공 가운데 빨간 공은 적어도 2개 포함되어야 한다.",
                    "같은 4개 가운데 파란 공은 적어도 1개 포함되어야 한다.",
                    "초록 공의 개수에는 제한이 없다.",
                ],
                "이 조건을 만족할 확률을 구하시오.",
            ),
            achievement_codes=codes,
            steps=[
                numeric_step("Step 1. 전체 경우", "126", "아무 조건 없이 9개 중 4개를 고르는 전체 경우를 먼저 구하세요."),
                numeric_step("Step 2. 유리한 경우", "66", "빨간 공 2개·3개인 경우를 파란 공 조건과 함께 나누어 세세요."),
                numeric_step("Step 3. 확률", "11/21", "유리한 경우를 전체 경우로 나누어 기약분수로 정리하세요."),
            ],
            final=numeric_step("최종 답", "11/21", "확률을 적으세요."),
            coach_hint="이런 확률 킬러는 공식을 찾기보다, 빨간 공 개수와 파란 공 조건을 같이 만족하는 경우를 빠짐없이 자르는 것이 핵심입니다.",
            expected_outline=["전체 경우", "조건별 분할", "합산", "최종 확률"],
            final_prompt="예: 11/21",
            problem_type="조건 분할 확률",
        ),
        _killer_track_problem(
            track_title=spec["title"],
            track_id=spec["trackId"],
            index=3,
            title="인접쌍의 기대값",
            statement=_condition_statement(
                "1부터 8까지의 자연수가 하나씩 적힌 카드 8장 중 서로 다른 4장을 같은 확률로 택한다.",
                [
                    "선택된 4장의 수들 가운데 {1,2}, {2,3}, ..., {7,8}처럼 서로 연속한 두 수로 이루어진 쌍의 개수를 확률변수 X라 한다.",
                    "같은 카드가 두 개의 인접쌍에 동시에 포함될 수도 있다.",
                    "X의 분포를 직접 모두 구하지 않고 기댓값만 구하려 한다.",
                ],
                "E(X)를 구하시오.",
            ),
            achievement_codes=codes,
            steps=[
                numeric_step("Step 1. 한 인접쌍이 포함될 확률", "3/14", "예를 들어 {1,2}가 포함될 확률을 조합으로 구하세요."),
                numeric_step("Step 2. 기대값의 합", "21/14", "인접쌍은 7개이므로 지표변수의 합으로 연결하세요."),
                numeric_step("Step 3. E(X)", "3/2", "기약분수로 정리하세요."),
            ],
            final=numeric_step("최종 답", "3/2", "기댓값을 적으세요."),
            coach_hint="직접 분포를 세지 말고, '각 인접쌍이 들어가는가'를 지표변수로 바꾸면 킬러도 짧아집니다.",
            expected_outline=["지표변수 설정", "한 쌍의 확률", "선형성 적용", "최종 답"],
            final_prompt="예: 3/2",
            problem_type="지표변수 기대값",
        ),
        _killer_track_problem(
            track_title=spec["title"],
            track_id=spec["trackId"],
            index=4,
            title="분산 변환",
            statement=_condition_statement(
                "빨간 공 5개, 파란 공 4개가 들어 있는 주머니에서 공 3개를 동시에 꺼낸다.",
                [
                    "꺼낸 3개의 공 가운데 빨간 공의 개수를 확률변수 X라 한다.",
                    "새 확률변수 Y를 Y=3X-2로 정의한다.",
                    "X의 분포를 먼저 읽고, 마지막 줄에서만 Y의 분산으로 옮겨가려 한다.",
                ],
                "V(Y)를 구하시오.",
            ),
            achievement_codes=codes,
            steps=[
                numeric_step("Step 1. E(X)", "5/3", "초기하분포의 기댓값 또는 분포 계산으로 E(X)를 구하세요."),
                numeric_step("Step 2. V(X)", "5/9", "초기하분포의 분산 또는 E(X^2)-[E(X)]^2로 V(X)를 구하세요."),
                numeric_step("Step 3. V(Y)", "5", "Y=3X-2의 분산은 9V(X)입니다."),
            ],
            final=numeric_step("최종 답", "5", "분산을 적으세요."),
            coach_hint="분산 문제는 X를 끝까지 계산한 뒤 마지막 줄에서만 선형변환을 적용하세요. 중간에 Y로 바로 가면 실수가 늘어납니다.",
            expected_outline=["X의 기댓값", "X의 분산", "선형변환", "최종 답"],
            final_prompt="예: 5",
            problem_type="초기하분포 분산",
        ),
        _killer_track_problem(
            track_title=spec["title"],
            track_id=spec["trackId"],
            index=5,
            title="원순열과 금지 자리",
            statement=_condition_statement(
                "서로 다른 6명 A, B, C, D, E, F를 원탁에 같은 확률로 한 줄씩 둘러앉힌다.",
                [
                    "A와 B는 반드시 서로 이웃해 앉아야 한다.",
                    "C와 D는 서로 이웃해 앉으면 안 된다.",
                    "회전하여 같은 배치는 같은 경우로 본다.",
                ],
                "이 조건을 만족할 확률을 구하시오.",
            ),
            achievement_codes=codes,
            steps=[
                numeric_step("Step 1. 전체 원순열", "120", "서로 다른 6명의 원순열 전체 개수는 (6-1)!입니다."),
                numeric_step("Step 2. 유리한 배치 수", "24", "A,B를 한 묶음으로 센 뒤, 그 안에서 C,D가 이웃하는 경우를 빼세요."),
                numeric_step("Step 3. 확률", "1/5", "유리한 경우를 전체 경우로 나누어 기약분수로 정리하세요."),
            ],
            final=numeric_step("최종 답", "1/5", "확률을 적으세요."),
            coach_hint="원순열 킬러는 조건을 하나씩 직접 세기보다, 먼저 강한 조건인 A,B의 인접을 묶고 금지 조건을 보완하는 편이 훨씬 안정적입니다.",
            expected_outline=["전체 원순열", "인접 조건 반영", "금지 경우 제거", "최종 확률"],
            final_prompt="예: 1/5",
            problem_type="원순열과 인접 금지",
        ),
        _killer_track_problem(
            track_title=spec["title"],
            track_id=spec["trackId"],
            index=6,
            title="조건부 최댓값 판정",
            statement=_condition_statement(
                "서로 독립인 세 개의 공정한 주사위를 동시에 한 번 던져 나온 눈의 최댓값을 M이라 하자.",
                [
                    "조건부 사건은 M=4 이다.",
                    "세 눈 가운데 4는 적어도 한 번 나타난다.",
                    "이 조건 아래에서 정확히 한 개의 주사위에서만 4가 나오는 경우를 구하려 한다.",
                ],
                "구하는 조건부확률을 구하시오.",
            ),
            achievement_codes=codes,
            steps=[
                numeric_step("Step 1. 조건부 표본공간", "37", "M=4인 경우의 수는 1~4만 쓰는 전체 경우에서 모두 1~3인 경우를 빼서 구하세요."),
                numeric_step("Step 2. 유리한 경우", "27", "정확히 하나만 4이면 4의 위치를 정하고 나머지 두 자리는 1~3 중에서 고르세요."),
                numeric_step("Step 3. 확률", "27/37", "유리한 경우를 조건부 표본공간으로 나누세요."),
            ],
            final=numeric_step("최종 답", "27/37", "확률을 적으세요."),
            coach_hint="조건부 최댓값 문제는 바로 비율을 쓰지 말고, 먼저 조건이 만든 새 표본공간을 다시 세는 것이 핵심입니다.",
            expected_outline=["조건부 표본공간", "정확히 한 번 등장", "기약분수 정리", "최종 답"],
            final_prompt="예: 27/37",
            problem_type="조건부 최댓값 확률",
        ),
        _killer_track_problem(
            track_title=spec["title"],
            track_id=spec["trackId"],
            index=7,
            title="고정점의 분산",
            statement=_condition_statement(
                "1,2,3,4,5,6을 한 줄로 임의로 배열하여 새로운 순열을 만든다.",
                [
                    "원래 자리와 같은 위치에 놓이는 수의 개수를 확률변수 X라 한다.",
                    "X의 분포를 직접 모두 세지 않고, 지표변수와 두 번째 계승적률을 이용해 접근한다.",
                    "같은 배열은 모두 같은 확률로 나온다.",
                ],
                "V(X)를 구하시오.",
            ),
            achievement_codes=codes,
            steps=[
                numeric_step("Step 1. E(X)", "1", "각 수가 제자리에 오는 사건의 지표변수를 두고 기대값의 선형성을 쓰세요."),
                numeric_step("Step 2. E(X(X-1))", "1", "서로 다른 두 수가 동시에 제자리에 오는 확률을 이용해 두 번째 계승적률을 구하세요."),
                numeric_step("Step 3. V(X)", "1", "V(X)=E(X(X-1))+E(X)-[E(X)]^2를 이용해 분산을 구하세요."),
            ],
            final=numeric_step("최종 답", "1", "분산을 적으세요."),
            coach_hint="순열형 확률변수는 분포를 전부 세지 않고도 지표변수와 계승적률로 훨씬 짧게 닫을 수 있습니다.",
            expected_outline=["지표변수 기대값", "동시 고정 확률", "분산 공식", "최종 답"],
            final_prompt="예: 1",
            problem_type="순열 고정점 분산",
        ),
        _killer_track_problem(
            track_title=spec["title"],
            track_id=spec["trackId"],
            index=8,
            title="분포표 복원과 분산",
            statement=_condition_statement(
                "확률변수 X는 0, 1, 2의 세 값만 가지며, 그 확률분포는 P(X=0)=p, P(X=1)=2p, P(X=2)=q 로 주어진다.",
                [
                    "p와 q는 0 이상 1 이하의 실수이다.",
                    "E(X)=1 이다.",
                    "V(X)=1/2 이다.",
                ],
                "P(X=1)의 값을 구하시오.",
            ),
            achievement_codes=codes,
            steps=[
                numeric_step("Step 1. p+q", "1/2", "전체확률과 기댓값 식을 정리하면 p+q를 먼저 구할 수 있습니다."),
                numeric_step("Step 2. p", "1/4", "분산 조건 또는 E(X^2)를 이용해 p를 결정하세요."),
                numeric_step("Step 3. P(X=1)", "1/2", "P(X=1)=2p를 계산하세요."),
            ],
            final=numeric_step("최종 답", "1/2", "확률을 적으세요."),
            coach_hint="확률분포 복원형은 전체확률, 기댓값, 분산이 각각 서로 다른 식을 준다는 점을 이용해 한 식씩 줄여 나가면 됩니다.",
            expected_outline=["전체확률·기댓값 정리", "분산으로 계수 결정", "요구 확률 계산", "최종 답"],
            final_prompt="예: 1/2",
            problem_type="분포 복원과 분산",
        ),
        _killer_track_problem(
            track_title=spec["title"],
            track_id=spec["trackId"],
            index=9,
            title="상자 이동 뒤 색 확률",
            statement=_condition_statement(
                "상자 A에는 빨간 공 3개와 파란 공 2개가, 상자 B에는 빨간 공 2개와 파란 공 3개가 들어 있다.",
                [
                    "먼저 상자 A에서 공 1개를 무작위로 꺼내 상자 B로 옮긴다.",
                    "그다음 상자 B에서 공 1개를 무작위로 꺼낸다.",
                    "공은 색만 구별하고, 같은 색 공은 서로 구별하지 않는다.",
                ],
                "마지막에 꺼낸 공이 빨간 공일 확률을 구하시오.",
            ),
            achievement_codes=codes,
            steps=[
                numeric_step("Step 1. 빨간 공을 옮기는 경우", "1/2", "빨간 공을 옮기면 상자 B의 빨간 공 비율이 어떻게 바뀌는지 먼저 구하세요."),
                numeric_step("Step 2. 파란 공을 옮기는 경우", "1/3", "파란 공을 옮기면 상자 B의 빨간 공 비율이 어떻게 바뀌는지 구하세요."),
                numeric_step("Step 3. 전체 확률", "13/30", "두 경우를 가중평균처럼 합쳐 전체 확률을 구하세요."),
            ],
            final=numeric_step("최종 답", "13/30", "확률을 적으세요."),
            coach_hint="색을 옮기는 문제는 바로 한 번에 세지 말고, 먼저 어떤 색이 이동했는지로 경우를 가른 뒤 마지막에 다시 합치는 것이 안정적입니다.",
            expected_outline=["이동 색 분리", "각 경우 확률", "경우 결합", "최종 답"],
            final_prompt="예: 13/30",
            problem_type="상자 이동 확률",
        ),
        _killer_track_problem(
            track_title=spec["title"],
            track_id=spec["trackId"],
            index=10,
            title="중앙값 조건과 짝수 개수",
            statement=_condition_statement(
                "1부터 9까지의 자연수가 하나씩 적힌 카드 9장 중 서로 다른 5장을 같은 확률로 택한다.",
                [
                    "택한 5개의 수를 크기순으로 정리했을 때 중앙값이 5이다.",
                    "다섯 수 가운데 짝수의 개수가 정확히 2개인 경우만 세려 한다.",
                    "같은 카드 집합은 한 가지 경우로 본다.",
                ],
                "이 조건부확률을 구하시오.",
            ),
            achievement_codes=codes,
            steps=[
                numeric_step("Step 1. 조건부 전체 경우", "36", "중앙값이 5이면 1~4에서 2개, 6~9에서 2개를 고르는 경우만 셉니다."),
                numeric_step("Step 2. 유리한 경우", "16", "좌우에서 각각 짝수 1개, 홀수 1개씩 고르는 경우를 세세요."),
                numeric_step("Step 3. 확률", "4/9", "유리한 경우를 전체 경우로 나누세요."),
            ],
            final=numeric_step("최종 답", "4/9", "확률을 적으세요."),
            coach_hint="중앙값 조건이 붙으면 먼저 중앙값을 기준으로 좌우를 분리하고, 그 안에서 짝홀 조건을 다시 세는 두 단계 사고가 필요합니다.",
            expected_outline=["중앙값 조건 분리", "짝홀 경우 계산", "조건부 확률", "최종 답"],
            final_prompt="예: 4/9",
            problem_type="중앙값 조건 조합",
        ),
    ]


def _geometry_killer_problems(spec: dict) -> list[dict]:
    codes = _achievement_codes_for_course_ids(spec["courseIds"])
    return [
        _killer_track_problem(
            track_title=spec["title"],
            track_id=spec["trackId"],
            index=1,
            title="쌍곡선 복원",
            statement=_condition_statement(
                "쌍곡선 x^2/a^2 - y^2/b^2 = 1 (a>0, b>0)에 대하여",
                [
                    "두 점근선의 기울기는 각각 4/3, -4/3 이다.",
                    "두 초점 사이의 거리는 10이다.",
                    "점근선에서 읽은 비율과 초점 거리 조건을 함께 이용해 표준형을 복원하려 한다.",
                ],
                "a^2+b^2의 값을 구하시오.",
            ),
            achievement_codes=codes,
            steps=[
                exact_step("Step 1. 비율", "b/a=4/3", "점근선 기울기에서 b/a를 읽으세요."),
                exact_step("Step 2. a, b", "a=3, b=4", "c=5와 a:b=3:4를 이용해 a, b를 구하세요."),
                numeric_step("Step 3. a^2+b^2", "25", "값을 계산하세요."),
            ],
            final=numeric_step("최종 답", "25", "최종 값을 적으세요."),
            coach_hint="기하 킬러는 식을 많이 쓰는 것이 아니라 비율과 초점 거리의 관계를 한 줄로 묶는 속도가 중요합니다.",
            expected_outline=["점근선 비율", "초점 거리 적용", "제곱합 계산", "최종 답"],
            final_prompt="예: 25",
            problem_type="쌍곡선 복원",
        ),
        _killer_track_problem(
            track_title=spec["title"],
            track_id=spec["trackId"],
            index=2,
            title="타원 초점 거리",
            statement=_condition_statement(
                "두 초점이 F1(-4,0), F2(4,0)인 타원에 대하여",
                [
                    "타원 위의 한 점 P가 PF1=10, PF2=2를 만족한다.",
                    "타원의 중심은 원점이고 장축은 x축과 평행하다.",
                    "초점까지의 거리 합으로 a를, 초점거리와의 관계로 b를 복원하려 한다.",
                ],
                "이 타원의 a^2+b^2의 값을 구하시오.",
            ),
            achievement_codes=codes,
            steps=[
                numeric_step("Step 1. a", "6", "타원에서는 PF1+PF2=2a 입니다."),
                numeric_step("Step 2. b^2", "20", "c=4, a=6에서 b^2=a^2-c^2를 쓰세요."),
                numeric_step("Step 3. a^2+b^2", "56", "최종 값을 계산하세요."),
            ],
            final=numeric_step("최종 답", "56", "최종 값을 적으세요."),
            coach_hint="초점 거리 문제가 나오면 좌표보다 먼저 PF1+PF2=2a, c^2=a^2-b^2를 자동으로 꺼내야 합니다.",
            expected_outline=["2a 복원", "b^2 계산", "합 계산", "최종 답"],
            final_prompt="예: 56",
            problem_type="타원 초점 거리",
        ),
        _killer_track_problem(
            track_title=spec["title"],
            track_id=spec["trackId"],
            index=3,
            title="벡터 직교 조건",
            statement=_condition_statement(
                "두 벡터 a, b에 대하여",
                [
                    "|a|=3, |b|=2, a·b=3 이다.",
                    "벡터 p=2a-b, q=a+tb 로 정의한다.",
                    "p와 q가 서로 수직이 되도록 하는 실수 t를 이용해 |q|^2을 구하려 한다.",
                ],
                "|q|^2의 값을 구하시오.",
            ),
            achievement_codes=codes,
            steps=[
                numeric_step("Step 1. t", "-6", "(2a-b)·(a+tb)=0을 전개해 t를 구하세요."),
                exact_step("Step 2. q", "a-6b", "구한 t를 q에 대입하세요."),
                numeric_step("Step 3. |q|^2", "117", "|a-6b|^2를 전개하세요."),
            ],
            final=numeric_step("최종 답", "117", "최종 값을 적으세요."),
            coach_hint="벡터 킬러는 좌표를 바로 잡기보다 내적 조건을 식으로 전개해 계수부터 정리하는 편이 더 빠릅니다.",
            expected_outline=["직교식 전개", "계수 결정", "노름 제곱 계산", "최종 답"],
            final_prompt="예: 117",
            problem_type="벡터 직교 조건",
        ),
        _killer_track_problem(
            track_title=spec["title"],
            track_id=spec["trackId"],
            index=4,
            title="사면체 내부 분할",
            statement=_condition_statement(
                "좌표공간에서 네 점 O(0,0,0), A(3,0,0), B(0,4,0), C(0,0,6)가 이루는 사면체 OABC가 있다.",
                [
                    "점 P는 선분 AB 위의 점으로 AP:PB=1:2 이다.",
                    "점 Q는 선분 OC 위의 점으로 OQ:QC=2:1 이다.",
                    "좌표와 내분비를 이용해 작은 사면체 OAPQ의 부피를 구하려 한다.",
                ],
                "사면체 OAPQ의 부피를 구하시오.",
            ),
            achievement_codes=codes,
            steps=[
                exact_step("Step 1. P, Q", "P=(2,4/3,0), Q=(0,0,4)", "내분점 공식을 이용해 점의 좌표를 구하세요."),
                numeric_step("Step 2. 6배 부피", "16", "det(OA, OP, OQ)의 절댓값을 구하세요."),
                numeric_step("Step 3. 부피", "8/3", "사면체 부피는 det의 절댓값을 6으로 나눈 값입니다."),
            ],
            final=numeric_step("최종 답", "8/3", "최종 값을 적으세요."),
            coach_hint="공간 킬러는 밑면을 억지로 그리기보다 좌표와 determinant로 바로 들어가면 훨씬 짧아집니다.",
            expected_outline=["내분점 좌표", "det 계산", "부피 정리", "최종 답"],
            final_prompt="예: 8/3",
            problem_type="사면체 내부 분할",
        ),
        _killer_track_problem(
            track_title=spec["title"],
            track_id=spec["trackId"],
            index=5,
            title="직교 점근선 쌍곡선",
            statement=_condition_statement(
                "쌍곡선 x^2/a^2 - y^2/b^2 = 1 (a>0, b>0)에 대하여",
                [
                    "두 점근선은 서로 수직이다.",
                    "한 초점의 좌표는 (5,0)이다.",
                    "점근선의 직교 조건과 초점 조건을 함께 이용해 실축의 길이를 복원하려 한다.",
                ],
                "이 쌍곡선의 실축의 길이를 구하시오.",
            ),
            achievement_codes=codes,
            steps=[
                exact_step("Step 1. 점근선 조건", "a=b", "점근선의 기울기가 서로 직교이면 b/a=1입니다."),
                exact_step("Step 2. a^2", "25/2", "c^2=a^2+b^2와 a=b를 이용하세요."),
                expr_step("Step 3. 실축의 길이", "5*sqrt(2)", "실축의 길이는 2a 입니다.", display="5√2"),
            ],
            final=expr_step("최종 답", "5*sqrt(2)", "최종 값을 적으세요.", display="5√2"),
            coach_hint="쌍곡선 복원형이라도 기울기 대신 직교 조건이 보이면 a=b라는 대칭부터 먼저 잡는 편이 훨씬 빠릅니다.",
            expected_outline=["직교 점근선 해석", "초점 거리 적용", "실축 길이 계산", "최종 답"],
            final_prompt="예: 5√2",
            problem_type="직교 점근선 쌍곡선",
        ),
        _killer_track_problem(
            track_title=spec["title"],
            track_id=spec["trackId"],
            index=6,
            title="이심률과 장축",
            statement=_condition_statement(
                "타원 x^2/a^2 + y^2/b^2 = 1 (a>b>0)에 대하여",
                [
                    "장축의 길이는 10이다.",
                    "이심률은 3/5 이다.",
                    "장축 길이와 이심률을 함께 사용해 a와 c를 먼저 복원한 뒤 b를 구하려 한다.",
                ],
                "a^2+b^2의 값을 구하시오.",
            ),
            achievement_codes=codes,
            steps=[
                exact_step("Step 1. a, c", "a=5, c=3", "장축의 길이와 이심률에서 a와 c를 복원하세요."),
                numeric_step("Step 2. b^2", "16", "b^2=a^2-c^2를 이용하세요."),
                numeric_step("Step 3. a^2+b^2", "41", "최종 값을 계산하세요."),
            ],
            final=numeric_step("최종 답", "41", "최종 값을 적으세요."),
            coach_hint="초점 거리 대신 이심률이 주어지면 e=c/a부터 바로 읽어 a와 c를 먼저 닫는 것이 핵심입니다.",
            expected_outline=["장축과 이심률 해석", "b^2 계산", "합 계산", "최종 답"],
            final_prompt="예: 41",
            problem_type="이심률과 장축",
        ),
        _killer_track_problem(
            track_title=spec["title"],
            track_id=spec["trackId"],
            index=7,
            title="합차 벡터 내적",
            statement=_condition_statement(
                "두 벡터 a, b에 대하여",
                [
                    "|a+b|=7 이다.",
                    "|a-b|=3 이다.",
                    "좌표를 직접 잡지 않고 합벡터와 차벡터의 제곱을 비교하여 내적을 구하려 한다.",
                ],
                "a·b의 값을 구하시오.",
            ),
            achievement_codes=codes,
            steps=[
                exact_step("Step 1. 제곱식", "49-9=40", "|a+b|^2-|a-b|^2를 계산하세요."),
                exact_step("Step 2. 내적 계수", "4a·b=40", "두 식의 차가 4a·b가 된다는 점을 이용하세요."),
                numeric_step("Step 3. a·b", "10", "내적값을 정리하세요."),
            ],
            final=numeric_step("최종 답", "10", "최종 값을 적으세요."),
            coach_hint="벡터 킬러가 꼭 좌표형일 필요는 없습니다. 합벡터와 차벡터가 보이면 제곱식의 차로 바로 내적을 닫을 수 있습니다.",
            expected_outline=["합차 제곱식", "내적 계수 비교", "최종 계산", "최종 답"],
            final_prompt="예: 10",
            problem_type="합차 벡터 내적",
        ),
        _killer_track_problem(
            track_title=spec["title"],
            track_id=spec["trackId"],
            index=8,
            title="원점에서 평면까지 거리",
            statement=_condition_statement(
                "좌표공간의 세 점 A(4,0,0), B(0,6,0), C(0,0,3)이 정하는 평면을 α라 하자.",
                [
                    "평면 α는 세 좌표축과 서로 다른 점에서 만난다.",
                    "원점 O(0,0,0)에서 평면 α까지의 거리를 구하려 한다.",
                    "최종적으로는 그 거리의 제곱을 답으로 적는다.",
                ],
                "원점 O에서 평면 α까지의 거리의 제곱을 구하시오.",
            ),
            achievement_codes=codes,
            steps=[
                exact_step("Step 1. 평면 방정식", "3x+2y+4z-12=0", "절편형 x/4+y/6+z/3=1을 정리하세요."),
                exact_step("Step 2. 거리 제곱 분자", "12^2", "원점에서의 거리 공식 분자를 제곱하세요."),
                exact_step("Step 3. 거리의 제곱", "144/29", "분모는 3^2+2^2+4^2 입니다."),
            ],
            final=exact_step("최종 답", "144/29", "최종 값을 적으세요."),
            coach_hint="공간도형 킬러에서 평면이 보이면 좌표를 많이 그리기보다 절편형이나 일반형으로 바꾼 뒤 거리 공식으로 바로 들어가는 게 훨씬 빠릅니다.",
            expected_outline=["평면 방정식 복원", "거리 공식 적용", "제곱 정리", "최종 답"],
            final_prompt="예: 144/29",
            problem_type="원점에서 평면까지 거리",
        ),
        _killer_track_problem(
            track_title=spec["title"],
            track_id=spec["trackId"],
            index=9,
            title="직선과 평면의 교점",
            statement=_condition_statement(
                "세 점 A(4,0,0), B(0,6,0), C(0,0,3)이 정하는 평면을 α라 하고, 직선 l을 x=y=z로 둔다.",
                [
                    "직선 l과 평면 α는 한 점 P에서 만난다.",
                    "P의 세 좌표는 서로 같다.",
                    "교점 자체보다 좌표의 합을 빠르게 구하려 한다.",
                ],
                "점 P의 좌표의 합을 구하시오.",
            ),
            achievement_codes=codes,
            steps=[
                exact_step("Step 1. 평면 식", "x/4+y/6+z/3=1", "세 절편을 바로 읽어 절편형을 씁니다."),
                exact_step("Step 2. 직선 대입", "3t/4=1", "x=y=z=t를 대입하세요."),
                numeric_step("Step 3. 좌표의 합", "4", "t=4/3에서 3t를 계산하세요."),
            ],
            final=numeric_step("최종 답", "4", "최종 값을 적으세요."),
            coach_hint="직선과 평면의 교점형은 직선의 매개변수를 먼저 넣고, 마지막에 좌표합 같은 요구값으로 바로 접는 편이 안정적입니다.",
            expected_outline=["평면 절편형", "매개변수 대입", "요구값 계산", "최종 답"],
            final_prompt="예: 4",
            problem_type="직선과 평면의 교점",
        ),
        _killer_track_problem(
            track_title=spec["title"],
            track_id=spec["trackId"],
            index=10,
            title="포물선 접선 조건",
            statement=_condition_statement(
                "꼭짓점이 원점이고 초점이 x축 위에 있는 포물선을 C라 하자.",
                [
                    "직선 y=x+2는 포물선 C와 한 점에서만 만난다.",
                    "즉, 이 직선은 포물선 C의 접선이다.",
                    "표준형과 중근 조건을 함께 이용해 초점과 준선 사이의 거리를 복원하려 한다.",
                ],
                "포물선 C의 초점과 준선 사이의 거리를 구하시오.",
            ),
            achievement_codes=codes,
            steps=[
                exact_step("Step 1. 포물선 식", "y^2=8x", "직선 y=x+2를 대입해 중근 조건을 만족하는 표준형을 찾으세요."),
                numeric_step("Step 2. p", "2", "표준형 y^2=4px에서 p를 읽으세요."),
                numeric_step("Step 3. 거리", "4", "초점과 준선 사이의 거리는 2p 입니다."),
            ],
            final=numeric_step("최종 답", "4", "최종 값을 적으세요."),
            coach_hint="포물선 접선형은 교점 방정식이 중근을 가져야 한다는 한 줄을 먼저 떠올리면 바로 풀립니다.",
            expected_outline=["중근 조건", "표준형 복원", "거리 계산", "최종 답"],
            final_prompt="예: 4",
            problem_type="포물선 접선 조건",
        ),
    ]


def _killer_track_problems(spec: dict) -> list[dict]:
    if spec["trackId"] == "calculus":
        return _calculus_killer_problems(spec)
    if spec["trackId"] == "probability-statistics":
        return _probability_statistics_killer_problems(spec)
    if spec["trackId"] == "geometry":
        return _geometry_killer_problems(spec)
    return []


def _killer_track_lesson_pack(spec: dict, problems: list[dict]) -> dict:
    sample_problem = problems[0]
    return {
        "id": f"lesson-track-{spec['trackId']}-killer",
        "title": spec["packTitle"],
        "unitTitle": spec["packTitle"],
        "teacherName": "하늘 선생님",
        "conceptIds": _concept_ids_for_course_ids(spec["courseIds"]),
        "questionStarters": spec["questionStarters"],
        "curriculumMeta": {
            "trackId": spec["trackId"],
            "courseIds": spec["courseIds"],
            "mode": "killer-track",
            "achievementCodes": _achievement_codes_for_course_ids(spec["courseIds"]),
        },
        "scenes": [
            {
                "id": f"scene-track-{spec['trackId']}-killer-1",
                "title": f"{spec['title']} 킬러 오프닝",
                "narration": spec["description"],
                "teachingGoal": "조건이 긴 문제를 어떤 순서로 읽으면 좋을지 먼저 정리해볼까요?",
                "takeaway": "킬러 문제도 결국은 첫 해석이 흔들리지 않으면 훨씬 차분해집니다.",
                "examCue": "조건을 읽자마자 어떤 변수를 먼저 잡을지 스스로 말해보면 좋아요.",
                "practiceBridge": "이 장면이 끝나면 바로 최상위 킬러 시퀀스로 들어가 볼게요.",
                "autoAdvanceSeconds": 18,
                "objects": [
                    {"id": f"{spec['trackId']}-killer-title", "type": "heading", "x": 6, "y": 10, "w": 52, "content": spec["packTitle"]},
                    {"id": f"{spec['trackId']}-killer-subtitle", "type": "callout", "x": 8, "y": 24, "w": 48, "content": spec["subtitle"], "delayMs": 180},
                    {"id": f"{spec['trackId']}-killer-badge", "type": "badge", "x": 64, "y": 12, "w": 22, "content": f"{len(problems)}문항", "delayMs": 260},
                ],
            },
            {
                "id": f"scene-track-{spec['trackId']}-killer-2",
                "title": "킬러 독해 흐름",
                "narration": "한 문제를 끝까지 밀기 전에, 조건을 변수와 관계식으로 압축하는 흐름부터 같이 잡아볼게요.",
                "teachingGoal": "문항 사이를 이어 주는 공통 해석 프레임을 잡아볼까요?",
                "takeaway": "문장이 길수록 먼저 압축해서 보는 습관이 중요합니다.",
                "examCue": "첫 줄에서 미지수보다 조건 구조를 먼저 적어보면 좋습니다.",
                "practiceBridge": "문제마다 같은 해석 흐름이 반복된다고 생각하면 훨씬 편해집니다.",
                "autoAdvanceSeconds": 18,
                "objects": [
                    {
                        "id": f"{spec['trackId']}-killer-loop",
                        "type": "checklist",
                        "x": 8,
                        "y": 20,
                        "w": 44,
                        "h": 38,
                        "label": "최상위 킬러 풀이 흐름",
                        "items": spec["narrativeStages"],
                    },
                    {
                        "id": f"{spec['trackId']}-killer-table",
                        "type": "table",
                        "x": 56,
                        "y": 20,
                        "w": 34,
                        "h": 36,
                        "table": {
                            "headers": ["문항", "포인트"],
                            "rows": [[problem["title"], problem["problemType"]] for problem in problems],
                        },
                        "delayMs": 200,
                    },
                ],
            },
            {
                "id": f"scene-track-{spec['trackId']}-killer-3",
                "title": "대표 킬러 해부",
                "narration": "첫 문제를 대표 킬러로 놓고, 조건 번역 -> 중간 복원 -> 최종 계산이 어떻게 이어지는지 차근차근 해부해볼게요.",
                "teachingGoal": "최상위 문제에서도 첫 세 줄이 어떻게 정해지는지 같이 확인해볼까요?",
                "takeaway": "킬러도 결국은 첫 줄이 정리되면 훨씬 덜 복잡해집니다.",
                "examCue": "대표 문제의 첫 줄을 머릿속으로 먼저 말해보면 좋아요.",
                "practiceBridge": "이후 문제들도 같은 방식으로 읽어 가면 됩니다.",
                "autoAdvanceSeconds": 20,
                "objects": [
                    {"id": f"{spec['trackId']}-killer-problem", "type": "callout", "x": 8, "y": 18, "w": 42, "content": sample_problem["statement"]},
                    {"id": f"{spec['trackId']}-killer-outline", "type": "checklist", "x": 54, "y": 18, "w": 34, "h": 42, "label": "대표 풀이 흐름", "items": sample_problem["expectedOutline"], "delayMs": 200},
                ],
            },
            {
                "id": f"scene-track-{spec['trackId']}-killer-4",
                "title": "문항 간 서사",
                "narration": "이 묶음은 쉬운 반복이 아니라, 앞 문제에서 익힌 해석을 다음 문제의 출발점으로 끌고 가는 서사형 문제 묶음입니다.",
                "teachingGoal": "문항 사이가 어떻게 연결되는지 먼저 보고 갈까요?",
                "takeaway": "각 문제는 독립적이지만 읽는 방식은 점점 더 정교해집니다.",
                "examCue": "다음 문제로 갈수록 무엇이 하나씩 더 필요해지는지 생각해보세요.",
                "practiceBridge": "이제 첫 문제부터 순서대로 들어가 볼게요.",
                "autoAdvanceSeconds": 18,
                "objects": [
                    {
                        "id": f"{spec['trackId']}-killer-story",
                        "type": "table",
                        "x": 8,
                        "y": 18,
                        "w": 82,
                        "h": 42,
                        "table": {
                            "headers": ["1단계", "2단계", "3단계", "4단계"],
                            "rows": [[problems[0]["problemType"], problems[1]["problemType"], problems[2]["problemType"], problems[3]["problemType"]]],
                        },
                    },
                ],
            },
            {
                "id": f"scene-track-{spec['trackId']}-killer-5",
                "title": "최상위 킬러 시작",
                "narration": "이제 최상위 킬러 시퀀스로 들어가 볼게요. 이 문제 묶음은 1번부터 끝 문제까지 조건을 읽는 정교함이 조금씩 올라가도록 배치해두었습니다.",
                "teachingGoal": "강의에서 킬러 실전으로 자연스럽게 넘어가 볼까요?",
                "takeaway": "풀다가 막히면 계산보다 먼저 번역이 흔들린 지점으로 돌아오면 됩니다.",
                "examCue": "정답보다 먼저 첫 줄을 틀리지 않는 데 집중해보면 좋아요.",
                "practiceBridge": "문제 묶음은 1번부터 순서대로 이어집니다.",
                "autoAdvanceSeconds": 14,
                "objects": [
                    {"id": f"{spec['trackId']}-killer-start", "type": "badge", "x": 8, "y": 20, "w": 42, "content": spec["packTitle"]},
                    {"id": f"{spec['trackId']}-killer-route", "type": "checklist", "x": 8, "y": 34, "w": 42, "h": 28, "label": "풀이 원칙", "items": ["첫 줄 번역", "중간 복원", "최종 계산"], "delayMs": 180},
                ],
            },
        ],
    }


def _killer_track_problem_set(spec: dict, problems: list[dict]) -> dict:
    return {
        "id": f"set-track-{spec['trackId']}-killer",
        "title": spec["packTitle"],
        "lessonPackId": f"lesson-track-{spec['trackId']}-killer",
        "conceptIds": _concept_ids_for_course_ids(spec["courseIds"]),
        "mode": "killer-track",
        "problems": deepcopy(problems),
    }


def _worked_example_strategy_scene(unit: dict) -> dict:
    sample_problem = unit["problems"][0]
    rows = _problem_step_rows(sample_problem)
    outline = _outline_preview(sample_problem, 4)
    return {
        "id": f"scene-{unit['id']}-3",
        "title": "대표 예제 접근",
        "narration": (
            f"대표 예제 '{sample_problem['title']}'은(는) 계산보다 순서가 먼저입니다. "
            "문제를 읽자마자 무엇을 세우고, 어디서 판정하고, 어떤 형식으로 끝낼지부터 같이 잡아볼게요."
        ),
        "teachingGoal": "대표 예제를 풀기 전에 풀이 순서를 머릿속에 가볍게 정리해볼까요?",
        "takeaway": "풀이를 길게 쓰기보다 순서와 기준 식을 먼저 잡는 편이 훨씬 안정적입니다.",
        "examCue": "문제를 읽자마자 3단계 풀이 흐름을 말로 복기해보면 좋아요.",
        "practiceBridge": "이 장면이 끝나면 같은 순서로 첫 문제에 바로 들어가 볼게요.",
        "autoAdvanceSeconds": 22,
        "source": f"{PDF_SOURCE_PATH} p.{unit['pdfPages']}",
        "objects": [
            {
                "id": f"{unit['id']}-sample-title",
                "type": "heading",
                "x": 6,
                "y": 10,
                "w": 50,
                "content": sample_problem["title"],
            },
            {
                "id": f"{unit['id']}-sample-statement",
                "type": "callout",
                "x": 8,
                "y": 23,
                "w": 38,
                "content": sample_problem["statement"],
                "delayMs": 160,
            },
            {
                "id": f"{unit['id']}-sample-strategy",
                "type": "table",
                "x": 50,
                "y": 22,
                "w": 42,
                "h": 44,
                "table": {
                    "headers": ["순서", "핵심 식", "확인 포인트"],
                    "rows": rows,
                },
                "delayMs": 340,
            },
            {
                "id": f"{unit['id']}-sample-why",
                "type": "table",
                "x": 8,
                "y": 62,
                "w": 50,
                "h": 22,
                "table": {
                    "headers": ["이 문제에서 먼저 볼 것", "이유"],
                    "rows": [
                        [outline[0], "첫 줄이 흔들리면 나머지 줄도 같이 흔들립니다"],
                        [outline[1] if len(outline) > 1 else "중간 판정", "계산이 아니라 판단이 점수를 갈라놓습니다"],
                    ],
                },
                "delayMs": 520,
            },
            {
                "id": f"{unit['id']}-sample-final",
                "type": "badge",
                "x": 8,
                "y": 86,
                "w": 34,
                "content": f"최종 답 {sample_problem.get('finalPrompt', '정리')}",
                "delayMs": 580,
            },
            {
                "id": f"{unit['id']}-sample-check",
                "type": "callout",
                "x": 62,
                "y": 62,
                "w": 28,
                "content": sample_problem["coachHint"],
                "delayMs": 520,
            },
        ],
    }


def _worked_example_board_scene(unit: dict) -> dict:
    sample_problem = unit["problems"][0]
    rows = _problem_step_rows(sample_problem)
    outline = _outline_preview(sample_problem, 4)
    objects: list[dict] = [
        {
            "id": f"{unit['id']}-board-title",
            "type": "heading",
            "x": 6,
            "y": 10,
            "w": 42,
            "content": "대표 예제 풀이 스캐폴드",
        },
        {
            "id": f"{unit['id']}-board-hint",
            "type": "table",
            "x": 8,
            "y": 22,
            "w": 38,
            "h": 42,
            "table": {
                "headers": ["풀이 줄", "왜 이 줄이 먼저인가"],
                "rows": [
                    [outline[0], "조건을 읽자마자 풀이 출발점을 고정하기 위해"],
                    [outline[1] if len(outline) > 1 else "중간 판정", "무슨 기준으로 걸러낼지 먼저 정하기 위해"],
                    [outline[2] if len(outline) > 2 else "정리", "끝에서 흔들리지 않도록 미리 형식을 보는 줄입니다"],
                ],
            },
            "delayMs": 180,
        },
        {
            "id": f"{unit['id']}-board-read",
            "type": "table",
            "x": 8,
            "y": 68,
            "w": 34,
            "h": 18,
            "table": {
                "headers": ["문제 읽기", "바로 할 일"],
                "rows": [
                    ["조건", "먼저 표시"],
                    ["질문", "한 줄 번역"],
                ],
            },
            "delayMs": 260,
        },
    ]
    if sample_problem.get("evaluationType") == "tangent-line":
        expression = str(sample_problem.get("functionSpec", {}).get("expression") or "f(x)")
        point_x = sample_problem.get("functionSpec", {}).get("pointX")
        objects.extend(
            [
                {
                    "id": f"{unit['id']}-board-eq1",
                    "type": "equation",
                    "x": 46,
                    "y": 18,
                    "w": 42,
                    "content": f"f(x) = {expression}",
                    "delayMs": 240,
                },
                {
                    "id": f"{unit['id']}-board-eq2",
                    "type": "equation",
                    "x": 46,
                    "y": 30,
                    "w": 42,
                    "content": f"x = {point_x} 에서의 접선을 본다",
                    "delayMs": 340,
                },
                {
                    "id": f"{unit['id']}-board-graph",
                    "type": "graph",
                    "x": 44,
                    "y": 42,
                    "w": 48,
                    "h": 28,
                    "graphSpec": {
                        "function": expression,
                        "xMin": float(point_x) - 3 if point_x is not None else -3,
                        "xMax": float(point_x) + 3 if point_x is not None else 3,
                        "yMin": -8,
                        "yMax": 12,
                        "tangentAt": point_x,
                        "markLabel": f"x={point_x}" if point_x is not None else "접점",
                    },
                    "delayMs": 460,
                },
            ]
        )
    else:
        objects.extend(
            [
                {
                    "id": f"{unit['id']}-board-table",
                    "type": "table",
                    "x": 44,
                    "y": 18,
                    "w": 48,
                    "h": 40,
                    "table": {
                        "headers": ["순서", "써야 할 식", "확인"],
                        "rows": rows,
                    },
                    "delayMs": 320,
                },
                {
                    "id": f"{unit['id']}-board-table-extra",
                    "type": "table",
                    "x": 46,
                    "y": 62,
                    "w": 42,
                    "h": 24,
                    "table": {
                        "headers": ["막히는 지점", "다시 붙잡을 기준"],
                        "rows": [
                            ["첫 줄이 안 보일 때", _problem_focus_checks(sample_problem)[0]],
                            ["중간 계산이 길어질 때", _problem_focus_checks(sample_problem)[1]],
                            ["마지막 정리가 흔들릴 때", _problem_focus_checks(sample_problem)[2]],
                        ],
                    },
                    "delayMs": 460,
                },
            ]
        )
    objects.append(
        {
            "id": f"{unit['id']}-board-badge",
            "type": "badge",
            "x": 8,
            "y": 88,
            "w": 42,
            "content": f"현재 문제 연결 {sample_problem['title']}",
            "delayMs": 540,
        }
    )
    return {
        "id": f"scene-{unit['id']}-4",
        "title": "대표 예제 해설",
        "narration": (
            "이 장면에서는 실제 풀이를 끝까지 밀기보다, 문제를 보는 눈을 먼저 맞춰볼게요. "
            "질문이 생기면 지금 보이는 식, 표, 그래프를 기준으로 바로 다시 설명할 수 있습니다."
        ),
        "teachingGoal": "대표 예제를 시험장에서 보는 순서대로 칠판에 얹어볼까요?",
        "takeaway": "좋은 풀이는 계산량보다 시선이 움직이는 순서가 안정적입니다.",
        "examCue": "보이는 칠판 요소 중 하나를 골라 질문해도 바로 이어서 설명할 수 있으면 좋습니다.",
        "practiceBridge": "다음 문제 묶음에서도 이 스캐폴드를 그대로 써보면 됩니다.",
        "autoAdvanceSeconds": 24,
        "source": f"{PDF_SOURCE_PATH} p.{unit['pdfPages']}",
        "objects": objects,
    }


def _worked_example_long_scenes(unit: dict) -> list[dict]:
    sample_problem = unit["problems"][0]
    outline = _outline_preview(sample_problem, 4)
    rows = _problem_step_rows(sample_problem)
    return [
        {
            "id": f"scene-{unit['id']}-worked-read",
            "title": "대표 예제 문제 읽기",
            "narration": (
                f"이제 대표 예제 '{sample_problem['title']}'를 실제 수업처럼 처음부터 천천히 읽어볼게요. "
                "문제를 받자마자 계산으로 들어가는 게 아니라, 조건과 질문이 어디서 갈리는지 먼저 잡는 게 핵심입니다."
            ),
            "teachingGoal": "대표 예제를 읽는 첫 10초의 시선을 같이 맞춰봅니다.",
            "takeaway": "문제 읽기만 제대로 돼도 풀이 절반은 이미 정리된 상태가 됩니다.",
            "examCue": "조건, 질문, 끝줄 형식을 따로 나눠 읽는 습관을 들여보면 좋아요.",
            "practiceBridge": "이 장면이 끝나면 왜 이 첫 줄을 선택하는지 바로 이어서 볼게요.",
            "autoAdvanceSeconds": 22,
            "source": f"{PDF_SOURCE_PATH} p.{unit['pdfPages']}",
            "objects": [
                {
                    "id": f"{unit['id']}-worked-read-statement",
                    "type": "callout",
                    "x": 8,
                    "y": 20,
                    "w": 42,
                    "content": sample_problem["statement"],
                },
                {
                    "id": f"{unit['id']}-worked-read-table",
                    "type": "table",
                    "x": 52,
                    "y": 20,
                    "w": 36,
                    "h": 40,
                    "table": {
                        "headers": ["읽는 순서", "지금 확인할 것"],
                        "rows": [
                            ["조건", _problem_focus_checks(sample_problem)[0]],
                            ["질문", outline[0]],
                            ["끝줄", sample_problem.get("finalPrompt") or "최종 답 형식"],
                        ],
                    },
                    "delayMs": 180,
                },
            ],
        },
        {
            "id": f"scene-{unit['id']}-worked-first-line",
            "title": "대표 예제 첫 줄 선택",
            "narration": (
                "좋은 강의는 답을 빨리 내는 강의가 아니라, 왜 이 첫 줄을 써야 하는지를 납득시키는 강의입니다. "
                "그래서 여기서는 첫 줄이 왜 자연스럽게 나오는지부터 같이 잡아볼게요."
            ),
            "teachingGoal": "대표 예제에서 첫 줄을 선택하는 이유를 분명하게 잡습니다.",
            "takeaway": "첫 줄은 외운 문장이 아니라, 조건을 식으로 바꾼 결과입니다.",
            "examCue": "다른 문제를 보더라도 왜 이 줄이 먼저 나오는지 설명할 수 있어야 합니다.",
            "practiceBridge": "첫 줄이 잡혔으면 이제 중간에 어디서 판정이 들어가는지 이어서 볼게요.",
            "autoAdvanceSeconds": 22,
            "source": f"{PDF_SOURCE_PATH} p.{unit['pdfPages']}",
            "objects": [
                {
                    "id": f"{unit['id']}-worked-first-table",
                    "type": "table",
                    "x": 8,
                    "y": 20,
                    "w": 56,
                    "h": 40,
                    "table": {
                        "headers": ["문제에서 읽은 것", "바로 적는 첫 줄", "왜 이렇게 쓰는가"],
                        "rows": [
                            ["주어진 조건", unit["contentElements"][0] if unit["contentElements"] else unit["domainTitle"], "문제의 출발점을 정하기 위해"],
                            ["핵심 질문", outline[0], "계산보다 먼저 기준 식을 고정하기 위해"],
                            ["선생님이 잡아주는 기준", sample_problem["coachHint"], "문제 전체의 줄 순서를 흔들리지 않게 하기 위해"],
                        ],
                    },
                    "delayMs": 180,
                },
                {
                    "id": f"{unit['id']}-worked-first-callout",
                    "type": "callout",
                    "x": 68,
                    "y": 24,
                    "w": 20,
                    "content": "첫 줄이 잡히면 이 문제는 이미 절반은 정리된 거예요.",
                    "delayMs": 260,
                },
            ],
        },
        {
            "id": f"scene-{unit['id']}-worked-middle",
            "title": "대표 예제 중간 전개",
            "narration": (
                "첫 줄 다음부터는 무작정 계산이 아니라, 어디서 판정하고 어디서 식을 바꿔야 하는지가 중요합니다. "
                "이 문제의 중간 전개를 교실 판서처럼 한 줄씩 짚어볼게요."
            ),
            "teachingGoal": "대표 예제의 중간 전개와 판단 포인트를 같이 봅니다.",
            "takeaway": "중간 전개는 계산이 아니라, 어떤 판단을 언제 넣는지의 문제입니다.",
            "examCue": "계산이 길어진다고 느껴지면 지금 표에서 어느 줄까지 왔는지 먼저 다시 확인해 보세요.",
            "practiceBridge": "중간 줄이 끝나면 이제 마지막 정리와 검산으로 자연스럽게 넘어갑니다.",
            "autoAdvanceSeconds": 24,
            "source": f"{PDF_SOURCE_PATH} p.{unit['pdfPages']}",
            "objects": [
                {
                    "id": f"{unit['id']}-worked-middle-table",
                    "type": "table",
                    "x": 8,
                    "y": 20,
                    "w": 58,
                    "h": 42,
                    "table": {
                        "headers": ["풀이 줄", "지금 해야 할 일", "놓치면 흔들리는 이유"],
                        "rows": [
                            [rows[0][0], rows[0][1], rows[0][2]],
                            [rows[1][0] if len(rows) > 1 else "중간 판정", rows[1][1] if len(rows) > 1 else "판정", rows[1][2] if len(rows) > 1 else "판정 근거가 빠지면 계산이 길어집니다"],
                            [rows[2][0] if len(rows) > 2 else "마지막 정리", rows[2][1] if len(rows) > 2 else "정리", rows[2][2] if len(rows) > 2 else "끝줄 형식이 흔들리기 쉽습니다"],
                        ],
                    },
                    "delayMs": 180,
                },
                {
                    "id": f"{unit['id']}-worked-middle-note",
                    "type": "callout",
                    "x": 68,
                    "y": 22,
                    "w": 20,
                    "content": "중간 줄에서 흔들리면 새 계산을 더 하기보다, 지금 어떤 판단이 필요한지 먼저 확인해볼게요.",
                    "delayMs": 260,
                },
            ],
        },
        {
            "id": f"scene-{unit['id']}-worked-final",
            "title": "대표 예제 끝줄 검산",
            "narration": (
                "좋은 해설은 마지막 답만 쓰고 끝나지 않습니다. "
                "왜 이 끝줄이 맞는지, 그리고 어디서 실수를 가장 많이 하는지까지 같이 확인해볼게요."
            ),
            "teachingGoal": "대표 예제의 마지막 정리와 검산 기준을 고정합니다.",
            "takeaway": "끝줄은 계산의 결과가 아니라, 앞에서 만든 흐름을 마무리하는 줄입니다.",
            "examCue": "답을 적고 나면 조건, 부호, 답 형식 세 가지를 아주 짧게 다시 보면 좋습니다.",
            "practiceBridge": "대표 예제가 끝났으니, 이제 같은 개념에서 가장 자주 나오는 실수로 바로 넘어가볼게요.",
            "autoAdvanceSeconds": 20,
            "source": f"{PDF_SOURCE_PATH} p.{unit['pdfPages']}",
            "objects": [
                {
                    "id": f"{unit['id']}-worked-final-table",
                    "type": "table",
                    "x": 8,
                    "y": 20,
                    "w": 56,
                    "h": 38,
                    "table": {
                        "headers": ["마지막에 확인할 것", "왜 꼭 봐야 하나"],
                        "rows": [
                            ["조건", "중간 계산은 맞아도 조건을 놓치면 답이 바로 바뀝니다"],
                            ["부호와 범위", "끝줄에서 가장 자주 흔들리는 지점입니다"],
                            ["답 형식", sample_problem.get("finalPrompt") or "최종 답 형식"],
                        ],
                    },
                    "delayMs": 180,
                },
                {
                    "id": f"{unit['id']}-worked-final-badge",
                    "type": "badge",
                    "x": 68,
                    "y": 22,
                    "w": 20,
                    "content": "대표 예제 끝",
                    "delayMs": 260,
                },
            ],
        },
    ]


def _killer_example_long_scenes(unit: dict) -> list[dict]:
    drill_problems = _drill_problems_for_unit(unit)
    killer_problem = next((problem for problem in drill_problems if problem.get("isKiller")), None)
    if killer_problem is None:
        killer_problem = drill_problems[-1] if drill_problems else unit["problems"][-1]
    outline = _outline_preview(killer_problem, 4)
    display_statement = killer_problem["statement"]
    if "(가)" not in display_statement and len(display_statement) < 120:
        display_statement = " ".join(
            [
                display_statement,
                f"이 문제를 볼 때는 먼저 '{outline[0]}'에서 출발하고,",
                "중간에서는 서로 다른 두 조건을 한 식으로 모아야 하며,",
                f"마지막에는 '{outline[-1]}'를 반드시 점검해야 합니다.",
            ]
        ).strip()
    return [
        {
            "id": f"scene-{unit['id']}-killer-read",
            "title": "킬러 예제 구조 읽기",
            "narration": (
                f"이제 '{killer_problem['title']}'를 진짜 킬러처럼 읽어볼게요. "
                "이 문제는 계산 자체보다, 어떤 개념이 섞였고 어느 조건이 출발점인지 읽어내는 게 더 중요합니다."
            ),
            "teachingGoal": "킬러 예제를 읽을 때 문제 구조부터 먼저 해부합니다.",
            "takeaway": "킬러 문제는 길어서 어려운 게 아니라, 구조를 먼저 못 잡으면 어려워집니다.",
            "examCue": "문장을 받으면 바로 계산하지 말고 어떤 개념이 섞였는지부터 짧게 정리해 보세요.",
            "practiceBridge": "구조를 읽었으니 이제 첫 줄을 어디서 꺼내는지 이어서 볼게요.",
            "autoAdvanceSeconds": 24,
            "source": f"{PDF_SOURCE_PATH} p.{unit['pdfPages']}",
            "objects": [
                {
                    "id": f"{unit['id']}-killer-read-problem",
                    "type": "callout",
                    "x": 8,
                    "y": 20,
                    "w": 42,
                    "content": display_statement,
                },
                {
                    "id": f"{unit['id']}-killer-read-structure",
                    "type": "table",
                    "x": 52,
                    "y": 20,
                    "w": 36,
                    "h": 40,
                    "table": {
                        "headers": ["이 문제를 볼 때", "먼저 잡을 것"],
                        "rows": [
                            ["섞인 개념", unit["domainTitle"]],
                            ["출발점", outline[0]],
                            ["가장 늦게 확인할 것", outline[-1]],
                        ],
                    },
                    "delayMs": 180,
                },
            ],
        },
        {
            "id": f"scene-{unit['id']}-killer-first",
            "title": "킬러 예제 첫 줄 선택",
            "narration": (
                "킬러라고 해서 첫 줄이 특별한 건 아닙니다. 오히려 대표 예제에서 보던 첫 줄을 더 정확하게 꺼내야 합니다. "
                "여기서는 왜 이 첫 줄이 자연스럽게 나오는지부터 다시 잡아볼게요."
            ),
            "teachingGoal": "킬러 예제에서 첫 줄을 선택하는 이유를 분명하게 합니다.",
            "takeaway": "킬러의 첫 줄은 새롭기보다 더 정확해야 합니다.",
            "examCue": "어려운 문제를 볼수록 첫 줄을 외우기보다, 조건이 어떤 식으로 바뀌는지 생각해보면 좋아요.",
            "practiceBridge": "첫 줄이 잡히면 이제 중간에서 어디서 구조를 바꿔야 하는지 이어서 볼게요.",
            "autoAdvanceSeconds": 24,
            "source": f"{PDF_SOURCE_PATH} p.{unit['pdfPages']}",
            "objects": [
                {
                    "id": f"{unit['id']}-killer-first-table",
                    "type": "table",
                    "x": 8,
                    "y": 20,
                    "w": 58,
                    "h": 40,
                    "table": {
                        "headers": ["조건", "첫 줄", "왜 이 줄인가"],
                        "rows": [
                            [killer_problem["title"], outline[0], "문제 전체를 가장 빨리 정리할 수 있는 출발점이기 때문입니다"],
                            ["선생님이 붙잡는 기준", killer_problem["coachHint"], "첫 줄이 흔들리면 뒤 계산도 같이 흔들리기 때문입니다"],
                            ["끝까지 유지할 것", unit["contentElements"][0] if unit["contentElements"] else unit["domainTitle"], "대표 예제와 같은 개념축을 유지해야 하기 때문입니다"],
                        ],
                    },
                    "delayMs": 180,
                },
                {
                    "id": f"{unit['id']}-killer-first-callout",
                    "type": "callout",
                    "x": 68,
                    "y": 24,
                    "w": 20,
                    "content": "여기서 첫 줄을 잘못 잡으면 계산을 아무리 오래 해도 방향이 틀어질 수 있어요.",
                    "delayMs": 260,
                },
            ],
        },
        {
            "id": f"scene-{unit['id']}-killer-middle",
            "title": "킬러 예제 중간 전환",
            "narration": (
                "킬러 문제의 승부는 대부분 중간 전환에서 갈립니다. "
                "어디서 식을 바꾸고, 어디서 조건을 다시 읽어야 하는지 한 줄씩 해설해볼게요."
            ),
            "teachingGoal": "킬러 예제에서 중간 전환이 들어가는 지점을 정확히 읽습니다.",
            "takeaway": "킬러 문제는 계산량보다 중간 전환을 어디서 만드는지가 더 중요합니다.",
            "examCue": "중간이 길어진다고 느껴지면 지금이 전환이 필요한 구간인지 먼저 확인해 보세요.",
            "practiceBridge": "중간 전환이 끝나면 마지막 줄과 검산이 더 분명하게 보일 거예요.",
            "autoAdvanceSeconds": 26,
            "source": f"{PDF_SOURCE_PATH} p.{unit['pdfPages']}",
            "objects": [
                {
                    "id": f"{unit['id']}-killer-middle-table",
                    "type": "table",
                    "x": 8,
                    "y": 20,
                    "w": 58,
                    "h": 42,
                    "table": {
                        "headers": ["구간", "지금 해야 할 일", "놓치면 생기는 일"],
                        "rows": [
                            ["첫 줄 직후", outline[1] if len(outline) > 1 else "중간 판정", "대표 예제와 다른 지점을 못 보고 계산이 길어집니다"],
                            ["중간 전개", outline[2] if len(outline) > 2 else "구조 복원", "조건이 어디서 식으로 바뀌는지 놓치기 쉽습니다"],
                            ["끝줄 직전", outline[-1], "버려지는 해와 답 형식이 동시에 흔들리기 쉽습니다"],
                        ],
                    },
                    "delayMs": 180,
                },
                {
                    "id": f"{unit['id']}-killer-middle-badge",
                    "type": "badge",
                    "x": 68,
                    "y": 22,
                    "w": 18,
                    "content": _problem_difficulty_badge(killer_problem),
                    "delayMs": 260,
                },
                {
                    "id": f"{unit['id']}-killer-middle-callout",
                    "type": "callout",
                    "x": 68,
                    "y": 48,
                    "w": 20,
                    "content": "킬러에서는 새 공식을 찾기보다, 이미 나온 식을 다시 읽는 순간이 꼭 나옵니다.",
                    "delayMs": 340,
                },
            ],
        },
        {
            "id": f"scene-{unit['id']}-killer-final",
            "title": "킬러 예제 끝줄 정리",
            "narration": (
                "마지막으로 킬러 예제를 끝까지 정리해볼게요. "
                "이 장면에서는 정답 자체보다, 왜 이 끝줄이 맞는지와 어디를 검산해야 하는지가 더 중요합니다."
            ),
            "teachingGoal": "킬러 예제의 끝줄과 검산 기준을 고정합니다.",
            "takeaway": "킬러 문제도 끝줄에서 보는 건 결국 조건, 형식, 버려지는 해입니다.",
            "examCue": "답을 적는 마지막 순간에 오히려 문제를 다시 한 번 짧게 읽어보는 습관이 도움이 됩니다.",
            "practiceBridge": "이제 실전 연결 장면으로 넘어가서, 방금 본 흐름을 문제풀이 행동으로 바꿔볼게요.",
            "autoAdvanceSeconds": 22,
            "source": f"{PDF_SOURCE_PATH} p.{unit['pdfPages']}",
            "objects": [
                {
                    "id": f"{unit['id']}-killer-final-table",
                    "type": "table",
                    "x": 8,
                    "y": 20,
                    "w": 56,
                    "h": 38,
                    "table": {
                        "headers": ["끝줄에서 볼 것", "왜 중요한가"],
                        "rows": [
                            ["조건", "킬러일수록 중간 계산은 맞아도 원래 조건과 어긋나는 경우가 생깁니다"],
                            ["답 형식", killer_problem.get("finalPrompt") or "최종 답 형식"],
                            ["버려지는 해", "긴 풀이 끝에서 가장 많이 놓치는 지점입니다"],
                        ],
                    },
                    "delayMs": 180,
                },
                {
                    "id": f"{unit['id']}-killer-final-callout",
                    "type": "callout",
                    "x": 68,
                    "y": 22,
                    "w": 20,
                    "content": "킬러의 마지막은 계산 실력보다 끝까지 기준을 놓치지 않는 힘에서 갈립니다.",
                    "delayMs": 260,
                },
            ],
        },
    ]


def _pitfall_scene(unit: dict) -> dict:
    pitfalls = _lesson_pitfalls(unit)
    return {
        "id": f"scene-{unit['id']}-5",
        "title": "실수 교정 보드",
        "narration": (
            "점수가 흔들리는 이유는 개념을 몰라서라기보다, 익숙한 문제에서 같은 실수를 반복하기 때문인 경우가 많습니다. "
            "그래서 함정과 교정 흐름을 한 장면에서 같이 정리해볼게요."
        ),
        "teachingGoal": "점수를 깎는 반복 실수를 교정 문장으로 바꿔볼까요?",
        "takeaway": "실수는 의지보다 확인 순서의 문제인 경우가 많습니다.",
        "examCue": "문제를 다 풀고 나면 마지막 10초를 어디에 써야 할지 떠올려 보세요.",
        "practiceBridge": "오답이 나오면 이 교정 문장으로 바로 돌아오면 됩니다.",
        "autoAdvanceSeconds": 20,
        "source": f"{PDF_SOURCE_PATH} p.{unit['pdfPages']}",
        "objects": [
            {
                "id": f"{unit['id']}-pitfall-table",
                "type": "table",
                "x": 8,
                "y": 20,
                "w": 56,
                "h": 46,
                "table": {
                    "headers": ["흔한 실수", "교정 흐름"],
                    "rows": [
                        [pitfalls[0], "정의와 조건을 먼저 확인한다"],
                        [pitfalls[1], "마지막 한 줄에서 부호와 범위를 다시 본다"],
                        [pitfalls[2], "기준 식을 먼저 적고 계산은 나중에 한다"],
                    ],
                },
            },
            {
                "id": f"{unit['id']}-pitfall-check",
                "type": "checklist",
                "x": 68,
                "y": 22,
                "w": 22,
                "h": 40,
                "label": "마지막 10초",
                "items": ["조건", "부호", "답 형식"],
                "delayMs": 260,
            },
        ],
    }


def _self_check_scene(unit: dict) -> dict:
    sample_problem = unit["problems"][0]
    return {
        "id": f"scene-{unit['id']}-6",
        "title": "30초 셀프체크",
        "narration": (
            "강의가 끝나기 전에 스스로 말할 수 있어야 하는 문장만 남겨볼게요. "
            "이 세 문장을 바로 말할 수 있으면 문제로 넘어가도 흐름이 잘 끊기지 않습니다."
        ),
        "teachingGoal": "강의 내용을 머릿속의 짧은 체크리스트로 압축해볼까요?",
        "takeaway": "이해는 길게 설명하는 능력보다 짧게 복기하는 능력에서 더 잘 드러납니다.",
        "examCue": "세 문장을 막힘없이 말할 수 있으면 실전 전환 준비가 된 셈입니다.",
        "practiceBridge": f"바로 이어서 '{sample_problem['title']}' 문제로 같은 흐름을 확인해볼게요.",
        "autoAdvanceSeconds": 18,
        "source": f"{PDF_SOURCE_PATH} p.{unit['pdfPages']}",
        "objects": [
            {
                "id": f"{unit['id']}-self-check",
                "type": "checklist",
                "x": 8,
                "y": 20,
                "w": 46,
                "h": 46,
                "label": "혼자 확인할 것",
                "items": _problem_focus_checks(sample_problem),
            },
            {
                "id": f"{unit['id']}-self-question",
                "type": "callout",
                "x": 58,
                "y": 24,
                "w": 32,
                "content": f"막히면 이렇게 물어보세요.\n{unit['questionStarters'][0]}",
                "delayMs": 260,
            },
            {
                "id": f"{unit['id']}-self-badge",
                "type": "metric",
                "x": 58,
                "y": 60,
                "w": 22,
                "content": "30 SEC CHECK",
                "delayMs": 420,
            },
        ],
    }


def _practice_bridge_scene(unit: dict) -> dict:
    sample_problem = unit["problems"][0]
    return {
        "id": f"scene-{unit['id']}-7",
        "title": "실전 문제 연결",
        "narration": (
            "이제 강의는 여기까지 보고 실전 확인으로 넘어가볼게요. "
            "맞히는 것도 중요하지만, 어느 단계에서 흔들리는지 확인하면서 강의와 문제를 왕복하는 게 더 중요합니다."
        ),
        "teachingGoal": "강의 내용을 곧바로 문제 묶음과 연결해볼까요?",
        "takeaway": "강의는 이해의 끝이 아니라 문제에 들어가기 전 호흡을 맞추는 단계입니다.",
        "examCue": "문제를 풀다가 멈추면 지금 본 장면의 순서로 다시 돌아오면 됩니다.",
        "practiceBridge": f"첫 문제는 '{sample_problem['title']}'입니다. 방금 본 풀이 흐름을 그대로 써보면 됩니다.",
        "autoAdvanceSeconds": 18,
        "source": f"{PDF_SOURCE_PATH} p.{unit['pdfPages']}",
        "objects": [
            {
                "id": f"{unit['id']}-bridge-problem",
                "type": "callout",
                "x": 8,
                "y": 20,
                "w": 44,
                "content": sample_problem["statement"],
            },
            {
                "id": f"{unit['id']}-bridge-actions",
                "type": "checklist",
                "x": 56,
                "y": 20,
                "w": 30,
                "h": 42,
                "label": "바로 할 일",
                "items": [
                    "강의 순서대로 첫 줄을 적는다",
                    "모르는 단계만 질문으로 다시 확인한다",
                    "오답이면 다시 보기 일정이 자동으로 다시 잡힌다",
                ],
                "delayMs": 220,
            },
            {
                "id": f"{unit['id']}-bridge-badge",
                "type": "badge",
                "x": 8,
                "y": 68,
                "w": 46,
                "content": f"문제 풀이 시작 {unit['courseTitle']} · {unit['domainTitle']}",
                "delayMs": 420,
            },
        ],
    }


def _school_teacher_element_scenes(unit: dict) -> list[dict]:
    scenes: list[dict] = []
    content_elements = list(unit.get("contentElements", []))
    starters = list(unit.get("questionStarters", [])) or ["이 부분을 다시 설명해줘"]
    for index, element in enumerate(content_elements, start=1):
        anchor_problem = unit["problems"][(index - 1) % len(unit["problems"])]
        drill_problems = _drill_problems_for_unit(unit)
        challenge_problem = drill_problems[min(index * 3, len(drill_problems) - 1)] if drill_problems else anchor_problem
        starter = starters[(index - 1) % len(starters)]
        kit = _element_lecture_kit(element, unit, anchor_problem)
        grading_steps = anchor_problem.get("gradingSpec", {}).get("steps", [])[:3]
        grading_rows = [
            [step.get("label", f"Step {step_index}"), step.get("expectedDisplay", ""), step.get("hint", "")]
            for step_index, step in enumerate(grading_steps, start=1)
        ] or [["첫 줄", kit["first_line"], "조건과 기준 식을 같이 적습니다"]]
        explanation_rows = _lecture_explanation_rows(element, kit, anchor_problem)
        board_rows = _board_reason_rows(kit)
        skill_rows = _killer_skill_rows(kit, anchor_problem, challenge_problem)
        application_rows = _application_bridge_rows(kit, anchor_problem, challenge_problem)
        scenes.extend(
            [
                {
                    "id": f"scene-{unit['id']}-element-{index}-1",
                    "title": f"{element} 핵심 설명",
                    "narration": (
                        f"{element}는 공식 이름만 기억한다고 풀리는 요소가 아닙니다. "
                        f"{kit['teacher_line']} 그래서 먼저 기준 문장과 첫 줄이 어떤 역할을 하는지부터 분명하게 잡아보겠습니다."
                    ),
                    "teachingGoal": f"{element}의 핵심 문장과 첫 줄을 먼저 고정합니다.",
                    "takeaway": f"{element}에서 점수를 가르는 건 암기량보다 첫 줄의 정확도입니다. {kit['why_it_matters']}",
                    "examCue": "문제를 읽으면 무엇부터 적어야 하는지 바로 떠올릴 수 있어야 합니다.",
                    "practiceBridge": "이 설명 바로 뒤에 칠판식 정리와 대표 예제로 이어집니다.",
                    "autoAdvanceSeconds": 22,
                    "source": f"{PDF_SOURCE_PATH} p.{unit['pdfPages']}",
                    "objects": [
                        {"id": f"{unit['id']}-element-{index}-heading", "type": "heading", "x": 6, "y": 10, "w": 42, "content": element},
                        {
                            "id": f"{unit['id']}-element-{index}-table",
                            "type": "table",
                            "x": 8,
                            "y": 22,
                            "w": 60,
                            "h": 42,
                            "table": {
                                "headers": ["구분", "교실에서 하는 말", "시험장에서의 의미"],
                                "rows": explanation_rows,
                            },
                            "delayMs": 140,
                        },
                        {"id": f"{unit['id']}-element-{index}-line", "type": "equation", "x": 8, "y": 68, "w": 50, "content": kit["first_line"], "delayMs": 300},
                        {"id": f"{unit['id']}-element-{index}-starter", "type": "callout", "x": 70, "y": 24, "w": 18, "content": starter, "delayMs": 240},
                    ],
                },
                {
                    "id": f"scene-{unit['id']}-element-{index}-2",
                    "title": f"{element} 자세한 해설",
                    "narration": (
                        f"{element}는 공식 이름만 아는 것으로는 잘 안 풀립니다. "
                        "교실에서 선생님이 말로 풀어주듯, 왜 첫 줄이 중요하고 조건이 어디서 식으로 바뀌는지 더 자세히 짚어보겠습니다."
                    ),
                    "teachingGoal": f"{element}를 문제에서 왜 먼저 보고, 어디서 한 번 더 점검하는지 이해합니다.",
                    "takeaway": "첫 줄을 잡는 기준과 중간 전환의 이유를 동시에 알면 응용 문제에서도 덜 흔들립니다.",
                    "examCue": "지금 문제라면 어떤 줄에서 조건이 식으로 바뀌는지 먼저 떠올려 보세요.",
                    "practiceBridge": "이 장면 뒤에는 실제 칠판 정리와 대표 문제 적용으로 바로 이어집니다.",
                    "autoAdvanceSeconds": 22,
                    "source": f"{PDF_SOURCE_PATH} p.{unit['pdfPages']}",
                    "objects": [
                        {
                            "id": f"{unit['id']}-element-{index}-deep-table",
                            "type": "table",
                            "x": 8,
                            "y": 18,
                            "w": 56,
                            "h": 42,
                            "table": {
                                "headers": ["교실 해설", "무슨 뜻인가", "문제에서 왜 필요한가"],
                                "rows": [
                                    [kit["board_lines"][0], "문제 조건을 풀이 첫 줄로 바꾸는 단계", "긴 문장을 읽자마자 출발점을 고정합니다"],
                                    [kit["board_lines"][1], "중간 전환이 왜 생기는지 보이는 단계", "응용 문제에서 구조를 복원할 수 있습니다"],
                                    [kit["board_lines"][2], "계산이 끝나기 전에 마지막 형식을 미리 보는 단계", "버려지는 해와 형식 실수를 줄입니다"],
                                ],
                            },
                            "delayMs": 180,
                        },
                        {
                            "id": f"{unit['id']}-element-{index}-deep-intuition",
                            "type": "table",
                            "x": 66,
                            "y": 20,
                            "w": 22,
                            "h": 40,
                            "table": {
                                "headers": ["문제 앞에서"],
                                "rows": [[row[0]] for row in kit["intuition_rows"][:3]],
                            },
                            "delayMs": 280,
                        },
                        {"id": f"{unit['id']}-element-{index}-deep-note", "type": "callout", "x": 8, "y": 66, "w": 80, "content": kit["why_it_matters"], "delayMs": 420},
                    ],
                },
                {
                    "id": f"scene-{unit['id']}-element-{index}-3",
                    "title": f"{element} 칠판 정리",
                    "narration": (
                        f"이제 {element}를 실제 칠판처럼 정리해보겠습니다. "
                        "정의, 조건, 마지막 검산이 어떤 줄 순서로 놓이는지 한 장으로 보이게 만드는 장면입니다."
                    ),
                    "teachingGoal": f"{element}를 칠판에서 어떤 줄 순서로 적는지 익힙니다.",
                    "takeaway": "같은 개념도 판서 순서가 잡히면 훨씬 덜 흔들립니다.",
                    "examCue": "첫 줄, 중간 판정, 마지막 검산이 모두 보여야 합니다.",
                    "practiceBridge": "바로 이어서 대표 문제에 같은 순서를 얹어봅니다.",
                    "autoAdvanceSeconds": 22,
                    "source": f"{PDF_SOURCE_PATH} p.{unit['pdfPages']}",
                    "objects": [
                        {"id": f"{unit['id']}-element-{index}-board-1", "type": "equation", "x": 8, "y": 18, "w": 36, "content": kit["board_lines"][0], "delayMs": 120},
                        {"id": f"{unit['id']}-element-{index}-board-2", "type": "equation", "x": 8, "y": 34, "w": 36, "content": kit["board_lines"][1], "delayMs": 260},
                        {"id": f"{unit['id']}-element-{index}-board-3", "type": "equation", "x": 8, "y": 50, "w": 36, "content": kit["board_lines"][2], "delayMs": 400},
                        {
                            "id": f"{unit['id']}-element-{index}-board-side",
                            "type": "table",
                            "x": 46,
                            "y": 18,
                            "w": 42,
                            "h": 42,
                            "table": {
                                "headers": ["칠판에서 적을 것", "이유"],
                                "rows": board_rows,
                            },
                            "delayMs": 220,
                        },
                        {"id": f"{unit['id']}-element-{index}-board-note", "type": "callout", "x": 8, "y": 66, "w": 80, "content": kit["why_it_matters"], "delayMs": 480},
                    ],
                },
                {
                    "id": f"scene-{unit['id']}-element-{index}-4",
                    "title": f"{element} 대표 적용",
                    "narration": (
                        f"방금 정리한 {element}를 바로 대표 문제에 연결합니다. "
                        "교실 수업처럼 예제를 통해 개념을 적용하는 장면입니다."
                    ),
                    "teachingGoal": f"{element}가 실제 문제에서 어떻게 쓰이는지 연결합니다.",
                    "takeaway": "개념은 예제에 꽂히는 순간 기억이 오래갑니다.",
                    "examCue": "대표 문제에서 어느 줄이 이 개념과 직접 연결되는지 찾으세요.",
                    "practiceBridge": "이후 실전 문제 묶음에서도 같은 연결을 반복합니다.",
                    "autoAdvanceSeconds": 21,
                    "source": f"{PDF_SOURCE_PATH} p.{unit['pdfPages']}",
                    "objects": [
                        {"id": f"{unit['id']}-element-{index}-problem", "type": "callout", "x": 8, "y": 20, "w": 40, "content": anchor_problem["statement"]},
                        {
                            "id": f"{unit['id']}-element-{index}-outline",
                            "type": "table",
                            "x": 50,
                            "y": 20,
                            "w": 38,
                            "h": 40,
                            "table": {
                                "headers": ["풀이 줄", "써야 할 것", "왜 이 줄인가"],
                                "rows": grading_rows,
                            },
                            "delayMs": 180,
                        },
                        {"id": f"{unit['id']}-element-{index}-problem-note", "type": "badge", "x": 8, "y": 64, "w": 36, "content": _problem_difficulty_badge(anchor_problem), "delayMs": 320},
                    ],
                },
                {
                    "id": f"scene-{unit['id']}-element-{index}-5",
                    "title": f"{element} 오개념 교정",
                    "narration": (
                        "학생이 자주 막히는 지점은 계산 실수보다도, 어디서 기준을 놓쳤는지 모르는 경우가 많습니다. "
                        "그래서 이 개념에서 특히 많이 나오는 착각과 교정 행동을 먼저 잡고 가겠습니다."
                    ),
                    "teachingGoal": f"{element}에서 점수를 깎는 전형적인 착각을 교정합니다.",
                    "takeaway": "오개념은 모르는 것이 아니라, 첫 줄과 판단 순서를 놓친 결과인 경우가 많습니다.",
                    "examCue": "비슷한 문제를 풀 때 내가 어떤 착각을 반복하는지 먼저 떠올려 보세요.",
                    "practiceBridge": "오개념을 먼저 잡아두면 뒤의 변형 예제와 킬러 예제도 훨씬 안정적으로 읽힙니다.",
                    "autoAdvanceSeconds": 20,
                    "source": f"{PDF_SOURCE_PATH} p.{unit['pdfPages']}",
                    "objects": [
                        {
                            "id": f"{unit['id']}-element-{index}-mis-table",
                            "type": "table",
                            "x": 8,
                            "y": 20,
                            "w": 62,
                            "h": 42,
                            "table": {
                                "headers": ["자주 하는 착각", "바른 해석", "교정 행동"],
                                "rows": kit["misconceptions"][:3],
                            },
                            "delayMs": 180,
                        },
                        {
                            "id": f"{unit['id']}-element-{index}-mis-problem",
                            "type": "callout",
                            "x": 72,
                            "y": 22,
                            "w": 16,
                            "content": challenge_problem["title"],
                            "delayMs": 260,
                        },
                    ],
                },
                {
                    "id": f"scene-{unit['id']}-element-{index}-6",
                    "title": f"{element} 변형 예제 해설",
                    "narration": (
                        f"{element}의 기본형이 익숙해졌다면, 이제 조건이 하나 더 붙은 변형 문제를 봐야 합니다. "
                        "이 장면에서는 기본 예제가 어떤 방식으로 길어지고 복잡해지는지 차근차근 연결해보겠습니다."
                    ),
                    "teachingGoal": f"{element}의 기본형과 변형형이 어떻게 이어지는지 봅니다.",
                    "takeaway": "변형 예제는 다른 문제가 아니라, 기본 예제 사이에 조건과 전환이 한 번 더 들어간 문제입니다.",
                    "examCue": "새로운 문제를 보면 무엇이 달라진 것인지보다 무엇이 그대로 남았는지 먼저 보세요.",
                    "practiceBridge": "다음 장면의 킬러 스킬은 지금 본 변형 예제에서 한 단계 더 올라간 순간에 필요합니다.",
                    "autoAdvanceSeconds": 22,
                    "source": f"{PDF_SOURCE_PATH} p.{unit['pdfPages']}",
                    "objects": [
                        {"id": f"{unit['id']}-element-{index}-ext-problem", "type": "callout", "x": 8, "y": 20, "w": 38, "content": challenge_problem["statement"], "delayMs": 140},
                        {
                            "id": f"{unit['id']}-element-{index}-ext-table",
                            "type": "table",
                            "x": 50,
                            "y": 20,
                            "w": 38,
                            "h": 42,
                            "table": {
                                "headers": ["단계", "무엇이 추가되는가", "그래도 유지할 것"],
                                "rows": kit["extension_rows"],
                            },
                            "delayMs": 240,
                        },
                        {
                            "id": f"{unit['id']}-element-{index}-ext-bridge",
                            "type": "table",
                            "x": 8,
                            "y": 66,
                            "w": 80,
                            "h": 18,
                            "table": {
                                "headers": ["기본에서 변형으로 갈 때"],
                                "rows": [[f"{row[0]}: {row[1]} / {row[2]}"] for row in application_rows],
                            },
                            "delayMs": 320,
                        },
                    ],
                },
                {
                    "id": f"scene-{unit['id']}-element-{index}-7",
                    "title": f"{element} 킬러 스킬",
                    "narration": (
                        f"{element}가 킬러 문제에 들어가면 계산량보다 구조 읽기가 더 중요해집니다. "
                        "어디서 중간 전환을 만들어야 하고, 무엇을 끝까지 놓치지 말아야 하는지 스킬 형태로 뽑아보겠습니다."
                    ),
                    "teachingGoal": f"{element}가 킬러 문제에서 어떻게 비틀리는지 읽습니다.",
                    "takeaway": "킬러 문제도 새 개념이 아니라 익숙한 줄을 끝까지 유지하는 힘에서 갈립니다.",
                    "examCue": "문장이 길어질수록 스킬을 새로 찾기보다 첫 줄과 중간 전환을 다시 붙잡아 보세요.",
                    "practiceBridge": "곧 이어지는 킬러 예제 해설에서 이 스킬들이 실제로 어떻게 쓰이는지 보여드릴게요.",
                    "autoAdvanceSeconds": 23,
                    "source": f"{PDF_SOURCE_PATH} p.{unit['pdfPages']}",
                    "objects": [
                        {
                            "id": f"{unit['id']}-element-{index}-skill-table",
                            "type": "table",
                            "x": 8,
                            "y": 20,
                            "w": 58,
                            "h": 42,
                            "table": {
                                "headers": ["스킬", "언제 쓰나", "효과"],
                                "rows": skill_rows,
                            },
                            "delayMs": 180,
                        },
                        {
                            "id": f"{unit['id']}-element-{index}-skill-problem",
                            "type": "callout",
                            "x": 68,
                            "y": 22,
                            "w": 20,
                            "content": challenge_problem["title"],
                            "delayMs": 260,
                        },
                        {
                            "id": f"{unit['id']}-element-{index}-skill-badge",
                            "type": "badge",
                            "x": 68,
                            "y": 58,
                            "w": 18,
                            "content": _problem_difficulty_badge(challenge_problem),
                            "delayMs": 380,
                        },
                    ],
                },
                {
                    "id": f"scene-{unit['id']}-element-{index}-8",
                    "title": f"{element} 킬러 예제 해설",
                    "narration": (
                        f"이제 {element}가 실제로 킬러 문제에서 어떻게 작동하는지 보겠습니다. "
                        "문제 문장을 단순히 번역하는 수준이 아니라, 어디서 구조를 복원하고 어떤 스킬을 끼워 넣는지 해설 중심으로 밀도 있게 보겠습니다."
                    ),
                    "teachingGoal": f"{element}가 킬러 예제에서 어떻게 쓰이는지 끝까지 해설합니다.",
                    "takeaway": "킬러 예제도 첫 줄, 중간 전환, 끝줄 검산이라는 큰 골격은 그대로입니다.",
                    "examCue": "긴 문장일수록 조건을 읽고 바로 구조가 떠오르게 만드는 연습이 중요합니다.",
                    "practiceBridge": "이 장면 다음에는 실제 문제로 들어가기 직전, 어떤 기준을 붙들고 가야 하는지 마지막으로 정리합니다.",
                    "autoAdvanceSeconds": 22,
                    "source": f"{PDF_SOURCE_PATH} p.{unit['pdfPages']}",
                    "objects": [
                        {
                            "id": f"{unit['id']}-element-{index}-killer-table",
                            "type": "table",
                            "x": 8,
                            "y": 22,
                            "w": 62,
                            "h": 40,
                            "table": {
                                "headers": ["문제 단계", "바로 꺼낼 줄", "왜 이 줄이 필요한가"],
                                "rows": [
                                    [challenge_problem["title"], kit["first_line"], "대표 문제에서 쓰던 첫 줄을 그대로 가져옵니다"],
                                    ["중간 전환", kit["advanced_moves"][0], "킬러에서는 이 전환을 직접 만들어야 하는 경우가 많습니다"],
                                    ["끝줄 정리", _outline_preview(challenge_problem, 1)[0], "답 형식과 버려지는 해를 끝까지 같이 봅니다"],
                                ],
                            },
                            "delayMs": 180,
                        },
                        {"id": f"{unit['id']}-element-{index}-killer-callout", "type": "callout", "x": 74, "y": 24, "w": 14, "content": challenge_problem["coachHint"], "delayMs": 280},
                    ],
                },
                {
                    "id": f"scene-{unit['id']}-element-{index}-9",
                    "title": f"{element} 실전 연결",
                    "narration": (
                        f"마지막으로 {element}를 실제 문제 풀이로 넘기기 직전의 상태로 정리해보겠습니다. "
                        "이 장면은 강의 내용이 문제풀이 행동으로 바로 연결되게 만드는 장면입니다."
                    ),
                    "teachingGoal": f"{element}를 문제풀이 행동으로 바꿔서 정리합니다.",
                    "takeaway": "강의를 많이 들은 학생보다, 지금 떠올린 기준을 문제에서 바로 쓰는 학생이 더 강합니다.",
                    "examCue": "문제를 받으면 첫 줄, 중간 전환, 끝줄 검산 순서를 그대로 다시 꺼내 보세요.",
                    "practiceBridge": "이제 문제 묶음으로 넘어가도 같은 기준으로 바로 첫 줄을 잡을 수 있습니다.",
                    "autoAdvanceSeconds": 22,
                    "source": f"{PDF_SOURCE_PATH} p.{unit['pdfPages']}",
                    "objects": [
                        {
                            "id": f"{unit['id']}-element-{index}-final-table",
                            "type": "table",
                            "x": 8,
                            "y": 20,
                            "w": 58,
                            "h": 42,
                            "table": {
                                "headers": ["문제 단계", "바로 꺼낼 줄", "고난도에서 덧붙일 것"],
                                "rows": application_rows,
                            },
                            "delayMs": 160,
                        },
                        {
                            "id": f"{unit['id']}-element-{index}-final-callout",
                            "type": "callout",
                            "x": 68,
                            "y": 22,
                            "w": 20,
                            "content": challenge_problem["coachHint"],
                            "delayMs": 280,
                        },
                    ],
                },
            ]
        )
    return scenes


def _question_language_scene(unit: dict) -> dict:
    sample_problem = unit["problems"][0]
    challenge_problem = (_drill_problems_for_unit(unit) or unit["problems"])[0]
    content_elements = list(unit.get("contentElements", []))
    rows = [
        ["대표 문제 조건", content_elements[0] if content_elements else unit["domainTitle"], "정의와 기준 식으로 바로 바꿉니다"],
        ["심화 문제 조건", challenge_problem.get("problemType", "심화 유형"), "조건을 다시 묶어 숨은 연결식을 찾습니다"],
        ["마지막 줄", "답 형식", sample_problem.get("finalPrompt") or "최종 답 정리"],
    ]
    return {
        "id": f"scene-{unit['id']}-question-language",
        "title": "조건 해석 훈련",
        "narration": (
            "문제가 길어질수록 문장 번역이 더 중요해집니다. "
            "대표 문제와 심화 문제를 같이 두고, 조건이 풀이 언어로 어떻게 바뀌는지 비교해보겠습니다."
        ),
        "teachingGoal": "대표 문제와 심화 문제의 조건 읽기 차이를 잡습니다.",
        "takeaway": "고난도 문제는 말이 많아지는 게 아니라, 같은 조건을 더 촘촘하게 읽게 되는 문제입니다.",
        "examCue": "조건을 읽을 때 바로 식이 안 보이면 어떤 줄을 먼저 만들지부터 생각해 보세요.",
        "practiceBridge": "이 장면 뒤의 심화 문제에서도 같은 번역 순서로 바로 들어갈 수 있습니다.",
        "autoAdvanceSeconds": 20,
        "source": f"{PDF_SOURCE_PATH} p.{unit['pdfPages']}",
        "objects": [
            {"id": f"{unit['id']}-language-title", "type": "heading", "x": 6, "y": 10, "w": 44, "content": "조건 → 풀이"},
            {
                "id": f"{unit['id']}-language-table",
                "type": "table",
                "x": 8,
                "y": 22,
                "w": 58,
                "h": 40,
                "table": {
                    "headers": ["문제에서 보는 말", "바로 떠올릴 것", "첫 줄"],
                    "rows": rows,
                },
                "delayMs": 160,
            },
            {
                "id": f"{unit['id']}-language-callout",
                "type": "callout",
                "x": 70,
                "y": 24,
                "w": 18,
                "content": "대표 문제와 심화 문제가 어디서 갈라지는지 같이 봅니다",
                "delayMs": 260,
            },
        ],
    }


def _challenge_bridge_scene(unit: dict) -> dict:
    drill_problems = _drill_problems_for_unit(unit)
    challenge_problem = drill_problems[min(12, len(drill_problems) - 1)] if drill_problems else unit["problems"][-1]
    skill_rows = [
        ["조건 재배치", "문장을 바로 계산하지 않고 같은 성질끼리 먼저 묶기"],
        ["중간 식 복원", "문제에 안 적힌 연결식을 스스로 한 줄 더 만드는 순간 찾기"],
        ["끝줄 선점", "최종 답 형식을 먼저 의식하고 중간 계산이 길어지는 걸 막기"],
    ]
    return {
        "id": f"scene-{unit['id']}-challenge-bridge",
        "title": "킬러 스킬 정리",
        "narration": (
            "대표 예제를 이해했다면 이제 같은 개념이 더 길고 낯선 문장으로 바뀐 경우도 연결해봐야 합니다. "
            "쉬운 문제와 어려운 문제의 차이는 개념이 아니라, 중간 구조를 한 번 더 복원하느냐에 있습니다."
        ),
        "teachingGoal": "기본 문제와 심화 문제의 연결 고리를 잡습니다.",
        "takeaway": "심화 문제도 첫 줄은 기본 문제와 크게 다르지 않습니다.",
        "examCue": "어려운 문제일수록 첫 줄과 중간 전환을 따로 봐야 합니다.",
        "practiceBridge": "곧바로 심화 문제 묶음에서도 이 연결을 반복해볼게요.",
        "autoAdvanceSeconds": 22,
        "source": f"{PDF_SOURCE_PATH} p.{unit['pdfPages']}",
        "objects": [
            {"id": f"{unit['id']}-challenge-title", "type": "heading", "x": 6, "y": 10, "w": 42, "content": "킬러 스킬"},
            {
                "id": f"{unit['id']}-challenge-problem",
                "type": "callout",
                "x": 8,
                "y": 22,
                "w": 38,
                "content": challenge_problem["statement"],
                "delayMs": 140,
            },
            {
                "id": f"{unit['id']}-challenge-outline",
                "type": "table",
                "x": 48,
                "y": 22,
                "w": 40,
                "h": 40,
                "table": {
                    "headers": ["심화 스킬", "무엇을 해야 하나"],
                    "rows": skill_rows,
                },
                "delayMs": 240,
            },
        ],
    }


def _concept_network_scene(unit: dict) -> dict:
    elements = list(unit.get("contentElements", [])) or [unit["domainTitle"]]
    rows: list[list[str]] = []
    for index, element in enumerate(elements):
        next_element = elements[index + 1] if index + 1 < len(elements) else "실전 문제"
        rows.append([element, f"{next_element}로 이어지는 이유", f"{element}에서 잡은 첫 줄이 {next_element}의 출발점이 됩니다"])
    return {
        "id": f"scene-{unit['id']}-concept-network",
        "title": "단원 구조 잡기",
        "narration": (
            "이 단원은 개념을 따로따로 외우는 순간 문제에서 끊깁니다. "
            "그래서 먼저 오늘 다루는 요소들이 어떤 순서로 이어지고, 각각이 문제에서 어떤 역할을 맡는지 한 장으로 묶어보겠습니다."
        ),
        "teachingGoal": "단원 전체를 어떤 순서로 이해해야 하는지 잡습니다.",
        "takeaway": "단원 구조를 먼저 잡아두면 뒤에서 나오는 예제와 킬러가 따로 보이지 않습니다.",
        "examCue": "문제를 읽으면서 지금 어느 개념 줄에 서 있는지 떠올려 보세요.",
        "practiceBridge": "이 장면 뒤부터는 개념 하나씩 실제 수업처럼 자세히 풀어갑니다.",
        "autoAdvanceSeconds": 20,
        "objects": [
            {"id": f"{unit['id']}-network-title", "type": "heading", "x": 6, "y": 10, "w": 40, "content": "단원 구조"},
            {
                "id": f"{unit['id']}-network-table",
                "type": "table",
                "x": 8,
                "y": 22,
                "w": 80,
                "h": 42,
                "table": {
                    "headers": ["개념", "어디로 이어지는가", "문제에서의 역할"],
                    "rows": rows,
                },
                "delayMs": 160,
            },
            {
                "id": f"{unit['id']}-network-note",
                "type": "callout",
                "x": 8,
                "y": 68,
                "w": 80,
                "content": "앞 개념의 첫 줄이 다음 개념의 첫 줄과 이어져야 수업이 문제까지 자연스럽게 연결됩니다.",
                "delayMs": 260,
            },
        ],
    }


def _multi_example_comparison_scene(unit: dict) -> dict:
    core_problem = unit["problems"][0]
    challenge_problem = (_drill_problems_for_unit(unit) or unit["problems"])[0]
    return {
        "id": f"scene-{unit['id']}-example-comparison",
        "title": "변형 예제 비교",
        "narration": (
            "한 문제만 보면 우연히 맞는 느낌이 남을 수 있습니다. "
            "기본 예제와 심화 예제를 나란히 놓고 무엇이 같고 무엇이 달라지는지 같이 보겠습니다."
        ),
        "teachingGoal": "기본 예제와 심화 예제의 공통 구조를 읽습니다.",
        "takeaway": "낯선 문제도 결국 익숙한 첫 줄에서 시작합니다.",
        "examCue": "새 문제를 보면 변하지 않는 첫 줄이 무엇인지 먼저 찾아보세요.",
        "practiceBridge": "난도가 올라가는 문제 묶음에서도 이 비교 방식이 그대로 필요합니다.",
        "autoAdvanceSeconds": 22,
        "objects": [
            {"id": f"{unit['id']}-compare-heading", "type": "heading", "x": 6, "y": 10, "w": 42, "content": "기본 예제 vs 심화 예제"},
            {
                "id": f"{unit['id']}-compare-core",
                "type": "callout",
                "x": 8,
                "y": 22,
                "w": 38,
                "content": core_problem["statement"],
                "delayMs": 160,
            },
            {
                "id": f"{unit['id']}-compare-hard",
                "type": "callout",
                "x": 50,
                "y": 22,
                "w": 38,
                "content": challenge_problem["statement"],
                "delayMs": 260,
            },
            {
                "id": f"{unit['id']}-compare-table",
                "type": "table",
                "x": 12,
                "y": 64,
                "w": 72,
                "h": 20,
                "table": {
                    "headers": ["비교 포인트", "기본 예제", "심화 예제"],
                    "rows": [
                        ["첫 줄", "기준 식을 바로 적는다", "기준 식은 같지만 조건을 더 묶는다"],
                        ["중간 전환", "대표 흐름을 그대로 사용", "중간 구조를 한 번 더 복원한다"],
                    ],
                },
                "delayMs": 360,
            },
        ],
    }


def _lecture_checkpoint_scene(unit: dict) -> dict:
    sample_problem = unit["problems"][0]
    challenge_problem = (_drill_problems_for_unit(unit) or unit["problems"])[-1]
    return {
        "id": f"scene-{unit['id']}-lecture-checkpoint",
        "title": "킬러 읽기 기준",
        "narration": (
            "강의가 길어질수록 오히려 고난도 문제를 읽는 순서는 짧아져야 합니다. "
            "대표 문제와 심화 문제를 동시에 떠올리면서, 어디부터 읽고 어디서 멈출지 기준을 잡아보겠습니다."
        ),
        "teachingGoal": "고난도 문제를 읽을 때 시선을 움직이는 순서를 고정합니다.",
        "takeaway": "어려운 문제도 결국 읽는 순서가 고정되면 덜 무너집니다.",
        "examCue": "막히면 조건, 전환, 끝줄 세 지점을 먼저 떠올려 보세요.",
        "practiceBridge": f"곧 이어지는 '{challenge_problem['title']}' 같은 문제에서도 이 순서를 그대로 씁니다.",
        "autoAdvanceSeconds": 18,
        "objects": [
            {
                "id": f"{unit['id']}-checkpoint-check",
                "type": "table",
                "x": 8,
                "y": 22,
                "w": 54,
                "h": 40,
                "table": {
                    "headers": ["읽는 순서", "대표 문제", "고난도 문제"],
                    "rows": [
                        ["첫 줄", sample_problem["title"], "같은 첫 줄을 더 오래 유지합니다"],
                        ["중간 전환", "문제 안에 보이는 판정", "숨은 연결식을 스스로 복원합니다"],
                        ["마지막 줄", "답 형식 확인", "버려지는 해와 형식을 동시에 점검합니다"],
                    ],
                },
            },
            {
                "id": f"{unit['id']}-checkpoint-table",
                "type": "callout",
                "x": 66,
                "y": 22,
                "w": 22,
                "content": "어려운 문제일수록 처음 10초에 읽는 순서를 고정해두면 훨씬 덜 흔들립니다.",
                "delayMs": 220,
            },
        ],
    }


def _applied_extension_scene(unit: dict) -> dict:
    challenge_problem = (_drill_problems_for_unit(unit) or unit["problems"])[-1]
    return {
        "id": f"scene-{unit['id']}-applied-extension",
        "title": "실전 연결",
        "narration": (
            "기초와 대표 예제를 지나면 실전에서는 더 긴 문장과 더 낯선 조건을 만나게 됩니다. "
            "마지막으로 실전형 문장 하나를 기준으로 응용 해석을 더 해보겠습니다."
        ),
        "teachingGoal": "응용 문제까지 이어지는 강의 흐름을 완성합니다.",
        "takeaway": "고난도 문제도 지금까지 본 개념과 판서 순서의 연장선입니다.",
        "examCue": "문장이 길어질수록 첫 줄과 마지막 줄을 더 의식해야 합니다.",
        "practiceBridge": "이 장면이 끝나면 바로 실전 문제 묶음에서 같은 흐름을 써보면 됩니다.",
        "autoAdvanceSeconds": 22,
        "objects": [
            {"id": f"{unit['id']}-applied-heading", "type": "heading", "x": 6, "y": 10, "w": 42, "content": "실전 연결"},
            {"id": f"{unit['id']}-applied-problem", "type": "callout", "x": 8, "y": 22, "w": 42, "content": challenge_problem["statement"], "delayMs": 140},
            {
                "id": f"{unit['id']}-applied-check",
                "type": "table",
                "x": 54,
                "y": 22,
                "w": 34,
                "h": 38,
                "table": {
                    "headers": ["실전에서 더 하는 일", "의미"],
                    "rows": [
                        ["조건을 두 번 읽고 묶기", "주어진 조건이 서로 어떻게 이어지는지 먼저 봅니다"],
                        ["중간 전환을 식으로 남기기", "머리로만 넘기지 않고 식으로 흔적을 남깁니다"],
                        ["마지막 검산 지점을 정하기", "끝줄에서 버려지는 해와 답 형식을 동시에 점검합니다"],
                    ],
                },
                "delayMs": 240,
            },
            {
                "id": f"{unit['id']}-applied-badge",
                "type": "badge",
                "x": 8,
                "y": 68,
                "w": 40,
                "content": _problem_difficulty_badge(challenge_problem),
                "delayMs": 360,
            },
        ],
    }


def _teacher_problem_clinic_scenes(unit: dict) -> list[dict]:
    scenes: list[dict] = []
    clinic_problems = (list(unit["problems"]) + _drill_problems_for_unit(unit)[:2])[:4]
    for index, problem in enumerate(clinic_problems, start=1):
        outline = _outline_preview(problem, 4)
        scenes.extend(
            [
                {
                    "id": f"scene-{unit['id']}-clinic-{index}-1",
                    "title": f"대표 문제 읽기 {index}",
                    "narration": (
                        "이 문제를 그냥 풀기 시작하지 말고, 조건과 질문이 어디서 갈리는지 먼저 짚어보겠습니다. "
                        "실제 수업에서 선생님이 판서 전에 문제를 같이 읽어주는 장면에 가깝게 구성했습니다."
                    ),
                    "teachingGoal": "대표 문제의 조건과 질문을 먼저 분리합니다.",
                    "takeaway": "문장을 나눠 읽으면 고난도 문제도 훨씬 덜 길게 느껴집니다.",
                    "examCue": "조건, 질문, 첫 줄을 따로 적는 습관을 들여보세요.",
                    "practiceBridge": "바로 다음 장면에서 이 문제의 실제 풀이 보드로 넘어갑니다.",
                    "autoAdvanceSeconds": 20,
                    "source": f"{PDF_SOURCE_PATH} p.{unit['pdfPages']}",
                    "objects": [
                        {"id": f"{unit['id']}-clinic-{index}-statement", "type": "callout", "x": 8, "y": 20, "w": 42, "content": problem["statement"]},
                        {
                            "id": f"{unit['id']}-clinic-{index}-read",
                            "type": "table",
                            "x": 52,
                            "y": 20,
                            "w": 36,
                            "h": 40,
                            "table": {
                                "headers": ["읽기 단계", "바로 적을 말"],
                                "rows": [
                                    ["조건", _problem_focus_checks(problem)[0]],
                                    ["질문", list(problem.get("expectedOutline", [])[:1])[0] if list(problem.get("expectedOutline", [])[:1]) else "무엇을 구하는지 한 줄 번역"],
                                    ["답 형식", problem.get("finalPrompt") or "최종 답 형식을 끝까지 본다"],
                                ],
                            },
                            "delayMs": 180,
                        },
                    ],
                },
                {
                    "id": f"scene-{unit['id']}-clinic-{index}-2",
                    "title": f"풀이 보드 {index}",
                    "narration": (
                        "이제 같은 문제를 실제 풀이 보드로 옮겨보겠습니다. "
                        "문제를 보는 순서가 풀이 줄 순서로 바로 이어져야 강의가 실제 점수로 연결됩니다."
                    ),
                    "teachingGoal": "대표 문제의 풀이 줄과 검산 지점을 확인합니다.",
                    "takeaway": "좋은 풀이 보드는 식을 많이 적는 게 아니라 줄의 순서가 흔들리지 않는 보드입니다.",
                    "examCue": "첫 줄, 중간 판정, 마지막 답 형식이 모두 보여야 합니다.",
                    "practiceBridge": "같은 단원 다른 문제도 같은 보드 구조로 들어가면 됩니다.",
                    "autoAdvanceSeconds": 20,
                    "source": f"{PDF_SOURCE_PATH} p.{unit['pdfPages']}",
                    "objects": [
                        {
                            "id": f"{unit['id']}-clinic-{index}-route",
                            "type": "table",
                            "x": 8,
                            "y": 20,
                            "w": 58,
                            "h": 40,
                            "table": {
                                "headers": ["풀이 줄", "써야 할 것", "놓치지 않을 것"],
                                "rows": _problem_step_rows(problem),
                            },
                        },
                        {
                            "id": f"{unit['id']}-clinic-{index}-coach",
                            "type": "callout",
                            "x": 70,
                            "y": 22,
                            "w": 18,
                            "content": problem["coachHint"],
                            "delayMs": 200,
                        },
                        {"id": f"{unit['id']}-clinic-{index}-type", "type": "badge", "x": 70, "y": 64, "w": 18, "content": _problem_difficulty_badge(problem), "delayMs": 280},
                    ],
                },
                {
                    "id": f"scene-{unit['id']}-clinic-{index}-3",
                    "title": f"고난도 확장 {index}",
                    "narration": (
                        "같은 대표 문제도 조건이 길어지면 어디가 달라지는지만 정확히 보면 됩니다. "
                        "이 장면에서는 대표 문제를 심화형으로 바꿨을 때 어떤 스킬이 추가되는지 같이 정리해보겠습니다."
                    ),
                    "teachingGoal": "대표 문제를 고난도 문제로 확장할 때 필요한 스킬을 읽습니다.",
                    "takeaway": "고난도 문제는 새로운 공식보다, 익숙한 줄을 더 오래 유지하는 문제입니다.",
                    "examCue": "대표 문제에서 이미 쓴 줄이 심화에서도 어디까지 유지되는지 먼저 보세요.",
                    "practiceBridge": "실전 문제 묶음에서도 지금 본 확장 포인트를 그대로 써볼 수 있습니다.",
                    "autoAdvanceSeconds": 20,
                    "source": f"{PDF_SOURCE_PATH} p.{unit['pdfPages']}",
                    "objects": [
                        {
                            "id": f"{unit['id']}-clinic-{index}-extend-table",
                            "type": "table",
                            "x": 8,
                            "y": 20,
                            "w": 58,
                            "h": 40,
                            "table": {
                                "headers": ["대표 문제에서 하던 일", "심화에서 더 해야 할 일", "끝까지 유지할 것"],
                                "rows": [
                                    [outline[0], "조건을 한 번 더 묶어 읽기", "첫 줄은 더 늦추지 않기"],
                                    [outline[1] if len(outline) > 1 else "중간 판정", "중간 구조 전환을 식으로 남기기", "판정 근거를 말로 설명할 수 있게 하기"],
                                    [outline[-1], "버려지는 해와 답 형식을 같이 보기", "끝줄을 가장 마지막이 아니라 계속 의식하기"],
                                ],
                            },
                            "delayMs": 180,
                        },
                        {
                            "id": f"{unit['id']}-clinic-{index}-extend-note",
                            "type": "callout",
                            "x": 70,
                            "y": 22,
                            "w": 18,
                            "content": problem["coachHint"],
                            "delayMs": 260,
                        },
                    ],
                },
            ]
        )
    return scenes


def _achievement_translation_scenes(unit: dict) -> list[dict]:
    scenes: list[dict] = []
    for index, code in enumerate(unit["achievementCodes"], start=1):
        scenes.append(
            {
                "id": f"scene-{unit['id']}-achievement-{index}",
                "title": f"성취기준 번역 {index}",
                "narration": (
                    "교육과정 문장을 학교 수업의 설명과 시험 문제의 언어로 다시 번역합니다. "
                    "이 장면은 왜 이 단원을 배우는지와 시험에서 어떻게 묻는지를 연결합니다."
                ),
                "teachingGoal": "성취기준을 시험장 언어로 번역합니다.",
                "takeaway": "교육과정 문장은 곧 문제 유형의 설계도입니다.",
                "examCue": "성취기준 번호보다, 그 기준이 실제로 어떤 질문으로 나오는지 떠올리세요.",
                "practiceBridge": "이후 문제 묶음은 모두 이 기준과 연결됩니다.",
                "autoAdvanceSeconds": 18,
                "source": f"{PDF_SOURCE_PATH} p.{unit['pdfPages']}",
                "objects": [
                    {"id": f"{unit['id']}-achievement-{index}-code", "type": "badge", "x": 8, "y": 18, "w": 24, "content": code},
                    {
                        "id": f"{unit['id']}-achievement-{index}-table",
                        "type": "table",
                        "x": 8,
                        "y": 30,
                        "w": 68,
                        "h": 34,
                        "table": {
                            "headers": ["교육과정", "수업 시간 설명", "시험장 해석"],
                            "rows": [[code, f"{unit['domainTitle']}의 핵심을 설명하고 적용하기", "문제를 보면 첫 줄을 바로 정할 수 있어야 함"]],
                        },
                    },
                ],
            }
        )
    return scenes


def _classroom_summary_scene(unit: dict) -> dict:
    return {
        "id": f"scene-{unit['id']}-classroom-summary",
        "title": "수업 마무리",
        "narration": (
            "학교 수업의 마지막처럼 오늘 배운 내용을 한 장에 정리합니다. "
            "학생은 이 장면만 다시 봐도 어떤 흐름으로 문제를 풀어야 하는지 떠올릴 수 있어야 합니다."
        ),
        "teachingGoal": "오늘 수업 전체를 한 장으로 압축합니다.",
        "takeaway": "좋은 강의는 결국 학생 머릿속에 남는 한 장의 정리입니다.",
        "examCue": "오늘 수업을 세 문장으로 다시 말할 수 있어야 합니다.",
        "practiceBridge": "이제 대표 문제와 실전 문제를 같은 순서로 풀면 됩니다.",
        "autoAdvanceSeconds": 20,
        "objects": [
            {"id": f"{unit['id']}-summary-title", "type": "heading", "x": 6, "y": 10, "w": 44, "content": f"{unit['domainTitle']} 수업 한 장 정리"},
            {
                "id": f"{unit['id']}-summary-check",
                "type": "table",
                "x": 8,
                "y": 24,
                "w": 56,
                "h": 40,
                "table": {
                    "headers": ["오늘 가져갈 한 줄", "실전에서 쓰는 방식"],
                    "rows": [
                        ["정의와 조건을 먼저 본다", "조건을 읽자마자 첫 줄의 재료를 고릅니다"],
                        ["기준 식을 먼저 적는다", "계산보다 먼저 풀이 출발점을 칠판에 남깁니다"],
                        ["마지막 한 줄 형식을 점검한다", "버려지는 해와 답 형식을 끝에서 같이 봅니다"],
                    ],
                },
            },
            {
                "id": f"{unit['id']}-summary-ask",
                "type": "callout",
                "x": 66,
                "y": 26,
                "w": 22,
                "content": "막히면 첫 줄과 끝줄부터 다시 볼까요?",
                "delayMs": 220,
            },
        ],
    }


def _lesson_pack(unit: dict) -> dict:
    unit_title = f"{unit['courseTitle']} - {unit['domainTitle']}"
    agenda = _lesson_agenda(unit)
    raw_scenes = [
        {
            "id": f"scene-{unit['id']}-1",
            "title": f"{unit['domainTitle']} 오프닝",
            "narration": (
                f"{unit['domainTitle']}은(는) {unit['coreIdea']} "
                "수능에서는 개념을 길게 암기하기보다, 어떤 식을 먼저 세우고 무엇을 확인할지 빠르게 잡는 감각이 더 중요합니다."
            ),
            "teachingGoal": "단원 전체를 어떤 순서로 보면 좋은지 바로 잡아볼까요?",
            "takeaway": "이 단원은 개념 자체보다 문제에 들어가는 순서가 점수와 더 직접 연결됩니다.",
            "examCue": "시험장에서 가장 먼저 떠올릴 문장을 한 줄로 정리해보면 좋아요.",
            "practiceBridge": "강의 마지막에는 바로 문제 묶음으로 넘어가 볼게요.",
            "autoAdvanceSeconds": 16,
            "objects": [
                {"id": f"{unit['id']}-h1", "type": "heading", "x": 6, "y": 10, "w": 48, "content": unit["domainTitle"]},
                {"id": f"{unit['id']}-note", "type": "callout", "x": 8, "y": 24, "w": 50, "content": unit["coreIdea"], "delayMs": 180},
                {"id": f"{unit['id']}-metric-1", "type": "metric", "x": 62, "y": 24, "w": 22, "content": f"핵심 요소 {len(unit['contentElements'])}개", "delayMs": 260},
                {"id": f"{unit['id']}-route", "type": "badge", "x": 8, "y": 62, "w": 46, "content": "개념 → 예제 → 킬러 → 실전", "delayMs": 420},
            ],
        },
        {
            "id": f"scene-{unit['id']}-2",
            "title": "오늘의 논지",
            "narration": (
                "이번 수업은 목차를 많이 보여주기보다, 이 단원에서 끝까지 붙잡아야 할 판단 기준을 먼저 정하고 시작하겠습니다."
            ),
            "teachingGoal": "오늘 수업에서 끝까지 유지할 기준 3가지를 먼저 잡습니다.",
            "takeaway": "좋은 강의는 많은 내용을 주는 것보다, 끝까지 흔들리지 않는 기준을 먼저 줍니다.",
            "examCue": "문제를 읽을 때도 지금 세운 기준 3개부터 먼저 떠올리면 됩니다.",
            "practiceBridge": "이 기준을 잡고 나면 개념 설명과 예제가 훨씬 빠르게 이어집니다.",
            "autoAdvanceSeconds": 18,
            "objects": [
                {
                    "id": f"{unit['id']}-agenda-table",
                    "type": "table",
                    "x": 8,
                    "y": 20,
                    "w": 56,
                    "h": 40,
                    "table": {
                        "headers": ["기준", "오늘 붙잡을 것", "왜 중요한가"],
                        "rows": [
                            ["1", f"{agenda[0]}의 첫 줄", "출발점이 잡혀야 긴 문제도 같은 기준으로 읽을 수 있습니다"],
                            ["2", f"{agenda[1]}의 판단 기준", "중간에 무엇을 보고 결론을 낼지 미리 정해둡니다"],
                            ["3", f"{agenda[2]}의 검산 기준", "끝줄 형식과 버려지는 해를 마지막까지 놓치지 않게 합니다"],
                        ],
                    },
                },
                {
                    "id": f"{unit['id']}-agenda-problem",
                    "type": "callout",
                    "x": 68,
                    "y": 24,
                    "w": 20,
                    "content": unit["problems"][0]["title"],
                    "delayMs": 220,
                },
                {"id": f"{unit['id']}-coach", "type": "badge", "x": 8, "y": 66, "w": 42, "content": "개념 → 예제 → 킬러 → 실전", "delayMs": 420},
            ],
        },
        _concept_network_scene(unit),
        *_school_teacher_element_scenes(unit),
        _worked_example_strategy_scene(unit),
        _worked_example_board_scene(unit),
        *_worked_example_long_scenes(unit),
        _pitfall_scene(unit),
        _multi_example_comparison_scene(unit),
        _lecture_checkpoint_scene(unit),
        _challenge_bridge_scene(unit),
        *_killer_example_long_scenes(unit),
        _applied_extension_scene(unit),
        _classroom_summary_scene(unit),
    ]
    return {
        "id": f"lesson-{unit['id']}",
        "title": unit["domainTitle"],
        "unitTitle": unit_title,
        "teacherName": "하늘 선생님",
        "conceptIds": [unit["id"]],
        "questionStarters": unit["questionStarters"],
        "curriculumMeta": {
            "courseId": unit["courseId"],
            "courseTitle": unit["courseTitle"],
        },
        "scenes": [_soften_scene(scene) for scene in raw_scenes],
    }


def _extended_core_problems(unit: dict) -> list[dict]:
    problems = deepcopy(unit["problems"])
    drill_problems = _drill_problems_for_unit(unit)
    selected_indexes = [0, 2, 5, 9, 13, 18, 23, 29]
    seen = {problem["id"] for problem in problems}
    for index in selected_indexes:
        if index >= len(drill_problems):
            continue
        candidate = deepcopy(drill_problems[index])
        if candidate["id"] in seen:
            continue
        problems.append(candidate)
        seen.add(candidate["id"])
    return problems


def _problem_set(unit: dict) -> dict:
    return {
        "id": f"set-{unit['id']}",
        "title": f"{unit['courseTitle']} · {unit['domainTitle']} 문제 묶음",
        "lessonPackId": f"lesson-{unit['id']}",
        "conceptIds": [unit["id"]],
        "problems": _extended_core_problems(unit),
    }


def _diagnostic_questions(units: list[dict]) -> list[dict]:
    distractor_pool = [
        item
        for unit in units
        for item in unit["contentElements"]
    ]
    questions: list[dict] = []
    for index, unit in enumerate(units, start=1):
        correct = unit["diagnostic"]["answer"]
        distractors = [item for item in distractor_pool if item != correct][:3]
        options = [correct, *distractors]
        questions.append(
            {
                "id": f"diag-curr-{index:02d}",
                "prompt": unit["diagnostic"]["prompt"],
                "options": options,
                "answer": 0,
                "concept": unit["id"],
            }
        )
    return questions


def build_curriculum_bundle() -> dict:
    concepts = [_unit_concept(unit, index) for index, unit in enumerate(UNIT_SPECS, start=1)]
    core_lesson_packs = [_lesson_pack(unit) for unit in UNIT_SPECS]
    core_problem_sets = [_problem_set(unit) for unit in UNIT_SPECS]
    drill_resources = [
        {
            "unitId": unit["id"],
            "lessonPack": _drill_lesson_pack(unit, drill_problems),
            "problemSet": _drill_problem_set(unit, drill_problems),
            "problemCount": len(drill_problems),
        }
        for unit in UNIT_SPECS
        for drill_problems in [_drill_problems_for_unit(unit)]
        if drill_problems
    ]
    killer_resources = [
        {
            "trackId": spec["trackId"],
            "title": spec["packTitle"],
            "lessonPack": _killer_track_lesson_pack(spec, killer_problems),
            "problemSet": _killer_track_problem_set(spec, killer_problems),
            "problemCount": len(killer_problems),
        }
        for spec in KILLER_TRACK_SPECS
        for killer_problems in [_killer_track_problems(spec)]
        if killer_problems
    ]
    lesson_packs = (
        core_lesson_packs
        + [item["lessonPack"] for item in drill_resources]
        + [item["lessonPack"] for item in killer_resources]
    )
    problem_sets = (
        core_problem_sets
        + [item["problemSet"] for item in drill_resources]
        + [item["problemSet"] for item in killer_resources]
    )
    course_summary: dict[str, dict] = {}
    for unit in UNIT_SPECS:
        course_summary.setdefault(
            unit["courseId"],
            {
                "courseId": unit["courseId"],
                "courseTitle": unit["courseTitle"],
                "domains": [],
            },
        )["domains"].append(
            {
                "unitId": unit["id"],
                "domainTitle": unit["domainTitle"],
                "contentElements": unit["contentElements"],
                "drillLessonPackId": f"lesson-{unit['id']}-drill",
                "drillProblemSetId": f"set-{unit['id']}-drill",
                "drillProblemCount": next(
                    (
                        item["problemCount"]
                        for item in drill_resources
                        if item["unitId"] == unit["id"]
                    ),
                    0,
                ),
            }
        )
    return {
        "bundleId": "suneung-math-curriculum-v1",
        "title": "오리지널 수능 수학 커리큘럼",
        "version": "2026.04.p0-deeper",
        "domain": "suneung-math",
        "source": {
            "path": PDF_SOURCE_PATH,
            "kind": "curriculum-reference",
        },
        "curriculum": {
            "courses": list(course_summary.values()),
            "drillLibraries": [
                {
                    "unitId": item["unitId"],
                    "lessonPackId": item["lessonPack"]["id"],
                    "problemSetId": item["problemSet"]["id"],
                    "problemCount": item["problemCount"],
                }
                for item in drill_resources
            ],
            "killerTracks": [
                {
                    "trackId": item["trackId"],
                    "title": item["title"],
                    "lessonPackId": item["lessonPack"]["id"],
                    "problemSetId": item["problemSet"]["id"],
                    "problemCount": item["problemCount"],
                }
                for item in killer_resources
            ],
        },
        "concepts": concepts,
        "diagnosticQuestions": _diagnostic_questions(UNIT_SPECS),
        "microScenes": {
            "slope": {
                "id": "curriculum-micro-standard",
                "title": "질문 답변",
                "narration": "지금 질문은 해당 단원의 핵심 식, 판정 기준, 최종 정리 순서로 다시 묶어서 설명하겠습니다.",
                "resumeLabel": "이어서 같이 볼게요",
                "objects": [
                    {"id": "curriculum-micro-1", "type": "callout", "x": 8, "y": 18, "w": 42, "content": "핵심 식 → 판정 기준 → 최종 정리"},
                ],
            },
            "point": {
                "id": "curriculum-micro-source",
                "title": "질문 답변: 장면 재설명",
                "narration": "지금 장면에서 놓친 조건과 기준 식을 다시 잡고, 바로 이어서 풀 수 있게 짧게 정리하겠습니다.",
                "resumeLabel": "이어서 같이 볼게요",
                "objects": [
                    {"id": "curriculum-micro-2", "type": "callout", "x": 8, "y": 18, "w": 42, "content": "조건 확인 → 기준 식 → 마지막 정리"},
                ],
            },
            "recap": {
                "id": "curriculum-micro-recap",
                "title": "질문 답변: 커리큘럼 복습",
                "narration": "이 단원은 개념, 대표 예제, 함정, 실전 문제로 복습됩니다.",
                "resumeLabel": "이어서 같이 볼게요",
                "objects": [
                    {"id": "curriculum-micro-3", "type": "bullet", "x": 8, "y": 20, "w": 42, "content": "핵심 개념 복기"},
                    {"id": "curriculum-micro-4", "type": "bullet", "x": 8, "y": 34, "w": 42, "content": "대표 예제 구조 확인"},
                    {"id": "curriculum-micro-5", "type": "bullet", "x": 8, "y": 48, "w": 42, "content": "실전 문제 재도전"},
                ],
            },
        },
        "lessonPacks": lesson_packs,
        "problemSets": problem_sets,
    }
