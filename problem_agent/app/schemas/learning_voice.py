from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class LearnerAgeBand(StrEnum):
    elementary = "elementary"
    middle_school = "middle_school"
    high_school = "high_school"
    adult = "adult"


class KoreanSpeechStyle(StrEnum):
    soft_haeyo = "soft_haeyo"
    polite_formal = "polite_formal"


class FeedbackSituation(StrEnum):
    correct = "correct"
    partially_correct = "partially_correct"
    wrong = "wrong"
    repeated_wrong = "repeated_wrong"
    hint_requested = "hint_requested"
    stuck = "stuck"
    summary = "summary"
    loading = "loading"
    error = "error"


class FeedbackDepth(StrEnum):
    quick = "quick"
    normal = "normal"
    deep = "deep"


class NextActionType(StrEnum):
    retry = "retry"
    show_hint = "show_hint"
    review_concept_card = "review_concept_card"
    solve_similar = "solve_similar"
    see_worked_example = "see_worked_example"
    mini_quiz = "mini_quiz"
    mark_conditions = "mark_conditions"
    split_steps = "split_steps"
    compare_terms = "compare_terms"
    review_formula = "review_formula"
    check_units = "check_units"
    rewrite_answer = "rewrite_answer"
    stop = "stop"


class LearnerToneProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    age_band: LearnerAgeBand = LearnerAgeBand.high_school
    speech_style: KoreanSpeechStyle = KoreanSpeechStyle.soft_haeyo
    warmth_level: Literal["low", "medium", "high"] = "high"
    emoji_policy: Literal["none", "rare", "contextual", "frequent"] = "contextual"
    encouragement_policy: Literal["specific_only", "light"] = "specific_only"


class FeedbackCopyInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    situation: FeedbackSituation
    concept: str | None = Field(default=None, max_length=120)
    user_answer: str | None = Field(default=None, max_length=400)
    correct_answer: str | None = Field(default=None, max_length=400)
    mistake_type: str | None = Field(default=None, max_length=80)
    learner_misconception: str | None = Field(default=None, max_length=500)
    evidence_summary: str | None = Field(default=None, max_length=800)
    source_reference_label: str | None = Field(default=None, max_length=120)
    confidence: Literal["low", "medium", "high"] = "medium"
    feedback_depth: FeedbackDepth = FeedbackDepth.normal
    next_action: NextActionType | None = None
    tone_profile: LearnerToneProfile = Field(default_factory=LearnerToneProfile)

    @field_validator(
        "concept",
        "user_answer",
        "correct_answer",
        "mistake_type",
        "learner_misconception",
        "evidence_summary",
        "source_reference_label",
    )
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None


class FeedbackCopyOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=160)
    body: str = Field(min_length=1, max_length=1200)
    next_action_type: NextActionType | None = None
    next_action_label: str | None = Field(default=None, max_length=80)
    secondary_action_type: NextActionType | None = None
    secondary_action_label: str | None = Field(default=None, max_length=80)
    tone_status: Literal["passed", "needs_review"] = "passed"
    warnings: list[str] = Field(default_factory=list, max_length=10)

    @field_validator("title", "body", "next_action_label", "secondary_action_label")
    @classmethod
    def normalize_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip()


class LearningContentCopy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    intro: str | None = Field(default=None, max_length=300)
    success: FeedbackCopyOutput | None = None
    failure: FeedbackCopyOutput | None = None
