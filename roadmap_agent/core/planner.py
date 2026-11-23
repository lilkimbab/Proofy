from __future__ import annotations

import copy
import json
import logging
import math
import os
import uuid
from datetime import date, timedelta
from pathlib import Path

from dotenv import load_dotenv

from .analyzer import AnalysisResult
from .data_collector import CollectedData
from .llm_client import LLMClient, LLMError
from .scheduler import SM2Record, sm2_update

load_dotenv()

logger = logging.getLogger(__name__)

ROADMAP_DIR = os.getenv("ROADMAP_DIR", "./roadmaps")
DEFAULT_DAILY_MINUTES = int(os.getenv("DEFAULT_DAILY_STUDY_MINUTES", "30"))
MAX_DAILY_MINUTES = int(os.getenv("MAX_DAILY_STUDY_MINUTES", "120"))
MAX_PLAN_DAYS = int(os.getenv("MAX_DAILY_PLAN_DAYS", "60"))

def _make_system_prompt(plan_days: int) -> str:
    if plan_days <= 7:
        unit_hint = f"전체 계획이 {plan_days}일이므로 마일스톤은 일(Day) 단위로 2~3개만 구성하세요. week 필드에 몇 번째 날인지를 넣으세요."
    elif plan_days <= 21:
        unit_hint = f"전체 계획이 {plan_days}일이므로 마일스톤은 단계(Phase) 단위로 2~3개 구성하세요. week 필드에 단계 번호를 넣으세요."
    else:
        unit_hint = f"전체 계획이 {plan_days}일이므로 마일스톤은 주(Week) 단위로 구성하세요."

    return f"""\
당신은 개인화 학습 계획 전문가입니다. 아래 분석 데이터를 바탕으로 반드시 아래 JSON 형식으로만 응답하세요.
{unit_hint}

{{
  "milestones": [
    {{"week": 1, "goal": "...", "target_concepts": ["개념1", "개념2"], "completion_target": 0.3}}
  ],
  "review_strategy": "복습 전략 설명 (3-5문장)",
  "recommendations": ["실행 가능한 팁1", "팁2", "팁3"]
}}
"""


