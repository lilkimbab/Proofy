from __future__ import annotations

import random
from copy import deepcopy


DIFFICULTY_WEIGHTS = {
    "medium": 1.2,
    "hard": 1.5,
    "advanced": 1.8,
    "killer": 2.05,
}

TRACK_LABELS = ["공통수학", "대수", "미적분", "확률과 통계", "기하"]


LEGACY_FIXED_DIAGNOSTIC = [
    {
        "id": "diag-onboard-01",
        "concept": "common1-polynomial",
        "unitTitle": "공통수학1 · 다항식",
        "difficulty": "medium",
        "prompt": "다항식 P(x)=x^3-3x+5를 x-2로 나눌 때의 나머지는?",
        "options": ["3", "5", "7", "9"],
        "answer": 2,
    },
    {
        "id": "diag-onboard-02",
        "concept": "common1-equation",
        "unitTitle": "공통수학1 · 방정식과 부등식",
        "difficulty": "hard",
        "prompt": "부등식 x^2-5x+6<0 의 해는?",
        "options": ["x<2 또는 x>3", "2<x<3", "x<2 또는 2<x<3", "x>3"],
        "answer": 1,
    },
    {
        "id": "diag-onboard-03",
        "concept": "common1-counting",
        "unitTitle": "공통수학1 · 경우의 수",
        "difficulty": "hard",
        "prompt": "1, 2, 3, 4, 5 중 서로 다른 세 수를 골라 만들 수 있는 세 자리 자연수의 개수는?",
        "options": ["30", "48", "60", "90"],
        "answer": 2,
    },
    {
        "id": "diag-onboard-04",
        "concept": "common2-coordinate",
        "unitTitle": "공통수학2 · 도형의 방정식",
        "difficulty": "hard",
        "prompt": "점 (2,-1)을 지나고 기울기가 3인 직선의 방정식은?",
        "options": ["y=3x-7", "y=3x+5", "y=-3x+5", "y=3x-5"],
        "answer": 0,
    },
    {
        "id": "diag-onboard-05",
        "concept": "common2-function",
        "unitTitle": "공통수학2 · 함수와 그래프",
        "difficulty": "hard",
        "prompt": "f(x)=2x-1, g(x)=x^2 일 때 (g∘f)(2)의 값은?",
        "options": ["7", "8", "9", "16"],
        "answer": 2,
    },
    {
        "id": "diag-onboard-06",
        "concept": "algebra-exp-log",
        "unitTitle": "대수 · 지수함수와 로그함수",
        "difficulty": "hard",
        "prompt": "log2(x-1)=3 을 만족하는 x의 값은?",
        "options": ["7", "8", "9", "10"],
        "answer": 2,
    },
    {
        "id": "diag-onboard-07",
        "concept": "algebra-trig",
        "unitTitle": "대수 · 삼각함수",
        "difficulty": "advanced",
        "prompt": "0<theta<pi/2 에서 sin(theta)=3/5 일 때 cos(theta)+tan(theta)의 값은?",
        "options": ["29/12", "7/3", "13/4", "17/5"],
        "answer": 0,
    },
    {
        "id": "diag-onboard-08",
        "concept": "algebra-sequence",
        "unitTitle": "대수 · 수열",
        "difficulty": "hard",
        "prompt": "등차수열의 첫째항이 4, 공차가 3일 때 제8항은?",
        "options": ["22", "25", "28", "31"],
        "answer": 1,
    },
    {
        "id": "diag-onboard-09",
        "concept": "calc1-limit",
        "unitTitle": "미적분I · 함수의 극한과 연속",
        "difficulty": "advanced",
        "prompt": "lim(x->2) (x^2-4)/(x-2) 의 값은?",
        "options": ["2", "3", "4", "5"],
        "answer": 2,
    },
    {
        "id": "diag-onboard-10",
        "concept": "calc1-diff",
        "unitTitle": "미적분I · 미분",
        "difficulty": "advanced",
        "prompt": "f(x)=x^3-3x^2+2 에 대하여 x=1 에서의 접선의 기울기는?",
        "options": ["-3", "-1", "0", "3"],
        "answer": 0,
    },
    {
        "id": "diag-onboard-11",
        "concept": "probstat-probability",
        "unitTitle": "확률과 통계 · 확률",
        "difficulty": "hard",
        "prompt": "공 3개가 든 주머니에서 2개를 동시에 꺼낼 때 특정 한 공이 포함될 확률은?",
        "options": ["1/3", "1/2", "2/3", "3/4"],
        "answer": 2,
    },
    {
        "id": "diag-onboard-12",
        "concept": "geometry-conic",
        "unitTitle": "기하 · 이차곡선",
        "difficulty": "advanced",
        "prompt": "타원 x^2/25 + y^2/9 = 1 의 초점 사이 거리는?",
        "options": ["4", "6", "8", "10"],
        "answer": 2,
    },
]


