from __future__ import annotations

from datetime import datetime
from enum import IntEnum, StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.learning_voice import FeedbackCopyOutput
from app.schemas.problem_kernels import ContentAtom, EvidenceLink, ProblemKernelPlan
from app.schemas.quality import (
    AssessmentBlueprint,
    AssessmentSessionReadinessReport,
    CourseLevel,
    GenerationGoal,
    GenerationQualitySummary,
    HighRigorGenerationProfile,
    LearningTaskStrategyProfile,
    MaterialReadinessReport,
    QualityMode,
    TargetRigor,
)


class ProblemType(StrEnum):
    multiple_choice = "multiple_choice"
    short_answer = "short_answer"


class Difficulty(StrEnum):
    easy = "easy"
    medium = "medium"
    hard = "hard"


class BloomLevel(StrEnum):
    remember = "remember"
    understand = "understand"
    apply = "apply"
    analyze = "analyze"
    evaluate = "evaluate"
    create = "create"


class MistakeType(StrEnum):
    none = "none"
    concept_misunderstanding = "concept_misunderstanding"
    missing_key_concept = "missing_key_concept"
    term_confusion = "term_confusion"
    calculation_error = "calculation_error"
    logic_error = "logic_error"
    misread_question = "misread_question"
    incomplete_answer = "incomplete_answer"
    unit_error = "unit_error"
    missing_condition = "missing_condition"
    wrong_rule_selected = "wrong_rule_selected"
    rule_overgeneralization = "rule_overgeneralization"
    evidence_mismatch = "evidence_mismatch"
    calculation_or_derivation_error = "calculation_or_derivation_error"
    procedure_order_error = "procedure_order_error"
    classification_boundary_error = "classification_boundary_error"
    comparison_conflation = "comparison_conflation"
    unsupported_claim = "unsupported_claim"
    incomplete_explanation = "incomplete_explanation"
    irrelevant_answer = "irrelevant_answer"


class AnswerInputMode(StrEnum):
    typed = "typed"
    tablet_ocr = "tablet_ocr"


class AssessmentSessionStatus(StrEnum):
    generated = "generated"
    in_progress = "in_progress"
    submitted = "submitted"


class ProblemDepth(StrEnum):
    standard = "standard"
    deep = "deep"


class ProblemStyle(StrEnum):
    auto = "auto"
    concept_check = "concept_check"
    exam_application = "exam_application"
    calculation_practice = "calculation_practice"
    misconception_drill = "misconception_drill"
    evidence_analysis = "evidence_analysis"
    error_detection = "error_detection"
    trace_and_explain = "trace_and_explain"
    condition_mutation = "condition_mutation"
    concept_comparison = "concept_comparison"
    concept_boundary = "concept_boundary"
    design_under_constraint = "design_under_constraint"


class SampleSizeStatus(StrEnum):
    insufficient = "insufficient"
    warming_up = "warming_up"
    reliable = "reliable"


class StatisticsConfidence(StrEnum):
    low = "low"
    medium = "medium"
    high = "high"


class LearningState(StrEnum):
    unreported = "unreported"
    secure_mastery = "secure_mastery"
    fragile_mastery = "fragile_mastery"
    high_confidence_misconception = "high_confidence_misconception"
    knowledge_gap = "knowledge_gap"
    partial_understanding = "partial_understanding"


class FeedbackActionEventType(StrEnum):
    next_action_clicked = "next_action_clicked"
    retry_completed = "retry_completed"
    followup_problem_completed = "followup_problem_completed"
    helpful_rating = "helpful_rating"


class FeedbackActionType(StrEnum):
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


class FollowupProblemType(StrEnum):
    concept_review = "concept_review"
    similar_case = "similar_case"
    condition_change = "condition_change"
    error_diagnosis = "error_diagnosis"
    calculation_drill = "calculation_drill"
    evidence_check = "evidence_check"
    trace_process = "trace_process"
    comparison_drill = "comparison_drill"
    source_review = "source_review"


FOLLOWUP_PROBLEM_TYPE_SLUGS: tuple[str, ...] = tuple(item.value for item in FollowupProblemType)

