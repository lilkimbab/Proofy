from __future__ import annotations

from collections import Counter
from contextlib import contextmanager
import csv
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import time
from typing import Any, Iterator, Literal
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import create_engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.agents import ProblemAgent, ProblemQualityChecker
from app.config import Settings, get_settings
from app.db import Base
from app.llm.openai_client import OpenAIClient
import app.models.entities  # noqa: F401
from app.models import Problem
from app.schemas.integration_contracts import RetrievedChunk
from app.schemas.problems import BloomLevel, Difficulty, GenerateProblemRequest, ProblemType
from app.schemas.quality import (
    GenerationAttemptMetrics,
    ProblemAnswerVerificationReport,
    QualityMode,
    TargetRigor,
)
from app.services.generated_artifact_publisher import GeneratedArtifactPublisher
from app.services.problem_answer_verifier import ProblemAnswerVerifier
from app.services.problem_service import ProblemService
from app.services.rejected_candidate_artifact_writer import RejectedCandidateArtifactWriter
from app.services.search_service import SearchAgentError, SearchService


REPORT_JSON_NAME = "live_problem_generation_report.json"
REPORT_JSONL_NAME = "live_problem_generation_cases.jsonl"
REPORT_MARKDOWN_NAME = "live_problem_generation_summary.md"
REPORT_HUMAN_REVIEW_CSV_NAME = "live_problem_generation_human_review.csv"
REPORT_HUMAN_REVIEW_SUMMARY_JSON_NAME = "live_problem_generation_human_review_summary.json"
REPORT_HUMAN_REVIEW_SUMMARY_MARKDOWN_NAME = "live_problem_generation_human_review_summary.md"
LIVE_EVAL_REPORT_SCHEMA_VERSION = "live_problem_generation_eval.v2"
DEFAULT_LIVE_EVAL_CASES_PATH = Path("evals/live_materials/example_cases.jsonl")
LIVE_EVAL_DATABASE_NAME = "live_problem_generation_eval.sqlite"
LIVE_EVAL_DATABASE_URL_WARNING = "live eval will use DATABASE_URL; ensure this is not production"
LIVE_EVAL_LLM_JUDGE_KEY_WARNING = "LLM judge is enabled but OPENAI_API_KEY is missing"
HUMAN_REVIEW_REDACTED_VALUE = "[redacted]"


class LiveProblemGenerationEvalCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    description: str = Field(min_length=1)
    document_id: str = Field(min_length=1)
    domain_family: str | None = None
    domain: str | None = None
    language: Literal["en", "ko"] | None = None
    content_atom_type: str | None = None
    problem_kernel: str | None = None
    concepts: list[str] = Field(min_length=1)
    request: dict[str, Any]
    expected_search_terms: list[str] = Field(default_factory=list)
    expected_problem_terms: list[str] = Field(default_factory=list)
    expected_search_term_aliases: dict[str, list[str]] = Field(default_factory=dict)
    expected_problem_term_aliases: dict[str, list[str]] = Field(default_factory=dict)
    expected_chunk_ids: list[str] = Field(default_factory=list)
    expected_pages: list[int] = Field(default_factory=list)
    expected_source_spans: list[str] = Field(default_factory=list)
    irrelevant_terms: list[str] = Field(default_factory=list)
    golden_label_mode: Literal["partial", "exhaustive"] = "partial"
    min_returned_chunks: int | None = None
    min_cited_chunks_per_problem: float | None = None
    min_average_quality_score: float | None = Field(default=None, ge=0, le=1)
    max_reject_rate: float | None = Field(default=None, ge=0, le=1)
    max_total_ms: float | None = None
    min_expected_search_term_coverage: float | None = Field(default=None, ge=0, le=1)
    min_expected_problem_term_coverage: float | None = Field(default=None, ge=0, le=1)
    min_hit_at_k: float | None = Field(default=None, ge=0, le=1)
    min_mrr_at_k: float | None = Field(default=None, ge=0, le=1)
    min_precision_at_k: float | None = Field(default=None, ge=0, le=1)
    min_cited_expected_chunk_recall: float | None = Field(default=None, ge=0, le=1)
    min_cited_expected_chunk_precision: float | None = Field(default=None, ge=0, le=1)
    min_cited_source_span_coverage: float | None = Field(default=None, ge=0, le=1)
    min_generation_context_expected_chunk_recall: float | None = Field(default=None, ge=0, le=1)
    min_generation_context_source_span_coverage: float | None = Field(default=None, ge=0, le=1)
    min_repeat_pass_rate: float | None = Field(default=None, ge=0, le=1)
    max_repeat_quality_score_stddev: float | None = Field(default=None, ge=0)
    max_repeat_duplicate_similarity: float | None = Field(default=None, ge=0, le=1)
    allow_missing_quality_score: bool = False
    allow_generic_high_rigor_operation: bool = False


class LiveEvalPreflightReport(BaseModel):
    enabled: bool
    can_run: bool
    missing_env_vars: list[str] = Field(default_factory=list)
    placeholder_case_ids: list[str] = Field(default_factory=list)
    placeholder_document_ids: list[str] = Field(default_factory=list)
    cases_path_exists: bool
    case_count: int = 0
    warnings: list[str] = Field(default_factory=list)


class LiveProblemQualityDiagnostic(BaseModel):
    problem_id: str
    type: str
    difficulty: str
    bloom_level: str
    item_model_id: str | None = None
    quality_status: str
    professor_grade_final_score: float | None = None
    professor_score_band: str | None = None
    structural_score: float | None = None
    pedagogical_score: float | None = None
    grounding_score: float | None = None
    assessment_design_score: float | None = None
    source_chunk_count: int
    has_source_evidence_snapshot: bool
    has_explanation: bool
    has_answer: bool
    multiple_choice_has_four_choices: bool | None = None
    multiple_choice_has_choice_explanations: bool | None = None
    multiple_choice_has_choice_diagnostics: bool | None = None
    incorrect_distractor_diagnostic_count: int | None = None
    short_answer_has_rubric: bool | None = None
    short_answer_rubric_item_count: int | None = None
    high_rigor_operation_detected: bool
    high_rigor_operation_label: str
    source_term_coverage: float
    expected_problem_term_coverage: float
    warning_flags: list[str] = Field(default_factory=list)
    quality_risk_level: str
    answer_verification_score: float | None = None
    answer_verification_action: str | None = None
    answer_verification_issues: list[str] = Field(default_factory=list)
    evidence_link_count: int = 0
    evidence_obligation_satisfaction: float | None = None
    answer_supported: bool | None = None
    explanation_supported: bool | None = None
    distractors_supported: bool | None = None
    rubric_supported: bool | None = None
    source_formula_or_rule_cited: bool | None = None
    missing_evidence_roles: list[str] = Field(default_factory=list)
    evidence_obligation_issues: list[str] = Field(default_factory=list)
    commercial_quality_score: float | None = None
    commercial_quality_band: str | None = None


class LiveProblemLLMJudgeResult(BaseModel):
    problem_id: str
    source_grounding_score: float = Field(ge=0, le=1)
    cognitive_rigor_score: float = Field(ge=0, le=1)
    distractor_quality_score: float = Field(ge=0, le=1)
    explanation_quality_score: float = Field(ge=0, le=1)
    difficulty_fit_score: float = Field(ge=0, le=1)
    overall_score: float = Field(ge=0, le=1)
    failure_reasons: list[str] = Field(default_factory=list)
    recommended_action: str


class LiveHumanReviewRow(BaseModel):
    case_id: str
    problem_id: str
    document_id: str
    type: str
    difficulty: str
    bloom_level: str
    item_model_id: str | None = None
    question: str
    choices_json: str
    answer_json: str
    explanation: str
    rubric_json: str
    source_chunk_ids_json: str
    source_evidence_snapshot_json: str
    professor_grade_final_score: float | None = None
    professor_score_band: str | None = None
    structural_score: float | None = None
    pedagogical_score: float | None = None
    grounding_score: float | None = None
    assessment_design_score: float | None = None
    quality_status: str
    high_rigor_operation_label: str
    reviewer_problem_quality_score: str = ""
    reviewer_source_grounding_score: str = ""
    reviewer_difficulty_fit_score: str = ""
    reviewer_notes: str = ""


class HumanReviewRecord(BaseModel):
    case_id: str
    problem_id: str
    reviewer_problem_quality_score: float | None = None
    reviewer_source_grounding_score: float | None = None
    reviewer_difficulty_fit_score: float | None = None
    reviewer_notes: str = ""


class HumanReviewSummary(BaseModel):
    reviewed_problem_count: int
    average_problem_quality_score: float | None = None
    average_source_grounding_score: float | None = None
    average_difficulty_fit_score: float | None = None
    low_quality_review_count: int = 0
    low_grounding_review_count: int = 0
    low_difficulty_fit_count: int = 0
    reviewer_notes_by_problem: dict[str, list[str]] = Field(default_factory=dict)
    correlation_professor_vs_human_quality: float | None = None
    disagreements: list[dict[str, Any]] = Field(default_factory=list)


class LiveCaseExecutionTrace(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True, extra="allow")

    search_query: str | None = None
    search_ms: float | None = None
    returned_chunk_count: int | None = None
    unique_returned_chunk_count: int | None = None
    hit_at_k: float | None = None
    mrr_at_k: float | None = None
    precision_at_k: float | None = None
    source_span_coverage: float | None = None
    generation_context_chunk_ids: list[str] = Field(default_factory=list)
    generation_context_expected_chunk_recall: float | None = None
    raw_content_atom_count: int | None = None
    raw_content_atom_type_counts: dict[str, int] = Field(default_factory=dict)
    selected_kernel_atom_ids: list[str] = Field(default_factory=list)
    problem_kernel_type: str | None = None
    selected_kernel_atom_chunk_ids: list[str] = Field(default_factory=list)
    kernel_atom_dropped_count: int = 0
    kernel_planning_failure_reason: str | None = None
    rejection_category_counts: dict[str, int] = Field(default_factory=dict)
    top_rejection_categories: list[str] = Field(default_factory=list)
    failure_stage: str | None = None
    retrieval_metrics: dict[str, Any] = Field(default_factory=dict)
    chunks: list[RetrievedChunk] = Field(default_factory=list, exclude=True)

    def to_trace_dict(self) -> dict[str, Any]:
        payload = self.model_dump(exclude_none=True, exclude={"chunks"})
        payload["chunks"] = list(self.chunks)
        return payload


class LiveProblemGenerationCaseResult(BaseModel):
    case_id: str
    repeat_index: int = 0
    repeated_case_group_id: str | None = None
    description: str
    document_id: str
    concepts: list[str]
    generated_problem_ids: list[str]
    golden_label_mode: Literal["partial", "exhaustive"] = "partial"
    search_query_mode: str = "compact"
    cost_profile: Literal["cheap", "balanced", "full"] = "balanced"
    search_query: str | None = None
    requested_count: int
    generated_count: int
    passed_count: int
    rejected_count: int
    discarded_count: int
    actual_retry_count: int
    reject_rate: float | None = None
    pass_rate: float | None = None
    actual_generation_models: list[str] = Field(default_factory=list)
    total_llm_input_tokens: int = 0
    total_llm_output_tokens: int = 0
    total_llm_tokens: int = 0
    total_estimated_cost_krw: float = 0.0
    llm_call_count: int = 0
    wasted_candidate_ratio: float | None = None
    generation_attempts: list[GenerationAttemptMetrics] = Field(default_factory=list)
    total_ms: float | None = None
    search_ms: float | None = None
    bottleneck_component: str | None = None
    bottleneck_component_ms: float | None = None
    bottleneck_component_ratio: float | None = None
    baseline_search_ms: float | None = None
    enhanced_search_ms: float | None = None
    effective_search_ms: float | None = None
    service_internal_search_ms: float | None = None
    search_latency_note: str | None = None
    planning_ms: float | None = None
    candidate_generation_total_ms: float | None = None
    quality_filter_total_ms: float | None = None
    db_write_ms: float | None = None
    db_commit_ms: float | None = None
    db_refresh_ms: float | None = None
    artifact_publish_ms: float | None = None
    artifact_publish_success_count: int = 0
    artifact_publish_failure_count: int = 0
    returned_chunk_count: int
    unique_returned_chunk_count: int
    empty_chunk_count: int
    wrong_document_chunk_count: int
    average_chunk_content_chars: float
    metadata_score_summary: dict[str, dict[str, float]] = Field(default_factory=dict)
    concept_overlap_ratio: float
    cited_chunk_count_total: int
    cited_chunk_count_avg: float
    expected_search_term_coverage: float
    hit_at_k: float | None = None
    mrr_at_k: float | None = None
    precision_at_k: float | None = None
    expected_page_hit: float | None = None
    source_span_coverage: float | None = None
    irrelevant_term_hit_count: int = 0
    cited_expected_chunk_recall: float | None = None
    cited_expected_chunk_precision: float | None = None
    cited_hit_at_k: float | None = None
    cited_source_span_coverage: float | None = None
    cited_expected_chunk_ids: list[str] = Field(default_factory=list)
    uncited_expected_chunk_ids: list[str] = Field(default_factory=list)
    cited_non_expected_chunk_ids: list[str] = Field(default_factory=list)
    generation_context_chunk_count: int = 0
    generation_context_chunk_ids: list[str] = Field(default_factory=list)
    generation_context_expected_chunk_recall: float | None = None
    generation_context_expected_chunk_precision: float | None = None
    generation_context_hit_at_k: float | None = None
    generation_context_source_span_coverage: float | None = None
    retrieved_to_context_reduction_ratio: float | None = None
    raw_content_atom_count: int = 0
    raw_content_atom_type_counts: dict[str, int] = Field(default_factory=dict)
    selected_kernel_atom_ids: list[str] = Field(default_factory=list)
    selected_kernel_atom_chunk_ids: list[str] = Field(default_factory=list)
    rescued_kernel_atom_chunk_count: int = 0
    generation_context_selected_atom_recall: float | None = None
    generation_context_atom_type_counts: dict[str, int] = Field(default_factory=dict)
    kernel_atom_dropped_count: int = 0
    problem_kernel_type: str | None = None
    kernel_planning_failure_reason: str | None = None
    expected_problem_term_coverage: float
    average_quality_score: float | None = None
    average_professor_grade_score: float | None = None
    commercial_quality_score: float | None = None
    commercial_quality_band_counts: dict[str, int] = Field(default_factory=dict)
    professor_vs_commercial_disagreement_count: int = 0
    professor_commercial_disagreements: list[dict[str, Any]] = Field(default_factory=list)
    source_term_coverage: float
    high_rigor_item_model_id_coverage: float | None = None
    high_rigor_mc_choice_diagnostics_coverage: float | None = None
    short_answer_rubric_coverage: float | None = None
    quality_status_counts: dict[str, int]
    item_model_id_counts: dict[str, int]
    professor_score_band_counts: dict[str, int] = Field(default_factory=dict)
    high_rigor_operation_counts: dict[str, int] = Field(default_factory=dict)
    low_quality_problem_count: int = 0
    medium_quality_problem_count: int = 0
    high_quality_problem_count: int = 0
    missing_diagnostics_count: int = 0
    missing_rubric_count: int = 0
    low_source_coverage_count: int = 0
    average_source_term_coverage: float | None = None
    average_expected_problem_term_coverage: float | None = None
    problem_quality_diagnostics: list[LiveProblemQualityDiagnostic] = Field(default_factory=list)
    llm_judge_results: list[LiveProblemLLMJudgeResult] = Field(default_factory=list)
    average_llm_judge_overall_score: float | None = None
    llm_judge_action_counts: dict[str, int] = Field(default_factory=dict)
    answer_verification_action_counts: dict[str, int] = Field(default_factory=dict)
    answer_correctness_issue_count: int = 0
    human_review_rows: list[LiveHumanReviewRow] = Field(default_factory=list, exclude=True)
    warning_count: int
    warnings: list[str]
    threshold_passed: bool
    threshold_failures: list[str]
    threshold_failures_quality: list[str] = Field(default_factory=list)
    threshold_failures_performance: list[str] = Field(default_factory=list)
    threshold_failures_stability: list[str] = Field(default_factory=list)
    baseline_query: str | None = None
    enhanced_query: str | None = None
    baseline_returned_chunk_count: int | None = None
    enhanced_returned_chunk_count: int | None = None
    baseline_expected_search_term_coverage: float | None = None
    enhanced_expected_search_term_coverage: float | None = None
    baseline_hit_at_k: float | None = None
    enhanced_hit_at_k: float | None = None
    baseline_mrr_at_k: float | None = None
    enhanced_mrr_at_k: float | None = None
    baseline_precision_at_k: float | None = None
    enhanced_precision_at_k: float | None = None
    baseline_source_span_coverage: float | None = None
    enhanced_source_span_coverage: float | None = None
    baseline_concept_overlap_ratio: float | None = None
    enhanced_concept_overlap_ratio: float | None = None
    baseline_average_chunk_content_chars: float | None = None
    enhanced_average_chunk_content_chars: float | None = None
    baseline_unique_chunk_ids: list[str] | None = None
    enhanced_unique_chunk_ids: list[str] | None = None
    chunk_id_overlap_ratio: float | None = None
    baseline_search_quality_score: float | None = None
    enhanced_search_quality_score: float | None = None
    enhanced_score_minus_baseline_score: float | None = None
    enhanced_wins_search_quality: bool | None = None
    query_mode_scores: dict[str, float] = Field(default_factory=dict)
    query_mode_hit_at_k: dict[str, float | None] = Field(default_factory=dict)
    query_mode_mrr_at_k: dict[str, float | None] = Field(default_factory=dict)
    query_mode_source_span_coverage: dict[str, float | None] = Field(default_factory=dict)
    best_query_mode_by_score: str | None = None
    primary_query_mode_score: float | None = None
    execution_status: Literal[
        "completed",
        "generation_failed",
        "search_failed",
        "db_failed",
        "unknown_failed",
    ] = "completed"
    exception_type: str | None = None
    exception_message: str | None = None
    exception_stage: str | None = None
    failure_stage: str | None = None
    failure_rejection_category_counts: dict[str, int] = Field(default_factory=dict)
    failure_top_rejection_categories: list[str] = Field(default_factory=list)


class LiveProblemGenerationEvalReport(BaseModel):
    report_schema_version: str = LIVE_EVAL_REPORT_SCHEMA_VERSION
    generated_at: datetime
    code_version: str | None = None
    git_commit: str | None = None
    cases_sha256: str | None = None
    settings_snapshot: dict[str, str] = Field(default_factory=dict)
    cases_path: str
    output_dir: str
    search_query_mode: str = "compact"
    cost_profile: Literal["cheap", "balanced", "full"] = "balanced"
    cost_profile_warning: str | None = None
    human_review_export_mode: Literal["full", "redacted"] = "full"
    repeat_count: int = 1
    logical_case_count: int = 0
    total_run_count: int = 0
    case_count: int
    passed_count: int
    failed_count: int
    failed_execution_count: int = 0
    generation_failed_count: int = 0
    search_failed_count: int = 0
    db_failed_count: int = 0
    average_total_ms: float | None = None
    p50_total_ms: float | None = None
    p95_total_ms: float | None = None
    p50_search_ms: float | None = None
    p95_search_ms: float | None = None
    p50_candidate_generation_total_ms: float | None = None
    p95_candidate_generation_total_ms: float | None = None
    p50_quality_filter_total_ms: float | None = None
    p95_quality_filter_total_ms: float | None = None
    p50_db_write_ms: float | None = None
    p95_db_write_ms: float | None = None
    p50_db_commit_ms: float | None = None
    p95_db_commit_ms: float | None = None
    p50_artifact_publish_ms: float | None = None
    p95_artifact_publish_ms: float | None = None
    average_reject_rate: float | None = None
    average_professor_grade_score: float | None = None
    average_commercial_quality_score: float | None = None
    llm_judge_enabled: bool = False
    generation_model: str | None = None
    generation_model_mismatch_warning: str | None = None
    total_llm_input_tokens: int = 0
    total_llm_output_tokens: int = 0
    total_llm_tokens: int = 0
    total_estimated_cost_krw: float = 0.0
    generation_model_counts: dict[str, int] = Field(default_factory=dict)
    token_usage_by_model: dict[str, dict[str, int]] = Field(default_factory=dict)
    cost_by_model: dict[str, float] = Field(default_factory=dict)
    cost_by_case: dict[str, float] = Field(default_factory=dict)
    highest_cost_cases: list[dict[str, Any]] = Field(default_factory=list)
    highest_wasted_candidate_cases: list[dict[str, Any]] = Field(default_factory=list)
    judge_model: str | None = None
    judge_same_model_warning: bool = False
    judge_same_family_warning: bool = False
    judge_independence_notes: list[str] = Field(default_factory=list)
    average_llm_judge_overall_score: float | None = None
    llm_judge_action_counts: dict[str, int] = Field(default_factory=dict)
    answer_verification_action_counts: dict[str, int] = Field(default_factory=dict)
    answer_correctness_issue_count: int = 0
    average_evidence_obligation_satisfaction: float | None = None
    missing_answer_evidence_count: int = 0
    missing_explanation_evidence_count: int = 0
    missing_formula_or_rule_count: int = 0
    commercial_score_band_counts: dict[str, int] = Field(default_factory=dict)
    professor_vs_commercial_disagreement_count: int = 0
    professor_commercial_disagreements: list[dict[str, Any]] = Field(default_factory=list)
    threshold_failure_category_counts: dict[str, int] = Field(default_factory=dict)
    bottleneck_counts: dict[str, int] = Field(default_factory=dict)
    quality_status_counts: dict[str, int] = Field(default_factory=dict)
    item_model_id_counts: dict[str, int] = Field(default_factory=dict)
    professor_score_band_counts: dict[str, int] = Field(default_factory=dict)
    commercial_score_band_counts: dict[str, int] = Field(default_factory=dict)
    professor_vs_commercial_disagreement_count: int = 0
    professor_commercial_disagreements: list[dict[str, Any]] = Field(default_factory=list)
    high_rigor_operation_counts: dict[str, int] = Field(default_factory=dict)
    low_quality_problem_count: int = 0
    medium_quality_problem_count: int = 0
    high_quality_problem_count: int = 0
    missing_diagnostics_count: int = 0
    missing_rubric_count: int = 0
    low_source_coverage_count: int = 0
    average_source_term_coverage: float | None = None
    average_expected_problem_term_coverage: float | None = None
    case_stability_summary: dict[str, Any] = Field(default_factory=dict)
    cases: list[LiveProblemGenerationCaseResult]