QUESTION_BANK = [
    {
        "id": "diag-bank-001",
        "concept": "common1-polynomial",
        "unitTitle": "공통수학1 · 다항식",
        "difficulty": "hard",
        "prompt": "다항식 P(x)를 x-1로 나누면 나머지가 2, x+2로 나누면 나머지가 -1이다. P(x)를 (x-1)(x+2)로 나눈 나머지가 ax+b일 때 a+b의 값은?",
        "options": ["0", "1", "2", "3"],
        "answer": 2,
    },
    {
        "id": "diag-bank-002",
        "concept": "common1-polynomial",
        "unitTitle": "공통수학1 · 다항식",
        "difficulty": "advanced",
        "prompt": "x^3-3x^2+ax+4가 x-2를 인수로 가질 때 a의 값은?",
        "options": ["0", "1", "2", "3"],
        "answer": 2,
    },
    {
        "id": "diag-bank-003",
        "concept": "common1-equation",
        "unitTitle": "공통수학1 · 방정식과 부등식",
        "difficulty": "hard",
        "prompt": "이차부등식 x^2-6x+k<0의 해가 정확히 1<x<5가 되도록 하는 k의 값은?",
        "options": ["4", "5", "6", "7"],
        "answer": 1,
    },
    {
        "id": "diag-bank-004",
        "concept": "common1-equation",
        "unitTitle": "공통수학1 · 방정식과 부등식",
        "difficulty": "advanced",
        "prompt": "두 근이 모두 양수인 이차방정식 x^2-(m+2)x+m=0을 만족시키는 정수 m의 개수는?",
        "options": ["1", "2", "3", "4"],
        "answer": 2,
    },
    {
        "id": "diag-bank-005",
        "concept": "common1-counting",
        "unitTitle": "공통수학1 · 경우의 수",
        "difficulty": "hard",
        "prompt": "숫자 1, 2, 3, 4, 5를 한 번씩만 써서 만든 다섯 자리 자연수 중 3의 배수의 개수는?",
        "options": ["24", "48", "72", "120"],
        "answer": 3,
    },
    {
        "id": "diag-bank-006",
        "concept": "common2-coordinate",
        "unitTitle": "공통수학2 · 도형의 방정식",
        "difficulty": "hard",
        "prompt": "원 x^2+y^2-4x+6y-12=0의 중심에서 직선 x-2y+5=0까지의 거리는?",
        "options": ["1", "sqrt(5)", "2sqrt(5)", "3"],
        "answer": 1,
    },
    {
        "id": "diag-bank-007",
        "concept": "common2-function",
        "unitTitle": "공통수학2 · 함수와 그래프",
        "difficulty": "advanced",
        "prompt": "함수 f(x)=2x+1, g(x)=x^2-4x일 때 g(f(x))의 최솟값은?",
        "options": ["-9", "-8", "-7", "-6"],
        "answer": 2,
    },
    {
        "id": "diag-bank-008",
        "concept": "common2-logic",
        "unitTitle": "공통수학2 · 논리",
        "difficulty": "hard",
        "prompt": "명제 p: 'x>3', q: 'x^2>9'에 대하여 p→q의 역이 거짓이 되도록 하는 x의 예로 알맞은 것은?",
        "options": ["-4", "-3", "0", "4"],
        "answer": 0,
    },
    {
        "id": "diag-bank-009",
        "concept": "algebra-function",
        "unitTitle": "대수 · 함수",
        "difficulty": "advanced",
        "prompt": "f(x)=x+1/x (x>0)의 최솟값은?",
        "options": ["1", "2", "sqrt(2)", "2sqrt(2)"],
        "answer": 1,
    },
    {
        "id": "diag-bank-010",
        "concept": "algebra-exp-log",
        "unitTitle": "대수 · 지수함수와 로그함수",
        "difficulty": "hard",
        "prompt": "log_2(x-1)+log_2(x-3)=3을 만족하는 x의 값은?",
        "options": ["4", "5", "1+sqrt(17)", "2+sqrt(11)"],
        "answer": 2,
    },
    {
        "id": "diag-bank-011",
        "concept": "algebra-exp-log",
        "unitTitle": "대수 · 지수함수와 로그함수",
        "difficulty": "advanced",
        "prompt": "2^(x+1)=8^x / 4 를 만족하는 x의 값은?",
        "options": ["-2", "-1", "1", "2"],
        "answer": 1,
    },
    {
        "id": "diag-bank-012",
        "concept": "algebra-trig",
        "unitTitle": "대수 · 삼각함수",
        "difficulty": "hard",
        "prompt": "0<theta<pi 에서 sin(theta)=3/5, cos(theta)<0 일 때 tan(theta)의 값은?",
        "options": ["-3/4", "3/4", "-4/3", "4/3"],
        "answer": 2,
    },
    {
        "id": "diag-bank-013",
        "concept": "algebra-sequence",
        "unitTitle": "대수 · 수열",
        "difficulty": "advanced",
        "prompt": "등차수열 {a_n}의 합 S_n에 대하여 S_4=20, S_8=72일 때 a_1의 값은?",
        "options": ["1", "2", "3", "4"],
        "answer": 1,
    },
    {
        "id": "diag-bank-014",
        "concept": "calc1-limit",
        "unitTitle": "미적분I · 함수의 극한과 연속",
        "difficulty": "hard",
        "prompt": "lim(x→1) (x^3-1)/(x-1)의 값은?",
        "options": ["1", "2", "3", "4"],
        "answer": 2,
    },
    {
        "id": "diag-bank-015",
        "concept": "calc1-limit",
        "unitTitle": "미적분I · 함수의 극한과 연속",
        "difficulty": "advanced",
        "prompt": "함수 f(x)=((x^2-4)/(x-2)) (x≠2), a (x=2)가 x=2에서 연속이 되도록 하는 a의 값은?",
        "options": ["2", "3", "4", "5"],
        "answer": 2,
    },
    {
        "id": "diag-bank-016",
        "concept": "calc1-diff",
        "unitTitle": "미적분I · 미분",
        "difficulty": "hard",
        "prompt": "f(x)=x^3-6x^2+9x+1에 대하여 f'(x)=0이 되는 모든 x의 합은?",
        "options": ["2", "3", "4", "5"],
        "answer": 2,
    },
    {
        "id": "diag-bank-017",
        "concept": "calc1-diff",
        "unitTitle": "미적분I · 미분",
        "difficulty": "advanced",
        "prompt": "곡선 y=x^2-4x+1 위의 점 (3, -2)에서의 접선의 방정식은?",
        "options": ["y=2x-8", "y=2x-6", "y=-2x+4", "y=4x-14"],
        "answer": 0,
    },
    {
        "id": "diag-bank-018",
        "concept": "calc1-integral",
        "unitTitle": "미적분I · 적분",
        "difficulty": "hard",
        "prompt": "∫(1부터 3까지) (2x-1) dx의 값은?",
        "options": ["4", "5", "6", "7"],
        "answer": 2,
    },
    {
        "id": "diag-bank-019",
        "concept": "probstat-counting",
        "unitTitle": "확률과 통계 · 경우의 수",
        "difficulty": "hard",
        "prompt": "남학생 3명, 여학생 2명을 한 줄로 세울 때 여학생 2명이 이웃하도록 하는 경우의 수는?",
        "options": ["12", "24", "36", "48"],
        "answer": 3,
    },
    {
        "id": "diag-bank-020",
        "concept": "probstat-probability",
        "unitTitle": "확률과 통계 · 확률",
        "difficulty": "advanced",
        "prompt": "흰 공 2개, 검은 공 3개가 들어 있는 상자에서 동시에 2개를 꺼낼 때 서로 다른 색일 확률은?",
        "options": ["2/5", "3/5", "4/5", "1/2"],
        "answer": 1,
    },
    {
        "id": "diag-bank-021",
        "concept": "probstat-distribution",
        "unitTitle": "확률과 통계 · 통계",
        "difficulty": "advanced",
        "prompt": "확률변수 X가 0, 1, 2를 각각 확률 1/4, 1/2, 1/4로 가질 때 E(X)의 값은?",
        "options": ["1/2", "1", "3/2", "2"],
        "answer": 1,
    },
    {
        "id": "diag-bank-022",
        "concept": "calc2-seq-limit",
        "unitTitle": "미적분II · 수열의 극한",
        "difficulty": "advanced",
        "prompt": "수열 a_n=(2n+1)/(n+3)에 대하여 lim(n→∞) a_n의 값은?",
        "options": ["0", "1", "2", "3"],
        "answer": 2,
    },
    {
        "id": "diag-bank-023",
        "concept": "calc2-diff",
        "unitTitle": "미적분II · 미분법",
        "difficulty": "advanced",
        "prompt": "f(x)=x^2e^x일 때 f'(0)의 값은?",
        "options": ["0", "1", "2", "e"],
        "answer": 0,
    },
    {
        "id": "diag-bank-024",
        "concept": "calc2-integral",
        "unitTitle": "미적분II · 적분법",
        "difficulty": "advanced",
        "prompt": "∫(0부터 1까지) (3x^2+2x) dx의 값은?",
        "options": ["1", "2", "3", "4"],
        "answer": 1,
    },
    {
        "id": "diag-bank-025",
        "concept": "geometry-conic",
        "unitTitle": "기하 · 이차곡선",
        "difficulty": "hard",
        "prompt": "타원 x^2/16 + y^2/7 = 1의 장축의 길이는?",
        "options": ["4", "7", "8", "16"],
        "answer": 2,
    },
    {
        "id": "diag-bank-026",
        "concept": "geometry-space",
        "unitTitle": "기하 · 공간도형과 공간좌표",
        "difficulty": "advanced",
        "prompt": "두 점 A(1,2,3), B(4,6,3) 사이의 거리는?",
        "options": ["4", "5", "sqrt(17)", "6"],
        "answer": 1,
    },
    {
        "id": "diag-bank-027",
        "concept": "geometry-vector",
        "unitTitle": "기하 · 벡터",
        "difficulty": "advanced",
        "prompt": "벡터 a=(1,2), b=(3,-1)에 대하여 a·b의 값은?",
        "options": ["1", "2", "3", "4"],
        "answer": 0,
    },
    {
        "id": "diag-bank-028",
        "concept": "geometry-vector",
        "unitTitle": "기하 · 벡터",
        "difficulty": "hard",
        "prompt": "벡터 a=(2,1), b=(1,-2)에 대하여 |a+b|^2의 값은?",
        "options": ["2", "4", "8", "10"],
        "answer": 0,
    },
    {
        "id": "diag-bank-029",
        "concept": "algebra-sequence",
        "unitTitle": "대수 · 수열",
        "difficulty": "killer",
        "prompt": "모든 항이 양수인 등비수열 {a_n}에 대하여 a_2+a_4=20, a_3+a_5=40이다. a_1+a_6의 값은?",
        "options": ["34", "48", "66", "72"],
        "answer": 2,
    },
    {
        "id": "diag-bank-030",
        "concept": "calc1-diff",
        "unitTitle": "미적분I · 미분",
        "difficulty": "killer",
        "prompt": "삼차함수 f(x)가 x=1에서 극솟값 -2, x=3에서 극댓값 2를 가질 때, f(5)의 값은?",
        "options": ["-26", "-18", "-10", "6"],
        "answer": 1,
    },
    {
        "id": "diag-bank-031",
        "concept": "probstat-random",
        "unitTitle": "확률과 통계 · 확률분포",
        "difficulty": "killer",
        "prompt": "주사위 세 개를 동시에 던져 나온 눈의 최댓값을 M, 최솟값을 m이라 하자. M-m=4일 확률은?",
        "options": ["1/6", "2/9", "1/4", "5/18"],
        "answer": 1,
    },
    {
        "id": "diag-bank-032",
        "concept": "geometry-conic",
        "unitTitle": "기하 · 이차곡선",
        "difficulty": "killer",
        "prompt": "타원 x^2/a^2 + y^2/b^2 = 1 (a>b>0)의 한 초점이 (2,0)이고 점 (2,3)이 타원 위에 있을 때, b^2의 값은?",
        "options": ["8", "10", "12", "14"],
        "answer": 2,
    },
]


