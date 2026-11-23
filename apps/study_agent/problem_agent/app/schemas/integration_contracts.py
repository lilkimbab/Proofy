from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field, model_validator

from app.schemas.problems import (
    AnswerInput,
    BloomLevel,
    Choice,
    ChoiceDiagnosticSpec,
    ChoiceFeedbackDiagnostic,
    Difficulty,
    DifficultyProfile,
    ItemDesignBrief,
    LearningState,
    MistakeType,
    ProblemType,
    ProfessorGradeItemScore,
    RubricItem,
    ShortAnswerEvaluationDetails,
    SourceRef,
    StudentResponseSimulationReport,
    TeacherReviewChecklist,
)


class RetrievedChunk(BaseModel):
    chunk_id: str = Field(min_length=1)
    document_id: str = Field(min_length=1)
    content: str = Field(min_length=1)
    page: int | None = None
    section_title: str | None = None
    concepts: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)


class GeneratedArtifactType(StrEnum):
    problem = "problem"
    assessment_report = "assessment_report"
    feedback = "feedback"
    learning_content = "learning_content"
    learning_signal = "learning_signal"


class GeneratedArtifactVisibility(StrEnum):
    private = "private"
    hidden_until_submission = "hidden_until_submission"


class GeneratedArtifactIndexPayload(BaseModel):
    artifact_id: str = Field(min_length=1, max_length=128)
    artifact_type: GeneratedArtifactType
    user_id: str = Field(min_length=1, max_length=128)
    document_id: str = Field(min_length=1, max_length=128)
    content: str = Field(min_length=1, max_length=12000)
    metadata: dict = Field(default_factory=dict)
    source_chunk_ids: list[str] = Field(default_factory=list)
    visibility: GeneratedArtifactVisibility = GeneratedArtifactVisibility.private
    created_at: datetime | None = None

    @model_validator(mode="after")
    def validate_generated_artifact(self) -> GeneratedArtifactIndexPayload:
        if any(not chunk_id.strip() for chunk_id in self.source_chunk_ids):
            raise ValueError("source_chunk_ids must not include empty values")
        if len(set(self.source_chunk_ids)) != len(self.source_chunk_ids):
            raise ValueError("source_chunk_ids must be unique")
        if self.artifact_type == GeneratedArtifactType.problem:
            if self.visibility != GeneratedArtifactVisibility.hidden_until_submission:
                raise ValueError("problem artifacts must use hidden_until_submission visibility")
        if self.artifact_type == GeneratedArtifactType.assessment_report:
            if self.visibility != GeneratedArtifactVisibility.private:
                raise ValueError("assessment_report artifacts must use private visibility")
        if self.artifact_type == GeneratedArtifactType.feedback:
            if self.visibility != GeneratedArtifactVisibility.private:
                raise ValueError("feedback artifacts must use private visibility")
        if self.artifact_type == GeneratedArtifactType.learning_content:
            if self.visibility != GeneratedArtifactVisibility.private:
                raise ValueError("learning_content artifacts must use private visibility")
        if self.artifact_type == GeneratedArtifactType.learning_signal:
            if self.visibility != GeneratedArtifactVisibility.private:
                raise ValueError("learning_signal artifacts must use private visibility")
        return self


class SearchChunksRequest(BaseModel):
    document_id: str = Field(min_length=1)
    concepts: list[str] = Field(min_length=1)
    difficulty: Difficulty
    query: str = Field(min_length=1)
    top_k: int = Field(default=6, ge=1, le=20)


class ChunkBatchRequest(BaseModel):
    document_id: str = Field(min_length=1)
    chunk_ids: list[str] = Field(min_length=1)


