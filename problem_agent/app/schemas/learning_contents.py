from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.learning_voice import LearningContentCopy
from app.schemas.problems import BloomLevel, Difficulty, MistakeType, ProblemStyle, ProblemType
from app.schemas.quality import (
    LearningTaskStrategyProfile,
    MaterialReadinessReport,
    QualityFlag,
    QualityStatus,
    TargetRigor,
)


class LearningContentType(StrEnum):
    flashcard = "flashcard"
    cloze = "cloze"
    true_false = "true_false"
    ordering = "ordering"
    matching = "matching"
    worked_example = "worked_example"
    mistake_drill = "mistake_drill"
    mini_exam = "mini_exam"
    concept_summary_card = "concept_summary_card"


class LearningContentInteractionMode(StrEnum):
    study_only = "study_only"
    auto_gradable = "auto_gradable"
    problem_linked = "problem_linked"
    problem_set = "problem_set"


class LearningContentQualityReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: QualityStatus
    score: float = Field(ge=0, le=1)
    flags: list[QualityFlag] = Field(default_factory=list)
    source_grounded: bool = True
    reasons: list[str] = Field(default_factory=list, max_length=20)
    action: str = Field(default="save", min_length=1, max_length=40)


class FlashcardPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    front: str = Field(min_length=1, max_length=500)
    back: str = Field(min_length=1, max_length=800)
    hint: str | None = Field(default=None, max_length=300)
    explanation: str = Field(min_length=1, max_length=1200)

    @model_validator(mode="after")
    def validate_distinct_sides(self) -> FlashcardPayload:
        if self.front.strip() == self.back.strip():
            raise ValueError("flashcard front and back must be different")
        return self


class ClozePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    prompt: str = Field(min_length=1, max_length=800)
    answer: str = Field(min_length=1, max_length=200)
    acceptable_answers: list[str] = Field(default_factory=list, max_length=10)
    explanation: str = Field(min_length=1, max_length=1200)

    @model_validator(mode="after")
    def validate_blank_and_answers(self) -> ClozePayload:
        if "____" not in self.prompt:
            raise ValueError("cloze prompt must include ____ blank")
        answers = [answer.strip() for answer in self.acceptable_answers]
        if any(not answer for answer in answers):
            raise ValueError("acceptable_answers must not include empty values")
        if self.answer.strip() not in answers:
            answers.insert(0, self.answer.strip())
        self.acceptable_answers = list(dict.fromkeys(answers))
        return self


class TrueFalsePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    statement: str = Field(min_length=1, max_length=800)
    answer: bool
    explanation: str = Field(min_length=1, max_length=1200)
    correction: str | None = Field(default=None, max_length=800)

    @model_validator(mode="after")
    def require_correction_for_false_statement(self) -> TrueFalsePayload:
        if self.answer is False and not (self.correction or "").strip():
            raise ValueError("false true_false content requires correction")
        return self


class OrderingItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=32)
    text: str = Field(min_length=1, max_length=300)


class OrderingPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    prompt: str = Field(min_length=1, max_length=800)
    items: list[OrderingItem] = Field(min_length=2, max_length=10)
    correct_order: list[str] = Field(min_length=2, max_length=10)
    explanation: str = Field(min_length=1, max_length=1200)

    @model_validator(mode="after")
    def validate_order_ids(self) -> OrderingPayload:
        item_ids = [item.id for item in self.items]
        if len(set(item_ids)) != len(item_ids):
            raise ValueError("ordering item ids must be unique")
        if set(self.correct_order) != set(item_ids):
            raise ValueError("correct_order must contain every ordering item id exactly once")
        if len(self.correct_order) != len(item_ids):
            raise ValueError("correct_order must not include duplicate item ids")
        return self


class MatchingPair(BaseModel):
    model_config = ConfigDict(extra="forbid")

    left: str = Field(min_length=1, max_length=200)
    right: str = Field(min_length=1, max_length=300)


class MatchingPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    prompt: str = Field(min_length=1, max_length=800)
    pairs: list[MatchingPair] = Field(min_length=2, max_length=12)
    explanation: str = Field(min_length=1, max_length=1200)

    @model_validator(mode="after")
    def validate_unique_pairs(self) -> MatchingPayload:
        left_values = [pair.left.strip() for pair in self.pairs]
        right_values = [pair.right.strip() for pair in self.pairs]
        if len(set(left_values)) != len(left_values):
            raise ValueError("matching left values must be unique")
        if len(set(right_values)) != len(right_values):
            raise ValueError("matching right values must be unique")
        return self