_FOLLOWUP_PROBLEM_TYPE_ALIASES: dict[str, str] = {
    "concept_check": FollowupProblemType.concept_review.value,
    "concept_boundary": FollowupProblemType.comparison_drill.value,
    "concept_review": FollowupProblemType.concept_review.value,
    "definition": FollowupProblemType.concept_review.value,
    "worked_example_completion": FollowupProblemType.trace_process.value,
    "transfer_problem": FollowupProblemType.calculation_drill.value,
    "formula_reasoning": FollowupProblemType.calculation_drill.value,
    "calculation_practice": FollowupProblemType.calculation_drill.value,
    "calculation_drill": FollowupProblemType.calculation_drill.value,
    "condition_mutation": FollowupProblemType.condition_change.value,
    "condition_check": FollowupProblemType.condition_change.value,
    "condition_application": FollowupProblemType.condition_change.value,
    "condition_change": FollowupProblemType.condition_change.value,
    "error_detection": FollowupProblemType.error_diagnosis.value,
    "error_diagnosis": FollowupProblemType.error_diagnosis.value,
    "evidence_selection": FollowupProblemType.evidence_check.value,
    "evidence_analysis": FollowupProblemType.evidence_check.value,
    "evidence_alignment": FollowupProblemType.evidence_check.value,
    "evidence_check": FollowupProblemType.evidence_check.value,
    "trace_and_explain": FollowupProblemType.trace_process.value,
    "trace_process": FollowupProblemType.trace_process.value,
    "range_query_boundary": FollowupProblemType.comparison_drill.value,
    "concept_comparison": FollowupProblemType.comparison_drill.value,
    "misconception_contrast": FollowupProblemType.comparison_drill.value,
    "comparison_judgment": FollowupProblemType.comparison_drill.value,
    "matching": FollowupProblemType.comparison_drill.value,
    "comparison_drill": FollowupProblemType.comparison_drill.value,
    "source_review": FollowupProblemType.source_review.value,
    "similar_case": FollowupProblemType.similar_case.value,
}


def normalize_followup_problem_type(value: object) -> str | None:
    if value is None:
        return None
    raw = str(value).strip()
    if not raw:
        return None
    normalized = raw.lower().replace("-", "_")
    normalized = "_".join(normalized.split())
    if normalized in _FOLLOWUP_PROBLEM_TYPE_ALIASES:
        return _FOLLOWUP_PROBLEM_TYPE_ALIASES[normalized]
    for alias, slug in _FOLLOWUP_PROBLEM_TYPE_ALIASES.items():
        if alias in normalized:
            return slug
    keyword_rules: tuple[tuple[tuple[str, ...], str], ...] = (
        (("계산", "공식", "수식", "대입", "formula", "calculation", "compute"), FollowupProblemType.calculation_drill.value),
        (("근거", "증거", "evidence", "citation", "grounding"), FollowupProblemType.evidence_check.value),
        (("조건", "변화", "condition", "mutation", "change"), FollowupProblemType.condition_change.value),
        (("오류", "진단", "틀린", "error", "diagnos"), FollowupProblemType.error_diagnosis.value),
        (("추적", "절차", "단계", "순서", "trace", "process", "step"), FollowupProblemType.trace_process.value),
        (("비교", "구분", "차이", "경계", "compare", "comparison", "boundary"), FollowupProblemType.comparison_drill.value),
        (("자료", "source", "review", "복습"), FollowupProblemType.source_review.value),
        (("사례", "case", "similar"), FollowupProblemType.similar_case.value),
        (("개념", "정의", "concept", "definition"), FollowupProblemType.concept_review.value),
    )
    for cues, slug in keyword_rules:
        if any(cue in normalized for cue in cues):
            return slug
    allowed = ", ".join(FOLLOWUP_PROBLEM_TYPE_SLUGS)
    raise ValueError(f"followup_problem_type must be one of: {allowed}")


class RegenerationCandidateStatus(StrEnum):
    open = "open"
    queued = "queued"
    resolved = "resolved"
    dismissed = "dismissed"


class QualityReportTargetType(StrEnum):
    problem = "problem"
    feedback = "feedback"
    learning_content = "learning_content"


class QualityReportReason(StrEnum):
    too_easy = "too_easy"
    too_hard = "too_hard"
    not_grounded = "not_grounded"
    answer_wrong = "answer_wrong"
    explanation_unclear = "explanation_unclear"
    tone_awkward = "tone_awkward"
    grading_unfair = "grading_unfair"
    copyright_concern = "copyright_concern"
    other = "other"


class QualityReportStatus(StrEnum):
    open = "open"
    reviewed = "reviewed"
    resolved = "resolved"


class HintMode(StrEnum):
    practice = "practice"
    exam = "exam"


class HintLevel(IntEnum):
    restate_question = 0
    recall_concept = 1
    first_step_question = 2
    partial_example = 3
    solution_structure = 4
    error_check = 5
    full_solution = 6


