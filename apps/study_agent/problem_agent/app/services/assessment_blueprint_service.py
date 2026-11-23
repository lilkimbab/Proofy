from __future__ import annotations

from app.schemas.problems import GenerateProblemRequest
from app.schemas.quality import (
    AssessmentBlueprint,
    BlueprintCell,
    CognitiveOperation,
    LearningTaskStrategyProfile,
    MaterialReadinessReport,
    ProblemStrategy,
    ReadinessLevel,
    TargetRigor,
)


class AssessmentBlueprintPlanner:
    """Builds a small generation blueprint before the LLM is called."""

    def plan(
        self,
        *,
        request: GenerateProblemRequest,
        strategy_profile: LearningTaskStrategyProfile,
        material_readiness: MaterialReadinessReport,
    ) -> AssessmentBlueprint:
        distribution = self._distribution(
            request=request,
            strategy_profile=strategy_profile,
            material_readiness=material_readiness,
        )
        warnings = self._warnings(request=request, material_readiness=material_readiness)
        return AssessmentBlueprint(
            goal=request.goal,
            course_level=request.course_level,
            target_rigor=request.target_rigor,
            total_count=request.count,
            distribution=distribution,
            warnings=warnings,
        )

    def _distribution(
        self,
        *,
        request: GenerateProblemRequest,
        strategy_profile: LearningTaskStrategyProfile,
        material_readiness: MaterialReadinessReport,
    ) -> list[BlueprintCell]:
        concept_count = len(request.concepts)
        base = request.count // concept_count
        remainder = request.count % concept_count
        cells: list[BlueprintCell] = []
        for index, concept in enumerate(request.concepts):
            count = base + (1 if index < remainder else 0)
            if count <= 0:
                continue
            strategies = self._strategies_for_cell(
                request=request,
                strategy_profile=strategy_profile,
                material_readiness=material_readiness,
            )
            cells.append(
                BlueprintCell(
                    concept=concept,
                    problem_type=request.type.value,
                    bloom_level=self._bloom_level(request=request, strategy_profile=strategy_profile),
                    count=count,
                    points=4 if request.type.value == "short_answer" else 1,
                    strategies=strategies,
                    required_evidence=self._required_evidence(strategies=strategies),
                )
            )
        return cells

    def _strategies_for_cell(
        self,
        *,
        request: GenerateProblemRequest,
        strategy_profile: LearningTaskStrategyProfile,
        material_readiness: MaterialReadinessReport,
    ) -> list[ProblemStrategy]:
        candidates = [
            strategy
            for strategy in strategy_profile.recommended_strategies
            if strategy in material_readiness.can_generate
        ]
        if not candidates:
            candidates = [ProblemStrategy.basic_concept_check, ProblemStrategy.general_explanation]
        if request.target_rigor == TargetRigor.high and ProblemStrategy.near_transfer_application in material_readiness.can_generate:
            candidates.insert(0, ProblemStrategy.near_transfer_application)
        return list(dict.fromkeys(candidates[:3]))

    def _bloom_level(
        self,
        *,
        request: GenerateProblemRequest,
        strategy_profile: LearningTaskStrategyProfile,
    ) -> str:
        if request.target_rigor == TargetRigor.high and CognitiveOperation.analyze in strategy_profile.cognitive_operations:
            return "analyze"
        if request.target_rigor in {TargetRigor.standard, TargetRigor.high} and (
            CognitiveOperation.apply in strategy_profile.cognitive_operations
        ):
            return "apply"
        return request.bloom_level.value

    def _required_evidence(self, *, strategies: list[ProblemStrategy]) -> list[str]:
        evidence = ["source_chunk_ids"]
        if ProblemStrategy.near_transfer_application in strategies:
            evidence.append("자료 속 관계/공식/조건을 바꾼 응용 근거")
        if ProblemStrategy.calculation in strategies or ProblemStrategy.formula_application in strategies:
            evidence.append("계산에 필요한 공식 또는 변수 관계")
        if ProblemStrategy.passage_evidence in strategies:
            evidence.append("지문 내 직접 근거 문장")
        return evidence

    def _warnings(
        self,
        *,
        request: GenerateProblemRequest,
        material_readiness: MaterialReadinessReport,
    ) -> list[str]:
        warnings: list[str] = []
        if material_readiness.level == ReadinessLevel.insufficient:
            warnings.append("현재 검색 근거로는 요청한 수준의 문제를 안정적으로 만들기 어렵다.")
        elif material_readiness.level == ReadinessLevel.limited and request.target_rigor == TargetRigor.high:
            warnings.append("자료 근거가 제한적이므로 고난도보다는 근거리 응용 중심으로 생성한다.")
        warnings.extend(material_readiness.recommended_uploads[:1])
        return list(dict.fromkeys(warnings))
