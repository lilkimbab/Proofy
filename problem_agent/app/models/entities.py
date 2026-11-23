from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Problem(Base):
    __tablename__ = "problems"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("prob"))
    user_id: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    document_id: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    type: Mapped[str] = mapped_column(String(32), nullable=False)
    difficulty: Mapped[str] = mapped_column(String(32), nullable=False)
    bloom_level: Mapped[str] = mapped_column(String(32), nullable=False)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    choices: Mapped[list[dict] | None] = mapped_column(JSON, nullable=True)
    answer: Mapped[dict] = mapped_column(JSON, nullable=False)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    choice_explanations: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    choice_diagnostics: Mapped[list[dict] | None] = mapped_column(JSON, nullable=True)
    rubric: Mapped[list[dict] | None] = mapped_column(JSON, nullable=True)
    concepts: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    source_chunk_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    source_refs: Mapped[list[dict] | None] = mapped_column(JSON, nullable=True)
    source_grounding_notes: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    source_evidence_snapshot: Mapped[list[dict] | None] = mapped_column(JSON, nullable=True)
    item_model_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    item_design_brief: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    difficulty_profile: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    teacher_review_checklist: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    professor_grade_score: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    student_response_simulation: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    quality_status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    submissions: Mapped[list[Submission]] = relationship(back_populates="problem", cascade="all, delete-orphan")
    feedbacks: Mapped[list[Feedback]] = relationship(back_populates="problem", cascade="all, delete-orphan")


class AssessmentSession(Base):
    __tablename__ = "assessment_sessions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("asess"))
    user_id: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    document_id: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="generated", nullable=False)
    problem_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    readiness: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    generation_metadata: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Submission(Base):
    __tablename__ = "submissions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("sub"))
    problem_id: Mapped[str] = mapped_column(ForeignKey("problems.id"), index=True, nullable=False)
    user_id: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    answer: Mapped[dict] = mapped_column(JSON, nullable=False)
    solution_steps: Mapped[str | None] = mapped_column(Text, nullable=True)
    elapsed_time_sec: Mapped[float | None] = mapped_column(Float, nullable=True)
    hint_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    confidence_level: Mapped[int | None] = mapped_column(Integer, nullable=True)
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    problem: Mapped[Problem] = relationship(back_populates="submissions")
    feedback: Mapped[Feedback | None] = relationship(back_populates="submission", cascade="all, delete-orphan", uselist=False)