class CognitiveLevel(StrEnum):
    recall = "recall"
    understand = "understand"
    apply = "apply"
    analyze = "analyze"
    evaluate = "evaluate"
    create = "create"


class ItemModelId(StrEnum):
    definition_with_boundary = "definition_with_boundary"
    concept_comparison = "concept_comparison"
    procedure_with_missing_step = "procedure_with_missing_step"
    error_detection = "error_detection"
    case_based_application = "case_based_application"
    data_interpretation = "data_interpretation"
    transfer_to_new_context = "transfer_to_new_context"
    misconception_contrast = "misconception_contrast"
    worked_example_completion = "worked_example_completion"
    evidence_selection = "evidence_selection"


class TeacherReviewDecision(StrEnum):
    approved = "approved"
    needs_revision = "needs_revision"
    rejected = "rejected"


class SourceRef(BaseModel):
    document_id: str = Field(min_length=1, max_length=128)
    chunk_id: str = Field(min_length=1, max_length=128)
    page: int | None = None
    section_title: str | None = Field(default=None, max_length=255)


class DifficultyProfile(BaseModel):
    difficulty: Difficulty
    cognitive_level: CognitiveLevel
    reasoning_steps_required: int = Field(ge=1, le=12)
    prerequisite_count: int = Field(default=0, ge=0, le=12)
    cognitive_demand_score: float = Field(ge=0, le=1)
    requires_transfer: bool = False
    requires_calculation: bool = False
    requires_comparison: bool = False
    requires_error_analysis: bool = False


class ItemModel(BaseModel):
    id: ItemModelId
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(min_length=1, max_length=500)
    supported_problem_types: list[ProblemType] = Field(min_length=1)
    recommended_cognitive_levels: list[CognitiveLevel] = Field(default_factory=list)
    required_evidence_types: list[str] = Field(default_factory=list, max_length=12)
    disallowed_patterns: list[str] = Field(default_factory=list, max_length=12)
    minimum_reasoning_steps: int = Field(default=1, ge=1, le=12)
    preferred_feedback_strategy: str | None = Field(default=None, max_length=500)


class ItemDesignBrief(BaseModel):
    target_concept: str = Field(min_length=1, max_length=120)
    prerequisite_concepts: list[str] = Field(default_factory=list, max_length=12)
    learning_objective: str = Field(min_length=1, max_length=500)
    cognitive_level: CognitiveLevel
    assessment_claim: str = Field(min_length=1, max_length=700)
    observable_evidence: list[str] = Field(min_length=1, max_length=12)
    expected_reasoning_steps: list[str] = Field(min_length=1, max_length=12)
    common_misconceptions: list[str] = Field(default_factory=list, max_length=12)
    target_misconception: str | None = Field(default=None, max_length=500)
    item_type: ProblemType
    difficulty: Difficulty
    context_strategy: str = Field(min_length=1, max_length=500)
    scoring_strategy: str = Field(min_length=1, max_length=500)
    content_atoms: list[ContentAtom] = Field(default_factory=list, max_length=20)
    problem_kernel_plan: ProblemKernelPlan | None = None
    evidence_links: list[EvidenceLink] = Field(default_factory=list, max_length=12)
    mcq_plan: dict[str, Any] | None = None


class TeacherReviewChecklist(BaseModel):
    learning_objective_clear: bool
    observable_evidence_clear: bool
    source_grounded: bool
    answer_unambiguous: bool
    no_hidden_answer_clue: bool
    no_unnecessary_trick: bool
    distractors_plausible: bool | None = None
    distractors_diagnostic: bool | None = None
    rubric_observable: bool | None = None
    difficulty_appropriate: bool
    cognitive_level_appropriate: bool
    fair_and_accessible: bool
    reviewer_notes: list[str] = Field(default_factory=list, max_length=20)
    required_revisions: list[str] = Field(default_factory=list, max_length=20)
    decision: TeacherReviewDecision


class ProfessorGradeItemScore(BaseModel):
    objective_alignment: float = Field(ge=0, le=1)
    source_grounding: float = Field(ge=0, le=1)
    cognitive_demand: float = Field(ge=0, le=1)
    misconception_diagnosticity: float = Field(ge=0, le=1)
    answer_clarity: float = Field(ge=0, le=1)
    distractor_quality: float = Field(ge=0, le=1)
    rubric_quality: float = Field(ge=0, le=1)
    fairness_accessibility: float = Field(ge=0, le=1)
    leakage_resistance: float = Field(ge=0, le=1)
    remediation_value: float = Field(ge=0, le=1)
    final_score: float = Field(ge=0, le=1)
    reject_reasons: list[str] = Field(default_factory=list, max_length=20)
    structural_score: float = Field(default=0.0, ge=0, le=1)
    pedagogical_score: float = Field(default=0.0, ge=0, le=1)
    grounding_score: float = Field(default=0.0, ge=0, le=1)
    assessment_design_score: float = Field(default=0.0, ge=0, le=1)
    calibration_notes: list[str] = Field(default_factory=list, max_length=20)