class WorkedExampleStep(BaseModel):
    model_config = ConfigDict(extra="forbid")

    order: int = Field(ge=1)
    text: str = Field(min_length=1, max_length=600)


class WorkedExamplePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    problem: str = Field(min_length=1, max_length=1000)
    steps: list[WorkedExampleStep] = Field(min_length=1, max_length=12)
    final_answer: str = Field(min_length=1, max_length=600)
    explanation: str = Field(min_length=1, max_length=1200)

    @field_validator("steps")
    @classmethod
    def validate_step_order(cls, steps: list[WorkedExampleStep]) -> list[WorkedExampleStep]:
        orders = [step.order for step in steps]
        if len(set(orders)) != len(orders):
            raise ValueError("worked_example step orders must be unique")
        return steps


class MistakeDrillPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    seed_problem_id: str = Field(min_length=1, max_length=128)
    seed_feedback_id: str = Field(min_length=1, max_length=128)
    target_mistake_type: MistakeType
    target_concepts: list[str] = Field(min_length=1, max_length=20)
    variant_strategy: str = Field(min_length=1, max_length=80)
    variant_focus: str | None = Field(default=None, max_length=500)
    selected_choice_id: str | None = Field(default=None, max_length=32)
    selected_choice_text: str | None = Field(default=None, max_length=500)
    misconception: str | None = Field(default=None, max_length=1200)
    repair_strategy: str | None = Field(default=None, max_length=1200)
    generated_problem_id: str | None = Field(default=None, max_length=128)
    remediation_event_id: str | None = Field(default=None, max_length=128)

    @field_validator("target_concepts")
    @classmethod
    def validate_target_concepts(cls, concepts: list[str]) -> list[str]:
        return _clean_unique_values(concepts, field_name="target_concepts", max_item_length=80)


class MiniExamItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content_id: str | None = Field(default=None, max_length=128)
    problem_id: str | None = Field(default=None, max_length=128)
    content_type: LearningContentType | str = Field(min_length=1)
    points: float = Field(default=1, gt=0)

    @model_validator(mode="after")
    def require_item_reference(self) -> MiniExamItem:
        if not self.content_id and not self.problem_id:
            raise ValueError("mini_exam item requires content_id or problem_id")
        return self


class MiniExamPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=200)
    time_limit_seconds: int | None = Field(default=None, ge=60, le=10800)
    items: list[MiniExamItem] = Field(min_length=1, max_length=50)
    blueprint: dict[str, Any] = Field(default_factory=dict)


class ConceptSummaryCardPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=200)
    summary: str = Field(min_length=1, max_length=1200)
    key_points: list[str] = Field(min_length=1, max_length=10)
    review_prompt: str | None = Field(default=None, max_length=500)

    @field_validator("key_points")
    @classmethod
    def validate_key_points(cls, key_points: list[str]) -> list[str]:
        return _clean_unique_values(key_points, field_name="key_points", max_item_length=200)


CONTENT_PAYLOAD_MODELS: dict[LearningContentType, type[BaseModel]] = {
    LearningContentType.flashcard: FlashcardPayload,
    LearningContentType.cloze: ClozePayload,
    LearningContentType.true_false: TrueFalsePayload,
    LearningContentType.ordering: OrderingPayload,
    LearningContentType.matching: MatchingPayload,
    LearningContentType.worked_example: WorkedExamplePayload,
    LearningContentType.mistake_drill: MistakeDrillPayload,
    LearningContentType.mini_exam: MiniExamPayload,
    LearningContentType.concept_summary_card: ConceptSummaryCardPayload,
}

CONTENT_INTERACTION_MODES: dict[LearningContentType, LearningContentInteractionMode] = {
    LearningContentType.flashcard: LearningContentInteractionMode.study_only,
    LearningContentType.cloze: LearningContentInteractionMode.auto_gradable,
    LearningContentType.true_false: LearningContentInteractionMode.auto_gradable,
    LearningContentType.ordering: LearningContentInteractionMode.auto_gradable,
    LearningContentType.matching: LearningContentInteractionMode.auto_gradable,
    LearningContentType.worked_example: LearningContentInteractionMode.study_only,
    LearningContentType.mistake_drill: LearningContentInteractionMode.problem_linked,
    LearningContentType.mini_exam: LearningContentInteractionMode.problem_set,
    LearningContentType.concept_summary_card: LearningContentInteractionMode.study_only,
}


