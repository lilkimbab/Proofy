from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import re
import time

from sqlalchemy import inspect as sqlalchemy_inspect
from sqlalchemy.orm import Session

from app.agents import ProblemAgent, ProblemQualityChecker
from app.config import Settings, get_settings
from app.llm import safety_identifier_for_user
from app.models import Feedback, Problem
from app.repositories.problem_item_analytics_repository import ProblemItemAnalyticsRepository
from app.repositories.problem_hint_repository import ProblemHintRepository
from app.repositories.problem_repository import ProblemRepository
from app.repositories.problem_regeneration_candidate_repository import ProblemRegenerationCandidateRepository
from app.repositories.problem_template_analytics_repository import ProblemTemplateAnalyticsRepository
from app.repositories.usage_ledger_repository import UsageLedgerRepository
from app.schemas.integration_contracts import RetrievedChunk
from app.schemas.problem_kernels import ContentAtom, ContentAtomType, ProblemKernelPlan
from app.schemas.problems import (
    BloomLevel,
    Difficulty,
    GenerateProblemRequest,
    HintLevel,
    HintMode,
    MistakeType,
    ProblemDepth,
    ProblemHintRequest,
    ProblemHintResponse,
    ProblemStyle,
    ProblemType,
)
from app.schemas.quality import (
    AssessmentBlueprint,
    CourseLevel,
    GenerationAttemptMetrics,
    GenerationGoal,
    GenerationPerformanceSummary,
    GenerationQualitySummary,
    HighRigorGenerationProfile,
    LearningTaskStrategyProfile,
    MaterialReadinessReport,
    QualityMode,
    QualityStatus,
    SourceGroundingProfile,
    TargetRigor,
)
from app.services.assessment_blueprint_service import AssessmentBlueprintPlanner
from app.services.content_atom_extractor import ContentAtomExtractor
from app.services.evidence_obligation_evaluator import EvidenceObligationEvaluator, EvidenceObligationReport
from app.services.generated_artifact_publisher import GeneratedArtifactPublisher
from app.services.high_rigor_generation_service import AdaptiveHighRigorPlanner
from app.services.learning_task_strategy_router import LearningTaskStrategyRouter
from app.services.material_readiness_service import MaterialReadinessAnalyzer
from app.services.problem_answer_verifier import ProblemAnswerVerifier
from app.services.problem_kernel_planner import ProblemKernelPlanner
from app.services.professor_grade_item_service import ProfessorGradeItemDesigner
from app.services.rejected_candidate_artifact_writer import RejectedCandidateArtifactWriter
from app.services.request_safety import validate_safe_user_requirements
from app.services.search_service import SearchAgentError, SearchService
from app.services.source_grounding_policy_service import SourceGroundingPolicyPlanner


@dataclass(frozen=True)
class ProblemGenerationBatchResult:
    problems: list[Problem]
    learning_task_strategy: LearningTaskStrategyProfile
    material_readiness: MaterialReadinessReport
    blueprint: AssessmentBlueprint
    high_rigor_profile: HighRigorGenerationProfile
    source_grounding_profile: SourceGroundingProfile
    quality_summary: GenerationQualitySummary


class KernelPlanningFailure(ValueError):
    def __init__(self, message: str, *, trace: dict | None = None):
        super().__init__(message)
        self.trace = trace or {}


class ProblemGenerationFailure(ValueError):
    def __init__(self, message: str, *, trace: dict | None = None):
        super().__init__(message)
        self.trace = trace or {}