class Planner:
    def __init__(self):
        self._llm = LLMClient()

    async def generate(
        self,
        user_id: str,
        doc_id: str,
        data: CollectedData,
        analysis: AnalysisResult,
    ) -> dict:
        # 기존 SM-2 이력 보존: 재생성 시 학습 진행 상태 초기화 방지
        review_schedule = self._merge_sm2(user_id, doc_id, analysis.sm2_records)

        # plan_days를 먼저 계산해 LLM에 적절한 마일스톤 단위를 전달
        daily_plan = _build_daily_plan(analysis, data)
        llm_output = await self._call_llm(data, analysis, len(daily_plan))

        roadmap = {
            "roadmap_id": str(uuid.uuid4()),
            "doc_id": doc_id,
            "user_id": user_id,
            "document_title": data.document.get("title", doc_id),
            "subject": data.document.get("subject", ""),
            "goal": data.document.get("goal", ""),
            "deadline": data.document.get("deadline"),
            "generated_at": date.today().isoformat(),
            "overall_progress": round(analysis.overall_progress, 3),
            "estimated_total_days": _estimate_total_days(analysis),
            "learning_pace": analysis.learning_pace,
            "weak_concepts": analysis.weak_concepts,
            "milestones": llm_output.get("milestones", []),
            "daily_plan": daily_plan,
            "review_schedule": review_schedule,
            "review_strategy": llm_output.get("review_strategy", ""),
            "recommendations": llm_output.get("recommendations", []),
        }

        self._save(user_id, doc_id, roadmap)
        return roadmap

    def _merge_sm2(
        self, user_id: str, doc_id: str, new_records: list[SM2Record]
    ) -> list[dict]:
        """재생성 시 기존 SM-2 레코드의 학습 상태(repetitions, ease_factor 등)를 보존한다."""
        existing = self.load(user_id, doc_id)
        if not existing:
            return [r.to_dict() for r in new_records]

        existing_map = {r["concept"]: r for r in existing.get("review_schedule", [])}
        result = []
        for record in new_records:
            if record.concept in existing_map:
                result.append(existing_map[record.concept])
            else:
                result.append(record.to_dict())
        return result

    async def _call_llm(self, data: CollectedData, analysis: AnalysisResult, plan_days: int = 30) -> dict:
        exec_summary = analysis.exec_summary
        objectives_text = "; ".join(exec_summary.get("learning_objectives", [])[:3]) or "없음"
        flow_text = exec_summary.get("conceptual_flow", "") or "없음"
        topics_text = ", ".join(exec_summary.get("key_topics", [])[:5]) or "없음"

        section_summary_text = "; ".join(
            f"{s.get('section_title', '')}[{s.get('intent', '')}]({s.get('focus', '')})"
            for s in data.section_summaries[:8]
        ) or "섹션 요약 없음"

        questions_text = "; ".join(analysis.top_questions[:3]) or "없음"

        user_prompt = f"""\
학습 분석 데이터:
- 문서: {data.document.get('title', '미상')}
- 학습 목표: {objectives_text}
- 전체 흐름: {flow_text}
- 핵심 주제: {topics_text}
- 마감일: {data.document.get('deadline') or '없음'}
- 전체 진도: {round(analysis.overall_progress * 100)}%
- 학습 속도: {analysis.learning_pace} (주당 {analysis.sessions_per_week:.1f}회)
- 총 개념 수: {len(analysis.all_concepts)}
- 약점 개념 TOP5: {', '.join(analysis.top_wrong_concepts) or '없음'}
- 최근 사용자 질문 (혼란 신호): {questions_text}
- 섹션 구성: {section_summary_text}
- 남은 섹션 수: {len(analysis.remaining_sections)}
"""
        try:
            return await self._llm.complete_json(_make_system_prompt(plan_days), user_prompt)
        except LLMError as e:
            logger.error(f"LLM 로드맵 생성 실패: {e}")
            return _fallback_llm_output(analysis)

    def _save(self, user_id: str, doc_id: str, roadmap: dict) -> None:
        out_dir = Path(ROADMAP_DIR) / user_id
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / f"{doc_id}.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(roadmap, f, ensure_ascii=False, indent=2)

    def load(self, user_id: str, doc_id: str) -> dict | None:
        path = Path(ROADMAP_DIR) / user_id / f"{doc_id}.json"
        if not path.exists():
            return None
        with open(path, encoding="utf-8") as f:
            return json.load(f)

    def delete(self, user_id: str, doc_id: str) -> bool:
        path = Path(ROADMAP_DIR) / user_id / f"{doc_id}.json"
        if path.exists():
            path.unlink()
            return True
        return False