class ProblemStoragePayload(BaseModel):
    user_id: str = Field(min_length=1)
    document_id: str = Field(min_length=1)
    type: ProblemType
    difficulty: Difficulty
    bloom_level: BloomLevel
    question: str = Field(min_length=1)
    choices: list[Choice] | None = None
    answer: dict
    explanation: str = Field(min_length=1)
    choice_explanations: dict[str, str] | None = None
    choice_diagnostics: list[ChoiceDiagnosticSpec] | None = None
    rubric: list[RubricItem] | None = None
    concepts: list[str] = Field(min_length=1)
    source_chunk_ids: list[str] = Field(min_length=1)
    source_refs: list[SourceRef] | None = None
    source_grounding_notes: list[str] = Field(default_factory=list)
    source_evidence_snapshot: list[RetrievedChunk] | None = None
    item_model_id: str | None = Field(default=None, max_length=80)
    item_design_brief: ItemDesignBrief | None = None
    difficulty_profile: DifficultyProfile | None = None
    teacher_review_checklist: TeacherReviewChecklist | None = None
    professor_grade_score: ProfessorGradeItemScore | None = None
    student_response_simulation: StudentResponseSimulationReport | None = None
    quality_status: str = "passed"

    @model_validator(mode="after")
    def validate_problem_shape(self) -> ProblemStoragePayload:
        if any(not concept.strip() for concept in self.concepts):
            raise ValueError("concepts must not include empty values")
        if any(not chunk_id.strip() for chunk_id in self.source_chunk_ids):
            raise ValueError("source_chunk_ids must not include empty values")
        if len(set(self.source_chunk_ids)) != len(self.source_chunk_ids):
            raise ValueError("source_chunk_ids must be unique")
        if self.source_evidence_snapshot is not None:
            snapshot_ids = [chunk.chunk_id for chunk in self.source_evidence_snapshot]
            if len(set(snapshot_ids)) != len(snapshot_ids):
                raise ValueError("source_evidence_snapshot chunk_ids must be unique")
            if snapshot_ids != self.source_chunk_ids:
                raise ValueError("source_evidence_snapshot must cover source_chunk_ids in order")
            mismatched_document_ids = [
                chunk.chunk_id for chunk in self.source_evidence_snapshot if chunk.document_id != self.document_id
            ]
            if mismatched_document_ids:
                raise ValueError("source_evidence_snapshot document_id must match problem document_id")
        if self.source_refs is not None:
            ref_ids = [ref.chunk_id for ref in self.source_refs]
            if len(set(ref_ids)) != len(ref_ids):
                raise ValueError("source_refs chunk_ids must be unique")
            if ref_ids != self.source_chunk_ids:
                raise ValueError("source_refs must cover source_chunk_ids in order")
            mismatched_ref_document_ids = [ref.chunk_id for ref in self.source_refs if ref.document_id != self.document_id]
            if mismatched_ref_document_ids:
                raise ValueError("source_refs document_id must match problem document_id")
        if self.type == ProblemType.multiple_choice:
            if not self.choices or len(self.choices) != 4:
                raise ValueError("multiple_choice problem requires exactly 4 choices")
            choice_ids = [choice.id for choice in self.choices]
            choice_texts = [choice.text.strip() for choice in self.choices]
            if len(set(choice_ids)) != len(choice_ids):
                raise ValueError("multiple_choice choices must have unique ids")
            if len(set(choice_texts)) != len(choice_texts):
                raise ValueError("multiple_choice choices must have unique texts")
            if self.answer.get("choice_id") not in choice_ids:
                raise ValueError("answer.choice_id must exist in choices")
            if not self.answer.get("text"):
                raise ValueError("multiple_choice problem requires answer.text")
            choice_text_by_id = {choice.id: choice.text for choice in self.choices}
            if self.answer.get("text") != choice_text_by_id.get(self.answer.get("choice_id")):
                raise ValueError("answer.text must match the selected choice text")
            if not self.choice_explanations:
                raise ValueError("multiple_choice problem requires choice_explanations")
            missing_explanations = set(choice_ids) - set(self.choice_explanations)
            if missing_explanations:
                raise ValueError("choice_explanations must cover every choice id")
            extra_explanations = set(self.choice_explanations) - set(choice_ids)
            if extra_explanations:
                raise ValueError("choice_explanations must not include unknown choice ids")
            if self.rubric is not None:
                raise ValueError("multiple_choice problem must use rubric=null")
            if self.choice_diagnostics is not None:
                diagnostic_ids = [diagnostic.choice_id for diagnostic in self.choice_diagnostics]
                if set(diagnostic_ids) != set(choice_ids):
                    raise ValueError("choice_diagnostics must cover every choice id")
                correct_diagnostics = [diagnostic for diagnostic in self.choice_diagnostics if diagnostic.is_correct]
                if len(correct_diagnostics) != 1 or correct_diagnostics[0].choice_id != self.answer.get("choice_id"):
                    raise ValueError("choice_diagnostics must mark exactly the answer choice as correct")
        if self.type == ProblemType.short_answer:
            if self.choices is not None:
                raise ValueError("short_answer problem must use choices=null")
            if self.choice_explanations is not None:
                raise ValueError("short_answer problem must use choice_explanations=null")
            if self.answer.get("choice_id") is not None:
                raise ValueError("short_answer problem must use answer.choice_id=null")
            if not self.answer.get("text"):
                raise ValueError("short_answer problem requires answer.text")
            if not self.rubric:
                raise ValueError("short_answer problem requires rubric")
            if self.choice_diagnostics is not None:
                raise ValueError("short_answer problem must use choice_diagnostics=null")
        return self


