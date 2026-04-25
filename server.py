from __future__ import annotations

import json
import mimetypes
import re
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import date, timedelta
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parent
STATIC_DIR = ROOT / "static"
TODAY = date(2026, 4, 10)


def json_bytes(payload: dict) -> bytes:
    return json.dumps(payload, ensure_ascii=False).encode("utf-8")


def normalize_text(value: str) -> str:
    collapsed = re.sub(r"\s+", "", value or "")
    return (
        collapsed.lower()
        .replace("−", "-")
        .replace("—", "-")
        .replace("×", "*")
        .replace("²", "^2")
        .replace("³", "^3")
    )


def score_to_label(score: int) -> str:
    if score >= 85:
        return "안정권"
    if score >= 70:
        return "상승권"
    if score >= 55:
        return "교정 필요"
    return "기초 재정비"


def scene_graph(curves: list[dict], marks: list[dict] | None = None) -> dict:
    return {
        "type": "graph",
        "x": 58,
        "y": 18,
        "w": 36,
        "h": 58,
        "graph": {
            "xMin": -1,
            "xMax": 4,
            "yMin": -4,
            "yMax": 6,
            "curves": curves,
            "marks": marks or [],
        },
    }


def quadratic_points() -> list[list[float]]:
    points = []
    for index in range(-10, 41):
        x_value = index / 10
        y_value = (x_value * x_value) - (4 * x_value) + 3
        points.append([x_value, y_value])
    return points


def tangent_points() -> list[list[float]]:
    return [[-1, 4], [4, -6]]