def load_live_problem_generation_cases(cases_path: Path) -> list[LiveProblemGenerationEvalCase]:
    rows: list[LiveProblemGenerationEvalCase] = []
    with cases_path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                rows.append(LiveProblemGenerationEvalCase.model_validate(json.loads(stripped)))
            except Exception as exc:
                raise ValueError(f"{cases_path}:{line_number} is not a valid live eval case: {exc}") from exc
    return rows


def live_problem_generation_preflight_from_env() -> LiveEvalPreflightReport:
    enabled = os.getenv("PROBLEM_AGENT_LIVE_EVAL_ENABLED", "").lower() == "true"
    cases_path = Path(os.getenv("PROBLEM_AGENT_LIVE_EVAL_CASES") or DEFAULT_LIVE_EVAL_CASES_PATH)
    cases_path_exists = cases_path.exists()
    missing_env_vars: list[str] = []
    warnings: list[str] = []
    cases: list[LiveProblemGenerationEvalCase] = []

    if not enabled:
        missing_env_vars.append("PROBLEM_AGENT_LIVE_EVAL_ENABLED=true")
    if _env_true("PROBLEM_AGENT_LIVE_EVAL_USE_DATABASE_URL"):
        warnings.append(LIVE_EVAL_DATABASE_URL_WARNING)
    if _env_true("PROBLEM_AGENT_LIVE_EVAL_LLM_JUDGE_ENABLED") and not os.getenv("OPENAI_API_KEY"):
        warnings.append(LIVE_EVAL_LLM_JUDGE_KEY_WARNING)
    for env_name in ("RAG_AGENT_URL", "OPENAI_API_KEY"):
        if not os.getenv(env_name):
            missing_env_vars.append(env_name)
    if not os.getenv("PROBLEM_AGENT_LIVE_EVAL_CASES") and not cases_path_exists:
        missing_env_vars.append("PROBLEM_AGENT_LIVE_EVAL_CASES")

    if cases_path_exists:
        try:
            cases = load_live_problem_generation_cases(cases_path)
        except Exception as exc:
            warnings.append(f"Could not load live eval cases: {exc}")
    else:
        warnings.append(f"Live eval cases path does not exist: {cases_path}")

    placeholder_case_ids, placeholder_document_ids = _placeholder_case_details(cases)
    if placeholder_case_ids:
        warnings.append("Replace REPLACE_WITH placeholders before running live evaluation.")
    if not cases and cases_path_exists:
        warnings.append("Live eval cases file contains no cases.")

    can_run = (
        enabled
        and not missing_env_vars
        and cases_path_exists
        and bool(cases)
        and not placeholder_case_ids
    )
    return LiveEvalPreflightReport(
        enabled=enabled,
        can_run=can_run,
        missing_env_vars=list(dict.fromkeys(missing_env_vars)),
        placeholder_case_ids=placeholder_case_ids,
        placeholder_document_ids=placeholder_document_ids,
        cases_path_exists=cases_path_exists,
        case_count=len(cases),
        warnings=warnings,
    )


def run_live_problem_generation_eval(
    *,
    cases_path: Path,
    output_dir: Path,
    settings: Settings,
    fail_on_threshold: bool = False,
    compare_baseline_search: bool = False,
    search_query_mode_sweep: bool = False,
    human_review_export_mode: Literal["full", "redacted"] = "full",
    repeat_count: int = 1,
    llm_judge_enabled: bool = False,
    llm_judge: object | None = None,
    judge_model: str | None = None,
    answer_verification_enabled: bool = False,
    answer_verifier: object | None = None,
    search_service: object | None = None,
    problem_agent: object | None = None,
    artifact_publisher: object | None = None,
    rejected_candidate_export_mode: Literal["redacted", "full"] = "redacted",
    rejected_candidate_artifact_writer: RejectedCandidateArtifactWriter | None = None,
) -> LiveProblemGenerationEvalReport:
    cases = load_live_problem_generation_cases(cases_path)
    repeat_count = _normalize_repeat_count(repeat_count)
    output_dir.mkdir(parents=True, exist_ok=True)
    rejected_candidate_artifact_writer = rejected_candidate_artifact_writer or RejectedCandidateArtifactWriter(
        output_dir,
        export_mode=rejected_candidate_export_mode,
    )

    results: list[LiveProblemGenerationCaseResult] = []
    with _eval_db_session(output_dir=output_dir, settings=settings) as db:
        for case in cases:
            for repeat_index in range(repeat_count):
                case_started = time.perf_counter()
                try:
                    result = _run_live_eval_case(
                        db=db,
                        case=case,
                        repeat_index=repeat_index,
                        settings=settings,
                        fail_on_threshold=fail_on_threshold,
                        compare_baseline_search=compare_baseline_search,
                        search_query_mode_sweep=search_query_mode_sweep,
                        llm_judge_enabled=llm_judge_enabled,
                        llm_judge=llm_judge,
                        judge_model=judge_model,
                        answer_verification_enabled=answer_verification_enabled,
                        answer_verifier=answer_verifier,
                        search_service=search_service,
                        problem_agent=problem_agent,
                        artifact_publisher=artifact_publisher,
                        rejected_candidate_artifact_writer=rejected_candidate_artifact_writer,
                    )
                except Exception as exc:
                    try:
                        db.rollback()
                    except Exception:
                        pass
                    result = _failed_case_result(
                        case=case,
                        repeat_index=repeat_index,
                        request=_safe_request_from_case(case),
                        exc=exc,
                        elapsed_ms=_elapsed_ms(case_started),
                        search_query_mode=_search_query_mode_from_settings(settings),
                        cost_profile=_normalize_cost_profile(settings.problem_agent_cost_profile),
                    )
                results.append(result)

    case_by_id = {case.id: case for case in cases}
    case_stability_summary = _case_stability_summary(results=results, cases_by_id=case_by_id)
    _apply_stability_thresholds(results=results, stability_summary=case_stability_summary)
    failed = [result for result in results if not result.threshold_passed]
    execution_counts = Counter(result.execution_status for result in results if result.execution_status != "completed")
    judge_independence = _judge_independence_metadata(
        settings=settings,
        llm_judge_enabled=llm_judge_enabled,
        judge_model=judge_model,
    )
    llm_usage_report = _llm_usage_report_summary(
        results=results,
        configured_generation_model=judge_independence.get("generation_model"),
    )
    report = LiveProblemGenerationEvalReport(
        report_schema_version=LIVE_EVAL_REPORT_SCHEMA_VERSION,
        generated_at=datetime.now(timezone.utc),
        code_version=LIVE_EVAL_REPORT_SCHEMA_VERSION,
        git_commit=_git_commit_short(),
        cases_sha256=_file_sha256(cases_path),
        settings_snapshot=_live_eval_settings_snapshot(settings),
        cases_path=str(cases_path),
        output_dir=str(output_dir),
        search_query_mode=_search_query_mode_from_settings(settings),
        cost_profile=_normalize_cost_profile(settings.problem_agent_cost_profile),
        cost_profile_warning=_cost_profile_warning(settings),
        human_review_export_mode=_normalize_human_review_export_mode(human_review_export_mode),
        repeat_count=repeat_count,
        logical_case_count=len(cases),
        total_run_count=len(results),
        case_count=len(results),
        passed_count=sum(1 for result in results if result.threshold_passed),
        failed_count=len(failed),
        failed_execution_count=sum(execution_counts.values()),
        generation_failed_count=execution_counts.get("generation_failed", 0),
        search_failed_count=execution_counts.get("search_failed", 0),
        db_failed_count=execution_counts.get("db_failed", 0),
        average_total_ms=_average([result.total_ms for result in results]),
        p50_total_ms=_percentile([result.total_ms for result in results], 50),
        p95_total_ms=_percentile([result.total_ms for result in results], 95),
        p50_search_ms=_percentile([result.search_ms for result in results], 50),
        p95_search_ms=_percentile([result.search_ms for result in results], 95),
        p50_candidate_generation_total_ms=_percentile(
            [result.candidate_generation_total_ms for result in results],
            50,
        ),
        p95_candidate_generation_total_ms=_percentile(
            [result.candidate_generation_total_ms for result in results],
            95,
        ),
        p50_quality_filter_total_ms=_percentile(
            [result.quality_filter_total_ms for result in results],
            50,
        ),
        p95_quality_filter_total_ms=_percentile(
            [result.quality_filter_total_ms for result in results],
            95,
        ),
        p50_db_write_ms=_percentile([result.db_write_ms for result in results], 50),
        p95_db_write_ms=_percentile([result.db_write_ms for result in results], 95),
        p50_db_commit_ms=_percentile([result.db_commit_ms for result in results], 50),
        p95_db_commit_ms=_percentile([result.db_commit_ms for result in results], 95),
        p50_artifact_publish_ms=_percentile([result.artifact_publish_ms for result in results], 50),
        p95_artifact_publish_ms=_percentile([result.artifact_publish_ms for result in results], 95),
        average_reject_rate=_average([result.reject_rate for result in results]),
        average_professor_grade_score=_average([result.average_professor_grade_score for result in results]),
        average_commercial_quality_score=_average([result.commercial_quality_score for result in results]),
        llm_judge_enabled=llm_judge_enabled,
        **judge_independence,
        **llm_usage_report,
        average_llm_judge_overall_score=_average(
            [judge.overall_score for result in results for judge in result.llm_judge_results]
        ),
        llm_judge_action_counts=_merge_counter(result.llm_judge_action_counts for result in results),
        answer_verification_action_counts=_merge_counter(
            result.answer_verification_action_counts for result in results
        ),
        answer_correctness_issue_count=sum(result.answer_correctness_issue_count for result in results),
        average_evidence_obligation_satisfaction=_average(
            [
                diagnostic.evidence_obligation_satisfaction
                for result in results
                for diagnostic in result.problem_quality_diagnostics
            ]
        ),
        missing_answer_evidence_count=sum(
            1
            for result in results
            for diagnostic in result.problem_quality_diagnostics
            if diagnostic.answer_supported is False
        ),
        missing_explanation_evidence_count=sum(
            1
            for result in results
            for diagnostic in result.problem_quality_diagnostics
            if diagnostic.explanation_supported is False
        ),
        missing_formula_or_rule_count=sum(
            1
            for result in results
            for diagnostic in result.problem_quality_diagnostics
            if diagnostic.source_formula_or_rule_cited is False
        ),
        bottleneck_counts=dict(Counter(result.bottleneck_component for result in results if result.bottleneck_component)),
        quality_status_counts=_merge_counter(result.quality_status_counts for result in results),
        item_model_id_counts=_merge_counter(result.item_model_id_counts for result in results),
        professor_score_band_counts=_merge_counter(result.professor_score_band_counts for result in results),
        commercial_score_band_counts=_merge_counter(result.commercial_quality_band_counts for result in results),
        professor_vs_commercial_disagreement_count=sum(
            result.professor_vs_commercial_disagreement_count for result in results
        ),
        professor_commercial_disagreements=[
            item for result in results for item in result.professor_commercial_disagreements
        ],
        threshold_failure_category_counts={
            "quality": sum(len(result.threshold_failures_quality) for result in results),
            "performance": sum(len(result.threshold_failures_performance) for result in results),
            "stability": sum(len(result.threshold_failures_stability) for result in results),
        },
        high_rigor_operation_counts=_merge_counter(result.high_rigor_operation_counts for result in results),
        low_quality_problem_count=sum(result.low_quality_problem_count for result in results),
        medium_quality_problem_count=sum(result.medium_quality_problem_count for result in results),
        high_quality_problem_count=sum(result.high_quality_problem_count for result in results),
        missing_diagnostics_count=sum(result.missing_diagnostics_count for result in results),
        missing_rubric_count=sum(result.missing_rubric_count for result in results),
        low_source_coverage_count=sum(result.low_source_coverage_count for result in results),
        average_source_term_coverage=_average([result.average_source_term_coverage for result in results]),
        average_expected_problem_term_coverage=_average(
            [result.average_expected_problem_term_coverage for result in results]
        ),
        case_stability_summary=case_stability_summary,
        cases=results,
    )
    _write_reports(report=report, output_dir=output_dir)
    if fail_on_threshold and failed:
        failures = [
            f"{result.case_id}: {'; '.join(result.threshold_failures)}"
            for result in failed
        ]
        raise AssertionError("Live problem generation thresholds failed: " + " | ".join(failures))
    return report


def run_live_problem_generation_eval_from_env() -> LiveProblemGenerationEvalReport:
    settings = get_settings()
    live_cost_profile = os.getenv("PROBLEM_AGENT_LIVE_EVAL_COST_PROFILE")
    if live_cost_profile:
        settings = settings.model_copy(
            update={"problem_agent_cost_profile": _normalize_cost_profile(live_cost_profile)}
        )
    if _normalize_cost_profile(settings.problem_agent_cost_profile) == "cheap":
        settings = settings.model_copy(update={"problem_agent_answer_verification_llm_enabled": False})
    cases_path = Path(os.getenv("PROBLEM_AGENT_LIVE_EVAL_CASES") or DEFAULT_LIVE_EVAL_CASES_PATH)
    output_dir = Path(os.getenv("PROBLEM_AGENT_LIVE_EVAL_OUTPUT_DIR", "evals/reports"))
    fail_on_threshold = os.getenv("PROBLEM_AGENT_LIVE_EVAL_FAIL_ON_THRESHOLD", "").lower() == "true"
    compare_baseline_search = (
        os.getenv("PROBLEM_AGENT_LIVE_EVAL_COMPARE_BASELINE_SEARCH", "").lower() == "true"
    )
    search_query_mode_sweep = _env_true("PROBLEM_AGENT_LIVE_EVAL_SEARCH_QUERY_MODE_SWEEP")
    llm_judge_enabled = _env_true("PROBLEM_AGENT_LIVE_EVAL_LLM_JUDGE_ENABLED")
    if _normalize_cost_profile(settings.problem_agent_cost_profile) == "cheap":
        llm_judge_enabled = False
    judge_model = os.getenv("PROBLEM_AGENT_LIVE_EVAL_JUDGE_MODEL") or None
    answer_verification_enabled = _env_true("PROBLEM_AGENT_LIVE_EVAL_ANSWER_VERIFICATION_ENABLED")
    repeat_count = _normalize_repeat_count(os.getenv("PROBLEM_AGENT_LIVE_EVAL_REPEAT_COUNT") or 1)
    human_review_export_mode = _normalize_human_review_export_mode(
        os.getenv("PROBLEM_AGENT_LIVE_EVAL_HUMAN_REVIEW_EXPORT_MODE") or "full"
    )
    rejected_candidate_export_mode = _normalize_rejected_candidate_export_mode(
        os.getenv("PROBLEM_AGENT_LIVE_EVAL_REJECTED_CANDIDATE_EXPORT_MODE") or "redacted"
    )
    return run_live_problem_generation_eval(
        cases_path=cases_path,
        output_dir=output_dir,
        settings=settings,
        fail_on_threshold=fail_on_threshold,
        compare_baseline_search=compare_baseline_search,
        search_query_mode_sweep=search_query_mode_sweep,
        human_review_export_mode=human_review_export_mode,
        repeat_count=repeat_count,
        llm_judge_enabled=llm_judge_enabled,
        judge_model=judge_model,
        answer_verification_enabled=answer_verification_enabled,
        rejected_candidate_export_mode=rejected_candidate_export_mode,
    )


def validate_live_eval_report_freshness(
    report: LiveProblemGenerationEvalReport,
    cases_path: Path,
) -> list[str]:
    warnings: list[str] = []
    if report.report_schema_version != LIVE_EVAL_REPORT_SCHEMA_VERSION:
        warnings.append(
            f"report schema version is stale or missing: {report.report_schema_version!r} "
            f"!= {LIVE_EVAL_REPORT_SCHEMA_VERSION!r}"
        )
    current_cases_sha256 = _file_sha256(cases_path)
    if report.cases_sha256 != current_cases_sha256:
        warnings.append("cases_sha256 does not match current cases file")
    try:
        cases_mtime = datetime.fromtimestamp(cases_path.stat().st_mtime, tz=timezone.utc)
    except OSError:
        warnings.append("cases file is missing")
    else:
        generated_at = report.generated_at
        if generated_at.tzinfo is None:
            generated_at = generated_at.replace(tzinfo=timezone.utc)
        if generated_at < cases_mtime:
            warnings.append("report generated_at is older than cases file modified time")
    if report.case_count == 0 or not report.cases:
        warnings.append("report has zero cases")
    return warnings


def _file_sha256(path: Path) -> str | None:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def _git_commit_short() -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
            timeout=2,
        )
    except Exception:
        return None
    commit = result.stdout.strip()
    return commit or None


def _live_eval_settings_snapshot(settings: Settings) -> dict[str, str]:
    field_names = (
        "problem_agent_search_query_mode",
        "problem_agent_generation_context_packing_enabled",
        "problem_agent_generation_context_max_chunks",
        "problem_agent_generation_context_min_chunks",
        "problem_agent_use_domain_general_kernels",
        "problem_agent_cost_profile",
        "problem_agent_allow_premium_escalation",
        "problem_agent_high_rigor_mcq_min_candidates",
        "problem_agent_high_rigor_mcq_retry_count",
        "llm_provider",
        "problem_model",
        "problem_quality_model",
        "llm_reasoning_effort_problem",
        "llm_reasoning_effort_problem_quality",
    )
    return {field_name: str(getattr(settings, field_name)) for field_name in field_names}