class SimulatedResponseKind(StrEnum):
    full_correct = "full_correct"
    partial_correct = "partial_correct"
    misconception = "misconception"
    condition_missing = "condition_missing"


class SimulatedResponseResult(BaseModel):
    kind: SimulatedResponseKind
    answer_summary: str = Field(min_length=1, max_length=1200)
    expected_score_ratio: float = Field(ge=0, le=1)
    observed_score_ratio: float = Field(ge=0, le=1)
    matched_rubric_indices: list[int] = Field(default_factory=list, max_length=20)
    unmatched_rubric_indices: list[int] = Field(default_factory=list, max_length=20)
    passed: bool
    notes: list[str] = Field(default_factory=list, max_length=10)


class StudentResponseSimulationReport(BaseModel):
    cases: list[SimulatedResponseResult] = Field(min_length=1, max_length=8)
    passed: bool
    flags: list[str] = Field(default_factory=list, max_length=20)


class Choice(BaseModel):
    id: str = Field(min_length=1, max_length=32)
    text: str = Field(min_length=1, max_length=500)


class RubricItem(BaseModel):
    criterion: str = Field(min_length=1, max_length=500)
    points: float = Field(gt=0)
    expected_evidence: list[str] = Field(default_factory=list, max_length=10)
    common_mistakes: list[str] = Field(default_factory=list, max_length=10)
    partial_credit_rules: list[str] = Field(default_factory=list, max_length=10)


class RubricCriterionResult(BaseModel):
    criterion: str = Field(min_length=1, max_length=500)
    max_points: float = Field(gt=0)
    awarded_points: float = Field(ge=0)
    matched: bool
    evidence_from_answer: str | None = Field(default=None, max_length=1200)
    missing_point: str | None = Field(default=None, max_length=1200)
    next_action: str | None = Field(default=None, max_length=1200)
    confidence: Literal["low", "medium", "high"] = "medium"

    @model_validator(mode="after")
    def validate_awarded_points(self) -> RubricCriterionResult:
        if self.awarded_points > self.max_points:
            raise ValueError("awarded_points cannot exceed max_points")
        if self.matched and self.awarded_points <= 0:
            raise ValueError("matched rubric result must award points")
        if not self.matched and self.awarded_points == self.max_points:
            raise ValueError("unmatched rubric result cannot award full points")
        return self


class ShortAnswerEvaluationDetails(BaseModel):
    confidence: Literal["low", "medium", "high"] = "medium"
    confidence_reasons: list[str] = Field(default_factory=list, max_length=10)
    needs_grading_review: bool = False
    grading_review_reasons: list[str] = Field(default_factory=list, max_length=10)
    rubric_results: list[RubricCriterionResult] = Field(default_factory=list)


class ChoiceDiagnosticSpec(BaseModel):
    choice_id: str = Field(min_length=1, max_length=32)
    is_correct: bool
    misconception_id: str | None = Field(default=None, max_length=128)
    mistake_type: MistakeType
    why_plausible: str | None = Field(default=None, max_length=1200)
    repair_strategy: str | None = Field(default=None, max_length=1200)
    followup_problem_type: str | None = Field(default=None, max_length=80)

    @field_validator("followup_problem_type", mode="before")
    @classmethod
    def normalize_followup_problem_type_value(cls, value: object) -> str | None:
        return normalize_followup_problem_type(value)

    @model_validator(mode="after")
    def validate_choice_diagnostic(self) -> ChoiceDiagnosticSpec:
        if self.is_correct:
            if self.mistake_type != MistakeType.none:
                raise ValueError("correct choice diagnostic must use mistake_type=none")
            return self
        if self.mistake_type == MistakeType.none:
            raise ValueError("incorrect choice diagnostic must include a concrete mistake_type")
        if not self.misconception_id and not self.mistake_type:
            raise ValueError("incorrect choice diagnostic requires misconception_id or mistake_type")
        if not self.why_plausible or not self.why_plausible.strip():
            raise ValueError("incorrect choice diagnostic requires why_plausible")
        if not self.repair_strategy or not self.repair_strategy.strip():
            raise ValueError("incorrect choice diagnostic requires repair_strategy")
        if not self.followup_problem_type or not self.followup_problem_type.strip():
            raise ValueError("incorrect choice diagnostic requires followup_problem_type")
        return self