def _track_for_concept(concept: str) -> str:
    if concept.startswith(("common1", "common2")):
        return "공통수학"
    if concept.startswith("algebra"):
        return "대수"
    if concept.startswith(("calc1", "calc2")):
        return "미적분"
    if concept.startswith("probstat"):
        return "확률과 통계"
    if concept.startswith("geometry"):
        return "기하"
    return "수학"


def _normalized_terms(prioritized_terms: list[str] | None) -> list[str]:
    if not prioritized_terms:
        return []
    normalized: list[str] = []
    for term in prioritized_terms:
        clean = str(term or "").strip().lower().replace(" ", "")
        if clean and clean not in normalized:
            normalized.append(clean)
    return normalized


def build_onboarding_diagnostic_bank() -> list[dict]:
    return deepcopy(QUESTION_BANK)


def _shuffle_question(question: dict, rng: random.Random) -> dict:
    shuffled = {
        key: value
        for key, value in question.items()
        if not key.startswith("_")
    }
    options = list(shuffled["options"])
    indexed = list(enumerate(options))
    rng.shuffle(indexed)
    shuffled["options"] = [option for _, option in indexed]
    shuffled["answer"] = next(
        new_index for new_index, (old_index, _) in enumerate(indexed) if old_index == question["answer"]
    )
    return shuffled