class LearningContentBase(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    id: str | None = Field(default=None, max_length=128)
    user_id: str | None = Field(default=None, max_length=128)
    document_id: str = Field(min_length=1, max_length=128)
    content_type: LearningContentType
    interaction_mode: LearningContentInteractionMode | None = None
    concepts: list[str] = Field(min_length=1, max_length=20)
    source_chunk_ids: list[str] = Field(min_length=1, max_length=20)
    source_revision_ids: list[str] = Field(default_factory=list, max_length=20)
    content_version: str | None = Field(default=None, max_length=80)
    difficulty: Difficulty = Difficulty.medium
    bloom_level: BloomLevel = BloomLevel.understand
    quality_status: QualityStatus
    quality_report: LearningContentQualityReport
    material_readiness: MaterialReadinessReport | None = None
    payload: dict[str, Any]
    display_copy: LearningContentCopy | None = Field(default=None, alias="copy")
    created_at: datetime | None = None

    @field_validator("concepts")
    @classmethod
    def validate_concepts(cls, concepts: list[str]) -> list[str]:
        return _clean_unique_values(concepts, field_name="concepts", max_item_length=80)

    @field_validator("source_chunk_ids")
    @classmethod
    def validate_source_chunk_ids(cls, source_chunk_ids: list[str]) -> list[str]:
        return _clean_unique_values(source_chunk_ids, field_name="source_chunk_ids", max_item_length=128)

    @field_validator("source_revision_ids")
    @classmethod
    def validate_source_revision_ids(cls, source_revision_ids: list[str]) -> list[str]:
        return _clean_unique_values(
            source_revision_ids,
            field_name="source_revision_ids",
            max_item_length=128,
        )

    @model_validator(mode="after")
    def validate_content_contract(self) -> LearningContentBase:
        expected_mode = CONTENT_INTERACTION_MODES[self.content_type]
        if self.interaction_mode is None:
            self.interaction_mode = expected_mode
        elif self.interaction_mode != expected_mode:
            raise ValueError(f"{self.content_type} requires interaction_mode={expected_mode}")
        if self.quality_report.status != self.quality_status:
            raise ValueError("quality_report.status must match quality_status")

        payload_model = CONTENT_PAYLOAD_MODELS[self.content_type]
        self.payload = payload_model.model_validate(self.payload).model_dump(mode="json", exclude_none=True)
        return self


class LearningContentResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    id: str | None = Field(default=None, max_length=128)
    user_id: str | None = Field(default=None, max_length=128)
    document_id: str
    content_type: LearningContentType
    interaction_mode: LearningContentInteractionMode
    concepts: list[str]
    source_chunk_ids: list[str]
    source_revision_ids: list[str] = Field(default_factory=list)
    content_version: str | None = None
    difficulty: Difficulty
    bloom_level: BloomLevel
    quality_status: QualityStatus
    quality_report: LearningContentQualityReport
    material_readiness: MaterialReadinessReport | None = None
    payload: dict[str, Any]
    private_payload_available: bool = False
    display_copy: LearningContentCopy | None = Field(default=None, alias="copy")
    created_at: datetime | None = None


class GenerateLearningContentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_id: str = Field(min_length=1, max_length=128)
    concepts: list[str] = Field(min_length=1, max_length=20)
    content_type: LearningContentType
    count: int = Field(default=5, ge=1, le=10)
    difficulty: Difficulty = Difficulty.medium
    bloom_level: BloomLevel = BloomLevel.understand
    user_requirements: str | None = Field(default=None, max_length=1000)

    @field_validator("concepts")
    @classmethod
    def validate_request_concepts(cls, concepts: list[str]) -> list[str]:
        return _clean_unique_values(concepts, field_name="concepts", max_item_length=80)

    @model_validator(mode="after")
    def normalize_user_requirements(self) -> GenerateLearningContentRequest:
        if self.user_requirements is not None:
            self.user_requirements = self.user_requirements.strip() or None
        return self


class RecommendLearningContentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_id: str = Field(min_length=1, max_length=128)
    concepts: list[str] = Field(min_length=1, max_length=20)
    count: int = Field(default=3, ge=1, le=10)
    difficulty: Difficulty = Difficulty.medium
    bloom_level: BloomLevel = BloomLevel.understand
    user_requirements: str | None = Field(default=None, max_length=1000)

    @field_validator("concepts")
    @classmethod
    def validate_recommendation_concepts(cls, concepts: list[str]) -> list[str]:
        return _clean_unique_values(concepts, field_name="concepts", max_item_length=80)

    @model_validator(mode="after")
    def normalize_recommendation_request(self) -> RecommendLearningContentRequest:
        if self.user_requirements is not None:
            self.user_requirements = self.user_requirements.strip() or None
        return self


class GenerateMistakeDrillRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    feedback_id: str = Field(min_length=1, max_length=128)
    count: int = Field(default=1, ge=1, le=3)
    problem_type: ProblemType | None = None
    difficulty: Difficulty | None = None
    bloom_level: BloomLevel | None = None
    variant_strategy: str = Field(default="same_concept_new_condition", min_length=1, max_length=80)
    user_requirements: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def normalize_mistake_drill_request(self) -> GenerateMistakeDrillRequest:
        self.variant_strategy = self.variant_strategy.strip()
        if self.user_requirements is not None:
            self.user_requirements = self.user_requirements.strip() or None
        return self


class GenerateMiniExamRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_id: str = Field(min_length=1, max_length=128)
    concepts: list[str] = Field(min_length=1, max_length=20)
    count: int = Field(default=5, ge=1, le=10)
    problem_type: ProblemType = ProblemType.multiple_choice
    difficulty: Difficulty = Difficulty.medium
    bloom_level: BloomLevel = BloomLevel.understand
    title: str | None = Field(default=None, max_length=200)
    time_limit_seconds: int | None = Field(default=None, ge=60, le=10800)
    user_requirements: str | None = Field(default=None, max_length=1000)

    @field_validator("concepts")
    @classmethod
    def validate_mini_exam_concepts(cls, concepts: list[str]) -> list[str]:
        return _clean_unique_values(concepts, field_name="concepts", max_item_length=80)

    @model_validator(mode="after")
    def normalize_mini_exam_request(self) -> GenerateMiniExamRequest:
        if self.title is not None:
            self.title = self.title.strip() or None
        if self.user_requirements is not None:
            self.user_requirements = self.user_requirements.strip() or None
        return self


class GenerateLearningContentResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contents: list[LearningContentResponse]
    learning_task_strategy: LearningTaskStrategyProfile | None = None
    material_readiness: MaterialReadinessReport | None = None


class ProblemRecommendationOption(BaseModel):
    model_config = ConfigDict(extra="forbid")

    problem_type: ProblemType
    difficulty: Difficulty
    bloom_level: BloomLevel
    target_rigor: TargetRigor
    problem_style: ProblemStyle
    label: str = Field(min_length=1, max_length=80)
    reason: str = Field(min_length=1, max_length=300)


class LearningContentRecommendationOption(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content_type: LearningContentType
    label: str = Field(min_length=1, max_length=80)
    recommendation_level: Literal["recommended", "available", "not_recommended"]
    reason: str = Field(min_length=1, max_length=300)


class LearningContentRecommendationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    problem_options: list[ProblemRecommendationOption] = Field(default_factory=list)
    content_options: list[LearningContentRecommendationOption] = Field(default_factory=list)
    selectable_content_types: list[LearningContentType] = Field(default_factory=list)
    available_content_types: list[LearningContentType] = Field(default_factory=list)
    recommended_content_types: list[LearningContentType] = Field(default_factory=list)
    not_recommended_content_types: list[LearningContentType] = Field(default_factory=list)
    reason: str
    learning_task_strategy: LearningTaskStrategyProfile
    material_readiness: MaterialReadinessReport


def _clean_unique_values(
    values: list[str],
    *,
    field_name: str,
    max_item_length: int,
    allow_empty: bool = False,
) -> list[str]:
    cleaned = [value.strip() for value in values]
    if not allow_empty and any(not value for value in cleaned):
        raise ValueError(f"{field_name} must not include empty values")
    if any(len(value) > max_item_length for value in cleaned):
        raise ValueError(f"each {field_name} item must be {max_item_length} characters or fewer")
    non_empty_values = [value for value in cleaned if value]
    if len(set(non_empty_values)) != len(non_empty_values):
        raise ValueError(f"{field_name} must be unique")
    return cleaned