class ChoiceFeedbackDiagnostic(BaseModel):
    selected_choice_id: str | None = Field(default=None, max_length=32)
    selected_choice_text: str | None = Field(default=None, max_length=500)
    correct_choice_id: str | None = Field(default=None, max_length=32)
    correct_choice_text: str | None = Field(default=None, max_length=500)
    selected_choice_explanation: str | None = Field(default=None, max_length=1200)
    correct_choice_explanation: str | None = Field(default=None, max_length=1200)
    misconception: str = Field(min_length=1, max_length=1200)
    repair_strategy: str = Field(min_length=1, max_length=1200)
    mistake_type: MistakeType
    misconception_id: str | None = Field(default=None, max_length=128)
    why_plausible: str | None = Field(default=None, max_length=1200)
    followup_problem_type: str | None = Field(default=None, max_length=80)

    @field_validator("followup_problem_type", mode="before")
    @classmethod
    def normalize_followup_problem_type_value(cls, value: object) -> str | None:
        return normalize_followup_problem_type(value)


class GenerateProblemRequest(BaseModel):
    document_id: str = Field(min_length=1, max_length=128)
    concepts: list[str] = Field(min_length=1, max_length=20)
    type: ProblemType
    count: int = Field(default=3, ge=1, le=10)
    difficulty: Difficulty = Difficulty.medium
    bloom_level: BloomLevel = BloomLevel.understand
    goal: GenerationGoal = GenerationGoal.practice
    course_level: CourseLevel = CourseLevel.general
    target_rigor: TargetRigor = TargetRigor.standard
    quality_mode: QualityMode = QualityMode.standard
    depth: ProblemDepth = ProblemDepth.standard
    problem_style: ProblemStyle = ProblemStyle.auto
    user_requirements: str | None = Field(default=None, max_length=1000)

    @field_validator("concepts")
    @classmethod
    def normalize_concepts(cls, concepts: list[str]) -> list[str]:
        cleaned = [concept.strip() for concept in concepts]
        if any(not concept for concept in cleaned):
            raise ValueError("concepts must not include empty values")
        if any(len(concept) > 80 for concept in cleaned):
            raise ValueError("each concept must be 80 characters or fewer")
        if len(set(cleaned)) != len(cleaned):
            raise ValueError("concepts must be unique")
        return cleaned

    @model_validator(mode="after")
    def validate_depth_request(self) -> GenerateProblemRequest:
        if self.user_requirements is not None:
            self.user_requirements = self.user_requirements.strip() or None
        if self.depth == ProblemDepth.deep and self.type != ProblemType.short_answer:
            raise ValueError("depth=deep is only supported for short_answer problems")
        return self


class AnswerInput(BaseModel):
    choice_id: str | None = Field(default=None, max_length=32)
    text: str | None = Field(default=None, max_length=4000)
    solution_steps: str | None = Field(default=None, max_length=6000)
    input_mode: AnswerInputMode = AnswerInputMode.typed
    tablet_image_url: str | None = Field(default=None, max_length=2048)
    ocr_text: str | None = Field(default=None, max_length=4000)
    ocr_confidence: float | None = Field(default=None, ge=0, le=1)

    @model_validator(mode="after")
    def require_choice_or_text(self) -> AnswerInput:
        if self.input_mode == AnswerInputMode.tablet_ocr and not self.text and self.ocr_text:
            self.text = self.ocr_text
        if self.choice_id is not None:
            self.choice_id = self.choice_id.strip()
        if self.text is not None:
            self.text = self.text.strip()
        if self.ocr_text is not None:
            self.ocr_text = self.ocr_text.strip()
        if not self.choice_id and not self.text:
            raise ValueError("choice_id or text is required")
        return self


class SubmitAnswerRequest(BaseModel):
    answer: AnswerInput
    elapsed_time_sec: float | None = Field(default=None, ge=0, le=86400)
    hint_count: int = Field(default=0, ge=0, le=100)
    confidence_level: int | None = Field(default=None, ge=1, le=4)


class ProblemHintRequest(BaseModel):
    level: HintLevel = HintLevel.restate_question
    mode: HintMode = HintMode.practice