def _run_live_eval_case(
    *,
    db: Session,
    case: LiveProblemGenerationEvalCase,
    repeat_index: int,
    settings: Settings,
    fail_on_threshold: bool,
    compare_baseline_search: bool,
    search_query_mode_sweep: bool,
    llm_judge_enabled: bool,
    llm_judge: object | None,
    judge_model: str | None,
    answer_verification_enabled: bool,
    answer_verifier: object | None,
    search_service: object | None,
    problem_agent: object | None,
    artifact_publisher: object | None,
    rejected_candidate_artifact_writer: RejectedCandidateArtifactWriter | None = None,
) -> LiveProblemGenerationCaseResult:
    case_started = time.perf_counter()
    request = _request_from_case(case)
    raw_search_service = search_service or SearchService(settings)
    capturing_search = _CapturingSearchService(raw_search_service)
    service = ProblemService(
        db=db,
        search_service=capturing_search,
        problem_agent=problem_agent or ProblemAgent(settings=settings),
        quality_checker=ProblemQualityChecker(),
        artifact_publisher=artifact_publisher or GeneratedArtifactPublisher(settings),
        rejected_candidate_artifact_writer=rejected_candidate_artifact_writer,
        live_eval_case_id=case.id,
        live_eval_repeat_index=repeat_index,
        settings=settings,
    )
    search_query_mode = service._search_query_mode()
    search_comparison = None
    if compare_baseline_search:
        search_comparison = _compare_baseline_and_enhanced_search(
            case=case,
            request=request,
            service=service,
            search_service=raw_search_service,
        )
        capturing_search.prime(
            query=search_comparison["enhanced_query"],
            chunks=search_comparison["enhanced_chunks"],
        )
    query_mode_sweep_result = (
        _compare_search_query_modes(
            case=case,
            request=request,
            service=service,
            search_service=raw_search_service,
        )
        if search_query_mode_sweep
        else {}
    )

    try:
        batch = service.generate_problem_batch(user_id=f"live_eval_{case.id}_r{repeat_index}", request=request)
    except Exception as exc:
        failure_trace = _live_case_failure_trace(
            case=case,
            request=request,
            chunks=capturing_search.last_chunks,
            exc=exc,
        )
        failed = _failed_case_result(
            case=case,
            repeat_index=repeat_index,
            request=request,
            exc=exc,
            elapsed_ms=_elapsed_ms(case_started),
            search_query_mode=search_query_mode,
            cost_profile=_normalize_cost_profile(settings.problem_agent_cost_profile),
            trace=failure_trace,
        )
        return failed.model_copy(
            update={
                **query_mode_sweep_result,
                **_search_comparison_result_fields(search_comparison),
            }
        )
    chunks = capturing_search.last_chunks
    problems = batch.problems
    performance = batch.quality_summary.performance
    service_internal_search_ms = performance.search_ms if performance else None
    baseline_search_ms = search_comparison["baseline_search_ms"] if search_comparison else None
    enhanced_search_ms = search_comparison["enhanced_search_ms"] if search_comparison else None
    if search_comparison is not None:
        effective_search_ms = enhanced_search_ms
        search_latency_note = "search_ms uses A/B enhanced search latency; ProblemService internal search used primed chunks"
    else:
        effective_search_ms = service_internal_search_ms
        search_latency_note = "search_ms measured inside ProblemService"

    returned_chunk_count = len(chunks)
    unique_returned_chunk_count = len({chunk.chunk_id for chunk in chunks})
    wrong_document_chunk_count = sum(1 for chunk in chunks if chunk.document_id != case.document_id)
    retrieval_metrics = _retrieval_metrics_for_case(case, chunks)
    cited_chunk_count_total = sum(len(problem.source_chunk_ids or []) for problem in problems)
    cited_chunk_count_avg = cited_chunk_count_total / len(problems) if problems else 0.0
    cited_evidence_metrics = _cited_evidence_metrics_for_case(case=case, chunks=chunks, problems=problems)
    generation_context_chunk_ids = (
        list(performance.generation_context_chunk_ids)
        if performance and performance.generation_context_chunk_ids
        else []
    )
    generation_context_metrics = _generation_context_metrics_for_case(
        case=case,
        chunks=chunks,
        generation_context_chunk_ids=generation_context_chunk_ids,
    )
    quality_scores = [
        float(problem.professor_grade_score["final_score"])
        for problem in problems
        if isinstance(problem.professor_grade_score, dict)
        and isinstance(problem.professor_grade_score.get("final_score"), int | float)
    ]
    problem_diagnostics = [
        _problem_quality_diagnostic(
            problem=problem,
            request=request,
            source_terms=case.concepts,
            expected_problem_terms=case.expected_problem_terms,
            expected_problem_term_aliases=case.expected_problem_term_aliases,
        )
        for problem in problems
    ]
    human_review_rows = [
        _human_review_row(
            case=case,
            problem=problem,
            diagnostic=diagnostic,
        )
        for problem, diagnostic in zip(problems, problem_diagnostics, strict=False)
    ]
    answer_verification_reports = (
        _run_answer_verification_for_case(
            request=request,
            problems=problems,
            verifier=answer_verifier,
            settings=settings,
        )
        if answer_verification_enabled
        else {}
    )
    if answer_verification_reports:
        for diagnostic in problem_diagnostics:
            verification_report = answer_verification_reports.get(diagnostic.problem_id)
            if verification_report is None:
                continue
            diagnostic.answer_verification_score = verification_report.answer_correctness_score
            diagnostic.answer_verification_action = verification_report.recommended_action
            diagnostic.answer_verification_issues = list(verification_report.issues)
            if verification_report.recommended_action == "reject":
                diagnostic.warning_flags.append("answer_verification_reject")
                diagnostic.quality_risk_level = "high"
            elif verification_report.recommended_action == "needs_review":
                diagnostic.warning_flags.append("answer_verification_needs_review")
                if diagnostic.quality_risk_level == "low":
                    diagnostic.quality_risk_level = "medium"
    cited_evidence_missing = bool(case.expected_chunk_ids) and not cited_evidence_metrics["cited_expected_chunk_ids"]
    for diagnostic in problem_diagnostics:
        score, band = _commercial_quality_score_for_diagnostic(
            diagnostic=diagnostic,
            execution_status="completed",
            cited_evidence_missing=cited_evidence_missing,
        )
        diagnostic.commercial_quality_score = score
        diagnostic.commercial_quality_band = band
    llm_judge_results = (
        _run_llm_judge_for_case(
            case=case,
            request=request,
            problems=problems,
            llm_judge=llm_judge,
            settings=settings,
            judge_model=judge_model,
        )
        if llm_judge_enabled
        else []
    )
    risk_counts = Counter(diagnostic.quality_risk_level for diagnostic in problem_diagnostics)
    professor_score_band_counts = Counter(
        diagnostic.professor_score_band or "unknown" for diagnostic in problem_diagnostics
    )
    commercial_score_band_counts = Counter(
        diagnostic.commercial_quality_band or "unknown" for diagnostic in problem_diagnostics
    )
    professor_commercial_disagreements = _professor_commercial_disagreements(problem_diagnostics)
    high_rigor_operation_counts = Counter(diagnostic.high_rigor_operation_label for diagnostic in problem_diagnostics)
    llm_judge_action_counts = Counter(result.recommended_action for result in llm_judge_results)
    high_rigor_mc_choice_diagnostics_coverage = _high_rigor_mc_choice_diagnostics_coverage(request, problems)
    short_answer_rubric_coverage = _short_answer_rubric_coverage(problems)
    answer_verification_action_counts = Counter(
        report.recommended_action for report in answer_verification_reports.values()
    )
    answer_correctness_issue_count = sum(len(report.issues) for report in answer_verification_reports.values())
    threshold_failures = _threshold_failures(
        case=case,
        request=request,
        generated_count=batch.quality_summary.generated,
        passed_count=batch.quality_summary.passed,
        returned_chunk_count=returned_chunk_count,
        wrong_document_chunk_count=wrong_document_chunk_count,
        cited_chunk_count_avg=cited_chunk_count_avg,
        average_quality_score=_average(quality_scores),
        reject_rate=performance.reject_rate if performance else None,
        total_ms=performance.total_ms if performance else None,
        expected_search_term_coverage=_term_coverage(
            case.expected_search_terms,
            _chunk_text(chunks),
            aliases=case.expected_search_term_aliases,
        ),
        hit_at_k=retrieval_metrics["hit_at_k"],
        mrr_at_k=retrieval_metrics["mrr_at_k"],
        precision_at_k=retrieval_metrics["precision_at_k"],
        source_span_coverage=retrieval_metrics["source_span_coverage"],
        cited_hit_at_k=cited_evidence_metrics["cited_hit_at_k"],
        cited_expected_chunk_recall=cited_evidence_metrics["cited_expected_chunk_recall"],
        cited_expected_chunk_precision=cited_evidence_metrics["cited_expected_chunk_precision"],
        cited_source_span_coverage=cited_evidence_metrics["cited_source_span_coverage"],
        generation_context_hit_at_k=generation_context_metrics["generation_context_hit_at_k"],
        generation_context_expected_chunk_recall=generation_context_metrics[
            "generation_context_expected_chunk_recall"
        ],
        generation_context_source_span_coverage=generation_context_metrics[
            "generation_context_source_span_coverage"
        ],
        expected_problem_term_coverage=_term_coverage(
            case.expected_problem_terms,
            _problem_text(problems),
            aliases=case.expected_problem_term_aliases,
        ),
        high_rigor_operation_counts=dict(high_rigor_operation_counts),
        high_rigor_mc_choice_diagnostics_coverage=high_rigor_mc_choice_diagnostics_coverage,
        short_answer_rubric_coverage=short_answer_rubric_coverage,
        selected_kernel_atom_chunk_ids=performance.selected_kernel_atom_chunk_ids if performance else [],
        generation_context_selected_atom_recall=(
            performance.generation_context_selected_atom_recall if performance else None
        ),
    )
    rejected_verifications = [
        f"{problem_id}: " + "; ".join(report.issues[:3])
        for problem_id, report in answer_verification_reports.items()
        if report.recommended_action == "reject"
    ]
    if rejected_verifications:
        threshold_failures.append(
            "answer verification rejected generated problem: " + " | ".join(rejected_verifications)
        )
    if (
        fail_on_threshold
        and search_comparison is not None
        and search_comparison["enhanced_score"] < search_comparison["baseline_score"] - 0.15
    ):
        threshold_failures.append(
            "enhanced search quality score is more than 0.15 below baseline "
            f"({search_comparison['enhanced_score']:.3f} < {search_comparison['baseline_score']:.3f})"
        )
    bottleneck = _classify_bottleneck(
        total_ms=performance.total_ms if performance else None,
        search_ms=effective_search_ms,
        candidate_generation_total_ms=performance.candidate_generation_total_ms if performance else None,
        quality_filter_total_ms=performance.quality_filter_total_ms if performance else None,
        db_write_ms=performance.db_write_ms if performance else None,
        db_commit_ms=performance.db_commit_ms if performance else None,
        db_refresh_ms=performance.db_refresh_ms if performance else None,
        artifact_publish_ms=performance.artifact_publish_ms if performance else None,
    )
    threshold_categories = _threshold_failure_categories(threshold_failures)

    return LiveProblemGenerationCaseResult(
        case_id=case.id,
        repeat_index=repeat_index,
        repeated_case_group_id=case.id,
        description=case.description,
        document_id=case.document_id,
        concepts=case.concepts,
        generated_problem_ids=[problem.id for problem in problems],
        golden_label_mode=case.golden_label_mode,
        search_query_mode=search_query_mode,
        cost_profile=_normalize_cost_profile(settings.problem_agent_cost_profile),
        search_query=capturing_search.last_kwargs.get("query") if capturing_search.last_kwargs else None,
        requested_count=request.count,
        generated_count=batch.quality_summary.generated,
        passed_count=batch.quality_summary.passed,
        rejected_count=batch.quality_summary.rejected,
        discarded_count=batch.quality_summary.discarded,
        actual_retry_count=performance.actual_retry_count if performance else 0,
        reject_rate=performance.reject_rate if performance else None,
        pass_rate=performance.pass_rate if performance else None,
        actual_generation_models=performance.actual_generation_models if performance else [],
        total_llm_input_tokens=performance.total_llm_input_tokens if performance else 0,
        total_llm_output_tokens=performance.total_llm_output_tokens if performance else 0,
        total_llm_tokens=performance.total_llm_tokens if performance else 0,
        total_estimated_cost_krw=performance.total_estimated_cost_krw if performance else 0.0,
        llm_call_count=performance.llm_call_count if performance else 0,
        wasted_candidate_ratio=performance.approximate_wasted_candidate_ratio if performance else None,
        generation_attempts=performance.attempts if performance else [],
        total_ms=performance.total_ms if performance else None,
        search_ms=effective_search_ms,
        bottleneck_component=bottleneck["component"],
        bottleneck_component_ms=bottleneck["component_ms"],
        bottleneck_component_ratio=bottleneck["component_ratio"],
        baseline_search_ms=baseline_search_ms,
        enhanced_search_ms=enhanced_search_ms,
        effective_search_ms=effective_search_ms,
        service_internal_search_ms=service_internal_search_ms,
        search_latency_note=search_latency_note,
        planning_ms=performance.planning_ms if performance else None,
        candidate_generation_total_ms=performance.candidate_generation_total_ms if performance else None,
        quality_filter_total_ms=performance.quality_filter_total_ms if performance else None,
        db_write_ms=performance.db_write_ms if performance else None,
        db_commit_ms=performance.db_commit_ms if performance else None,
        db_refresh_ms=performance.db_refresh_ms if performance else None,
        artifact_publish_ms=performance.artifact_publish_ms if performance else None,
        artifact_publish_success_count=performance.artifact_publish_success_count if performance else 0,
        artifact_publish_failure_count=performance.artifact_publish_failure_count if performance else 0,
        returned_chunk_count=returned_chunk_count,
        unique_returned_chunk_count=unique_returned_chunk_count,
        empty_chunk_count=sum(1 for chunk in chunks if not chunk.content.strip()),
        wrong_document_chunk_count=wrong_document_chunk_count,
        average_chunk_content_chars=_average([len(chunk.content) for chunk in chunks]) or 0.0,
        metadata_score_summary=_metadata_score_summary(chunks),
        concept_overlap_ratio=_concept_overlap_ratio(case.concepts, chunks),
        cited_chunk_count_total=cited_chunk_count_total,
        cited_chunk_count_avg=cited_chunk_count_avg,
        expected_search_term_coverage=_term_coverage(
            case.expected_search_terms,
            _chunk_text(chunks),
            aliases=case.expected_search_term_aliases,
        ),
        hit_at_k=retrieval_metrics["hit_at_k"],
        mrr_at_k=retrieval_metrics["mrr_at_k"],
        precision_at_k=retrieval_metrics["precision_at_k"],
        expected_page_hit=retrieval_metrics["expected_page_hit"],
        source_span_coverage=retrieval_metrics["source_span_coverage"],
        irrelevant_term_hit_count=retrieval_metrics["irrelevant_term_hit_count"],
        cited_expected_chunk_recall=cited_evidence_metrics["cited_expected_chunk_recall"],
        cited_expected_chunk_precision=cited_evidence_metrics["cited_expected_chunk_precision"],
        cited_hit_at_k=cited_evidence_metrics["cited_hit_at_k"],
        cited_source_span_coverage=cited_evidence_metrics["cited_source_span_coverage"],
        cited_expected_chunk_ids=cited_evidence_metrics["cited_expected_chunk_ids"],
        uncited_expected_chunk_ids=cited_evidence_metrics["uncited_expected_chunk_ids"],
        cited_non_expected_chunk_ids=cited_evidence_metrics["cited_non_expected_chunk_ids"],
        generation_context_chunk_count=(
            performance.generation_context_chunk_count
            if performance
            else generation_context_metrics["generation_context_chunk_count"]
        ),
        generation_context_chunk_ids=generation_context_chunk_ids,
        generation_context_expected_chunk_recall=generation_context_metrics[
            "generation_context_expected_chunk_recall"
        ],
        generation_context_expected_chunk_precision=generation_context_metrics[
            "generation_context_expected_chunk_precision"
        ],
        generation_context_hit_at_k=generation_context_metrics["generation_context_hit_at_k"],
        generation_context_source_span_coverage=generation_context_metrics[
            "generation_context_source_span_coverage"
        ],
        retrieved_to_context_reduction_ratio=(
            performance.generation_context_reduction_ratio
            if performance
            else generation_context_metrics["retrieved_to_context_reduction_ratio"]
        ),
        raw_content_atom_count=performance.raw_content_atom_count if performance else 0,
        raw_content_atom_type_counts=performance.raw_content_atom_type_counts if performance else {},
        selected_kernel_atom_ids=performance.selected_kernel_atom_ids if performance else [],
        selected_kernel_atom_chunk_ids=performance.selected_kernel_atom_chunk_ids if performance else [],
        rescued_kernel_atom_chunk_count=performance.rescued_kernel_atom_chunk_count if performance else 0,
        generation_context_selected_atom_recall=(
            performance.generation_context_selected_atom_recall if performance else None
        ),
        generation_context_atom_type_counts=performance.generation_context_atom_type_counts if performance else {},
        kernel_atom_dropped_count=_kernel_atom_dropped_count(
            selected_kernel_atom_chunk_ids=performance.selected_kernel_atom_chunk_ids if performance else [],
            generation_context_chunk_ids=generation_context_chunk_ids,
        ),
        problem_kernel_type=performance.problem_kernel_type if performance else None,
        kernel_planning_failure_reason=performance.kernel_planning_failure_reason if performance else None,
        expected_problem_term_coverage=_term_coverage(
            case.expected_problem_terms,
            _problem_text(problems),
            aliases=case.expected_problem_term_aliases,
        ),
        average_quality_score=_average(quality_scores),
        average_professor_grade_score=_average(quality_scores),
        commercial_quality_score=_average(
            [diagnostic.commercial_quality_score for diagnostic in problem_diagnostics]
        ),
        commercial_quality_band_counts=dict(commercial_score_band_counts),
        source_term_coverage=_term_coverage(case.concepts, _problem_text(problems)),
        high_rigor_item_model_id_coverage=_high_rigor_item_model_id_coverage(request, problems),
        high_rigor_mc_choice_diagnostics_coverage=high_rigor_mc_choice_diagnostics_coverage,
        short_answer_rubric_coverage=short_answer_rubric_coverage,
        quality_status_counts=dict(Counter(problem.quality_status for problem in problems)),
        item_model_id_counts=dict(Counter(problem.item_model_id or "none" for problem in problems)),
        professor_score_band_counts=dict(professor_score_band_counts),
        commercial_score_band_counts=dict(commercial_score_band_counts),
        professor_vs_commercial_disagreement_count=len(professor_commercial_disagreements),
        professor_commercial_disagreements=professor_commercial_disagreements,
        high_rigor_operation_counts=dict(high_rigor_operation_counts),
        low_quality_problem_count=risk_counts.get("high", 0),
        medium_quality_problem_count=risk_counts.get("medium", 0),
        high_quality_problem_count=risk_counts.get("low", 0),
        missing_diagnostics_count=sum(
            1 for diagnostic in problem_diagnostics if "missing_choice_diagnostics" in diagnostic.warning_flags
        ),
        missing_rubric_count=sum(1 for diagnostic in problem_diagnostics if "missing_rubric" in diagnostic.warning_flags),
        low_source_coverage_count=sum(
            1 for diagnostic in problem_diagnostics if "low_source_term_coverage" in diagnostic.warning_flags
        ),
        average_source_term_coverage=_average(
            [diagnostic.source_term_coverage for diagnostic in problem_diagnostics]
        ),
        average_expected_problem_term_coverage=_average(
            [diagnostic.expected_problem_term_coverage for diagnostic in problem_diagnostics]
        ),
        problem_quality_diagnostics=problem_diagnostics,
        llm_judge_results=llm_judge_results,
        average_llm_judge_overall_score=_average([result.overall_score for result in llm_judge_results]),
        llm_judge_action_counts=dict(llm_judge_action_counts),
        answer_verification_action_counts=dict(answer_verification_action_counts),
        answer_correctness_issue_count=answer_correctness_issue_count,
        human_review_rows=human_review_rows,
        warning_count=len(batch.quality_summary.warnings),
        warnings=batch.quality_summary.warnings,
        threshold_passed=not threshold_failures,
        threshold_failures=threshold_failures,
        threshold_failures_quality=threshold_categories["quality"],
        threshold_failures_performance=threshold_categories["performance"],
        threshold_failures_stability=threshold_categories["stability"],
        **query_mode_sweep_result,
        **_search_comparison_result_fields(search_comparison),
    )


def _request_from_case(case: LiveProblemGenerationEvalCase) -> GenerateProblemRequest:
    payload = {
        "document_id": case.document_id,
        "concepts": case.concepts,
        **case.request,
    }
    return GenerateProblemRequest.model_validate(payload)


def _safe_request_from_case(case: LiveProblemGenerationEvalCase) -> GenerateProblemRequest | None:
    try:
        return _request_from_case(case)
    except Exception:
        return None


def _live_case_failure_trace(
    *,
    case: LiveProblemGenerationEvalCase,
    request: GenerateProblemRequest | None,
    chunks: list[RetrievedChunk],
    exc: Exception,
) -> dict[str, Any]:
    trace = dict(getattr(exc, "trace", {}) or {})
    trace["chunks"] = list(chunks or [])
    if chunks:
        trace.setdefault("returned_chunk_count", len(chunks))
        trace.setdefault("unique_returned_chunk_count", len({chunk.chunk_id for chunk in chunks}))
        trace.setdefault("retrieval_metrics", _retrieval_metrics_for_case(case, chunks))
    if request is not None:
        trace.setdefault("search_query", trace.get("search_query"))
    if trace.get("selected_kernel_atom_chunk_ids"):
        generation_context_chunk_ids = list(trace.get("generation_context_chunk_ids") or [])
        selected_kernel_atom_chunk_ids = list(trace.get("selected_kernel_atom_chunk_ids") or [])
        trace.setdefault(
            "kernel_atom_dropped_count",
            _kernel_atom_dropped_count(
                selected_kernel_atom_chunk_ids=selected_kernel_atom_chunk_ids,
                generation_context_chunk_ids=generation_context_chunk_ids,
            ),
        )
    message = str(exc)
    rejection_counts = _failure_rejection_category_counts(message)
    if rejection_counts:
        trace.setdefault("rejection_category_counts", rejection_counts)
        trace.setdefault("top_rejection_categories", _failure_top_rejection_categories(message, rejection_counts))
    _, failure_stage = _classify_case_exception(exc)
    trace.setdefault("failure_stage", failure_stage)
    return LiveCaseExecutionTrace.model_validate(trace).to_trace_dict()