class SubmissionStoragePayload(BaseModel):
    problem_id: str = Field(min_length=1)
    user_id: str = Field(min_length=1)
    answer: dict
    solution_steps: str | None = None
    elapsed_time_sec: float | None = Field(default=None, ge=0, le=86400)
    hint_count: int = Field(default=0, ge=0, le=100)
    confidence_level: int | None = Field(default=None, ge=1, le=4)

    @model_validator(mode="after")
    def validate_answer(self) -> SubmissionStoragePayload:
        answer = AnswerInput.model_validate(self.answer)
        self.answer = answer.model_dump(mode="json", exclude_none=True)
        return self


class FeedbackStoragePayload(BaseModel):
    submission_id: str = Field(min_length=1)
    problem_id: str = Field(min_length=1)
    user_id: str = Field(min_length=1)
    is_correct: bool
    score: float = Field(ge=0)
    max_score: float = Field(gt=0)
    mistake_type: MistakeType | None = None
    weak_concepts: list[str] = Field(default_factory=list)
    summary: str = Field(min_length=1)
    feedback: str = Field(min_length=1)
    recommended_review: list[str] = Field(default_factory=list)
    source_chunk_ids: list[str] = Field(min_length=1)
    evaluation_details: ShortAnswerEvaluationDetails | None = None
    learning_state: LearningState = LearningState.unreported

    @model_validator(mode="after")
    def validate_score(self) -> FeedbackStoragePayload:
        if self.score > self.max_score:
            raise ValueError("score cannot exceed max_score")
        if self.is_correct and self.score != self.max_score:
            raise ValueError("correct feedback score must equal max_score")
        if not self.is_correct and self.score == self.max_score:
            raise ValueError("full-score feedback must be marked correct")
        if self.is_correct and self.mistake_type not in (None, MistakeType.none):
            raise ValueError("correct feedback must use mistake_type=none")
        if not self.is_correct and self.mistake_type == MistakeType.none:
            raise ValueError("incorrect feedback must include a concrete mistake_type")
        return self


class ConceptMasteryUpdatePayload(BaseModel):
    concept: str = Field(min_length=1)
    attempts: int = Field(ge=0)
    correct_count: int = Field(ge=0)
    wrong_count: int = Field(ge=0)
    mastery: float = Field(ge=0, le=1)
    mistake_types: list[str] = Field(default_factory=list)
    should_review: bool = False
    last_attempt_at: datetime | None = None


