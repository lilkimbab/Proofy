from __future__ import annotations

from app.schemas.integration_contracts import RetrievedChunk
from app.schemas.problems import GenerateProblemRequest, ProblemStyle, ProblemType
from app.schemas.quality import (
    LearningTaskStrategyProfile,
    MaterialReadinessReport,
    SourceGroundingMode,
    SourceGroundingProfile,
)


class SourceGroundingPolicyPlanner:
    """Infer how far generation may extend beyond retrieved chunks.

    The planner stays internal because users should not have to choose a mode.
    It only interprets their natural-language request and keeps simple quiz
    requests simple while allowing explicit exam/application requests to create
    self-contained cases or extensions.
    """

    def plan(
        self,
        *,
        request: GenerateProblemRequest,
        chunks: list[RetrievedChunk] | None = None,
        strategy_profile: LearningTaskStrategyProfile | None = None,
        material_readiness: MaterialReadinessReport | None = None,
    ) -> SourceGroundingProfile:
        del chunks, strategy_profile, material_readiness
        text = self._request_text(request)
        simple = self._simple_request(request=request, text=text)
        extension_signals = self._extension_signals(text)
        application_signals = self._application_signals(text)
        contextual_extension = (
            not simple
            and bool(self._assessment_signals(text))
            and bool(self._reasoning_signals(text))
            and bool(self._novel_context_signals(text))
        )
        contextual_application = (
            not simple
            and bool(self._reasoning_signals(text))
            and bool(self._concrete_context_signals(text))
        )

        if (extension_signals or contextual_extension) and not simple:
            signals = list(dict.fromkeys([*extension_signals, *self._contextual_signals(text)]))
            return SourceGroundingProfile(
                mode=SourceGroundingMode.model_extension,
                allow_synthetic_context=True,
                allow_external_knowledge=True,
                strict_source_rejection=False,
                signals=signals or ["contextual_extension"],
                reason=(
                    "문장 맥락상 평가형 문제를 위해 새 조건이나 사례를 구성하고 높은 사고 작업을 "
                    "요구하므로 자료 개념을 출발점으로 한 자기완결 확장 생성을 허용한다."
                ),
            )

        if (application_signals or contextual_application) and not simple:
            signals = list(dict.fromkeys([*application_signals, *self._contextual_signals(text)]))
            return SourceGroundingProfile(
                mode=SourceGroundingMode.source_application,
                allow_synthetic_context=True,
                allow_external_knowledge=False,
                strict_source_rejection=False,
                signals=signals or ["contextual_application"],
                reason="문장 맥락상 자료 속 관계를 구체 조건, 사례, 비교, 분석, 계산, 추론에 적용하는 요청이다.",
            )

        return SourceGroundingProfile(
            mode=SourceGroundingMode.source_grounded,
            allow_synthetic_context=False,
            allow_external_knowledge=False,
            strict_source_rejection=True,
            signals=["simple_or_unspecified"] if simple else ["source_grounded_default"],
            reason="간단한 확인형 요청이거나 확장/응용 신호가 없어 업로드 자료 안에서만 생성한다.",
        )

    def _request_text(self, request: GenerateProblemRequest) -> str:
        return " ".join(
            [
                request.user_requirements or "",
                " ".join(request.concepts),
                request.type.value,
                request.difficulty.value,
                request.bloom_level.value,
                request.problem_style.value,
                request.target_rigor.value,
                request.goal.value,
                request.depth.value,
            ]
        ).lower()

    def _simple_request(self, *, request: GenerateProblemRequest, text: str) -> bool:
        if request.problem_style == ProblemStyle.concept_check:
            return True
        strong_cues = (
            "고난도",
            "심화",
            "응용",
            "분석",
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
        if any(cue in text for cue in strong_cues):
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
        if any(cue in text for cue in ("다른 조건", "조건 변화", "새 조건", "새 예제", "사례", "시나리오")):
            return False
        if any(cue in text for cue in simple_cues):
            return True
        return request.type == ProblemType.multiple_choice and request.problem_style == ProblemStyle.auto

    def _extension_signals(self, text: str) -> list[str]:
        cues = (
            "자료 밖",
            "외부 지식",
            "일반 지식",
            "새 구조",
            "새 규칙",
            "새 기준",
            "새 방식",
            "확장",
            "variant",
            "extension",
            "extend",
            "counterexample",
        )
        return [cue for cue in cues if cue in text]

    def _application_signals(self, text: str) -> list[str]:
        cues = (
            "응용",
            "적용",
            "분석",
            "비교",
            "판단",
            "추론",
            "평가",
            "예측",
            "계산",
            "추적",
            "과정",
            "단계",
            "다른 조건",
            "조건 변화",
            "변화 설명",
            "사례",
            "상황",
            "시나리오",
            "새 예제",
            "직접 만들어",
            "네가 직접",
            "지문",
            "표",
            "그래프",
            "도표",
            "apply",
            "analyze",
            "compare",
            "infer",
            "evaluate",
            "calculate",
            "trace",
            "scenario",
            "case",
        )
        return [cue for cue in cues if cue in text]

    def _assessment_signals(self, text: str) -> list[str]:
        cues = (
            "시험",
            "고사",
            "평가",
            "출제",
            "예상",
            "대비",
            "실전",
            "exam",
            "test",
            "assessment",
        )
        return [cue for cue in cues if cue in text]

    def _reasoning_signals(self, text: str) -> list[str]:
        cues = (
            "응용",
            "적용",
            "분석",
            "비교",
            "판단",
            "추론",
            "평가",
            "설계",
            "증명",
            "반례",
            "계산",
            "추적",
            "근거",
            "왜",
            "어떻게",
            "apply",
            "analyze",
            "compare",
            "infer",
            "evaluate",
            "design",
            "prove",
            "calculate",
            "reason",
        )
        return [cue for cue in cues if cue in text]

    def _novel_context_signals(self, text: str) -> list[str]:
        cues = (
            "새",
            "새로운",
            "직접",
            "가상",
            "변형",
            "확장",
            "조건",
            "사례",
            "상황",
            "시나리오",
            "구조",
            "규칙",
            "기준",
            "original",
            "new",
            "novel",
            "hypothetical",
            "variant",
            "extend",
        )
        return [cue for cue in cues if cue in text]

    def _concrete_context_signals(self, text: str) -> list[str]:
        cues = (
            "조건",
            "사례",
            "상황",
            "시나리오",
            "지문",
            "자료",
            "표",
            "그래프",
            "도표",
            "입력",
            "값",
            "수치",
            "데이터",
            "case",
            "scenario",
            "condition",
            "data",
            "table",
            "graph",
            "input",
        )
        return [cue for cue in cues if cue in text]

    def _contextual_signals(self, text: str) -> list[str]:
        return list(
            dict.fromkeys(
                [
                    *self._assessment_signals(text),
                    *self._reasoning_signals(text),
                    *self._novel_context_signals(text),
                    *self._concrete_context_signals(text),
                ]
            )
        )