def _failed_case_result(
    *,
    case: LiveProblemGenerationEvalCase,
    repeat_index: int = 0,
    request: GenerateProblemRequest | None,
    exc: Exception,
    elapsed_ms: float,
    search_query_mode: str = "compact",
    cost_profile: Literal["cheap", "balanced", "full"] = "balanced",
    trace: dict[str, Any] | None = None,
) -> LiveProblemGenerationCaseResult:
    execution_status, exception_stage = _classify_case_exception(exc)
    exception_message = _compact_exception_message(exc)
    requested_count = request.count if request is not None else _raw_case_count(case)
    threshold_failure = f"case execution failed: {exception_message}"
    trace = trace or {}
    parsed_rejection_counts = _failure_rejection_category_counts(exception_message)
    rejection_counts = dict(trace.get("rejection_category_counts") or parsed_rejection_counts)
    top_categories = list(trace.get("top_rejection_categories") or [])
    if not top_categories:
        top_categories = _failure_top_rejection_categories(exception_message, rejection_counts)
    chunks = trace.get("chunks") or []
    generation_context_chunk_ids = list(trace.get("generation_context_chunk_ids") or [])
    generation_context_metrics = _generation_context_metrics_for_case(
        case=case,
        chunks=chunks,
        generation_context_chunk_ids=generation_context_chunk_ids,
    )
    retrieval_metrics = dict(trace.get("retrieval_metrics") or {})
    for metric_key in (
        "hit_at_k",
        "mrr_at_k",
        "precision_at_k",
        "expected_page_hit",
        "source_span_coverage",
        "irrelevant_term_hit_count",
    ):
        if trace.get(metric_key) is not None:
            retrieval_metrics.setdefault(metric_key, trace.get(metric_key))
    if trace.get("generation_context_expected_chunk_recall") is not None:
        generation_context_metrics["generation_context_expected_chunk_recall"] = trace.get(
            "generation_context_expected_chunk_recall"
        )
    threshold_categories = _threshold_failure_categories([threshold_failure])
    return LiveProblemGenerationCaseResult(
        case_id=case.id,
        repeat_index=repeat_index,
        repeated_case_group_id=case.id,
        description=case.description,
        document_id=case.document_id,
        concepts=case.concepts,
        generated_problem_ids=[],
        golden_label_mode=case.golden_label_mode,
        search_query_mode=search_query_mode,
        cost_profile=cost_profile,
        search_query=trace.get("search_query"),
        requested_count=requested_count,
        generated_count=0,
        passed_count=0,
        rejected_count=0,
        discarded_count=0,
        actual_retry_count=0,
        reject_rate=None,
        pass_rate=None,
        actual_generation_models=list(trace.get("actual_generation_models") or []),
        total_llm_input_tokens=int(trace.get("total_llm_input_tokens") or 0),
        total_llm_output_tokens=int(trace.get("total_llm_output_tokens") or 0),
        total_llm_tokens=int(trace.get("total_llm_tokens") or 0),
        total_estimated_cost_krw=float(trace.get("total_estimated_cost_krw") or 0.0),
        llm_call_count=int(trace.get("llm_call_count") or 0),
        wasted_candidate_ratio=trace.get("approximate_wasted_candidate_ratio"),
        generation_attempts=[
            GenerationAttemptMetrics.model_validate(attempt)
            for attempt in list(trace.get("generation_attempts") or [])
        ],
        total_ms=elapsed_ms,
        search_ms=trace.get("search_ms"),
        returned_chunk_count=int(trace.get("returned_chunk_count") or len(chunks)),
        unique_returned_chunk_count=int(
            trace.get("unique_returned_chunk_count") or len({chunk.chunk_id for chunk in chunks})
        ),
        empty_chunk_count=sum(1 for chunk in chunks if not str(chunk.content or "").strip()),
        wrong_document_chunk_count=sum(1 for chunk in chunks if chunk.document_id != case.document_id),
        average_chunk_content_chars=_average([len(chunk.content) for chunk in chunks]) or 0.0,
        metadata_score_summary=_metadata_score_summary(chunks),
        concept_overlap_ratio=_concept_overlap_ratio(case.concepts, chunks),
        cited_chunk_count_total=0,
        cited_chunk_count_avg=0.0,
        expected_search_term_coverage=_term_coverage(
            case.expected_search_terms,
            _chunk_text(chunks),
            aliases=case.expected_search_term_aliases,
        ),
        hit_at_k=retrieval_metrics.get("hit_at_k"),
        mrr_at_k=retrieval_metrics.get("mrr_at_k"),
        precision_at_k=retrieval_metrics.get("precision_at_k"),
        expected_page_hit=retrieval_metrics.get("expected_page_hit"),
        source_span_coverage=retrieval_metrics.get("source_span_coverage"),
        irrelevant_term_hit_count=int(retrieval_metrics.get("irrelevant_term_hit_count") or 0),
        generation_context_chunk_count=generation_context_metrics["generation_context_chunk_count"],
        generation_context_chunk_ids=generation_context_chunk_ids,
        generation_context_expected_chunk_recall=generation_context_metrics[
            "generation_context_expected_chunk_recall"
        ],
        generation_context_expected_chunk_precision=generation_context_metrics[
            "generation_context_expected_chunk_precision"
        ],
        generation_context_hit_at_k=generation_context_metrics["generation_context_hit_at_k"],
        generation_context_source_span_coverage=generation_context_metrics[
            "generation_context_source_span_coverage"
        ],
        retrieved_to_context_reduction_ratio=generation_context_metrics[
            "retrieved_to_context_reduction_ratio"
        ],
        raw_content_atom_count=int(trace.get("raw_content_atom_count") or 0),
        raw_content_atom_type_counts=dict(trace.get("raw_content_atom_type_counts") or {}),
        selected_kernel_atom_ids=list(trace.get("selected_kernel_atom_ids") or []),
        selected_kernel_atom_chunk_ids=list(trace.get("selected_kernel_atom_chunk_ids") or []),
        rescued_kernel_atom_chunk_count=int(trace.get("rescued_kernel_atom_chunk_count") or 0),
        generation_context_selected_atom_recall=trace.get("generation_context_selected_atom_recall"),
        generation_context_atom_type_counts=dict(trace.get("generation_context_atom_type_counts") or {}),
        kernel_atom_dropped_count=int(trace.get("kernel_atom_dropped_count") or 0),
        problem_kernel_type=trace.get("problem_kernel_type"),
        kernel_planning_failure_reason=trace.get("kernel_planning_failure_reason"),
        expected_problem_term_coverage=0.0 if case.expected_problem_terms else 1.0,
        commercial_quality_score=0.0,
        commercial_quality_band_counts={"reject": 1},
        source_term_coverage=0.0,
        quality_status_counts={},
        item_model_id_counts={},
        warning_count=1,
        warnings=[exception_message],
        threshold_passed=False,
        threshold_failures=[threshold_failure],
        threshold_failures_quality=threshold_categories["quality"],
        threshold_failures_performance=threshold_categories["performance"],
        threshold_failures_stability=threshold_categories["stability"],
        execution_status=execution_status,
        exception_type=type(exc).__name__,
        exception_message=exception_message,
        exception_stage=exception_stage,
        failure_stage=str(trace.get("failure_stage") or exception_stage),
        failure_rejection_category_counts=rejection_counts,
        failure_top_rejection_categories=top_categories,
    )


def _raw_case_count(case: LiveProblemGenerationEvalCase) -> int:
    try:
        return max(0, int(case.request.get("count", 0)))
    except Exception:
        return 0


def _classify_case_exception(
    exc: Exception,
) -> tuple[Literal["generation_failed", "search_failed", "db_failed", "unknown_failed"], str]:
    message = str(exc).lower()
    if isinstance(exc, SearchAgentError) or "search agent" in message or "rag agent" in message:
        return "search_failed", "search"
    if isinstance(exc, SQLAlchemyError) or "database" in message or "sqlalchemy" in message:
        return "db_failed", "db"
    if isinstance(exc, (ValueError, RuntimeError)):
        return "generation_failed", "generation"
    return "unknown_failed", "unknown"


def _compact_exception_message(exc: Exception) -> str:
    message = re.sub(r"\s+", " ", str(exc or "")).strip()
    return message or type(exc).__name__


def _failure_rejection_category_counts(message: str) -> dict[str, int]:
    match = re.search(r"rejection_category_counts=(\{.*?\})", message)
    if not match:
        return {}
    try:
        payload = json.loads(match.group(1))
    except json.JSONDecodeError:
        return {}
    return {
        str(key): int(value)
        for key, value in payload.items()
        if isinstance(value, int | float) and int(value) > 0
    }


def _failure_top_rejection_categories(message: str, counts: dict[str, int]) -> list[str]:
    match = re.search(r"top_rejection_categories=(\[.*?\])", message)
    if match:
        try:
            payload = json.loads(match.group(1))
        except json.JSONDecodeError:
            payload = []
        if isinstance(payload, list):
            return [str(item) for item in payload if str(item).strip()]
    return [category for category, _ in Counter(counts).most_common()]


def live_eval_preflight_skip_message(report: LiveEvalPreflightReport) -> str:
    parts = ["Live problem generation benchmark preflight failed."]
    if report.missing_env_vars:
        parts.append("Missing env vars: " + ", ".join(report.missing_env_vars))
    if report.placeholder_case_ids:
        parts.append("Placeholder case ids: " + ", ".join(report.placeholder_case_ids))
    if report.placeholder_document_ids:
        parts.append("Placeholder document ids: " + ", ".join(report.placeholder_document_ids))
    if not report.cases_path_exists:
        parts.append("Cases file does not exist.")
    if report.warnings:
        parts.append("Warnings: " + " | ".join(report.warnings))
    return " ".join(parts)


def _placeholder_case_details(
    cases: list[LiveProblemGenerationEvalCase],
) -> tuple[list[str], list[str]]:
    case_ids: list[str] = []
    document_ids: list[str] = []
    for case in cases:
        values_to_check = [
            case.document_id,
            *case.concepts,
            *case.expected_search_terms,
            *case.expected_problem_terms,
            *case.expected_search_term_aliases.keys(),
            *[alias for aliases in case.expected_search_term_aliases.values() for alias in aliases],
            *case.expected_problem_term_aliases.keys(),
            *[alias for aliases in case.expected_problem_term_aliases.values() for alias in aliases],
            *case.expected_chunk_ids,
            *case.expected_source_spans,
            *case.irrelevant_terms,
        ]
        if any(_has_placeholder(value) for value in values_to_check):
            case_ids.append(case.id)
        if _has_placeholder(case.document_id):
            document_ids.append(case.document_id)
    return list(dict.fromkeys(case_ids)), list(dict.fromkeys(document_ids))


def _has_placeholder(value: object) -> bool:
    return "REPLACE_WITH" in str(value or "")


@contextmanager
def _eval_db_session(*, output_dir: Path, settings: Settings) -> Iterator[Session]:
    database_url = _eval_database_url(output_dir=output_dir, settings=settings)
    engine_kwargs: dict[str, Any] = {}
    if database_url.startswith("sqlite"):
        engine_kwargs["connect_args"] = {"check_same_thread": False}
        if database_url == "sqlite+pysqlite://":
            engine_kwargs["poolclass"] = StaticPool
    engine = create_engine(database_url, **engine_kwargs)
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
        engine.dispose()


def _eval_database_url(*, output_dir: Path, settings: Settings) -> str:
    if not _env_true("PROBLEM_AGENT_LIVE_EVAL_USE_DATABASE_URL"):
        return f"sqlite+pysqlite:///{output_dir / LIVE_EVAL_DATABASE_NAME}"
    _validate_live_eval_database_url(settings.database_url)
    return settings.database_url


def _validate_live_eval_database_url(database_url: str) -> None:
    if _env_true("PROBLEM_AGENT_LIVE_EVAL_ALLOW_NONLOCAL_DATABASE"):
        return

    lowered = database_url.lower()
    if "prod" in lowered or "production" in lowered:
        raise ValueError(_unsafe_live_eval_database_url_message())
    if lowered.startswith("sqlite"):
        return

    hostname = urlparse(database_url).hostname
    if hostname in {"localhost", "127.0.0.1"}:
        return
    raise ValueError(_unsafe_live_eval_database_url_message())


def _unsafe_live_eval_database_url_message() -> str:
    return (
        "Unsafe live eval DATABASE_URL; by default live evaluation writes to an isolated sqlite DB. "
        "Set PROBLEM_AGENT_LIVE_EVAL_ALLOW_NONLOCAL_DATABASE=true only for a disposable non-production benchmark DB."
    )


def _env_true(name: str) -> bool:
    return os.getenv(name, "").strip().lower() == "true"


def _search_query_mode_from_settings(settings: Settings) -> str:
    mode = str(getattr(settings, "problem_agent_search_query_mode", "compact") or "compact").strip().lower()
    return mode if mode in {"compact", "expanded", "hybrid"} else "compact"


def _normalize_cost_profile(value: str | None) -> Literal["cheap", "balanced", "full"]:
    profile = str(value or "balanced").strip().lower()
    if profile in {"cheap", "balanced", "full"}:
        return profile  # type: ignore[return-value]
    return "balanced"


def _cost_profile_warning(settings: Settings) -> str | None:
    if _normalize_cost_profile(settings.problem_agent_cost_profile) == "full":
        return "full cost profile is enabled; high-rigor generation may use premium models and higher retry counts"
    return None


def _judge_independence_metadata(
    *,
    settings: Settings,
    llm_judge_enabled: bool,
    judge_model: str | None,
) -> dict[str, Any]:
    generation_model = str(getattr(settings, "problem_model", "") or "").strip() or None
    effective_judge_model = (
        str(judge_model or getattr(settings, "problem_quality_model", "") or "").strip()
        if llm_judge_enabled
        else None
    )
    same_model = False
    same_family = False
    notes: list[str] = []
    if generation_model and effective_judge_model:
        same_model = generation_model.strip().lower() == effective_judge_model.strip().lower()
        generation_family = _model_family(generation_model)
        judge_family = _model_family(effective_judge_model)
        same_family = bool(generation_family and judge_family and generation_family == judge_family)
        if same_model:
            notes.append("LLM judge uses the same model as generation; treat judge score as weak evidence.")
        if same_family:
            notes.append("LLM judge appears to be same model family; use human review for release decision.")
    return {
        "generation_model": generation_model,
        "judge_model": effective_judge_model,
        "judge_same_model_warning": same_model,
        "judge_same_family_warning": same_family,
        "judge_independence_notes": notes,
    }