class UserConceptUpdatePayload(BaseModel):
    user_id: str = Field(min_length=1)
    problem_id: str = Field(min_length=1)
    submission_id: str = Field(min_length=1)
    feedback_id: str = Field(min_length=1)
    concepts: list[str] = Field(min_length=1)
    is_correct: bool
    score: float = Field(ge=0)
    max_score: float = Field(gt=0)
    mistake_type: MistakeType | None = None
    weak_concepts: list[str] = Field(default_factory=list)
    recommended_review: list[str] = Field(default_factory=list)
    mastery_updates: list[ConceptMasteryUpdatePayload] = Field(default_factory=list)
    learning_state: LearningState = LearningState.unreported

    @model_validator(mode="after")
    def validate_score(self) -> UserConceptUpdatePayload:
        if self.score > self.max_score:
            raise ValueError("score cannot exceed max_score")
        if self.is_correct and self.score != self.max_score:
            raise ValueError("correct update score must equal max_score")
        if not self.is_correct and self.score == self.max_score:
            raise ValueError("full-score update must be marked correct")
        if self.is_correct and self.mistake_type not in (None, MistakeType.none):
            raise ValueError("correct update must use mistake_type=none")
        if not self.is_correct and self.mistake_type == MistakeType.none:
            raise ValueError("incorrect update must include a concrete mistake_type")
        return self


class UserConceptStatUpdateResult(BaseModel):
    recommended_review: list[str] = Field(default_factory=list)
    mastery_updates: list[ConceptMasteryUpdatePayload] = Field(default_factory=list)


class MistakeRemediationEventPayload(BaseModel):
    user_id: str = Field(min_length=1)
    source_feedback_id: str = Field(min_length=1)
    source_problem_id: str = Field(min_length=1)
    followup_problem_id: str = Field(min_length=1)
    followup_content_id: str | None = None
    target_concepts: list[str] = Field(min_length=1)
    target_mistake_type: MistakeType | None = None

    @model_validator(mode="after")
    def validate_target(self) -> MistakeRemediationEventPayload:
        cleaned = [concept.strip() for concept in self.target_concepts if concept and concept.strip()]
        if not cleaned:
            raise ValueError("target_concepts must not be empty")
        self.target_concepts = list(dict.fromkeys(cleaned))
        if self.target_mistake_type == MistakeType.none:
            raise ValueError("target_mistake_type must be concrete when provided")
        return self


class ProblemItemAttemptPayload(BaseModel):
    user_id: str = Field(min_length=1)
    problem_id: str = Field(min_length=1)
    document_id: str = Field(min_length=1)
    submission_id: str = Field(min_length=1)
    feedback_id: str = Field(min_length=1)
    problem_type: ProblemType
    is_correct: bool
    score: float = Field(ge=0)
    max_score: float = Field(gt=0)
    elapsed_time_sec: float | None = Field(default=None, ge=0, le=86400)
    hint_count: int = Field(default=0, ge=0, le=100)
    selected_choice_id: str | None = Field(default=None, max_length=32)
    mistake_type: MistakeType | None = None
    choice_diagnostic: ChoiceFeedbackDiagnostic | None = None

    @model_validator(mode="after")
    def validate_attempt(self) -> ProblemItemAttemptPayload:
        if self.score > self.max_score:
            raise ValueError("score cannot exceed max_score")
        if self.problem_type == ProblemType.multiple_choice and not self.selected_choice_id:
            raise ValueError("multiple_choice item attempt requires selected_choice_id")
        if self.problem_type != ProblemType.multiple_choice and self.choice_diagnostic is not None:
            raise ValueError("choice_diagnostic is only valid for multiple_choice item attempts")
        if self.is_correct and self.mistake_type not in (None, MistakeType.none):
            raise ValueError("correct item attempt must use mistake_type=none")
        if not self.is_correct and self.mistake_type == MistakeType.none:
            raise ValueError("incorrect item attempt must include a concrete mistake_type")
        return self