def build_lesson_scenes() -> list[dict]:
    return [
        {
            "id": "scene-intro",
            "title": "접선 문제는 결국 두 조각입니다",
            "narration": "오늘은 접선의 방정식을 3단계로 끝냅니다. 기울기 하나, 점 하나, 그리고 점기울기식으로 연결하면 됩니다.",
            "objects": [
                {
                    "id": "title",
                    "type": "heading",
                    "x": 6,
                    "y": 8,
                    "w": 44,
                    "content": "접선의 방정식 = 기울기 + 한 점",
                },
                {
                    "id": "formula-main",
                    "type": "equation",
                    "x": 8,
                    "y": 24,
                    "w": 40,
                    "content": "y - y₁ = m(x - x₁)",
                    "delayMs": 400,
                },
                {
                    "id": "badge",
                    "type": "badge",
                    "x": 8,
                    "y": 38,
                    "content": "오늘의 핵심: m = f'(a)",
                    "delayMs": 900,
                },
                {
                    "id": "note",
                    "type": "note",
                    "x": 8,
                    "y": 52,
                    "w": 40,
                    "content": "접점의 x좌표가 주어지면 도함수값과 함수값만 구하면 끝납니다.",
                    "delayMs": 1300,
                },
                scene_graph(
                    [
                        {"color": "#f7e6a7", "points": quadratic_points()},
                        {"color": "#f3a43b", "points": tangent_points()},
                    ],
                    [{"x": 1, "y": 0, "label": "(1, 0)"}],
                ),
            ],
        },
        {
            "id": "scene-derivative",
            "title": "먼저 함수와 도함수를 분리해서 봅니다",
            "narration": "문제에서 주어진 함수는 x제곱에서 4x를 빼고 3을 더한 꼴입니다. 접선의 기울기를 얻기 위해 도함수를 먼저 계산합니다.",
            "objects": [
                {
                    "id": "function",
                    "type": "equation",
                    "x": 8,
                    "y": 12,
                    "w": 42,
                    "content": "f(x) = x² - 4x + 3",
                },
                {
                    "id": "step-arrow",
                    "type": "arrow",
                    "x": 20,
                    "y": 28,
                    "w": 12,
                    "h": 8,
                    "delayMs": 500,
                },
                {
                    "id": "derivative",
                    "type": "equation",
                    "x": 8,
                    "y": 40,
                    "w": 42,
                    "content": "f'(x) = 2x - 4",
                    "delayMs": 900,
                },
                {
                    "id": "highlight",
                    "type": "callout",
                    "x": 8,
                    "y": 56,
                    "w": 42,
                    "content": "이 문제에서 가장 흔한 실수는 -4를 +4로 바꾸는 부호 실수입니다.",
                    "delayMs": 1300,
                },
            ],
        },
        {
            "id": "scene-slope",
            "title": "접점 x=1을 넣으면 기울기가 나옵니다",
            "narration": "접점의 x좌표가 1이면 그 지점의 접선 기울기는 f'(1)입니다. 도함수에 1을 넣으면 기울기 -2를 바로 얻습니다.",
            "objects": [
                {
                    "id": "substitute",
                    "type": "equation",
                    "x": 8,
                    "y": 14,
                    "w": 42,
                    "content": "f'(1) = 2(1) - 4",
                },
                {
                    "id": "slope",
                    "type": "equation",
                    "x": 8,
                    "y": 30,
                    "w": 42,
                    "content": "m = f'(1) = -2",
                    "delayMs": 500,
                },
                {
                    "id": "sticky",
                    "type": "note",
                    "x": 8,
                    "y": 46,
                    "w": 42,
                    "content": "접선의 기울기와 도함수값을 연결하지 못하면 다음 단계로 못 갑니다.",
                    "delayMs": 950,
                },
                {
                    "id": "tag",
                    "type": "badge",
                    "x": 8,
                    "y": 62,
                    "content": "기울기 확보 완료",
                    "delayMs": 1400,
                },
            ],
        },
        {
            "id": "scene-point",
            "title": "이제 같은 x값을 원함수에 넣어 접점을 구합니다",
            "narration": "기울기만으로는 직선이 정해지지 않습니다. 같은 x=1을 원함수에 넣어 접점의 좌표를 찾습니다.",
            "objects": [
                {
                    "id": "point-value",
                    "type": "equation",
                    "x": 8,
                    "y": 14,
                    "w": 42,
                    "content": "f(1) = 1 - 4 + 3 = 0",
                },
                {
                    "id": "point-pair",
                    "type": "equation",
                    "x": 8,
                    "y": 30,
                    "w": 42,
                    "content": "접점 = (1, 0)",
                    "delayMs": 550,
                },
                {
                    "id": "point-callout",
                    "type": "callout",
                    "x": 8,
                    "y": 48,
                    "w": 42,
                    "content": "접선 문제에서 x좌표는 도함수와 원함수 둘 다에 다시 들어갑니다.",
                    "delayMs": 1000,
                },
                scene_graph(
                    [
                        {"color": "#f7e6a7", "points": quadratic_points()},
                        {"color": "#f3a43b", "points": tangent_points()},
                    ],
                    [{"x": 1, "y": 0, "label": "접점 (1, 0)"}],
                ),
            ],
        },
        {
            "id": "scene-finish",
            "title": "기울기와 점을 점기울기식에 꽂으면 끝납니다",
            "narration": "이제 기울기 -2와 점 (1, 0)을 점기울기식에 대입합니다. 마지막으로 정리만 하면 접선의 방정식을 얻을 수 있습니다.",
            "objects": [
                {
                    "id": "plug-in",
                    "type": "equation",
                    "x": 8,
                    "y": 16,
                    "w": 42,
                    "content": "y - 0 = -2(x - 1)",
                },
                {
                    "id": "answer",
                    "type": "equation",
                    "x": 8,
                    "y": 34,
                    "w": 42,
                    "content": "y = -2x + 2",
                    "delayMs": 500,
                },
                {
                    "id": "finish-note",
                    "type": "note",
                    "x": 8,
                    "y": 52,
                    "w": 42,
                    "content": "문제를 풀 때는 도함수 → 접점 → 직선식 순서를 습관처럼 고정하세요.",
                    "delayMs": 1050,
                },
                {
                    "id": "ready-practice",
                    "type": "badge",
                    "x": 8,
                    "y": 66,
                    "content": "이제 같은 구조 문제로 바로 넘어갑니다",
                    "delayMs": 1450,
                },
            ],
        },
    ]