def _pick_from_top(candidates: list[dict], rng: random.Random, width: int = 3) -> dict | None:
    if not candidates:
        return None
    window = candidates[: min(len(candidates), width)]
    return rng.choice(window)


def _weighted_pick(candidates: list[dict], rng: random.Random) -> dict | None:
    if not candidates:
        return None
    total = sum(max(0.2, float(item.get("_weight", 1.0))) for item in candidates)
    threshold = rng.random() * total
    upto = 0.0
    for item in candidates:
        upto += max(0.2, float(item.get("_weight", 1.0)))
        if upto >= threshold:
            return item
    return candidates[-1]


def build_onboarding_diagnostic(
    *,
    size: int = 12,
    seed: str | int | None = None,
    prioritized_terms: list[str] | None = None,
) -> list[dict]:
    if seed is None and not prioritized_terms:
        return deepcopy(LEGACY_FIXED_DIAGNOSTIC)

    bank = build_onboarding_diagnostic_bank()
    rng = random.Random(str(seed or "onboarding-diagnostic"))
    terms = _normalized_terms(prioritized_terms)

    for question in bank:
        haystack = (
            f"{question['concept']} {question['unitTitle']} {question['prompt']}".lower().replace(" ", "")
        )
        priority = 0.0
        if question["difficulty"] == "killer":
            priority += 2.4
        elif question["difficulty"] == "advanced":
            priority += 1.8
        elif question["difficulty"] == "hard":
            priority += 1.2
        for term in terms:
            if term and term in haystack:
                priority += 2.7
        question["_priority"] = priority + rng.random() * 0.35
        question["_track"] = _track_for_concept(str(question["concept"]))
        question["_weight"] = (
            DIFFICULTY_WEIGHTS.get(question["difficulty"], 1.0)
            + priority
            + rng.random() * 0.8
        )

    selected: list[dict] = []
    selected_ids: set[str] = set()

    def choose(candidate: dict) -> None:
        if candidate["id"] in selected_ids:
            return
        selected.append(_shuffle_question(candidate, rng))
        selected_ids.add(str(candidate["id"]))

    required_killers = min(3, len([item for item in bank if item["difficulty"] == "killer"]), max(2, size // 4))
    killer_pool = [item for item in bank if item["difficulty"] == "killer"]
    for _ in range(required_killers):
        candidate = _weighted_pick([item for item in killer_pool if item["id"] not in selected_ids], rng)
        if candidate:
            choose(candidate)

    while len(selected) < size:
        remaining = [item for item in bank if item["id"] not in selected_ids]
        candidate = _weighted_pick(remaining, rng)
        if not candidate:
            break
        choose(candidate)

    rng.shuffle(selected)
    return selected[:size]
