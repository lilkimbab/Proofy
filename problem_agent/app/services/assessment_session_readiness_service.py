from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import UserConceptStat
from app.schemas.integration_contracts import RetrievedChunk
from app.schemas.problems import GenerateProblemRequest
from app.schemas.quality import (
    AssessmentSessionReadinessReport,
    AssessmentReadinessStatus,
    AssessmentSessionCoverageReport,
    GenerationGoal,
    LearningTaskStrategyProfile,
    MaterialReadinessReport,
    ReadinessLevel,
    TargetRigor,
)
from app.services.assessment_blueprint_service import AssessmentBlueprintPlanner
from app.services.learning_task_strategy_router import LearningTaskStrategyRouter
from app.services.material_readiness_service import MaterialReadinessAnalyzer
from app.services.request_safety import validate_safe_user_requirements
from app.services.search_service import SearchService


class AssessmentSessionReadinessService:
    """Decides whether a full problem set should be diagnostic, personalized, or exam-like."""

    MIN_PERSONALIZATION_ATTEMPTS = 5
    MIN_RELIABLE_ATTEMPTS = 8

    def __init__(
        self,
        *,
        db: Session,
        search_service: SearchService,
        learning_task_router: LearningTaskStrategyRouter | None = None,
        material_readiness_analyzer: MaterialReadinessAnalyzer | None = None,
        blueprint_planner: AssessmentBlueprintPlanner | None = None,
    ):
        self.db = db
        self.search_service = search_service
        self.learning_task_router = learning_task_router or LearningTaskStrategyRouter()
        self.material_readiness_analyzer = material_readiness_analyzer or MaterialReadinessAnalyzer()
        self.blueprint_planner = blueprint_planner or AssessmentBlueprintPlanner()

    def evaluate(
        self,
        *,
        user_id: str,
        request: GenerateProblemRequest,
    ) -> AssessmentSessionReadinessReport:
        validate_safe_user_requirements(
            request.user_requirements,
            error_message="unsafe assessment session request",
        )
        chunks = self.search_service.search_chunks(
            document_id=request.document_id,
            concepts=request.concepts,
            difficulty=request.difficulty.value,
            query=" ".join(request.concepts),
            top_k=10 if request.target_rigor == TargetRigor.high or request.goal == GenerationGoal.exam_prep else 6,
        )
        blocking_reasons = self._chunk_blocking_reasons(request=request, chunks=chunks)
        if blocking_reasons:
            return self._not_ready_report(request=request, blocking_reasons=blocking_reasons)

        strategy_profile = self.learning_task_router.route(request=request, chunks=chunks)
        material_readiness = self.material_readiness_analyzer.analyze(
            request=request,
            chunks=chunks,
            strategy_profile=strategy_profile,
        )
        stats = self._stats_for_concepts(user_id=user_id, concepts=request.concepts)
        total_attempts = sum(stat.attempts for stat in stats)
        weak_concepts = self._weak_concepts(stats=stats, request=request)
        covered_concepts = self._covered_concepts(request=request, chunks=chunks, stats=stats)
        learner_history_score = self._learner_history_score(
            request=request,
            stats=stats,
            total_attempts=total_attempts,
        )
        material_score = material_readiness.score
        quality_gate_score = self._quality_gate_score(material_readiness=material_readiness)
        score = round(material_score * 0.50 + learner_history_score * 0.25 + quality_gate_score * 0.25, 3)

        can_source_based = True
        can_personalized = can_source_based and (
            total_attempts >= self.MIN_PERSONALIZATION_ATTEMPTS or bool(weak_concepts)
        )
        can_exam = can_source_based and self._has_exam_or_high_rigor_intent(request)
        status = self._status(
            can_personalized=can_personalized,
            can_exam=can_exam,
        )
        recommended_blueprint = self.blueprint_planner.plan(
            request=self._blueprint_request(
                request=request,
                status=status,
                weak_concepts=weak_concepts,
            ),
            strategy_profile=strategy_profile,
            material_readiness=material_readiness,
        )
        coverage_report = self._coverage_report(
            request=request,
            chunks=chunks,
            weak_concepts=weak_concepts,
            recommended_blueprint=recommended_blueprint,
        )

        return AssessmentSessionReadinessReport(
            status=status,
            score=score,
            material_score=material_score,
            learner_history_score=learner_history_score,
            quality_gate_score=quality_gate_score,
            total_attempts=total_attempts,
            covered_concepts=covered_concepts,
            weak_concepts=weak_concepts,
            can_generate_source_based_set=can_source_based,
            can_generate_personalized_set=can_personalized,
            can_generate_exam_set=can_exam,
            recommended_blueprint=recommended_blueprint,
            coverage_report=coverage_report,
            recommended_next_step=self._recommended_next_step(
                status=status,
                material_readiness=material_readiness,
                total_attempts=total_attempts,
            ),
            reasons=self._reasons(
                material_readiness=material_readiness,
                strategy_profile=strategy_profile,
                total_attempts=total_attempts,
                weak_concepts=weak_concepts,
            ),
            blocking_reasons=[],
            warnings=self._warnings(
                material_readiness=material_readiness,
                total_attempts=total_attempts,
                can_exam=can_exam,
                request=request,
            ),
        )

    def _chunk_blocking_reasons(
        self,
        *,
        request: GenerateProblemRequest,
        chunks: list[RetrievedChunk],
    ) -> list[str]:
        if not chunks:
            return ["검색된 자료 근거가 없어 문제 세트 기준을 판단할 수 없다."]
        chunk_ids = [chunk.chunk_id for chunk in chunks]
        reasons: list[str] = []
        if len(chunk_ids) != len(set(chunk_ids)):
            reasons.append("검색 결과에 중복 chunk가 포함되어 있다.")
        wrong_document_chunks = [chunk.chunk_id for chunk in chunks if chunk.document_id != request.document_id]
        if wrong_document_chunks:
            reasons.append("다른 문서의 chunk가 섞여 있어 세트 생성 기준으로 쓰기 어렵다.")
        return reasons

    def _not_ready_report(
        self,
        *,
        request: GenerateProblemRequest,
        blocking_reasons: list[str],
    ) -> AssessmentSessionReadinessReport:
        return AssessmentSessionReadinessReport(
            status=AssessmentReadinessStatus.not_ready,
            score=0.0,
            material_score=0.0,
            learner_history_score=0.0,
            quality_gate_score=0.0,
            total_attempts=0,
            covered_concepts=[],
            weak_concepts=[],
            can_generate_source_based_set=False,
            can_generate_personalized_set=False,
            can_generate_exam_set=False,
            recommended_next_step="자료를 조금 더 넣은 뒤, 먼저 짧은 진단 문제부터 만드는 편이 좋아요.",
            reasons=[f"요청 개념: {', '.join(request.concepts)}"],
            blocking_reasons=blocking_reasons,
            warnings=[],
        )

    def _coverage_report(
        self,
        *,
        request: GenerateProblemRequest,
        chunks: list[RetrievedChunk],
        weak_concepts: list[str],
        recommended_blueprint,
    ) -> AssessmentSessionCoverageReport:
        requested_concepts = [concept.strip() for concept in request.concepts if concept.strip()]
        source_covered_concepts = [
            concept for concept in requested_concepts if self._concept_has_source_evidence(concept=concept, chunks=chunks)
        ]
        source_missing_concepts = [concept for concept in requested_concepts if concept not in source_covered_concepts]
        weak_or_missing_concepts = list(dict.fromkeys([*weak_concepts, *source_missing_concepts]))
        coverage_ratio = round(len(source_covered_concepts) / max(len(requested_concepts), 1), 3)
        warnings: list[str] = []
        if source_missing_concepts:
            warnings.append("일부 요청 개념은 검색된 자료 근거가 약해 세트에서 낮은 비중으로 다뤄야 한다.")
        if weak_concepts:
            warnings.append("반복 오답 또는 낮은 숙련도 개념은 세트 앞부분에 배치하는 편이 좋다.")
        return AssessmentSessionCoverageReport(
            requested_concepts=requested_concepts,
            source_covered_concepts=source_covered_concepts,
            weak_or_missing_concepts=weak_or_missing_concepts,
            coverage_ratio=coverage_ratio,
            difficulty_distribution={request.difficulty.value: recommended_blueprint.total_count},
            problem_type_distribution=self._count_by_blueprint_field(recommended_blueprint, "problem_type"),
            bloom_distribution=self._count_by_blueprint_field(recommended_blueprint, "bloom_level"),
            estimated_time_minutes=self._estimated_time_minutes(
                blueprint=recommended_blueprint,
                difficulty=request.difficulty.value,
            ),
            includes_multi_concept_items=bool(
                len(requested_concepts) >= 2
                and (request.goal == GenerationGoal.exam_prep or request.target_rigor == TargetRigor.high)
            ),
            warnings=warnings,
        )

    def _concept_has_source_evidence(self, *, concept: str, chunks: list[RetrievedChunk]) -> bool:
        normalized_concept = concept.casefold()
        for chunk in chunks:
            chunk_concepts = [chunk_concept.casefold() for chunk_concept in chunk.concepts]
            if normalized_concept in chunk_concepts:
                return True
            if normalized_concept and normalized_concept in chunk.content.casefold():
                return True
        return False

    def _count_by_blueprint_field(self, blueprint, field_name: str) -> dict[str, int]:
        counts: dict[str, int] = {}
        for cell in blueprint.distribution:
            key = str(getattr(cell, field_name))
            counts[key] = counts.get(key, 0) + cell.count
        return counts

    def _estimated_time_minutes(self, *, blueprint, difficulty: str) -> int:
        total_minutes = 0.0
        for cell in blueprint.distribution:
            per_item_minutes = 2.0 if cell.problem_type == "multiple_choice" else 5.0
            if difficulty == "hard" or cell.bloom_level in {"analyze", "evaluate", "create"}:
                per_item_minutes += 1.0
            total_minutes += per_item_minutes * cell.count
        return max(1, round(total_minutes))

    def _stats_for_concepts(self, *, user_id: str, concepts: list[str]) -> list[UserConceptStat]:
        cleaned = [concept.strip() for concept in concepts if concept.strip()]
        if not cleaned:
            return []
        return (
            self.db.query(UserConceptStat)
            .filter(UserConceptStat.user_id == user_id)
            .filter(UserConceptStat.concept.in_(cleaned))
            .all()
        )

    def _weak_concepts(
        self,
        *,
        stats: list[UserConceptStat],
        request: GenerateProblemRequest,
    ) -> list[str]:
        weak = [
            stat.concept
            for stat in stats
            if stat.wrong_count >= 2 or (stat.attempts >= 2 and stat.mastery < 0.55)
        ]
        if request.goal == GenerationGoal.weak_concept_repair and not weak:
            return request.concepts[:3]
        return list(dict.fromkeys(weak))[:5]

    def _covered_concepts(
        self,
        *,
        request: GenerateProblemRequest,
        chunks: list[RetrievedChunk],
        stats: list[UserConceptStat],
    ) -> list[str]:
        chunk_concepts = [concept for chunk in chunks for concept in chunk.concepts]
        stat_concepts = [stat.concept for stat in stats]
        return list(dict.fromkeys([*request.concepts, *chunk_concepts, *stat_concepts]))[:20]

    def _learner_history_score(
        self,
        *,
        request: GenerateProblemRequest,
        stats: list[UserConceptStat],
        total_attempts: int,
    ) -> float:
        attempts_score = min(total_attempts / self.MIN_RELIABLE_ATTEMPTS, 1.0) * 0.65
        concept_score = min(len(stats) / max(len(request.concepts), 1), 1.0) * 0.35
        return round(attempts_score + concept_score, 3)

    def _quality_gate_score(self, *, material_readiness: MaterialReadinessReport) -> float:
        if material_readiness.level == ReadinessLevel.sufficient:
            return min(material_readiness.score + 0.12, 1.0)
        if material_readiness.level == ReadinessLevel.limited:
            return min(material_readiness.score + 0.04, 1.0)
        return material_readiness.score * 0.5

    def _status(
        self,
        *,
        can_personalized: bool,
        can_exam: bool,
    ) -> AssessmentReadinessStatus:
        if can_exam:
            return AssessmentReadinessStatus.exam_ready
        if can_personalized:
            return AssessmentReadinessStatus.personalized_ready
        return AssessmentReadinessStatus.diagnostic_ready

    def _has_exam_or_high_rigor_intent(self, request: GenerateProblemRequest) -> bool:
        if request.goal == GenerationGoal.exam_prep or request.target_rigor == TargetRigor.high:
            return True
        requirements = (request.user_requirements or "").lower()
        cues = (
            "시험",
            "고난도",
            "심화",
            "응용",
            "예상",
            "대비",
            "수능",
            "대학",
            "복합",
            "다단계",
            "계산",
            "수식",
            "advanced",
            "exam",
        )
        return any(cue in requirements for cue in cues)

    def _recommended_next_step(
        self,
        *,
        status: AssessmentReadinessStatus,
        material_readiness: MaterialReadinessReport,
        total_attempts: int,
    ) -> str:
        if status == AssessmentReadinessStatus.not_ready:
            return "자료 근거를 더 넣고, 너무 어려운 세트보다는 기본 확인 문제부터 시작하는 편이 좋아요."
        if status == AssessmentReadinessStatus.diagnostic_ready:
            return "아직 풀이 기록이 적으니 3~5문제 진단 세트로 약한 부분을 먼저 찾는 게 좋아요."
        if status == AssessmentReadinessStatus.personalized_ready:
            return "풀이 기록을 바탕으로 약한 개념을 섞은 개인 맞춤 세트를 만들 수 있어요."
        if material_readiness.level == ReadinessLevel.sufficient:
            return "자료 근거와 풀이 기록이 충분해서 시험 대비 세트로 구성해도 좋아요."
        return "자료가 많지는 않아도, 있는 근거 안에서 만들 수 있는 가장 높은 수준의 응용 문제로 구성할 수 있어요."

    def _reasons(
        self,
        *,
        material_readiness: MaterialReadinessReport,
        strategy_profile: LearningTaskStrategyProfile,
        total_attempts: int,
        weak_concepts: list[str],
    ) -> list[str]:
        reasons = [
            f"자료 준비도는 {material_readiness.level.value} 수준이다.",
            f"현재 관련 풀이 기록은 {total_attempts}회다.",
            f"판단된 자료 형태: {', '.join(form.value for form in strategy_profile.content_forms)}",
        ]
        if weak_concepts:
            reasons.append("반복 오답 또는 낮은 숙련도로 보이는 개념이 있다: " + ", ".join(weak_concepts))
        else:
            reasons.append("아직 세트 구성에 쓸 만한 약점 기록은 많지 않다.")
        return reasons

    def _warnings(
        self,
        *,
        material_readiness: MaterialReadinessReport,
        total_attempts: int,
        can_exam: bool,
        request: GenerateProblemRequest,
    ) -> list[str]:
        warnings = list(material_readiness.recommended_uploads[:2])
        if total_attempts < self.MIN_PERSONALIZATION_ATTEMPTS:
            warnings.append("풀이 기록이 적어서 개인 맞춤 근거는 약하지만, 자료 기반 고난도 세트 생성은 가능하다.")
        if can_exam and material_readiness.level != ReadinessLevel.sufficient:
            warnings.append("자료가 제한적이므로 외부 사실을 추가하지 않고, 근거 안에서 응용 맥락만 바꿔 출제한다.")
        if request.goal == GenerationGoal.exam_prep and not can_exam:
            warnings.append("시험 대비 세트 의도가 명확하지 않아 기본 진단 세트로 판단했다.")
        return list(dict.fromkeys(warnings))

    def _blueprint_request(
        self,
        *,
        request: GenerateProblemRequest,
        status: AssessmentReadinessStatus,
        weak_concepts: list[str],
    ) -> GenerateProblemRequest:
        update: dict = {}
        if status == AssessmentReadinessStatus.diagnostic_ready:
            update["count"] = min(max(request.count, 3), 5)
        if status == AssessmentReadinessStatus.personalized_ready and weak_concepts:
            update["concepts"] = list(dict.fromkeys([*weak_concepts, *request.concepts]))[:8]
        if status == AssessmentReadinessStatus.exam_ready:
            update["target_rigor"] = TargetRigor.high
            update["goal"] = GenerationGoal.exam_prep
        if not update:
            return request
        return request.model_copy(update=update)
