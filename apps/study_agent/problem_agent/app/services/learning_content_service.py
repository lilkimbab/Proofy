from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from app.agents import FeedbackAgent, LearningContentAgent, LearningContentQualityChecker
from app.config import Settings, get_settings
from app.llm import safety_identifier_for_user
from app.models import Feedback, Problem
from app.repositories.feedback_repository import FeedbackRepository
from app.repositories.learning_content_repository import LearningContentRepository
from app.repositories.mistake_remediation_event_repository import MistakeRemediationEventRepository
from app.repositories.problem_repository import ProblemRepository
from app.repositories.usage_ledger_repository import UsageLedgerRepository
from app.schemas.integration_contracts import RetrievedChunk
from app.schemas.learning_contents import (
    GenerateMistakeDrillRequest,
    GenerateLearningContentRequest,
    GenerateMiniExamRequest,
    LearningContentBase,
    LearningContentQualityReport,
    LearningContentRecommendationOption,
    LearningContentType,
    ProblemRecommendationOption,
    RecommendLearningContentRequest,
)
from app.schemas.problems import BloomLevel, Difficulty, GenerateProblemRequest, ProblemStyle, ProblemType
from app.schemas.quality import (
    ContentForm,
    LearningTaskStrategyProfile,
    MaterialReadinessReport,
    QualityStatus,
    TargetRigor,
)
from app.services.learning_task_strategy_router import LearningTaskStrategyRouter
from app.services.material_readiness_service import MaterialReadinessAnalyzer
from app.services.request_safety import validate_safe_user_requirements
from app.services.learning_voice_renderer import LearningVoiceRenderer
from app.services.generated_artifact_publisher import GeneratedArtifactPublisher
from app.services.problem_service import ProblemService
from app.services.search_service import SearchAgentError, SearchService


@dataclass(frozen=True)
class LearningContentGenerationResult:
    contents: list[LearningContentBase]
    rejected: int
    warnings: list[str]
    learning_task_strategy: LearningTaskStrategyProfile | None = None
    material_readiness: MaterialReadinessReport | None = None


@dataclass(frozen=True)
class LearningContentRecommendationResult:
    problem_options: list[ProblemRecommendationOption]
    content_options: list[LearningContentRecommendationOption]
    selectable_content_types: list[LearningContentType]
    available_content_types: list[LearningContentType]
    recommended_content_types: list[LearningContentType]
    not_recommended_content_types: list[LearningContentType]
    reason: str
    learning_task_strategy: LearningTaskStrategyProfile
    material_readiness: MaterialReadinessReport


