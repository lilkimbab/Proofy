from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class GenerateRequest(BaseModel):
    user_id: str
    doc_id: str


class MilestoneSchema(BaseModel):
    week: int
    goal: str
    target_concepts: list[str]
    completion_target: float  # 0.0–1.0


class DayPlanSchema(BaseModel):
    day: int
    date: str  # YYYY-MM-DD
    type: Literal["학습", "복습", "평가", "휴식"]
    title: str
    section_id: str | None = None
    section_titles: list[str]
    intents: list[str] = []          # 섹션별 intent (definition, example, comparison, exercise)
    flashcard_count: int = 0         # 오늘 학습 섹션의 플래시카드 수 (자기 테스트 도전)
    concepts_to_study: list[str]
    concepts_to_review: list[str]
    estimated_minutes: int
    status: Literal["예정", "진행 중", "완료", "미완료"] = "예정"


class ReviewScheduleSchema(BaseModel):
    concept: str
    last_reviewed: str | None
    next_review: str  # YYYY-MM-DD
    interval_days: int
    ease_factor: float
    repetitions: int
    is_weak: bool


class RoadmapSchema(BaseModel):
    roadmap_id: str
    doc_id: str
    user_id: str
    document_title: str
    subject: str
    goal: str
    deadline: str | None
    generated_at: str
    overall_progress: float
    estimated_total_days: int
    learning_pace: Literal["빠름", "보통", "느림"]
    weak_concepts: list[str]
    milestones: list[MilestoneSchema]
    daily_plan: list[DayPlanSchema]
    review_schedule: list[ReviewScheduleSchema]
    review_strategy: str
    recommendations: list[str]


class TodayPlanResponse(BaseModel):
    date: str
    study_items: list[DayPlanSchema]
    review_concepts: list[str]
    estimated_minutes: int


class ProgressUpdateRequest(BaseModel):
    section_id: str   # daily_plan item의 section_id 또는 section title
    completed: bool


class ReviewUpdateRequest(BaseModel):
    concept: str
    quality: int = Field(ge=0, le=5)   # 0-2: 오답, 3-5: 정답


class ErrorResponse(BaseModel):
    detail: str
