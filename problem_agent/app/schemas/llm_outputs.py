from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.learning_contents import LearningContentBase, LearningContentType
from app.schemas.problems import BloomLevel, Difficulty, MistakeType, ProblemType, RubricCriterionResult


class GeneratedChoice(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    text: str = Field(min_length=1)


class GeneratedAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid")

    choice_id: str | None
    text: str = Field(min_length=1)


class GeneratedRubricItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    criterion: str = Field(min_length=1)
    points: float = Field(gt=0)
    expected_evidence: list[str] = Field(default_factory=list)
    common_mistakes: list[str] = Field(default_factory=list)
    partial_credit_rules: list[str] = Field(default_factory=list)


class GeneratedMCQDistractorPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    misconception_id: str = Field(min_length=1)
    mistake_type: str = Field(min_length=1)
    why_plausible: str = Field(min_length=1)
    violated_or_ignored_evidence_role: str = Field(min_length=1)
    repair_strategy: str = Field(min_length=1)


class GeneratedMCQPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kernel_type: str = Field(min_length=1)
    source_rule_or_evidence: str = Field(min_length=1)
    concrete_scenario: str = Field(min_length=1)
    correct_answer_claim: str = Field(min_length=1)
    correct_answer_evidence_link: str = Field(min_length=1)
    distractor_plans: list[GeneratedMCQDistractorPlan] = Field(min_length=3, max_length=3)
    prohibited_patterns: list[str] = Field(default_factory=list)
    required_source_chunk_ids: list[str] = Field(default_factory=list)


class RawChoiceDiagnosticSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    choice_id: str = Field(min_length=1)
    is_correct: bool | None = None
    misconception_id: str | None = None
    mistake_type: str | None = None
    why_plausible: str | None = None
    repair_strategy: str | None = None
    followup_problem_type: str | None = None


class GeneratedProblem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_id: str = Field(min_length=1)
    type: ProblemType
    difficulty: Difficulty
    bloom_level: BloomLevel
    question: str = Field(min_length=1)
    choices: list[GeneratedChoice] | None
    answer: GeneratedAnswer
    explanation: str = Field(min_length=1)
    choice_explanations: dict[str, str] | None
    choice_diagnostics: list[RawChoiceDiagnosticSpec] | None = None
    rubric: list[GeneratedRubricItem] | None
    concepts: list[str] = Field(min_length=1)
    source_chunk_ids: list[str] = Field(min_length=1)
    mcq_plan: GeneratedMCQPlan | None = None

    @model_validator(mode="after")
    def validate_problem_shape(self) -> GeneratedProblem:
        if any(not concept.strip() for concept in self.concepts):
            raise ValueError("concepts must not include empty values")
        if any(not chunk_id.strip() for chunk_id in self.source_chunk_ids):
            raise ValueError("source_chunk_ids must not include empty values")
        if len(set(self.source_chunk_ids)) != len(self.source_chunk_ids):
            raise ValueError("source_chunk_ids must be unique")
        if self.type == ProblemType.multiple_choice:
            if self.choices is None or len(self.choices) != 4:
                raise ValueError("multiple_choice problem requires exactly 4 choices")
            choice_ids = [choice.id for choice in self.choices]
            choice_texts = [choice.text.strip() for choice in self.choices]
            if len(set(choice_ids)) != len(choice_ids):
                raise ValueError("multiple_choice choices must have unique ids")
            if len(set(choice_texts)) != len(choice_texts):
                raise ValueError("multiple_choice choices must have unique texts")
            if self.answer.choice_id not in choice_ids:
                raise ValueError("answer.choice_id must exist in choices")
            choice_text_by_id = {choice.id: choice.text for choice in self.choices}
            if self.answer.choice_id and self.answer.text != choice_text_by_id[self.answer.choice_id]:
                raise ValueError("answer.text must match the selected choice text")
            if self.choice_explanations is None:
                raise ValueError("multiple_choice problem requires choice_explanations")
            missing_explanations = set(choice_ids) - set(self.choice_explanations)
            if missing_explanations:
                raise ValueError("choice_explanations must cover every choice id")
            extra_explanations = set(self.choice_explanations) - set(choice_ids)
            if extra_explanations:
                raise ValueError("choice_explanations must not include unknown choice ids")
            if self.rubric is not None:
                raise ValueError("multiple_choice problem must use rubric=null")
        if self.type == ProblemType.short_answer:
            if self.choices is not None:
                raise ValueError("short_answer problem must use choices=null")
            if self.answer.choice_id is not None:
                raise ValueError("short_answer problem must use answer.choice_id=null")
            if self.choice_explanations is not None:
                raise ValueError("short_answer problem must use choice_explanations=null")
            if not self.rubric:
                raise ValueError("short_answer problem requires rubric")
            if self.choice_diagnostics is not None:
                raise ValueError("short_answer problem must use choice_diagnostics=null")

        return self


class ProblemGenerationOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    problems: list[GeneratedProblem] = Field(min_length=1, max_length=10)


class FeedbackGenerationOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    is_correct: bool
    score: float = Field(ge=0)
    max_score: float = Field(gt=0)
    mistake_type: MistakeType
    weak_concepts: list[str]
    summary: str = Field(min_length=1)
    feedback: str = Field(min_length=1)
    recommended_review: list[str]
    rubric_results: list[RubricCriterionResult] = Field(default_factory=list)
    confidence: Literal["low", "medium", "high"] = "medium"

    @model_validator(mode="after")
    def validate_feedback_score(self) -> FeedbackGenerationOutput:
        if self.score > self.max_score:
            raise ValueError("score cannot exceed max_score")
        if self.is_correct and self.score != self.max_score:
            raise ValueError("correct feedback score must equal max_score")
        if not self.is_correct and self.score == self.max_score:
            raise ValueError("full-score feedback must be marked correct")
        if self.is_correct and self.mistake_type != MistakeType.none:
            raise ValueError("correct feedback must use mistake_type=none")
        if not self.is_correct and self.mistake_type == MistakeType.none:
            raise ValueError("incorrect feedback must include a concrete mistake_type")
        return self


class GeneratedLearningContentCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_id: str = Field(min_length=1)
    content_type: LearningContentType
    difficulty: Difficulty
    bloom_level: BloomLevel
    concepts: list[str] = Field(min_length=1)
    source_chunk_ids: list[str] = Field(min_length=1)
    payload: dict[str, Any]

    @model_validator(mode="after")
    def validate_learning_content_candidate(self) -> GeneratedLearningContentCandidate:
        LearningContentBase(
            document_id=self.document_id,
            content_type=self.content_type,
            concepts=self.concepts,
            source_chunk_ids=self.source_chunk_ids,
            difficulty=self.difficulty,
            bloom_level=self.bloom_level,
            quality_status="passed",
            quality_report={"status": "passed", "score": 0.8, "source_grounded": True},
            payload=self.payload,
        )
        return self


class LearningContentGenerationOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contents: list[GeneratedLearningContentCandidate] = Field(min_length=1, max_length=10)