class LearningContentService:
    def __init__(
        self,
        *,
        search_service: SearchService,
        learning_content_agent: LearningContentAgent,
        quality_checker: LearningContentQualityChecker,
        repository: LearningContentRepository,
        feedback_repository: FeedbackRepository | None = None,
        problem_repository: ProblemRepository | None = None,
        problem_service: ProblemService | None = None,
        voice_renderer: LearningVoiceRenderer | None = None,
        feedback_agent: FeedbackAgent | None = None,
        remediation_repository: MistakeRemediationEventRepository | None = None,
        learning_task_router: LearningTaskStrategyRouter | None = None,
        material_readiness_analyzer: MaterialReadinessAnalyzer | None = None,
        artifact_publisher: GeneratedArtifactPublisher | None = None,
        usage_ledger_repository: UsageLedgerRepository | None = None,
        settings: Settings | None = None,
    ):
        self.settings = settings or getattr(learning_content_agent, "settings", None) or get_settings()
        self.search_service = search_service
        self.learning_content_agent = learning_content_agent
        self.quality_checker = quality_checker
        self.repository = repository
        self.feedback_repository = feedback_repository
        self.problem_repository = problem_repository
        self.problem_service = problem_service
        self.voice_renderer = voice_renderer or LearningVoiceRenderer()
        self.feedback_agent = feedback_agent or FeedbackAgent()
        self.remediation_repository = remediation_repository
        self.learning_task_router = learning_task_router or LearningTaskStrategyRouter()
        self.material_readiness_analyzer = material_readiness_analyzer or MaterialReadinessAnalyzer()
        self.artifact_publisher = artifact_publisher or GeneratedArtifactPublisher()
        self.usage_ledger_repo = usage_ledger_repository

    def generate_contents(
        self,
        *,
        user_id: str,
        request: GenerateLearningContentRequest,
    ) -> LearningContentGenerationResult:
        self._validate_user_requirements_controls(request.user_requirements)
        chunks = self.search_service.search_chunks(
            document_id=request.document_id,
            concepts=request.concepts,
            difficulty=request.difficulty.value,
            query=" ".join(request.concepts),
            top_k=max(6, request.count),
        )
        self._validate_retrieved_chunks(document_id=request.document_id, chunks=chunks)
        strategy_profile, material_readiness = self._analyze_learning_material(
            document_id=request.document_id,
            concepts=request.concepts,
            count=request.count,
            difficulty=request.difficulty,
            bloom_level=request.bloom_level,
            user_requirements=request.user_requirements,
            chunks=chunks,
        )

        self._enforce_learning_content_llm_budget_if_needed(user_id=user_id)
        learning_content_llm = getattr(self.learning_content_agent, "llm", None)
        self._reset_llm_usage(learning_content_llm)
        candidates = self.learning_content_agent.generate(
            request,
            chunks,
            safety_identifier=safety_identifier_for_user(user_id),
            learning_task_strategy=strategy_profile,
            material_readiness=material_readiness,
            candidate_count=request.count,
        )
        self._record_learning_content_llm_usage(user_id=user_id, client=learning_content_llm)

        valid_contents: list[tuple[float, LearningContentBase]] = []
        invalid_errors: list[str] = []
        warning_messages: list[str] = []
        rejected_count = 0
        for candidate in candidates:
            content = LearningContentBase.model_validate(candidate)
            quality = self.quality_checker.validate(content, retrieved_chunks=chunks)
            if not quality.is_valid:
                invalid_errors.extend(quality.errors)
                rejected_count += 1
                continue

            flags = list(dict.fromkeys([*content.quality_report.flags, *quality.flags]))
            score = quality.source_coverage_score or content.quality_report.score
            validated_content = content.model_copy(
                update={
                    "quality_status": QualityStatus.passed,
                    "material_readiness": material_readiness,
                    "quality_report": LearningContentQualityReport(
                        status=QualityStatus.passed,
                        score=min(max(score, 0), 1),
                        flags=flags,
                        source_grounded=True,
                        reasons=["저장 전 결정적 품질 검증을 통과했다."],
                        action="save",
                    ),
                },
                deep=True,
            )
            validated_content = self._attach_copy(validated_content)
            if flags:
                warning_messages.append("quality flags: " + ", ".join(flag.value for flag in flags))
            valid_contents.append((validated_content.quality_report.score, validated_content))

        saved_count_target = request.count
        valid_contents = sorted(valid_contents, key=lambda candidate: candidate[0], reverse=True)[:saved_count_target]
        if len(valid_contents) < request.count:
            detail = "; ".join(dict.fromkeys(invalid_errors)) or "LLM returned fewer learning contents than requested"
            raise ValueError(
                f"Only {len(valid_contents)} valid learning contents were generated out of {request.count}: {detail}"
            )

        saved = self.repository.create_many(
            user_id=user_id,
            contents=[content for _score, content in valid_contents],
        )
        self._publish_learning_contents(saved)
        return LearningContentGenerationResult(
            contents=saved,
            rejected=rejected_count,
            warnings=list(dict.fromkeys(warning_messages)),
            learning_task_strategy=strategy_profile,
            material_readiness=material_readiness,
        )

    def _enforce_learning_content_llm_budget_if_needed(self, *, user_id: str) -> None:
        if self.usage_ledger_repo is None or not self._learning_content_will_use_llm():
            return
        if not self.settings.llm_enforce_monthly_budget or self.settings.llm_monthly_user_budget_krw <= 0:
            return
        budget_summary = self.usage_ledger_repo.summary_for_user(
            user_id=user_id,
            since=self._current_month_start(),
        )
        if budget_summary["budget_status"] == "exceeded":
            raise ValueError("monthly LLM budget exceeded")

    def _record_learning_content_llm_usage(self, *, user_id: str, client: object) -> None:
        if self.usage_ledger_repo is None:
            return
        ledger = self.usage_ledger_repo.create_from_llm_client(
            user_id=user_id,
            feature="learning_content_generation",
            client=client,
            premium_reason="direct learning content generation",
        )
        if ledger is not None:
            self.usage_ledger_repo.db.commit()

    def _learning_content_will_use_llm(self) -> bool:
        learning_content_llm = getattr(self.learning_content_agent, "llm", None)
        return bool(getattr(learning_content_llm, "available", False))

    def _validate_user_requirements_controls(self, user_requirements: str | None) -> None:
        validate_safe_user_requirements(
            user_requirements,
            error_message="unsafe learning content generation request",
        )

    def _reset_llm_usage(self, client: object) -> None:
        reset = getattr(client, "reset_last_call", None)
        if callable(reset):
            reset()

    def _current_month_start(self) -> datetime:
        now = datetime.now(timezone.utc)
        return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    def get_content(self, content_id: str) -> LearningContentBase | None:
        return self.repository.get(content_id)

    def recommend_content_types(
        self,
        *,
        request: RecommendLearningContentRequest,
    ) -> LearningContentRecommendationResult:
        self._validate_user_requirements_controls(request.user_requirements)
        chunks = self.search_service.search_chunks(
            document_id=request.document_id,
            concepts=request.concepts,
            difficulty=request.difficulty.value,
            query=" ".join(request.concepts),
            top_k=max(6, request.count),
        )
        self._validate_retrieved_chunks(document_id=request.document_id, chunks=chunks)
        strategy_profile, material_readiness = self._analyze_learning_material(
            document_id=request.document_id,
            concepts=request.concepts,
            count=request.count,
            difficulty=request.difficulty,
            bloom_level=request.bloom_level,
            user_requirements=request.user_requirements,
            chunks=chunks,
        )
        problem_options = self._problem_options(request=request, strategy_profile=strategy_profile)
        content_options = self._content_options(strategy_profile=strategy_profile)
        return LearningContentRecommendationResult(
            problem_options=problem_options,
            content_options=content_options,
            selectable_content_types=self._content_types_from_values(
                strategy_profile.selectable_learning_content_types
            ),
            available_content_types=self._content_types_from_values(
                strategy_profile.available_learning_content_types
            ),
            recommended_content_types=self._content_types_from_values(
                strategy_profile.recommended_learning_content_types
            ),
            not_recommended_content_types=self._content_types_from_values(
                strategy_profile.not_recommended_learning_content_types
            ),
            reason=strategy_profile.learning_content_type_reason,
            learning_task_strategy=strategy_profile,
            material_readiness=material_readiness,
        )

    def generate_mistake_drills(
        self,
        *,
        user_id: str,
        request: GenerateMistakeDrillRequest,
    ) -> LearningContentGenerationResult:
        self._validate_user_requirements_controls(request.user_requirements)
        if self.feedback_repository is None or self.problem_repository is None or self.problem_service is None:
            raise RuntimeError("Mistake drill generation requires feedback and problem repositories")

        feedback = self.feedback_repository.get(request.feedback_id)
        if feedback is None or feedback.user_id != user_id:
            raise LookupError("Feedback not found")
        if feedback.is_correct:
            raise ValueError("Mistake drill can only be generated from incorrect feedback")
        if feedback.mistake_type in (None, "none"):
            raise ValueError("Mistake drill requires a concrete mistake_type")

        seed_problem = self.problem_repository.get(feedback.problem_id)
        if seed_problem is None or seed_problem.user_id != user_id:
            raise LookupError("Problem not found")

        target_concepts = self._mistake_drill_concepts(feedback=feedback, seed_problem=seed_problem)
        choice_diagnostic = self._mistake_drill_choice_diagnostic(feedback=feedback, seed_problem=seed_problem)
        drill_problem_request = self._mistake_drill_problem_request(
            request=request,
            feedback=feedback,
            seed_problem=seed_problem,
            target_concepts=target_concepts,
            choice_diagnostic=choice_diagnostic,
        )
        generated_problems = self.problem_service.generate_problems(user_id=user_id, request=drill_problem_request)
        contents: list[tuple[LearningContentBase, Problem]] = []
        rejected_count = 0
        errors: list[str] = []

        for generated_problem in generated_problems:
            content = LearningContentBase(
                document_id=generated_problem.document_id,
                content_type=LearningContentType.mistake_drill,
                concepts=target_concepts,
                source_chunk_ids=generated_problem.source_chunk_ids,
                difficulty=generated_problem.difficulty,
                bloom_level=generated_problem.bloom_level,
                quality_status=QualityStatus.passed,
                quality_report=LearningContentQualityReport(
                    status=QualityStatus.passed,
                    score=0.8,
                    source_grounded=True,
                    reasons=["방금 틀린 지점과 같은 개념을 다시 묻는 연습이다."],
                    action="validate_before_save",
                ),
                payload={
                    "seed_problem_id": seed_problem.id,
                    "seed_feedback_id": feedback.id,
                    "target_mistake_type": feedback.mistake_type,
                    "target_concepts": target_concepts,
                    "variant_strategy": request.variant_strategy,
                    **self._mistake_drill_payload_focus(choice_diagnostic),
                    "generated_problem_id": generated_problem.id,
                },
                content_version="mistake_drill_v1",
            )
            chunks = self.search_service.get_chunks_by_ids(
                document_id=generated_problem.document_id,
                chunk_ids=generated_problem.source_chunk_ids,
            )
            quality = self.quality_checker.validate(content, retrieved_chunks=chunks)
            if not quality.is_valid:
                errors.extend(quality.errors)
                rejected_count += 1
                continue
            validated_content = content.model_copy(
                update={
                    "quality_report": LearningContentQualityReport(
                        status=QualityStatus.passed,
                        score=quality.source_coverage_score or content.quality_report.score,
                        flags=quality.flags,
                        source_grounded=True,
                        reasons=["오답 맞춤 연습으로 바로 풀 수 있게 준비됐다."],
                        action="save",
                    )
                },
                deep=True,
            )
            validated_content = self._attach_copy(validated_content)
            contents.append((validated_content, generated_problem))

        if len(contents) < request.count:
            detail = "; ".join(dict.fromkeys(errors)) or "No valid mistake drill content was generated"
            raise ValueError(
                f"Only {len(contents)} valid mistake drills were generated out of {request.count}: {detail}"
            )

        prepared_contents = self._attach_remediation_events(
            user_id=user_id,
            feedback=feedback,
            seed_problem=seed_problem,
            contents_with_problems=contents[: request.count],
        )
        saved = self.repository.create_many(user_id=user_id, contents=prepared_contents)
        self._link_remediation_events_to_saved_contents(saved)
        self._publish_learning_contents(saved)
        return LearningContentGenerationResult(contents=saved, rejected=rejected_count, warnings=[])

    def generate_mini_exam(
        self,
        *,
        user_id: str,
        request: GenerateMiniExamRequest,
    ) -> LearningContentGenerationResult:
        self._validate_user_requirements_controls(request.user_requirements)
        if self.problem_service is None:
            raise RuntimeError("Mini exam generation requires problem service")

        problem_request = GenerateProblemRequest(
            document_id=request.document_id,
            concepts=request.concepts,
            type=request.problem_type,
            count=request.count,
            difficulty=request.difficulty,
            bloom_level=request.bloom_level,
            user_requirements=request.user_requirements,
        )
        problem_batch = self.problem_service.generate_problem_batch(user_id=user_id, request=problem_request)
        generated_problems = problem_batch.problems
        source_chunk_ids = list(
            dict.fromkeys(chunk_id for problem in generated_problems for chunk_id in problem.source_chunk_ids)
        )
        if not source_chunk_ids:
            raise ValueError("Mini exam requires source grounded problems")

        content = LearningContentBase(
            document_id=request.document_id,
            content_type=LearningContentType.mini_exam,
            concepts=request.concepts,
            source_chunk_ids=source_chunk_ids,
            difficulty=request.difficulty,
            bloom_level=request.bloom_level,
            quality_status=QualityStatus.passed,
            quality_report=LearningContentQualityReport(
                status=QualityStatus.passed,
                score=0.85,
                source_grounded=True,
                reasons=["자료 기반 문제를 묶은 짧은 점검 세트다."],
                action="validate_before_save",
            ),
            material_readiness=problem_batch.material_readiness,
            payload={
                "title": request.title or f"{request.concepts[0]} 미니 점검",
                "time_limit_seconds": request.time_limit_seconds,
                "items": [
                    {
                        "problem_id": problem.id,
                        "content_type": problem.type,
                        "points": self._problem_points(problem),
                    }
                    for problem in generated_problems
                ],
                "blueprint": {
                    "total_count": len(generated_problems),
                    "concepts": request.concepts,
                    "problem_type": request.problem_type.value,
                    "difficulty": request.difficulty.value,
                    "bloom_level": request.bloom_level.value,
                    "source_chunk_ids": source_chunk_ids,
                    "quality_summary": problem_batch.quality_summary.model_dump(mode="json"),
                },
            },
            content_version="mini_exam_v1",
        )

        chunks = self.search_service.get_chunks_by_ids(
            document_id=request.document_id,
            chunk_ids=source_chunk_ids,
        )
        quality = self.quality_checker.validate(content, retrieved_chunks=chunks)
        if not quality.is_valid:
            detail = "; ".join(quality.errors) or "Mini exam quality check failed"
            raise ValueError(detail)

        validated_content = content.model_copy(
            update={
                "quality_report": LearningContentQualityReport(
                    status=QualityStatus.passed,
                    score=quality.source_coverage_score or content.quality_report.score,
                    flags=quality.flags,
                    source_grounded=True,
                    reasons=["미니 점검 세트로 바로 풀 수 있게 준비됐다."],
                    action="save",
                )
            },
            deep=True,
        )
        saved = self.repository.create_many(user_id=user_id, contents=[self._attach_copy(validated_content)])
        self._publish_learning_contents(saved)
        return LearningContentGenerationResult(contents=saved, rejected=0, warnings=[])

    def _validate_retrieved_chunks(
        self,
        *,
        document_id: str,
        chunks: list[RetrievedChunk],
    ) -> None:
        if not chunks:
            raise ValueError("Search Agent returned no chunks")

        chunk_ids = [chunk.chunk_id for chunk in chunks]
        if len(set(chunk_ids)) != len(chunk_ids):
            raise SearchAgentError("Search Agent returned duplicate chunk ids")

        mismatched_document_ids = [chunk.chunk_id for chunk in chunks if chunk.document_id != document_id]
        if mismatched_document_ids:
            raise SearchAgentError(
                f"Search Agent returned chunks from a different document: {', '.join(mismatched_document_ids)}"
            )

    def _analyze_learning_material(
        self,
        *,
        document_id: str,
        concepts: list[str],
        count: int,
        difficulty: Difficulty,
        bloom_level: BloomLevel,
        user_requirements: str | None,
        chunks: list[RetrievedChunk],
    ) -> tuple[LearningTaskStrategyProfile, MaterialReadinessReport]:
        strategy_request = GenerateProblemRequest(
            document_id=document_id,
            concepts=concepts,
            type=ProblemType.short_answer,
            count=count,
            difficulty=difficulty,
            bloom_level=bloom_level,
            user_requirements=user_requirements,
        )
        strategy_profile = self.learning_task_router.route(request=strategy_request, chunks=chunks)
        material_readiness = self.material_readiness_analyzer.analyze(
            request=strategy_request,
            chunks=chunks,
            strategy_profile=strategy_profile,
        )
        return strategy_profile, material_readiness

    def _content_types_from_values(self, values: list[str]) -> list[LearningContentType]:
        content_types: list[LearningContentType] = []
        for value in values:
            try:
                content_types.append(LearningContentType(value))
            except ValueError:
                continue
        return list(dict.fromkeys(content_types))

    def _problem_options(
        self,
        *,
        request: RecommendLearningContentRequest,
        strategy_profile: LearningTaskStrategyProfile,
    ) -> list[ProblemRecommendationOption]:
        forms = set(strategy_profile.content_forms)
        options = [
            ProblemRecommendationOption(
                problem_type=ProblemType.multiple_choice,
                difficulty=request.difficulty,
                bloom_level=request.bloom_level,
                target_rigor=TargetRigor.standard,
                problem_style=ProblemStyle.concept_check,
                label="객관식 빠른 확인",
                reason="처음 학습할 때 부담 없이 핵심 개념을 확인하기 좋습니다.",
            ),
            ProblemRecommendationOption(
                problem_type=ProblemType.short_answer,
                difficulty=request.difficulty,
                bloom_level=BloomLevel.understand,
                target_rigor=TargetRigor.standard,
                problem_style=ProblemStyle.concept_check,
                label="주관식 개념 설명",
                reason="학생이 개념을 자기 말로 설명할 수 있는지 확인합니다.",
            ),
        ]
        if forms & {
            ContentForm.formula,
            ContentForm.concept_relation,
            ContentForm.procedure,
            ContentForm.case,
            ContentForm.data_table,
            ContentForm.graph,
            ContentForm.code,
            ContentForm.argument,
            ContentForm.passage,
        }:
            options.append(
                ProblemRecommendationOption(
                    problem_type=ProblemType.short_answer,
                    difficulty=Difficulty.hard,
                    bloom_level=BloomLevel.analyze,
                    target_rigor=TargetRigor.high,
                    problem_style=self._high_rigor_problem_style(forms=forms),
                    label="고난도 응용 주관식",
                    reason="자료에 관계, 절차, 수식, 근거 중 하나 이상이 있어 분석형 문제로 확장할 수 있습니다.",
                )
            )
        return options

    def _high_rigor_problem_style(self, *, forms: set[ContentForm]) -> ProblemStyle:
        if forms & {ContentForm.formula, ContentForm.data_table, ContentForm.graph}:
            return ProblemStyle.calculation_practice
        if forms & {ContentForm.argument, ContentForm.passage}:
            return ProblemStyle.evidence_analysis
        if ContentForm.code in forms:
            return ProblemStyle.error_detection
        return ProblemStyle.exam_application

    def _content_options(
        self,
        *,
        strategy_profile: LearningTaskStrategyProfile,
    ) -> list[LearningContentRecommendationOption]:
        recommended = set(strategy_profile.recommended_learning_content_types)
        available = set(strategy_profile.available_learning_content_types)
        options: list[LearningContentRecommendationOption] = []
        for content_type in self._content_types_from_values(strategy_profile.selectable_learning_content_types):
            value = content_type.value
            if value in recommended:
                level = "recommended"
            elif value in available:
                level = "available"
            else:
                level = "not_recommended"
            options.append(
                LearningContentRecommendationOption(
                    content_type=content_type,
                    label=self._content_type_label(content_type),
                    recommendation_level=level,
                    reason=self._content_type_reason(content_type=content_type, level=level),
                )
            )
        return options

    def _content_type_label(self, content_type: LearningContentType) -> str:
        labels = {
            LearningContentType.concept_summary_card: "핵심 정리 카드",
            LearningContentType.flashcard: "개념 카드",
            LearningContentType.true_false: "OX",
            LearningContentType.cloze: "빈칸",
            LearningContentType.matching: "매칭",
            LearningContentType.ordering: "순서 배열",
            LearningContentType.worked_example: "풀이 예시",
            LearningContentType.mini_exam: "미니 시험",
            LearningContentType.mistake_drill: "오답 맞춤 연습",
        }
        return labels[content_type]

    def _content_type_reason(self, *, content_type: LearningContentType, level: str) -> str:
        if level == "recommended":
            return "이 자료와 잘 맞아 먼저 추천합니다."
        if level == "available":
            return "자료와 자연스럽게 연결할 수 있는 추가 선택지입니다."
        reasons = {
            LearningContentType.ordering: "절차나 시간 흐름이 뚜렷할 때 더 잘 맞습니다.",
            LearningContentType.matching: "서로 연결할 용어와 설명 쌍이 충분할 때 더 좋습니다.",
            LearningContentType.mini_exam: "여러 개념이나 여러 자료 조각이 있을 때 더 좋습니다.",
        }
        return reasons.get(content_type, "이번 자료에서는 기본 추천보다 우선순위가 낮습니다.")

    def _mistake_drill_concepts(self, *, feedback: Feedback, seed_problem: Problem) -> list[str]:
        concepts = [
            *feedback.weak_concepts,
            *feedback.recommended_review,
            *seed_problem.concepts,
        ]
        cleaned = [concept.strip() for concept in concepts if concept and concept.strip()]
        return list(dict.fromkeys(cleaned))[:5]

    def _mistake_drill_problem_request(
        self,
        *,
        request: GenerateMistakeDrillRequest,
        feedback: Feedback,
        seed_problem: Problem,
        target_concepts: list[str],
        choice_diagnostic: dict | None,
    ) -> GenerateProblemRequest:
        problem_type = request.problem_type or ProblemType(seed_problem.type)
        difficulty = request.difficulty or seed_problem.difficulty
        bloom_level = request.bloom_level or seed_problem.bloom_level
        focus_instruction = self._mistake_drill_focus_instruction(
            feedback=feedback,
            choice_diagnostic=choice_diagnostic,
        )
        user_requirements = (
            "이전 오답과 같은 개념을 다른 조건이나 표현으로 다시 연습하게 해줘. "
            f"오답 유형: {feedback.mistake_type}. "
            f"피드백 요약: {feedback.summary}. "
            f"변형 전략: {request.variant_strategy}. "
            f"{focus_instruction}"
        )
        if request.user_requirements:
            user_requirements = f"{user_requirements} 사용자 요청: {request.user_requirements}"
        return GenerateProblemRequest(
            document_id=seed_problem.document_id,
            concepts=target_concepts or seed_problem.concepts,
            type=problem_type,
            count=request.count,
            difficulty=difficulty,
            bloom_level=bloom_level,
            user_requirements=user_requirements,
        )

    def _mistake_drill_choice_diagnostic(self, *, feedback: Feedback, seed_problem: Problem) -> dict | None:
        if seed_problem.type != ProblemType.multiple_choice.value:
            return None
        submission = feedback.submission
        if submission is None:
            return None
        return self.feedback_agent.multiple_choice_diagnostic_payload(
            problem=seed_problem,
            submission=submission,
        )

    def _mistake_drill_focus_instruction(self, *, feedback: Feedback, choice_diagnostic: dict | None) -> str:
        strategy_by_mistake_type = {
            "calculation_error": "이번에는 수치나 단위를 바꿔 같은 공식 대입을 다시 확인하게 하라.",
            "unit_error": "이번에는 최종 단위 확인을 따로 요구하라.",
            "term_confusion": "이번에는 비슷한 용어를 비교하게 하라.",
            "misread_question": "이번에는 조건을 먼저 표시하고 답하게 하라.",
            "logic_error": "이번에는 원인과 결과 또는 단계 순서를 바꿔 묻지 않도록 주의하게 하라.",
            "missing_key_concept": "이번에는 빠뜨린 핵심 개념을 답안에 반드시 포함하게 하라.",
            "incomplete_answer": "이번에는 결론뿐 아니라 이유까지 쓰게 하라.",
            "concept_misunderstanding": "이번에는 같은 개념을 새 조건에 적용하게 하라.",
        }
        base_strategy = strategy_by_mistake_type.get(
            str(feedback.mistake_type or ""),
            "이번에는 같은 개념을 다른 조건에서 다시 확인하게 하라.",
        )
        if not choice_diagnostic:
            return base_strategy
        misconception = choice_diagnostic.get("misconception") or ""
        repair_strategy = choice_diagnostic.get("repair_strategy") or ""
        selected_choice_text = choice_diagnostic.get("selected_choice_text") or ""
        details = []
        if selected_choice_text:
            details.append(f"이전 선택 보기: {selected_choice_text}")
        if misconception:
            details.append(f"헷갈린 지점: {misconception}")
        if repair_strategy:
            details.append(f"다시 연습할 방향: {repair_strategy}")
        return " ".join([base_strategy, *details]).strip()

    def _mistake_drill_payload_focus(self, choice_diagnostic: dict | None) -> dict:
        if not choice_diagnostic:
            return {}
        return {
            "variant_focus": choice_diagnostic.get("repair_strategy"),
            "selected_choice_id": choice_diagnostic.get("selected_choice_id"),
            "selected_choice_text": choice_diagnostic.get("selected_choice_text"),
            "misconception": choice_diagnostic.get("misconception"),
            "repair_strategy": choice_diagnostic.get("repair_strategy"),
        }


    def _attach_remediation_events(
        self,
        *,
        user_id: str,
        feedback: Feedback,
        seed_problem: Problem,
        contents_with_problems: list[tuple[LearningContentBase, Problem]],
    ) -> list[LearningContentBase]:
        if self.remediation_repository is None:
            return [content for content, _problem in contents_with_problems]

        prepared: list[LearningContentBase] = []
        try:
            for content, generated_problem in contents_with_problems:
                event = self.remediation_repository.create(
                    {
                        "user_id": user_id,
                        "source_feedback_id": feedback.id,
                        "source_problem_id": seed_problem.id,
                        "followup_problem_id": generated_problem.id,
                        "target_concepts": content.concepts,
                        "target_mistake_type": feedback.mistake_type,
                    }
                )
                prepared.append(
                    content.model_copy(
                        update={
                            "payload": {
                                **content.payload,
                                "remediation_event_id": event.id,
                            }
                        },
                        deep=True,
                    )
                )
            return prepared
        except Exception:
            self.remediation_repository.rollback()
            raise

    def _link_remediation_events_to_saved_contents(self, contents: list[LearningContentBase]) -> None:
        if self.remediation_repository is None:
            return
        try:
            for content in contents:
                event_id = content.payload.get("remediation_event_id")
                if event_id and content.id:
                    self.remediation_repository.set_followup_content_id(
                        event_id=event_id,
                        followup_content_id=content.id,
                    )
            self.remediation_repository.commit()
        except Exception:
            self.remediation_repository.rollback()
            raise

    def _problem_points(self, problem: Problem) -> float:
        if problem.type == ProblemType.short_answer.value:
            rubric = problem.rubric or []
            points = sum(float(item.get("points", 0)) for item in rubric if isinstance(item, dict))
            return points or 1.0
        return 1.0

    def _attach_copy(self, content: LearningContentBase) -> LearningContentBase:
        return content.model_copy(
            update={"display_copy": self.voice_renderer.render_learning_content_copy(content)},
            deep=True,
        )

    def _publish_learning_contents(self, contents: list[LearningContentBase]) -> None:
        for content in contents:
            self.artifact_publisher.publish_learning_content(content)
