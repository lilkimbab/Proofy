from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any
from urllib import error, request

from app.core.config import settings


@dataclass
class LLMReply:
    text: str
    provider: str


@dataclass
class LessonInterruptionPlan:
    teacher_reply: str
    provider: str
    focus_object_id: str | None = None
    response_mode: str = "answer"
    scene_strategy: str = "current"
    micro_scene_key: str | None = None
    board_title: str = "같이 다시 볼 포인트"
    board_points: list[str] | None = None
    branch_outline: list[str] | None = None
    resume_label: str = "이어서 같이 볼게요"


@dataclass
class PlanStrategyReply:
    headline: str
    coach_message: str
    weekly_focus: list[str]
    monthly_focus: list[str]
    adaptation_rules: list[str]
    provider: str


class LessonLLMService:
    def __init__(self) -> None:
        self.provider = settings.llm_provider.strip().lower()
        self.api_url = settings.llm_api_url.strip()
        self.api_key = settings.llm_api_key.strip()
        self.model = settings.llm_model.strip()
        self.gemini_api_key = settings.gemini_api_key.strip()
        self.gemini_model = settings.gemini_model.strip()
        self.timeout_seconds = settings.llm_timeout_seconds
        self.question_timeout_seconds = max(4, min(self.timeout_seconds, 8))
        self.strategy_timeout_seconds = max(6, min(self.timeout_seconds, 12))

    @property
    def configured(self) -> bool:
        if self.provider == "gemini":
            return bool(self.gemini_api_key and self.gemini_model)
        return bool(self.api_url and self.api_key and self.model)

    def answer_lesson_question(
        self,
        *,
        question: str,
        unit_title: str,
        scene_title: str,
        narration: str,
        scene_goal: str,
        scene_takeaway: str,
        scene_exam_cue: str,
        practice_statement: str,
        mastery_snapshot: list[dict[str, Any]],
        scene_objects: list[dict[str, str]] | None = None,
        selected_object_id: str | None = None,
    ) -> LLMReply:
        fallback = self._heuristic_lesson_answer(
            question=question,
            scene_title=scene_title,
            narration=narration,
            scene_goal=scene_goal,
            scene_takeaway=scene_takeaway,
            scene_exam_cue=scene_exam_cue,
            practice_statement=practice_statement,
            scene_objects=scene_objects or [],
            selected_object_id=selected_object_id,
        )
        if not self.configured:
            return LLMReply(text=fallback, provider="fallback")

        mastery_text = ", ".join(
            f"{item['title']}:{item['score']}" for item in mastery_snapshot[:4] if item.get("title")
        )
        selected_object_summary = next(
            (
                item.get("summary", "")
                for item in (scene_objects or [])
                if str(item.get("id")) == str(selected_object_id)
            ),
            "없음",
        )
        object_text = "\n".join(
            f"- {item.get('type')}: {item.get('summary')}"
            for item in (scene_objects or [])[:6]
        ) or "없음"
        system_prompt = (
            "너는 친근하지만 실력이 좋은 수능 수학 강사다. "
            "답변은 한국어로 하고, 학생을 다그치지 말고 같이 정리해 주는 말투를 쓴다. "
            "첫 문장에서 학생 질문에 대한 직접적인 답을 먼저 준다. "
            "애매하게 장면을 요약하지 말고, 질문에 정확히 필요한 개념이나 풀이 기준을 바로 말한다. "
            "문장은 너무 길지 않게, '직접 답 -> 왜 그런지 -> 지금 문제에 어떻게 쓰는지' 순서로 설명한다. "
            "가능하면 현재 칠판 객체나 식을 한 번 언급해서 답을 구체화한다. "
            "말투는 '같이 볼까요?', '여기서 이렇게 생각하면 편해요.'처럼 자연스럽고 부드럽게 유지한다. "
            "마지막 한 문장은 학생이 바로 다시 강의로 돌아갈 수 있게 짧게 정리한다."
        )
        user_prompt = (
            f"[단원]\n{unit_title}\n\n"
            f"[현재 장면]\n{scene_title}\n{narration}\n\n"
            f"[장면 목표]\n{scene_goal or '없음'}\n\n"
            f"[장면 핵심]\n{scene_takeaway or '없음'}\n\n"
            f"[시험 포인트]\n{scene_exam_cue or '없음'}\n\n"
            f"[현재 칠판 객체]\n{object_text}\n\n"
            f"[선택 객체]\n{selected_object_summary}\n\n"
            f"[현재 문제]\n{practice_statement}\n\n"
            f"[학생 mastery]\n{mastery_text}\n\n"
            f"[학생 질문]\n{question}"
        )
        response_text = self._chat(system_prompt, user_prompt, timeout_seconds=self.question_timeout_seconds)
        return LLMReply(
            text=response_text or fallback,
            provider=self.provider if response_text else "fallback",
        )

    def _heuristic_lesson_answer(
        self,
        *,
        question: str,
        scene_title: str,
        narration: str,
        scene_goal: str,
        scene_takeaway: str,
        scene_exam_cue: str,
        practice_statement: str,
        scene_objects: list[dict[str, str]],
        selected_object_id: str | None,
    ) -> str:
        selected_summary = next(
            (
                str(item.get("summary") or "")
                for item in scene_objects
                if str(item.get("id")) == str(selected_object_id)
            ),
            "",
        )
        anchor = selected_summary or (scene_objects[0]["summary"] if scene_objects else "")
        takeaway = scene_takeaway or scene_goal or narration or scene_title
        exam_point = scene_exam_cue or "지금 장면의 기준 식과 조건을 먼저 고정하는 것"
        problem_first_line = practice_statement.split(".")[0].strip() if practice_statement else "현재 문제의 첫 줄"

        if any(token in question for token in ("왜", "원리", "의미", "개념")):
            return (
                f"핵심은 {takeaway}라는 뜻이에요. "
                f"즉, 여기서는 {exam_point}를 먼저 잡아야 하고, {anchor or '현재 칠판의 식'}이 그 기준이 됩니다. "
                f"그래서 문제로 돌아가면 {problem_first_line}에서 바로 그 기준을 먼저 적으면 훨씬 덜 흔들립니다."
            )
        if any(token in question for token in ("어떻게", "순서", "풀이", "접근", "과정")):
            return (
                f"순서는 복잡하지 않아요. 먼저 {exam_point}를 확인하고, 다음으로 {anchor or '핵심 식'}을 적고, 마지막에 현재 문제 조건에 얹으면 됩니다. "
                f"즉 지금 문제에서는 {problem_first_line}부터 같은 흐름으로 시작하면 돼요."
            )
        if any(token in question for token in ("기초", "처음", "다시", "천천히")):
            return (
                f"기초부터 다시 보면, 먼저 {takeaway}를 한 문장으로 잡는 게 시작이에요. "
                f"그다음 {anchor or '현재 칠판의 핵심 식'}을 보고 왜 그 식이 먼저 나오는지만 이해하면 됩니다. "
                f"문제로 돌아가면 {problem_first_line} 앞에서 그 기준 문장부터 다시 떠올려 볼까요?"
            )
        return (
            f"지금 질문의 답은 {takeaway}를 먼저 기준으로 잡으면 된다는 거예요. "
            f"여기서는 {exam_point}가 가장 중요하고, {anchor or '칠판의 핵심 식'}이 그 출발점입니다. "
            f"이 기준으로 다시 보면 현재 문제도 훨씬 자연스럽게 이어집니다."
        )

    def plan_lesson_interruption(
        self,
        *,
        question: str,
        unit_title: str,
        scene_title: str,
        narration: str,
        scene_goal: str,
        scene_takeaway: str,
        scene_exam_cue: str,
        practice_statement: str,
        mastery_snapshot: list[dict[str, Any]],
        scene_objects: list[dict[str, str]],
        available_micro_scenes: list[str],
        selected_object_id: str | None = None,
    ) -> LessonInterruptionPlan:
        heuristic_branch = self._should_branch_question(question)
        fallback_focus = selected_object_id or (scene_objects[0]["id"] if scene_objects else None)
        fallback_reply = (
            f"좋아요. 지금 질문은 '{scene_title}' 장면의 핵심을 다시 한번 짚어보면 풀릴 부분이에요. "
            f"우선 {narration} 흐름을 다시 같이 보고, 바로 '{practice_statement}'에 어떻게 연결되는지 확인해볼까요? "
            "답을 본 뒤에는 핵심 식과 조건만 한 번 더 보고 넘어가면 됩니다."
        )
        fallback = LessonInterruptionPlan(
            teacher_reply=fallback_reply,
            provider="fallback",
            focus_object_id=fallback_focus,
            response_mode="branch" if heuristic_branch else "answer",
            scene_strategy="current",
            board_title="같이 다시 볼 포인트",
            board_points=[
                "지금 장면에서 꼭 잡아야 할 식부터 다시 봅니다.",
                "왜 필요한지보다 어디에 쓰이는지 먼저 연결해 봅니다.",
                "같은 구조를 현재 문제에 바로 얹어 봅니다.",
            ],
            branch_outline=[
                "질문을 먼저 분명하게 다시 봅니다.",
                "핵심 개념을 짧게 다시 세웁니다.",
                "바로 현재 문제에 다시 얹어 봅니다.",
            ],
            resume_label="이어서 같이 볼게요",
        )
        if not self.configured:
            return fallback

        mastery_text = ", ".join(
            f"{item['title']}:{item['score']}" for item in mastery_snapshot[:6] if item.get("title")
        )
        object_text = "\n".join(
            f"- id={item['id']} | type={item['type']} | summary={item['summary']}"
            for item in scene_objects
        )
        micro_scene_text = ", ".join(available_micro_scenes) if available_micro_scenes else "없음"
        selected_text = selected_object_id or "없음"
        system_prompt = (
            "너는 친근하지만 정확한 수능 수학 AI 강사다. 학생 질문에 대해 현재 칠판 장면을 활용해 설명하고, "
            "필요하면 보충 장면으로 잠깐 전환한다. 반드시 JSON만 출력한다. "
            "teacher_reply는 한국어 3~5문장으로 쓰고, 말투는 부드럽고 자연스럽게 한다. "
            "학생을 평가하거나 지적하지 말고 '같이 보자', '이렇게 생각하면 편하다'는 톤을 유지한다. "
            "response_mode는 answer 또는 branch 중 하나다. "
            "branch는 질문 때문에 강의 흐름을 잠깐 바꿔 3장면 정도의 짧은 분기 강의가 필요한 경우다. "
            "board_points는 2~3개, branch_outline은 2~3개, scene_strategy는 current 또는 micro 중 하나, "
            "focus_object_id는 현재 장면 object id 중 하나 또는 NONE이다."
        )
        user_prompt = (
            f"[단원]\n{unit_title}\n\n"
            f"[현재 장면]\n{scene_title}\n{narration}\n\n"
            f"[장면 목표]\n{scene_goal or '없음'}\n\n"
            f"[장면 한 줄 요약]\n{scene_takeaway or '없음'}\n\n"
            f"[시험 포인트]\n{scene_exam_cue or '없음'}\n\n"
            f"[현재 문제]\n{practice_statement}\n\n"
            f"[학생 mastery]\n{mastery_text}\n\n"
            f"[현재 장면 객체]\n{object_text}\n\n"
            f"[사용 가능한 보충 장면 키]\n{micro_scene_text}\n\n"
            f"[현재 선택된 객체]\n{selected_text}\n\n"
            f"[학생 질문]\n{question}\n\n"
            "다음 JSON 스키마로만 답해라.\n"
            "{\n"
            '  "teacher_reply": "...",\n'
            '  "response_mode": "answer or branch",\n'
            '  "focus_object_id": "object-id or NONE",\n'
            '  "scene_strategy": "current or micro",\n'
            '  "micro_scene_key": "scene key or NONE",\n'
            '  "board_title": "짧은 제목",\n'
            '  "board_points": ["포인트1", "포인트2"],\n'
            '  "branch_outline": ["질문 다시 보기", "핵심 개념 다시 세우기", "문제에 연결"],\n'
            '  "resume_label": "이어서 같이 볼게요"\n'
            "}"
        )
        response_text = self._chat(system_prompt, user_prompt, timeout_seconds=self.question_timeout_seconds)
        if not response_text:
            return fallback
        payload = self._extract_json(response_text)
        if not payload:
            return fallback

        board_points = payload.get("board_points")
        if not isinstance(board_points, list):
            board_points = []
        valid_object_ids = {item["id"] for item in scene_objects}
        focus_object_id = payload.get("focus_object_id")
        if not isinstance(focus_object_id, str) or focus_object_id == "NONE":
            focus_object_id = None
        if focus_object_id not in valid_object_ids:
            focus_object_id = fallback_focus
        micro_scene_key = payload.get("micro_scene_key")
        if not isinstance(micro_scene_key, str) or micro_scene_key == "NONE":
            micro_scene_key = None
        if micro_scene_key and micro_scene_key not in available_micro_scenes:
            micro_scene_key = None
        scene_strategy = str(payload.get("scene_strategy") or "current").strip().lower()
        if scene_strategy not in {"current", "micro"}:
            scene_strategy = "current"
        if scene_strategy == "micro" and not micro_scene_key:
            scene_strategy = "current"
        response_mode = str(payload.get("response_mode") or ("branch" if heuristic_branch else "answer")).strip().lower()
        if response_mode not in {"answer", "branch"}:
            response_mode = "branch" if heuristic_branch else "answer"
        branch_outline = payload.get("branch_outline")
        if not isinstance(branch_outline, list):
            branch_outline = []

        teacher_reply = str(payload.get("teacher_reply") or "").strip() or fallback_reply
        return LessonInterruptionPlan(
            teacher_reply=teacher_reply,
            provider=self.provider,
            focus_object_id=focus_object_id,
            response_mode=response_mode,
            scene_strategy=scene_strategy,
            micro_scene_key=micro_scene_key,
            board_title=str(payload.get("board_title") or "같이 다시 볼 포인트").strip() or "같이 다시 볼 포인트",
            board_points=[str(item).strip() for item in board_points if str(item).strip()][:3],
            branch_outline=[str(item).strip() for item in branch_outline if str(item).strip()][:3] or fallback.branch_outline,
            resume_label=str(payload.get("resume_label") or "이어서 같이 볼게요").strip() or "이어서 같이 볼게요",
        )

    def _should_branch_question(self, question: str) -> bool:
        text = question.strip()
        if len(text) >= 16:
            return True
        branch_keywords = (
            "왜",
            "어떻게",
            "의미",
            "개념",
            "차이",
            "연결",
            "기초",
            "다시",
            "처음",
            "정리",
            "이해",
            "설명",
            "흐름",
            "원리",
        )
        return any(keyword in text for keyword in branch_keywords)

    def answer_highlight_question(
        self,
        *,
        document_title: str,
        highlighted_text: str,
        note: str,
        question: str,
    ) -> LLMReply:
        fallback = (
            "하이라이트한 구절의 핵심은 정의와 적용 조건을 분리해서 보는 것입니다. "
            "이 문장을 문제에 옮길 때는 조건, 계산, 결론을 따로 체크하세요."
        )
        if not self.configured:
            return LLMReply(text=fallback, provider="fallback")

        system_prompt = (
            "너는 수능 수학 학습 조교다. 사용자가 하이라이트한 자료를 바탕으로 "
            "핵심 개념, 시험에서의 함정, 다시 읽을 포인트를 짧고 선명하게 설명한다."
        )
        user_prompt = (
            f"[문서]\n{document_title}\n\n"
            f"[하이라이트]\n{highlighted_text}\n\n"
            f"[학생 메모]\n{note or '없음'}\n\n"
            f"[질문]\n{question or '이 부분의 핵심과 문제 적용 포인트를 설명해줘.'}"
        )
        response_text = self._chat(system_prompt, user_prompt, timeout_seconds=self.strategy_timeout_seconds)
        return LLMReply(
            text=response_text or fallback,
            provider=self.provider if response_text else "fallback",
        )

    def build_plan_strategy(
        self,
        *,
        profile: dict[str, Any],
        mastery_snapshot: list[dict[str, Any]],
        today_plan: dict[str, Any],
        weekly_plan: list[dict[str, Any]],
        days_left: int,
        question_signals: list[dict[str, Any]] | None = None,
    ) -> PlanStrategyReply:
        weak_units = [item.get("title", "") for item in sorted(mastery_snapshot, key=lambda x: x.get("score", 0))[:4]]
        repeated_questions = [
            signal
            for signal in (question_signals or [])
            if str(signal.get("unitTitle") or signal.get("conceptId") or "").strip()
        ][:6]
        fallback = PlanStrategyReply(
            headline=f"{weak_units[0] if weak_units else '약한 단원'}부터 먼저 잡고 수능일까지 순서대로 밀어갑니다.",
            coach_message=(
                f"D-{days_left} 기준으로 약한 단원을 먼저 회복하고, "
                "간격 복습과 고난도 연결 문제를 섞어 계속 끌고 가겠습니다."
            ),
            weekly_focus=[
                "이번 주는 가장 약한 단원부터 강의-문제-복습 순서로 붙입니다.",
                "막힌 단원은 2~4일 간격으로 다시 불러와서 잊히기 전에 회수합니다.",
                "목표 점수가 높을수록 고난도 문제를 더 빠르게 섞습니다.",
            ],
            monthly_focus=[
                "초반에는 개념 회복과 대표 유형 정리를 먼저 끝냅니다.",
                "중반에는 약점 단원을 섞은 실전형 문제 흐름으로 넘어갑니다.",
                "후반에는 킬러와 실수 복구를 중심으로 압축합니다.",
            ],
            adaptation_rules=[
                "미완료 일정은 다음 날 첫 과제로 자동 재배치합니다.",
                "정답률이 낮은 단원은 복습 간격을 더 짧게 잡습니다.",
                "정답률이 높아지면 같은 단원을 고난도로 올려 연결합니다.",
            ],
            provider="fallback",
        )
        if not self.configured:
            return fallback

        mastery_text = "\n".join(
            f"- {item.get('title')}: score={item.get('score')} risk={item.get('risk')}"
            for item in mastery_snapshot[:10]
            if item.get("title")
        )
        today_tasks = "\n".join(
            f"- {task.get('title')} ({task.get('minutes')}분, {task.get('status')})"
            for task in today_plan.get("tasks", [])
        )
        weekly_tasks = "\n".join(
            f"- {day.get('label')}: {day.get('theme')} / {day.get('focus')}"
            for day in weekly_plan[:7]
        )
        question_text = "\n".join(
            f"- {signal.get('unitTitle') or signal.get('conceptId')}: {signal.get('category')} 질문 {signal.get('weight')}"
            for signal in repeated_questions
        ) or "없음"
        system_prompt = (
            "너는 수능 수학 학습 설계를 잘하는 전략 코치다. "
            "학생의 목표 점수, 남은 기간, 약점 단원, 현재 계획을 읽고 "
            "현실적이지만 밀도 높은 장기 전략을 한국어로 정리한다. "
            "특히 학생이 자주 묻는 질문 유형을 다음날 강의와 문제 배치에 반영해라. "
            "반드시 JSON만 출력한다. 문구는 학생 친화적이고 단정하게 쓴다."
        )
        user_prompt = (
            f"[학생 프로필]\n{json.dumps(profile, ensure_ascii=False)}\n\n"
            f"[마스터리]\n{mastery_text}\n\n"
            f"[오늘 계획]\n{today_tasks}\n\n"
            f"[주간 계획]\n{weekly_tasks}\n\n"
            f"[반복 질문 신호]\n{question_text}\n\n"
            f"[수능까지 남은 일수]\n{days_left}\n\n"
            "다음 JSON 스키마로만 답해라.\n"
            "{\n"
            '  "headline": "한 줄 전략",\n'
            '  "coach_message": "학생에게 들려줄 짧은 설명",\n'
            '  "weekly_focus": ["이번 주 포인트1", "이번 주 포인트2", "이번 주 포인트3"],\n'
            '  "monthly_focus": ["장기 전략1", "장기 전략2", "장기 전략3"],\n'
            '  "adaptation_rules": ["자동 조정 규칙1", "자동 조정 규칙2", "자동 조정 규칙3"]\n'
            "}"
        )
        response_text = self._chat(system_prompt, user_prompt)
        if not response_text:
            return fallback
        payload = self._extract_json(response_text)
        if not payload:
            return fallback

        def _items(value: Any) -> list[str]:
            if not isinstance(value, list):
                return []
            return [str(item).strip() for item in value if str(item).strip()][:4]

        return PlanStrategyReply(
            headline=str(payload.get("headline") or fallback.headline).strip() or fallback.headline,
            coach_message=str(payload.get("coach_message") or fallback.coach_message).strip() or fallback.coach_message,
            weekly_focus=_items(payload.get("weekly_focus")) or fallback.weekly_focus,
            monthly_focus=_items(payload.get("monthly_focus")) or fallback.monthly_focus,
            adaptation_rules=_items(payload.get("adaptation_rules")) or fallback.adaptation_rules,
            provider=self.provider,
        )

    def _chat(self, system_prompt: str, user_prompt: str, *, timeout_seconds: int | None = None) -> str | None:
        if self.provider == "gemini":
            return self._chat_gemini(system_prompt, user_prompt, timeout_seconds=timeout_seconds)
        body = json.dumps(
            {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "temperature": 0.4,
            }
        ).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }
        req = request.Request(self.api_url, data=body, headers=headers, method="POST")
        try:
            with request.urlopen(req, timeout=timeout_seconds or self.timeout_seconds) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (TimeoutError, error.HTTPError, error.URLError, json.JSONDecodeError):
            return None
        return self._extract_text(payload)

    def _chat_gemini(self, system_prompt: str, user_prompt: str, *, timeout_seconds: int | None = None) -> str | None:
        if not self.gemini_api_key or not self.gemini_model:
            return None
        endpoint = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self.gemini_model}:generateContent"
        )
        body = json.dumps(
            {
                "systemInstruction": {
                    "parts": [{"text": system_prompt}],
                },
                "contents": [
                    {
                        "role": "user",
                        "parts": [{"text": user_prompt}],
                    }
                ],
                "generationConfig": {
                    "temperature": 0.4,
                    "candidateCount": 1,
                },
            }
        ).encode("utf-8")
        req = request.Request(
            endpoint,
            data=body,
            headers={
                "Content-Type": "application/json",
                "x-goog-api-key": self.gemini_api_key,
            },
            method="POST",
        )
        try:
            with request.urlopen(req, timeout=timeout_seconds or self.timeout_seconds) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (TimeoutError, error.HTTPError, error.URLError, json.JSONDecodeError):
            return None
        return self._extract_text(payload)

    def _extract_text(self, payload: dict[str, Any]) -> str | None:
        if isinstance(payload.get("output_text"), str) and payload["output_text"].strip():
            return payload["output_text"].strip()

        choices = payload.get("choices")
        if isinstance(choices, list) and choices:
            message = choices[0].get("message", {})
            content = message.get("content")
            if isinstance(content, str) and content.strip():
                return content.strip()
            if isinstance(content, list):
                parts: list[str] = []
                for item in content:
                    if isinstance(item, dict) and isinstance(item.get("text"), str):
                        parts.append(item["text"])
                if parts:
                    return "\n".join(part.strip() for part in parts if part.strip())

        output = payload.get("output")
        if isinstance(output, list):
            parts: list[str] = []
            for item in output:
                content = item.get("content") if isinstance(item, dict) else None
                if not isinstance(content, list):
                    continue
                for block in content:
                    if isinstance(block, dict) and isinstance(block.get("text"), str):
                        parts.append(block["text"])
            if parts:
                return "\n".join(part.strip() for part in parts if part.strip())

        candidates = payload.get("candidates")
        if isinstance(candidates, list) and candidates:
            content = candidates[0].get("content", {})
            parts = content.get("parts", [])
            if isinstance(parts, list):
                text_parts = [
                    part.get("text", "").strip()
                    for part in parts
                    if isinstance(part, dict) and isinstance(part.get("text"), str)
                ]
                text_parts = [item for item in text_parts if item]
                if text_parts:
                    return "\n".join(text_parts)
        return None

    def _extract_json(self, text: str) -> dict[str, Any] | None:
        cleaned = text.strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
            cleaned = re.sub(r"\s*```$", "", cleaned)
        try:
            payload = json.loads(cleaned)
            return payload if isinstance(payload, dict) else None
        except json.JSONDecodeError:
            pass
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if not match:
            return None
        try:
            payload = json.loads(match.group(0))
        except json.JSONDecodeError:
            return None
        return payload if isinstance(payload, dict) else None
