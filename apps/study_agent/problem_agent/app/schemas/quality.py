from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field


class GenerationGoal(StrEnum):
    practice = "practice"
    concept_review = "concept_review"
    exam_prep = "exam_prep"
    weak_concept_repair = "weak_concept_repair"


class CourseLevel(StrEnum):
    general = "general"
    middle_school = "middle_school"
    high_school = "high_school"
    university = "university"
    professional = "professional"


class TargetRigor(StrEnum):
    basic = "basic"
    standard = "standard"
    high = "high"


class HighRigorIntensity(StrEnum):
    standard = "standard"
    advanced = "advanced"
    elite = "elite"


class VerificationLevel(StrEnum):
    standard = "standard"
    enhanced = "enhanced"
    strict = "strict"


class SourceGroundingMode(StrEnum):
    source_grounded = "source_grounded"
    source_application = "source_application"
    model_extension = "model_extension"


class QualityMode(StrEnum):
    standard = "standard"
    strict = "strict"


class SubjectDomain(StrEnum):
    korean_language = "korean_language"
    math = "math"
    science = "science"
    social_studies = "social_studies"
    english_or_foreign_language = "english_or_foreign_language"
    computer_science = "computer_science"
    general_concept = "general_concept"
    unknown = "unknown"


class ContentForm(StrEnum):
    definition = "definition"
    formula = "formula"
    procedure = "procedure"
    concept_relation = "concept_relation"
    passage = "passage"
    case = "case"
    data_table = "data_table"
    graph = "graph"
    code = "code"
    argument = "argument"
    timeline = "timeline"


class CognitiveOperation(StrEnum):
    recall = "recall"
    explain = "explain"
    apply = "apply"
    compare = "compare"
    classify = "classify"
    calculate = "calculate"
    infer = "infer"
    analyze = "analyze"
    evaluate = "evaluate"
    design = "design"


class ResponseMode(StrEnum):
    multiple_choice = "multiple_choice"
    short_answer = "short_answer"
    calculation = "calculation"
    proof_or_derivation = "proof_or_derivation"
    essay = "essay"
    code_answer = "code_answer"
    ordering = "ordering"
    matching = "matching"


class ProblemStrategy(StrEnum):
    basic_concept_check = "basic_concept_check"
    near_transfer_application = "near_transfer_application"
    comparison_judgment = "comparison_judgment"
    calculation = "calculation"
    formula_application = "formula_application"
    passage_evidence = "passage_evidence"
    variable_prediction = "variable_prediction"
    case_analysis = "case_analysis"
    code_reasoning = "code_reasoning"
    general_explanation = "general_explanation"


class ReadinessLevel(StrEnum):
    sufficient = "sufficient"
    limited = "limited"
    insufficient = "insufficient"


class AssessmentReadinessStatus(StrEnum):
    not_ready = "not_ready"
    diagnostic_ready = "diagnostic_ready"
    personalized_ready = "personalized_ready"
    exam_ready = "exam_ready"


class QualityStatus(StrEnum):
    passed = "passed"
    limited_source = "limited_source"
    needs_review = "needs_review"
    rejected = "rejected"


class QualityFlag(StrEnum):
    limited_source = "limited_source"
    insufficient_source = "insufficient_source"
    definition_only_risk = "definition_only_risk"
    unsupported_source = "unsupported_source"
    weak_source_overlap = "weak_source_overlap"
    source_verbatim_overlap = "source_verbatim_overlap"
    prompt_injection_leak = "prompt_injection_leak"
    shallow_deep_question = "shallow_deep_question"
    answer_leak = "answer_leak"
    weak_application_fit = "weak_application_fit"
    blueprint_mismatch = "blueprint_mismatch"
    low_strategy_confidence = "low_strategy_confidence"
    option_length_cue = "option_length_cue"
    absolute_wording = "absolute_wording"
    all_or_none_option = "all_or_none_option"
    overlapping_options = "overlapping_options"
    implausible_distractor = "implausible_distractor"
    unfocused_stem = "unfocused_stem"
    weak_rubric_evidence = "weak_rubric_evidence"
    item_model_quality_violation = "item_model_quality_violation"
    weak_concept_integration = "weak_concept_integration"
    low_cognitive_demand = "low_cognitive_demand"
    ai_like_wording = "ai_like_wording"
    invalid_latex = "invalid_latex"


class LearningTaskStrategyProfile(BaseModel):
    subject_domain: SubjectDomain = SubjectDomain.unknown
    confidence: str = Field(default="low")
    topic_label: str = Field(default="unknown")
    core_keywords: list[str] = Field(default_factory=list)
    content_forms: list[ContentForm] = Field(default_factory=list)
    cognitive_operations: list[CognitiveOperation] = Field(default_factory=list)
    response_modes: list[ResponseMode] = Field(default_factory=list)
    recommended_strategies: list[ProblemStrategy] = Field(default_factory=list)
    avoid_strategies: list[ProblemStrategy] = Field(default_factory=list)
    selectable_learning_content_types: list[str] = Field(default_factory=list)
    available_learning_content_types: list[str] = Field(default_factory=list)
    recommended_learning_content_types: list[str] = Field(default_factory=list)
    not_recommended_learning_content_types: list[str] = Field(default_factory=list)
    learning_content_type_reason: str = ""
    strategy_id: str = "general_concept_explain_v1"
    reason: str = ""