class ProblemService:
    EVIDENCE_SNAPSHOT_CONTENT_LIMIT = 2400
    SEARCH_QUERY_STYLE_CUES = {
        ProblemStyle.error_detection: (
            "오류",
            "잘못",
            "틀린",
            "반례",
            "예외",
            "수정",
            "error",
            "bug",
            "misconception",
        ),
        ProblemStyle.calculation_practice: (
            "공식",
            "수식",
            "계산",
            "단위",
            "변수",
            "대입",
            "formula",
            "equation",
            "unit",
        ),
        ProblemStyle.evidence_analysis: (
            "근거",
            "자료",
            "지문",
            "표",
            "그래프",
            "비교",
            "해석",
            "evidence",
            "data",
            "graph",
        ),
        ProblemStyle.exam_application: (
            "적용",
            "사례",
            "조건",
            "상황",
            "비교",
            "판단",
            "application",
            "case",
            "condition",
        ),
        ProblemStyle.misconception_drill: (
            "오개념",
            "헷갈린",
            "혼동",
            "착각",
            "misconception",
            "confusion",
        ),
        ProblemStyle.concept_check: (
            "정의",
            "의미",
            "핵심",
            "개념",
            "definition",
            "concept",
        ),
    }
    HIGH_RIGOR_SEARCH_QUERY_CUES = (
        "조건",
        "변화",
        "비교",
        "추론",
        "판단",
        "한계",
        "반례",
        "적용",
        "분석",
        "transfer",
        "analyze",
        "compare",
    )
    EXAM_PREP_SEARCH_QUERY_CUES = ("시험", "출제", "예상", "변별", "exam", "assessment")
    UNIVERSITY_SEARCH_QUERY_CUES = ("대학", "심화", "전공", "university", "advanced")
    COMPACT_SEARCH_QUERY_STYLE_CUES = {
        ProblemStyle.calculation_practice: ("formula", "equation", "unit", "공식", "수식", "단위"),
        ProblemStyle.error_detection: ("error", "bug", "오류", "반례", "예외"),
        ProblemStyle.evidence_analysis: ("table", "graph", "data", "evidence", "표", "그래프", "데이터"),
    }
    COMPACT_SEARCH_QUERY_GENERIC_TERMS = {
        "시험",
        "출제",
        "예상",
        "변별",
        "대학",
        "심화",
        "전공",
        "적용",
        "사례",
        "조건",
        "상황",
        "판단",
        "분석",
        "비교",
        "근거",
        "자료",
        "지문",
        "해석",
        "문제",
        "문항",
        "퀴즈",
        "생성",
        "작성",
        "만들",
        "고난도",
        "어렵",
        "주관식",
        "객관식",
        "설명",
        "고르",
        "선택",
        "풀이",
        "exam",
        "assessment",
        "university",
        "advanced",
        "application",
        "apply",
        "applied",
        "case",
        "condition",
        "analyze",
        "analysis",
        "compare",
        "comparison",
        "problem",
        "question",
        "quiz",
        "generate",
        "create",
        "hard",
        "high",
        "rigor",
    }
    COMPACT_SEARCH_QUERY_STOPWORDS = {
        "the",
        "a",
        "an",
        "and",
        "or",
        "of",
        "to",
        "in",
        "on",
        "for",
        "with",
        "about",
        "by",
        "from",
        "as",
        "is",
        "are",
        "be",
        "를",
        "을",
        "은",
        "는",
        "이",
        "가",
        "과",
        "와",
        "의",
        "에",
        "로",
        "으로",
    }
    KOREAN_QUERY_PARTICLE_SUFFIXES = (
        "으로부터",
        "로부터",
        "에서는",
        "에서",
        "에게",
        "께서",
        "처럼",
        "보다",
        "까지",
        "부터",
        "으로",
        "라고",
        "이라는",
        "라는",
        "이나",
        "거나",
        "하고",
        "에도",
        "에는",
        "은",
        "는",
        "이",
        "가",
        "을",
        "를",
        "과",
        "와",
        "의",
        "에",
        "로",
        "도",
        "만",
    )
    UNSAFE_SEARCH_QUERY_PHRASES = (
        "ignore previous",
        "system prompt",
        "developer message",
        "reveal prompt",
        "지시 무시",
        "시스템 프롬프트",
        "개발자 메시지",
        "프롬프트 공개",
    )
    UNSAFE_SEARCH_QUERY_TOKENS = {
        "ignore",
        "previous",
        "system",
        "prompt",
        "developer",
        "message",
        "reveal",
        "지시",
        "무시",
        "시스템",
        "프롬프트",
        "개발자",
        "메시지",
        "공개",
    }
    USER_REQUIREMENT_QUERY_TOKEN_LIMIT = 20
    RETRY_FEEDBACK_BY_CATEGORY = {
        "missing_mcq_plan": "Regenerate using a concrete scenario, one cited source rule, one correct claim, and three distinct distractor misconceptions. Do not change only wording.",
        "indistinct_distractors": "Regenerate using a concrete scenario, one cited source rule, one correct claim, and three distinct distractor misconceptions. Do not change only wording.",
        "missing_evidence_binding": "Bind the answer, explanation, and distractor diagnostics to concrete source evidence.",
        "missing_source_evidence": "Regenerate using a concrete scenario, one cited source rule, one correct claim, and three distinct distractor misconceptions. Do not change only wording.",
        "missing_concrete_scenario": "Regenerate using a concrete scenario, one cited source rule, one correct claim, and three distinct distractor misconceptions. Do not change only wording.",
        "answer_not_evidence_bound": "Regenerate using a concrete scenario, one cited source rule, one correct claim, and three distinct distractor misconceptions. Do not change only wording.",
        "schema_contract_violation": "Regenerate using a concrete scenario, one cited source rule, one correct claim, and three distinct distractor misconceptions. Do not change only wording.",
        "missing_concrete_context": "Add a concrete condition, case, input, table, code, changed scenario, or flawed claim to the stem.",
        "low_cognitive_demand": "Increase reasoning demand: require applying, comparing, tracing, diagnosing, or justifying, not recalling.",
        "missing_reasoning_steps": "Make the item require at least two reasoning steps; for multi-step high-rigor, require at least three.",
        "weak_distractor_diagnostics": "Make wrong choices diagnose distinct misconceptions or reasoning failures with why_plausible and repair_strategy.",
        "source_grounding_issue": "Use only facts grounded in the retrieved source chunks and cite valid source_chunk_ids.",
        "unsupported_number": "Do not introduce unsupported numbers unless they are directly grounded or clearly derived from source relations.",
        "duplicate_reasoning_template": "Do not create another variant with the same reasoning template or changed numbers only.",
        "shallow_definition_recall": "Avoid definition-only stems; transform the concept into a case, boundary, error, or condition-change decision.",
        "missing_rubric": "For short-answer items, include a rubric with criteria, points, and expected evidence.",
        "weak_evidence_link": "Connect the answer and explanation to specific evidence from the source chunks.",
        "evidence_analysis_structure": "Make the MCQ ask for source-evidence selection or source-grounded claim evaluation; the explanation must connect the answer to specific source evidence.",
        "testwise_option_cue": "Remove test-wise cues: avoid absolute words such as 항상, 절대, 무조건, always, never in multiple distractors.",
        "item_model_mismatch": "Align the generated task with the selected item model; do not label a case-application question as evidence_selection unless it asks for evidence/claim alignment.",
        "request_mismatch": "Match the requested document_id, type, difficulty, bloom_level, and concepts.",
        "other": "Revise the item to satisfy the quality policy while preserving the requested format.",
    }
    RETRY_CATEGORY_PRIORITY = (
        "missing_mcq_plan",
        "indistinct_distractors",
        "missing_evidence_binding",
        "missing_source_evidence",
        "missing_concrete_scenario",
        "answer_not_evidence_bound",
        "schema_contract_violation",
        "missing_concrete_context",
        "low_cognitive_demand",
        "missing_reasoning_steps",
        "testwise_option_cue",
        "weak_distractor_diagnostics",
        "source_grounding_issue",
        "unsupported_number",
        "duplicate_reasoning_template",
        "shallow_definition_recall",
        "missing_rubric",
        "weak_evidence_link",
        "evidence_analysis_structure",
        "item_model_mismatch",
        "request_mismatch",
        "other",
    )
    RETRY_CATEGORY_CUES = {
        "missing_mcq_plan": (
            "missing_mcq_plan",
            "no mcq plan",
            "must include mcq_plan",
            "candidate must include mcq_plan",
        ),
        "indistinct_distractors": (
            "indistinct_distractors",
            "indistinct distractors",
            "repeated distractor",
            "repeated mistake_type",
            "repeated repair_strategy",
            "different distractor",
        ),
        "missing_evidence_binding": (
            "missing_evidence_binding",
            "missing evidence binding",
            "evidence binding",
            "answer/explanation tied to evidence",
        ),
        "missing_source_evidence": (
            "missing_source_evidence",
            "missing source evidence",
            "required_source_chunk_ids",
            "no required source",
        ),
        "missing_concrete_scenario": (
            "missing_concrete_scenario",
            "missing concrete scenario",
            "concrete_scenario",
            "no concrete scenario",
        ),
        "answer_not_evidence_bound": (
            "answer_not_evidence_bound",
            "answer not evidence bound",
            "correct_answer_evidence_link",
            "correct answer claim",
        ),
        "schema_contract_violation": (
            "schema_contract_violation",
            "schema contract",
            "mcq plan contract",
            "invalid mcq_plan",
        ),
        "missing_concrete_context": (
            "concrete condition",
            "concrete context",
            "case, source evidence, input",
            "case, input",
            "input, data, code",
            "changed scenario",
            "flawed claim",
            "must include a concrete",
            "구체 조건",
            "구체적인 조건",
            "사례",
            "입력",
            "상황",
        ),
        "low_cognitive_demand": (
            "low_cognitive_demand",
            "cognitive_demand_score",
            "cognitive demand",
            "low cognitive",
            "beyond recall",
            "weak_application_fit",
            "낮은 사고",
        ),
        "missing_reasoning_steps": (
            "reasoning steps",
            "multi-step",
            "at least two reasoning steps",
            "at least three reasoning steps",
            "three reasoning steps",
            "사고 단계",
            "다단계",
        ),
        "weak_distractor_diagnostics": (
            "distractor",
            "distractors",
            "choice_diagnostics",
            "distinct misconception",
            "why_plausible",
            "repair_strategy",
            "오답",
            "진단",
        ),
        "source_grounding_issue": (
            "source_chunk",
            "source_chunk_ids",
            "unsupported_source",
            "insufficient_source",
            "weak_source_overlap",
            "source grounding",
            "different document",
            "retrieved chunks",
            "valid source",
            "근거 chunk",
        ),
        "unsupported_number": (
            "unsupported number",
            "unsupported_numbers",
            "synthetic number",
            "source-supported numbers",
            "자료에 없는 수치",
            "지원되지 않는 수치",
        ),
        "duplicate_reasoning_template": (
            "duplicate generated problem",
            "too similar to a previously generated problem",
            "reasoning template",
            "formula-substitution",
            "number substitution",
            "same question skeleton",
            "repeated",
            "중복",
        ),
        "shallow_definition_recall": (
            "definition_only_risk",
            "definition-only",
            "too close to recall",
            "procedure listing",
            "broad correctness",
            "recall",
            "definition recall",
            "정의",
            "첫 단계",
            "순서 나열",
        ),
        "missing_rubric": (
            "rubric is required",
            "rubric is missing",
            "missing rubric",
            "weak_rubric_evidence",
            "rubric should",
            "rubric with",
            "루브릭",
            "채점 기준",
        ),
        "weak_evidence_link": (
            "weak evidence",
            "claim link",
            "specific evidence",
            "weak_concept_integration",
            "근거 연결",
            "결론 근거",
        ),
        "evidence_analysis_structure": (
            "evidence_selection item must ask",
            "evidence_analysis mcq must ask",
            "evidence_analysis mcq explanation",
            "source-evidence selection",
            "source-grounded claim evaluation",
            "select or cite source evidence",
            "source evidence selection",
        ),
        "testwise_option_cue": (
            "absolute_wording",
            "absolute wording",
            "test-wise guessing",
            "항상",
            "절대",
            "무조건",
            "always",
            "never",
        ),
        "item_model_mismatch": (
            "item model mismatch",
            "selected item model",
            "label a case-application question",
            "item_model_id mismatch",
            "align the generated task",
        ),
        "request_mismatch": (
            "does not match request",
            "must overlap request concepts",
            "requested document_id",
            "requested type",
            "requested difficulty",
            "requested bloom_level",
            "request mismatch",
        ),
    }
    PREMIUM_ESCALATION_REJECTION_CATEGORIES = {
        "missing_evidence_binding",
        "missing_source_evidence",
        "weak_evidence_link",
        "source_grounding_issue",
        "schema_contract_violation",
        "low_cognitive_demand",
    }

    def __init__(
        self,
        *,
        db: Session,
        search_service: SearchService,
        problem_agent: ProblemAgent,
        quality_checker: ProblemQualityChecker,
        learning_task_router: LearningTaskStrategyRouter | None = None,
        material_readiness_analyzer: MaterialReadinessAnalyzer | None = None,
        blueprint_planner: AssessmentBlueprintPlanner | None = None,
        high_rigor_planner: AdaptiveHighRigorPlanner | None = None,
        source_grounding_planner: SourceGroundingPolicyPlanner | None = None,
        content_atom_extractor: ContentAtomExtractor | None = None,
        problem_kernel_planner: ProblemKernelPlanner | None = None,
        professor_grade_item_designer: ProfessorGradeItemDesigner | None = None,
        answer_verifier: ProblemAnswerVerifier | None = None,
        artifact_publisher: GeneratedArtifactPublisher | None = None,
        rejected_candidate_artifact_writer: RejectedCandidateArtifactWriter | None = None,
        live_eval_case_id: str | None = None,
        live_eval_repeat_index: int = 0,
        settings: Settings | None = None,
    ):
        self.settings = settings or get_settings()
        self.db = db
        self.search_service = search_service
        self.problem_agent = problem_agent
        self.quality_checker = quality_checker
        self.learning_task_router = learning_task_router or LearningTaskStrategyRouter()
        self.material_readiness_analyzer = material_readiness_analyzer or MaterialReadinessAnalyzer()
        self.blueprint_planner = blueprint_planner or AssessmentBlueprintPlanner()
        self.high_rigor_planner = high_rigor_planner or AdaptiveHighRigorPlanner()
        self.source_grounding_planner = source_grounding_planner or SourceGroundingPolicyPlanner()
        self.content_atom_extractor = content_atom_extractor or ContentAtomExtractor()
        self.problem_kernel_planner = problem_kernel_planner or ProblemKernelPlanner()
        self.evidence_obligation_evaluator = EvidenceObligationEvaluator()
        self.professor_grade_item_designer = professor_grade_item_designer or ProfessorGradeItemDesigner()
        self.answer_verifier = answer_verifier or ProblemAnswerVerifier(settings=self.settings)
        self.artifact_publisher = artifact_publisher or GeneratedArtifactPublisher()
        self.rejected_candidate_artifact_writer = rejected_candidate_artifact_writer
        self.live_eval_case_id = live_eval_case_id
        self.live_eval_repeat_index = live_eval_repeat_index
        self.problem_repo = ProblemRepository(db)
        self.item_analytics_repo = ProblemItemAnalyticsRepository(db)
        self.template_analytics_repo = ProblemTemplateAnalyticsRepository(db)
        self.hint_repo = ProblemHintRepository(db)
        self.regeneration_candidate_repo = ProblemRegenerationCandidateRepository(db)
        self.usage_ledger_repo = UsageLedgerRepository(db, self.settings)

    def generate_problems(self, *, user_id: str, request: GenerateProblemRequest) -> list[Problem]:
        return self.generate_problem_batch(user_id=user_id, request=request).problems

    def generate_problem_batch(self, *, user_id: str, request: GenerateProblemRequest) -> ProblemGenerationBatchResult:
        total_started = time.perf_counter()
        request_preparation_started = time.perf_counter()
        self._validate_generation_request_controls(request)
        request = self._normalize_request_intent(request)
        self._enforce_generation_limits(user_id=user_id, request=request)
        preliminary_high_rigor_profile = self.high_rigor_planner.plan(request=request)
        query = self._build_search_query(request)
        request_preparation_ms = self._elapsed_ms(request_preparation_started)

        search_started = time.perf_counter()
        chunks = self.search_service.search_chunks(
            document_id=request.document_id,
            concepts=request.concepts,
            difficulty=request.difficulty.value,
            query=query,
            top_k=self._search_top_k(request, preliminary_high_rigor_profile),
            include_images=self._visual_context_requested(request),
        )
        search_ms = self._elapsed_ms(search_started)

        retrieved_chunk_count = len(chunks)
        planning_started = time.perf_counter()
        self._validate_retrieved_chunks_for_request(request=request, chunks=chunks)
        raw_content_atoms: list[ContentAtom] = []
        raw_content_atom_type_counts: dict[str, int] = {}
        content_atoms: list[ContentAtom] = []
        problem_kernel_plan: ProblemKernelPlan | None = None
        content_atom_type_counts: dict[str, int] = {}
        kernel_planning_failure_reason: str | None = None
        kernel_fallback_warning: str | None = None
        if self.settings.problem_agent_use_domain_general_kernels:
            raw_content_atoms = self.content_atom_extractor.extract(
                chunks=chunks,
                concepts=request.concepts,
                problem_style=request.problem_style,
            )
            raw_content_atom_type_counts = dict(Counter(atom.atom_type.value for atom in raw_content_atoms))
            problem_kernel_plan = self.problem_kernel_planner.plan(
                request=request,
                content_atoms=raw_content_atoms,
            )
            kernel_planning_failure_reason = problem_kernel_plan.failure_reason
            if (
                problem_kernel_plan.failure_reason
                and (self._is_high_rigor_generation_request(request) or preliminary_high_rigor_profile.enabled)
                and self.settings.problem_agent_allow_standard_fallback_on_kernel_failure
            ):
                kernel_fallback_warning = (
                    "kernel planning failed for high-rigor request; standard concept_check fallback applied"
                )
                request = request.model_copy(
                    update={
                        "difficulty": Difficulty.medium,
                        "bloom_level": BloomLevel.understand,
                        "goal": GenerationGoal.concept_review,
                        "target_rigor": TargetRigor.standard,
                        "depth": ProblemDepth.standard,
                        "quality_mode": QualityMode.standard,
                        "problem_style": ProblemStyle.concept_check,
                    }
                )
                problem_kernel_plan = self.problem_kernel_planner.plan(
                    request=request,
                    content_atoms=raw_content_atoms,
                )
                kernel_planning_failure_reason = None

        selected_kernel_atom_ids = self._selected_kernel_atom_ids(
            content_atoms=raw_content_atoms,
            problem_kernel_plan=problem_kernel_plan,
        )
        selected_kernel_atom_chunk_ids = self._selected_kernel_atom_chunk_ids(
            content_atoms=raw_content_atoms,
            problem_kernel_plan=problem_kernel_plan,
        )
        generation_chunks = self._select_generation_context_chunks(
            request=request,
            chunks=chunks,
            search_query=query,
            content_atoms=raw_content_atoms,
            problem_kernel_plan=problem_kernel_plan,
        )
        pre_rescue_generation_chunk_ids = {chunk.chunk_id for chunk in generation_chunks}
        generation_chunks = self._rescue_kernel_atom_chunks(
            request=request,
            chunks=chunks,
            generation_chunks=generation_chunks,
            search_query=query,
            selected_kernel_atom_chunk_ids=selected_kernel_atom_chunk_ids,
        )
        generation_context_chunk_count = len(generation_chunks)
        generation_context_chunk_ids = [chunk.chunk_id for chunk in generation_chunks]
        generation_context_chunk_id_set = set(generation_context_chunk_ids)
        rescued_kernel_atom_chunk_count = len(
            (generation_context_chunk_id_set - pre_rescue_generation_chunk_ids)
            & set(selected_kernel_atom_chunk_ids)
        )
        generation_context_selected_atom_recall = (
            len(set(selected_kernel_atom_chunk_ids) & generation_context_chunk_id_set)
            / len(set(selected_kernel_atom_chunk_ids))
            if selected_kernel_atom_chunk_ids
            else None
        )
        dropped_retrieved_chunk_count = max(0, retrieved_chunk_count - generation_context_chunk_count)
        generation_context_reduction_ratio = (
            1 - (generation_context_chunk_count / retrieved_chunk_count)
            if retrieved_chunk_count > 0
            else None
        )
        if raw_content_atoms:
            content_atoms = [
                atom for atom in raw_content_atoms if atom.source_chunk_id in generation_context_chunk_id_set
            ]
        content_atom_type_counts = dict(Counter(atom.atom_type.value for atom in content_atoms))

        learning_task_strategy = self.learning_task_router.route(request=request, chunks=generation_chunks)
        material_readiness = self.material_readiness_analyzer.analyze(
            request=request,
            chunks=generation_chunks,
            strategy_profile=learning_task_strategy,
        )
        blueprint = self.blueprint_planner.plan(
            request=request,
            strategy_profile=learning_task_strategy,
            material_readiness=material_readiness,
        )
        high_rigor_profile = self.high_rigor_planner.plan(
            request=request,
            chunks=generation_chunks,
            strategy_profile=learning_task_strategy,
            material_readiness=material_readiness,
        )
        source_grounding_profile = self.source_grounding_planner.plan(
            request=request,
            chunks=generation_chunks,
            strategy_profile=learning_task_strategy,
            material_readiness=material_readiness,
        )
        planning_ms = self._elapsed_ms(planning_started)
        if (
            problem_kernel_plan is not None
            and problem_kernel_plan.failure_reason
            and (self._is_high_rigor_generation_request(request) or high_rigor_profile.enabled)
        ):
            trace = self._kernel_failure_trace(
                request=request,
                query=query,
                chunks=chunks,
                generation_chunks=generation_chunks,
                raw_content_atoms=raw_content_atoms,
                raw_content_atom_type_counts=raw_content_atom_type_counts,
                problem_kernel_plan=problem_kernel_plan,
                selected_kernel_atom_ids=selected_kernel_atom_ids,
                selected_kernel_atom_chunk_ids=selected_kernel_atom_chunk_ids,
                generation_context_selected_atom_recall=generation_context_selected_atom_recall,
            )
            raise KernelPlanningFailure(
                f"{problem_kernel_plan.failure_reason}: high-rigor generation requires source chunks with "
                "rules, formulas, procedures, comparisons, conditions, data, or evidence claims. "
                "자료에서 고난도 문항에 필요한 규칙/공식/절차/근거 구조가 충분히 확인되지 않았습니다.",
                trace=trace,
            )

        existing_lookup_started = time.perf_counter()
        existing_problem_fingerprints = self._existing_problem_fingerprints(user_id=user_id, request=request)
        existing_problem_lookup_ms = self._elapsed_ms(existing_lookup_started)
        seen_problem_signatures = {
            str(fingerprint.get("signature") or "")
            for fingerprint in existing_problem_fingerprints
            if fingerprint.get("signature")
        }
        planning_continue_started = time.perf_counter()
        generation_strategy = self._generation_strategy(request, high_rigor_profile)
        batch_candidate_count = self._batch_candidate_generation_count(
            request,
            high_rigor_profile,
            existing_problem_count=len(existing_problem_fingerprints),
        )
        candidate_count = 1 if generation_strategy == "single_then_repair" else batch_candidate_count
        planning_ms += self._elapsed_ms(planning_continue_started)
        cost_profile = self._cost_profile()
        problem_llm = getattr(self.problem_agent, "llm", None)
        safety_identifier = safety_identifier_for_user(user_id)
        valid_candidates: list[tuple[float, dict]] = []
        invalid_errors: list[str] = []
        warning_messages = list(blueprint.warnings)
        if kernel_fallback_warning:
            warning_messages.append(kernel_fallback_warning)
        if (
            (self._is_high_rigor_generation_request(request) or high_rigor_profile.enabled)
            and generation_context_chunk_count < 2
        ):
            warning_messages.append("low generation context coverage")
        rejected_count = 0
        generated_count = 0
        attempt_metrics: list[GenerationAttemptMetrics] = []
        candidate_generation_total_ms = 0.0
        quality_filter_total_ms = 0.0
        actual_retry_count = 0
        repair_call_count = 0
        initial_candidate_valid: bool | None = None
        repair_successful: bool | None = None
        latest_invalid_candidate: dict | None = None

        def generate_candidates(
            *,
            attempt_index: int,
            attempt_candidate_count: int,
            quality_feedback: list[str] | None = None,
            premium_escalation: bool = False,
            repair_invalid_candidate: dict | None = None,
            repair_errors: list[str] | None = None,
        ) -> tuple[list[dict], str | None, float, dict[str, object]]:
            self._reset_llm_usage(problem_llm)
            llm_generation_started = time.perf_counter()
            try:
                if repair_invalid_candidate is not None and hasattr(self.problem_agent, "repair_candidate"):
                    batch = self.problem_agent.repair_candidate(
                        request,
                        repair_invalid_candidate,
                        repair_errors or quality_feedback or [],
                        generation_chunks,
                        safety_identifier=safety_identifier,
                        learning_task_strategy=learning_task_strategy,
                        material_readiness=material_readiness,
                        blueprint=blueprint,
                        high_rigor_profile=high_rigor_profile,
                        source_grounding_profile=source_grounding_profile,
                        content_atoms=content_atoms,
                        problem_kernel_plan=problem_kernel_plan,
                        cost_profile=cost_profile,
                        premium_escalation=premium_escalation,
                    )
                else:
                    batch = self.problem_agent.generate(
                        request,
                        generation_chunks,
                        safety_identifier=safety_identifier,
                        learning_task_strategy=learning_task_strategy,
                        material_readiness=material_readiness,
                        blueprint=blueprint,
                        high_rigor_profile=high_rigor_profile,
                        source_grounding_profile=source_grounding_profile,
                        content_atoms=content_atoms,
                        problem_kernel_plan=problem_kernel_plan,
                        candidate_count=attempt_candidate_count,
                        quality_feedback=quality_feedback,
                        cost_profile=cost_profile,
                        premium_escalation=premium_escalation,
                    )
            except Exception as exc:
                usage_snapshot = self._generation_llm_usage_snapshot(
                    problem_llm,
                    prompt_char_count=getattr(self.problem_agent, "last_prompt_char_count", None),
                    evidence_pack_atom_count=getattr(self.problem_agent, "last_evidence_pack_atom_count", None),
                    raw_context_char_count=getattr(self.problem_agent, "last_raw_context_char_count", None),
                    compressed_prompt_enabled=getattr(self.problem_agent, "last_compressed_prompt_enabled", None),
                )
                generation_mode = getattr(self.problem_agent, "last_generation_mode", None)
                self._write_eval_usage_ledger(
                    attempt_index=attempt_index,
                    usage_snapshot=usage_snapshot,
                    generation_mode=generation_mode,
                    failure_status="generation_failed",
                )
                rejection_categories = (
                    self._rejection_category_counts([str(exc)])
                    if usage_snapshot.get("model")
                    else {}
                )
                self._write_rejected_payload_artifacts(
                    payload=getattr(self.problem_agent, "last_invalid_payload", None),
                    attempt_index=attempt_index,
                    quality_errors=[str(exc)],
                    rejection_categories=rejection_categories,
                    usage_snapshot=usage_snapshot,
                    problem_style=request.problem_style.value,
                    kernel_type=problem_kernel_plan.kernel_type.value if problem_kernel_plan else None,
                    selected_atom_ids=selected_kernel_atom_ids,
                    selected_atom_chunk_ids=selected_kernel_atom_chunk_ids,
                )
                self._attach_generation_exception_trace(
                    exc=exc,
                    attempt_index=attempt_index,
                    usage_snapshot=usage_snapshot,
                    generation_mode=generation_mode,
                    generation_context_chunk_ids=generation_context_chunk_ids,
                    raw_content_atom_count=len(raw_content_atoms),
                    raw_content_atom_type_counts=raw_content_atom_type_counts,
                    selected_kernel_atom_ids=selected_kernel_atom_ids,
                    selected_kernel_atom_chunk_ids=selected_kernel_atom_chunk_ids,
                    rescued_kernel_atom_chunk_count=rescued_kernel_atom_chunk_count,
                    generation_context_selected_atom_recall=generation_context_selected_atom_recall,
                    generation_context_atom_type_counts=content_atom_type_counts,
                    problem_kernel_type=problem_kernel_plan.kernel_type.value if problem_kernel_plan else None,
                    kernel_planning_failure_reason=kernel_planning_failure_reason,
                    rejection_category_counts=rejection_categories,
                )
                raise
            llm_generation_ms = self._elapsed_ms(llm_generation_started)
            usage_snapshot = self._generation_llm_usage_snapshot(
                problem_llm,
                prompt_char_count=getattr(self.problem_agent, "last_prompt_char_count", None),
                evidence_pack_atom_count=getattr(self.problem_agent, "last_evidence_pack_atom_count", None),
                raw_context_char_count=getattr(self.problem_agent, "last_raw_context_char_count", None),
                compressed_prompt_enabled=getattr(self.problem_agent, "last_compressed_prompt_enabled", None),
            )
            self.usage_ledger_repo.create_from_llm_client(
                user_id=user_id,
                feature="problem_generation",
                client=problem_llm,
                premium_reason=self._problem_generation_premium_reason(request),
            )
            return batch, getattr(self.problem_agent, "last_generation_mode", None), llm_generation_ms, usage_snapshot

        def collect_valid_candidates(
            generated_batch: list[dict],
            generation_mode: str | None,
            *,
            attempt_index: int,
            usage_snapshot: dict[str, object],
        ) -> None:
            nonlocal rejected_count, latest_invalid_candidate
            fallback_high_rigor = self._is_high_rigor_fallback_generation(
                request=request,
                generation_mode=generation_mode,
            )
            if fallback_high_rigor:
                warning_messages.append("deterministic fallback high-rigor generation requires review")
            for candidate_index, problem_data in enumerate(generated_batch):
                problem_data = self._with_request_document_id(problem_data, request)
                problem_data.setdefault("problem_style", request.problem_style.value)
                problem_data = self._with_choice_diagnostics(problem_data)
                request_match_errors = self._validate_problem_matches_request(problem_data, request)
                if request_match_errors:
                    latest_invalid_candidate = latest_invalid_candidate or problem_data
                    invalid_errors.extend(request_match_errors)
                    self._write_rejected_candidate_artifact(
                        problem_data=problem_data,
                        attempt_index=attempt_index,
                        candidate_index=candidate_index,
                        quality_errors=request_match_errors,
                        usage_snapshot=usage_snapshot,
                    )
                    rejected_count += 1
                    continue
                quick_validation_errors = self._quick_validate_high_rigor_mcq_candidate(
                    problem_data=problem_data,
                    request=request,
                    high_rigor_profile=high_rigor_profile,
                )
                if quick_validation_errors:
                    latest_invalid_candidate = latest_invalid_candidate or problem_data
                    invalid_errors.extend(quick_validation_errors)
                    self._write_rejected_candidate_artifact(
                        problem_data=problem_data,
                        attempt_index=attempt_index,
                        candidate_index=candidate_index,
                        quality_errors=quick_validation_errors,
                        usage_snapshot=usage_snapshot,
                    )
                    rejected_count += 1
                    continue
                design_result = self.professor_grade_item_designer.enrich(
                    problem_data=problem_data,
                    request=request,
                    chunks=generation_chunks,
                )
                problem_data = design_result.problem_data
                problem_data = self._with_problem_kernel_metadata(
                    problem_data=problem_data,
                    content_atoms=content_atoms,
                    problem_kernel_plan=problem_kernel_plan,
                )
                is_valid, errors, quality_report = self.quality_checker.validate_with_quality_report(
                    problem_data,
                    retrieved_chunks=generation_chunks,
                    request=request,
                    blueprint=blueprint,
                    material_readiness=material_readiness,
                    learning_task_strategy=learning_task_strategy,
                    high_rigor_profile=high_rigor_profile,
                    source_grounding_profile=source_grounding_profile,
                    content_atoms=content_atoms,
                    problem_kernel_plan=problem_kernel_plan,
                )
                if not is_valid:
                    latest_invalid_candidate = latest_invalid_candidate or problem_data
                    invalid_errors.extend(errors)
                    self._write_rejected_candidate_artifact(
                        problem_data=problem_data,
                        attempt_index=attempt_index,
                        candidate_index=candidate_index,
                        quality_errors=errors,
                        usage_snapshot=usage_snapshot,
                    )
                    rejected_count += 1
                    continue
                if design_result.rejection_errors:
                    latest_invalid_candidate = latest_invalid_candidate or problem_data
                    invalid_errors.extend(design_result.rejection_errors)
                    self._write_rejected_candidate_artifact(
                        problem_data=problem_data,
                        attempt_index=attempt_index,
                        candidate_index=candidate_index,
                        quality_errors=design_result.rejection_errors,
                        usage_snapshot=usage_snapshot,
                    )
                    rejected_count += 1
                    continue
                if quality_report.flags:
                    warning_messages.append(
                        "quality flags: " + ", ".join(flag.value for flag in quality_report.flags)
                    )
                evidence_obligation_report = self.evidence_obligation_evaluator.evaluate(
                    problem_data=problem_data,
                    content_atoms=content_atoms,
                    problem_kernel_plan=problem_kernel_plan,
                    cited_chunks=generation_chunks,
                )
                problem_data = self._with_problem_kernel_metadata(
                    problem_data=problem_data,
                    content_atoms=content_atoms,
                    problem_kernel_plan=problem_kernel_plan,
                    evidence_obligation_report=evidence_obligation_report,
                )
                answer_verification_needs_review = False
                if self.settings.problem_agent_answer_verification_enabled:
                    verification_report = self.answer_verifier.verify(
                        problem=problem_data,
                        request=request,
                        chunks=generation_chunks,
                        content_atoms=content_atoms,
                        problem_kernel_plan=problem_kernel_plan,
                    )
                    if verification_report.recommended_action == "reject":
                        latest_invalid_candidate = latest_invalid_candidate or problem_data
                        verification_errors = [
                            "answer verification rejected problem: " + issue
                            for issue in verification_report.issues
                        ] or ["answer verification rejected problem"]
                        invalid_errors.extend(verification_errors)
                        self._write_rejected_candidate_artifact(
                            problem_data=problem_data,
                            attempt_index=attempt_index,
                            candidate_index=candidate_index,
                            quality_errors=verification_errors,
                            usage_snapshot=usage_snapshot,
                        )
                        rejected_count += 1
                        continue
                    if verification_report.recommended_action == "needs_review":
                        answer_verification_needs_review = True
                        warning_messages.append(
                            "answer verification needs_review: "
                            + "; ".join(verification_report.issues[:3])
                        )
                problem_signature = self._problem_signature(problem_data)
                if problem_signature in seen_problem_signatures:
                    latest_invalid_candidate = latest_invalid_candidate or problem_data
                    duplicate_errors = ["duplicate generated problem from current or previous generations"]
                    invalid_errors.extend(duplicate_errors)
                    self._write_rejected_candidate_artifact(
                        problem_data=problem_data,
                        attempt_index=attempt_index,
                        candidate_index=candidate_index,
                        quality_errors=duplicate_errors,
                        usage_snapshot=usage_snapshot,
                    )
                    rejected_count += 1
                    continue
                if self._is_reused_problem(problem_data=problem_data, seen_fingerprints=existing_problem_fingerprints):
                    latest_invalid_candidate = latest_invalid_candidate or problem_data
                    reuse_errors = ["problem is too similar to a previously generated problem"]
                    invalid_errors.extend(reuse_errors)
                    self._write_rejected_candidate_artifact(
                        problem_data=problem_data,
                        attempt_index=attempt_index,
                        candidate_index=candidate_index,
                        quality_errors=reuse_errors,
                        usage_snapshot=usage_snapshot,
                    )
                    rejected_count += 1
                    continue
                seen_problem_signatures.add(problem_signature)
                problem_with_snapshot = self._with_source_evidence_snapshot(
                    problem_data=problem_data,
                    chunks=generation_chunks,
                )
                valid_candidates.append(
                    (
                        quality_report.score,
                        {
                            **problem_with_snapshot,
                            "quality_status": self._quality_status_for_generation(
                                request=request,
                                quality_status=quality_report.status.value,
                                generation_mode=generation_mode,
                                answer_verification_needs_review=answer_verification_needs_review,
                            ),
                        },
                    )
                )
                if len(valid_candidates) == request.count and not self._should_rerank_candidates(request):
                    break

        def run_generation_attempt(
            *,
            attempt_index: int,
            attempt_candidate_count: int,
            quality_feedback: list[str] | None = None,
            retry_feedback_categories: list[str] | None = None,
            premium_escalation: bool = False,
            repair_invalid_candidate: dict | None = None,
            repair_errors: list[str] | None = None,
        ) -> dict[str, object]:
            nonlocal generated_count, candidate_generation_total_ms, quality_filter_total_ms
            generated_batch, generation_mode, llm_generation_ms, usage_snapshot = generate_candidates(
                attempt_index=attempt_index,
                attempt_candidate_count=attempt_candidate_count,
                quality_feedback=quality_feedback,
                premium_escalation=premium_escalation,
                repair_invalid_candidate=repair_invalid_candidate,
                repair_errors=repair_errors,
            )
            candidate_generation_total_ms += llm_generation_ms
            generated_count += len(generated_batch)

            valid_before = len(valid_candidates)
            rejected_before = rejected_count
            invalid_error_count_before = len(invalid_errors)
            filter_started = time.perf_counter()
            collect_valid_candidates(
                generated_batch,
                generation_mode,
                attempt_index=attempt_index,
                usage_snapshot=usage_snapshot,
            )
            quality_filter_ms = self._elapsed_ms(filter_started)
            quality_filter_total_ms += quality_filter_ms
            new_invalid_errors = invalid_errors[invalid_error_count_before:]
            new_rejection_categories = [
                self._categorize_generation_error(error)
                for error in new_invalid_errors
            ]
            new_rejection_category_counts = dict(Counter(new_rejection_categories))

            attempt_metrics.append(
                GenerationAttemptMetrics(
                    attempt_index=attempt_index,
                    generation_mode=generation_mode,
                    model=usage_snapshot.get("model"),
                    input_tokens=usage_snapshot.get("input_tokens"),
                    output_tokens=usage_snapshot.get("output_tokens"),
                    total_tokens=usage_snapshot.get("total_tokens"),
                    estimated_cost_krw=usage_snapshot.get("estimated_cost_krw"),
                    prompt_char_count=usage_snapshot.get("prompt_char_count"),
                    evidence_pack_atom_count=usage_snapshot.get("evidence_pack_atom_count"),
                    raw_context_char_count=usage_snapshot.get("raw_context_char_count"),
                    compressed_prompt_enabled=usage_snapshot.get("compressed_prompt_enabled"),
                    context_chunk_count=generation_context_chunk_count,
                    candidate_count_requested=attempt_candidate_count,
                    valid_candidates_produced=len(valid_candidates) - valid_before,
                    rejected_candidates_produced=rejected_count - rejected_before,
                    requested_candidate_count=attempt_candidate_count,
                    generated_candidate_count=len(generated_batch),
                    valid_candidate_count_after_attempt=len(valid_candidates),
                    rejected_count_after_attempt=rejected_count,
                    llm_generation_ms=llm_generation_ms,
                    quality_filter_ms=quality_filter_ms,
                    retry_feedback_count=len(quality_feedback or []),
                    retry_feedback_categories=list(retry_feedback_categories or []),
                    new_rejection_category_counts=new_rejection_category_counts,
                )
            )
            return {
                "generated_batch": generated_batch,
                "new_valid_count": len(valid_candidates) - valid_before,
                "new_rejection_categories": new_rejection_categories,
                "dominant_rejection_category": self._dominant_rejection_category(new_rejection_categories),
            }

        initial_attempt = run_generation_attempt(attempt_index=0, attempt_candidate_count=candidate_count)
        initial_candidate_valid = bool(initial_attempt["new_valid_count"])

        retry_count = self._quality_retry_count(request=request, high_rigor_profile=high_rigor_profile)
        previous_zero_valid_retry_category: str | None = None
        for retry_index in range(retry_count):
            if len(valid_candidates) >= request.count:
                break
            retry_feedback_categories = self._top_rejection_categories_from_errors(invalid_errors)
            retry_feedback = self._summarize_retry_feedback(invalid_errors)
            if not retry_feedback:
                break
            actual_retry_count += 1
            premium_escalation = self._should_escalate_to_premium_generation(
                cost_profile=cost_profile,
                invalid_errors=invalid_errors,
                valid_candidate_count=len(valid_candidates),
                user_id=user_id,
            )
            repair_invalid_candidate = latest_invalid_candidate if generation_strategy == "single_then_repair" else None
            if generation_strategy == "single_then_repair":
                if repair_invalid_candidate is None:
                    break
                repair_call_count += 1
            attempt_result = run_generation_attempt(
                attempt_index=retry_index + 1,
                attempt_candidate_count=1 if generation_strategy == "single_then_repair" else candidate_count,
                quality_feedback=retry_feedback,
                retry_feedback_categories=retry_feedback_categories,
                premium_escalation=premium_escalation,
                repair_invalid_candidate=repair_invalid_candidate,
                repair_errors=list(dict.fromkeys(invalid_errors))[:8],
            )
            if generation_strategy == "single_then_repair" and attempt_result["new_valid_count"] > 0:
                repair_successful = True
            elif generation_strategy == "single_then_repair":
                repair_successful = False
            if (
                attempt_result["new_valid_count"] == 0
                and attempt_result["dominant_rejection_category"]
                and attempt_result["dominant_rejection_category"] == previous_zero_valid_retry_category
            ):
                warning_messages.append(
                    "stopped retries early: repeated rejection category "
                    f"{attempt_result['dominant_rejection_category']}"
                )
                break
            previous_zero_valid_retry_category = (
                str(attempt_result["dominant_rejection_category"])
                if attempt_result["new_valid_count"] == 0 and attempt_result["dominant_rejection_category"]
                else None
            )

        valid_problem_data = [
            problem_data
            for _, problem_data in sorted(valid_candidates, key=lambda candidate: candidate[0], reverse=True)[
                : request.count
            ]
        ]
        discarded_count = max(0, len(valid_candidates) - len(valid_problem_data))

        if len(valid_problem_data) < request.count:
            detail = "; ".join(dict.fromkeys(invalid_errors)) or "LLM returned fewer problems than requested"
            rejection_category_counts = self._rejection_category_counts(invalid_errors)
            top_rejection_categories = self._top_rejection_categories_from_counts(rejection_category_counts)
            category_counts_json = json.dumps(rejection_category_counts, ensure_ascii=False, sort_keys=True)
            top_categories_json = json.dumps(top_rejection_categories, ensure_ascii=False)
            usage_summary = self._generation_usage_summary(
                attempts=attempt_metrics,
                generated_count=generated_count,
                rejected_count=rejected_count,
            )
            tokens_saved_estimate = self._tokens_saved_estimate_vs_batch(
                attempts=attempt_metrics,
                batch_candidate_count=batch_candidate_count,
                actual_generated_count=generated_count,
                generation_strategy=generation_strategy,
            )
            raise ProblemGenerationFailure(
                f"Only {len(valid_problem_data)} valid problems were generated out of {request.count}: "
                f"{detail}; rejection_category_counts={category_counts_json}; "
                f"top_rejection_categories={top_categories_json}",
                trace={
                    "generation_context_chunk_ids": generation_context_chunk_ids,
                    "raw_content_atom_count": len(raw_content_atoms),
                    "raw_content_atom_type_counts": raw_content_atom_type_counts,
                    "selected_kernel_atom_ids": selected_kernel_atom_ids,
                    "selected_kernel_atom_chunk_ids": selected_kernel_atom_chunk_ids,
                    "rescued_kernel_atom_chunk_count": rescued_kernel_atom_chunk_count,
                    "generation_context_selected_atom_recall": generation_context_selected_atom_recall,
                    "generation_context_atom_type_counts": content_atom_type_counts,
                    "problem_kernel_type": problem_kernel_plan.kernel_type.value if problem_kernel_plan else None,
                    "kernel_planning_failure_reason": kernel_planning_failure_reason,
                    "rejection_category_counts": rejection_category_counts,
                    "top_rejection_categories": top_rejection_categories,
                    "generation_strategy": generation_strategy,
                    "repair_call_count": repair_call_count,
                    "initial_candidate_valid": initial_candidate_valid,
                    "repair_successful": repair_successful if repair_call_count else None,
                    "tokens_saved_estimate_vs_batch": tokens_saved_estimate,
                    "generation_attempts": [attempt.model_dump(mode="json") for attempt in attempt_metrics],
                    **usage_summary,
                },
            )

        try:
            db_write_started = time.perf_counter()
            saved = self.problem_repo.create_many(user_id=user_id, problems_data=valid_problem_data)
            db_write_ms = self._elapsed_ms(db_write_started)

            db_commit_started = time.perf_counter()
            self.db.commit()
            db_commit_ms = self._elapsed_ms(db_commit_started)

            db_refresh_started = time.perf_counter()
            self._refresh_saved_problems_if_needed(saved)
            db_refresh_ms = self._elapsed_ms(db_refresh_started)

            artifact_publish_success_count = 0
            artifact_publish_failure_count = 0
            artifact_publish_started = time.perf_counter()
            try:
                publish_result = self._publish_saved_problems(saved)
                artifact_publish_success_count = publish_result["succeeded"]
                artifact_publish_failure_count = publish_result["failed"]
                if publish_result["errors"]:
                    warning_messages.append(
                        "artifact publish failures: " + "; ".join(publish_result["errors"][:3])
                    )
            except Exception:
                artifact_publish_ms = self._elapsed_ms(artifact_publish_started)
                raise
            artifact_publish_ms = self._elapsed_ms(artifact_publish_started)

            reject_rate = rejected_count / generated_count if generated_count > 0 else None
            pass_rate = len(saved) / generated_count if generated_count > 0 else None
            rejection_category_counts = self._rejection_category_counts(invalid_errors)
            top_rejection_categories = self._top_rejection_categories_from_counts(rejection_category_counts)
            usage_summary = self._generation_usage_summary(
                attempts=attempt_metrics,
                generated_count=generated_count,
                rejected_count=rejected_count,
            )
            tokens_saved_estimate = self._tokens_saved_estimate_vs_batch(
                attempts=attempt_metrics,
                batch_candidate_count=batch_candidate_count,
                actual_generated_count=generated_count,
                generation_strategy=generation_strategy,
            )
            if reject_rate is not None and reject_rate > 0.5:
                warning_messages.append(f"high reject rate: {reject_rate:.3f}")
            if actual_retry_count > 0:
                warning_messages.append(f"retry attempts used: {actual_retry_count}")
            performance = GenerationPerformanceSummary(
                total_ms=self._elapsed_ms(total_started),
                request_preparation_ms=request_preparation_ms,
                search_ms=search_ms,
                planning_ms=planning_ms,
                existing_problem_lookup_ms=existing_problem_lookup_ms,
                retrieved_chunk_count=retrieved_chunk_count,
                generation_context_chunk_count=generation_context_chunk_count,
                generation_context_chunk_ids=generation_context_chunk_ids,
                generation_context_reduction_ratio=generation_context_reduction_ratio,
                dropped_retrieved_chunk_count=dropped_retrieved_chunk_count,
                raw_content_atom_count=len(raw_content_atoms),
                raw_content_atom_type_counts=raw_content_atom_type_counts,
                selected_kernel_atom_ids=selected_kernel_atom_ids,
                selected_kernel_atom_chunk_ids=selected_kernel_atom_chunk_ids,
                rescued_kernel_atom_chunk_count=rescued_kernel_atom_chunk_count,
                generation_context_selected_atom_recall=generation_context_selected_atom_recall,
                content_atom_count=len(content_atoms),
                content_atom_type_counts=content_atom_type_counts,
                generation_context_atom_type_counts=content_atom_type_counts,
                problem_kernel_type=problem_kernel_plan.kernel_type.value if problem_kernel_plan else None,
                kernel_planning_failure_reason=kernel_planning_failure_reason,
                generation_strategy=generation_strategy,
                repair_call_count=repair_call_count,
                initial_candidate_valid=initial_candidate_valid,
                repair_successful=repair_successful if repair_call_count else None,
                tokens_saved_estimate_vs_batch=tokens_saved_estimate,
                candidate_generation_total_ms=candidate_generation_total_ms,
                quality_filter_total_ms=quality_filter_total_ms,
                db_write_ms=db_write_ms,
                db_commit_ms=db_commit_ms,
                db_refresh_ms=db_refresh_ms,
                artifact_publish_ms=artifact_publish_ms,
                artifact_publish_success_count=artifact_publish_success_count,
                artifact_publish_failure_count=artifact_publish_failure_count,
                actual_retry_count=actual_retry_count,
                reject_rate=reject_rate,
                pass_rate=pass_rate,
                total_llm_input_tokens=usage_summary["total_llm_input_tokens"],
                total_llm_output_tokens=usage_summary["total_llm_output_tokens"],
                total_llm_tokens=usage_summary["total_llm_tokens"],
                total_estimated_cost_krw=usage_summary["total_estimated_cost_krw"],
                actual_generation_models=usage_summary["actual_generation_models"],
                llm_call_count=usage_summary["llm_call_count"],
                rejected_candidate_count=rejected_count,
                approximate_wasted_candidate_ratio=usage_summary["approximate_wasted_candidate_ratio"],
                rejection_category_counts=rejection_category_counts,
                top_rejection_categories=top_rejection_categories,
                attempts=attempt_metrics,
            )
            return ProblemGenerationBatchResult(
                problems=saved,
                learning_task_strategy=learning_task_strategy,
                material_readiness=material_readiness,
                blueprint=blueprint,
                high_rigor_profile=high_rigor_profile,
                source_grounding_profile=source_grounding_profile,
                quality_summary=GenerationQualitySummary(
                    generated=generated_count,
                    passed=len(saved),
                    rejected=rejected_count,
                    discarded=discarded_count,
                    warnings=list(dict.fromkeys(warning_messages)),
                    performance=performance,
                ),
            )
        except Exception:
            self.db.rollback()
            raise

    def get_problem(self, problem_id: str) -> Problem | None:
        return self.problem_repo.get(problem_id)

    def get_problem_analytics(self, problem_id: str):
        return self.item_analytics_repo.get(problem_id)

    def create_problem_hint(
        self,
        *,
        user_id: str,
        problem_id: str,
        request: ProblemHintRequest,
    ) -> ProblemHintResponse:
        problem = self.problem_repo.get(problem_id)
        if problem is None or problem.user_id != user_id:
            raise LookupError("Problem not found")
        if request.mode == HintMode.exam:
            raise PermissionError("Hints are blocked in exam mode")

        has_submission = self._has_feedback(problem_id=problem_id, user_id=user_id)
        if request.level == HintLevel.full_solution and not has_submission:
            raise PermissionError("Full solution is available only after submission")

        hint = self._hint_text(problem=problem, level=request.level, has_submission=has_submission)
        answer_revealed = request.level == HintLevel.full_solution
        if not answer_revealed:
            self._assert_hint_does_not_reveal_answer(problem=problem, hint=hint)

        self.hint_repo.create(
            problem_id=problem.id,
            user_id=user_id,
            level=int(request.level),
            mode=request.mode.value,
            hint_text=hint,
            answer_revealed=answer_revealed,
        )
        self.db.commit()
        hint_count = self.hint_repo.count_for_problem_user(problem_id=problem.id, user_id=user_id)
        return ProblemHintResponse(
            problem_id=problem.id,
            level=request.level,
            mode=request.mode,
            hint=hint,
            next_level=self._next_hint_level(request.level, has_submission=has_submission),
            hint_count=hint_count,
            answer_revealed=answer_revealed,
            source_refs=problem.source_refs,
        )

    def list_problem_analytics(
        self,
        *,
        user_id: str,
        document_id: str | None = None,
        needs_review: bool | None = None,
        limit: int = 50,
    ):
        return self.item_analytics_repo.list_for_user(
            user_id=user_id,
            document_id=document_id,
            needs_review=needs_review,
            limit=limit,
        )

    def list_problem_template_analytics(
        self,
        *,
        user_id: str,
        document_id: str | None = None,
        needs_review: bool | None = None,
        limit: int = 50,
    ):
        return self.template_analytics_repo.list_for_user(
            user_id=user_id,
            document_id=document_id,
            needs_review=needs_review,
            limit=limit,
        )

    def _has_feedback(self, *, problem_id: str, user_id: str) -> bool:
        return (
            self.db.query(Feedback)
            .filter(Feedback.problem_id == problem_id, Feedback.user_id == user_id)
            .first()
            is not None
        )

    def _hint_text(self, *, problem: Problem, level: HintLevel, has_submission: bool) -> str:
        concept = self._first_concept(problem)
        if level == HintLevel.restate_question:
            return f"문제에서 묻는 건 {concept}을 어떤 조건에 적용할지 확인하는 거예요. 질문의 조건을 먼저 표시해보세요."
        if level == HintLevel.recall_concept:
            return f"{concept}의 핵심 관계를 먼저 떠올려보세요. 자료에서 어떤 값이나 조건이 서로 연결되는지 보는 게 좋아요."
        if level == HintLevel.first_step_question:
            return "첫 단계만 생각해볼게요. 문제에서 이미 주어진 조건과, 아직 구해야 하는 값을 각각 나눠 적어보세요."
        if level == HintLevel.partial_example:
            return "비슷한 상황에서는 조건을 먼저 정리한 뒤, 자료의 핵심 관계에 하나씩 대입해요. 지금 문제도 같은 순서로 접근해보세요."
        if level == HintLevel.solution_structure:
            return "풀이 구조는 조건 정리 → 자료의 관계 선택 → 값이나 판단 적용 → 결론 확인 순서로 잡으면 좋아요."
        if level == HintLevel.error_check:
            return "마지막으로 단위, 방향, 원인과 결과의 순서가 바뀌지 않았는지 확인해보세요."
        if level == HintLevel.full_solution and has_submission:
            return f"전체 풀이는 이렇게 볼 수 있어요. {problem.explanation}"
        raise PermissionError("Full solution is available only after submission")

    def _first_concept(self, problem: Problem) -> str:
        for concept in problem.concepts or []:
            if str(concept).strip():
                return str(concept).strip()
        return "이 개념"

    def _next_hint_level(self, level: HintLevel, *, has_submission: bool) -> HintLevel | None:
        next_value = int(level) + 1
        if next_value > int(HintLevel.full_solution):
            return None
        if next_value == int(HintLevel.full_solution) and not has_submission:
            return None
        return HintLevel(next_value)

    def _assert_hint_does_not_reveal_answer(self, *, problem: Problem, hint: str) -> None:
        answer_text = str((problem.answer or {}).get("text") or "").strip()
        if len(answer_text) >= 8 and answer_text in hint:
            raise ValueError("Hint would reveal the answer")
        answer_choice = str((problem.answer or {}).get("choice_id") or "").strip()
        if answer_choice and f"정답은 {answer_choice}" in hint:
            raise ValueError("Hint would reveal the answer")

    def list_problem_regeneration_candidates(
        self,
        *,
        user_id: str,
        document_id: str | None = None,
        status: str | None = "open",
        limit: int = 50,
    ):
        return self.regeneration_candidate_repo.list_for_user(
            user_id=user_id,
            document_id=document_id,
            status=status,
            limit=limit,
        )

    def regenerate_problem_from_candidate(self, *, user_id: str, candidate_id: str) -> tuple[Problem, object]:
        candidate = self.regeneration_candidate_repo.get_for_user(candidate_id=candidate_id, user_id=user_id)
        if candidate is None:
            raise LookupError("Problem regeneration candidate not found")
        if candidate.status != "open":
            raise ValueError("Problem regeneration candidate is not open")

        source_problem = self.problem_repo.get(candidate.problem_id)
        if source_problem is None or source_problem.user_id != user_id:
            raise LookupError("Source problem not found")

        request = self._regeneration_request_from_problem(problem=source_problem, candidate=candidate)
        result = self.generate_problem_batch(user_id=user_id, request=request)
        generated_problem = result.problems[0]
        if (
            self._problem_fingerprint_from_model(generated_problem)["signature"]
            == self._problem_fingerprint_from_model(source_problem)["signature"]
        ):
            raise ValueError("Regenerated problem is identical to the source problem")

        notes = self._regeneration_resolution_notes(
            source_problem=source_problem,
            generated_problem=generated_problem,
            candidate=candidate,
        )
        self.regeneration_candidate_repo.mark_resolved(
            candidate=candidate,
            generated_problem_id=generated_problem.id,
            notes=notes,
        )
        self.db.commit()
        self.db.refresh(candidate)
        self.db.refresh(generated_problem)
        return generated_problem, candidate

    def _existing_problem_fingerprints(self, *, user_id: str, request: GenerateProblemRequest) -> list[dict]:
        existing_problems = self.problem_repo.list_recent_for_user_document(
            user_id=user_id,
            document_id=request.document_id,
        )
        return [self._problem_fingerprint_from_model(problem) for problem in existing_problems]

    def _regeneration_request_from_problem(
        self,
        *,
        problem: Problem,
        candidate,
    ) -> GenerateProblemRequest:
        return GenerateProblemRequest(
            document_id=problem.document_id,
            concepts=problem.concepts,
            type=problem.type,
            count=1,
            difficulty=self._regeneration_difficulty(problem=problem, candidate=candidate),
            bloom_level=self._regeneration_bloom_level(problem=problem, candidate=candidate),
            goal=self._regeneration_goal(candidate),
            course_level=CourseLevel.general,
            target_rigor=self._regeneration_target_rigor(candidate),
            quality_mode=self._regeneration_quality_mode(candidate),
            depth=self._regeneration_depth(problem=problem, candidate=candidate),
            user_requirements=self._regeneration_requirements(problem=problem, candidate=candidate),
        )

    def _regeneration_difficulty(self, *, problem: Problem, candidate) -> Difficulty:
        reasons = set(candidate.trigger_reasons or [])
        if "very_high_correct_rate" in reasons:
            return Difficulty.hard
        return Difficulty(problem.difficulty)

    def _regeneration_bloom_level(self, *, problem: Problem, candidate) -> BloomLevel:
        reasons = set(candidate.trigger_reasons or [])
        current = BloomLevel(problem.bloom_level)
        if "very_high_correct_rate" in reasons and current in {BloomLevel.remember, BloomLevel.understand}:
            return BloomLevel.apply
        return current

    def _regeneration_target_rigor(self, candidate) -> TargetRigor:
        if candidate.suggested_action == "increase_cognitive_demand":
            return TargetRigor.high
        return TargetRigor.standard

    def _regeneration_goal(self, candidate) -> GenerationGoal:
        if candidate.suggested_action == "increase_cognitive_demand":
            return GenerationGoal.exam_prep
        return GenerationGoal.practice

    def _regeneration_quality_mode(self, candidate) -> QualityMode:
        if candidate.suggested_action == "increase_cognitive_demand":
            return QualityMode.strict
        return QualityMode.standard

    def _regeneration_depth(self, *, problem: Problem, candidate) -> ProblemDepth:
        if problem.type == ProblemType.short_answer.value and candidate.suggested_action == "increase_cognitive_demand":
            return ProblemDepth.deep
        return ProblemDepth.standard

    def _regeneration_requirements(self, *, problem: Problem, candidate) -> str:
        reason_text = ", ".join(candidate.trigger_reasons or ["quality_review"])
        action = candidate.suggested_action or "review_item"
        base = (
            f"이전 문항의 재검토 사유는 {reason_text}입니다. "
            f"개선 방향은 {action}입니다. "
            "기존 문항과 같은 질문, 같은 보기 조합, 같은 풀이 구조를 반복하지 마세요. "
        )
        if action == "rewrite_distractors":
            return base + "오답 보기는 그럴듯하지만 서로 다른 오개념을 진단하도록 다시 설계하세요."
        if action == "revise_rubric_or_prompt":
            return base + "답안 요구사항과 rubric 기준이 더 분명하게 드러나도록 문제를 다시 설계하세요."
        if action == "increase_cognitive_demand":
            return base + "단순 개념 확인보다 조건 변화나 응용 판단이 필요한 문제로 높이세요."
        if action == "check_ambiguity_or_source_grounding":
            return base + "정답 근거가 자료에서 명확히 확인되고 모호하지 않게 다시 설계하세요."
        return base + "자료 근거는 유지하되 학습자가 새롭게 판단해야 하는 문제로 바꾸세요."

    def _regeneration_resolution_notes(self, *, source_problem: Problem, generated_problem: Problem, candidate) -> list[str]:
        notes = [
            f"source_problem_id={source_problem.id}",
            f"generated_problem_id={generated_problem.id}",
            f"suggested_action={candidate.suggested_action}",
            "기존 문제와 같은 signature가 아니며 저장 전 재사용 방지 검사를 통과했습니다.",
        ]
        if source_problem.difficulty != generated_problem.difficulty:
            notes.append(f"difficulty_changed={source_problem.difficulty}->{generated_problem.difficulty}")
        if source_problem.bloom_level != generated_problem.bloom_level:
            notes.append(f"bloom_level_changed={source_problem.bloom_level}->{generated_problem.bloom_level}")
        return notes

    def _problem_fingerprint_from_model(self, problem: Problem) -> dict:
        return self._problem_fingerprint(
            {
                "type": problem.type,
                "difficulty": problem.difficulty,
                "bloom_level": problem.bloom_level,
                "question": problem.question,
                "choices": problem.choices,
                "answer": problem.answer,
                "explanation": problem.explanation,
                "rubric": problem.rubric,
                "concepts": problem.concepts,
                "item_model_id": problem.item_model_id,
                "difficulty_profile": problem.difficulty_profile,
                "item_design_brief": problem.item_design_brief,
            }
        )

    def _with_choice_diagnostics(self, problem_data: dict) -> dict:
        if problem_data.get("type") == ProblemType.short_answer.value:
            return {**problem_data, "choice_diagnostics": None}
        if problem_data.get("type") != ProblemType.multiple_choice.value:
            return problem_data
        if problem_data.get("choice_diagnostics"):
            return problem_data

        choices = [choice for choice in (problem_data.get("choices") or []) if isinstance(choice, dict)]
        answer = problem_data.get("answer") or {}
        choice_explanations = problem_data.get("choice_explanations") or {}
        concept = self._diagnostic_concept(problem_data)
        answer_id = str(answer.get("choice_id") or "")

        diagnostics = []
        for choice in choices:
            choice_id = str(choice.get("id") or "")
            is_correct = choice_id == answer_id
            explanation = str(choice_explanations.get(choice_id) or "").strip()
            if is_correct:
                diagnostics.append(
                    {
                        "choice_id": choice_id,
                        "is_correct": True,
                        "misconception_id": None,
                        "mistake_type": MistakeType.none.value,
                        "why_plausible": None,
                        "repair_strategy": None,
                        "followup_problem_type": None,
                    }
                )
                continue

            mistake_type = self._choice_mistake_type(f"{choice.get('text')} {explanation}")
            diagnostics.append(
                {
                    "choice_id": choice_id,
                    "is_correct": False,
                    "misconception_id": self._misconception_id(concept=concept, choice_id=choice_id),
                    "mistake_type": mistake_type.value,
                    "why_plausible": self._why_plausible_for_choice(
                        concept=concept,
                        choice_text=str(choice.get("text") or ""),
                        explanation=explanation,
                    ),
                    "repair_strategy": self._repair_strategy_for_choice(
                        concept=concept,
                        mistake_type=mistake_type,
                        explanation=explanation,
                    ),
                    "followup_problem_type": self._followup_problem_type(mistake_type),
                }
            )

        return {**problem_data, "choice_diagnostics": diagnostics}

    def _diagnostic_concept(self, problem_data: dict) -> str:
        concepts = [str(concept).strip() for concept in (problem_data.get("concepts") or []) if str(concept).strip()]
        return concepts[0] if concepts else "이 개념"

    def _choice_mistake_type(self, text: str) -> MistakeType:
        normalized = str(text or "").lower()
        if any(cue in normalized for cue in ("계산", "대입", "값", "분자", "분모", "곱", "나누")):
            return MistakeType.calculation_error
        if any(cue in normalized for cue in ("단위", "kg", "n", "m/s")):
            return MistakeType.unit_error
        if any(cue in normalized for cue in ("용어", "정의", "뜻", "혼동")):
            return MistakeType.term_confusion
        if any(cue in normalized for cue in ("잘못 읽", "먼저", "나중", "순서")):
            return MistakeType.misread_question
        return MistakeType.concept_misunderstanding

    def _misconception_id(self, *, concept: str, choice_id: str) -> str:
        base = re.sub(r"[^0-9A-Za-z가-힣]+", "_", concept).strip("_").lower()
        return f"mis_{base or 'concept'}_{choice_id.lower() or 'choice'}"


    def _why_plausible_for_choice(self, *, concept: str, choice_text: str, explanation: str) -> str:
        giveaway_cues = ("자료에 없는", "관계없는", "오답", "틀린", "정답이 아님")
        if explanation and not any(cue in explanation for cue in giveaway_cues):
            return explanation
        if choice_text:
            return f"'{choice_text}'처럼 보면 {concept}의 조건이나 관계를 다르게 해석한 것이다."
        return f"{concept}의 조건을 다르게 해석하면 고를 수 있는 보기다."

    def _repair_strategy_for_choice(self, *, concept: str, mistake_type: MistakeType, explanation: str) -> str:
        if mistake_type == MistakeType.calculation_error:
            return "공식의 분자와 분모, 대입한 값을 한 줄씩 확인한다."
        if mistake_type == MistakeType.unit_error:
            return "계산 결과 뒤에 단위가 자료의 변수와 맞는지 확인한다."
        if mistake_type == MistakeType.misread_question:
            return "문제 조건의 순서와 비교 대상을 표시하면서 다시 읽는다."
        if explanation:
            return f"{concept}에서 {explanation} 부분을 자료의 관계와 다시 비교한다."
        return f"{concept}의 조건과 결과가 어떤 순서로 연결되는지 표시한다."

    def _followup_problem_type(self, mistake_type: MistakeType) -> str:
        if mistake_type in {MistakeType.calculation_error, MistakeType.unit_error}:
            return "calculation_drill"
        if mistake_type == MistakeType.misread_question:
            return "error_diagnosis"
        return "comparison_drill"

    def _with_source_evidence_snapshot(self, *, problem_data: dict, chunks: list[RetrievedChunk]) -> dict:
        chunk_by_id = {chunk.chunk_id: chunk for chunk in chunks}
        snapshot = []
        for chunk_id in problem_data.get("source_chunk_ids") or []:
            chunk = chunk_by_id.get(chunk_id)
            if chunk is None:
                raise SearchAgentError(f"Generated problem cited an unknown source chunk: {chunk_id}")
            chunk_data = chunk.model_dump(mode="json")
            chunk_data["content"] = self._trim_evidence_content(chunk_data["content"])
            snapshot.append(chunk_data)
        return {**problem_data, "source_evidence_snapshot": snapshot}

    def _with_problem_kernel_metadata(
        self,
        *,
        problem_data: dict,
        content_atoms: list[ContentAtom],
        problem_kernel_plan: ProblemKernelPlan | None,
        evidence_obligation_report: EvidenceObligationReport | None = None,
    ) -> dict:
        if not content_atoms and problem_kernel_plan is None and evidence_obligation_report is None:
            return problem_data
        design_brief = problem_data.get("item_design_brief")
        if not isinstance(design_brief, dict):
            return problem_data
        evidence_links = evidence_obligation_report.evidence_links if evidence_obligation_report else []
        mcq_plan = self._extract_mcq_plan(problem_data)
        enriched_design_brief = {
            **design_brief,
            "content_atoms": [atom.model_dump(mode="json") for atom in content_atoms[:12]],
            "problem_kernel_plan": problem_kernel_plan.model_dump(mode="json") if problem_kernel_plan else None,
            "evidence_links": [link.model_dump(mode="json") for link in evidence_links[:12]],
        }
        if mcq_plan is not None:
            enriched_design_brief["mcq_plan"] = mcq_plan
        if evidence_obligation_report is not None:
            enriched_design_brief["evidence_obligation_report"] = evidence_obligation_report.model_dump(
                mode="json",
                exclude={"evidence_links"},
            )
            enriched_design_brief["evidence_contract"] = {
                "selected_atom_ids": list(problem_kernel_plan.content_atom_ids if problem_kernel_plan else []),
                "evidence_roles": [
                    obligation.role.value
                    for obligation in (problem_kernel_plan.required_evidence_roles if problem_kernel_plan else [])
                ],
                "answer_supported_by": [
                    link.link_id for link in evidence_links if "answer" in link.used_in
                ],
                "explanation_supported_by": [
                    link.link_id for link in evidence_links if "explanation" in link.used_in
                ],
                "distractor_failure_modes": [
                    str(item.get("misconception_id") or item.get("mistake_type") or "")
                    for item in problem_data.get("choice_diagnostics") or []
                    if isinstance(item, dict) and not item.get("is_correct")
                ],
            }
        cleaned_problem_data = {key: value for key, value in problem_data.items() if key != "mcq_plan"}
        return {**cleaned_problem_data, "item_design_brief": enriched_design_brief}

    def _with_request_document_id(self, problem_data: dict, request: GenerateProblemRequest) -> dict:
        return {**problem_data, "document_id": request.document_id}

    def _visual_context_requested(self, request: GenerateProblemRequest) -> bool:
        text = " ".join(
            [
                request.user_requirements or "",
                " ".join(request.concepts or []),
            ]
        ).lower()
        visual_cues = (
            "그림",
            "도표",
            "그래프",
            "차트",
            "시각",
            "이미지",
            "수식",
            "diagram",
            "figure",
            "graph",
            "chart",
            "image",
            "visual",
            "formula",
        )
        return any(cue in text for cue in visual_cues)

    def _trim_evidence_content(self, content: str) -> str:
        if len(content) <= self.EVIDENCE_SNAPSHOT_CONTENT_LIMIT:
            return content
        return content[: self.EVIDENCE_SNAPSHOT_CONTENT_LIMIT].rstrip()

    def _validate_retrieved_chunks_for_request(
        self,
        *,
        request: GenerateProblemRequest,
        chunks: list[RetrievedChunk],
    ) -> None:
        if not chunks:
            raise ValueError("Search Agent returned no chunks")

        chunk_ids = [chunk.chunk_id for chunk in chunks]
        if len(set(chunk_ids)) != len(chunk_ids):
            raise SearchAgentError("Search Agent returned duplicate chunk ids")

        mismatched_document_ids = [chunk.chunk_id for chunk in chunks if chunk.document_id != request.document_id]
        if mismatched_document_ids:
            raise SearchAgentError(
                f"Search Agent returned chunks from a different document: {', '.join(mismatched_document_ids)}"
            )

    def _validate_problem_matches_request(self, problem_data: dict, request: GenerateProblemRequest) -> list[str]:
        expected = {
            "document_id": request.document_id,
            "type": request.type.value,
            "difficulty": request.difficulty.value,
            "bloom_level": request.bloom_level.value,
        }
        errors = [
            f"{field} does not match request"
            for field, expected_value in expected.items()
            if problem_data.get(field) != expected_value
        ]
        generated_concepts = {str(concept).strip() for concept in (problem_data.get("concepts") or []) if str(concept).strip()}
        requested_concepts = set(request.concepts)
        if generated_concepts and not (generated_concepts & requested_concepts):
            errors.append("generated concepts must overlap request concepts")
        return errors

    def _quick_validate_high_rigor_mcq_candidate(
        self,
        *,
        problem_data: dict,
        request: GenerateProblemRequest,
        high_rigor_profile: HighRigorGenerationProfile | None,
    ) -> list[str]:
        if not self._requires_high_rigor_mcq_plan(request=request, high_rigor_profile=high_rigor_profile):
            return []

        errors: list[str] = []
        plan = self._extract_mcq_plan(problem_data)
        if not isinstance(plan, dict) or not plan:
            return ["missing_mcq_plan: high-rigor multiple_choice candidate must include mcq_plan"]

        required_chunk_ids = [
            str(chunk_id).strip()
            for chunk_id in plan.get("required_source_chunk_ids") or []
            if str(chunk_id).strip()
        ]
        cited_chunk_ids = {
            str(chunk_id).strip()
            for chunk_id in (problem_data.get("source_chunk_ids") or [])
            if str(chunk_id).strip()
        }
        if not required_chunk_ids or not (set(required_chunk_ids) & cited_chunk_ids):
            errors.append("missing_source_evidence: mcq_plan.required_source_chunk_ids must cite problem source_chunk_ids")

        scenario = str(plan.get("concrete_scenario") or "").strip()
        if len(scenario) < 12 or self._generic_mcq_plan_text(scenario):
            errors.append("missing_concrete_scenario: mcq_plan.concrete_scenario must describe the concrete case")

        answer_claim = str(plan.get("correct_answer_claim") or "").strip()
        answer_link = str(plan.get("correct_answer_evidence_link") or "").strip()
        if not answer_claim or not answer_link:
            errors.append("answer_not_evidence_bound: mcq_plan must link correct_answer_claim to evidence")
        else:
            answer_text = str((problem_data.get("answer") or {}).get("text") or "")
            explanation = str(problem_data.get("explanation") or "")
            if not self._texts_share_meaningful_token(
                answer_claim,
                " ".join([answer_link, answer_text, explanation]),
            ):
                errors.append("answer_not_evidence_bound: correct answer claim is not tied to the evidence link")

        distractor_plans = [item for item in (plan.get("distractor_plans") or []) if isinstance(item, dict)]
        if len(distractor_plans) != 3:
            errors.append("schema_contract_violation: mcq_plan.distractor_plans must contain exactly 3 wrong-choice plans")
            return list(dict.fromkeys(errors))

        required_fields = (
            "misconception_id",
            "mistake_type",
            "why_plausible",
            "violated_or_ignored_evidence_role",
            "repair_strategy",
        )
        missing_fields = [
            field
            for item in distractor_plans
            for field in required_fields
            if not str(item.get(field) or "").strip()
        ]
        if missing_fields:
            errors.append("schema_contract_violation: mcq_plan distractor plans are missing required fields")

        mistake_types = [self._normalize_mcq_plan_token(item.get("mistake_type")) for item in distractor_plans]
        misconception_ids = [self._normalize_mcq_plan_token(item.get("misconception_id")) for item in distractor_plans]
        evidence_roles = [
            self._normalize_mcq_plan_token(item.get("violated_or_ignored_evidence_role"))
            for item in distractor_plans
        ]
        repairs = [self._normalize_mcq_plan_text(item.get("repair_strategy")) for item in distractor_plans]
        if len(set(mistake_types)) < len(mistake_types):
            errors.append("indistinct_distractors: distractor mistake_type values must be distinct")
        if len(set(zip(misconception_ids, mistake_types, evidence_roles))) < 3:
            errors.append("indistinct_distractors: distractor failure modes must be distinct")
        if len(set(repairs)) < len(repairs) or any(self._generic_repair_strategy(repair) for repair in repairs):
            errors.append("indistinct_distractors: repair_strategy must be specific and non-repeated")

        return list(dict.fromkeys(errors))

    def _requires_high_rigor_mcq_plan(
        self,
        *,
        request: GenerateProblemRequest,
        high_rigor_profile: HighRigorGenerationProfile | None,
    ) -> bool:
        return request.type == ProblemType.multiple_choice and (
            request.target_rigor == TargetRigor.high
            or request.difficulty == Difficulty.hard
            or request.bloom_level in {BloomLevel.analyze, BloomLevel.evaluate, BloomLevel.create}
            or request.depth == ProblemDepth.deep
            or bool(high_rigor_profile and high_rigor_profile.enabled)
        )

    def _extract_mcq_plan(self, problem_data: dict) -> dict | None:
        plan = problem_data.get("mcq_plan")
        if isinstance(plan, dict):
            return plan
        design_brief = problem_data.get("item_design_brief")
        if isinstance(design_brief, dict) and isinstance(design_brief.get("mcq_plan"), dict):
            return design_brief["mcq_plan"]
        return None

    def _normalize_mcq_plan_token(self, value: object) -> str:
        return re.sub(r"[^0-9A-Za-z가-힣_]+", "_", str(value or "").strip().lower()).strip("_")

    def _normalize_mcq_plan_text(self, value: object) -> str:
        normalized = re.sub(r"\s+", " ", str(value or "").strip().lower())
        return re.sub(r"[^0-9a-z가-힣%._/+ -]+", "", normalized).strip()

    def _generic_mcq_plan_text(self, text: str) -> bool:
        normalized = self._normalize_mcq_plan_text(text)
        generic_values = {
            "concrete scenario",
            "source scenario",
            "given condition",
            "case",
            "scenario",
            "상황",
            "사례",
            "조건",
        }
        return normalized in generic_values

    def _generic_repair_strategy(self, text: str) -> bool:
        normalized = self._normalize_mcq_plan_text(text)
        if len(normalized) < 12:
            return True
        generic_cues = (
            "review the source",
            "check the source",
            "read again",
            "study again",
            "다시 확인",
            "다시 읽",
            "복습",
            "자료 확인",
        )
        return any(cue in normalized for cue in generic_cues) and len(normalized) < 35

    def _texts_share_meaningful_token(self, left: str, right: str) -> bool:
        left_tokens = self._meaningful_text_tokens(left)
        if not left_tokens:
            return False
        right_tokens = self._meaningful_text_tokens(right)
        return bool(left_tokens & right_tokens)

    def _meaningful_text_tokens(self, text: str) -> set[str]:
        raw_tokens = re.findall(r"[0-9A-Za-z가-힣_]+", str(text or "").lower())
        stopwords = {
            "the",
            "and",
            "or",
            "with",
            "from",
            "this",
            "that",
            "answer",
            "claim",
            "source",
            "rule",
            "evidence",
            "correct",
            "정답",
            "근거",
            "자료",
            "규칙",
            "설명",
            "주장",
            "문제",
        }
        return {token for token in raw_tokens if len(token) >= 3 and token not in stopwords}

    def _categorize_generation_error(self, error: str) -> str:
        normalized = str(error or "").strip().lower()
        if not normalized:
            return "other"
        for category in self.RETRY_CATEGORY_PRIORITY:
            if category == "other":
                continue
            cues = self.RETRY_CATEGORY_CUES.get(category, ())
            if any(cue.lower() in normalized for cue in cues):
                return category
        return "other"

    def _summarize_retry_feedback(self, invalid_errors: list[str]) -> list[str]:
        categories = self._top_rejection_categories_from_errors(invalid_errors)
        feedback = [
            self.RETRY_FEEDBACK_BY_CATEGORY[category]
            for category in categories
            if category in self.RETRY_FEEDBACK_BY_CATEGORY
        ]
        return list(dict.fromkeys(feedback))[:8]

    def _rejection_category_counts(self, invalid_errors: list[str]) -> dict[str, int]:
        counts: Counter[str] = Counter()
        for error in invalid_errors:
            counts[self._categorize_generation_error(error)] += 1
        return dict(counts)

    def _top_rejection_categories_from_errors(self, invalid_errors: list[str]) -> list[str]:
        return self._top_rejection_categories_from_counts(
            self._rejection_category_counts(invalid_errors),
        )

    def _top_rejection_categories_from_counts(self, category_counts: dict[str, int]) -> list[str]:
        if not category_counts:
            return []
        priority = {category: index for index, category in enumerate(self.RETRY_CATEGORY_PRIORITY)}
        return [
            category
            for category, _ in sorted(
                category_counts.items(),
                key=lambda item: (-item[1], priority.get(item[0], len(priority))),
            )
        ]

    def _dominant_rejection_category(self, categories: list[str]) -> str | None:
        if not categories:
            return None
        return self._top_rejection_categories_from_counts(dict(Counter(categories)))[0]

    def _candidate_generation_count(
        self,
        request: GenerateProblemRequest,
        high_rigor_profile: HighRigorGenerationProfile | None = None,
        existing_problem_count: int = 0,
    ) -> int:
        if self._generation_strategy(request, high_rigor_profile) == "single_then_repair":
            return 1
        return self._batch_candidate_generation_count(
            request,
            high_rigor_profile=high_rigor_profile,
            existing_problem_count=existing_problem_count,
        )

    def _batch_candidate_generation_count(
        self,
        request: GenerateProblemRequest,
        high_rigor_profile: HighRigorGenerationProfile | None = None,
        existing_problem_count: int = 0,
    ) -> int:
        provider = str(self.settings.llm_provider or "").strip().lower()
        high_rigor = self._is_high_rigor_generation_request(request) or bool(
            high_rigor_profile and high_rigor_profile.enabled
        )
        cost_profile = self._cost_profile()
        if high_rigor and cost_profile == "cheap":
            return request.count
        if high_rigor and cost_profile == "balanced":
            if request.type == ProblemType.multiple_choice:
                return min(10, max(request.count, 2))
            return request.count
        if high_rigor and request.type == ProblemType.multiple_choice:
            minimum = self._high_rigor_mcq_candidate_minimum(request)
            if provider == "gemini":
                gemini_multiplier = int(getattr(self.settings, "llm_gemini_high_rigor_candidate_multiplier", 1) or 1)
                base = request.count * gemini_multiplier if gemini_multiplier >= 2 else request.count
                return min(10, max(base, minimum))
            if existing_problem_count:
                base = max(request.count + min(existing_problem_count, 5), request.count * 2)
            else:
                profile_multiplier = (
                    high_rigor_profile.candidate_multiplier
                    if high_rigor_profile and high_rigor_profile.enabled
                    else 1
                )
                base = request.count * profile_multiplier
            return min(10, max(base, minimum))
        if provider == "gemini":
            gemini_multiplier = int(getattr(self.settings, "llm_gemini_high_rigor_candidate_multiplier", 1) or 1)
            if high_rigor and gemini_multiplier >= 2:
                minimum = 3 if request.count == 1 else request.count + 2
                return min(10, max(request.count * gemini_multiplier, minimum))
            return request.count
        if existing_problem_count:
            base = max(request.count + min(existing_problem_count, 5), request.count * 2)
            if high_rigor:
                base = max(base, 3 if request.count == 1 else request.count + 2)
            return min(10, base)
        if high_rigor:
            minimum = 3 if request.count == 1 else request.count + 2
            profile_multiplier = (
                high_rigor_profile.candidate_multiplier
                if high_rigor_profile and high_rigor_profile.enabled
                else 1
            )
            return min(10, max(minimum, request.count * profile_multiplier))
        if not self._should_rerank_candidates(request, high_rigor_profile):
            return request.count
        multiplier = high_rigor_profile.candidate_multiplier if high_rigor_profile and high_rigor_profile.enabled else 3
        return min(10, max(request.count, request.count * multiplier))

    def _generation_strategy(
        self,
        request: GenerateProblemRequest,
        high_rigor_profile: HighRigorGenerationProfile | None = None,
    ) -> str:
        configured = str(getattr(self.settings, "problem_agent_generation_strategy", "") or "").strip().lower()
        cost_profile = self._cost_profile()
        strategy = configured if configured in {"batch_candidates", "single_then_repair"} else None
        if strategy is None:
            strategy = "batch_candidates" if cost_profile == "full" else "single_then_repair"
        high_rigor = self._is_high_rigor_generation_request(request) or bool(
            high_rigor_profile and high_rigor_profile.enabled
        )
        if strategy == "single_then_repair" and high_rigor and request.type == ProblemType.multiple_choice and request.count == 1:
            return "single_then_repair"
        return "batch_candidates"

    def _high_rigor_mcq_candidate_minimum(self, request: GenerateProblemRequest) -> int:
        configured_minimum = int(getattr(self.settings, "problem_agent_high_rigor_mcq_min_candidates", 3) or 3)
        count_minimum = 3 if request.count == 1 else request.count + 2
        return min(10, max(configured_minimum, count_minimum))

    def _quality_retry_count(
        self,
        *,
        request: GenerateProblemRequest,
        high_rigor_profile: HighRigorGenerationProfile | None = None,
    ) -> int:
        high_rigor = self._is_high_rigor_generation_request(request) or bool(
            high_rigor_profile and high_rigor_profile.enabled
        )
        if not high_rigor:
            return 0
        if request.count <= 0:
            return 0
        cost_profile = self._cost_profile()
        if cost_profile == "cheap":
            return 0
        if cost_profile == "balanced":
            return 1
        if request.type == ProblemType.multiple_choice:
            return int(getattr(self.settings, "problem_agent_high_rigor_mcq_retry_count", 2) or 0)
        return 2 if str(self.settings.llm_provider or "").strip().lower() == "gemini" else 1

    def _cost_profile(self) -> str:
        profile = str(getattr(self.settings, "problem_agent_cost_profile", "balanced") or "balanced").strip().lower()
        if profile in {"cheap", "balanced", "full"}:
            return profile
        return "balanced"

    def _should_escalate_to_premium_generation(
        self,
        *,
        cost_profile: str,
        invalid_errors: list[str],
        valid_candidate_count: int,
        user_id: str,
    ) -> bool:
        if cost_profile not in {"cheap", "balanced"}:
            return False
        if not self.settings.problem_agent_allow_premium_escalation:
            return False
        if valid_candidate_count != 0:
            return False
        categories = set(self._top_rejection_categories_from_errors(invalid_errors))
        if not categories.intersection(self.PREMIUM_ESCALATION_REJECTION_CATEGORIES):
            return False
        return self._premium_escalation_budget_allows(user_id=user_id)

    def _premium_escalation_budget_allows(self, *, user_id: str) -> bool:
        if not self.settings.llm_enforce_monthly_budget or self.settings.llm_monthly_user_budget_krw <= 0:
            return True
        month_start = self._current_month_start()
        budget_summary = self.usage_ledger_repo.summary_for_user(user_id=user_id, since=month_start)
        return budget_summary.get("budget_status") not in {"exceeded"}

    def _reset_llm_usage(self, client: object) -> None:
        reset = getattr(client, "reset_last_call", None)
        if callable(reset):
            reset()

    def _generation_llm_usage_snapshot(
        self,
        client: object | None,
        *,
        prompt_char_count: int | None,
        evidence_pack_atom_count: int | None = None,
        raw_context_char_count: int | None = None,
        compressed_prompt_enabled: bool | None = None,
    ) -> dict[str, object]:
        snapshot = self.usage_ledger_repo.usage_snapshot_from_llm_client(client) or {}
        return {
            "model": snapshot.get("model"),
            "input_tokens": snapshot.get("input_tokens"),
            "output_tokens": snapshot.get("output_tokens"),
            "total_tokens": snapshot.get("total_tokens"),
            "estimated_cost_krw": snapshot.get("estimated_cost_krw"),
            "prompt_char_count": prompt_char_count,
            "evidence_pack_atom_count": evidence_pack_atom_count,
            "raw_context_char_count": raw_context_char_count,
            "compressed_prompt_enabled": compressed_prompt_enabled,
        }

    def _write_eval_usage_ledger(
        self,
        *,
        attempt_index: int,
        usage_snapshot: dict[str, object],
        generation_mode: str | None,
        failure_status: str | None,
    ) -> None:
        if self.rejected_candidate_artifact_writer is None:
            return
        self.rejected_candidate_artifact_writer.write_usage(
            case_id=self.live_eval_case_id or "unknown_case",
            repeat_index=self.live_eval_repeat_index,
            attempt_index=attempt_index,
            usage=usage_snapshot,
            generation_mode=generation_mode,
            failure_status=failure_status,
        )

    def _write_rejected_candidate_artifact(
        self,
        *,
        problem_data: dict,
        attempt_index: int,
        candidate_index: int,
        quality_errors: list[str],
        usage_snapshot: dict[str, object],
        evidence_obligation_issues: list[str] | None = None,
    ) -> None:
        if self.rejected_candidate_artifact_writer is None:
            return
        rejection_categories = self._rejection_category_counts(quality_errors)
        design_brief = problem_data.get("item_design_brief")
        selected_atom_ids = []
        selected_atom_chunk_ids = []
        if isinstance(design_brief, dict):
            selected_atom_ids = [
                str(atom_id)
                for atom_id in design_brief.get("selected_atom_ids", [])
                if str(atom_id).strip()
            ]
            selected_atom_chunk_ids = [
                str(chunk_id)
                for chunk_id in design_brief.get("selected_atom_chunk_ids", [])
                if str(chunk_id).strip()
            ]
        self.rejected_candidate_artifact_writer.write_rejected_candidate(
            case_id=self.live_eval_case_id or str(problem_data.get("document_id") or "unknown_case"),
            repeat_index=self.live_eval_repeat_index,
            attempt_index=attempt_index,
            candidate_index=candidate_index,
            candidate=problem_data,
            kernel_type=self._problem_kernel_type_for_artifact(problem_data),
            problem_style=str(problem_data.get("problem_style") or ""),
            selected_atom_ids=selected_atom_ids or [],
            selected_atom_chunk_ids=selected_atom_chunk_ids or [],
            evidence_obligation_issues=evidence_obligation_issues,
            quality_errors=quality_errors,
            rejection_categories=rejection_categories,
            usage=usage_snapshot,
        )

    def _write_rejected_payload_artifacts(
        self,
        *,
        payload: object,
        attempt_index: int,
        quality_errors: list[str],
        rejection_categories: dict[str, int],
        usage_snapshot: dict[str, object],
        problem_style: str,
        kernel_type: str | None,
        selected_atom_ids: list[str],
        selected_atom_chunk_ids: list[str],
    ) -> None:
        if self.rejected_candidate_artifact_writer is None:
            return
        if not payload:
            return
        self.rejected_candidate_artifact_writer.write_rejected_payload_candidates(
            case_id=self.live_eval_case_id or "unknown_case",
            repeat_index=self.live_eval_repeat_index,
            attempt_index=attempt_index,
            payload=payload,
            kernel_type=kernel_type,
            problem_style=problem_style,
            selected_atom_ids=selected_atom_ids,
            selected_atom_chunk_ids=selected_atom_chunk_ids,
            quality_errors=quality_errors,
            rejection_categories=rejection_categories,
            usage=usage_snapshot,
        )

    def _problem_kernel_type_for_artifact(self, problem_data: dict) -> str | None:
        design_brief = problem_data.get("item_design_brief")
        if not isinstance(design_brief, dict):
            return None
        plan = design_brief.get("problem_kernel_plan")
        if isinstance(plan, dict):
            value = plan.get("kernel_type")
            return str(value) if value else None
        return None

    def _attach_generation_exception_trace(
        self,
        *,
        exc: Exception,
        attempt_index: int,
        usage_snapshot: dict[str, object],
        generation_mode: str | None,
        generation_context_chunk_ids: list[str],
        raw_content_atom_count: int,
        raw_content_atom_type_counts: dict[str, int],
        selected_kernel_atom_ids: list[str],
        selected_kernel_atom_chunk_ids: list[str],
        rescued_kernel_atom_chunk_count: int,
        generation_context_selected_atom_recall: float | None,
        generation_context_atom_type_counts: dict[str, int],
        problem_kernel_type: str | None,
        kernel_planning_failure_reason: str | None,
        rejection_category_counts: dict[str, int],
    ) -> None:
        trace = dict(getattr(exc, "trace", {}) or {})
        trace.update(
            {
                "generation_context_chunk_ids": generation_context_chunk_ids,
                "raw_content_atom_count": raw_content_atom_count,
                "raw_content_atom_type_counts": raw_content_atom_type_counts,
                "selected_kernel_atom_ids": selected_kernel_atom_ids,
                "selected_kernel_atom_chunk_ids": selected_kernel_atom_chunk_ids,
                "rescued_kernel_atom_chunk_count": rescued_kernel_atom_chunk_count,
                "generation_context_selected_atom_recall": generation_context_selected_atom_recall,
                "generation_context_atom_type_counts": generation_context_atom_type_counts,
                "problem_kernel_type": problem_kernel_type,
                "kernel_planning_failure_reason": kernel_planning_failure_reason,
                "rejection_category_counts": rejection_category_counts,
                "top_rejection_categories": self._top_rejection_categories_from_counts(rejection_category_counts),
                "actual_generation_models": [usage_snapshot["model"]] if usage_snapshot.get("model") else [],
                "total_llm_input_tokens": int(usage_snapshot.get("input_tokens") or 0),
                "total_llm_output_tokens": int(usage_snapshot.get("output_tokens") or 0),
                "total_llm_tokens": int(usage_snapshot.get("total_tokens") or 0),
                "total_estimated_cost_krw": float(usage_snapshot.get("estimated_cost_krw") or 0.0),
                "llm_call_count": 1 if usage_snapshot.get("model") else 0,
                "generation_attempts": [
                    {
                        "attempt_index": attempt_index,
                        "generation_mode": generation_mode,
                        "model": usage_snapshot.get("model"),
                        "input_tokens": usage_snapshot.get("input_tokens"),
                        "output_tokens": usage_snapshot.get("output_tokens"),
                        "total_tokens": usage_snapshot.get("total_tokens"),
                        "estimated_cost_krw": usage_snapshot.get("estimated_cost_krw"),
                        "prompt_char_count": usage_snapshot.get("prompt_char_count"),
                        "evidence_pack_atom_count": usage_snapshot.get("evidence_pack_atom_count"),
                        "raw_context_char_count": usage_snapshot.get("raw_context_char_count"),
                        "compressed_prompt_enabled": usage_snapshot.get("compressed_prompt_enabled"),
                        "context_chunk_count": len(generation_context_chunk_ids),
                        "candidate_count_requested": 1,
                        "valid_candidates_produced": 0,
                        "rejected_candidates_produced": 0,
                        "requested_candidate_count": 1,
                        "generated_candidate_count": 0,
                        "valid_candidate_count_after_attempt": 0,
                        "rejected_count_after_attempt": 0,
                        "llm_generation_ms": 0.0,
                        "quality_filter_ms": 0.0,
                        "retry_feedback_count": 0,
                        "retry_feedback_categories": [],
                        "new_rejection_category_counts": rejection_category_counts,
                    }
                ],
            }
        )
        setattr(exc, "trace", trace)

    def _generation_usage_summary(
        self,
        *,
        attempts: list[GenerationAttemptMetrics],
        generated_count: int,
        rejected_count: int,
    ) -> dict[str, object]:
        models = [attempt.model for attempt in attempts if attempt.model]
        total_input_tokens = sum(int(attempt.input_tokens or 0) for attempt in attempts)
        total_output_tokens = sum(int(attempt.output_tokens or 0) for attempt in attempts)
        total_tokens = sum(int(attempt.total_tokens or 0) for attempt in attempts)
        total_cost = round(sum(float(attempt.estimated_cost_krw or 0.0) for attempt in attempts), 6)
        return {
            "total_llm_input_tokens": total_input_tokens,
            "total_llm_output_tokens": total_output_tokens,
            "total_llm_tokens": total_tokens,
            "total_estimated_cost_krw": total_cost,
            "actual_generation_models": list(dict.fromkeys(models)),
            "llm_call_count": len(models),
            "rejected_candidate_count": rejected_count,
            "approximate_wasted_candidate_ratio": (
                rejected_count / generated_count if generated_count > 0 else None
            ),
        }

    def _tokens_saved_estimate_vs_batch(
        self,
        *,
        attempts: list[GenerationAttemptMetrics],
        batch_candidate_count: int,
        actual_generated_count: int,
        generation_strategy: str,
    ) -> int | None:
        if generation_strategy != "single_then_repair":
            return None
        actual_output_tokens = sum(int(attempt.output_tokens or 0) for attempt in attempts)
        if actual_output_tokens <= 0 or actual_generated_count <= 0:
            return None
        if batch_candidate_count <= actual_generated_count:
            return 0
        per_candidate_output = actual_output_tokens / actual_generated_count
        estimated_batch_output = per_candidate_output * batch_candidate_count
        return max(0, int(round(estimated_batch_output - actual_output_tokens)))

    def _validate_generation_request_controls(self, request: GenerateProblemRequest) -> None:
        validate_safe_user_requirements(
            request.user_requirements,
            error_message="unsafe problem generation request",
        )

    def _enforce_generation_limits(self, *, user_id: str, request: GenerateProblemRequest) -> None:
        month_start = self._current_month_start()
        monthly_limit = self.settings.problem_generation_monthly_limit
        if monthly_limit > 0:
            used = self.problem_repo.count_generated_for_user_since(user_id=user_id, since=month_start)
            if used + request.count > monthly_limit:
                raise ValueError("problem generation monthly limit exceeded")

        high_rigor_limit = self.settings.problem_generation_high_rigor_monthly_limit
        if high_rigor_limit > 0 and self._is_high_rigor_generation_request(request):
            used_high_rigor = self.problem_repo.count_generated_for_user_since(
                user_id=user_id,
                since=month_start,
                high_rigor_only=True,
            )
            if used_high_rigor + request.count > high_rigor_limit:
                raise ValueError("high-rigor problem generation monthly limit exceeded")

        if self.settings.llm_enforce_monthly_budget and self.settings.llm_monthly_user_budget_krw > 0:
            budget_summary = self.usage_ledger_repo.summary_for_user(user_id=user_id, since=month_start)
            if budget_summary["budget_status"] == "exceeded":
                raise ValueError("monthly LLM budget exceeded")

    def _current_month_start(self) -> datetime:
        now = datetime.now(timezone.utc)
        return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    def _elapsed_ms(self, started: float) -> float:
        return max(0.0, (time.perf_counter() - started) * 1000)

    def _refresh_saved_problems_if_needed(self, saved: list[Problem]) -> None:
        fields_needed_after_commit = {
            "id",
            "user_id",
            "document_id",
            "type",
            "difficulty",
            "bloom_level",
            "question",
            "choices",
            "concepts",
            "source_refs",
            "source_chunk_ids",
            "quality_status",
            "item_model_id",
            "created_at",
        }
        for problem in saved:
            state = sqlalchemy_inspect(problem)
            state_dict = state.dict
            expired = set(state.expired_attributes)
            missing_required = not state_dict.get("id") or not state_dict.get("created_at")
            if missing_required or expired.intersection(fields_needed_after_commit):
                self.db.refresh(problem)

    def _publish_saved_problems(self, saved: list[Problem]) -> dict:
        if hasattr(self.artifact_publisher, "publish_problems"):
            result = self.artifact_publisher.publish_problems(saved)
            return {
                "succeeded": int(getattr(result, "succeeded", 0) or 0),
                "failed": int(getattr(result, "failed", 0) or 0),
                "errors": list(getattr(result, "errors", []) or []),
            }

        artifact_publishing_enabled = self._artifact_publishing_enabled()
        succeeded = 0
        failed = 0
        errors: list[str] = []
        for problem in saved:
            try:
                if self.artifact_publisher.publish_problem(problem):
                    succeeded += 1
                elif artifact_publishing_enabled:
                    failed += 1
            except Exception as exc:
                if self._artifact_publishing_fail_fast_enabled():
                    raise
                if artifact_publishing_enabled:
                    failed += 1
                    errors.append(str(exc))
        return {"succeeded": succeeded, "failed": failed, "errors": errors}

    def _artifact_publishing_enabled(self) -> bool:
        settings = getattr(self.artifact_publisher, "settings", self.settings)
        return bool(
            getattr(settings, "generated_artifact_publish_enabled", False)
            and (
                getattr(settings, "generated_artifact_index_url", None)
                or getattr(settings, "generated_artifact_add_url", None)
            )
        )

    def _artifact_publishing_fail_fast_enabled(self) -> bool:
        settings = getattr(self.artifact_publisher, "settings", self.settings)
        return bool(getattr(settings, "generated_artifact_publish_fail_fast", False))

    def _is_high_rigor_generation_request(self, request: GenerateProblemRequest) -> bool:
        return (
            request.difficulty == Difficulty.hard
            or request.bloom_level in {BloomLevel.analyze, BloomLevel.evaluate, BloomLevel.create}
            or request.target_rigor == TargetRigor.high
            or request.depth == ProblemDepth.deep
            or request.quality_mode == QualityMode.strict
            or request.problem_style in {
                ProblemStyle.exam_application,
                ProblemStyle.calculation_practice,
                ProblemStyle.evidence_analysis,
                ProblemStyle.error_detection,
            }
        )

    def _is_high_rigor_fallback_generation(
        self,
        *,
        request: GenerateProblemRequest,
        generation_mode: str | None,
    ) -> bool:
        return (
            generation_mode == ProblemAgent.GENERATION_MODE_DETERMINISTIC_FALLBACK
            and self._is_high_rigor_generation_request(request)
        )

    def _quality_status_for_generation(
        self,
        *,
        request: GenerateProblemRequest,
        quality_status: str,
        generation_mode: str | None,
        answer_verification_needs_review: bool = False,
    ) -> str:
        if answer_verification_needs_review:
            return QualityStatus.needs_review.value
        if self._is_high_rigor_fallback_generation(request=request, generation_mode=generation_mode):
            return QualityStatus.needs_review.value
        return quality_status

    def _problem_generation_premium_reason(self, request: GenerateProblemRequest) -> str:
        return (
            f"difficulty={request.difficulty.value}, "
            f"bloom_level={request.bloom_level.value}, "
            f"target_rigor={request.target_rigor.value}, "
            f"depth={request.depth.value}"
        )

    def _should_rerank_candidates(
        self,
        request: GenerateProblemRequest,
        high_rigor_profile: HighRigorGenerationProfile | None = None,
    ) -> bool:
        return (
            bool(high_rigor_profile and high_rigor_profile.enabled)
            or request.quality_mode.value == "strict"
            or request.target_rigor.value == "high"
            or request.depth.value == "deep"
            or request.difficulty.value == "hard"
        )

    def _search_top_k(
        self,
        request: GenerateProblemRequest,
        high_rigor_profile: HighRigorGenerationProfile | None = None,
    ) -> int:
        base = max(6, request.count)
        if high_rigor_profile and high_rigor_profile.enabled:
            return max(base, high_rigor_profile.recommended_top_k)
        return base

    def _selected_kernel_atom_chunk_ids(
        self,
        *,
        content_atoms: list[ContentAtom],
        problem_kernel_plan: ProblemKernelPlan | None,
    ) -> list[str]:
        selected_atoms = self._selected_kernel_atoms(
            content_atoms=content_atoms,
            problem_kernel_plan=problem_kernel_plan,
        )
        selected: list[str] = []
        for atom in selected_atoms:
            if atom.source_chunk_id not in selected:
                selected.append(atom.source_chunk_id)
        return selected

    def _selected_kernel_atom_ids(
        self,
        *,
        content_atoms: list[ContentAtom],
        problem_kernel_plan: ProblemKernelPlan | None,
    ) -> list[str]:
        return [
            atom.atom_id
            for atom in self._selected_kernel_atoms(
                content_atoms=content_atoms,
                problem_kernel_plan=problem_kernel_plan,
            )
        ]

    def _selected_kernel_atoms(
        self,
        *,
        content_atoms: list[ContentAtom],
        problem_kernel_plan: ProblemKernelPlan | None,
    ) -> list[ContentAtom]:
        if problem_kernel_plan is None:
            return []
        atom_by_id = {atom.atom_id: atom for atom in content_atoms}
        atoms = [atom_by_id[atom_id] for atom_id in problem_kernel_plan.content_atom_ids if atom_id in atom_by_id]
        return sorted(
            atoms,
            key=lambda atom: self._kernel_atom_priority(atom=atom, problem_kernel_plan=problem_kernel_plan),
            reverse=True,
        )

    def _kernel_atom_priority(self, *, atom: ContentAtom, problem_kernel_plan: ProblemKernelPlan) -> float:
        return (
            self._kernel_atom_type_relevance(atom_type=atom.atom_type, problem_kernel_plan=problem_kernel_plan)
            + atom.confidence
            + min(0.2, len(atom.concepts) * 0.03)
        )

    def _kernel_atom_type_relevance(
        self,
        *,
        atom_type: ContentAtomType,
        problem_kernel_plan: ProblemKernelPlan,
    ) -> float:
        relevance_map: dict[str, dict[ContentAtomType, float]] = {
            "compute_from_given": {
                ContentAtomType.formula: 3.0,
                ContentAtomType.rule: 2.0,
            },
            "diagnose_error": {
                ContentAtomType.rule: 3.0,
                ContentAtomType.procedure: 2.5,
                ContentAtomType.formula: 2.5,
                ContentAtomType.condition_exception: 2.0,
            },
            "evidence_to_claim": {
                ContentAtomType.evidence_claim: 3.0,
                ContentAtomType.data_table: 3.0,
                ContentAtomType.cause_effect: 2.0,
                ContentAtomType.comparison: 1.5,
            },
            "compare_boundary": {
                ContentAtomType.comparison: 3.0,
                ContentAtomType.classification: 2.5,
                ContentAtomType.definition: 1.0,
            },
            "trace_process": {
                ContentAtomType.procedure: 3.0,
                ContentAtomType.code_state: 2.5,
                ContentAtomType.rule: 1.5,
            },
            "condition_mutation": {
                ContentAtomType.condition_exception: 3.0,
                ContentAtomType.rule: 2.5,
                ContentAtomType.cause_effect: 1.5,
            },
            "apply_rule_to_case": {
                ContentAtomType.rule: 3.0,
                ContentAtomType.classification: 2.0,
                ContentAtomType.condition_exception: 1.5,
            },
        }
        return relevance_map.get(problem_kernel_plan.kernel_type.value, {}).get(atom_type, 0.0)

    def _kernel_atom_chunk_score_bonuses(
        self,
        *,
        content_atoms: list[ContentAtom],
        problem_kernel_plan: ProblemKernelPlan | None,
    ) -> dict[str, float]:
        bonuses: dict[str, float] = {}
        for atom in self._selected_kernel_atoms(
            content_atoms=content_atoms,
            problem_kernel_plan=problem_kernel_plan,
        ):
            relevance = self._kernel_atom_type_relevance(atom_type=atom.atom_type, problem_kernel_plan=problem_kernel_plan)
            if relevance <= 0:
                relevance = 0.5
            bonuses[atom.source_chunk_id] = bonuses.get(atom.source_chunk_id, 0.0) + relevance * (0.5 + atom.confidence)
        return bonuses

    def _rescue_kernel_atom_chunks(
        self,
        *,
        request: GenerateProblemRequest,
        chunks: list[RetrievedChunk],
        generation_chunks: list[RetrievedChunk],
        search_query: str,
        selected_kernel_atom_chunk_ids: list[str],
    ) -> list[RetrievedChunk]:
        if not selected_kernel_atom_chunk_ids or not chunks:
            return generation_chunks
        if not getattr(self.settings, "problem_agent_generation_context_packing_enabled", True):
            return generation_chunks

        max_chunks = max(1, int(getattr(self.settings, "problem_agent_generation_context_max_chunks", 8) or 8))
        required_ids = set(selected_kernel_atom_chunk_ids)
        chunk_by_id = {chunk.chunk_id: chunk for chunk in chunks if chunk.document_id == request.document_id}
        selected_by_id = {chunk.chunk_id: chunk for chunk in generation_chunks}
        missing_required_ids = [chunk_id for chunk_id in selected_kernel_atom_chunk_ids if chunk_id not in selected_by_id]
        if not missing_required_ids:
            return generation_chunks

        source_terms = self._generation_context_query_terms(request=request, search_query=search_query)

        def score(chunk: RetrievedChunk) -> float:
            try:
                rank = chunks.index(chunk)
            except ValueError:
                rank = max_chunks
            return self._generation_context_chunk_score(chunk=chunk, source_terms=source_terms, rank=rank)

        for chunk_id in missing_required_ids:
            rescue_chunk = chunk_by_id.get(chunk_id)
            if rescue_chunk is None:
                continue
            if len(selected_by_id) < max_chunks:
                selected_by_id[chunk_id] = rescue_chunk
                continue
            replaceable = [
                chunk for chunk in selected_by_id.values() if chunk.chunk_id not in required_ids
            ]
            if not replaceable:
                continue
            lowest = min(replaceable, key=score)
            selected_by_id.pop(lowest.chunk_id, None)
            selected_by_id[chunk_id] = rescue_chunk

        original_order = {chunk.chunk_id: index for index, chunk in enumerate(chunks)}
        return sorted(selected_by_id.values(), key=lambda chunk: original_order.get(chunk.chunk_id, len(chunks)))

    def _kernel_failure_trace(
        self,
        *,
        request: GenerateProblemRequest,
        query: str,
        chunks: list[RetrievedChunk],
        generation_chunks: list[RetrievedChunk],
        raw_content_atoms: list[ContentAtom],
        raw_content_atom_type_counts: dict[str, int],
        problem_kernel_plan: ProblemKernelPlan,
        selected_kernel_atom_ids: list[str],
        selected_kernel_atom_chunk_ids: list[str],
        generation_context_selected_atom_recall: float | None,
    ) -> dict:
        available_atom_types = sorted(raw_content_atom_type_counts)
        desired_kernel = problem_kernel_plan.kernel_type.value
        missing_atom_types = self._missing_kernel_atom_types(problem_kernel_plan=problem_kernel_plan)
        return {
            "search_query": query,
            "returned_chunk_count": len(chunks),
            "unique_returned_chunk_count": len({chunk.chunk_id for chunk in chunks}),
            "generation_context_chunk_ids": [chunk.chunk_id for chunk in generation_chunks],
            "raw_content_atom_count": len(raw_content_atoms),
            "raw_content_atom_type_counts": raw_content_atom_type_counts,
            "available_atom_types": available_atom_types,
            "problem_kernel_type": desired_kernel,
            "desired_kernel": desired_kernel,
            "missing_atom_types": missing_atom_types,
            "recommended_fallback_problem_style": "concept_check",
            "kernel_planning_failure_reason": problem_kernel_plan.failure_reason,
            "selected_kernel_atom_ids": selected_kernel_atom_ids,
            "selected_kernel_atom_chunk_ids": selected_kernel_atom_chunk_ids,
            "generation_context_selected_atom_recall": generation_context_selected_atom_recall,
            "product_message": (
                "자료에서 고난도 문항에 필요한 규칙/공식/절차/근거 구조가 충분히 확인되지 않았습니다."
            ),
            "request_problem_style": request.problem_style.value,
        }

    def _missing_kernel_atom_types(self, *, problem_kernel_plan: ProblemKernelPlan) -> list[str]:
        kernel_map = {
            "compute_from_given": ["formula", "rule"],
            "diagnose_error": ["rule", "procedure", "formula", "condition_exception"],
            "evidence_to_claim": ["evidence_claim", "data_table", "comparison", "cause_effect"],
            "compare_boundary": ["comparison", "classification"],
            "trace_process": ["procedure", "code_state"],
            "condition_mutation": ["condition_exception", "rule", "cause_effect"],
            "apply_rule_to_case": ["rule", "classification"],
        }
        return kernel_map.get(problem_kernel_plan.kernel_type.value, ["rule", "formula", "procedure", "evidence_claim"])

    def _select_generation_context_chunks(
        self,
        *,
        request: GenerateProblemRequest,
        chunks: list[RetrievedChunk],
        search_query: str,
        content_atoms: list[ContentAtom] | None = None,
        problem_kernel_plan: ProblemKernelPlan | None = None,
    ) -> list[RetrievedChunk]:
        if not chunks:
            return []
        if not getattr(self.settings, "problem_agent_generation_context_packing_enabled", True):
            return list(chunks)

        max_chunks = max(1, int(getattr(self.settings, "problem_agent_generation_context_max_chunks", 8) or 8))
        min_chunks = max(1, int(getattr(self.settings, "problem_agent_generation_context_min_chunks", 3) or 3))
        min_chunks = min(min_chunks, max_chunks)
        visual_context_requested = self._visual_context_requested(request)

        candidates: list[tuple[int, RetrievedChunk]] = []
        seen_exact_content: set[str] = set()
        selected_content_signatures: list[set[str]] = []
        for index, chunk in enumerate(chunks):
            if chunk.document_id != request.document_id:
                continue
            content = self._normalize_context_chunk_content(chunk.content)
            if not content:
                continue
            if content in seen_exact_content:
                continue
            token_signature = self._context_chunk_token_signature(content)
            if self._is_near_duplicate_context_chunk(token_signature, selected_content_signatures):
                continue
            seen_exact_content.add(content)
            selected_content_signatures.append(token_signature)
            candidates.append((index, chunk))

        if not candidates:
            return []

        source_terms = self._generation_context_query_terms(request=request, search_query=search_query)
        atom_chunk_bonuses = self._kernel_atom_chunk_score_bonuses(
            content_atoms=content_atoms or [],
            problem_kernel_plan=problem_kernel_plan,
        )
        scored = [
            (
                self._generation_context_chunk_score(chunk=chunk, source_terms=source_terms, rank=index)
                + atom_chunk_bonuses.get(chunk.chunk_id, 0.0),
                index,
                chunk,
            )
            for index, chunk in candidates
        ]
        selected_by_id: dict[str, tuple[int, RetrievedChunk]] = {}

        def add(index: int, chunk: RetrievedChunk) -> None:
            if len(selected_by_id) >= max_chunks:
                return
            selected_by_id.setdefault(chunk.chunk_id, (index, chunk))

        top_index, top_chunk = candidates[0]
        add(top_index, top_chunk)

        if visual_context_requested:
            for index, chunk in candidates:
                if chunk.metadata.get("image_available"):
                    add(index, chunk)

        selected_pages = {item.page for _, item in selected_by_id.values() if item.page is not None}
        selected_sections = {
            str(item.section_title or "").strip().lower()
            for _, item in selected_by_id.values()
            if str(item.section_title or "").strip()
        }
        ranked = sorted(scored, key=lambda item: (-item[0], item[1]))
        for _, index, chunk in ranked:
            if len(selected_by_id) >= max_chunks:
                break
            page_key = chunk.page
            section_key = str(chunk.section_title or "").strip().lower()
            if (
                len(selected_by_id) < min_chunks
                or (page_key is not None and page_key not in selected_pages)
                or (section_key and section_key not in selected_sections)
            ):
                add(index, chunk)
                if page_key is not None:
                    selected_pages.add(page_key)
                if section_key:
                    selected_sections.add(section_key)

        for _, index, chunk in ranked:
            if len(selected_by_id) >= min_chunks or len(selected_by_id) >= max_chunks:
                break
            add(index, chunk)

        return [chunk for _, chunk in sorted(selected_by_id.values(), key=lambda item: item[0])]

    def _generation_context_query_terms(self, *, request: GenerateProblemRequest, search_query: str) -> set[str]:
        concept_terms = self._concept_query_term_keys(request)
        terms = set(concept_terms)
        terms.update(
            term.lower()
            for term in self._safe_query_terms_from_requirements(
                request.user_requirements,
                compact=True,
                concept_terms=concept_terms,
            )
        )
        terms.update(term.lower() for term in self._source_likely_operation_cues(request))
        for token in re.findall(r"[0-9A-Za-z가-힣_+/#.-]+", search_query):
            normalized = self._normalize_compact_query_token(token)
            if normalized and not self._is_compact_generic_query_term(normalized):
                terms.add(normalized.lower())
        return {term for term in terms if term}

    def _source_likely_operation_cues(self, request: GenerateProblemRequest) -> tuple[str, ...]:
        cues = list(self.COMPACT_SEARCH_QUERY_STYLE_CUES.get(request.problem_style, ()))
        if request.problem_style in {ProblemStyle.calculation_practice, ProblemStyle.exam_application}:
            cues.extend(("formula", "equation", "unit", "공식", "수식", "단위"))
        if request.problem_style in {ProblemStyle.evidence_analysis, ProblemStyle.exam_application}:
            cues.extend(("table", "graph", "data", "표", "그래프", "데이터"))
        if request.problem_style in {ProblemStyle.error_detection, ProblemStyle.exam_application}:
            cues.extend(("error", "bug", "code", "오류", "반례", "코드"))
        return tuple(dict.fromkeys(cues))

    def _generation_context_chunk_score(self, *, chunk: RetrievedChunk, source_terms: set[str], rank: int) -> float:
        text = self._chunk_retrieval_text(chunk)
        score = 0.0
        for term in source_terms:
            if term and term in text:
                score += 2.0 if len(term) > 2 else 1.0
        score += self._chunk_metadata_relevance_score(chunk)
        score += max(0.0, 1.0 - (rank * 0.03))
        if chunk.metadata.get("image_available"):
            score += 0.5
        return score

    def _chunk_retrieval_text(self, chunk: RetrievedChunk) -> str:
        values = [
            chunk.content,
            chunk.section_title or "",
            " ".join(chunk.concepts or []),
            " ".join(chunk.tags or []),
        ]
        return " ".join(values).lower()

    def _chunk_metadata_relevance_score(self, chunk: RetrievedChunk) -> float:
        metadata = chunk.metadata or {}
        for key in ("score", "similarity", "relevance_score"):
            value = metadata.get(key)
            if isinstance(value, int | float):
                return max(0.0, min(1.0, float(value)))
        for key in ("distance", "dist"):
            value = metadata.get(key)
            if isinstance(value, int | float):
                return max(0.0, min(1.0, 1.0 - float(value)))
        return 0.0

    def _normalize_context_chunk_content(self, content: str) -> str:
        return re.sub(r"\s+", " ", str(content or "").strip().lower())

    def _context_chunk_token_signature(self, content: str) -> set[str]:
        return set(re.findall(r"[0-9A-Za-z가-힣_+/#.-]+", content))

    def _is_near_duplicate_context_chunk(self, tokens: set[str], existing: list[set[str]]) -> bool:
        if not tokens:
            return True
        for other in existing:
            union = tokens | other
            if union and len(tokens & other) / len(union) >= 0.92:
                return True
        return False

    def _build_search_query(self, request: GenerateProblemRequest) -> str:
        mode = self._search_query_mode()
        if mode == "expanded":
            return self._build_expanded_search_query(request)

        terms = self._compact_search_query_terms(request)
        if mode == "hybrid":
            terms.extend(self._hybrid_search_query_extra_terms(request, terms))

        query_terms = self._dedupe_query_terms(terms)
        fallback = self._normalize_query_term(" ".join(request.concepts)) or request.document_id
        return " ".join(query_terms) or fallback

    def _search_query_mode(self) -> str:
        settings = getattr(self, "settings", None)
        mode = str(getattr(settings, "problem_agent_search_query_mode", "compact") or "compact").strip().lower()
        return mode if mode in {"compact", "expanded", "hybrid"} else "compact"

    def _build_expanded_search_query(self, request: GenerateProblemRequest) -> str:
        terms: list[str] = []

        def add_terms(values: list[str] | tuple[str, ...]) -> None:
            for value in values:
                normalized = self._normalize_query_term(value)
                if normalized:
                    terms.append(normalized)

        add_terms(tuple(request.concepts))
        add_terms(self.SEARCH_QUERY_STYLE_CUES.get(request.problem_style, ()))

        if self._is_high_rigor_request(request):
            add_terms(self.HIGH_RIGOR_SEARCH_QUERY_CUES)

        if request.goal == GenerationGoal.exam_prep:
            add_terms(self.EXAM_PREP_SEARCH_QUERY_CUES)

        if request.course_level == CourseLevel.university:
            add_terms(self.UNIVERSITY_SEARCH_QUERY_CUES)

        add_terms(tuple(self._safe_query_terms_from_requirements(request.user_requirements)))

        query_terms = self._dedupe_query_terms(terms)
        fallback = self._normalize_query_term(" ".join(request.concepts)) or request.document_id
        return " ".join(query_terms) or fallback

    def _compact_search_query_terms(self, request: GenerateProblemRequest) -> list[str]:
        terms: list[str] = []
        concept_terms = self._concept_query_term_keys(request)

        def add_terms(values: list[str] | tuple[str, ...]) -> None:
            for value in values:
                normalized = self._normalize_query_term(value)
                if normalized:
                    terms.append(normalized)

        add_terms(tuple(request.concepts))
        add_terms(self.COMPACT_SEARCH_QUERY_STYLE_CUES.get(request.problem_style, ()))
        add_terms(
            tuple(
                self._safe_query_terms_from_requirements(
                    request.user_requirements,
                    compact=True,
                    concept_terms=concept_terms,
                )
            )
        )
        return terms

    def _hybrid_search_query_extra_terms(self, request: GenerateProblemRequest, existing_terms: list[str]) -> list[str]:
        existing_keys = {term.lower() for term in self._dedupe_query_terms(existing_terms)}
        extras: list[str] = []

        def add_candidates(values: tuple[str, ...]) -> None:
            for value in values:
                if len(extras) >= 5:
                    return
                normalized = self._normalize_query_term(value)
                key = normalized.lower()
                if normalized and key not in existing_keys:
                    extras.append(normalized)
                    existing_keys.add(key)

        add_candidates(self.SEARCH_QUERY_STYLE_CUES.get(request.problem_style, ()))
        if self._is_high_rigor_request(request):
            add_candidates(self.HIGH_RIGOR_SEARCH_QUERY_CUES)
        return extras

    def _build_generation_intent_summary(self, request: GenerateProblemRequest) -> str:
        parts = [
            f"type={request.type.value}",
            f"difficulty={request.difficulty.value}",
            f"bloom_level={request.bloom_level.value}",
            f"goal={request.goal.value}",
            f"course_level={request.course_level.value}",
            f"target_rigor={request.target_rigor.value}",
            f"problem_style={request.problem_style.value}",
            f"quality_mode={request.quality_mode.value}",
            f"depth={request.depth.value}",
        ]
        requirement_terms = self._safe_query_terms_from_requirements(request.user_requirements)
        if requirement_terms:
            parts.append("requirements=" + " ".join(requirement_terms))
        return "; ".join(parts)

    def _is_high_rigor_request(self, request: GenerateProblemRequest) -> bool:
        return (
            request.target_rigor == TargetRigor.high
            or request.difficulty == Difficulty.hard
            or request.bloom_level in {BloomLevel.analyze, BloomLevel.evaluate, BloomLevel.create}
            or request.quality_mode == QualityMode.strict
            or request.depth == ProblemDepth.deep
        )

    def _safe_query_terms_from_requirements(
        self,
        user_requirements: str | None,
        *,
        compact: bool = False,
        concept_terms: set[str] | None = None,
    ) -> list[str]:
        if not user_requirements:
            return []

        cleaned = re.sub(r"\s+", " ", user_requirements).strip()
        for phrase in self.UNSAFE_SEARCH_QUERY_PHRASES:
            cleaned = re.sub(re.escape(phrase), " ", cleaned, flags=re.IGNORECASE)

        tokens = re.findall(r"[0-9A-Za-z가-힣_+/#.-]+", cleaned)
        safe_tokens: list[str] = []
        for token in tokens:
            token = self._normalize_compact_query_token(token) if compact else token
            if not token:
                continue
            if token.lower() in self.UNSAFE_SEARCH_QUERY_TOKENS:
                continue
            if compact and not self._is_compact_requirement_query_term(token, concept_terms or set()):
                continue
            safe_tokens.append(token)
            if len(safe_tokens) >= self.USER_REQUIREMENT_QUERY_TOKEN_LIMIT:
                break
        return safe_tokens

    def _dedupe_query_terms(self, terms: list[str]) -> list[str]:
        seen: set[str] = set()
        deduped: list[str] = []
        for term in terms:
            key = term.lower()
            if key in seen:
                continue
            seen.add(key)
            deduped.append(term)
        return deduped

    def _normalize_query_term(self, value: str) -> str:
        return re.sub(r"\s+", " ", str(value or "").strip())

    def _normalize_compact_query_token(self, token: str) -> str:
        normalized = self._normalize_query_term(token).strip(".,;:!?()[]{}\"'")
        if not normalized:
            return ""
        return self._strip_korean_query_particle(normalized)

    def _strip_korean_query_particle(self, token: str) -> str:
        if not re.search(r"[가-힣]", token):
            return token
        for suffix in self.KOREAN_QUERY_PARTICLE_SUFFIXES:
            if token.endswith(suffix) and len(token) > len(suffix) + 1:
                return token[: -len(suffix)]
        return token

    def _is_compact_requirement_query_term(self, token: str, concept_terms: set[str]) -> bool:
        key = token.lower()
        if key in concept_terms:
            return True
        if self._is_compact_source_cue(token):
            return True
        if key in self.COMPACT_SEARCH_QUERY_STOPWORDS:
            return False
        if self._is_compact_generic_query_term(token):
            return False
        if len(token) <= 1 and not re.search(r"[0-9+#/]", token):
            return False
        return True

    def _is_compact_source_cue(self, token: str) -> bool:
        key = token.lower()
        return any(
            key == str(cue).lower()
            for cues in self.COMPACT_SEARCH_QUERY_STYLE_CUES.values()
            for cue in cues
        )

    def _is_compact_generic_query_term(self, token: str) -> bool:
        key = token.lower()
        if key in self.COMPACT_SEARCH_QUERY_GENERIC_TERMS:
            return True
        korean_roots = (
            "시험",
            "출제",
            "예상",
            "변별",
            "대학",
            "심화",
            "전공",
            "적용",
            "사례",
            "조건",
            "상황",
            "판단",
            "분석",
            "비교",
            "문제",
            "문항",
            "퀴즈",
            "생성",
            "작성",
            "만들",
            "설명",
            "고르",
            "선택",
        )
        return any(token.startswith(root) and len(token) <= len(root) + 3 for root in korean_roots)

    def _concept_query_term_keys(self, request: GenerateProblemRequest) -> set[str]:
        keys: set[str] = set()
        for concept in request.concepts:
            normalized = self._normalize_query_term(concept)
            if normalized:
                keys.add(normalized.lower())
            for token in re.findall(r"[0-9A-Za-z가-힣_+/#.-]+", normalized):
                compact_token = self._normalize_compact_query_token(token)
                if compact_token:
                    keys.add(compact_token.lower())
        return keys

    def _problem_signature(self, problem_data: dict) -> str:
        choices = problem_data.get("choices") or []
        choice_text = " ".join(
            str(choice.get("text") or "")
            for choice in choices
            if isinstance(choice, dict)
        )
        answer_text = str((problem_data.get("answer") or {}).get("text") or "")
        return self._normalize_signature_text(
            " ".join(
                [
                    str(problem_data.get("type") or ""),
                    str(problem_data.get("question") or ""),
                    choice_text,
                    answer_text,
                ]
            )
        )

    def _problem_fingerprint(self, problem_data: dict) -> dict:
        question = self._normalize_signature_text(str(problem_data.get("question") or ""))
        return {
            "signature": self._problem_signature(problem_data),
            "type": str(problem_data.get("type") or ""),
            "question": question,
            "question_tokens": self._question_tokens(question),
            "number_normalized_question_tokens": self._number_normalized_question_tokens(question),
            "concepts": {
                self._normalize_signature_text(str(concept))
                for concept in (problem_data.get("concepts") or [])
                if str(concept).strip()
            },
            "reasoning_template": self._reasoning_template_fingerprint(problem_data),
        }

    def _is_reused_problem(self, *, problem_data: dict, seen_fingerprints: list[dict]) -> bool:
        current = self._problem_fingerprint(problem_data)
        for seen in seen_fingerprints:
            if current["signature"] == seen.get("signature"):
                return True
            if current["type"] != seen.get("type"):
                continue
            if current["concepts"] and seen.get("concepts") and not (current["concepts"] & seen["concepts"]):
                continue
            if current["question"] and current["question"] == seen.get("question"):
                return True
            if self._question_similarity(current["question_tokens"], seen.get("question_tokens", set())) >= 0.86:
                return True
            if self._is_reused_reasoning_template(current=current, seen=seen):
                return True
        return False

    def _is_reused_reasoning_template(self, *, current: dict, seen: dict) -> bool:
        if current.get("type") != seen.get("type"):
            return False
        if not current.get("reasoning_template") or current.get("reasoning_template") != seen.get("reasoning_template"):
            return False
        current_concepts = current.get("concepts") or set()
        seen_concepts = seen.get("concepts") or set()
        if current_concepts and seen_concepts and not (current_concepts & seen_concepts):
            return False

        question_similarity = self._question_similarity(
            current.get("question_tokens", set()),
            seen.get("question_tokens", set()),
        )
        if question_similarity >= 0.55:
            return True

        operation = self._reasoning_operation_from_template(str(current.get("reasoning_template") or ""))
        if operation in {"formula_substitution", "calculation_substitution", "definition_recall", "generic_application"}:
            return True

        number_normalized_similarity = self._question_similarity(
            current.get("number_normalized_question_tokens", set()),
            seen.get("number_normalized_question_tokens", set()),
        )
        return number_normalized_similarity >= 0.70

    def _reasoning_template_fingerprint(self, problem_data: dict) -> str:
        operation = self._reasoning_operation(problem_data)
        concept_key = "|".join(
            sorted(
                {
                    self._normalize_template_concept(str(concept))
                    for concept in (problem_data.get("concepts") or [])
                    if str(concept).strip()
                }
            )
        )
        profile = problem_data.get("difficulty_profile") or {}
        if not isinstance(profile, dict):
            profile = {}
        profile_markers = [
            key
            for key in (
                "requires_transfer",
                "requires_calculation",
                "requires_comparison",
                "requires_error_analysis",
            )
            if profile.get(key) is True
        ]
        try:
            reasoning_steps = int(profile.get("reasoning_steps_required") or 0)
        except (TypeError, ValueError):
            reasoning_steps = 0
        step_bucket = "steps_3_plus" if reasoning_steps >= 3 else "steps_2" if reasoning_steps == 2 else "steps_0_1"

        broad_template_operations = {
            "formula_substitution",
            "calculation_substitution",
            "definition_recall",
            "generic_application",
        }
        if operation in broad_template_operations:
            stem_key = "broad_stem"
        else:
            normalized_stem = self._reasoning_template_text(str(problem_data.get("question") or ""))
            stem_key = " ".join(sorted(self._question_tokens(normalized_stem))[:18])
        return "|".join(
            [
                self._normalize_signature_text(str(problem_data.get("type") or "")),
                operation,
                concept_key or "no_concept",
                self._normalize_signature_text(str(problem_data.get("difficulty") or "")),
                self._normalize_signature_text(str(problem_data.get("bloom_level") or "")),
                self._normalize_signature_text(str(problem_data.get("item_model_id") or "")),
                step_bucket,
                ",".join(profile_markers),
                stem_key,
            ]
        )

    def _reasoning_operation(self, problem_data: dict) -> str:
        text = self._reasoning_template_source_text(problem_data)
        item_model_id = self._normalize_signature_text(str(problem_data.get("item_model_id") or ""))
        profile = problem_data.get("difficulty_profile") or {}
        if not isinstance(profile, dict):
            profile = {}

        if item_model_id == "misconception_contrast" or self._contains_any(
            text, ("오개념", "헷갈", "혼동", "착각", "misconception", "confusion")
        ):
            return "misconception_contrast"
        if item_model_id == "error_detection" or self._contains_any(
            text, ("오류", "잘못", "틀린", "수정", "반례", "bug", "error", "debug", "wrong")
        ):
            return "error_diagnosis"
        if item_model_id == "evidence_selection" or (
            self._contains_any(text, ("근거", "증거", "자료", "문장", "evidence", "source"))
            and self._contains_any(text, ("고르", "선택", "찾", "뒷받침", "select", "choose", "support"))
        ):
            return "evidence_selection"
        if item_model_id == "data_interpretation" or self._contains_any(
            text, ("표", "그래프", "도표", "자료값", "데이터", "해석", "table", "graph", "data", "interpret")
        ):
            return "data_interpretation"
        if self._contains_any(
            text, ("추적", "단계별", "상태", "큐", "스택", "배열", "코드", "trace", "state", "queue", "stack", "array", "code")
        ):
            return "trace_and_explain"
        if self._contains_any(text, ("설계", "제약", "최적", "tradeoff", "constraint", "design", "optimize")):
            return "design_under_constraint"
        if self._contains_any(text, ("비교", "차이", "공통점", "공통", "compare", "contrast", "difference")) or profile.get(
            "requires_comparison"
        ) is True:
            return "concept_comparison"
        if self._contains_any(text, ("경계", "구분", "범위", "예외", "한계", "boundary", "limitation", "exception")):
            return "concept_boundary"
        if self._contains_any(text, ("조건", "변화", "바뀌", "달라지", "changed condition", "condition changes")):
            return "condition_mutation"
        if item_model_id in {"case_based_application", "transfer_to_new_context"} or profile.get("requires_transfer") is True:
            return "transfer_to_new_context"

        has_calculation = self._has_calculation_template_signal(text) or profile.get("requires_calculation") is True
        if has_calculation:
            if self._contains_any(
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
            return "calculation_substitution"

        definition_cues = ("정의", "무엇인가", "무엇인지", "의미", "개념", "define", "definition")
        reasoning_cues = (
            "조건",
            "사례",
            "상황",
            "적용",
            "분석",
            "비교",
            "판단",
            "추론",
            "해석",
            "변화",
            "근거",
            "case",
            "scenario",
            "apply",
            "analyze",
            "compare",
            "infer",
            "interpret",
        )
        if self._contains_any(text, definition_cues) and not self._contains_any(text, reasoning_cues):
            return "definition_recall"
        if self._contains_any(text, reasoning_cues):
            return "generic_application"
        return "definition_recall"

    def _reasoning_operation_from_template(self, template: str) -> str:
        parts = str(template or "").split("|")
        return parts[1] if len(parts) > 1 else ""

    def _reasoning_template_source_text(self, problem_data: dict) -> str:
        parts = [
            str(problem_data.get("type") or ""),
            str(problem_data.get("question") or ""),
            str(problem_data.get("difficulty") or ""),
            str(problem_data.get("bloom_level") or ""),
            str(problem_data.get("item_model_id") or ""),
            str((problem_data.get("answer") or {}).get("text") or ""),
            str(problem_data.get("explanation") or ""),
            self._flatten_template_field(problem_data.get("difficulty_profile")),
            self._flatten_template_field(problem_data.get("item_design_brief")),
        ]
        choices = problem_data.get("choices") or []
        parts.extend(str(choice.get("text") or "") for choice in choices if isinstance(choice, dict))
        rubric = problem_data.get("rubric") or []
        parts.extend(self._flatten_template_field(item) for item in rubric if isinstance(item, dict))
        return self._reasoning_template_text(" ".join(parts))

    def _flatten_template_field(self, value) -> str:
        if isinstance(value, dict):
            return " ".join(f"{key} {self._flatten_template_field(item)}" for key, item in value.items())
        if isinstance(value, list):
            return " ".join(self._flatten_template_field(item) for item in value)
        return str(value or "")

    def _reasoning_template_text(self, text: str) -> str:
        normalized = self._normalize_signature_text(text)
        normalized = re.sub(r"\d+\s*/\s*\d+", " <num> ", normalized)
        normalized = re.sub(r"\d+(?:\.\d+)?", " <num> ", normalized)
        normalized = re.sub(r"\b[a-zA-Z]\b", " <var> ", normalized)
        return self._normalize_signature_text(normalized)

    def _normalize_template_concept(self, concept: str) -> str:
        return self._normalize_signature_text(self._reasoning_template_text(concept))

    def _contains_any(self, text: str, cues: tuple[str, ...]) -> bool:
        return any(cue in text for cue in cues)

    def _has_calculation_template_signal(self, text: str) -> bool:
        calculation_cues = ("계산", "공식", "수식", "대입", "값을 구", "구하", "formula", "equation", "calculate")
        has_formula = bool(re.search(r"[a-z가-힣]\w*\s*=\s*[a-z0-9가-힣]", text))
        return bool(
            has_formula
            or self._contains_any(text, calculation_cues)
            or ("<num>" in text and self._contains_any(text, calculation_cues + ("몇", "합", "차", "곱", "나누")))
        )

    def _number_normalized_question_tokens(self, text: str) -> set[str]:
        normalized = self._reasoning_template_text(text)
        return {
            token
            for token in re.findall(r"[0-9a-zA-Z가-힣_<>]+", normalized)
            if len(token) > 1
        }

    def _question_tokens(self, text: str) -> set[str]:
        return {
            token
            for token in re.findall(r"[0-9a-zA-Z가-힣]+", text)
            if len(token) > 1
        }

    def _question_similarity(self, left: set[str], right: set[str]) -> float:
        if not left or not right:
            return 0.0
        return len(left & right) / len(left | right)

    def _normalize_signature_text(self, text: str) -> str:
        return re.sub(r"\s+", " ", str(text or "").strip().lower())

    def _normalize_request_intent(self, request: GenerateProblemRequest) -> GenerateProblemRequest:
        style_updates = self._updates_from_problem_style(request)
        requirements = (request.user_requirements or "").lower()
        if not requirements:
            return request.model_copy(update=style_updates) if style_updates else request

        exam_cues = (
            "시험",
            "고사",
            "평가",
            "예상 문제",
            "예상",
            "출제",
            "나올 만",
            "나올법",
            "대비",
            "exam",
            "test",
            "assessment",
            "midterm",
            "final",
        )
        high_rigor_cues = (
            "고난도",
            "심화",
            "심층",
            "증명",
            "실전",
            "어렵",
            "난도 높",
            "난이도 높",
            "변별",
            "대학",
            "복합",
            "복잡",
            "여러 개념",
            "개념 혼합",
            "다단계",
            "여러 단계",
            "사고력",
            "새 구조",
            "새 규칙",
            "새 기준",
            "hard",
            "advanced",
            "proof",
            "design",
        )
        updates = dict(style_updates)
        has_exam_intent = any(cue in requirements for cue in exam_cues)
        raw_high_rigor_intent = any(cue in requirements for cue in high_rigor_cues)
        has_high_rigor_intent = raw_high_rigor_intent and not self._simple_generation_intent(
            request=request,
            requirements=requirements,
        )

        if has_exam_intent and request.goal == GenerationGoal.practice:
            updates["goal"] = GenerationGoal.exam_prep
        if "대학" in requirements and request.course_level == CourseLevel.general:
            updates["course_level"] = CourseLevel.university
        if has_high_rigor_intent and request.target_rigor != TargetRigor.high:
            updates["target_rigor"] = TargetRigor.high
        if has_exam_intent and has_high_rigor_intent and request.quality_mode == QualityMode.standard:
            updates["quality_mode"] = QualityMode.strict
        if has_high_rigor_intent and request.difficulty != Difficulty.hard:
            updates["difficulty"] = Difficulty.hard
        if has_high_rigor_intent and request.bloom_level in {BloomLevel.remember, BloomLevel.understand}:
            updates["bloom_level"] = BloomLevel.analyze
        if (
            has_high_rigor_intent
            and request.type == ProblemType.short_answer
            and request.depth == ProblemDepth.standard
        ):
            updates["depth"] = ProblemDepth.deep

        if not updates:
            return request
        return request.model_copy(update=updates)

    def _simple_generation_intent(self, *, request: GenerateProblemRequest, requirements: str) -> bool:
        if request.problem_style == ProblemStyle.concept_check:
            return True
        strong_cues = (
            "고난도",
            "심화",
            "응용",
            "분석",
            "비교",
            "판단",
            "추론",
            "평가",
            "설계",
            "시험",
            "고사",
            "출제",
            "hard",
            "advanced",
            "exam",
        )
        if any(cue in requirements for cue in strong_cues):
            return False
        simple_cues = (
            "간단",
            "쉽게",
            "기본",
            "기초",
            "짧",
            "정의",
            "개념 확인",
            "암기",
            "요약",
            "플래시카드",
            "ox",
            "o/x",
            "true/false",
            "퀴즈",
            "basic",
            "simple",
            "recall",
            "definition",
            "flashcard",
        )
        return any(cue in requirements for cue in simple_cues)

    def _updates_from_problem_style(self, request: GenerateProblemRequest) -> dict:
        updates = {}
        if request.problem_style == ProblemStyle.concept_check:
            if request.bloom_level == BloomLevel.remember:
                updates["bloom_level"] = BloomLevel.understand
            return updates

        if request.problem_style in {
            ProblemStyle.exam_application,
            ProblemStyle.calculation_practice,
            ProblemStyle.evidence_analysis,
            ProblemStyle.error_detection,
        }:
            if request.goal == GenerationGoal.practice:
                updates["goal"] = GenerationGoal.exam_prep
            if request.target_rigor != TargetRigor.high:
                updates["target_rigor"] = TargetRigor.high
            if request.quality_mode == QualityMode.standard:
                updates["quality_mode"] = QualityMode.strict
            if request.difficulty != Difficulty.hard:
                updates["difficulty"] = Difficulty.hard
            if request.bloom_level in {BloomLevel.remember, BloomLevel.understand}:
                updates["bloom_level"] = BloomLevel.analyze
            if request.type == ProblemType.short_answer and request.depth == ProblemDepth.standard:
                updates["depth"] = ProblemDepth.deep
            return updates

        if request.problem_style == ProblemStyle.misconception_drill:
            if request.bloom_level == BloomLevel.remember:
                updates["bloom_level"] = BloomLevel.understand
            return updates

        return updates