def _llm_usage_report_summary(
    *,
    results: list[LiveProblemGenerationCaseResult],
    configured_generation_model: str | None,
) -> dict[str, Any]:
    model_counts: Counter[str] = Counter()
    token_usage_by_model: dict[str, dict[str, int]] = {}
    cost_by_model: dict[str, float] = {}
    for result in results:
        for attempt in result.generation_attempts:
            if not attempt.model:
                continue
            model = attempt.model
            model_counts[model] += 1
            token_usage = token_usage_by_model.setdefault(
                model,
                {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
            )
            token_usage["input_tokens"] += int(attempt.input_tokens or 0)
            token_usage["output_tokens"] += int(attempt.output_tokens or 0)
            token_usage["total_tokens"] += int(attempt.total_tokens or 0)
            cost_by_model[model] = round(
                cost_by_model.get(model, 0.0) + float(attempt.estimated_cost_krw or 0.0),
                6,
            )

    cost_by_case = {
        result.case_id: round(float(result.total_estimated_cost_krw or 0.0), 6)
        for result in results
    }
    highest_cost_cases = [
        {
            "case_id": result.case_id,
            "total_estimated_cost_krw": round(float(result.total_estimated_cost_krw or 0.0), 6),
            "total_llm_tokens": result.total_llm_tokens,
            "actual_generation_models": result.actual_generation_models,
        }
        for result in sorted(results, key=lambda item: item.total_estimated_cost_krw or 0.0, reverse=True)
        if result.total_estimated_cost_krw
    ][:5]
    highest_wasted_candidate_cases = [
        {
            "case_id": result.case_id,
            "wasted_candidate_ratio": result.wasted_candidate_ratio,
            "generated_count": result.generated_count,
            "rejected_count": result.rejected_count,
        }
        for result in sorted(results, key=lambda item: item.wasted_candidate_ratio or 0.0, reverse=True)
        if result.wasted_candidate_ratio is not None
    ][:5]
    actual_models = set(model_counts)
    configured_model = str(configured_generation_model or "").strip()
    mismatch_warning = None
    if actual_models and configured_model and actual_models != {configured_model}:
        mismatch_warning = (
            "configured generation model differs from actual LLM model used; "
            "high-rigor routing may be using problem_quality_model"
        )
    return {
        "generation_model_mismatch_warning": mismatch_warning,
        "total_llm_input_tokens": sum(result.total_llm_input_tokens for result in results),
        "total_llm_output_tokens": sum(result.total_llm_output_tokens for result in results),
        "total_llm_tokens": sum(result.total_llm_tokens for result in results),
        "total_estimated_cost_krw": round(
            sum(float(result.total_estimated_cost_krw or 0.0) for result in results),
            6,
        ),
        "generation_model_counts": dict(model_counts),
        "token_usage_by_model": token_usage_by_model,
        "cost_by_model": cost_by_model,
        "cost_by_case": cost_by_case,
        "highest_cost_cases": highest_cost_cases,
        "highest_wasted_candidate_cases": highest_wasted_candidate_cases,
    }


def _model_family(model: str | None) -> str | None:
    normalized = str(model or "").strip().lower()
    if not normalized:
        return None
    if normalized.startswith("gpt"):
        return "gpt"
    if normalized.startswith("gemini"):
        return "gemini"
    return normalized.split("-", 1)[0]


def _compare_baseline_and_enhanced_search(
    *,
    case: LiveProblemGenerationEvalCase,
    request: GenerateProblemRequest,
    service: ProblemService,
    search_service: object,
) -> dict[str, Any]:
    baseline_query = " ".join(request.concepts)
    enhanced_query = service._build_search_query(request)
    high_rigor_profile = service.high_rigor_planner.plan(request=request)
    top_k = service._search_top_k(request, high_rigor_profile)
    include_images = service._visual_context_requested(request)
    min_returned_chunks = case.min_returned_chunks if case.min_returned_chunks is not None else 1

    baseline_started = time.perf_counter()
    baseline_chunks = search_service.search_chunks(
        document_id=request.document_id,
        concepts=request.concepts,
        difficulty=request.difficulty.value,
        query=baseline_query,
        top_k=top_k,
        include_images=include_images,
    )
    baseline_search_ms = _elapsed_ms(baseline_started)
    enhanced_started = time.perf_counter()
    enhanced_chunks = search_service.search_chunks(
        document_id=request.document_id,
        concepts=request.concepts,
        difficulty=request.difficulty.value,
        query=enhanced_query,
        top_k=top_k,
        include_images=include_images,
    )
    enhanced_search_ms = _elapsed_ms(enhanced_started)
    baseline_score = _search_quality_score(
        case=case,
        chunks=baseline_chunks,
        min_returned_chunks=min_returned_chunks,
    )
    enhanced_score = _search_quality_score(
        case=case,
        chunks=enhanced_chunks,
        min_returned_chunks=min_returned_chunks,
    )
    return {
        "baseline_query": baseline_query,
        "enhanced_query": enhanced_query,
        "baseline_chunks": list(baseline_chunks),
        "enhanced_chunks": list(enhanced_chunks),
        "concepts": list(case.concepts),
        "expected_search_terms": list(case.expected_search_terms),
        "case": case,
        "baseline_score": baseline_score,
        "enhanced_score": enhanced_score,
        "baseline_search_ms": baseline_search_ms,
        "enhanced_search_ms": enhanced_search_ms,
    }


def _compare_search_query_modes(
    *,
    case: LiveProblemGenerationEvalCase,
    request: GenerateProblemRequest,
    service: ProblemService,
    search_service: object,
) -> dict[str, Any]:
    high_rigor_profile = service.high_rigor_planner.plan(request=request)
    top_k = service._search_top_k(request, high_rigor_profile)
    include_images = service._visual_context_requested(request)
    min_returned_chunks = case.min_returned_chunks if case.min_returned_chunks is not None else 1
    primary_mode = service._search_query_mode()

    scores: dict[str, float] = {}
    hit_at_k: dict[str, float | None] = {}
    mrr_at_k: dict[str, float | None] = {}
    source_span_coverage: dict[str, float | None] = {}

    for mode in ("baseline", "compact", "hybrid", "expanded"):
        query = _search_query_for_mode(service=service, request=request, mode=mode)
        chunks = list(
            search_service.search_chunks(
                document_id=request.document_id,
                concepts=request.concepts,
                difficulty=request.difficulty.value,
                query=query,
                top_k=top_k,
                include_images=include_images,
            )
        )
        retrieval_metrics = _retrieval_metrics_for_case(case, chunks)
        scores[mode] = _search_quality_score(
            case=case,
            chunks=chunks,
            min_returned_chunks=min_returned_chunks,
        )
        hit_at_k[mode] = retrieval_metrics["hit_at_k"]
        mrr_at_k[mode] = retrieval_metrics["mrr_at_k"]
        source_span_coverage[mode] = retrieval_metrics["source_span_coverage"]

    return {
        "query_mode_scores": scores,
        "query_mode_hit_at_k": hit_at_k,
        "query_mode_mrr_at_k": mrr_at_k,
        "query_mode_source_span_coverage": source_span_coverage,
        "best_query_mode_by_score": _best_query_mode_by_score(scores, primary_mode),
        "primary_query_mode_score": scores.get(primary_mode),
    }


def _search_query_for_mode(
    *,
    service: ProblemService,
    request: GenerateProblemRequest,
    mode: str,
) -> str:
    if mode == "baseline":
        return " ".join(request.concepts)
    if mode == "expanded":
        return service._build_expanded_search_query(request)

    terms = service._compact_search_query_terms(request)
    if mode == "hybrid":
        terms.extend(service._hybrid_search_query_extra_terms(request, terms))
    query_terms = service._dedupe_query_terms(terms)
    fallback = service._normalize_query_term(" ".join(request.concepts)) or request.document_id
    return " ".join(query_terms) or fallback


def _best_query_mode_by_score(scores: dict[str, float], primary_mode: str) -> str | None:
    if not scores:
        return None
    best_score = max(scores.values())
    if primary_mode in scores and abs(scores[primary_mode] - best_score) < 1e-9:
        return primary_mode
    return max(scores, key=scores.get)


def _search_comparison_result_fields(search_comparison: dict[str, Any] | None) -> dict[str, Any]:
    if search_comparison is None:
        return {}

    baseline_chunks = search_comparison["baseline_chunks"]
    enhanced_chunks = search_comparison["enhanced_chunks"]
    baseline_ids = _unique_chunk_ids(baseline_chunks)
    enhanced_ids = _unique_chunk_ids(enhanced_chunks)
    baseline_score = search_comparison["baseline_score"]
    enhanced_score = search_comparison["enhanced_score"]
    case = search_comparison["case"]
    baseline_retrieval_metrics = _retrieval_metrics_for_case(case, baseline_chunks)
    enhanced_retrieval_metrics = _retrieval_metrics_for_case(case, enhanced_chunks)
    return {
        "baseline_query": search_comparison["baseline_query"],
        "enhanced_query": search_comparison["enhanced_query"],
        "baseline_returned_chunk_count": len(baseline_chunks),
        "enhanced_returned_chunk_count": len(enhanced_chunks),
        "baseline_expected_search_term_coverage": _term_coverage(
            search_comparison["expected_search_terms"],
            _chunk_text(baseline_chunks),
            aliases=case.expected_search_term_aliases,
        ),
        "enhanced_expected_search_term_coverage": _term_coverage(
            search_comparison["expected_search_terms"],
            _chunk_text(enhanced_chunks),
            aliases=case.expected_search_term_aliases,
        ),
        "baseline_hit_at_k": baseline_retrieval_metrics["hit_at_k"],
        "enhanced_hit_at_k": enhanced_retrieval_metrics["hit_at_k"],
        "baseline_mrr_at_k": baseline_retrieval_metrics["mrr_at_k"],
        "enhanced_mrr_at_k": enhanced_retrieval_metrics["mrr_at_k"],
        "baseline_precision_at_k": baseline_retrieval_metrics["precision_at_k"],
        "enhanced_precision_at_k": enhanced_retrieval_metrics["precision_at_k"],
        "baseline_source_span_coverage": baseline_retrieval_metrics["source_span_coverage"],
        "enhanced_source_span_coverage": enhanced_retrieval_metrics["source_span_coverage"],
        "baseline_concept_overlap_ratio": _concept_overlap_ratio_from_comparison(
            search_comparison,
            baseline_chunks,
        ),
        "enhanced_concept_overlap_ratio": _concept_overlap_ratio_from_comparison(
            search_comparison,
            enhanced_chunks,
        ),
        "baseline_average_chunk_content_chars": _average([len(chunk.content) for chunk in baseline_chunks]) or 0.0,
        "enhanced_average_chunk_content_chars": _average([len(chunk.content) for chunk in enhanced_chunks]) or 0.0,
        "baseline_unique_chunk_ids": baseline_ids,
        "enhanced_unique_chunk_ids": enhanced_ids,
        "chunk_id_overlap_ratio": _chunk_id_overlap_ratio(baseline_ids, enhanced_ids),
        "baseline_search_quality_score": baseline_score,
        "enhanced_search_quality_score": enhanced_score,
        "enhanced_score_minus_baseline_score": enhanced_score - baseline_score,
        "enhanced_wins_search_quality": enhanced_score >= baseline_score + 0.05,
    }


def _problem_quality_diagnostic(
    *,
    problem: Problem,
    request: GenerateProblemRequest,
    source_terms: list[str],
    expected_problem_terms: list[str],
    expected_problem_term_aliases: dict[str, list[str]] | None = None,
) -> LiveProblemQualityDiagnostic:
    problem_type = str(problem.type or "")
    choices = problem.choices or []
    choice_explanations = problem.choice_explanations or {}
    choice_diagnostics = problem.choice_diagnostics or []
    rubric = problem.rubric or []
    source_term_coverage = _term_coverage(source_terms, _single_problem_text(problem))
    expected_problem_term_coverage = _term_coverage(
        expected_problem_terms,
        _single_problem_text(problem),
        aliases=expected_problem_term_aliases,
    )
    professor_score = _professor_final_score(problem)
    professor_score_band = _professor_score_band(professor_score)
    operation_label = _high_rigor_operation_label(problem)
    warning_flags = _problem_warning_flags(
        problem=problem,
        problem_type=problem_type,
        professor_score=professor_score,
        source_term_coverage=source_term_coverage,
        choices=choices,
        choice_explanations=choice_explanations,
        choice_diagnostics=choice_diagnostics,
        rubric=rubric,
    )
    evidence_report = _evidence_obligation_report_from_problem(problem)
    return LiveProblemQualityDiagnostic(
        problem_id=str(problem.id),
        type=problem_type,
        difficulty=str(problem.difficulty or ""),
        bloom_level=str(problem.bloom_level or ""),
        item_model_id=problem.item_model_id,
        quality_status=str(problem.quality_status or ""),
        professor_grade_final_score=professor_score,
        professor_score_band=professor_score_band,
        structural_score=_professor_score_component(problem, "structural_score"),
        pedagogical_score=_professor_score_component(problem, "pedagogical_score"),
        grounding_score=_professor_score_component(problem, "grounding_score"),
        assessment_design_score=_professor_score_component(problem, "assessment_design_score"),
        source_chunk_count=len(problem.source_chunk_ids or []),
        has_source_evidence_snapshot=bool(problem.source_evidence_snapshot),
        has_explanation=bool(str(problem.explanation or "").strip()),
        has_answer=bool(problem.answer),
        multiple_choice_has_four_choices=(len(choices) == 4 if problem_type == ProblemType.multiple_choice.value else None),
        multiple_choice_has_choice_explanations=(
            bool(choice_explanations) and len(choice_explanations) >= len(choices)
            if problem_type == ProblemType.multiple_choice.value
            else None
        ),
        multiple_choice_has_choice_diagnostics=(
            bool(choice_diagnostics) and len(choice_diagnostics) >= len(choices)
            if problem_type == ProblemType.multiple_choice.value
            else None
        ),
        incorrect_distractor_diagnostic_count=(
            _incorrect_distractor_diagnostic_count(choice_diagnostics)
            if problem_type == ProblemType.multiple_choice.value
            else None
        ),
        short_answer_has_rubric=(bool(rubric) if problem_type == ProblemType.short_answer.value else None),
        short_answer_rubric_item_count=(len(rubric) if problem_type == ProblemType.short_answer.value else None),
        high_rigor_operation_detected=operation_label != "definition_recall",
        high_rigor_operation_label=operation_label,
        source_term_coverage=source_term_coverage,
        expected_problem_term_coverage=expected_problem_term_coverage,
        warning_flags=warning_flags,
        evidence_link_count=len(_evidence_links_from_problem(problem)),
        evidence_obligation_satisfaction=_evidence_obligation_satisfaction(evidence_report),
        answer_supported=_optional_bool(evidence_report.get("answer_supported") if evidence_report else None),
        explanation_supported=_optional_bool(
            evidence_report.get("explanation_supported") if evidence_report else None
        ),
        distractors_supported=_optional_bool(
            evidence_report.get("distractors_supported") if evidence_report else None
        ),
        rubric_supported=_optional_bool(evidence_report.get("rubric_supported") if evidence_report else None),
        source_formula_or_rule_cited=_optional_bool(
            evidence_report.get("source_formula_or_rule_cited") if evidence_report else None
        ),
        missing_evidence_roles=list(evidence_report.get("missing_roles") or []) if evidence_report else [],
        evidence_obligation_issues=list(evidence_report.get("issues") or []) if evidence_report else [],
        quality_risk_level=_quality_risk_level(
            problem=problem,
            professor_score=professor_score,
            source_term_coverage=source_term_coverage,
            warning_flags=warning_flags,
        ),
    )


def _evidence_obligation_report_from_problem(problem: Problem) -> dict[str, Any]:
    design_brief = problem.item_design_brief or {}
    if not isinstance(design_brief, dict):
        return {}
    report = design_brief.get("evidence_obligation_report") or {}
    return report if isinstance(report, dict) else {}


def _evidence_links_from_problem(problem: Problem) -> list[dict[str, Any]]:
    design_brief = problem.item_design_brief or {}
    if not isinstance(design_brief, dict):
        return []
    links = design_brief.get("evidence_links") or []
    return [link for link in links if isinstance(link, dict)]


def _evidence_obligation_satisfaction(report: dict[str, Any]) -> float | None:
    if not report:
        return None
    required = int(report.get("required_link_count") or 0)
    if required <= 0:
        return 1.0
    return min(1.0, (int(report.get("satisfied_link_count") or 0) / required))


def _optional_bool(value: Any) -> bool | None:
    return value if isinstance(value, bool) else None


def _human_review_row(
    *,
    case: LiveProblemGenerationEvalCase,
    problem: Problem,
    diagnostic: LiveProblemQualityDiagnostic,
) -> LiveHumanReviewRow:
    return LiveHumanReviewRow(
        case_id=case.id,
        problem_id=str(problem.id),
        document_id=str(problem.document_id or ""),
        type=str(problem.type or ""),
        difficulty=str(problem.difficulty or ""),
        bloom_level=str(problem.bloom_level or ""),
        item_model_id=problem.item_model_id,
        question=str(problem.question or ""),
        choices_json=_json_cell(problem.choices or []),
        answer_json=_json_cell(problem.answer or {}),
        explanation=str(problem.explanation or ""),
        rubric_json=_json_cell(problem.rubric or []),
        source_chunk_ids_json=_json_cell(problem.source_chunk_ids or []),
        source_evidence_snapshot_json=_json_cell(problem.source_evidence_snapshot or []),
        professor_grade_final_score=_professor_final_score(problem),
        professor_score_band=diagnostic.professor_score_band,
        structural_score=diagnostic.structural_score,
        pedagogical_score=diagnostic.pedagogical_score,
        grounding_score=diagnostic.grounding_score,
        assessment_design_score=diagnostic.assessment_design_score,
        quality_status=str(problem.quality_status or ""),
        high_rigor_operation_label=diagnostic.high_rigor_operation_label,
    )


def _run_llm_judge_for_case(
    *,
    case: LiveProblemGenerationEvalCase,
    request: GenerateProblemRequest,
    problems: list[Problem],
    llm_judge: object | None,
    settings: Settings,
    judge_model: str | None,
) -> list[LiveProblemLLMJudgeResult]:
    judge = llm_judge or _LiveEvalLLMJudge(settings=settings, judge_model=judge_model)
    results: list[LiveProblemLLMJudgeResult] = []
    for problem in problems:
        raw_result = judge.judge_problem(
            case=case,
            request=request,
            problem=problem,
            judge_model=judge_model,
        )
        payload = dict(raw_result)
        payload.setdefault("problem_id", str(problem.id))
        results.append(LiveProblemLLMJudgeResult.model_validate(payload))
    return results


def _run_answer_verification_for_case(
    *,
    request: GenerateProblemRequest,
    problems: list[Problem],
    verifier: object | None,
    settings: Settings,
) -> dict[str, ProblemAnswerVerificationReport]:
    answer_verifier = verifier or ProblemAnswerVerifier(settings=settings)
    results: dict[str, ProblemAnswerVerificationReport] = {}
    for problem in problems:
        raw_result = answer_verifier.verify(
            problem=problem,
            request=request,
            chunks=_verification_chunks(problem),
        )
        results[str(problem.id)] = ProblemAnswerVerificationReport.model_validate(raw_result)
    return results


def _verification_chunks(problem: Problem) -> list[RetrievedChunk]:
    chunks: list[RetrievedChunk] = []
    for item in problem.source_evidence_snapshot or []:
        if isinstance(item, RetrievedChunk):
            chunks.append(item)
            continue
        if isinstance(item, dict):
            try:
                chunks.append(RetrievedChunk.model_validate(item))
            except Exception:
                continue
    return chunks


class _LiveEvalLLMJudge:
    def __init__(self, *, settings: Settings, judge_model: str | None = None):
        self.settings = settings
        self.client = OpenAIClient(settings.model_copy(update={"llm_provider": "openai"}))
        self.judge_model = judge_model or settings.problem_quality_model

    def judge_problem(
        self,
        *,
        case: LiveProblemGenerationEvalCase,
        request: GenerateProblemRequest,
        problem: Problem,
        judge_model: str | None = None,
    ) -> dict[str, Any]:
        return self.client.generate_json(
            model=judge_model or self.judge_model,
            prompt=_llm_judge_prompt(case=case, request=request, problem=problem),
            schema_name="LiveProblemQualityJudgeResult",
            schema=_llm_judge_schema(),
            max_output_tokens=900,
            reasoning_effort="low",
        )


def _llm_judge_prompt(
    *,
    case: LiveProblemGenerationEvalCase,
    request: GenerateProblemRequest,
    problem: Problem,
) -> str:
    payload = {
        "case_id": case.id,
        "requested_concepts": case.concepts,
        "requested_type": request.type.value,
        "requested_difficulty": request.difficulty.value,
        "requested_bloom_level": request.bloom_level.value,
        "requested_problem_style": request.problem_style.value if request.problem_style else None,
        "requested_target_rigor": request.target_rigor.value if request.target_rigor else None,
        "user_requirements": request.user_requirements,
        "problem": {
            "id": str(problem.id),
            "question": problem.question,
            "choices": problem.choices,
            "answer": problem.answer,
            "explanation": problem.explanation,
            "rubric": problem.rubric,
            "source_evidence_snapshot": problem.source_evidence_snapshot,
            "source_chunk_ids": problem.source_chunk_ids,
        },
    }
    return (
        "You are an independent evaluator for generated study problems. "
        "Score only the provided problem against the request and source evidence. "
        "Return strict JSON matching the schema. Use 0.0 to 1.0 scores. "
        "Recommended action must be one of pass, needs_review, reject.\n\n"
        + json.dumps(payload, ensure_ascii=False, indent=2)
    )


def _llm_judge_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "problem_id": {"type": "string"},
            "source_grounding_score": {"type": "number", "minimum": 0, "maximum": 1},
            "cognitive_rigor_score": {"type": "number", "minimum": 0, "maximum": 1},
            "distractor_quality_score": {"type": "number", "minimum": 0, "maximum": 1},
            "explanation_quality_score": {"type": "number", "minimum": 0, "maximum": 1},
            "difficulty_fit_score": {"type": "number", "minimum": 0, "maximum": 1},
            "overall_score": {"type": "number", "minimum": 0, "maximum": 1},
            "failure_reasons": {"type": "array", "items": {"type": "string"}},
            "recommended_action": {"type": "string", "enum": ["pass", "needs_review", "reject"]},
        },
        "required": [
            "problem_id",
            "source_grounding_score",
            "cognitive_rigor_score",
            "distractor_quality_score",
            "explanation_quality_score",
            "difficulty_fit_score",
            "overall_score",
            "failure_reasons",
            "recommended_action",
        ],
    }