def _build_daily_plan(analysis: AnalysisResult, data: CollectedData) -> list[dict]:
    today = date.today()

    deadline: date | None = None
    raw_deadline = data.document.get("deadline")
    if raw_deadline:
        try:
            deadline = date.fromisoformat(str(raw_deadline)[:10])
        except ValueError:
            pass

    if deadline and deadline > today:
        max_days = min((deadline - today).days, MAX_PLAN_DAYS)
    else:
        max_days = MAX_PLAN_DAYS

    remaining = list(analysis.remaining_sections)

    # 하루 학습 가능 시간 기반으로 섹션 수 결정
    sections_per_day = max(1, MAX_DAILY_MINUTES // DEFAULT_DAILY_MINUTES)
    # 마감일이 촉박하면 더 늘림
    if remaining and max_days > 0 and math.ceil(len(remaining) / sections_per_day) > max_days:
        sections_per_day = math.ceil(len(remaining) / max_days)

    # 자료 분량 기반 적응형 기간 계산
    # SM-2 3라운드 복습 간격: +1, +1, +6 = 8일 → 버퍼 포함 +14일
    study_days = math.ceil(len(remaining) / sections_per_day) if remaining else 0
    adaptive_max = study_days + 14
    max_days = min(adaptive_max, max_days)

    # SM-2 시뮬레이션: 개념은 해당 섹션을 학습한 날 다음 날부터 복습 스케줄에 진입
    sim = {r.concept: copy.copy(r) for r in analysis.sm2_records}
    for r in sim.values():
        r.next_review = "9999-12-31"  # 학습 전까지는 복습 대상 아님
        r.repetitions = 0
    ready: set[str] = set()  # 이미 학습된 개념

    plan: list[dict] = []

    for day_offset in range(max_days):
        current_date = today + timedelta(days=day_offset)
        date_str = current_date.isoformat()

        day_sections = [remaining.pop(0) for _ in range(sections_per_day) if remaining]

        # 오늘 학습한 섹션의 개념 → 내일부터 복습 대상
        if day_sections:
            for s in day_sections:
                title = s["title"]
                ready.add(title)
                if title in sim:
                    sim[title].next_review = (current_date + timedelta(days=1)).isoformat()
                    sim[title].repetitions = 0

        # 오늘 복습 대상: 이미 학습된 개념 중 next_review가 오늘인 것만
        due_today = [r for r in sim.values() if r.concept in ready and r.next_review == date_str]
        review_concepts = [r.concept for r in due_today[:3]]

        if day_sections:
            plan.append({
                "day": len(plan) + 1,
                "date": date_str,
                "type": "학습",
                "title": " / ".join(s["title"] for s in day_sections),
                "section_id": day_sections[0]["id"],
                "section_titles": [s["title"] for s in day_sections],
                "intents": [s.get("intent", "definition") for s in day_sections],
                "flashcard_count": sum(len(s.get("flashcards", [])) for s in day_sections),
                "concepts_to_study": _extract_study_concepts(day_sections),
                "concepts_to_review": review_concepts,
                "estimated_minutes": DEFAULT_DAILY_MINUTES * len(day_sections),
                "status": "예정",
            })
        elif review_concepts:
            plan.append({
                "day": len(plan) + 1,
                "date": date_str,
                "type": "복습",
                "title": f"복습: {', '.join(review_concepts[:2])}",
                "section_id": None,
                "section_titles": [],
                "intents": [],
                "flashcard_count": 0,
                "concepts_to_study": [],
                "concepts_to_review": review_concepts,
                "estimated_minutes": DEFAULT_DAILY_MINUTES // 2,
                "status": "예정",
            })

        # SM-2 업데이트 시뮬레이션 (계획상 정답=4 가정)
        for r in due_today[:3]:
            sm2_update(r, 4)

        # 조기 종료: 섹션 완료 후 남은 복습 일정이 없으면 중단
        if not remaining:
            future = [r for r in sim.values()
                      if r.concept in ready and
                      r.next_review <= (today + timedelta(days=max_days)).isoformat() and
                      r.next_review != "9999-12-31"]
            if not future:
                break

    return plan


def _estimate_total_days(analysis: AnalysisResult) -> int:
    sessions_per_week = max(analysis.sessions_per_week, 0.1)
    remaining = len(analysis.remaining_sections)
    if remaining == 0:
        return 0
    days_per_session = 7.0 / sessions_per_week
    return round(remaining * days_per_session)


def _extract_study_concepts(sections: list[dict]) -> list[str]:
    """섹션의 flashcard 질문과 focus에서 오늘 학습할 핵심 개념 목록을 추출한다."""
    concepts: list[str] = []
    seen: set[str] = set()
    for s in sections:
        # 1차: 플래시카드 질문 (가장 구체적인 학습 단위)
        for fc in s.get("flashcards", [])[:3]:
            q = fc.get("question", "")
            if q and q not in seen:
                concepts.append(q)
                seen.add(q)
        # 2차: focus 필드에서 핵심어 추출 (문장이 아닌 경우에만)
        focus = s.get("focus", "")
        if focus and len(focus) < 40 and focus not in seen:
            concepts.append(focus)
            seen.add(focus)
    return concepts[:5]


def _fallback_llm_output(analysis: AnalysisResult) -> dict:
    weeks = max(1, round(_estimate_total_days(analysis) / 7))
    milestones = [
        {
            "week": i + 1,
            "goal": f"{i + 1}주차 학습 목표",
            "target_concepts": analysis.all_concepts[i * 3:(i + 1) * 3],
            "completion_target": round((i + 1) / weeks, 2),
        }
        for i in range(min(weeks, 4))
    ]
    return {
        "milestones": milestones,
        "review_strategy": "약점 개념을 중심으로 매일 복습하고, 퀴즈를 통해 이해도를 확인하세요.",
        "recommendations": [
            "매일 꾸준히 학습하는 것이 효과적입니다.",
            "약점 개념은 반복 학습을 통해 보완하세요.",
            "학습 후 퀴즈로 복습 효과를 높이세요.",
        ],
    }
