from __future__ import annotations

from app.schemas.integration_contracts import RetrievedChunk
from app.schemas.problems import BloomLevel, Difficulty, GenerateProblemRequest, ProblemDepth
from app.schemas.quality import (
    CognitiveOperation,
    CourseLevel,
    GenerationGoal,
    HighRigorGenerationProfile,
    HighRigorIntensity,
    LearningTaskStrategyProfile,
    MaterialReadinessReport,
    ReadinessLevel,
    TargetRigor,
    VerificationLevel,
)


class AdaptiveHighRigorPlanner:
    """Infer high-rigor generation needs from natural-language requests.

    Users should not have to pick a separate "elite exam" mode. This planner
    reads broad intent signals such as assessment setting, difficulty,
    multi-step reasoning, and concept integration, then converts them into
    internal search/candidate/verification settings.
    """

    def plan(
        self,
        *,
        request: GenerateProblemRequest,
        chunks: list[RetrievedChunk] | None = None,
        strategy_profile: LearningTaskStrategyProfile | None = None,
        material_readiness: MaterialReadinessReport | None = None,
    ) -> HighRigorGenerationProfile:
        signals = self._signals(request=request, chunks=chunks or [], strategy_profile=strategy_profile)
        request_signals = self._signals(request=request, chunks=[], strategy_profile=None)
        explicit_elite = any(signal in signals for signal in {"최상위 난도", "긴 풀이"})
        high_intent_signals = {
            "최상위 난도",
            "복합 개념",
            "다단계",
            "긴 풀이",
            "평가 대비",
        }
        has_high_intent_signal = bool(request_signals & high_intent_signals)
        high_request = (
            request.goal == GenerationGoal.exam_prep
            or request.target_rigor == TargetRigor.high
            or request.difficulty == Difficulty.hard
            or request.depth == ProblemDepth.deep
            or has_high_intent_signal
        )

        if not high_request:
            return HighRigorGenerationProfile(
                enabled=False,
                recommended_top_k=6,
                candidate_multiplier=1,
                reason="일반 연습 요청으로 판단했다.",
            )

        multi_concept_required = self._multi_concept_required(
            request=request,
            signals=signals,
            chunks=chunks or [],
            strategy_profile=strategy_profile,
        )
        multi_step_required = self._multi_step_required(
            request=request,
            signals=signals,
            strategy_profile=strategy_profile,
        )
        intensity = self._intensity(
            request=request,
            signals=signals,
            explicit_elite=explicit_elite,
            multi_concept_required=multi_concept_required,
            multi_step_required=multi_step_required,
        )
        verification_level = self._verification_level(
            request=request,
            intensity=intensity,
            material_readiness=material_readiness,
        )
        recommended_top_k = self._recommended_top_k(
            intensity=intensity,
            multi_concept_required=multi_concept_required,
            broad_search_required=True,
        )
        candidate_multiplier = {
            HighRigorIntensity.standard: 2,
            HighRigorIntensity.advanced: 3,
            HighRigorIntensity.elite: 4,
        }[intensity]

        return HighRigorGenerationProfile(
            enabled=True,
            intensity=intensity,
            multi_concept_required=multi_concept_required,
            multi_step_required=multi_step_required,
            broad_search_required=True,
            solution_depth="multi_step" if multi_step_required else "application",
            verification_level=verification_level,
            estimated_solve_time_minutes=self._estimated_solve_time_minutes(intensity),
            recommended_top_k=recommended_top_k,
            candidate_multiplier=candidate_multiplier,
            signals=sorted(signals),
            reason=self._reason(
                intensity=intensity,
                multi_concept_required=multi_concept_required,
                multi_step_required=multi_step_required,
                signals=signals,
            ),
        )

    def _signals(
        self,
        *,
        request: GenerateProblemRequest,
        chunks: list[RetrievedChunk],
        strategy_profile: LearningTaskStrategyProfile | None,
    ) -> set[str]:
        text = " ".join(
            [
                request.user_requirements or "",
                " ".join(request.concepts),
                " ".join(chunk.content for chunk in chunks[:4]),
            ]
        ).lower()
        signals: set[str] = set()

        signal_patterns = {
            "최상위 난도": (
                "고난도",
                "최상위",
                "최고난도",
                "매우 어렵",
                "어렵",
                "난도 높",
                "난이도 높",
                "변별",
                "상위권",
            ),
            "복합 개념": ("여러 개념", "개념 혼합", "복합 개념", "섞어서", "융합", "연결", "엮"),
            "다단계": ("여러 단계", "다단계", "단계", "풀이 과정", "긴 풀이", "차근"),
            "긴 풀이": ("많은 시간", "사고력", "오래 걸리", "오래 생각", "시간이 걸리"),
            "평가 대비": ("시험", "고사", "평가", "예상 문제", "예상", "출제", "나올 만", "나올법", "대비", "실전"),
            "심화 응용": ("심화", "심층", "응용", "적용", "분석", "비교", "판단", "추론", "평가", "설계", "전공"),
            "정량/논증": ("계산", "수식", "공식", "증명", "유도", "논증", "근거"),
            "확장 설계": ("확장", "새 상황", "새 사례", "새 구조", "새 규칙", "새 기준", "설계"),
        }
        for signal, patterns in signal_patterns.items():
            if any(pattern in text for pattern in patterns):
                signals.add(signal)

        if strategy_profile is not None:
            if len(strategy_profile.core_keywords) >= 3:
                signals.add("복합 개념")
            if any(
                operation in strategy_profile.cognitive_operations
                for operation in {CognitiveOperation.analyze, CognitiveOperation.evaluate, CognitiveOperation.design}
            ):
                signals.add("다단계")

        return signals

    def _multi_concept_required(
        self,
        *,
        request: GenerateProblemRequest,
        signals: set[str],
        chunks: list[RetrievedChunk],
        strategy_profile: LearningTaskStrategyProfile | None,
    ) -> bool:
        chunk_concepts = {
            concept.strip()
            for chunk in chunks
            for concept in chunk.concepts
            if concept.strip()
        }
        return (
            "복합 개념" in signals
            or len(request.concepts) >= 2
            or len(chunk_concepts) >= 3
            or bool(strategy_profile and len(strategy_profile.core_keywords) >= 3)
        )

    def _multi_step_required(
        self,
        *,
        request: GenerateProblemRequest,
        signals: set[str],
        strategy_profile: LearningTaskStrategyProfile | None,
    ) -> bool:
        return (
            "다단계" in signals
            or "긴 풀이" in signals
            or "최상위 난도" in signals
            or "정량/논증" in signals
            or "확장 설계" in signals
            or request.depth == ProblemDepth.deep
            or request.bloom_level in {BloomLevel.analyze, BloomLevel.evaluate, BloomLevel.create}
            or bool(
                strategy_profile
                and any(
                    operation in strategy_profile.cognitive_operations
                    for operation in {CognitiveOperation.calculate, CognitiveOperation.analyze, CognitiveOperation.evaluate}
                )
            )
        )

    def _intensity(
        self,
        *,
        request: GenerateProblemRequest,
        signals: set[str],
        explicit_elite: bool,
        multi_concept_required: bool,
        multi_step_required: bool,
    ) -> HighRigorIntensity:
        if explicit_elite or (
            request.course_level in {CourseLevel.university, CourseLevel.professional}
            and multi_concept_required
            and multi_step_required
        ):
            return HighRigorIntensity.elite
        if (
            request.target_rigor == TargetRigor.high
            or request.depth == ProblemDepth.deep
            or request.difficulty == Difficulty.hard
            or len(signals) >= 2
        ):
            return HighRigorIntensity.advanced
        return HighRigorIntensity.standard

    def _verification_level(
        self,
        *,
        request: GenerateProblemRequest,
        intensity: HighRigorIntensity,
        material_readiness: MaterialReadinessReport | None,
    ) -> VerificationLevel:
        if intensity == HighRigorIntensity.elite:
            return VerificationLevel.strict
        if material_readiness is not None and material_readiness.level == ReadinessLevel.limited:
            return VerificationLevel.strict
        if request.quality_mode.value == "strict" or intensity == HighRigorIntensity.advanced:
            return VerificationLevel.enhanced
        return VerificationLevel.standard

    def _recommended_top_k(
        self,
        *,
        intensity: HighRigorIntensity,
        multi_concept_required: bool,
        broad_search_required: bool,
    ) -> int:
        if intensity == HighRigorIntensity.elite:
            return 14 if multi_concept_required else 12
        if intensity == HighRigorIntensity.advanced:
            return 10 if broad_search_required else 8
        return 8

    def _estimated_solve_time_minutes(self, intensity: HighRigorIntensity) -> int:
        if intensity == HighRigorIntensity.elite:
            return 20
        if intensity == HighRigorIntensity.advanced:
            return 10
        return 5

    def _reason(
        self,
        *,
        intensity: HighRigorIntensity,
        multi_concept_required: bool,
        multi_step_required: bool,
        signals: set[str],
    ) -> str:
        parts = [f"{intensity.value} 난도 요청으로 판단했다."]
        if multi_concept_required:
            parts.append("여러 개념을 함께 다루도록 검색 범위를 넓힌다.")
        if multi_step_required:
            parts.append("풀이가 여러 단계로 나뉘도록 생성과 검증을 강화한다.")
        if signals:
            parts.append("감지한 신호: " + ", ".join(sorted(signals)))
        return " ".join(parts)