def build_question_scene(kind: str) -> dict:
    if kind == "slope":
        return {
            "id": "micro-slope",
            "title": "질문 답변: 왜 접선 기울기가 도함수값인가?",
            "narration": "도함수는 특정 점에서 함수가 얼마나 가파르게 변하는지를 나타냅니다. 그 점에서의 순간 변화율이 바로 접선의 기울기입니다.",
            "objects": [
                {
                    "id": "micro-title",
                    "type": "heading",
                    "x": 6,
                    "y": 10,
                    "w": 44,
                    "content": "순간 변화율 = 접선의 기울기",
                },
                {
                    "id": "micro-limit",
                    "type": "equation",
                    "x": 8,
                    "y": 28,
                    "w": 42,
                    "content": "f'(a) = lim h→0 [f(a+h) - f(a)] / h",
                    "delayMs": 450,
                },
                {
                    "id": "micro-note",
                    "type": "callout",
                    "x": 8,
                    "y": 48,
                    "w": 42,
                    "content": "두 점을 잇는 할선의 기울기를 극한으로 보내면 접선의 기울기가 됩니다.",
                    "delayMs": 950,
                },
                scene_graph(
                    [
                        {"color": "#f7e6a7", "points": quadratic_points()},
                        {"color": "#f3a43b", "points": tangent_points()},
                    ],
                    [{"x": 1, "y": 0, "label": "a = 1"}],
                ),
            ],
            "resumeLabel": "원래 강의로 돌아가기",
        }

    if kind == "point":
        return {
            "id": "micro-point",
            "title": "질문 답변: 왜 원함수에도 x=1을 넣나요?",
            "narration": "직선 하나를 정하려면 기울기와 한 점이 필요합니다. 도함수는 기울기만 주기 때문에, 원함수에 같은 x값을 넣어 실제 접점을 찾아야 합니다.",
            "objects": [
                {
                    "id": "need-two",
                    "type": "heading",
                    "x": 6,
                    "y": 10,
                    "w": 44,
                    "content": "직선을 정하려면 점 하나가 더 필요합니다",
                },
                {
                    "id": "compare",
                    "type": "equation",
                    "x": 8,
                    "y": 30,
                    "w": 42,
                    "content": "도함수 → 기울기 / 원함수 → 접점 좌표",
                    "delayMs": 400,
                },
                {
                    "id": "micro-point-form",
                    "type": "equation",
                    "x": 8,
                    "y": 46,
                    "w": 42,
                    "content": "(x, y) = (1, f(1)) = (1, 0)",
                    "delayMs": 900,
                },
                {
                    "id": "micro-point-note",
                    "type": "callout",
                    "x": 8,
                    "y": 62,
                    "w": 42,
                    "content": "접선 문제에서 같은 x값이 두 엔진을 모두 움직인다고 기억하면 됩니다.",
                    "delayMs": 1300,
                },
            ],
            "resumeLabel": "원래 강의로 돌아가기",
        }

    return {
        "id": "micro-recap",
        "title": "질문 답변: 지금 장면을 다시 짚어볼게요",
        "narration": "지금 단계는 접선의 기울기와 접점을 분리해서 보는 구간입니다. 기울기는 도함수, 점은 원함수라는 역할 분리를 유지하면 흐름이 흔들리지 않습니다.",
        "objects": [
            {
                "id": "recap-1",
                "type": "heading",
                "x": 6,
                "y": 12,
                "w": 44,
                "content": "접선 문제의 기본 루틴",
            },
            {
                "id": "recap-2",
                "type": "bullet",
                "x": 8,
                "y": 30,
                "w": 42,
                "content": "1. 도함수로 기울기 찾기",
                "delayMs": 300,
            },
            {
                "id": "recap-3",
                "type": "bullet",
                "x": 8,
                "y": 42,
                "w": 42,
                "content": "2. 원함수로 접점 찾기",
                "delayMs": 700,
            },
            {
                "id": "recap-4",
                "type": "bullet",
                "x": 8,
                "y": 54,
                "w": 42,
                "content": "3. 점기울기식에 대입하기",
                "delayMs": 1100,
            },
        ],
        "resumeLabel": "원래 강의로 돌아가기",
    }