class ProblemHintEvent(Base):
    __tablename__ = "problem_hint_events"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("hint"))
    problem_id: Mapped[str] = mapped_column(ForeignKey("problems.id"), index=True, nullable=False)
    user_id: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    level: Mapped[int] = mapped_column(Integer, nullable=False)
    mode: Mapped[str] = mapped_column(String(32), default="practice", nullable=False)
    hint_text: Mapped[str] = mapped_column(Text, nullable=False)
    answer_revealed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class Feedback(Base):
    __tablename__ = "feedbacks"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("fb"))
    submission_id: Mapped[str] = mapped_column(ForeignKey("submissions.id"), index=True, unique=True, nullable=False)
    problem_id: Mapped[str] = mapped_column(ForeignKey("problems.id"), index=True, nullable=False)
    user_id: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    is_correct: Mapped[bool] = mapped_column(Boolean, nullable=False)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    max_score: Mapped[float] = mapped_column(Float, nullable=False)
    mistake_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    weak_concepts: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    feedback: Mapped[str] = mapped_column(Text, nullable=False)
    recommended_review: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    source_chunk_ids: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    evaluation_details: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    learning_state: Mapped[str] = mapped_column(String(64), default="unreported", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    submission: Mapped[Submission] = relationship(back_populates="feedback")
    problem: Mapped[Problem] = relationship(back_populates="feedbacks")


class FeedbackActionEvent(Base):
    __tablename__ = "feedback_action_events"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("fact"))
    feedback_id: Mapped[str] = mapped_column(ForeignKey("feedbacks.id"), index=True, nullable=False)
    problem_id: Mapped[str] = mapped_column(ForeignKey("problems.id"), index=True, nullable=False)
    user_id: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    event_type: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    action_type: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    target_problem_id: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    target_content_id: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    is_successful: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    helpful_rating: Mapped[int | None] = mapped_column(Integer, nullable=True)
    event_metadata: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class MistakeRemediationEvent(Base):
    __tablename__ = "mistake_remediation_events"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("rem"))
    user_id: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    source_feedback_id: Mapped[str] = mapped_column(ForeignKey("feedbacks.id"), index=True, nullable=False)
    source_problem_id: Mapped[str] = mapped_column(ForeignKey("problems.id"), index=True, nullable=False)
    followup_problem_id: Mapped[str] = mapped_column(ForeignKey("problems.id"), index=True, nullable=False)
    followup_content_id: Mapped[str | None] = mapped_column(String(128), index=True, nullable=True)
    target_concepts: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    target_mistake_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    resolved: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    repeated_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class ProblemItemAnalytics(Base):
    __tablename__ = "problem_item_analytics"

    problem_id: Mapped[str] = mapped_column(ForeignKey("problems.id"), primary_key=True)
    document_id: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    problem_type: Mapped[str] = mapped_column(String(32), nullable=False)
    total_attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    correct_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    incorrect_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    correct_rate: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    correct_rate_smoothed: Mapped[float] = mapped_column(Float, default=0.5, nullable=False)
    average_score: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    max_score: Mapped[float] = mapped_column(Float, default=1, nullable=False)
    discrimination_proxy: Mapped[float | None] = mapped_column(Float, nullable=True)
    sample_size_status: Mapped[str] = mapped_column(String(32), default="insufficient", nullable=False)
    statistics_confidence: Mapped[str] = mapped_column(String(32), default="low", nullable=False)
    statistics_note: Mapped[str] = mapped_column(Text, default="통계가 아직 적어서 참고용으로만 봅니다.", nullable=False)
    quality_score_for_review: Mapped[float | None] = mapped_column(Float, nullable=True)
    quality_score_source: Mapped[str] = mapped_column(String(64), default="item_quality", nullable=False)
    timed_attempt_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    average_time_sec: Mapped[float | None] = mapped_column(Float, nullable=True)
    hint_usage_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    hint_usage_rate: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    choice_selection_counts: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    choice_selection_distribution: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    choice_mistake_type_counts: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    non_functioning_distractors: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    mistake_type_counts: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    common_mistake_types: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    missed_rubric_criteria_counts: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    common_missed_rubric_criteria: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    needs_review: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    review_reasons: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class ProblemTemplateAnalytics(Base):
    __tablename__ = "problem_template_analytics"

    template_key: Mapped[str] = mapped_column(String(128), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    document_id: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    item_model_id: Mapped[str] = mapped_column(String(80), index=True, nullable=False)
    concept: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    difficulty: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    problem_type: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    problem_ids: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    problem_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    correct_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    incorrect_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    correct_rate: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    correct_rate_smoothed: Mapped[float] = mapped_column(Float, default=0.5, nullable=False)
    average_score: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    max_score: Mapped[float] = mapped_column(Float, default=1, nullable=False)
    discrimination_proxy: Mapped[float | None] = mapped_column(Float, nullable=True)
    sample_size_status: Mapped[str] = mapped_column(String(32), default="insufficient", nullable=False)
    statistics_confidence: Mapped[str] = mapped_column(String(32), default="low", nullable=False)
    statistics_note: Mapped[str] = mapped_column(Text, default="템플릿 통계가 아직 적어서 참고용으로만 봅니다.", nullable=False)
    item_quality_average: Mapped[float | None] = mapped_column(Float, nullable=True)
    usage_quality_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    quality_score_for_review: Mapped[float | None] = mapped_column(Float, nullable=True)
    quality_score_source: Mapped[str] = mapped_column(String(64), default="template_item_quality", nullable=False)
    hint_usage_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    hint_usage_rate: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    mistake_type_counts: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    common_mistake_types: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    missed_rubric_criteria_counts: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    common_missed_rubric_criteria: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    needs_review: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    review_reasons: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class ProblemRegenerationCandidate(Base):
    __tablename__ = "problem_regeneration_candidates"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("regen"))
    problem_id: Mapped[str] = mapped_column(ForeignKey("problems.id"), index=True, nullable=False)
    generated_problem_id: Mapped[str | None] = mapped_column(ForeignKey("problems.id"), index=True, nullable=True)
    user_id: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    document_id: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="open", nullable=False)
    trigger_reasons: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    source_metrics: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    suggested_action: Mapped[str] = mapped_column(String(80), default="review_item", nullable=False)
    resolution_notes: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class UsageLedger(Base):
    __tablename__ = "usage_ledger"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("usage"))
    user_id: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    feature: Mapped[str] = mapped_column(String(80), index=True, nullable=False)
    model: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    request_id: Mapped[str | None] = mapped_column(String(128), index=True, nullable=True)
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    estimated_cost_krw: Mapped[float | None] = mapped_column(Float, nullable=True)
    premium_model_used: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    premium_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class UserQualityReport(Base):
    __tablename__ = "user_quality_reports"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: new_id("qreport"))
    user_id: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    target_type: Mapped[str] = mapped_column(String(40), index=True, nullable=False)
    target_id: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    reason: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="open", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class UserConceptStat(Base):
    __tablename__ = "user_concept_stats"

    user_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    concept: Mapped[str] = mapped_column(String(255), primary_key=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    correct_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    wrong_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    mastery: Mapped[float] = mapped_column(Float, default=0.5, nullable=False)
    mistake_types: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