class ProblemHintResponse(BaseModel):
    problem_id: str
    level: HintLevel
    mode: HintMode
    hint: str
    next_level: HintLevel | None = None
    hint_count: int
    answer_revealed: bool = False
    source_refs: list[SourceRef] | None = None


class ProblemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    document_id: str
    type: ProblemType
    difficulty: Difficulty
    bloom_level: BloomLevel
    question: str
    choices: list[Choice] | None = None
    concepts: list[str]
    source_chunk_ids: list[str]
    source_refs: list[SourceRef] | None = None
    source_grounding_notes: list[str] = Field(default_factory=list)
    quality_status: str
    created_at: datetime
    item_model_id: str | None = None
    item_design_brief: ItemDesignBrief | None = None
    difficulty_profile: DifficultyProfile | None = None
    teacher_review_checklist: TeacherReviewChecklist | None = None
    professor_grade_score: ProfessorGradeItemScore | None = None
    student_response_simulation: StudentResponseSimulationReport | None = None
    explanation: str | None = None
    answer: dict | None = None
    choice_explanations: dict | None = None
    choice_diagnostics: list[ChoiceDiagnosticSpec] | None = None
    rubric: list[RubricItem] | None = None


class GenerateProblemResponse(BaseModel):
    problems: list[ProblemResponse]
    learning_task_strategy: LearningTaskStrategyProfile | None = None
    material_readiness: MaterialReadinessReport | None = None
    blueprint: AssessmentBlueprint | None = None
    high_rigor_profile: HighRigorGenerationProfile | None = None
    quality_summary: GenerationQualitySummary | None = None


class AssessmentSessionGenerateRequest(GenerateProblemRequest):
    time_limit_seconds: int | None = Field(default=None, ge=60, le=10800)


class AssessmentSessionGenerateResponse(BaseModel):
    session_id: str
    status: AssessmentSessionStatus
    retry_of_session_id: str | None = None
    created_at: datetime
    time_limit_seconds: int | None = None
    problems: list[ProblemResponse]
    readiness: AssessmentSessionReadinessReport
    learning_task_strategy: LearningTaskStrategyProfile | None = None
    material_readiness: MaterialReadinessReport | None = None
    blueprint: AssessmentBlueprint | None = None
    high_rigor_profile: HighRigorGenerationProfile | None = None
    quality_summary: GenerationQualitySummary | None = None


class AssessmentSessionProblemResult(BaseModel):
    problem_id: str
    submitted: bool
    feedback_id: str | None = None
    is_correct: bool | None = None
    score: float | None = None
    max_score: float | None = None
    mistake_type: MistakeType | None = None
    weak_concepts: list[str] = Field(default_factory=list)
    recommended_review: list[str] = Field(default_factory=list)


class AssessmentSessionConceptResult(BaseModel):
    concept: str
    problem_count: int
    submitted_count: int
    correct_count: int
    total_score: float
    max_score: float
    score_ratio: float | None = None
    status: Literal["strong", "needs_review", "incomplete"]


class AssessmentSessionReportResponse(BaseModel):
    session_id: str
    status: AssessmentSessionStatus
    document_id: str
    retry_of_session_id: str | None = None
    previous_score_ratio: float | None = None
    score_delta: float | None = None
    previous_completion_ratio: float | None = None
    completion_delta: float | None = None
    concept_score_deltas: dict[str, float] = Field(default_factory=dict)
    problem_count: int
    submitted_count: int
    correct_count: int
    total_score: float
    max_score: float
    score_ratio: float | None = None
    completion_ratio: float = Field(ge=0, le=1)
    total_elapsed_time_sec: float | None = None
    time_limit_seconds: int | None = None
    time_remaining_seconds: float | None = None
    time_over_limit: bool = False
    strong_concepts: list[str] = Field(default_factory=list)
    weak_concepts: list[str] = Field(default_factory=list)
    recommended_review: list[str] = Field(default_factory=list)
    concept_results: list[AssessmentSessionConceptResult] = Field(default_factory=list)
    results: list[AssessmentSessionProblemResult]
    next_step: str
    created_at: datetime
    submitted_at: datetime | None = None


class AssessmentSessionDetailResponse(BaseModel):
    session_id: str
    status: AssessmentSessionStatus
    document_id: str
    retry_of_session_id: str | None = None
    problem_ids: list[str]
    problems: list[ProblemResponse]
    readiness: AssessmentSessionReadinessReport | None = None
    quality_summary: GenerationQualitySummary | None = None
    time_limit_seconds: int | None = None
    submitted_count: int
    created_at: datetime
    submitted_at: datetime | None = None
    report: AssessmentSessionReportResponse | None = None