def build_problem() -> dict:
    return {
        "id": "problem-tangent-001",
        "title": "접선의 방정식 기본형",
        "statement": "함수 f(x) = x² - 4x + 3의 그래프 위의 점 x = 1에서의 접선의 방정식을 구하시오.",
        "coachHint": "종이에 풀이한 뒤, 컴퓨터에는 핵심 단계만 입력하세요. 도함수, 기울기, 접점, 최종식 순서면 충분합니다.",
        "expectedOutline": [
            "도함수 구하기",
            "x=1 대입으로 기울기 구하기",
            "원함수에 x=1 대입으로 접점 구하기",
            "점기울기식으로 직선 완성",
        ],
    }


DIAGNOSTIC_QUESTIONS = [
    {
        "id": "diag-1",
        "prompt": "f(x) = x²의 도함수는 무엇인가?",
        "options": ["x", "2x", "x²", "2"],
        "answer": 1,
        "concept": "derivative-basic",
    },
    {
        "id": "diag-2",
        "prompt": "접선의 방정식을 구할 때 반드시 필요한 정보 조합은 무엇인가?",
        "options": ["기울기와 한 점", "두 점", "넓이와 둘레", "미분계수와 적분값"],
        "answer": 0,
        "concept": "tangent-structure",
    },
    {
        "id": "diag-3",
        "prompt": "x = a에서의 접점을 구하려면 무엇을 해야 하는가?",
        "options": ["도함수에만 a를 넣는다", "원함수에만 a를 넣는다", "도함수와 원함수에 모두 a를 넣는다", "아무것도 넣지 않는다"],
        "answer": 2,
        "concept": "point-evaluation",
    },
]


def default_mastery() -> list[dict]:
    return [
        {"id": "derivative-basic", "title": "도함수 계산", "score": 74, "trend": "+6", "risk": "중간"},
        {"id": "tangent-structure", "title": "접선 구조 이해", "score": 62, "trend": "+11", "risk": "높음"},
        {"id": "point-evaluation", "title": "접점 좌표 계산", "score": 58, "trend": "+9", "risk": "높음"},
        {"id": "sign-accuracy", "title": "부호/정리 정확도", "score": 49, "trend": "-3", "risk": "매우 높음"},
    ]


def default_plan(profile: dict | None = None) -> list[dict]:
    profile = profile or {}
    daily_minutes = int(profile.get("dailyMinutes", 120))
    return [
        {
            "date": TODAY.isoformat(),
            "label": "오늘",
            "theme": "접선의 방정식 루프",
            "focus": "도함수 → 접점 → 직선식",
            "tasks": [
                {
                    "id": "task-lesson",
                    "title": "AI 칠판 강의 18분",
                    "type": "lesson",
                    "minutes": 18,
                    "status": "ready",
                },
                {
                    "id": "task-practice",
                    "title": "핵심 문제 1세트",
                    "type": "practice",
                    "minutes": 22,
                    "status": "ready",
                },
                {
                    "id": "task-review",
                    "title": "오답 회복 루틴",
                    "type": "review",
                    "minutes": 20,
                    "status": "locked",
                },
            ],
            "minutesTarget": min(60, daily_minutes),
        },
        {
            "date": (TODAY + timedelta(days=1)).isoformat(),
            "label": "D+1",
            "theme": "도함수 부호 안정화",
            "focus": "부호 실수 방지 루틴",
            "tasks": [
                {"id": "task-next-1", "title": "부호 교정 드릴 12문항", "type": "practice", "minutes": 30, "status": "planned"},
                {"id": "task-next-2", "title": "짧은 복습 강의 10분", "type": "lesson", "minutes": 10, "status": "planned"},
            ],
            "minutesTarget": min(70, daily_minutes),
        },
        {
            "date": (TODAY + timedelta(days=2)).isoformat(),
            "label": "D+2",
            "theme": "접선 응용",
            "focus": "문항 변형 적응",
            "tasks": [
                {"id": "task-next-3", "title": "유형 변형 6문항", "type": "practice", "minutes": 35, "status": "planned"},
            ],
            "minutesTarget": min(80, daily_minutes),
        },
    ]