class MaterialReadinessReport(BaseModel):
    score: float = Field(ge=0, le=1)
    level: ReadinessLevel
    reasons: list[str] = Field(default_factory=list)
    can_generate: list[ProblemStrategy] = Field(default_factory=list)
    risky_generations: list[ProblemStrategy] = Field(default_factory=list)
    recommended_uploads: list[str] = Field(default_factory=list)


class HighRigorGenerationProfile(BaseModel):
    """Internal strategy profile for difficult natural-language requests.

    This is not a user-facing mode. It lets the backend strengthen search,
    candidate generation, and validation when the user asks for exam-like,
    multi-step, or multi-concept problems in natural language.
    """

    enabled: bool = False
    intensity: HighRigorIntensity = HighRigorIntensity.standard
    multi_concept_required: bool = False
    multi_step_required: bool = False
    broad_search_required: bool = False
    solution_depth: str = "standard"
    verification_level: VerificationLevel = VerificationLevel.standard
    estimated_solve_time_minutes: int | None = Field(default=None, ge=1, le=180)
    recommended_top_k: int = Field(default=6, ge=1, le=30)
    candidate_multiplier: int = Field(default=1, ge=1, le=5)
    signals: list[str] = Field(default_factory=list)
    reason: str = ""


class SourceGroundingProfile(BaseModel):
    """Internal source-use policy inferred from the user's natural-language request.

    This is not a user-facing mode. It tells generation and validation how far a
    problem may move from the uploaded material while staying anchored to it.
    """

    mode: SourceGroundingMode = SourceGroundingMode.source_grounded
    allow_synthetic_context: bool = False
    allow_external_knowledge: bool = False
    strict_source_rejection: bool = True
    signals: list[str] = Field(default_factory=list)
    reason: str = ""


class BlueprintCell(BaseModel):
    concept: str = Field(min_length=1)
    problem_type: str = Field(min_length=1)
    bloom_level: str = Field(min_length=1)
    count: int = Field(ge=1)
    points: float = Field(gt=0)
    strategies: list[ProblemStrategy] = Field(default_factory=list)
    required_evidence: list[str] = Field(default_factory=list)


class AssessmentBlueprint(BaseModel):
    goal: GenerationGoal
    course_level: CourseLevel
    target_rigor: TargetRigor
    total_count: int = Field(ge=1)
    distribution: list[BlueprintCell] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class AssessmentSessionCoverageReport(BaseModel):
    requested_concepts: list[str] = Field(default_factory=list)
    source_covered_concepts: list[str] = Field(default_factory=list)
    weak_or_missing_concepts: list[str] = Field(default_factory=list)
    coverage_ratio: float = Field(ge=0, le=1)
    difficulty_distribution: dict[str, int] = Field(default_factory=dict)
    problem_type_distribution: dict[str, int] = Field(default_factory=dict)
    bloom_distribution: dict[str, int] = Field(default_factory=dict)
    estimated_time_minutes: int = Field(ge=0)
    includes_multi_concept_items: bool = False
    warnings: list[str] = Field(default_factory=list)


class ProblemQualityReport(BaseModel):
    status: QualityStatus
    score: float = Field(ge=0, le=1)
    flags: list[QualityFlag] = Field(default_factory=list)
    source_grounded: bool = True
    source_coverage_score: float | None = Field(default=None, ge=0, le=1)
    unsupported_numbers: list[str] = Field(default_factory=list)
    verbatim_overlap_chars: int = Field(default=0, ge=0)
    cognitive_level_fit: bool = True
    blueprint_aligned: bool = True
    choice_quality_issues: list[str] = Field(default_factory=list)
    rubric_quality_issues: list[str] = Field(default_factory=list)
    item_model_quality_issues: list[str] = Field(default_factory=list)
    repetition_risk: str = "low"
    action: str = "save"


class ProblemAnswerVerificationReport(BaseModel):
    verified: bool
    confidence: Literal["low", "medium", "high"]
    answer_correctness_score: float = Field(ge=0, le=1)
    ambiguity_score: float = Field(ge=0, le=1)
    grounding_score: float = Field(ge=0, le=1)
    issues: list[str] = Field(default_factory=list)
    recommended_action: Literal["pass", "needs_review", "reject"]
    numeric_grounding: dict[str, list[str]] = Field(default_factory=dict)


class GenerationAttemptMetrics(BaseModel):
    attempt_index: int
    generation_mode: str | None = None
    model: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    estimated_cost_krw: float | None = None
    prompt_char_count: int | None = None
    evidence_pack_atom_count: int | None = None
    raw_context_char_count: int | None = None
    compressed_prompt_enabled: bool | None = None
    context_chunk_count: int | None = None
    candidate_count_requested: int | None = None
    valid_candidates_produced: int | None = None
    rejected_candidates_produced: int | None = None
    requested_candidate_count: int
    generated_candidate_count: int
    valid_candidate_count_after_attempt: int
    rejected_count_after_attempt: int
    llm_generation_ms: float
    quality_filter_ms: float
    retry_feedback_count: int = 0
    retry_feedback_categories: list[str] = Field(default_factory=list)
    new_rejection_category_counts: dict[str, int] = Field(default_factory=dict)


