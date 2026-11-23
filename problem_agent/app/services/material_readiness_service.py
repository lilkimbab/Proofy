from __future__ import annotations

from app.schemas.integration_contracts import RetrievedChunk
from app.schemas.problems import GenerateProblemRequest
from app.schemas.quality import (
    ContentForm,
    LearningTaskStrategyProfile,
    MaterialReadinessReport,
    ProblemStrategy,
    ReadinessLevel,
    TargetRigor,
)


class MaterialReadinessAnalyzer:
    """Estimates which problem strategies are supported by retrieved chunks."""

    def analyze(
        self,
        *,
        request: GenerateProblemRequest,
        chunks: list[RetrievedChunk],
        strategy_profile: LearningTaskStrategyProfile,
    ) -> MaterialReadinessReport:
        total_chars = sum(len(chunk.content) for chunk in chunks)
        distinct_concepts = {concept for chunk in chunks for concept in chunk.concepts} | set(request.concepts)
        forms = set(strategy_profile.content_forms)

        volume_score = min(total_chars / 1200, 1.0) * 0.20
        concept_score = min(len(distinct_concepts) / 4, 1.0) * 0.20
        evidence_score = self._evidence_score(forms=forms) * 0.35
        structure_score = self._structure_score(chunks=chunks) * 0.15
        level_score = self._level_score(request=request, forms=forms) * 0.10
        score = min(volume_score + concept_score + evidence_score + structure_score + level_score, 1.0)

        can_generate = self._can_generate(forms=forms)
        risky_generations = self._risky_generations(forms=forms, request=request)
        reasons = self._reasons(
            total_chars=total_chars,
            distinct_concept_count=len(distinct_concepts),
            forms=forms,
            score=score,
        )
        recommended_uploads = self._recommended_uploads(forms=forms, request=request)
        level = self._level(score=score, can_generate=can_generate, request=request)

        return MaterialReadinessReport(
            score=round(score, 3),
            level=level,
            reasons=reasons,
            can_generate=can_generate,
            risky_generations=risky_generations,
            recommended_uploads=recommended_uploads,
        )

    def _evidence_score(self, *, forms: set[ContentForm]) -> float:
        score = 0.15
        if ContentForm.definition in forms:
            score += 0.15
        if ContentForm.formula in forms:
            score += 0.25
        if ContentForm.concept_relation in forms:
            score += 0.25
        if ContentForm.procedure in forms:
            score += 0.20
        if ContentForm.case in forms:
            score += 0.20
        if ContentForm.passage in forms or ContentForm.argument in forms:
            score += 0.20
        if ContentForm.code in forms:
            score += 0.25
        return min(score, 1.0)

    def _structure_score(self, *, chunks: list[RetrievedChunk]) -> float:
        if not chunks:
            return 0
        titled = sum(1 for chunk in chunks if chunk.section_title)
        paged = sum(1 for chunk in chunks if chunk.page is not None)
        return ((titled / len(chunks)) + (paged / len(chunks))) / 2

    def _level_score(self, *, request: GenerateProblemRequest, forms: set[ContentForm]) -> float:
        if request.target_rigor != TargetRigor.high:
            return 1.0
        if forms & {ContentForm.formula, ContentForm.concept_relation, ContentForm.procedure, ContentForm.argument}:
            return 0.8
        return 0.35

    def _can_generate(self, *, forms: set[ContentForm]) -> list[ProblemStrategy]:
        strategies = [ProblemStrategy.basic_concept_check, ProblemStrategy.general_explanation]
        if forms & {ContentForm.formula, ContentForm.concept_relation, ContentForm.procedure, ContentForm.case}:
            strategies.append(ProblemStrategy.near_transfer_application)
        if ContentForm.formula in forms:
            strategies.extend([ProblemStrategy.formula_application, ProblemStrategy.calculation])
        if ContentForm.concept_relation in forms:
            strategies.extend([ProblemStrategy.comparison_judgment, ProblemStrategy.variable_prediction])
        if forms & {ContentForm.passage, ContentForm.argument}:
            strategies.append(ProblemStrategy.passage_evidence)
        if ContentForm.case in forms:
            strategies.append(ProblemStrategy.case_analysis)
        if ContentForm.code in forms:
            strategies.append(ProblemStrategy.code_reasoning)
        return list(dict.fromkeys(strategies))

    def _risky_generations(
        self,
        *,
        forms: set[ContentForm],
        request: GenerateProblemRequest,
    ) -> list[ProblemStrategy]:
        risky: list[ProblemStrategy] = []
        if ContentForm.case not in forms:
            risky.append(ProblemStrategy.case_analysis)
        if ContentForm.formula not in forms:
            risky.extend([ProblemStrategy.formula_application, ProblemStrategy.calculation])
        if request.target_rigor == TargetRigor.high and not (
            forms & {ContentForm.formula, ContentForm.concept_relation, ContentForm.procedure, ContentForm.argument}
        ):
            risky.append(ProblemStrategy.near_transfer_application)
        return list(dict.fromkeys(risky))

    def _reasons(
        self,
        *,
        total_chars: int,
        distinct_concept_count: int,
        forms: set[ContentForm],
        score: float,
    ) -> list[str]:
        reasons = [
            f"가져온 근거는 약 {total_chars}자다.",
            f"함께 잡힌 개념은 {distinct_concept_count}개다.",
            "자료에서 보이는 형태: " + ", ".join(sorted(form.value for form in forms)),
        ]
        if forms == {ContentForm.definition}:
            reasons.append("정의 중심 자료라 단순 암기 문제 반복 위험이 있다.")
        elif forms & {ContentForm.formula, ContentForm.concept_relation}:
            reasons.append("정의 중심이어도 관계나 공식이 보여서 간단한 응용 문제는 만들 수 있다.")
        if score < 0.45:
            reasons.append("근거가 적어서 시험 대비용 어려운 문제는 적게 만드는 편이 좋다.")
        return reasons

    def _recommended_uploads(
        self,
        *,
        forms: set[ContentForm],
        request: GenerateProblemRequest,
    ) -> list[str]:
        uploads: list[str] = []
        if request.target_rigor == TargetRigor.high and ContentForm.case not in forms:
            uploads.append("수업 예제나 과제 문제를 더 넣으면 응용 문제 품질이 좋아진다.")
        if ContentForm.formula not in forms and request.type.value == "short_answer":
            uploads.append("풀이형 문제를 원한다면 공식, 조건, 풀이 단계가 보이는 자료가 있으면 좋다.")
        if not uploads:
            uploads.append("현재 자료만으로 기본 문제와 간단한 응용 문제를 만들 수 있다.")
        return uploads

    def _level(
        self,
        *,
        score: float,
        can_generate: list[ProblemStrategy],
        request: GenerateProblemRequest,
    ) -> ReadinessLevel:
        if score >= 0.62:
            return ReadinessLevel.sufficient
        if ProblemStrategy.near_transfer_application in can_generate or request.target_rigor != TargetRigor.high:
            return ReadinessLevel.limited
        return ReadinessLevel.insufficient