def _json_cell(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _problem_warning_flags(
    *,
    problem: Problem,
    problem_type: str,
    professor_score: float | None,
    source_term_coverage: float,
    choices: list[dict],
    choice_explanations: dict,
    choice_diagnostics: list[dict],
    rubric: list[dict],
) -> list[str]:
    flags: list[str] = []
    if problem.quality_status in {"rejected", "needs_review"}:
        flags.append(f"quality_status_{problem.quality_status}")
    if professor_score is not None and professor_score < 0.75:
        flags.append("low_professor_grade_score")
    if source_term_coverage < 0.3:
        flags.append("low_source_term_coverage")
    if not str(problem.explanation or "").strip():
        flags.append("missing_explanation")
    if not problem.answer:
        flags.append("missing_answer")
    if problem_type == ProblemType.multiple_choice.value:
        if len(choices) != 4:
            flags.append("multiple_choice_not_four_choices")
        if not choice_explanations or len(choice_explanations) < len(choices):
            flags.append("missing_choice_explanations")
        if not choice_diagnostics or len(choice_diagnostics) < len(choices):
            flags.append("missing_choice_diagnostics")
    if problem_type == ProblemType.short_answer.value and not rubric:
        flags.append("missing_rubric")
    return flags


def _quality_risk_level(
    *,
    problem: Problem,
    professor_score: float | None,
    source_term_coverage: float,
    warning_flags: list[str],
) -> str:
    if (
        problem.quality_status in {"rejected", "needs_review"}
        or (professor_score is not None and professor_score < 0.65)
        or "missing_choice_diagnostics" in warning_flags
        or "missing_rubric" in warning_flags
        or source_term_coverage < 0.3
    ):
        return "high"
    if (professor_score is not None and professor_score < 0.75) or warning_flags:
        return "medium"
    return "low"


def _professor_final_score(problem: Problem) -> float | None:
    score = problem.professor_grade_score
    if not isinstance(score, dict):
        return None
    final_score = score.get("final_score")
    if not isinstance(final_score, int | float):
        return None
    return float(final_score)


def _professor_score_component(problem: Problem, field_name: str) -> float | None:
    score = problem.professor_grade_score
    if not isinstance(score, dict):
        return None
    value = score.get(field_name)
    if not isinstance(value, int | float):
        return None
    return float(value)


def _professor_score_band(score: float | None) -> str | None:
    if score is None:
        return None
    if score >= 0.90:
        return "excellent"
    if score >= 0.78:
        return "good"
    if score >= 0.65:
        return "needs_review"
    return "weak"


def _commercial_quality_score_for_diagnostic(
    *,
    diagnostic: LiveProblemQualityDiagnostic,
    execution_status: str,
    cited_evidence_missing: bool = False,
) -> tuple[float, str]:
    if execution_status != "completed":
        return 0.0, "reject"
    score = diagnostic.professor_grade_final_score
    if score is None:
        score = 0.6
    score = max(0.0, min(1.0, float(score)))
    if diagnostic.quality_status == "needs_review":
        score = min(score, 0.74)
    if diagnostic.answer_verification_action == "needs_review":
        score = min(score, 0.74)
    if diagnostic.answer_verification_action == "reject":
        score = min(score, 0.49)
    if cited_evidence_missing:
        score = min(score, 0.65)
    if "source_grounding_issue" in diagnostic.warning_flags or "low_source_term_coverage" in diagnostic.warning_flags:
        score = min(score, 0.70)
    if (
        diagnostic.type == ProblemType.multiple_choice.value
        and "missing_choice_diagnostics" in diagnostic.warning_flags
    ):
        score = min(score, 0.65)
    return score, _commercial_quality_band(score)


def _commercial_quality_band(score: float) -> str:
    if score >= 0.85:
        return "release_ready"
    if score >= 0.70:
        return "usable_with_review"
    if score >= 0.50:
        return "needs_revision"
    return "reject"


def _professor_commercial_disagreements(
    diagnostics: list[LiveProblemQualityDiagnostic],
) -> list[dict[str, Any]]:
    disagreements: list[dict[str, Any]] = []
    for diagnostic in diagnostics:
        if (
            diagnostic.professor_grade_final_score is not None
            and diagnostic.professor_grade_final_score >= 0.85
            and (diagnostic.commercial_quality_score or 0.0) < 0.70
        ):
            disagreements.append(
                {
                    "problem_id": diagnostic.problem_id,
                    "professor_grade_final_score": diagnostic.professor_grade_final_score,
                    "professor_score_band": diagnostic.professor_score_band,
                    "commercial_quality_score": diagnostic.commercial_quality_score,
                    "commercial_quality_band": diagnostic.commercial_quality_band,
                }
            )
    return disagreements


def _incorrect_distractor_diagnostic_count(choice_diagnostics: list[dict]) -> int:
    return sum(
        1
        for diagnostic in choice_diagnostics
        if isinstance(diagnostic, dict) and diagnostic.get("is_correct") is False
    )


def _high_rigor_operation_label(problem: Problem) -> str:
    text = _single_problem_text(problem).lower()
    item_model_id = str(problem.item_model_id or "").lower()
    if item_model_id == "error_detection" or _contains_any(
        text, ("오류", "잘못", "틀린", "수정", "반례", "bug", "error", "debug", "wrong")
    ):
        return "error_diagnosis"
    if item_model_id == "data_interpretation" or _contains_any(
        text, ("표", "그래프", "도표", "자료값", "데이터", "해석", "table", "graph", "data", "interpret")
    ):
        return "data_interpretation"
    if item_model_id == "evidence_selection" or _contains_any(
        text, ("근거", "증거", "자료", "지문", "뒷받침", "evidence", "source", "support", "weaken")
    ):
        return "evidence_interpretation"
    if _contains_any(
        text,
        ("추적", "단계별", "상태", "큐", "스택", "배열", "코드", "trace", "state", "queue", "stack", "array", "code"),
    ):
        return "trace_and_explain"
    if _contains_any(text, ("설계", "제약", "최적", "선택", "tradeoff", "constraint", "design", "optimize")):
        return "design_under_constraint"
    if _contains_any(text, ("비교", "차이", "공통점", "공통", "compare", "contrast", "difference")):
        return "concept_comparison"
    if _has_calculation_signal(text) and _contains_any(
        text,
        (
            "조건",
            "비교",
            "해석",
            "판단",
            "왜",
            "근거",
            "변화",
            "결과",
            "영향",
            "condition",
            "compare",
            "interpret",
            "justify",
        ),
    ):
        return "calculation_reasoning"
    if item_model_id in {"case_based_application", "transfer_to_new_context"} or _contains_any(
        text, ("조건", "변화", "바뀌", "달라지", "changed condition", "condition changes")
    ):
        return "condition_mutation"
    if _contains_any(
        text,
        (
            "사례",
            "상황",
            "적용",
            "분석",
            "판단",
            "추론",
            "case",
            "scenario",
            "apply",
            "analyze",
            "infer",
        ),
    ):
        return "generic_application"
    return "definition_recall"


def _has_calculation_signal(text: str) -> bool:
    return _contains_any(text, ("계산", "공식", "수식", "대입", "값", "비율", "formula", "equation", "calculate")) or bool(
        any(character.isdigit() for character in text)
    )


def _contains_any(text: str, cues: tuple[str, ...]) -> bool:
    return any(cue in text for cue in cues)


class _CapturingSearchService:
    def __init__(self, inner: object):
        self.inner = inner
        self.last_kwargs: dict[str, Any] = {}
        self.last_chunks: list[RetrievedChunk] = []
        self._primed_query: str | None = None
        self._primed_chunks: list[RetrievedChunk] | None = None

    def prime(self, *, query: str, chunks: list[RetrievedChunk]) -> None:
        self._primed_query = query
        self._primed_chunks = list(chunks)

    def search_chunks(self, **kwargs: Any) -> list[RetrievedChunk]:
        self.last_kwargs = dict(kwargs)
        if self._primed_query is not None and kwargs.get("query") == self._primed_query:
            chunks = list(self._primed_chunks or [])
            self.last_chunks = chunks
            self._primed_query = None
            self._primed_chunks = None
            return chunks
        chunks = self.inner.search_chunks(**kwargs)
        self.last_chunks = list(chunks)
        return chunks

    def get_chunks_by_ids(self, **kwargs: Any) -> list[RetrievedChunk]:
        return self.inner.get_chunks_by_ids(**kwargs)


def _threshold_failures(
    *,
    case: LiveProblemGenerationEvalCase,
    request: GenerateProblemRequest,
    generated_count: int,
    passed_count: int,
    returned_chunk_count: int,
    wrong_document_chunk_count: int,
    cited_chunk_count_avg: float,
    average_quality_score: float | None,
    reject_rate: float | None,
    total_ms: float | None,
    expected_search_term_coverage: float,
    hit_at_k: float | None,
    mrr_at_k: float | None,
    precision_at_k: float | None,
    source_span_coverage: float | None,
    cited_hit_at_k: float | None,
    cited_expected_chunk_recall: float | None,
    cited_expected_chunk_precision: float | None,
    cited_source_span_coverage: float | None,
    generation_context_hit_at_k: float | None,
    generation_context_expected_chunk_recall: float | None,
    generation_context_source_span_coverage: float | None,
    selected_kernel_atom_chunk_ids: list[str],
    generation_context_selected_atom_recall: float | None,
    expected_problem_term_coverage: float,
    high_rigor_operation_counts: dict[str, int],
    high_rigor_mc_choice_diagnostics_coverage: float | None,
    short_answer_rubric_coverage: float | None,
) -> list[str]:
    high_rigor = _is_high_rigor_request(request)
    requested_count = request.count
    min_returned_chunks = case.min_returned_chunks if case.min_returned_chunks is not None else 1
    min_cited_chunks = (
        case.min_cited_chunks_per_problem
        if case.min_cited_chunks_per_problem is not None
        else 1
    )
    min_quality = (
        case.min_average_quality_score
        if case.min_average_quality_score is not None
        else (0.75 if high_rigor else 0.70)
    )
    max_reject_rate = case.max_reject_rate if case.max_reject_rate is not None else (0.60 if high_rigor else 0.45)
    max_total_ms = (
        case.max_total_ms
        if case.max_total_ms is not None
        else (80_000 if requested_count >= 3 else 45_000)
    )
    min_search_coverage = (
        case.min_expected_search_term_coverage
        if case.min_expected_search_term_coverage is not None
        else 0.40
    )
    min_problem_coverage = (
        case.min_expected_problem_term_coverage
        if case.min_expected_problem_term_coverage is not None
        else 0.30
    )

    failures: list[str] = []
    if requested_count > 0 and passed_count == 0:
        failures.append("no passed problems generated")
    if generated_count == 0:
        failures.append("no candidates generated")
    if wrong_document_chunk_count > 0:
        failures.append(f"wrong_document_chunk_count {wrong_document_chunk_count} > 0")
    if returned_chunk_count < min_returned_chunks:
        failures.append(f"returned_chunk_count {returned_chunk_count} < {min_returned_chunks}")
    if cited_chunk_count_avg < min_cited_chunks:
        failures.append(f"cited_chunk_count_avg {cited_chunk_count_avg:.3f} < {min_cited_chunks}")
    if average_quality_score is None:
        if not case.allow_missing_quality_score and (case.min_average_quality_score is not None or high_rigor):
            failures.append("average_quality_score is missing")
    elif average_quality_score < min_quality:
        failures.append(f"average_quality_score {average_quality_score:.3f} < {min_quality}")
    if reject_rate is not None and reject_rate > max_reject_rate:
        failures.append(f"reject_rate {reject_rate:.3f} > {max_reject_rate}")
    if total_ms is not None and total_ms > max_total_ms:
        failures.append(f"total_ms {total_ms:.1f} > {max_total_ms}")
    if case.expected_search_terms and expected_search_term_coverage < min_search_coverage:
        failures.append(
            f"expected_search_term_coverage {expected_search_term_coverage:.3f} < {min_search_coverage}"
        )
    if case.expected_chunk_ids:
        min_hit_at_k = case.min_hit_at_k if case.min_hit_at_k is not None else 1.0
        if (hit_at_k or 0.0) < min_hit_at_k:
            failures.append(f"hit_at_k {(hit_at_k or 0.0):.3f} < {min_hit_at_k}")
    if case.min_mrr_at_k is not None and (mrr_at_k or 0.0) < case.min_mrr_at_k:
        failures.append(f"mrr_at_k {(mrr_at_k or 0.0):.3f} < {case.min_mrr_at_k}")
    if (
        case.golden_label_mode == "exhaustive"
        and case.min_precision_at_k is not None
        and (precision_at_k or 0.0) < case.min_precision_at_k
    ):
        failures.append(f"precision_at_k {(precision_at_k or 0.0):.3f} < {case.min_precision_at_k}")
    if case.expected_source_spans and (source_span_coverage or 0.0) < 0.5:
        failures.append(f"source_span_coverage {(source_span_coverage or 0.0):.3f} < 0.5")
    if case.expected_chunk_ids and (hit_at_k or 0.0) >= 1.0 and (generation_context_hit_at_k or 0.0) <= 0.0:
        failures.append("generation context dropped all expected evidence chunks")
    if high_rigor and selected_kernel_atom_chunk_ids and (generation_context_selected_atom_recall or 0.0) < 1.0:
        failures.append("generation context dropped selected kernel atom chunks")
    min_generation_context_recall = case.min_generation_context_expected_chunk_recall
    if min_generation_context_recall is None and high_rigor and case.expected_chunk_ids:
        min_generation_context_recall = 0.5
    if case.expected_chunk_ids and min_generation_context_recall is not None:
        if (generation_context_hit_at_k or 0.0) > 0.0 and (
            generation_context_expected_chunk_recall or 0.0
        ) < min_generation_context_recall:
            failures.append(
                "generation_context_expected_chunk_recall "
                f"{(generation_context_expected_chunk_recall or 0.0):.3f} < {min_generation_context_recall}"
            )
    min_generation_context_span_coverage = case.min_generation_context_source_span_coverage
    if min_generation_context_span_coverage is None and high_rigor and case.expected_source_spans:
        min_generation_context_span_coverage = 0.5
    if (
        case.expected_source_spans
        and min_generation_context_span_coverage is not None
        and (generation_context_source_span_coverage or 0.0) < min_generation_context_span_coverage
    ):
        failures.append(
            "generation_context_source_span_coverage "
            f"{(generation_context_source_span_coverage or 0.0):.3f} < {min_generation_context_span_coverage}"
        )
    min_cited_recall = case.min_cited_expected_chunk_recall
    if min_cited_recall is None and high_rigor and case.expected_chunk_ids:
        min_cited_recall = 0.5
    if case.expected_chunk_ids and min_cited_recall is not None:
        if (cited_hit_at_k or 0.0) <= 0.0:
            failures.append("no generated problem cited any expected evidence chunk")
        elif (cited_expected_chunk_recall or 0.0) < min_cited_recall:
            failures.append(
                f"cited_expected_chunk_recall {(cited_expected_chunk_recall or 0.0):.3f} < {min_cited_recall}"
            )
    if (
        case.golden_label_mode == "exhaustive"
        and case.min_cited_expected_chunk_precision is not None
        and (cited_expected_chunk_precision or 0.0) < case.min_cited_expected_chunk_precision
    ):
        failures.append(
            "cited_expected_chunk_precision "
            f"{(cited_expected_chunk_precision or 0.0):.3f} < {case.min_cited_expected_chunk_precision}"
        )
    if (
        case.min_cited_source_span_coverage is not None
        and (cited_source_span_coverage or 0.0) < case.min_cited_source_span_coverage
    ):
        failures.append(
            f"cited_source_span_coverage {(cited_source_span_coverage or 0.0):.3f} "
            f"< {case.min_cited_source_span_coverage}"
        )
    if case.expected_problem_terms and expected_problem_term_coverage < min_problem_coverage:
        failures.append(
            f"expected_problem_term_coverage {expected_problem_term_coverage:.3f} < {min_problem_coverage}"
        )
    if high_rigor and not case.allow_generic_high_rigor_operation and _only_generic_high_rigor_operations(
        high_rigor_operation_counts
    ):
        failures.append("high-rigor problems lack specific thinking operations")
    if (
        high_rigor
        and request.type == ProblemType.multiple_choice
        and high_rigor_mc_choice_diagnostics_coverage is not None
        and high_rigor_mc_choice_diagnostics_coverage < 1.0
    ):
        failures.append(
            f"high_rigor_mc_choice_diagnostics_coverage {high_rigor_mc_choice_diagnostics_coverage:.3f} < 1.0"
        )
    if (
        request.type == ProblemType.short_answer
        and short_answer_rubric_coverage is not None
        and short_answer_rubric_coverage < 1.0
    ):
        failures.append(f"short_answer_rubric_coverage {short_answer_rubric_coverage:.3f} < 1.0")
    return failures


def _threshold_failure_categories(failures: list[str]) -> dict[str, list[str]]:
    categories = {"quality": [], "performance": [], "stability": []}
    for failure in failures:
        normalized = failure.lower()
        if any(
            cue in normalized
            for cue in (
                "total_ms",
                "search_ms",
                "latency",
                "candidate_generation",
                "quality_filter",
                "db_write",
                "db_commit",
                "db_refresh",
                "artifact_publish",
            )
        ):
            categories["performance"].append(failure)
        elif any(
            cue in normalized
            for cue in (
                "reject_rate",
                "retry",
                "repeat stability",
                "repeat pass_rate",
                "duplicate_question_similarity",
                "quality_score_stddev",
            )
        ):
            categories["stability"].append(failure)
        else:
            categories["quality"].append(failure)
    return categories


def _apply_threshold_failure_categories(result: LiveProblemGenerationCaseResult) -> None:
    categories = _threshold_failure_categories(result.threshold_failures)
    result.threshold_failures_quality = categories["quality"]
    result.threshold_failures_performance = categories["performance"]
    result.threshold_failures_stability = categories["stability"]


def _only_generic_high_rigor_operations(operation_counts: dict[str, int]) -> bool:
    total = sum(operation_counts.values())
    if total <= 0:
        return False
    weak_operations = {"definition_recall", "generic_application"}
    return set(operation_counts) <= weak_operations


def _write_reports(*, report: LiveProblemGenerationEvalReport, output_dir: Path) -> None:
    report_json = output_dir / REPORT_JSON_NAME
    cases_jsonl = output_dir / REPORT_JSONL_NAME
    summary_md = output_dir / REPORT_MARKDOWN_NAME
    human_review_csv = output_dir / REPORT_HUMAN_REVIEW_CSV_NAME
    report_json.write_text(
        json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    cases_jsonl.write_text(
        "".join(
            json.dumps(case.model_dump(mode="json"), ensure_ascii=False) + "\n"
            for case in report.cases
        ),
        encoding="utf-8",
    )
    summary_md.write_text(_markdown_summary(report), encoding="utf-8")
    _write_human_review_csv(report=report, path=human_review_csv)


def _write_human_review_csv(*, report: LiveProblemGenerationEvalReport, path: Path) -> None:
    columns = [
        "case_id",
        "problem_id",
        "document_id",
        "type",
        "difficulty",
        "bloom_level",
        "item_model_id",
        "question",
        "choices_json",
        "answer_json",
        "explanation",
        "rubric_json",
        "source_chunk_ids_json",
        "source_evidence_snapshot_json",
        "professor_grade_final_score",
        "professor_score_band",
        "structural_score",
        "pedagogical_score",
        "grounding_score",
        "assessment_design_score",
        "quality_status",
        "high_rigor_operation_label",
        "reviewer_problem_quality_score",
        "reviewer_source_grounding_score",
        "reviewer_difficulty_fit_score",
        "reviewer_notes",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for case in report.cases:
            for row in case.human_review_rows:
                writer.writerow(_human_review_csv_row(row, mode=report.human_review_export_mode))


def _human_review_csv_row(
    row: LiveHumanReviewRow,
    *,
    mode: Literal["full", "redacted"],
) -> dict[str, Any]:
    values = row.model_dump()
    if mode == "redacted":
        for field_name in (
            "answer_json",
            "explanation",
            "rubric_json",
            "source_evidence_snapshot_json",
        ):
            values[field_name] = HUMAN_REVIEW_REDACTED_VALUE
    return values


def load_human_review_csv(path: Path) -> list[HumanReviewRecord]:
    records: list[HumanReviewRecord] = []
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row_number, row in enumerate(reader, start=2):
            case_id = str(row.get("case_id") or "").strip()
            problem_id = str(row.get("problem_id") or "").strip()
            if not case_id or not problem_id:
                raise ValueError(f"human review CSV row {row_number} is missing case_id or problem_id")
            records.append(
                HumanReviewRecord(
                    case_id=case_id,
                    problem_id=problem_id,
                    reviewer_problem_quality_score=_parse_human_review_score(
                        row.get("reviewer_problem_quality_score"),
                        row_number=row_number,
                        column="reviewer_problem_quality_score",
                    ),
                    reviewer_source_grounding_score=_parse_human_review_score(
                        row.get("reviewer_source_grounding_score"),
                        row_number=row_number,
                        column="reviewer_source_grounding_score",
                    ),
                    reviewer_difficulty_fit_score=_parse_human_review_score(
                        row.get("reviewer_difficulty_fit_score"),
                        row_number=row_number,
                        column="reviewer_difficulty_fit_score",
                    ),
                    reviewer_notes=str(row.get("reviewer_notes") or "").strip(),
                )
            )
    return records


def summarize_human_review(
    records: list[HumanReviewRecord],
    report: LiveProblemGenerationEvalReport | None = None,
) -> HumanReviewSummary:
    problem_quality_scores = [record.reviewer_problem_quality_score for record in records]
    source_grounding_scores = [record.reviewer_source_grounding_score for record in records]
    difficulty_fit_scores = [record.reviewer_difficulty_fit_score for record in records]
    notes_by_problem: dict[str, list[str]] = {}
    for record in records:
        if record.reviewer_notes:
            notes_by_problem.setdefault(record.problem_id, []).append(record.reviewer_notes)

    professor_by_problem = _professor_review_lookup(report) if report is not None else {}
    professor_human_pairs: list[tuple[float, float]] = []
    disagreements: list[dict[str, Any]] = []
    for record in records:
        human_score = record.reviewer_problem_quality_score
        professor_info = professor_by_problem.get(record.problem_id)
        if human_score is None or professor_info is None:
            continue
        professor_score = professor_info.get("professor_grade_final_score")
        if isinstance(professor_score, int | float):
            professor_human_pairs.append((float(professor_score), human_score))
        professor_band = str(professor_info.get("professor_score_band") or "")
        if professor_band in {"excellent", "good"} and human_score < 0.6:
            disagreements.append(
                {
                    "case_id": record.case_id,
                    "problem_id": record.problem_id,
                    "professor_score_band": professor_band,
                    "professor_grade_final_score": professor_score,
                    "reviewer_problem_quality_score": human_score,
                    "reviewer_notes": record.reviewer_notes,
                }
            )

    return HumanReviewSummary(
        reviewed_problem_count=len(records),
        average_problem_quality_score=_average(problem_quality_scores),
        average_source_grounding_score=_average(source_grounding_scores),
        average_difficulty_fit_score=_average(difficulty_fit_scores),
        low_quality_review_count=sum(1 for score in problem_quality_scores if score is not None and score < 0.6),
        low_grounding_review_count=sum(1 for score in source_grounding_scores if score is not None and score < 0.6),
        low_difficulty_fit_count=sum(1 for score in difficulty_fit_scores if score is not None and score < 0.6),
        reviewer_notes_by_problem=notes_by_problem,
        correlation_professor_vs_human_quality=_pearson_correlation(professor_human_pairs),
        disagreements=disagreements,
    )


def write_human_review_summary(summary: HumanReviewSummary, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / REPORT_HUMAN_REVIEW_SUMMARY_JSON_NAME
    markdown_path = output_dir / REPORT_HUMAN_REVIEW_SUMMARY_MARKDOWN_NAME
    json_path.write_text(
        json.dumps(summary.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    markdown_path.write_text(_human_review_summary_markdown(summary), encoding="utf-8")


def _parse_human_review_score(value: object, *, row_number: int, column: str) -> float | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        score = float(text)
    except ValueError as exc:
        raise ValueError(f"human review CSV row {row_number} has invalid {column}: {text!r}") from exc
    if score < 0:
        raise ValueError(f"human review CSV row {row_number} has negative {column}: {score}")
    if score > 1:
        score = score / 5
    if score > 1:
        raise ValueError(f"human review CSV row {row_number} has out-of-range {column}: {text!r}")
    return score


def _professor_review_lookup(report: LiveProblemGenerationEvalReport) -> dict[str, dict[str, Any]]:
    lookup: dict[str, dict[str, Any]] = {}
    for case in report.cases:
        for diagnostic in case.problem_quality_diagnostics:
            lookup[diagnostic.problem_id] = {
                "case_id": case.case_id,
                "professor_grade_final_score": diagnostic.professor_grade_final_score,
                "professor_score_band": diagnostic.professor_score_band,
            }
    return lookup


def _pearson_correlation(pairs: list[tuple[float, float]]) -> float | None:
    if len(pairs) < 2:
        return None
    left_values = [left for left, _ in pairs]
    right_values = [right for _, right in pairs]
    left_mean = sum(left_values) / len(left_values)
    right_mean = sum(right_values) / len(right_values)
    left_var = sum((value - left_mean) ** 2 for value in left_values)
    right_var = sum((value - right_mean) ** 2 for value in right_values)
    if left_var == 0 or right_var == 0:
        return None
    covariance = sum((left - left_mean) * (right - right_mean) for left, right in pairs)
    return covariance / ((left_var * right_var) ** 0.5)


def _human_review_summary_markdown(summary: HumanReviewSummary) -> str:
    lines = [
        "# Live Problem Generation Human Review Summary",
        "",
        f"- reviewed_problem_count: {summary.reviewed_problem_count}",
        f"- average_problem_quality_score: {_format_optional(summary.average_problem_quality_score)}",
        f"- average_source_grounding_score: {_format_optional(summary.average_source_grounding_score)}",
        f"- average_difficulty_fit_score: {_format_optional(summary.average_difficulty_fit_score)}",
        f"- low_quality_review_count: {summary.low_quality_review_count}",
        f"- low_grounding_review_count: {summary.low_grounding_review_count}",
        f"- low_difficulty_fit_count: {summary.low_difficulty_fit_count}",
        f"- correlation_professor_vs_human_quality: {_format_optional(summary.correlation_professor_vs_human_quality)}",
        "",
        "## Disagreements",
        "",
        "| case | problem | professor_band | professor_score | human_score | notes |",
        "| --- | --- | --- | ---: | ---: | --- |",
    ]
    if summary.disagreements:
        for item in summary.disagreements:
            lines.append(
                "| "
                + " | ".join(
                    [
                        str(item.get("case_id") or ""),
                        str(item.get("problem_id") or ""),
                        str(item.get("professor_score_band") or ""),
                        _format_optional(item.get("professor_grade_final_score")),
                        _format_optional(item.get("reviewer_problem_quality_score")),
                        _markdown_cell(str(item.get("reviewer_notes") or "")),
                    ]
                )
                + " |"
            )
    else:
        lines.append("| - | - | - | - | - | - |")
    return "\n".join(lines) + "\n"


def _markdown_summary(report: LiveProblemGenerationEvalReport) -> str:
    lines = [
        "# Live Problem Generation Benchmark",
        "",
        f"- report_schema_version: {report.report_schema_version}",
        f"- git_commit: {report.git_commit or 'unknown'}",
        f"- cases_sha256: {report.cases_sha256 or 'unknown'}",
        f"- logical_cases: {report.logical_case_count}",
        f"- repeat_count: {report.repeat_count}",
        f"- total_runs: {report.total_run_count}",
        f"- human_review_export_mode: {report.human_review_export_mode}",
        f"- cost_profile: {report.cost_profile}",
        f"- cost_profile_warning: {report.cost_profile_warning or ''}",
        f"- cases: {report.case_count}",
        f"- passed: {report.passed_count}",
        f"- failed: {report.failed_count}",
        f"- execution_failed: {report.failed_execution_count}",
        f"- average_total_ms: {_format_optional(report.average_total_ms)}",
        f"- average_reject_rate: {_format_optional(report.average_reject_rate)}",
        f"- average_professor_grade_score: {_format_optional(report.average_professor_grade_score)}",
        f"- professor_score_band_counts: {dict(sorted(report.professor_score_band_counts.items()))}",
        f"- average_commercial_quality_score: {_format_optional(report.average_commercial_quality_score)}",
        f"- commercial_score_band_counts: {dict(sorted(report.commercial_score_band_counts.items()))}",
        f"- professor_vs_commercial_disagreement_count: {report.professor_vs_commercial_disagreement_count}",
        f"- threshold_failure_category_counts: {dict(sorted(report.threshold_failure_category_counts.items()))}",
        f"- llm_judge_enabled: {report.llm_judge_enabled}",
        f"- generation_model: {report.generation_model or 'unknown'}",
        f"- actual_generation_models: {dict(sorted(report.generation_model_counts.items()))}",
        f"- total_llm_tokens: {report.total_llm_tokens}",
        f"- total_estimated_cost_krw: {_format_optional(report.total_estimated_cost_krw)}",
        f"- generation_model_mismatch_warning: {report.generation_model_mismatch_warning or ''}",
        f"- judge_model: {report.judge_model or 'not_enabled'}",
        f"- judge_same_model_warning: {report.judge_same_model_warning}",
        f"- judge_same_family_warning: {report.judge_same_family_warning}",
        f"- average_llm_judge_overall_score: {_format_optional(report.average_llm_judge_overall_score)}",
        f"- answer_verification_action_counts: {dict(sorted(report.answer_verification_action_counts.items()))}",
        f"- answer_correctness_issue_count: {report.answer_correctness_issue_count}",
        f"- average_evidence_obligation_satisfaction: {_format_optional(report.average_evidence_obligation_satisfaction)}",
        f"- missing_answer_evidence_count: {report.missing_answer_evidence_count}",
        f"- missing_explanation_evidence_count: {report.missing_explanation_evidence_count}",
        f"- missing_formula_or_rule_count: {report.missing_formula_or_rule_count}",
        "",
        "## Latency Percentiles",
        "",
        "| component | p50_ms | p95_ms |",
        "| --- | ---: | ---: |",
        f"| total | {_format_optional(report.p50_total_ms)} | {_format_optional(report.p95_total_ms)} |",
        f"| search | {_format_optional(report.p50_search_ms)} | {_format_optional(report.p95_search_ms)} |",
        f"| generation | {_format_optional(report.p50_candidate_generation_total_ms)} | {_format_optional(report.p95_candidate_generation_total_ms)} |",
        f"| quality_filter | {_format_optional(report.p50_quality_filter_total_ms)} | {_format_optional(report.p95_quality_filter_total_ms)} |",
        f"| db_write | {_format_optional(report.p50_db_write_ms)} | {_format_optional(report.p95_db_write_ms)} |",
        f"| db_commit | {_format_optional(report.p50_db_commit_ms)} | {_format_optional(report.p95_db_commit_ms)} |",
        f"| artifact_publish | {_format_optional(report.p50_artifact_publish_ms)} | {_format_optional(report.p95_artifact_publish_ms)} |",
        "",
        "## Token and Cost Summary",
        "",
        f"- configured_generation_model: {report.generation_model or 'unknown'}",
        f"- actual_generation_model_warning: {report.generation_model_mismatch_warning or ''}",
        "",
        "| model | calls | input_tokens | output_tokens | total_tokens | estimated_cost_krw |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
        *[
            "| "
            + " | ".join(
                [
                    model,
                    str(report.generation_model_counts.get(model, 0)),
                    str(report.token_usage_by_model.get(model, {}).get("input_tokens", 0)),
                    str(report.token_usage_by_model.get(model, {}).get("output_tokens", 0)),
                    str(report.token_usage_by_model.get(model, {}).get("total_tokens", 0)),
                    _format_optional(report.cost_by_model.get(model)),
                ]
            )
            + " |"
            for model in sorted(report.generation_model_counts)
        ],
        "",
        "### Highest Cost Cases",
        "",
        "| case | estimated_cost_krw | total_tokens | actual_models |",
        "| --- | ---: | ---: | --- |",
        *[
            "| "
            + " | ".join(
                [
                    str(item.get("case_id", "")),
                    _format_optional(item.get("total_estimated_cost_krw")),
                    str(item.get("total_llm_tokens", 0)),
                    ", ".join(item.get("actual_generation_models") or []),
                ]
            )
            + " |"
            for item in report.highest_cost_cases
        ],
        "",
        "### Highest Wasted Candidate Cases",
        "",
        "| case | wasted_candidate_ratio | generated | rejected |",
        "| --- | ---: | ---: | ---: |",
        *[
            "| "
            + " | ".join(
                [
                    str(item.get("case_id", "")),
                    _format_optional(item.get("wasted_candidate_ratio")),
                    str(item.get("generated_count", 0)),
                    str(item.get("rejected_count", 0)),
                ]
            )
            + " |"
            for item in report.highest_wasted_candidate_cases
        ],
        "",
        "## Bottleneck Distribution",
        "",
        "| component | count |",
        "| --- | ---: |",
        *[f"| {component} | {count} |" for component, count in sorted(report.bottleneck_counts.items())],
        "",
        "## Case Summary",
        "",
        "| case | repeat | threshold | generated | rejected | raw_hit | context_recall | cited_recall | commercial | total_ms | search_ms | service_search_ms | bottleneck | warnings |",
        "| --- | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | ---: |",
    ]
    for case in report.cases:
        lines.append(
            "| "
            + " | ".join(
                [
                    case.case_id,
                    f"r{case.repeat_index}",
                    "pass" if case.threshold_passed else "fail",
                    str(case.passed_count),
                    str(case.rejected_count),
                    _format_optional(case.hit_at_k),
                    _format_optional(case.generation_context_expected_chunk_recall),
                    _format_optional(case.cited_expected_chunk_recall),
                    _format_optional(case.commercial_quality_score),
                    _format_optional(case.total_ms),
                    _format_optional(case.search_ms),
                    _format_optional(case.service_internal_search_ms),
                    str(case.bottleneck_component or ""),
                    str(case.warning_count),
                ]
            )
            + " |"
        )
    if report.case_stability_summary:
        lines.extend(
            [
                "",
                "## Repeated-Run Stability",
                "",
                "| case | runs | pass_rate | avg_reject_rate | avg_retry | avg_quality | quality_stddev | max_question_similarity | repeated_template_count |",
                "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
            ]
        )
        for case_id, summary in sorted(report.case_stability_summary.items()):
            lines.append(
                "| "
                + " | ".join(
                    [
                        case_id,
                        str(summary.get("run_count", 0)),
                        _format_optional(summary.get("pass_rate")),
                        _format_optional(summary.get("average_reject_rate")),
                        _format_optional(summary.get("average_retry_count")),
                        _format_optional(summary.get("average_quality_score")),
                        _format_optional(summary.get("quality_score_stddev")),
                        _format_optional(summary.get("duplicate_question_similarity_max")),
                        str(summary.get("repeated_reasoning_template_count", 0)),
                    ]
                )
                + " |"
            )
    failed_cases = [case for case in report.cases if case.execution_status != "completed"]
    if failed_cases:
        lines.extend(
            [
                "",
                "## Failed Cases",
                "",
                "| case | execution_status | failure_stage | raw_chunks | context_chunks | raw_atoms | kernel | top_rejection_categories | exception_type | exception_message | threshold_failures |",
                "| --- | --- | --- | ---: | ---: | ---: | --- | --- | --- | --- | --- |",
            ]
        )
        for case in failed_cases:
            lines.append(
                "| "
                + " | ".join(
                    [
                        case.case_id,
                        case.execution_status,
                        str(case.failure_stage or case.exception_stage or ""),
                        str(case.returned_chunk_count),
                        str(case.generation_context_chunk_count),
                        str(case.raw_content_atom_count),
                        str(case.problem_kernel_type or case.kernel_planning_failure_reason or ""),
                        _markdown_cell(", ".join(case.failure_top_rejection_categories)),
                        str(case.exception_type or ""),
                        _markdown_cell(str(case.exception_message or "")),
                        _markdown_cell("; ".join(case.threshold_failures)),
                    ]
                )
                + " |"
            )
    lines.extend(
        [
            "",
            "## Slowest Cases",
            "",
            "| case | total_ms | search_ms | service_search_ms | generation_ms | quality_filter_ms |",
            "| --- | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for case in sorted(report.cases, key=lambda item: item.total_ms or 0, reverse=True)[:5]:
        lines.append(
            "| "
            + " | ".join(
                [
                    case.case_id,
                    _format_optional(case.total_ms),
                    _format_optional(case.search_ms),
                    _format_optional(case.service_internal_search_ms),
                    _format_optional(case.candidate_generation_total_ms),
                    _format_optional(case.quality_filter_total_ms),
                ]
            )
            + " |"
        )
    ab_cases = [case for case in report.cases if case.baseline_search_ms is not None or case.enhanced_search_ms is not None]
    if ab_cases:
        lines.extend(
            [
                "",
                "## Search Latency",
                "",
                "| case | effective_search_ms | baseline_search_ms | enhanced_search_ms | service_search_ms | note |",
                "| --- | ---: | ---: | ---: | ---: | --- |",
            ]
        )
        for case in ab_cases:
            lines.append(
                "| "
                + " | ".join(
                    [
                        case.case_id,
                        _format_optional(case.effective_search_ms),
                        _format_optional(case.baseline_search_ms),
                        _format_optional(case.enhanced_search_ms),
                        _format_optional(case.service_internal_search_ms),
                        str(case.search_latency_note or ""),
                    ]
                )
                + " |"
            )
    sweep_cases = [case for case in report.cases if case.query_mode_scores]
    if sweep_cases:
        lines.extend(
            [
                "",
                "## Search Query Mode Sweep",
                "",
                "| case | primary_mode | best_mode | baseline | compact | hybrid | expanded | primary_score |",
                "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: |",
            ]
        )
        for case in sweep_cases:
            lines.append(
                "| "
                + " | ".join(
                    [
                        case.case_id,
                        case.search_query_mode,
                        str(case.best_query_mode_by_score or ""),
                        _format_optional(case.query_mode_scores.get("baseline")),
                        _format_optional(case.query_mode_scores.get("compact")),
                        _format_optional(case.query_mode_scores.get("hybrid")),
                        _format_optional(case.query_mode_scores.get("expanded")),
                        _format_optional(case.primary_query_mode_score),
                    ]
                )
                + " |"
            )
        not_best_cases = [
            case
            for case in sweep_cases
            if case.best_query_mode_by_score is not None
            and case.best_query_mode_by_score != case.search_query_mode
        ]
        if not_best_cases:
            lines.extend(
                [
                    "",
                    "## Configured Query Mode Not Best",
                    "",
                    "| case | configured_mode | best_mode | configured_score | best_score |",
                    "| --- | --- | --- | ---: | ---: |",
                ]
            )
            for case in not_best_cases:
                best_score = case.query_mode_scores.get(case.best_query_mode_by_score or "")
                lines.append(
                    "| "
                    + " | ".join(
                        [
                            case.case_id,
                            case.search_query_mode,
                            str(case.best_query_mode_by_score or ""),
                            _format_optional(case.primary_query_mode_score),
                            _format_optional(best_score),
                        ]
                    )
                    + " |"
                )
    lines.extend(
        [
            "",
            "## Highest Reject-Rate Cases",
            "",
            "| case | reject_rate | generated | rejected | warnings |",
            "| --- | ---: | ---: | ---: | ---: |",
        ]
    )
    for case in sorted(report.cases, key=lambda item: item.reject_rate or 0, reverse=True)[:5]:
        lines.append(
            "| "
            + " | ".join(
                [
                    case.case_id,
                    _format_optional(case.reject_rate),
                    str(case.generated_count),
                    str(case.rejected_count),
                    str(case.warning_count),
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## Lowest Search-Quality Cases",
            "",
            "| case | golden_mode | hit_at_k | mrr_at_k | precision_at_k | context_recall | cited_recall | cited_precision | context_span_coverage | cited_span_coverage | span_coverage | enhanced_score_delta | returned_chunks |",
            "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for case in sorted(report.cases, key=_search_quality_sort_key)[:5]:
        lines.append(
            "| "
            + " | ".join(
                [
                    case.case_id,
                    case.golden_label_mode,
                    _format_optional(case.hit_at_k),
                    _format_optional(case.mrr_at_k),
                    _format_optional(case.precision_at_k),
                    _format_optional(case.generation_context_expected_chunk_recall),
                    _format_optional(case.cited_expected_chunk_recall),
                    _format_optional(case.cited_expected_chunk_precision),
                    _format_optional(case.generation_context_source_span_coverage),
                    _format_optional(case.cited_source_span_coverage),
                    _format_optional(case.source_span_coverage),
                    _format_optional(case.enhanced_score_minus_baseline_score),
                    str(case.returned_chunk_count),
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## Lowest Problem-Quality Cases",
            "",
            "| case | avg_score | low_quality | medium_quality | avg_source_coverage |",
            "| --- | ---: | ---: | ---: | ---: |",
        ]
    )
    for case in sorted(report.cases, key=_problem_quality_sort_key)[:5]:
        lines.append(
            "| "
            + " | ".join(
                [
                    case.case_id,
                    _format_optional(case.average_professor_grade_score),
                    str(case.low_quality_problem_count),
                    str(case.medium_quality_problem_count),
                    _format_optional(case.average_source_term_coverage),
                ]
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## High-Rigor Operation Distribution",
            "",
            "| operation | count |",
            "| --- | ---: |",
        ]
    )
    for operation, count in sorted(report.high_rigor_operation_counts.items()):
        lines.append(f"| {operation} | {count} |")
    if report.llm_judge_enabled:
        lines.extend(
            [
                "",
                "## LLM Judge",
                "",
                f"- generation_model: {report.generation_model or 'unknown'}",
                f"- judge_model: {report.judge_model or 'unknown'}",
                f"- judge_same_model_warning: {report.judge_same_model_warning}",
                f"- judge_same_family_warning: {report.judge_same_family_warning}",
                "",
                "### Judge Independence Notes",
                "",
                *(
                    [f"- {note}" for note in report.judge_independence_notes]
                    if report.judge_independence_notes
                    else ["- none"]
                ),
                "",
                "| action | count |",
                "| --- | ---: |",
            ]
        )
        for action, count in sorted(report.llm_judge_action_counts.items()):
            lines.append(f"| {action} | {count} |")
    lines.append("")
    return "\n".join(lines)


def _chunk_text(chunks: list[RetrievedChunk]) -> str:
    return " ".join(
        " ".join(
            [
                chunk.content or "",
                chunk.section_title or "",
                " ".join(chunk.concepts or []),
                " ".join(chunk.tags or []),
                json.dumps(chunk.metadata or {}, ensure_ascii=False),
            ]
        )
        for chunk in chunks
    )


def _problem_text(problems: list[Problem]) -> str:
    parts: list[str] = []
    for problem in problems:
        parts.append(_single_problem_text(problem))
    return " ".join(parts)


def _single_problem_text(problem: Problem) -> str:
    return " ".join(
        [
            str(problem.question or ""),
            str(problem.explanation or ""),
            json.dumps(problem.answer or {}, ensure_ascii=False),
            json.dumps(problem.choices or [], ensure_ascii=False),
            json.dumps(problem.choice_explanations or {}, ensure_ascii=False),
            json.dumps(problem.choice_diagnostics or [], ensure_ascii=False),
            json.dumps(problem.rubric or [], ensure_ascii=False),
            json.dumps(problem.item_design_brief or {}, ensure_ascii=False),
        ]
    )


def _term_coverage(
    terms: list[str],
    text: str,
    aliases: dict[str, list[str]] | None = None,
) -> float:
    raw_text = _normalize_whitespace(str(text or "")).lower()
    comparable_text = _normalize_term_match_text(text)
    normalized_terms = [str(term).strip() for term in terms if str(term).strip()]
    if not normalized_terms:
        return 1.0
    matched = sum(
        1
        for term in normalized_terms
        if _term_matches_text(
            term=term,
            raw_text=raw_text,
            comparable_text=comparable_text,
            aliases=aliases or {},
        )
    )
    return matched / len(normalized_terms)


def _term_matches_text(
    *,
    term: str,
    raw_text: str,
    comparable_text: str,
    aliases: dict[str, list[str]],
) -> bool:
    candidates = [term, *_term_aliases(term, aliases)]
    for candidate in candidates:
        raw_candidate = _normalize_whitespace(str(candidate or "")).lower()
        comparable_candidate = _normalize_term_match_text(candidate)
        if raw_candidate and raw_candidate in raw_text:
            return True
        if comparable_candidate and comparable_candidate in comparable_text:
            return True
    return False


def _term_aliases(term: str, aliases: dict[str, list[str]]) -> list[str]:
    normalized_term = _normalize_term_match_text(term)
    matched_aliases: list[str] = []
    for key, values in aliases.items():
        if str(key).strip() == str(term).strip() or _normalize_term_match_text(key) == normalized_term:
            matched_aliases.extend(str(value) for value in values if str(value).strip())
    return matched_aliases


def _normalize_term_match_text(value: object) -> str:
    text = _normalize_whitespace(str(value or "")).lower()
    text = re.sub(r"\bb\s*\[\s*\+\s*\]\s*-?\s*tree\b", "b plus tree", text)
    text = re.sub(r"\bb\s*\+\s*-?\s*tree\b", "b plus tree", text)
    text = re.sub(r"\bb\s*\[\s*\+\s*\]", "b plus", text)
    text = re.sub(r"\bb\s*\+", "b plus", text)
    text = re.sub(r"\bi\s*/\s*o\b", "io", text)
    text = re.sub(r"[^0-9a-z가-힣]+", " ", text)
    return _normalize_whitespace(text)


def _normalize_whitespace(value: str) -> str:
    return " ".join(str(value or "").split())


def _retrieval_metrics_for_case(
    case: LiveProblemGenerationEvalCase,
    chunks: list[RetrievedChunk],
) -> dict[str, float | int | None]:
    return {
        "hit_at_k": _hit_at_k(case.expected_chunk_ids, chunks),
        "mrr_at_k": _mrr_at_k(case.expected_chunk_ids, chunks),
        "precision_at_k": _precision_at_k(case.expected_chunk_ids, chunks),
        "expected_page_hit": _expected_page_hit(case.expected_pages, chunks),
        "source_span_coverage": _source_span_coverage(case.expected_source_spans, chunks),
        "irrelevant_term_hit_count": _irrelevant_term_hit_count(case.irrelevant_terms, chunks),
    }


def _cited_evidence_metrics_for_case(
    *,
    case: LiveProblemGenerationEvalCase,
    chunks: list[RetrievedChunk],
    problems: list[Problem],
) -> dict[str, Any]:
    expected_ids = [str(chunk_id).strip() for chunk_id in case.expected_chunk_ids if str(chunk_id).strip()]
    expected = set(expected_ids)
    cited_ids = _cited_chunk_ids(problems)
    cited = set(cited_ids)
    cited_expected_ids = [chunk_id for chunk_id in expected_ids if chunk_id in cited]
    uncited_expected_ids = [chunk_id for chunk_id in expected_ids if chunk_id not in cited]
    cited_non_expected_ids = [chunk_id for chunk_id in cited_ids if expected and chunk_id not in expected]
    if expected:
        cited_hit_at_k = 1.0 if cited_expected_ids else 0.0
        cited_expected_chunk_recall = len(cited_expected_ids) / len(expected)
        cited_expected_chunk_precision = len(cited_expected_ids) / len(cited_ids) if cited_ids else 0.0
    else:
        cited_hit_at_k = None
        cited_expected_chunk_recall = None
        cited_expected_chunk_precision = None

    chunk_by_id = {chunk.chunk_id: chunk for chunk in chunks}
    cited_chunks = [chunk_by_id[chunk_id] for chunk_id in cited_ids if chunk_id in chunk_by_id]
    return {
        "cited_expected_chunk_recall": cited_expected_chunk_recall,
        "cited_expected_chunk_precision": cited_expected_chunk_precision,
        "cited_hit_at_k": cited_hit_at_k,
        "cited_source_span_coverage": _source_span_coverage(case.expected_source_spans, cited_chunks),
        "cited_expected_chunk_ids": cited_expected_ids,
        "uncited_expected_chunk_ids": uncited_expected_ids,
        "cited_non_expected_chunk_ids": cited_non_expected_ids,
    }


def _generation_context_metrics_for_case(
    *,
    case: LiveProblemGenerationEvalCase,
    chunks: list[RetrievedChunk],
    generation_context_chunk_ids: list[str],
) -> dict[str, Any]:
    expected_ids = [str(chunk_id).strip() for chunk_id in case.expected_chunk_ids if str(chunk_id).strip()]
    expected = set(expected_ids)
    context_ids = [str(chunk_id).strip() for chunk_id in generation_context_chunk_ids if str(chunk_id).strip()]
    context = set(context_ids)
    context_expected_ids = [chunk_id for chunk_id in expected_ids if chunk_id in context]
    if expected:
        context_hit_at_k = 1.0 if context_expected_ids else 0.0
        context_expected_recall = len(context_expected_ids) / len(expected)
        context_expected_precision = len(context_expected_ids) / len(context_ids) if context_ids else 0.0
    else:
        context_hit_at_k = None
        context_expected_recall = None
        context_expected_precision = None

    chunk_by_id = {chunk.chunk_id: chunk for chunk in chunks}
    context_chunks = [chunk_by_id[chunk_id] for chunk_id in context_ids if chunk_id in chunk_by_id]
    retrieved_count = len(chunks)
    context_count = len(context_ids)
    return {
        "generation_context_chunk_count": context_count,
        "generation_context_expected_chunk_recall": context_expected_recall,
        "generation_context_expected_chunk_precision": context_expected_precision,
        "generation_context_hit_at_k": context_hit_at_k,
        "generation_context_source_span_coverage": _source_span_coverage(case.expected_source_spans, context_chunks),
        "retrieved_to_context_reduction_ratio": (
            1 - (context_count / retrieved_count) if retrieved_count > 0 else None
        ),
    }


def _kernel_atom_dropped_count(
    *,
    selected_kernel_atom_chunk_ids: list[str],
    generation_context_chunk_ids: list[str],
) -> int:
    selected = {str(chunk_id).strip() for chunk_id in selected_kernel_atom_chunk_ids if str(chunk_id).strip()}
    context = {str(chunk_id).strip() for chunk_id in generation_context_chunk_ids if str(chunk_id).strip()}
    return len(selected - context)


def _cited_chunk_ids(problems: list[Problem]) -> list[str]:
    seen: set[str] = set()
    ids: list[str] = []
    for problem in problems:
        for chunk_id in problem.source_chunk_ids or []:
            normalized = str(chunk_id).strip()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            ids.append(normalized)
    return ids


def _hit_at_k(expected_chunk_ids: list[str], chunks: list[RetrievedChunk]) -> float | None:
    expected = {str(chunk_id).strip() for chunk_id in expected_chunk_ids if str(chunk_id).strip()}
    if not expected:
        return None
    retrieved = {chunk.chunk_id for chunk in chunks}
    return 1.0 if expected & retrieved else 0.0


def _mrr_at_k(expected_chunk_ids: list[str], chunks: list[RetrievedChunk]) -> float | None:
    expected = {str(chunk_id).strip() for chunk_id in expected_chunk_ids if str(chunk_id).strip()}
    if not expected:
        return None
    for index, chunk in enumerate(chunks, start=1):
        if chunk.chunk_id in expected:
            return 1.0 / index
    return 0.0


def _precision_at_k(expected_chunk_ids: list[str], chunks: list[RetrievedChunk]) -> float | None:
    expected = {str(chunk_id).strip() for chunk_id in expected_chunk_ids if str(chunk_id).strip()}
    if not expected:
        return None
    if not chunks:
        return 0.0
    hits = sum(1 for chunk in chunks if chunk.chunk_id in expected)
    return hits / len(chunks)


def _expected_page_hit(expected_pages: list[int], chunks: list[RetrievedChunk]) -> float | None:
    expected = {int(page) for page in expected_pages}
    if not expected:
        return None
    retrieved_pages = {chunk.page for chunk in chunks if chunk.page is not None}
    return 1.0 if expected & retrieved_pages else 0.0


def _source_span_coverage(expected_source_spans: list[str], chunks: list[RetrievedChunk]) -> float | None:
    spans = [_normalize_retrieval_text(span) for span in expected_source_spans if str(span).strip()]
    if not spans:
        return None
    normalized_text = _normalize_retrieval_text(_chunk_text(chunks))
    matched = sum(1 for span in spans if span in normalized_text)
    return matched / len(spans)


def _irrelevant_term_hit_count(irrelevant_terms: list[str], chunks: list[RetrievedChunk]) -> int:
    terms = [_normalize_retrieval_text(term) for term in irrelevant_terms if str(term).strip()]
    if not terms:
        return 0
    normalized_text = _normalize_retrieval_text(_chunk_text(chunks))
    return sum(1 for term in terms if term in normalized_text)


def _normalize_retrieval_text(value: object) -> str:
    return " ".join(str(value or "").lower().split())


def _concept_overlap_ratio(concepts: list[str], chunks: list[RetrievedChunk]) -> float:
    return _term_coverage(concepts, _chunk_text(chunks))


def _concept_overlap_ratio_from_comparison(
    search_comparison: dict[str, Any],
    chunks: list[RetrievedChunk],
) -> float:
    return _concept_overlap_ratio(search_comparison["concepts"], chunks)


def _search_quality_score(
    *,
    case: LiveProblemGenerationEvalCase,
    chunks: list[RetrievedChunk],
    min_returned_chunks: int,
) -> float:
    returned_chunk_sufficiency = min(len(chunks) / max(min_returned_chunks, 1), 1.0)
    if case.expected_chunk_ids or case.expected_source_spans:
        retrieval_metrics = _retrieval_metrics_for_case(case, chunks)
        if case.golden_label_mode == "exhaustive" and case.expected_chunk_ids:
            return (
                0.25 * float(retrieval_metrics["hit_at_k"] or 0.0)
                + 0.20 * float(retrieval_metrics["mrr_at_k"] or 0.0)
                + 0.20 * float(retrieval_metrics["precision_at_k"] or 0.0)
                + 0.20 * float(retrieval_metrics["source_span_coverage"] or 0.0)
                + 0.10
                * _term_coverage(
                    case.expected_search_terms,
                    _chunk_text(chunks),
                    aliases=case.expected_search_term_aliases,
                )
                + 0.05 * _concept_overlap_ratio(case.concepts, chunks)
            )
        return (
            0.35 * float(retrieval_metrics["hit_at_k"] or 0.0)
            + 0.25 * float(retrieval_metrics["mrr_at_k"] or 0.0)
            + 0.20 * float(retrieval_metrics["source_span_coverage"] or 0.0)
            + 0.10
            * _term_coverage(
                case.expected_search_terms,
                _chunk_text(chunks),
                aliases=case.expected_search_term_aliases,
            )
            + 0.10 * _concept_overlap_ratio(case.concepts, chunks)
        )
    return (
        0.45
        * _term_coverage(
            case.expected_search_terms,
            _chunk_text(chunks),
            aliases=case.expected_search_term_aliases,
        )
        + 0.35 * _concept_overlap_ratio(case.concepts, chunks)
        + 0.20 * returned_chunk_sufficiency
    )


def _unique_chunk_ids(chunks: list[RetrievedChunk]) -> list[str]:
    seen: set[str] = set()
    ids: list[str] = []
    for chunk in chunks:
        if chunk.chunk_id in seen:
            continue
        seen.add(chunk.chunk_id)
        ids.append(chunk.chunk_id)
    return ids


def _chunk_id_overlap_ratio(baseline_ids: list[str], enhanced_ids: list[str]) -> float:
    if not baseline_ids and not enhanced_ids:
        return 1.0
    union = set(baseline_ids) | set(enhanced_ids)
    if not union:
        return 0.0
    return len(set(baseline_ids) & set(enhanced_ids)) / len(union)


def _metadata_score_summary(chunks: list[RetrievedChunk]) -> dict[str, dict[str, float]]:
    values_by_key: dict[str, list[float]] = {"score": [], "distance": []}
    score_keys = {"score", "similarity", "relevance_score"}
    distance_keys = {"distance", "dist"}
    for chunk in chunks:
        for key, value in (chunk.metadata or {}).items():
            if not isinstance(value, int | float):
                continue
            normalized_key = str(key).lower()
            if normalized_key in score_keys:
                values_by_key["score"].append(float(value))
            if normalized_key in distance_keys:
                values_by_key["distance"].append(float(value))
    return {
        key: {
            "min": min(values),
            "max": max(values),
            "avg": sum(values) / len(values),
        }
        for key, values in values_by_key.items()
        if values
    }


def _high_rigor_item_model_id_coverage(request: GenerateProblemRequest, problems: list[Problem]) -> float | None:
    if not _is_high_rigor_request(request):
        return None
    if not problems:
        return 0.0
    return sum(1 for problem in problems if problem.item_model_id) / len(problems)


def _high_rigor_mc_choice_diagnostics_coverage(
    request: GenerateProblemRequest,
    problems: list[Problem],
) -> float | None:
    mc_problems = [problem for problem in problems if problem.type == ProblemType.multiple_choice.value]
    if not _is_high_rigor_request(request) or not mc_problems:
        return None
    covered = 0
    for problem in mc_problems:
        diagnostics = problem.choice_diagnostics or []
        choices = problem.choices or []
        if len(diagnostics) >= len(choices) >= 1:
            covered += 1
    return covered / len(mc_problems)


def _short_answer_rubric_coverage(problems: list[Problem]) -> float | None:
    short_answers = [problem for problem in problems if problem.type == ProblemType.short_answer.value]
    if not short_answers:
        return None
    return sum(1 for problem in short_answers if problem.rubric) / len(short_answers)


def _is_high_rigor_request(request: GenerateProblemRequest) -> bool:
    return (
        request.target_rigor == TargetRigor.high
        or request.difficulty == Difficulty.hard
        or request.bloom_level in {BloomLevel.analyze, BloomLevel.evaluate, BloomLevel.create}
        or request.quality_mode == QualityMode.strict
    )


def _average(values: list[float | int | None]) -> float | None:
    present = [float(value) for value in values if value is not None]
    if not present:
        return None
    return sum(present) / len(present)


def _percentile(values: list[float | int | None], percentile: float) -> float | None:
    """Return a linear-interpolated percentile over non-null values.

    The percentile argument uses the common 0-100 scale, so 50 is p50 and 95 is p95.
    """

    present = sorted(float(value) for value in values if value is not None)
    if not present:
        return None
    if percentile <= 0:
        return present[0]
    if percentile >= 100:
        return present[-1]
    rank = (percentile / 100) * (len(present) - 1)
    lower_index = int(rank)
    upper_index = min(lower_index + 1, len(present) - 1)
    fraction = rank - lower_index
    return present[lower_index] + (present[upper_index] - present[lower_index]) * fraction


def _classify_bottleneck(
    *,
    total_ms: float | None,
    search_ms: float | None,
    candidate_generation_total_ms: float | None,
    quality_filter_total_ms: float | None,
    db_write_ms: float | None,
    db_commit_ms: float | None,
    db_refresh_ms: float | None,
    artifact_publish_ms: float | None,
) -> dict[str, str | float | None]:
    components = {
        "search": search_ms,
        "generation": candidate_generation_total_ms,
        "quality_filter": quality_filter_total_ms,
        "db_write": db_write_ms,
        "db_commit": db_commit_ms,
        "db_refresh": db_refresh_ms,
        "artifact_publish": artifact_publish_ms,
    }
    present = {
        component: float(value)
        for component, value in components.items()
        if value is not None and value >= 0
    }
    if not present:
        return {"component": None, "component_ms": None, "component_ratio": None}
    component, component_ms = max(present.items(), key=lambda item: item[1])
    component_ratio = component_ms / total_ms if total_ms and total_ms > 0 else None
    return {
        "component": component,
        "component_ms": component_ms,
        "component_ratio": component_ratio,
    }


def _elapsed_ms(started: float) -> float:
    return (time.perf_counter() - started) * 1000


def _merge_counter(counters: Iterator[dict[str, int]]) -> dict[str, int]:
    merged: Counter[str] = Counter()
    for counter in counters:
        merged.update(counter)
    return dict(merged)


def _normalize_repeat_count(value: int | str) -> int:
    try:
        repeat_count = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("PROBLEM_AGENT_LIVE_EVAL_REPEAT_COUNT must be an integer from 1 to 10") from exc
    if repeat_count < 1 or repeat_count > 10:
        raise ValueError("PROBLEM_AGENT_LIVE_EVAL_REPEAT_COUNT must be between 1 and 10")
    return repeat_count


def _normalize_human_review_export_mode(value: object) -> Literal["full", "redacted"]:
    mode = str(value or "full").strip().lower()
    if mode == "full" or mode == "redacted":
        return mode
    raise ValueError("PROBLEM_AGENT_LIVE_EVAL_HUMAN_REVIEW_EXPORT_MODE must be 'full' or 'redacted'")


def _normalize_rejected_candidate_export_mode(value: object) -> Literal["full", "redacted"]:
    mode = str(value or "redacted").strip().lower()
    if mode == "full" or mode == "redacted":
        return mode
    raise ValueError(
        "PROBLEM_AGENT_LIVE_EVAL_REJECTED_CANDIDATE_EXPORT_MODE must be 'full' or 'redacted'"
    )


def _case_stability_summary(
    *,
    results: list[LiveProblemGenerationCaseResult],
    cases_by_id: dict[str, LiveProblemGenerationEvalCase],
) -> dict[str, Any]:
    grouped: dict[str, list[LiveProblemGenerationCaseResult]] = {}
    for result in results:
        group_id = result.repeated_case_group_id or result.case_id
        grouped.setdefault(group_id, []).append(result)

    summary: dict[str, Any] = {}
    for group_id, group_results in grouped.items():
        case = cases_by_id.get(group_id)
        request = _safe_request_from_case(case) if case is not None else None
        high_rigor = _is_high_rigor_request(request) if request is not None else False
        run_count = len(group_results)
        operation_counts = _merge_counter(result.high_rigor_operation_counts for result in group_results)
        questions = [
            row.question
            for result in group_results
            for row in result.human_review_rows
            if row.question.strip()
        ]
        duplicate_similarity_max = _max_text_similarity(questions)
        primary_operations = [_primary_operation_label(result.high_rigor_operation_counts) for result in group_results]
        primary_operations = [operation for operation in primary_operations if operation]
        repeated_reasoning_template_count = 0
        failure_messages: list[str] = []
        threshold_failures: list[str] = []

        if primary_operations:
            repeated_reasoning_template_count = max(Counter(primary_operations).values())
        if high_rigor and run_count > 1 and len(primary_operations) == run_count and len(set(primary_operations)) == 1:
            failure_messages.append("same reasoning template appears in all repeats")

        min_repeat_pass_rate = case.min_repeat_pass_rate if case is not None else None
        if min_repeat_pass_rate is None and high_rigor:
            min_repeat_pass_rate = 0.67
        pass_rate = sum(1 for result in group_results if result.threshold_passed) / run_count if run_count else 0.0
        if min_repeat_pass_rate is not None and pass_rate < min_repeat_pass_rate:
            threshold_failures.append(f"repeat pass_rate {pass_rate:.3f} < {min_repeat_pass_rate}")

        quality_scores = [result.average_professor_grade_score for result in group_results]
        quality_score_stddev = _stddev(quality_scores)
        max_quality_stddev = case.max_repeat_quality_score_stddev if case is not None else None
        if (
            max_quality_stddev is not None
            and quality_score_stddev is not None
            and quality_score_stddev > max_quality_stddev
        ):
            threshold_failures.append(
                f"repeat quality_score_stddev {quality_score_stddev:.3f} > {max_quality_stddev}"
            )

        max_duplicate_similarity = case.max_repeat_duplicate_similarity if case is not None else None
        if max_duplicate_similarity is None and run_count > 1:
            max_duplicate_similarity = 0.85
        if (
            max_duplicate_similarity is not None
            and duplicate_similarity_max is not None
            and duplicate_similarity_max > max_duplicate_similarity
        ):
            threshold_failures.append(
                f"repeat duplicate_question_similarity_max {duplicate_similarity_max:.3f} > {max_duplicate_similarity}"
            )

        failure_messages.extend(
            message
            for result in group_results
            for message in [*(result.threshold_failures or []), *(result.warnings or [])]
            if message
        )
        failure_messages.extend(threshold_failures)

        summary[group_id] = {
            "run_count": run_count,
            "pass_rate": pass_rate,
            "average_reject_rate": _average([result.reject_rate for result in group_results]),
            "average_retry_count": _average([result.actual_retry_count for result in group_results]),
            "average_quality_score": _average(quality_scores),
            "quality_score_stddev": quality_score_stddev,
            "average_total_ms": _average([result.total_ms for result in group_results]),
            "generated_operation_counts": operation_counts,
            "duplicate_question_similarity_max": duplicate_similarity_max,
            "repeated_reasoning_template_count": repeated_reasoning_template_count,
            "failure_messages": list(dict.fromkeys(failure_messages)),
            "threshold_failures": threshold_failures,
        }
    return summary


def _apply_stability_thresholds(
    *,
    results: list[LiveProblemGenerationCaseResult],
    stability_summary: dict[str, Any],
) -> None:
    for result in results:
        group_id = result.repeated_case_group_id or result.case_id
        failures = list(stability_summary.get(group_id, {}).get("threshold_failures") or [])
        if not failures:
            continue
        prefixed = [f"repeat stability: {failure}" for failure in failures]
        result.threshold_failures = list(dict.fromkeys([*result.threshold_failures, *prefixed]))
        result.threshold_passed = False
        _apply_threshold_failure_categories(result)


def _primary_operation_label(operation_counts: dict[str, int]) -> str | None:
    if not operation_counts:
        return None
    return Counter(operation_counts).most_common(1)[0][0]


def _max_text_similarity(texts: list[str]) -> float | None:
    if len(texts) < 2:
        return None
    max_similarity = 0.0
    for left_index, left in enumerate(texts):
        for right in texts[left_index + 1 :]:
            max_similarity = max(max_similarity, _text_similarity(left, right))
    return max_similarity


def _text_similarity(left: str, right: str) -> float:
    left_tokens = _similarity_tokens(left)
    right_tokens = _similarity_tokens(right)
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / len(left_tokens | right_tokens)


def _similarity_tokens(text: str) -> set[str]:
    normalized = re.sub(r"\d+(?:\.\d+)?", "<num>", str(text or "").lower())
    return {token for token in re.findall(r"[0-9a-zA-Z가-힣_+]+", normalized) if len(token) > 1}


def _stddev(values: list[float | int | None]) -> float | None:
    present = [float(value) for value in values if value is not None]
    if not present:
        return None
    if len(present) == 1:
        return 0.0
    mean = sum(present) / len(present)
    return (sum((value - mean) ** 2 for value in present) / len(present)) ** 0.5


def _search_quality_sort_key(case: LiveProblemGenerationCaseResult) -> tuple[float, float]:
    score = (
        case.enhanced_search_quality_score
        if case.enhanced_search_quality_score is not None
        else (
            (case.hit_at_k or 0.0)
            if case.hit_at_k is not None
            else case.expected_search_term_coverage
        )
    )
    return (score, case.concept_overlap_ratio)


def _problem_quality_sort_key(case: LiveProblemGenerationCaseResult) -> tuple[float, float, float]:
    score = case.average_professor_grade_score if case.average_professor_grade_score is not None else 1.0
    source_coverage = case.average_source_term_coverage if case.average_source_term_coverage is not None else 1.0
    return (score, source_coverage, -case.low_quality_problem_count)


def _format_optional(value: float | None) -> str:
    if value is None:
        return "-"
    return f"{value:.3f}"


def _markdown_cell(value: str) -> str:
    return re.sub(r"\s+", " ", value).replace("|", "\\|").strip()


if __name__ == "__main__":
    run_live_problem_generation_eval_from_env()