class RejectedCandidateArtifactRecord(BaseModel):
    case_id: str
    repeat_index: int = 0
    attempt_index: int = 0
    candidate_index: int = 0
    document_id: str | None = None
    type: str | None = None
    kernel_type: str | None = None
    problem_style: str | None = None
    question_preview: str | None = None
    choices_preview: list[str] = Field(default_factory=list)
    answer_preview: str | None = None
    explanation_preview: str | None = None
    rubric_preview: str | None = None
    source_chunk_ids: list[str] = Field(default_factory=list)
    selected_atom_ids: list[str] = Field(default_factory=list)
    selected_atom_chunk_ids: list[str] = Field(default_factory=list)
    evidence_obligation_issues: list[str] = Field(default_factory=list)
    quality_errors: list[str] = Field(default_factory=list)
    rejection_categories: dict[str, int] = Field(default_factory=dict)
    llm_model: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    created_at: str


class EvalUsageLedgerRecord(BaseModel):
    case_id: str
    repeat_index: int = 0
    attempt_index: int = 0
    model: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    estimated_cost_krw: float | None = None
    generation_mode: str | None = None
    failure_status: str | None = None
    created_at: str


class GenerationPerformanceSummary(BaseModel):
    total_ms: float
    request_preparation_ms: float | None = None
    search_ms: float | None = None
    planning_ms: float | None = None
    existing_problem_lookup_ms: float | None = None
    retrieved_chunk_count: int = 0
    generation_context_chunk_count: int = 0
    generation_context_chunk_ids: list[str] = Field(default_factory=list)
    generation_context_reduction_ratio: float | None = None
    dropped_retrieved_chunk_count: int = 0
    raw_content_atom_count: int = 0
    raw_content_atom_type_counts: dict[str, int] = Field(default_factory=dict)
    selected_kernel_atom_ids: list[str] = Field(default_factory=list)
    selected_kernel_atom_chunk_ids: list[str] = Field(default_factory=list)
    rescued_kernel_atom_chunk_count: int = 0
    generation_context_selected_atom_recall: float | None = None
    content_atom_count: int = 0
    content_atom_type_counts: dict[str, int] = Field(default_factory=dict)
    generation_context_atom_type_counts: dict[str, int] = Field(default_factory=dict)
    problem_kernel_type: str | None = None
    kernel_planning_failure_reason: str | None = None
    generation_strategy: str | None = None
    repair_call_count: int = 0
    initial_candidate_valid: bool | None = None
    repair_successful: bool | None = None
    tokens_saved_estimate_vs_batch: int | None = None
    candidate_generation_total_ms: float | None = None
    quality_filter_total_ms: float | None = None
    db_write_ms: float | None = None
    db_commit_ms: float | None = None
    db_refresh_ms: float | None = None
    artifact_publish_ms: float | None = None
    artifact_publish_success_count: int = 0
    artifact_publish_failure_count: int = 0
    actual_retry_count: int = 0
    reject_rate: float | None = None
    pass_rate: float | None = None
    total_llm_input_tokens: int = 0
    total_llm_output_tokens: int = 0
    total_llm_tokens: int = 0
    total_estimated_cost_krw: float = 0.0
    actual_generation_models: list[str] = Field(default_factory=list)
    llm_call_count: int = 0
    rejected_candidate_count: int = 0
    approximate_wasted_candidate_ratio: float | None = None
    rejection_category_counts: dict[str, int] = Field(default_factory=dict)
    top_rejection_categories: list[str] = Field(default_factory=list)
    attempts: list[GenerationAttemptMetrics] = Field(default_factory=list)


class GenerationQualitySummary(BaseModel):
    generated: int = Field(ge=0)
    passed: int = Field(ge=0)
    rejected: int = Field(ge=0)
    discarded: int = Field(default=0, ge=0)
    warnings: list[str] = Field(default_factory=list)
    performance: GenerationPerformanceSummary | None = None


class AssessmentSessionReadinessReport(BaseModel):
    status: AssessmentReadinessStatus
    score: float = Field(ge=0, le=1)
    material_score: float = Field(ge=0, le=1)
    learner_history_score: float = Field(ge=0, le=1)
    quality_gate_score: float = Field(ge=0, le=1)
    total_attempts: int = Field(ge=0)
    covered_concepts: list[str] = Field(default_factory=list)
    weak_concepts: list[str] = Field(default_factory=list)
    can_generate_source_based_set: bool = False
    can_generate_personalized_set: bool = False
    can_generate_exam_set: bool = False
    recommended_blueprint: AssessmentBlueprint | None = None
    coverage_report: AssessmentSessionCoverageReport | None = None
    recommended_next_step: str
    reasons: list[str] = Field(default_factory=list)
    blocking_reasons: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
