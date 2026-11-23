from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal

from .data_collector import CollectedData
from .scheduler import SM2Record, build_initial_records


@dataclass
class AnalysisResult:
    overall_progress: float = 0.0
    total_sections: int = 0
    completed_section_ids: list[str] = field(default_factory=list)
    remaining_sections: list[dict] = field(default_factory=list)  # {id, title, intent, focus, flashcards}
    weak_concepts: list[str] = field(default_factory=list)
    top_wrong_concepts: list[str] = field(default_factory=list)
    top_questions: list[str] = field(default_factory=list)
    sessions_per_week: float = 2.0
    learning_pace: Literal["빠름", "보통", "느림"] = "보통"
    all_concepts: list[str] = field(default_factory=list)
    sm2_records: list[SM2Record] = field(default_factory=list)
    exec_summary: dict = field(default_factory=dict)  # key_topics, learning_objectives, conceptual_flow


def analyze(data: CollectedData) -> AnalysisResult:
    result = AnalysisResult()

    result.exec_summary = data.exec_summary
    result.total_sections = len(data.sections)
    result.overall_progress = _calculate_progress(data)
    result.completed_section_ids, result.remaining_sections = _split_sections(data)
    result.weak_concepts, result.top_wrong_concepts = _identify_weak_concepts(data.quiz_attempts)
    result.top_questions = [q.get("question", "") for q in data.questions[:5] if q.get("question")]
    result.sessions_per_week = _estimate_pace(data.query_history)
    result.learning_pace = _pace_label(result.sessions_per_week)
    result.all_concepts = _collect_all_concepts(data)

    wrong_attempts = _count_wrong_by_concept(data.quiz_attempts)
    weak_set = set(result.weak_concepts)
    result.sm2_records = build_initial_records(result.all_concepts, weak_set, wrong_attempts)

    return result


def _calculate_progress(data: CollectedData) -> float:
    doc_progress = data.document.get("progress", 0)
    if isinstance(doc_progress, (int, float)) and doc_progress > 0:
        return min(doc_progress / 100.0, 1.0)
    if not data.sections:
        return 0.0
    attempted_docs = {a.get("document_id") for a in data.quiz_attempts if a.get("is_correct")}
    if attempted_docs:
        return min(len(attempted_docs) / len(data.sections), 1.0)
    return 0.0


def _split_sections(data: CollectedData) -> tuple[list[str], list[dict]]:
    if not data.sections:
        return [], []
    total = len(data.sections)
    progress = data.document.get("progress", 0) or 0
    completed_count = round(total * progress / 100)
    sorted_sections = sorted(data.sections, key=lambda s: s.get("order_index", 0))
    completed = [s["id"] for s in sorted_sections[:completed_count]]
    remaining = [
        {
            "id": s["id"],
            "title": s.get("title", ""),
            "intent": s.get("intent", "definition"),
            "focus": s.get("focus", ""),
            "flashcards": s.get("flashcards", []),
            "keywords": s.get("keywords") or [],
        }
        for s in sorted_sections[completed_count:]
    ]
    return completed, remaining


def _identify_weak_concepts(attempts: list[dict]) -> tuple[list[str], list[str]]:
    counter: Counter = Counter()
    for attempt in attempts:
        if not attempt.get("is_correct"):
            for concept in attempt.get("weak_concepts") or []:
                counter[concept] += 1
    all_weak = [c for c, _ in counter.most_common()]
    return all_weak, all_weak[:5]


def _count_wrong_by_concept(attempts: list[dict]) -> dict[str, int]:
    counter: Counter = Counter()
    for attempt in attempts:
        if not attempt.get("is_correct"):
            for concept in attempt.get("weak_concepts") or []:
                counter[concept] += 1
    return dict(counter)


def _estimate_pace(query_history: list[dict]) -> float:
    if not query_history:
        return 2.0
    timestamps: list[datetime] = []
    for q in query_history:
        ts_str = q.get("ts", "")
        if not ts_str:
            continue
        try:
            dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            timestamps.append(dt)
        except ValueError:
            continue
    if not timestamps:
        return 2.0
    timestamps.sort()
    now = datetime.now(timezone.utc)
    recent = [t for t in timestamps if (now - t).days <= 28]
    if not recent:
        return 2.0
    weeks = max((now - recent[0]).days / 7.0, 1.0)
    unique_days = {t.date() for t in recent}
    return round(len(unique_days) / weeks, 1)


def _pace_label(sessions_per_week: float) -> str:
    if sessions_per_week >= 5:
        return "빠름"
    if sessions_per_week >= 2:
        return "보통"
    return "느림"


def _collect_all_concepts(data: CollectedData) -> list[str]:
    """
    SM-2 단위 개념 목록. 섹션 제목을 1차 기준으로 삼고
    Supabase 키워드를 보조로 추가한다.
    """
    concepts: list[str] = []
    seen: set[str] = set()

    # 1차: 섹션 제목 (짧고 의미 있음 — SM-2 단위로 적합)
    for section in data.sections:
        title = section.get("title", "")
        if title and title not in seen:
            concepts.append(title)
            seen.add(title)

    # 2차: Supabase 섹션 keywords
    for section in data.sections:
        for kw in section.get("keywords") or []:
            if kw and kw not in seen:
                concepts.append(kw)
                seen.add(kw)

    # 3차: section_summaries key_concepts (있을 때만)
    for summary in data.section_summaries:
        for kc in summary.get("key_concepts", []):
            if kc and kc not in seen:
                concepts.append(kc)
                seen.add(kc)

    return concepts