class ProblemItemStatPayload(BaseModel):
    problem_id: str = Field(min_length=1)
    document_id: str = Field(min_length=1)
    problem_type: ProblemType
    total_attempts: int = Field(default=0, ge=0)
    correct_count: int = Field(default=0, ge=0)
    incorrect_count: int = Field(default=0, ge=0)
    correct_rate: float = Field(default=0, ge=0, le=1)
    correct_rate_smoothed: float = Field(default=0.5, ge=0, le=1)
    average_score: float = Field(default=0, ge=0)
    max_score: float = Field(default=1, gt=0)
    discrimination_proxy: float | None = Field(default=None, ge=-1, le=1)
    sample_size_status: str = Field(default="insufficient")
    statistics_confidence: str = Field(default="low")
    statistics_note: str = Field(default="통계가 아직 적어서 참고용으로만 봅니다.", min_length=1)
    quality_score_for_review: float | None = Field(default=None, ge=0, le=1)
    quality_score_source: str = Field(default="item_quality", min_length=1)
    timed_attempt_count: int = Field(default=0, ge=0)
    average_time_sec: float | None = Field(default=None, ge=0)
    hint_usage_count: int = Field(default=0, ge=0)
    hint_usage_rate: float = Field(default=0, ge=0, le=1)
    choice_selection_counts: dict[str, int] = Field(default_factory=dict)
    choice_selection_distribution: dict[str, float] = Field(default_factory=dict)
    choice_mistake_type_counts: dict[str, dict[str, int]] = Field(default_factory=dict)
    non_functioning_distractors: list[str] = Field(default_factory=list)
    mistake_type_counts: dict[str, int] = Field(default_factory=dict)
    common_mistake_types: list[str] = Field(default_factory=list)
    missed_rubric_criteria_counts: dict[str, int] = Field(default_factory=dict)
    common_missed_rubric_criteria: list[str] = Field(default_factory=list)
    needs_review: bool = False
    review_reasons: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_item_statistics(self) -> ProblemItemStatPayload:
        if self.correct_count + self.incorrect_count > self.total_attempts:
            raise ValueError("correct_count + incorrect_count cannot exceed total_attempts")
        if self.average_score > self.max_score:
            raise ValueError("average_score cannot exceed max_score")
        expected_rate = round(self.correct_count / self.total_attempts, 3) if self.total_attempts else 0
        if self.correct_rate and abs(self.correct_rate - expected_rate) > 0.001:
            raise ValueError("correct_rate must equal correct_count / total_attempts")
        if self.sample_size_status not in {"insufficient", "warming_up", "reliable"}:
            raise ValueError("sample_size_status must be insufficient, warming_up, or reliable")
        if self.statistics_confidence not in {"low", "medium", "high"}:
            raise ValueError("statistics_confidence must be low, medium, or high")
        if any(count < 0 for count in self.choice_selection_counts.values()):
            raise ValueError("choice_selection_counts cannot include negative counts")
        if any(value < 0 or value > 1 for value in self.choice_selection_distribution.values()):
            raise ValueError("choice_selection_distribution values must be between 0 and 1")
        for choice_id, mistake_counts in self.choice_mistake_type_counts.items():
            if not choice_id.strip():
                raise ValueError("choice_mistake_type_counts cannot include empty choice ids")
            if any(count < 0 for count in mistake_counts.values()):
                raise ValueError("choice_mistake_type_counts cannot include negative counts")
        if any(count < 0 for count in self.mistake_type_counts.values()):
            raise ValueError("mistake_type_counts cannot include negative counts")
        if any(count < 0 for count in self.missed_rubric_criteria_counts.values()):
            raise ValueError("missed_rubric_criteria_counts cannot include negative counts")
        return self