@dataclass
class DemoStore:
    profile: dict = field(
        default_factory=lambda: {
            "name": "민준",
            "examDate": "2026-11-19",
            "targetScore": 84,
            "dailyMinutes": 120,
            "weeklyRestDay": "일요일",
            "weakUnits": ["미분", "함수의 증가와 감소"],
            "studyMood": "실전 위주",
        }
    )
    mastery: list[dict] = field(default_factory=default_mastery)
    plan: list[dict] = field(default_factory=default_plan)
    lesson_scenes: list[dict] = field(default_factory=build_lesson_scenes)
    practice_problem: dict = field(default_factory=build_problem)
    attempts: list[dict] = field(default_factory=list)

    def bootstrap(self) -> dict:
        return {
            "app": {
                "name": "Proofy Demo",
                "tagline": "AI Professor · AI TA · AI Coach",
            },
            "profile": self.profile,
            "diagnosticQuestions": DIAGNOSTIC_QUESTIONS,
            "dashboard": self.dashboard(),
            "lessonPreview": {
                "title": self.lesson_scenes[0]["title"],
                "sceneCount": len(self.lesson_scenes),
                "practiceProblemId": self.practice_problem["id"],
            },
            "latestAttempt": self.attempts[-1] if self.attempts else None,
        }

    def update_profile(self, payload: dict) -> dict:
        self.profile.update(
            {
                "name": payload.get("name") or self.profile["name"],
                "examDate": payload.get("examDate") or self.profile["examDate"],
                "targetScore": int(payload.get("targetScore") or self.profile["targetScore"]),
                "dailyMinutes": int(payload.get("dailyMinutes") or self.profile["dailyMinutes"]),
                "studyMood": payload.get("studyMood") or self.profile["studyMood"],
                "weakUnits": payload.get("weakUnits") or self.profile["weakUnits"],
            }
        )
        self.plan = default_plan(self.profile)
        return {"profile": self.profile, "dashboard": self.dashboard()}

    def submit_diagnostic(self, answers: dict) -> dict:
        correct = 0
        concept_hits: dict[str, bool] = {}
        for question in DIAGNOSTIC_QUESTIONS:
            answer = answers.get(question["id"])
            is_correct = answer == question["answer"]
            concept_hits[question["concept"]] = is_correct
            if is_correct:
                correct += 1

        updated = []
        for item in self.mastery:
            next_item = deepcopy(item)
            if item["id"] == "derivative-basic":
                next_item["score"] = 82 if concept_hits.get("derivative-basic") else 63
            if item["id"] == "tangent-structure":
                next_item["score"] = 78 if concept_hits.get("tangent-structure") else 57
            if item["id"] == "point-evaluation":
                next_item["score"] = 76 if concept_hits.get("point-evaluation") else 54
            updated.append(next_item)
        self.mastery = updated

        return {
            "score": correct * 33,
            "summary": "도함수 계산은 버티지만, 접선 문제에서 기울기와 접점을 분리해서 잡는 루틴이 아직 불안정합니다.",
            "topRisks": [
                "접선의 기울기와 도함수값 연결이 약함",
                "접점을 찾을 때 원함수 대입을 빠뜨림",
                "부호 실수 빈도가 높음",
            ],
            "recommendedTrack": "접선의 방정식 기본 루프",
            "mastery": self.mastery,
            "dashboard": self.dashboard(),
        }

    def dashboard(self) -> dict:
        days_left = (date.fromisoformat(self.profile["examDate"]) - TODAY).days
        today_tasks = self.plan[0]["tasks"]
        completed = sum(1 for task in today_tasks if task["status"] == "done")
        readiness = int(sum(item["score"] for item in self.mastery) / len(self.mastery))
        return {
            "headline": "오늘은 접선의 방정식 한 루프를 완성하는 날입니다.",
            "stats": {
                "daysLeft": days_left,
                "targetScore": self.profile["targetScore"],
                "todayMinutes": self.plan[0]["minutesTarget"],
                "completedTasks": completed,
                "readiness": readiness,
            },
            "mastery": self.mastery,
            "todayPlan": self.plan[0],
            "weeklyPlan": self.plan,
            "alerts": [
                "부호 실수 위험이 가장 높습니다. 풀이 검산을 1회 더 넣으세요.",
                "접선 문제는 도함수와 원함수에 같은 x값을 넣는 루틴이 필요합니다.",
            ],
            "coachMessage": "강의를 들은 뒤 바로 1문제만 정확하게 풀어도 오늘 계획의 절반은 성공입니다.",
        }

    def lesson_session(self) -> dict:
        return {
            "sessionId": "lesson-session-001",
            "unitTitle": "미분 - 접선의 방정식",
            "teacherName": "AI Professor Haneul",
            "scenes": self.lesson_scenes,
            "outline": [
                {"id": scene["id"], "title": scene["title"]} for scene in self.lesson_scenes
            ],
            "questionStarters": [
                "왜 접선 기울기가 도함수값이야?",
                "왜 원함수에도 1을 넣어?",
                "다시 한 번만 정리해줘",
            ],
            "practiceProblem": self.practice_problem,
        }

    def answer_question(self, question: str) -> dict:
        normalized = normalize_text(question)
        if "기울기" in question or "도함수" in question or "slope" in normalized:
            scene = build_question_scene("slope")
        elif "원함수" in question or "왜1" in normalized or "점" in question:
            scene = build_question_scene("point")
        else:
            scene = build_question_scene("recap")

        return {
            "mode": "interrupt",
            "scene": scene,
            "teacherReply": scene["narration"],
        }

    def submit_practice(self, payload: dict) -> dict:
        step_one = str(payload.get("stepOne", ""))
        step_two = str(payload.get("stepTwo", ""))
        step_three = str(payload.get("stepThree", ""))
        final_answer = str(payload.get("finalAnswer", ""))

        evaluated = [
            self._grade_step_one(step_one),
            self._grade_step_two(step_two),
            self._grade_step_three(step_three),
            self._grade_final(final_answer),
        ]
        accepted_count = sum(1 for item in evaluated if item["accepted"])
        solved = accepted_count >= 3 and evaluated[-1]["accepted"]

        recovery_plan = self._recalculate_plan(solved)
        attempt = {
            "id": f"attempt-{len(self.attempts) + 1:03d}",
            "problemId": self.practice_problem["id"],
            "solved": solved,
            "score": accepted_count * 25,
            "evaluatedSteps": evaluated,
            "submitted": {
                "stepOne": step_one,
                "stepTwo": step_two,
                "stepThree": step_three,
                "finalAnswer": final_answer,
            },
            "summary": (
                "핵심 구조는 거의 잡혔습니다. 이제 부호와 접점 계산을 같은 루틴으로 묶으면 안정됩니다."
                if solved
                else "접선 문제의 순서는 보였지만, 기울기와 접점을 분리해서 적는 습관이 더 필요합니다."
            ),
            "recommendedScenes": ["scene-slope", "scene-point"],
            "recoveryPlan": recovery_plan,
        }
        self.attempts.append(attempt)

        return {
            "attempt": attempt,
            "dashboard": self.dashboard(),
            "review": self.review_latest(),
        }

    def review_latest(self) -> dict:
        if not self.attempts:
            return {
                "empty": True,
                "headline": "아직 풀이 기록이 없습니다.",
                "message": "강의를 들은 뒤 문제를 풀면 이곳에 내 풀이와 권장 풀이 비교가 생깁니다.",
            }

        attempt = self.attempts[-1]
        wrong_steps = [item for item in attempt["evaluatedSteps"] if not item["accepted"]]
        return {
            "empty": False,
            "headline": "내 풀이를 권장 루틴과 비교합니다.",
            "attemptId": attempt["id"],
            "solved": attempt["solved"],
            "summary": attempt["summary"],
            "wrongSteps": wrong_steps,
            "goodSteps": [item for item in attempt["evaluatedSteps"] if item["accepted"]],
            "retrySet": [
                "도함수 부호 재확인 문제 2문항",
                "접점 좌표 계산 미니 퀴즈 1문항",
            ],
            "tomorrowPlan": self.plan[1],
        }

    def _recalculate_plan(self, solved: bool) -> dict:
        today_tasks = self.plan[0]["tasks"]
        today_tasks[0]["status"] = "done"
        today_tasks[1]["status"] = "done" if solved else "retry"
        today_tasks[2]["status"] = "done" if not solved else "planned"
        if solved:
            today_tasks[2]["title"] = "오늘 풀이를 5분 복기"
            self.plan[1]["focus"] = "접선 구조를 변형 문제에 이식"
            self.plan[1]["tasks"][0]["title"] = "접선 변형 4문항"
        else:
            today_tasks[2]["title"] = "부호 실수 회복 루틴 20분"
            today_tasks[2]["status"] = "ready"
            self.plan[1]["focus"] = "부호 실수와 접점 계산 보강"
            self.plan[1]["tasks"][0]["title"] = "도함수/접점 회복 세트"

        return {
            "today": self.plan[0],
            "tomorrow": self.plan[1],
            "coachMessage": (
                "정답을 맞혔더라도 같은 구조를 내일 한 번 더 반복해서 자동화하세요."
                if solved
                else "오늘은 회복 루틴을 열어두고, 내일은 같은 구조를 더 짧은 문제 세트로 다시 잡겠습니다."
            ),
        }

    def _grade_step_one(self, value: str) -> dict:
        normalized = normalize_text(value)
        if not normalized:
            return {
                "id": "step-1",
                "label": "도함수 계산",
                "accepted": False,
                "reason": "도함수를 먼저 적어야 접선 기울기를 구할 수 있습니다.",
                "errorType": "missing-step",
                "expected": "f'(x) = 2x - 4",
            }
        if "2x+4" in normalized:
            return {
                "id": "step-1",
                "label": "도함수 계산",
                "accepted": False,
                "reason": "-4x를 미분한 결과의 부호가 뒤집혔습니다.",
                "errorType": "sign-error",
                "expected": "f'(x) = 2x - 4",
            }
        if "2x-4" in normalized:
            return {
                "id": "step-1",
                "label": "도함수 계산",
                "accepted": True,
                "reason": "도함수를 정확히 계산했습니다.",
                "expected": "f'(x) = 2x - 4",
            }
        return {
            "id": "step-1",
            "label": "도함수 계산",
            "accepted": False,
            "reason": "도함수 형태가 맞지 않습니다. x²와 -4x를 각각 미분해 보세요.",
            "errorType": "concept",
            "expected": "f'(x) = 2x - 4",
        }

    def _grade_step_two(self, value: str) -> dict:
        normalized = normalize_text(value)
        if not normalized:
            return {
                "id": "step-2",
                "label": "기울기 계산",
                "accepted": False,
                "reason": "도함수에 x=1을 넣어 접선 기울기를 구해야 합니다.",
                "errorType": "missing-step",
                "expected": "f'(1) = -2",
            }
        if "-2" in normalized:
            return {
                "id": "step-2",
                "label": "기울기 계산",
                "accepted": True,
                "reason": "접선의 기울기를 정확히 찾았습니다.",
                "expected": "f'(1) = -2",
            }
        if "2" in normalized:
            return {
                "id": "step-2",
                "label": "기울기 계산",
                "accepted": False,
                "reason": "대입 후 정리에서 부호가 한 번 더 뒤집힌 것으로 보입니다.",
                "errorType": "arithmetic",
                "expected": "f'(1) = -2",
            }
        return {
            "id": "step-2",
            "label": "기울기 계산",
            "accepted": False,
            "reason": "기울기 단계는 도함수값 하나로 끝납니다. f'(1)을 다시 계산해 보세요.",
            "errorType": "concept",
            "expected": "f'(1) = -2",
        }

    def _grade_step_three(self, value: str) -> dict:
        normalized = normalize_text(value)
        if not normalized:
            return {
                "id": "step-3",
                "label": "접점 계산",
                "accepted": False,
                "reason": "같은 x=1을 원함수에 넣어 접점을 구해야 합니다.",
                "errorType": "missing-step",
                "expected": "f(1) = 0 또는 접점 (1, 0)",
            }
        if "(1,0)" in normalized or "f(1)=0" in normalized or "=0" in normalized:
            return {
                "id": "step-3",
                "label": "접점 계산",
                "accepted": True,
                "reason": "접점 좌표를 정확히 찾았습니다.",
                "expected": "f(1) = 0 또는 접점 (1, 0)",
            }
        return {
            "id": "step-3",
            "label": "접점 계산",
            "accepted": False,
            "reason": "접점이 빠졌습니다. 점기울기식에는 점 좌표가 반드시 필요합니다.",
            "errorType": "missing-point",
            "expected": "f(1) = 0 또는 접점 (1, 0)",
        }

    def _grade_final(self, value: str) -> dict:
        normalized = normalize_text(value)
        accepted_forms = ["y=-2x+2", "y-0=-2(x-1)", "y=-2(x-1)"]
        if not normalized:
            return {
                "id": "final",
                "label": "최종 답",
                "accepted": False,
                "reason": "최종 직선식을 적어야 풀이가 완성됩니다.",
                "errorType": "missing-step",
                "expected": "y = -2x + 2",
            }
        if any(form == normalized for form in accepted_forms):
            return {
                "id": "final",
                "label": "최종 답",
                "accepted": True,
                "reason": "최종 접선의 방정식이 맞습니다.",
                "expected": "y = -2x + 2",
            }
        return {
            "id": "final",
            "label": "최종 답",
            "accepted": False,
            "reason": "직선식의 정리 결과가 다릅니다. 기울기와 접점을 다시 대입해 보세요.",
            "errorType": "equation-build",
            "expected": "y = -2x + 2",
        }