class AssessmentSessionHistoryAttempt(BaseModel):
    session_id: str
    retry_of_session_id: str | None = None
    attempt_number: int
    status: AssessmentSessionStatus
    score_ratio: float | None = None
    score_delta_from_previous: float | None = None
    completion_ratio: float
    submitted_count: int
    problem_count: int
    strong_concepts: list[str] = Field(default_factory=list)
    weak_concepts: list[str] = Field(default_factory=list)
    created_at: datetime
    submitted_at: datetime | None = None


class AssessmentSessionHistoryResponse(BaseModel):
    root_session_id: str
    current_session_id: str
    attempt_count: int
    best_session_id: str | None = None
    best_score_ratio: float | None = None
    latest_score_ratio: float | None = None
    latest_score_delta_from_first: float | None = None
    trend: Literal["improved", "declined", "unchanged", "insufficient_data"]
    attempts: list[AssessmentSessionHistoryAttempt]


class AssessmentSessionSubmitItem(BaseModel):
    problem_id: str = Field(min_length=1, max_length=128)
    answer: AnswerInput
    elapsed_time_sec: float | None = Field(default=None, ge=0, le=86400)
    hint_count: int = Field(default=0, ge=0, le=100)
    confidence_level: int | None = Field(default=None, ge=1, le=4)

    def to_submit_answer_request(self) -> SubmitAnswerRequest:
        return SubmitAnswerRequest(
            answer=self.answer,
            elapsed_time_sec=self.elapsed_time_sec,
            hint_count=self.hint_count,
            confidence_level=self.confidence_level,
        )


class AssessmentSessionSubmitRequest(BaseModel):
    submissions: list[AssessmentSessionSubmitItem] = Field(min_length=1, max_length=20)
    finalize: bool = True

    @model_validator(mode="after")
    def validate_unique_problem_ids(self) -> AssessmentSessionSubmitRequest:
        problem_ids = [item.problem_id for item in self.submissions]
        if len(set(problem_ids)) != len(problem_ids):
            raise ValueError("assessment session submissions must not include duplicate problem_ids")
        return self


class ProblemItemAnalyticsResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    problem_id: str
    document_id: str
    problem_type: ProblemType
    total_attempts: int
    correct_count: int
    incorrect_count: int
    correct_rate: float
    correct_rate_smoothed: float
    average_score: float
    max_score: float
    discrimination_proxy: float | None = None
    sample_size_status: SampleSizeStatus
    statistics_confidence: StatisticsConfidence
    statistics_note: str
    quality_score_for_review: float | None = None
    quality_score_source: str
    timed_attempt_count: int
    average_time_sec: float | None = None
    hint_usage_count: int
    hint_usage_rate: float
    choice_selection_counts: dict[str, int]
    choice_selection_distribution: dict[str, float]
    choice_mistake_type_counts: dict[str, dict[str, int]]
    non_functioning_distractors: list[str]
    mistake_type_counts: dict[str, int]
    common_mistake_types: list[str]
    missed_rubric_criteria_counts: dict[str, int]
    common_missed_rubric_criteria: list[str]
    needs_review: bool
    review_reasons: list[str]
    updated_at: datetime


class ProblemItemAnalyticsListResponse(BaseModel):
    items: list[ProblemItemAnalyticsResponse]
    total: int
    limit: int


class ProblemTemplateAnalyticsResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    template_key: str
    user_id: str
    document_id: str
    item_model_id: str
    concept: str
    difficulty: Difficulty
    problem_type: ProblemType
    problem_ids: list[str]
    problem_count: int
    total_attempts: int
    correct_count: int
    incorrect_count: int
    correct_rate: float
    correct_rate_smoothed: float
    average_score: float
    max_score: float
    discrimination_proxy: float | None = None
    sample_size_status: SampleSizeStatus
    statistics_confidence: StatisticsConfidence
    statistics_note: str
    item_quality_average: float | None = None
    usage_quality_score: float | None = None
    quality_score_for_review: float | None = None
    quality_score_source: str
    hint_usage_count: int
    hint_usage_rate: float
    mistake_type_counts: dict[str, int]
    common_mistake_types: list[str]
    missed_rubric_criteria_counts: dict[str, int]
    common_missed_rubric_criteria: list[str]
    needs_review: bool
    review_reasons: list[str]
    updated_at: datetime


class ProblemTemplateAnalyticsListResponse(BaseModel):
    items: list[ProblemTemplateAnalyticsResponse]
    total: int
    limit: int


class ProblemRegenerationCandidateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    problem_id: str
    generated_problem_id: str | None = None
    user_id: str
    document_id: str
    status: RegenerationCandidateStatus
    trigger_reasons: list[str]
    source_metrics: dict
    suggested_action: str
    resolution_notes: list[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class ProblemRegenerationCandidateListResponse(BaseModel):
    items: list[ProblemRegenerationCandidateResponse]
    total: int
    limit: int


class ProblemRegenerationResultResponse(BaseModel):
    candidate: ProblemRegenerationCandidateResponse
    problem: ProblemResponse
    original_problem_id: str
    trigger_reasons: list[str]
    suggested_action: str


class UsageLedgerResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: str
    feature: str
    model: str
    request_id: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    estimated_cost_krw: float | None = None
    premium_model_used: bool
    premium_reason: str | None = None
    created_at: datetime


class UsageLedgerListResponse(BaseModel):
    items: list[UsageLedgerResponse]
    total: int
    limit: int


class UsageLedgerSummaryResponse(BaseModel):
    user_id: str
    feature: str | None = None
    total_calls: int
    premium_call_count: int
    total_input_tokens: int
    total_output_tokens: int
    total_tokens: int
    total_estimated_cost_krw: float
    budget_limit_krw: float | None = None
    budget_used_ratio: float | None = None
    budget_status: Literal["not_configured", "ok", "warning", "exceeded"]


class QualityReportRequest(BaseModel):
    target_type: QualityReportTargetType
    target_id: str = Field(min_length=1, max_length=128)
    reason: QualityReportReason
    message: str | None = Field(default=None, max_length=1000)

    @field_validator("message")
    @classmethod
    def normalize_message(cls, message: str | None) -> str | None:
        if message is None:
            return None
        cleaned = message.strip()
        return cleaned or None


class QualityReportResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: str
    target_type: QualityReportTargetType
    target_id: str
    reason: QualityReportReason
    message: str | None = None
    status: QualityReportStatus
    created_at: datetime


class FeedbackResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: str
    submission_id: str
    problem_id: str
    is_correct: bool
    score: float
    max_score: float
    mistake_type: MistakeType | None
    weak_concepts: list[str]
    summary: str
    feedback: str
    recommended_review: list[str]
    source_chunk_ids: list[str]
    evaluation_details: ShortAnswerEvaluationDetails | None = None
    choice_diagnostic: ChoiceFeedbackDiagnostic | None = None
    learning_state: LearningState = LearningState.unreported
    display_copy: FeedbackCopyOutput | None = Field(default=None, alias="copy")
    created_at: datetime


class AssessmentSessionSubmitResponse(BaseModel):
    session_id: str
    status: AssessmentSessionStatus
    feedbacks: list[FeedbackResponse]
    report: AssessmentSessionReportResponse


class FeedbackActionEventRequest(BaseModel):
    event_type: FeedbackActionEventType
    action_type: FeedbackActionType | None = None
    target_problem_id: str | None = Field(default=None, min_length=1, max_length=128)
    target_content_id: str | None = Field(default=None, min_length=1, max_length=128)
    is_successful: bool | None = None
    helpful_rating: int | None = Field(default=None, ge=1, le=5)
    event_metadata: dict = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_event_payload(self) -> FeedbackActionEventRequest:
        if self.event_type == FeedbackActionEventType.next_action_clicked and self.action_type is None:
            raise ValueError("action_type is required for next_action_clicked")
        if self.event_type == FeedbackActionEventType.helpful_rating and self.helpful_rating is None:
            raise ValueError("helpful_rating is required for helpful_rating events")
        if self.event_type in {
            FeedbackActionEventType.retry_completed,
            FeedbackActionEventType.followup_problem_completed,
        } and self.is_successful is None:
            raise ValueError("is_successful is required for completion events")
        if self.event_type == FeedbackActionEventType.followup_problem_completed and self.target_problem_id is None:
            raise ValueError("target_problem_id is required for followup_problem_completed")
        if len(self.event_metadata) > 20:
            raise ValueError("event_metadata can include at most 20 keys")
        return self


class FeedbackActionEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    feedback_id: str
    problem_id: str
    user_id: str
    event_type: FeedbackActionEventType
    action_type: FeedbackActionType | None = None
    target_problem_id: str | None = None
    target_content_id: str | None = None
    is_successful: bool | None = None
    helpful_rating: int | None = None
    event_metadata: dict
    created_at: datetime


class FeedbackActionEventListResponse(BaseModel):
    items: list[FeedbackActionEventResponse]
    total: int
    limit: int