STORE = DemoStore()


class DemoHandler(BaseHTTPRequestHandler):
    server_version = "LectureOSDemo/0.1"

    def _send_json(self, status: HTTPStatus, payload: dict) -> None:
        body = json_bytes(payload)
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        if not raw:
            return {}
        return json.loads(raw.decode("utf-8"))

    def _serve_static(self, path: str) -> None:
        relative = path.lstrip("/") or "index.html"
        file_path = (STATIC_DIR / relative).resolve()
        if not str(file_path).startswith(str(STATIC_DIR.resolve())) or not file_path.exists():
            file_path = STATIC_DIR / "index.html"
        content = file_path.read_bytes()
        content_type = mimetypes.guess_type(file_path.name)[0] or "text/plain"
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", f"{content_type}; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path == "/api/bootstrap":
            self._send_json(HTTPStatus.OK, STORE.bootstrap())
            return
        if parsed.path == "/api/dashboard":
            self._send_json(HTTPStatus.OK, STORE.dashboard())
            return
        if parsed.path == "/api/lesson/session":
            self._send_json(HTTPStatus.OK, STORE.lesson_session())
            return
        if parsed.path == "/api/review/latest":
            self._send_json(HTTPStatus.OK, STORE.review_latest())
            return
        self._serve_static(parsed.path)

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        payload = self._read_json()
        if parsed.path == "/api/profile":
            self._send_json(HTTPStatus.OK, STORE.update_profile(payload))
            return
        if parsed.path == "/api/diagnostic/submit":
            self._send_json(HTTPStatus.OK, STORE.submit_diagnostic(payload.get("answers", {})))
            return
        if parsed.path == "/api/lesson/question":
            self._send_json(HTTPStatus.OK, STORE.answer_question(payload.get("question", "")))
            return
        if parsed.path == "/api/practice/submit":
            self._send_json(HTTPStatus.OK, STORE.submit_practice(payload))
            return
        self._send_json(
            HTTPStatus.NOT_FOUND,
            {"error": "not-found", "message": f"No route for {parsed.path}"},
        )

    def log_message(self, format: str, *args) -> None:
        return


def run() -> None:
    server = ThreadingHTTPServer(("127.0.0.1", 8000), DemoHandler)
    print("Proofy demo running at http://127.0.0.1:8000")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    run()
