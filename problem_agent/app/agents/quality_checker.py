from __future__ import annotations

from dataclasses import dataclass
import math
import re

from app.agents.korean_style import korean_tone_issues
from app.schemas.integration_contracts import RetrievedChunk
from app.schemas.problem_kernels import ContentAtom, ContentAtomType, EvidenceRole, ProblemKernelPlan, ProblemKernelType
from app.schemas.problems import (
    BloomLevel,
    GenerateProblemRequest,
    ItemModelId,
    ProblemDepth,
    ProblemStyle,
    ProblemType,
    normalize_followup_problem_type,
)
from app.schemas.quality import (
    AssessmentBlueprint,
    HighRigorGenerationProfile,
    LearningTaskStrategyProfile,
    MaterialReadinessReport,
    ProblemQualityReport,
    ProblemStrategy,
    QualityFlag,
    QualityMode,
    QualityStatus,
    ReadinessLevel,
    SourceGroundingMode,
    SourceGroundingProfile,
    TargetRigor,
)
from app.services.evidence_obligation_evaluator import EvidenceObligationEvaluator
from app.services.request_safety import contains_unsafe_instruction_text


@dataclass(frozen=True)
class SourceGroundingCheck:
    flags: list[QualityFlag]
    coverage_score: float | None
    unsupported_numbers: list[str]
    verbatim_overlap_chars: int


@dataclass(frozen=True)
class ChoiceQualityCheck:
    flags: list[QualityFlag]
    issues: list[str]


@dataclass(frozen=True)
class RubricQualityCheck:
    flags: list[QualityFlag]
    issues: list[str]


@dataclass(frozen=True)
class ItemModelQualityCheck:
    flags: list[QualityFlag]
    issues: list[str]


class ProblemQualityChecker:
    def validate(self, problem: dict, *, retrieved_chunks: list[RetrievedChunk] | None = None) -> tuple[bool, list[str]]:
        errors: list[str] = []
        required = [
            "document_id",
            "type",
            "difficulty",
            "bloom_level",
            "question",
            "answer",
            "explanation",
            "concepts",
            "source_chunk_ids",
        ]
        for field in required:
            if problem.get(field) in (None, "", []):
                errors.append(f"{field} is required")

        concepts = problem.get("concepts") or []
        if any(not str(concept or "").strip() for concept in concepts):
            errors.append("concepts must not include empty values")

        source_chunk_ids = problem.get("source_chunk_ids") or []
        if any(not str(chunk_id or "").strip() for chunk_id in source_chunk_ids):
            errors.append("source_chunk_ids must not include empty values")
        if len(set(source_chunk_ids)) != len(source_chunk_ids):
            errors.append("source_chunk_ids must be unique")
        if retrieved_chunks is not None and source_chunk_ids:
            retrieved_chunk_map = {chunk.chunk_id: chunk for chunk in retrieved_chunks}
            retrieved_chunk_ids = set(retrieved_chunk_map)
            missing_chunk_ids = [chunk_id for chunk_id in source_chunk_ids if chunk_id not in retrieved_chunk_ids]
            if missing_chunk_ids:
                errors.append(f"source_chunk_ids not found in retrieved chunks: {', '.join(missing_chunk_ids)}")
            mismatched_document_ids = [
                chunk_id
                for chunk_id in source_chunk_ids
                if chunk_id in retrieved_chunk_map and retrieved_chunk_map[chunk_id].document_id != problem.get("document_id")
            ]
            if mismatched_document_ids:
                errors.append(f"source_chunk_ids belong to a different document: {', '.join(mismatched_document_ids)}")

        if problem.get("type") == "multiple_choice":
            choices = problem.get("choices") or []
            if len(choices) != 4:
                errors.append("multiple_choice problem must have exactly 4 choices")
            if problem.get("rubric") is not None:
                errors.append("multiple_choice problem must not have rubric")

            choice_ids = []
            choice_texts = []
            for index, choice in enumerate(choices):
                if not isinstance(choice, dict):
                    errors.append(f"choice {index + 1} must be an object")
                    continue
                choice_id = str(choice.get("id") or "").strip()
                choice_text = str(choice.get("text") or "").strip()
                if not choice_id:
                    errors.append("choice.id must not be empty")
                if not choice_text:
                    errors.append("choice.text must not be empty")
                choice_ids.append(choice_id)
                choice_texts.append(choice_text)

            if len(set(choice_ids)) != len(choice_ids):
                errors.append("choice ids must be unique")
            non_empty_choice_texts = [text for text in choice_texts if text]
            if len(set(non_empty_choice_texts)) != len(non_empty_choice_texts):
                errors.append("choice texts must be unique")

            choice_id_set = set(choice_ids)
            choice_text_by_id = {
                str(choice.get("id") or "").strip(): str(choice.get("text") or "").strip()
                for choice in choices
                if isinstance(choice, dict)
            }
            answer = problem.get("answer") or {}
            answer_id = answer.get("choice_id")
            if answer_id not in choice_id_set:
                errors.append("answer.choice_id must exist in choices")
            if not str(answer.get("text") or "").strip():
                errors.append("answer.text is required for multiple_choice")
            elif answer_id in choice_text_by_id and str(answer.get("text") or "").strip() != choice_text_by_id[answer_id]:
                errors.append("answer.text must match the selected choice text")

            choice_explanations = problem.get("choice_explanations") or {}
            if not choice_explanations:
                errors.append("choice_explanations are required for multiple_choice")
            else:
                missing_explanations = [
                    choice_id
                    for choice_id in choice_ids
                    if choice_id and not str(choice_explanations.get(choice_id) or "").strip()
                ]
                if missing_explanations:
                    errors.append("choice_explanations must include every choice id")
                extra_explanations = set(choice_explanations) - set(choice_ids)
                if extra_explanations:
                    errors.append("choice_explanations must not include unknown choice ids")

            choice_diagnostic_errors = self._validate_choice_diagnostics_shape(
                problem=problem,
                choice_ids=choice_ids,
                answer_id=str(answer_id or ""),
            )
            errors.extend(choice_diagnostic_errors)

        if problem.get("type") == "short_answer":
            if problem.get("choices") is not None:
                errors.append("short_answer problem must not have choices")
            if problem.get("choice_explanations") is not None:
                errors.append("short_answer problem must not have choice_explanations")
            if problem.get("choice_diagnostics") is not None:
                errors.append("short_answer problem must not have choice_diagnostics")
            if (problem.get("answer") or {}).get("choice_id") is not None:
                errors.append("short_answer answer.choice_id must be null")
            rubric = problem.get("rubric") or []
            if not rubric:
                errors.append("rubric is required for short_answer")
            else:
                total_points = 0.0
                for index, item in enumerate(rubric):
                    if not isinstance(item, dict):
                        errors.append(f"rubric item {index + 1} must be an object")
                        continue
                    if not str(item.get("criterion") or "").strip():
                        errors.append("rubric.criterion must not be empty")
                    try:
                        points = float(item.get("points"))
                    except (TypeError, ValueError):
                        errors.append("rubric.points must be a positive number")
                        continue
                    if not math.isfinite(points) or points <= 0:
                        errors.append("rubric.points must be a positive number")
                        continue
                    total_points += points
                if total_points <= 0:
                    errors.append("rubric total points must be greater than 0")

            if not str((problem.get("answer") or {}).get("text") or "").strip():
                errors.append("answer.text is required for short_answer")

        return not errors, errors


    def _validate_choice_diagnostics_shape(self, *, problem: dict, choice_ids: list[str], answer_id: str) -> list[str]:
        diagnostics = problem.get("choice_diagnostics")
        if diagnostics is None:
            return []
        if not isinstance(diagnostics, list):
            return ["choice_diagnostics must be a list"]

        errors: list[str] = []
        diagnostic_ids: list[str] = []
        correct_ids: list[str] = []
        for index, diagnostic in enumerate(diagnostics, start=1):
            if not isinstance(diagnostic, dict):
                errors.append(f"choice_diagnostics[{index}] must be an object")
                continue
            choice_id = str(diagnostic.get("choice_id") or "").strip()
            diagnostic_ids.append(choice_id)
            is_correct = bool(diagnostic.get("is_correct"))
            mistake_type = str(diagnostic.get("mistake_type") or "").strip()
            if is_correct:
                correct_ids.append(choice_id)
                if mistake_type != "none":
                    errors.append("correct choice diagnostic must use mistake_type=none")
                continue
            if mistake_type in {"", "none"}:
                errors.append("incorrect choice diagnostic must include a concrete mistake_type")
            for field in ("why_plausible", "repair_strategy", "followup_problem_type"):
                if not str(diagnostic.get(field) or "").strip():
                    errors.append(f"incorrect choice diagnostic requires {field}")
            if str(diagnostic.get("followup_problem_type") or "").strip():
                try:
                    diagnostic["followup_problem_type"] = normalize_followup_problem_type(
                        diagnostic.get("followup_problem_type")
                    )
                except ValueError as exc:
                    errors.append(str(exc))

        if set(diagnostic_ids) != set(choice_ids):
            errors.append("choice_diagnostics must cover every choice id")
        if len(correct_ids) != 1 or correct_ids[0] != answer_id:
            errors.append("choice_diagnostics must mark exactly the answer choice as correct")
        return errors

    def validate_with_quality_report(
        self,
        problem: dict,
        *,
        retrieved_chunks: list[RetrievedChunk] | None = None,
        request: GenerateProblemRequest | None = None,
        blueprint: AssessmentBlueprint | None = None,
        material_readiness: MaterialReadinessReport | None = None,
        learning_task_strategy: LearningTaskStrategyProfile | None = None,
        high_rigor_profile: HighRigorGenerationProfile | None = None,
        source_grounding_profile: SourceGroundingProfile | None = None,
        content_atoms: list[ContentAtom] | None = None,
        problem_kernel_plan: ProblemKernelPlan | None = None,
    ) -> tuple[bool, list[str], ProblemQualityReport]:
        is_valid, errors = self.validate(problem, retrieved_chunks=retrieved_chunks)
        source_grounded = not any("source_chunk" in error for error in errors)
        if not is_valid:
            return (
                False,
                errors,
                ProblemQualityReport(
                    status=QualityStatus.rejected,
                    score=0,
                    flags=self._flags_from_shape_errors(errors),
                    source_grounded=source_grounded,
                    cognitive_level_fit=False,
                    blueprint_aligned=False,
                    action="reject",
                ),
            )

        flags: list[QualityFlag] = []
        score = 1.0
        status = QualityStatus.passed
        cognitive_level_fit = True
        blueprint_aligned = True

        if material_readiness is not None:
            if material_readiness.level == ReadinessLevel.insufficient:
                flags.append(QualityFlag.insufficient_source)
                score -= 0.35
                status = QualityStatus.needs_review
            elif material_readiness.level == ReadinessLevel.limited and request is not None and request.goal.value == "exam_prep":
                flags.append(QualityFlag.limited_source)
                score -= 0.15
                status = QualityStatus.limited_source

        if request is not None and self._definition_only_risk(problem=problem, request=request):
            flags.append(QualityFlag.definition_only_risk)
            score -= 0.25
            cognitive_level_fit = False
            status = QualityStatus.needs_review

        if blueprint is not None and self._blueprint_mismatch(problem=problem, blueprint=blueprint):
            flags.append(QualityFlag.blueprint_mismatch)
            score -= 0.20
            blueprint_aligned = False
            status = QualityStatus.needs_review

        if learning_task_strategy is not None and learning_task_strategy.confidence == "low":
            flags.append(QualityFlag.low_strategy_confidence)
            score -= 0.10
            if status == QualityStatus.passed:
                status = QualityStatus.needs_review

        grounding_check = self._source_grounding_check(
            problem=problem,
            retrieved_chunks=retrieved_chunks,
            request=request,
            blueprint=blueprint,
            source_grounding_profile=source_grounding_profile,
        )
        if grounding_check.flags:
            flags.extend(grounding_check.flags)
            score -= 0.20
            source_grounded = False
            status = QualityStatus.needs_review

        choice_quality_check = self._choice_quality_check(problem)
        if choice_quality_check.flags:
            flags.extend(choice_quality_check.flags)
            score -= 0.35 if QualityFlag.option_length_cue in choice_quality_check.flags else 0.10
            if status == QualityStatus.passed:
                status = QualityStatus.needs_review

        rubric_quality_check = self._rubric_quality_check(problem=problem, request=request)
        if rubric_quality_check.flags:
            flags.extend(rubric_quality_check.flags)
            score -= 0.15
            cognitive_level_fit = False
            if status == QualityStatus.passed:
                status = QualityStatus.needs_review

        item_model_quality_check = self._item_model_quality_check(
            problem=problem,
            request=request,
            retrieved_chunks=retrieved_chunks,
        )
        if item_model_quality_check.flags:
            flags.extend(item_model_quality_check.flags)
            score -= 0.18
            cognitive_level_fit = False
            if status == QualityStatus.passed:
                status = QualityStatus.needs_review

        professor_review_issues = self._professor_review_issues(problem)
        if professor_review_issues:
            flags.append(QualityFlag.item_model_quality_violation)
            score -= 0.18
            cognitive_level_fit = False
            if status == QualityStatus.passed:
                status = QualityStatus.needs_review

        if self._prompt_injection_leak(problem):
            flags.append(QualityFlag.prompt_injection_leak)
            score -= 0.50
            status = QualityStatus.rejected

        if self._answer_leak(problem):
            flags.append(QualityFlag.answer_leak)
            score -= 0.30
            if status != QualityStatus.rejected:
                status = QualityStatus.needs_review

        if self._invalid_latex(problem):
            flags.append(QualityFlag.invalid_latex)
            score -= 0.20
            if status != QualityStatus.rejected:
                status = QualityStatus.needs_review

        tone_issues = korean_tone_issues(self._all_problem_text(problem))
        if tone_issues:
            flags.append(QualityFlag.ai_like_wording)
            score -= 0.10
            if status == QualityStatus.passed:
                status = QualityStatus.needs_review

        if request is not None and self._shallow_deep_question(problem=problem, request=request):
            flags.append(QualityFlag.shallow_deep_question)
            score -= 0.25
            cognitive_level_fit = False
            if status != QualityStatus.rejected:
                status = QualityStatus.needs_review

        if request is not None and self._weak_calculation_fit(
            problem=problem,
            request=request,
            retrieved_chunks=retrieved_chunks,
            blueprint=blueprint,
        ):
            flags.append(QualityFlag.weak_application_fit)
            score -= 0.20
            cognitive_level_fit = False
            if status != QualityStatus.rejected:
                status = QualityStatus.needs_review

        if request is not None and self._weak_concept_integration(
            problem=problem,
            request=request,
            retrieved_chunks=retrieved_chunks,
            high_rigor_profile=high_rigor_profile,
        ):
            flags.append(QualityFlag.weak_concept_integration)
            score -= 0.18
            cognitive_level_fit = False
            if status != QualityStatus.rejected:
                status = QualityStatus.needs_review

        high_rigor_application_issues = self._high_rigor_application_issues(
            problem=problem,
            high_rigor_profile=high_rigor_profile,
        )
        if high_rigor_application_issues:
            flags.append(QualityFlag.weak_application_fit)
            score -= 0.22
            cognitive_level_fit = False
            if status != QualityStatus.rejected:
                status = QualityStatus.needs_review

        high_rigor_demand_issues = self._high_rigor_cognitive_demand_issues(
            problem=problem,
            high_rigor_profile=high_rigor_profile,
        )
        if high_rigor_demand_issues:
            flags.append(QualityFlag.low_cognitive_demand)
            score -= 0.22
            cognitive_level_fit = False
            if status != QualityStatus.rejected:
                status = QualityStatus.needs_review

        high_rigor_multiple_choice_issues = self._high_rigor_multiple_choice_issues(
            problem=problem,
            high_rigor_profile=high_rigor_profile,
        )
        if high_rigor_multiple_choice_issues:
            flags.extend(self._high_rigor_multiple_choice_flags(high_rigor_multiple_choice_issues))
            score -= 0.22
            cognitive_level_fit = False
            if status != QualityStatus.rejected:
                status = QualityStatus.needs_review

        extension_contract_issues = self._model_extension_contract_issues(
            problem=problem,
            request=request,
            source_grounding_profile=source_grounding_profile,
            retrieved_chunks=retrieved_chunks,
        )
        if extension_contract_issues:
            flags.append(QualityFlag.item_model_quality_violation)
            score -= 0.20
            cognitive_level_fit = False
            if status != QualityStatus.rejected:
                status = QualityStatus.needs_review

        kernel_obligation_issues = self._kernel_obligation_issues(
            problem=problem,
            request=request,
            retrieved_chunks=retrieved_chunks,
            content_atoms=content_atoms or [],
            problem_kernel_plan=problem_kernel_plan,
        )
        if kernel_obligation_issues:
            flags.append(QualityFlag.item_model_quality_violation)
            score -= 0.20
            cognitive_level_fit = False
            if status != QualityStatus.rejected:
                status = QualityStatus.needs_review

        strict_reject = (
            request is not None
            and request.quality_mode == QualityMode.strict
            and (
                QualityFlag.insufficient_source in flags
                or QualityFlag.definition_only_risk in flags
                or QualityFlag.blueprint_mismatch in flags
                or QualityFlag.unsupported_source in flags
                or QualityFlag.weak_source_overlap in flags
                or QualityFlag.shallow_deep_question in flags
                or QualityFlag.prompt_injection_leak in flags
                or QualityFlag.answer_leak in flags
                or QualityFlag.source_verbatim_overlap in flags
                or QualityFlag.weak_application_fit in flags
                or QualityFlag.all_or_none_option in flags
                or QualityFlag.option_length_cue in flags
                or QualityFlag.absolute_wording in flags
                or QualityFlag.overlapping_options in flags
                or QualityFlag.implausible_distractor in flags
                or QualityFlag.unfocused_stem in flags
                or QualityFlag.weak_rubric_evidence in flags
                or QualityFlag.item_model_quality_violation in flags
                or QualityFlag.weak_concept_integration in flags
                or QualityFlag.low_cognitive_demand in flags
                or (
                    QualityFlag.ai_like_wording in flags
                    and not (high_rigor_profile is not None and high_rigor_profile.enabled)
                )
                or QualityFlag.invalid_latex in flags
            )
        )
        high_rigor_reject = (
            high_rigor_profile is not None
            and high_rigor_profile.enabled
            and bool(set(flags) & self._high_rigor_reject_flags())
        )
        if strict_reject or high_rigor_reject:
            status = QualityStatus.rejected

        score = max(round(score, 3), 0)
        action = "reject" if status == QualityStatus.rejected else "save"
        report = ProblemQualityReport(
            status=status,
            score=score,
            flags=list(dict.fromkeys(flags)),
            source_grounded=source_grounded,
            source_coverage_score=grounding_check.coverage_score,
            unsupported_numbers=grounding_check.unsupported_numbers,
            verbatim_overlap_chars=grounding_check.verbatim_overlap_chars,
            cognitive_level_fit=cognitive_level_fit,
            blueprint_aligned=blueprint_aligned,
            choice_quality_issues=choice_quality_check.issues,
            rubric_quality_issues=rubric_quality_check.issues,
            item_model_quality_issues=list(
                dict.fromkeys(
                    [
                        *item_model_quality_check.issues,
                        *professor_review_issues,
                        *high_rigor_application_issues,
                        *high_rigor_demand_issues,
                        *high_rigor_multiple_choice_issues,
                        *extension_contract_issues,
                        *kernel_obligation_issues,
                    ]
                )
            ),
            repetition_risk=self._repetition_risk(problem),
            action=action,
        )
        if status == QualityStatus.rejected:
            errors = [*errors, self._reject_reason(report)]
        return status != QualityStatus.rejected, errors, report

    def _flags_from_shape_errors(self, errors: list[str]) -> list[QualityFlag]:
        flags: list[QualityFlag] = []
        if any("source_chunk" in error for error in errors):
            flags.append(QualityFlag.unsupported_source)
        return flags

    def _definition_only_risk(self, *, problem: dict, request: GenerateProblemRequest) -> bool:
        if request.target_rigor != TargetRigor.high:
            return False
        question = str(problem.get("question") or "").lower()
        definition_patterns = (
            "무엇인가",
            "무엇인지",
            "정의",
            "설명으로 가장 적절",
            "설명해",
            "의미를 쓰",
            "개념을 쓰",
        )
        application_cues = (
            "조건",
            "경우",
            "상황",
            "적용",
            "비교",
            "분석",
            "예측",
            "판단",
            "계산",
            "왜",
            "어떻게",
            "변화",
            "클수록",
            "작을수록",
            "반례",
            "사례",
        )
        return any(pattern in question for pattern in definition_patterns) and not any(
            cue in question for cue in application_cues
        )

    def _blueprint_mismatch(self, *, problem: dict, blueprint: AssessmentBlueprint) -> bool:
        required_strategies = {
            strategy for cell in blueprint.distribution for strategy in cell.strategies
        }
        if ProblemStrategy.near_transfer_application not in required_strategies:
            return False
        question = str(problem.get("question") or "").lower()
        answer_text = str((problem.get("answer") or {}).get("text") or "").lower()
        combined = f"{question}\n{answer_text}"
        application_cues = (
            "조건",
            "경우",
            "상황",
            "적용",
            "비교",
            "예측",
            "계산",
            "변화",
            "클수록",
            "작을수록",
            "같은 힘",
            "같은 조건",
            "달라지",
            "바뀌",
            "늘어",
            "줄어",
            "증가",
            "감소",
        )
        return not any(cue in combined for cue in application_cues)

    def _repetition_risk(self, problem: dict) -> str:
        question = str(problem.get("question") or "")
        choices = problem.get("choices") or []
        choice_texts = [str(choice.get("text") or "") for choice in choices if isinstance(choice, dict)]
        if choice_texts and any(question.strip() == text.strip() for text in choice_texts):
            return "high"
        if question.count("?") > 1 or len(question) < 12:
            return "medium"
        return "low"

    def _source_grounding_check(
        self,
        *,
        problem: dict,
        retrieved_chunks: list[RetrievedChunk] | None,
        request: GenerateProblemRequest | None,
        blueprint: AssessmentBlueprint | None,
        source_grounding_profile: SourceGroundingProfile | None = None,
    ) -> SourceGroundingCheck:
        if retrieved_chunks is None:
            return SourceGroundingCheck(flags=[], coverage_score=None, unsupported_numbers=[], verbatim_overlap_chars=0)
        source_chunk_ids = problem.get("source_chunk_ids") or []
        chunk_by_id = {chunk.chunk_id: chunk for chunk in retrieved_chunks}
        cited_chunks = [chunk_by_id[chunk_id] for chunk_id in source_chunk_ids if chunk_id in chunk_by_id]
        if not cited_chunks:
            return SourceGroundingCheck(
                flags=[QualityFlag.unsupported_source],
                coverage_score=0,
                unsupported_numbers=[],
                verbatim_overlap_chars=0,
            )

        source_text = self._source_text(cited_chunks)
        generated_text = self._grounding_text(problem)
        source_tokens = self._content_tokens(source_text)
        generated_tokens = self._content_tokens(generated_text)
        flags: list[QualityFlag] = []
        coverage_score: float | None = None
        if generated_tokens:
            overlap = source_tokens & generated_tokens
            coverage_score = round(len(overlap) / max(1, min(len(generated_tokens), len(source_tokens))), 3)
            if len(overlap) < min(2, len(generated_tokens)):
                flags.append(QualityFlag.weak_source_overlap)

        source_numbers = set(re.findall(r"\d+(?:\.\d+)?", source_text))
        generated_numbers = set(re.findall(r"\d+(?:\.\d+)?", generated_text))
        if self._allows_synthetic_calculation_values(
            problem=problem,
            request=request,
            blueprint=blueprint,
            source_text=source_text,
        ) or self._allows_synthetic_application_context(
            problem=problem,
            request=request,
            source_text=source_text,
            source_grounding_profile=source_grounding_profile,
        ) or self._allows_model_extension_context(
            problem=problem,
            request=request,
            source_grounding_profile=source_grounding_profile,
            retrieved_chunks=cited_chunks,
        ):
            unsupported_numbers = set()
        else:
            unsupported_numbers = {
                number
                for number in generated_numbers - source_numbers
                if number not in {"0", "1", "2", "3", "4", "5"}
            }
        if unsupported_numbers:
            flags.append(QualityFlag.unsupported_source)

        verbatim_overlap_chars = self._max_verbatim_source_overlap(
            generated_text=generated_text,
            cited_chunks=cited_chunks,
        )
        if verbatim_overlap_chars >= 90:
            flags.append(QualityFlag.source_verbatim_overlap)

        return SourceGroundingCheck(
            flags=list(dict.fromkeys(flags)),
            coverage_score=coverage_score,
            unsupported_numbers=sorted(unsupported_numbers, key=float),
            verbatim_overlap_chars=verbatim_overlap_chars,
        )

    def _source_text(self, chunks: list[RetrievedChunk]) -> str:
        return " ".join(
            " ".join([chunk.content, chunk.section_title or "", " ".join(chunk.concepts)])
            for chunk in chunks
        )

    def _calculation_required(
        self,
        *,
        request: GenerateProblemRequest,
        blueprint: AssessmentBlueprint | None = None,
    ) -> bool:
        if request.problem_style == ProblemStyle.calculation_practice:
            return True
        requirement = (request.user_requirements or "").lower()
        calculation_cues = (
            "계산",
            "수식",
            "공식",
            "풀이",
            "값을 구",
            "구하",
            "정량",
            "숫자",
            "solve",
            "calculation",
            "numerical",
        )
        if any(cue in requirement for cue in calculation_cues):
            return True
        blueprint_requires_calculation = bool(
            blueprint
            and any(
                strategy in {ProblemStrategy.calculation, ProblemStrategy.formula_application}
                for cell in blueprint.distribution
                for strategy in cell.strategies
            )
        )
        return (
            request.goal.value == "exam_prep"
            and request.target_rigor == TargetRigor.high
            and request.difficulty.value == "hard"
            and blueprint_requires_calculation
        )

    def _source_has_formula_evidence(self, source_text: str) -> bool:
        return bool(re.search(r"[A-Za-z가-힣]\w*\s*=\s*[A-Za-z0-9가-힣]", source_text))

    def _problem_has_calculation_work(self, problem: dict) -> bool:
        text = self._all_problem_text(problem)
        solution_text = self._calculation_solution_text(problem)
        number_count = len(set(re.findall(r"\d+(?:\.\d+)?", text)))
        has_equation = bool(
            re.search(r"\$[^$]*=[^$]*\$", text)
            or re.search(r"[A-Za-z가-힣]\w*\s*=\s*[A-Za-z0-9가-힣]", text)
        )
        solution_has_equation = bool(
            re.search(r"\$[^$]*=[^$]*\$", solution_text)
            or re.search(r"[A-Za-z가-힣]\w*\s*=\s*[A-Za-z0-9가-힣]", solution_text)
        )
        calculation_cues = (
            "계산",
            "구하",
            "대입",
            "나누",
            "곱",
            "단위",
            "값",
            "m/s",
            "kg",
        )
        solution_has_arithmetic = bool(
            re.search(r"\d+(?:\.\d+)?\s*[+\-*/÷]\s*\d+(?:\.\d+)?", solution_text)
        )
        if number_count >= 2:
            return has_equation and solution_has_equation and solution_has_arithmetic
        return has_equation and solution_has_equation and any(cue in solution_text.lower() for cue in calculation_cues)

    def _allows_synthetic_calculation_values(
        self,
        *,
        problem: dict,
        request: GenerateProblemRequest | None,
        blueprint: AssessmentBlueprint | None,
        source_text: str,
    ) -> bool:
        if request is None:
            return False
        if not self._calculation_required(request=request, blueprint=blueprint):
            return False
        return self._source_has_formula_evidence(source_text) and self._problem_has_calculation_work(problem)

    def _allows_synthetic_application_context(
        self,
        *,
        problem: dict,
        request: GenerateProblemRequest | None,
        source_text: str,
        source_grounding_profile: SourceGroundingProfile | None = None,
    ) -> bool:
        if request is None:
            return False
        profile_allows_application = (
            source_grounding_profile is not None
            and source_grounding_profile.allow_synthetic_context
            and source_grounding_profile.mode
            in {SourceGroundingMode.source_application, SourceGroundingMode.model_extension}
        )
        if not profile_allows_application and not self._requests_synthetic_application_context(request):
            return False
        return (
            self._structured_application_requested(request)
            and self._problem_has_structured_application_work(problem)
            and self._source_has_transferable_application_basis(source_text)
        )

    def _allows_model_extension_context(
        self,
        *,
        problem: dict,
        request: GenerateProblemRequest | None,
        source_grounding_profile: SourceGroundingProfile | None,
        retrieved_chunks: list[RetrievedChunk],
    ) -> bool:
        if (
            source_grounding_profile is None
            or source_grounding_profile.mode != SourceGroundingMode.model_extension
            or not source_grounding_profile.allow_synthetic_context
        ):
            return False
        return not self._model_extension_contract_issues(
            problem=problem,
            request=request,
            source_grounding_profile=source_grounding_profile,
            retrieved_chunks=retrieved_chunks,
        )

    def _model_extension_contract_issues(
        self,
        *,
        problem: dict,
        request: GenerateProblemRequest | None,
        source_grounding_profile: SourceGroundingProfile | None,
        retrieved_chunks: list[RetrievedChunk] | None,
    ) -> list[str]:
        if source_grounding_profile is None or source_grounding_profile.mode != SourceGroundingMode.model_extension:
            return []

        question = str(problem.get("question") or "").lower()
        answer_text = str((problem.get("answer") or {}).get("text") or "").lower()
        explanation = str(problem.get("explanation") or "").lower()
        rubric = [item for item in (problem.get("rubric") or []) if isinstance(item, dict)]
        rubric_text = " ".join(
            " ".join(
                [
                    str(item.get("criterion") or ""),
                    " ".join(str(value) for value in (item.get("expected_evidence") or [])),
                    " ".join(str(value) for value in (item.get("partial_credit_rules") or [])),
                ]
            )
            for item in rubric
        ).lower()
        combined = f"{question} {answer_text} {explanation} {rubric_text}"
        source_text = self._source_text(retrieved_chunks or [])
        generated_tokens = self._content_tokens(combined)
        source_tokens = self._content_tokens(source_text)
        request_concepts = self._concept_signals((request.concepts if request else []) or [])
        mentioned_request_concept = any(
            self._concept_mentioned(concept=concept, text=combined)
            for concept in request_concepts
        )
        source_overlap = len(generated_tokens & source_tokens)

        assumption_cues = (
            "다음",
            "조건",
            "가정",
            "사례",
            "상황",
            "시나리오",
            "자료",
            "지문",
            "표",
            "그래프",
            "도표",
            "정의",
            "규칙",
            "구조",
            "기준",
            "방식",
            "연산",
            "given",
            "assume",
            "define",
            "case",
            "scenario",
            "condition",
        )
        reasoning_cues = (
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
            "도출",
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
        evidence_count = sum(len(item.get("expected_evidence") or []) for item in rubric)
        issues: list[str] = []
        if not mentioned_request_concept and source_overlap < 2:
            issues.append("model-extension item must stay anchored to at least one requested or source concept")
        if not any(cue in question for cue in assumption_cues):
            issues.append("model-extension item must state the concrete assumptions, case, data, or conditions in the question")
        if not any(cue in combined for cue in reasoning_cues):
            issues.append("model-extension item must require reasoning such as application, analysis, comparison, inference, evaluation, design, proof, or calculation")
        if problem.get("type") == "short_answer" and (len(rubric) < 2 or evidence_count < 2):
            issues.append("model-extension short-answer item needs a rubric with multiple observable evidence points")
        return list(dict.fromkeys(issues))

    def _requests_synthetic_application_context(self, request: GenerateProblemRequest) -> bool:
        text = " ".join([request.user_requirements or "", " ".join(request.concepts)]).lower()
        cues = (
            "예제",
            "예시",
            "새 상황",
            "새로운 상황",
            "원본 문제",
            "직접 만들",
            "직접 적절",
            "네가 직접",
            "문제 상황",
            "상황을 만들어",
            "사례를 만들어",
            "조건을 만들어",
            "지문을 만들어",
            "데이터를 만들어",
            "조건은 네가",
            "가상의",
            "hypothetical",
            "new situation",
            "new scenario",
            "original problem",
            "create an example",
            "make an example",
            "create a case",
            "make a case",
            "create a scenario",
            "make a scenario",
        )
        return any(cue in text for cue in cues)

    def _source_has_transferable_application_basis(self, source_text: str) -> bool:
        text = source_text.lower()
        rule_cues = (
            "공식",
            "관계",
            "법칙",
            "원리",
            "규칙",
            "절차",
            "과정",
            "단계",
            "알고리즘",
            "수행",
            "적용",
            "비교",
            "분석",
            "판단",
            "원인",
            "결과",
            "영향",
            "특징",
            "구조",
            "패턴",
            "흐름",
            "사례",
            "조건",
            "자료",
            "지문",
            "데이터",
            "증가",
            "감소",
            "비례",
            "반비례",
            "하면",
            "경우",
            "algorithm",
            "procedure",
            "property",
            "invariant",
            "case",
            "scenario",
            "condition",
            "data",
            "evidence",
            "cause",
            "effect",
            "pattern",
            "complexity",
            "time",
            "build",
            "construct",
            "update",
            "transform",
            "optimize",
            "constraint",
            "operation",
            "step",
            "state",
            "flow",
        )
        return any(cue in text for cue in rule_cues)

    def _weak_calculation_fit(
        self,
        *,
        problem: dict,
        request: GenerateProblemRequest,
        retrieved_chunks: list[RetrievedChunk] | None,
        blueprint: AssessmentBlueprint | None,
    ) -> bool:
        if not self._calculation_required(request=request, blueprint=blueprint):
            return False
        if self._structured_application_requested(request) and self._problem_has_structured_application_work(problem):
            return False
        source_text = self._source_text(retrieved_chunks or [])
        if not self._source_has_formula_evidence(source_text):
            return True
        if not self._problem_has_calculation_work(problem):
            return True
        if problem.get("type") != "short_answer":
            return False
        rubric_text = " ".join(
            " ".join(
                [
                    str(item.get("criterion") or ""),
                    " ".join(str(value) for value in (item.get("expected_evidence") or [])),
                    " ".join(str(value) for value in (item.get("partial_credit_rules") or [])),
                ]
            )
            for item in (problem.get("rubric") or [])
            if isinstance(item, dict)
        )
        return not any(cue in rubric_text for cue in ("공식", "대입", "계산", "단위", "값"))

    def _weak_concept_integration(
        self,
        *,
        problem: dict,
        request: GenerateProblemRequest,
        retrieved_chunks: list[RetrievedChunk] | None,
        high_rigor_profile: HighRigorGenerationProfile | None,
    ) -> bool:
        if not high_rigor_profile or not high_rigor_profile.enabled or not high_rigor_profile.multi_concept_required:
            return False
        if not self._explicit_multi_concept_request(request):
            return False

        available_concepts = self._concept_signals(
            [
                *request.concepts,
                *[
                    concept
                    for chunk in (retrieved_chunks or [])
                    for concept in chunk.concepts
                ],
            ]
        )
        if len(available_concepts) < 2:
            return False

        required_concepts = self._concept_signals(request.concepts)
        if len(required_concepts) < 2:
            required_concepts = available_concepts
        required_count = min(2, len(required_concepts))
        generated_text = self._grounding_text(problem)
        mentioned_concepts = {
            concept
            for concept in required_concepts
            if self._concept_mentioned(concept=concept, text=generated_text)
        }
        source_chunk_ids = set(problem.get("source_chunk_ids") or [])
        cited_concepts = self._concept_signals(
            [
                concept
                for chunk in (retrieved_chunks or [])
                if chunk.chunk_id in source_chunk_ids
                for concept in chunk.concepts
            ]
        )
        cited_required_concepts = {
            concept
            for concept in required_concepts
            if concept in cited_concepts
        }
        return len(mentioned_concepts) < required_count or len(cited_required_concepts) < required_count

    def _explicit_multi_concept_request(self, request: GenerateProblemRequest) -> bool:
        text = " ".join([request.user_requirements or "", " ".join(request.concepts)])
        patterns = (
            "여러 개념",
            "개념 혼합",
            "복합 개념",
            "섞어서",
            "융합",
            "연결",
            "엮",
            "모두 포함",
            "함께 다루",
            "동시에 다루",
        )
        return any(pattern in text for pattern in patterns)

    def _concept_signals(self, values: list[str]) -> list[str]:
        signals: list[str] = []
        for value in values:
            concept = str(value or "").strip()
            if len(concept) < 2:
                continue
            if concept not in signals:
                signals.append(concept)
        return signals

    def _concept_mentioned(self, *, concept: str, text: str) -> bool:
        normalized_concept = self._normalize_for_overlap(concept)
        normalized_text = self._normalize_for_overlap(text)
        if normalized_concept in normalized_text:
            return True
        concept_tokens = self._content_tokens(concept)
        text_tokens = self._content_tokens(text)
        return bool(concept_tokens) and len(concept_tokens & text_tokens) == len(concept_tokens)

    def _structured_application_requested(self, request: GenerateProblemRequest) -> bool:
        text = " ".join([request.user_requirements or "", " ".join(request.concepts)]).lower()
        request_cues = (
            "추적",
            "단계",
            "과정",
            "흐름",
            "변화",
            "조건",
            "사례",
            "상황",
            "자료",
            "표",
            "그래프",
            "도표",
            "비교",
            "분석",
            "판단",
            "예측",
            "적용",
            "simulation",
            "simulate",
            "trace",
            "step",
            "process",
            "case",
            "scenario",
            "condition",
            "compare",
            "analyze",
            "apply",
        )
        return any(cue in text for cue in request_cues)

    def _problem_has_structured_application_work(self, problem: dict) -> bool:
        question = str(problem.get("question") or "")
        answer_text = str((problem.get("answer") or {}).get("text") or "")
        explanation = str(problem.get("explanation") or "")
        rubric = [item for item in (problem.get("rubric") or []) if isinstance(item, dict)]
        rubric_text = " ".join(
            " ".join(
                [
                    str(item.get("criterion") or ""),
                    " ".join(str(value) for value in (item.get("expected_evidence") or [])),
                    " ".join(str(value) for value in (item.get("partial_credit_rules") or [])),
                ]
            )
            for item in rubric
        )
        combined = f"{question} {answer_text} {explanation} {rubric_text}".lower()
        concrete_cues = (
            "조건",
            "사례",
            "상황",
            "자료",
            "표",
            "그래프",
            "도표",
            "배열",
            "입력",
            "수치",
            "변수",
            "경우",
            "[",
            "$",
            "given",
            "case",
            "scenario",
            "condition",
            "table",
            "graph",
            "array",
        )
        work_cues = (
            "단계",
            "과정",
            "추적",
            "비교",
            "분석",
            "판단",
            "예측",
            "적용",
            "근거",
            "이유",
            "왜",
            "결론",
            "변화",
            "결과",
            "영향",
            "관계",
            "계산",
            "step",
            "trace",
            "process",
            "compare",
            "analyze",
            "apply",
            "reason",
            "result",
        )
        outcome_cues = (
            "결과",
            "결론",
            "따라서",
            "그러므로",
            "때문",
            "상승",
            "하락",
            "증가",
            "감소",
            "최종",
            "예측",
            "판단",
            "영향",
            "달라",
            "바뀌",
            "result",
            "therefore",
            "because",
            "conclusion",
            "effect",
        )
        source_rule_link_cues = (
            "근거",
            "관계",
            "원리",
            "규칙",
            "법칙",
            "공식",
            "조건",
            "비교",
            "반면",
            "같은",
            "다른",
            "하면",
            "경우",
            "source",
            "rule",
            "principle",
            "relationship",
            "compare",
        )
        evidence_count = sum(
            len(item.get("expected_evidence") or [])
            for item in rubric
        )
        return (
            any(cue in combined for cue in concrete_cues)
            and any(cue in combined for cue in work_cues)
            and any(cue in combined for cue in outcome_cues)
            and any(cue in combined for cue in source_rule_link_cues)
            and (len(rubric) >= 2 or evidence_count >= 3)
        )

    def _high_rigor_application_issues(
        self,
        *,
        problem: dict,
        high_rigor_profile: HighRigorGenerationProfile | None,
    ) -> list[str]:
        if not high_rigor_profile or not high_rigor_profile.enabled:
            return []

        question = str(problem.get("question") or "").lower()
        answer_text = str((problem.get("answer") or {}).get("text") or "").lower()
        explanation = str(problem.get("explanation") or "").lower()
        combined = f"{question} {answer_text} {explanation}"
        concrete_context_cues = (
            "조건",
            "상황",
            "사례",
            "예시",
            "입력",
            "주어진",
            "다음",
            "자료",
            "지문",
            "표",
            "그래프",
            "도표",
            "배열",
            "[",
            "값",
            "수치",
            "변수",
            "경우",
            "변화",
            "바뀌",
            "달라지",
            "반례",
            "오류",
            "잘못",
        )
        reasoning_cues = (
            "적용",
            "분석",
            "비교",
            "추론",
            "평가",
            "판단",
            "예측",
            "계산",
            "해석",
            "도출",
            "증명",
            "논증",
            "설계",
            "추적",
            "검토",
            "왜",
            "어떻게",
            "근거",
            "원인",
            "결과",
            "영향",
            "한계",
            "시간복잡도",
            "복잡도",
        )
        recall_only_patterns = (
            "무엇인가",
            "무엇인지",
            "정의",
            "의미를 쓰",
            "개념을 쓰",
            "가장 먼저",
            "첫 단계",
            "첫 번째 단계",
            "첫번째 단계",
            "두 단계를 서술",
            "나열하시오",
        )

        has_concrete_context = any(cue in question for cue in concrete_context_cues)
        has_reasoning_work = any(cue in combined for cue in reasoning_cues)
        issues: list[str] = []
        if not has_concrete_context:
            issues.append("high-rigor item must include a concrete condition, source evidence, case, input, or changed scenario")
        if not has_reasoning_work:
            issues.append("high-rigor item must require application, analysis, comparison, inference, evaluation, calculation, or error checking")
        if any(pattern in question for pattern in recall_only_patterns) and not (
            has_concrete_context and has_reasoning_work
        ):
            issues.append("high-rigor item is too close to recall or procedure listing")
        return list(dict.fromkeys(issues))

    def _high_rigor_cognitive_demand_issues(
        self,
        *,
        problem: dict,
        high_rigor_profile: HighRigorGenerationProfile | None,
    ) -> list[str]:
        if not high_rigor_profile or not high_rigor_profile.enabled:
            return []
        profile = problem.get("difficulty_profile") or {}
        if not isinstance(profile, dict):
            return []

        issues: list[str] = []
        try:
            demand_score = float(profile.get("cognitive_demand_score"))
        except (TypeError, ValueError):
            demand_score = None
        try:
            reasoning_steps = int(profile.get("reasoning_steps_required") or 0)
        except (TypeError, ValueError):
            reasoning_steps = 0

        is_multiple_choice = problem.get("type") == ProblemType.multiple_choice.value
        threshold = self._high_rigor_demand_threshold(high_rigor_profile)

        if not is_multiple_choice and demand_score is not None and demand_score < threshold:
            issues.append(f"high-rigor item cognitive_demand_score must be at least {threshold:.2f}")
        if not is_multiple_choice and high_rigor_profile.multi_step_required and reasoning_steps < 3:
            issues.append("high-rigor multi-step item must require at least three reasoning steps")
        return issues

    def _high_rigor_multiple_choice_issues(
        self,
        *,
        problem: dict,
        high_rigor_profile: HighRigorGenerationProfile | None,
    ) -> list[str]:
        if not high_rigor_profile or not high_rigor_profile.enabled:
            return []
        if problem.get("type") != ProblemType.multiple_choice.value:
            return []

        question = str(problem.get("question") or "").lower()
        combined = self._high_rigor_multiple_choice_text(problem)
        concrete_context_cues = (
            "조건",
            "상황",
            "사례",
            "입력",
            "주어진",
            "다음",
            "자료",
            "지문",
            "표",
            "그래프",
            "배열",
            "코드",
            "값",
            "수치",
            "변수",
            "변화",
            "바뀌",
            "달라지",
            "반례",
            "오류",
            "잘못",
            "같은",
            "case",
            "input",
            "condition",
            "scenario",
            "graph",
            "table",
            "code",
            "changed",
            "counterexample",
            "error",
        )
        reasoning_cues = (
            "적용",
            "분석",
            "비교",
            "추론",
            "평가",
            "판단",
            "예측",
            "계산",
            "해석",
            "도출",
            "증명",
            "논증",
            "설계",
            "추적",
            "검토",
            "근거",
            "원인",
            "결과",
            "영향",
            "한계",
            "시간복잡도",
            "복잡도",
            "수정",
            "반례",
            "왜",
            "어떻게",
            "관계",
            "application",
            "analyze",
            "compare",
            "infer",
            "evaluate",
            "predict",
            "calculate",
            "interpret",
            "trace",
            "debug",
            "justify",
            "evidence",
            "limitation",
            "complexity",
        )
        recall_only_patterns = (
            "무엇인가",
            "무엇인지",
            "정의",
            "의미",
            "개념을 쓰",
            "가장 먼저",
            "첫 단계",
            "첫 번째 단계",
            "첫번째 단계",
            "나열하시오",
            "다음 중 옳은 것은",
            "다음 중 맞는 것은",
            "which of the following is true",
            "which of the following is correct",
            "define",
            "definition",
        )
        broad_correctness_patterns = (
            "다음 중 옳은 것은",
            "다음 중 맞는 것은",
            "which of the following is true",
            "which of the following is correct",
        )

        profile = problem.get("difficulty_profile") or {}
        if not isinstance(profile, dict):
            profile = {}
        has_concrete_context = any(cue in question for cue in concrete_context_cues)
        has_reasoning_work = any(cue in combined for cue in reasoning_cues) or self._difficulty_profile_has_reasoning(profile)
        broad_correctness_stem = any(pattern in question for pattern in broad_correctness_patterns)

        issues: list[str] = []
        if not has_concrete_context:
            issues.append(
                "high-rigor multiple-choice item must include a concrete condition, case, source evidence, input, data, code, or changed scenario"
            )
        if not has_reasoning_work:
            issues.append("high-rigor multiple-choice item must require reasoning beyond recall")
        if any(pattern in question for pattern in recall_only_patterns) and not (
            has_concrete_context and has_reasoning_work and not broad_correctness_stem
        ):
            issues.append("high-rigor multiple-choice item is too close to recall or broad correctness checking")

        if profile:
            threshold = self._high_rigor_demand_threshold(high_rigor_profile)
            try:
                demand_score = float(profile.get("cognitive_demand_score"))
            except (TypeError, ValueError):
                demand_score = None
            try:
                reasoning_steps = int(profile.get("reasoning_steps_required") or 0)
            except (TypeError, ValueError):
                reasoning_steps = 0
            if demand_score is not None and demand_score < threshold:
                issues.append(f"high-rigor multiple-choice cognitive_demand_score must be at least {threshold:.2f}")
            if reasoning_steps < 2:
                issues.append("high-rigor multiple-choice item must require at least two reasoning steps")
            if high_rigor_profile.multi_step_required and reasoning_steps < 3:
                issues.append("high-rigor multi-step multiple-choice item must require at least three reasoning steps")

        issues.extend(self._high_rigor_multiple_choice_diagnostic_issues(problem))
        return list(dict.fromkeys(issues))

    def _high_rigor_multiple_choice_flags(self, issues: list[str]) -> list[QualityFlag]:
        flags: list[QualityFlag] = []
        for issue in issues:
            if "cognitive_demand_score" in issue or "reasoning steps" in issue:
                flags.append(QualityFlag.low_cognitive_demand)
            elif "distractors" in issue:
                flags.append(QualityFlag.item_model_quality_violation)
            elif "recall or broad correctness" in issue:
                flags.append(QualityFlag.definition_only_risk)
            elif "reasoning beyond recall" in issue:
                flags.append(QualityFlag.low_cognitive_demand)
            elif "concrete condition" in issue:
                flags.append(QualityFlag.weak_application_fit)
            else:
                flags.append(QualityFlag.item_model_quality_violation)
        return list(dict.fromkeys(flags))

    def _high_rigor_demand_threshold(self, high_rigor_profile: HighRigorGenerationProfile) -> float:
        intensity = high_rigor_profile.intensity.value
        if intensity == "advanced":
            return 0.58
        if intensity == "elite":
            return 0.68
        return 0.50

    def _difficulty_profile_has_reasoning(self, profile: dict) -> bool:
        try:
            reasoning_steps = int(profile.get("reasoning_steps_required") or 0)
        except (TypeError, ValueError):
            reasoning_steps = 0
        return reasoning_steps >= 2 or any(
            profile.get(field) is True
            for field in (
                "requires_transfer",
                "requires_calculation",
                "requires_comparison",
                "requires_error_analysis",
            )
        )

    def _high_rigor_multiple_choice_text(self, problem: dict) -> str:
        parts = [
            str(problem.get("question") or ""),
            str((problem.get("answer") or {}).get("text") or ""),
            str(problem.get("explanation") or ""),
            str(problem.get("item_model_id") or ""),
        ]
        choices = problem.get("choices") or []
        parts.extend(str(choice.get("text") or "") for choice in choices if isinstance(choice, dict))
        choice_explanations = problem.get("choice_explanations") or {}
        parts.extend(str(value) for value in choice_explanations.values())
        diagnostics = problem.get("choice_diagnostics") or []
        for diagnostic in diagnostics:
            if not isinstance(diagnostic, dict):
                continue
            parts.extend(
                str(diagnostic.get(field) or "")
                for field in ("mistake_type", "misconception_id", "why_plausible", "repair_strategy")
            )
        profile = problem.get("difficulty_profile") or {}
        if isinstance(profile, dict):
            parts.extend(str(value) for value in profile.values())
        return " ".join(parts).lower()

    def _high_rigor_multiple_choice_diagnostic_issues(self, problem: dict) -> list[str]:
        choices = [choice for choice in (problem.get("choices") or []) if isinstance(choice, dict)]
        answer_id = str((problem.get("answer") or {}).get("choice_id") or "").strip()
        incorrect_choice_ids = [
            str(choice.get("id") or "").strip()
            for choice in choices
            if str(choice.get("id") or "").strip() and str(choice.get("id") or "").strip() != answer_id
        ]
        if not incorrect_choice_ids:
            return []

        diagnostics_by_id = {
            str(item.get("choice_id") or "").strip(): item
            for item in (problem.get("choice_diagnostics") or [])
            if isinstance(item, dict)
        }
        incorrect_diagnostics = [diagnostics_by_id.get(choice_id) for choice_id in incorrect_choice_ids]
        if any(item is None for item in incorrect_diagnostics):
            return ["high-rigor multiple-choice distractors must diagnose distinct misconception or reasoning failures"]

        concrete_diagnostics = [item for item in incorrect_diagnostics if isinstance(item, dict)]
        why_texts = [self._normalize_for_overlap(str(item.get("why_plausible") or "")) for item in concrete_diagnostics]
        repair_texts = [self._normalize_for_overlap(str(item.get("repair_strategy") or "")) for item in concrete_diagnostics]
        mistake_types = {
            str(item.get("mistake_type") or "").strip().lower()
            for item in concrete_diagnostics
            if str(item.get("mistake_type") or "").strip().lower() not in {"", "none"}
        }
        misconception_ids = {
            str(item.get("misconception_id") or "").strip().lower()
            for item in concrete_diagnostics
            if str(item.get("misconception_id") or "").strip()
        }

        issues: list[str] = []
        if any(len(text) < 12 for text in why_texts) or any(len(text) < 12 for text in repair_texts):
            issues.append("high-rigor multiple-choice distractors must diagnose distinct misconception or reasoning failures")

        diagnostic_keys = {
            "|".join(
                [
                    str(item.get("mistake_type") or "").strip().lower(),
                    str(item.get("misconception_id") or "").strip().lower(),
                    self._normalize_for_overlap(str(item.get("why_plausible") or "")),
                    self._normalize_for_overlap(str(item.get("repair_strategy") or "")),
                ]
            )
            for item in concrete_diagnostics
        }
        if len(diagnostic_keys) < 2 and len(incorrect_choice_ids) >= 2:
            issues.append("high-rigor multiple-choice distractors must diagnose distinct misconception or reasoning failures")

        same_mistake_type = len(mistake_types) <= 1
        same_repair = len(set(repair_texts)) <= 1
        all_generic_repairs = bool(repair_texts) and all(self._is_generic_distractor_repair(text) for text in repair_texts)
        if same_mistake_type and (same_repair or all_generic_repairs):
            issues.append("high-rigor multiple-choice distractors must diagnose distinct misconception or reasoning failures")

        if self._texts_are_almost_identical(why_texts):
            issues.append("high-rigor multiple-choice distractors must diagnose distinct misconception or reasoning failures")

        distinct_signal_count = len(mistake_types | misconception_ids | set(why_texts) | set(repair_texts))
        if distinct_signal_count < 2:
            issues.append("high-rigor multiple-choice distractors must diagnose distinct misconception or reasoning failures")

        return list(dict.fromkeys(issues))

    def _is_generic_distractor_repair(self, text: str) -> bool:
        generic_patterns = (
            "다시 확인",
            "자료를 다시",
            "개념을 다시",
            "복습",
            "review",
            "check again",
            "revisit",
        )
        return len(text) < 18 or any(pattern in text for pattern in generic_patterns)

    def _texts_are_almost_identical(self, texts: list[str]) -> bool:
        normalized = [text for text in texts if text]
        if len(normalized) < 2:
            return False
        if len(set(normalized)) == 1:
            return True
        first = normalized[0]
        return all(self._token_jaccard(first, text) >= 0.88 for text in normalized[1:])

    def _high_rigor_reject_flags(self) -> set[QualityFlag]:
        return {
            QualityFlag.insufficient_source,
            QualityFlag.unsupported_source,
            QualityFlag.weak_source_overlap,
            QualityFlag.definition_only_risk,
            QualityFlag.blueprint_mismatch,
            QualityFlag.shallow_deep_question,
            QualityFlag.weak_application_fit,
            QualityFlag.weak_concept_integration,
            QualityFlag.low_cognitive_demand,
            QualityFlag.weak_rubric_evidence,
            QualityFlag.item_model_quality_violation,
            QualityFlag.answer_leak,
            QualityFlag.invalid_latex,
        }

    def _professor_review_issues(self, problem: dict) -> list[str]:
        issues: list[str] = []
        checklist = problem.get("teacher_review_checklist") or {}
        if isinstance(checklist, dict):
            issues.extend(str(issue) for issue in (checklist.get("required_revisions") or []) if str(issue).strip())
        grade_score = problem.get("professor_grade_score") or {}
        if isinstance(grade_score, dict):
            issues.extend(str(issue) for issue in (grade_score.get("reject_reasons") or []) if str(issue).strip())
        return list(dict.fromkeys(issues))

    def _choice_quality_check(self, problem: dict) -> ChoiceQualityCheck:
        if problem.get("type") != "multiple_choice":
            return ChoiceQualityCheck(flags=[], issues=[])

        flags: list[QualityFlag] = []
        issues: list[str] = []
        question = str(problem.get("question") or "").strip().lower()
        choices = [choice for choice in (problem.get("choices") or []) if isinstance(choice, dict)]
        answer_id = str((problem.get("answer") or {}).get("choice_id") or "").strip()

        unfocused_stem_patterns = (
            "다음 중 옳은 것은",
            "다음 중 맞는 것은",
            "which of the following is true",
            "which of the following is correct",
            "all of the following",
            "except",
        )
        if any(pattern in question for pattern in unfocused_stem_patterns):
            flags.append(QualityFlag.unfocused_stem)
            issues.append("stem is too broad or uses a known item-writing flaw pattern")

        all_or_none_patterns = (
            "all of the above",
            "none of the above",
            "위의 내용 모두",
            "위 보기 모두",
            "모두 정답",
            "모두 옳",
            "모두 맞",
            "정답 없음",
            "해당 없음",
            "답이 없음",
            "모두 아니다",
        )
        if any(
            any(pattern in str(choice.get("text") or "").strip().lower() for pattern in all_or_none_patterns)
            for choice in choices
        ):
            flags.append(QualityFlag.all_or_none_option)
            issues.append("choice set contains all/none-of-the-above style option")

        lengths_by_id = {
            str(choice.get("id") or "").strip(): len(str(choice.get("text") or "").strip())
            for choice in choices
        }
        lengths = [length for length in lengths_by_id.values() if length > 0]
        if len(lengths) >= 4 and answer_id in lengths_by_id:
            median_length = sorted(lengths)[len(lengths) // 2]
            answer_length = lengths_by_id[answer_id]
            longest = max(lengths)
            shortest = min(lengths)
            if (
                longest - shortest >= 45
                and answer_length == longest
                and median_length > 0
                and longest / median_length >= 1.8
            ):
                flags.append(QualityFlag.option_length_cue)
                issues.append("correct choice is much longer than the other choices")
            if shortest <= 12 and answer_length == shortest and longest >= max(shortest * 3, 45):
                flags.append(QualityFlag.option_length_cue)
                issues.append("correct choice is much shorter than the other choices")

        normalized_choices = [
            self._normalize_for_overlap(str(choice.get("text") or ""))
            for choice in choices
        ]
        for index, left in enumerate(normalized_choices):
            if len(left) < 8:
                continue
            for right in normalized_choices[index + 1 :]:
                if len(right) < 8:
                    continue
                if self._token_jaccard(left, right) >= 0.82 or left in right or right in left:
                    flags.append(QualityFlag.overlapping_options)
                    issues.append("two or more choices overlap too strongly")
                    break
            if QualityFlag.overlapping_options in flags:
                break

        absolute_terms = ("항상", "절대", "전혀", "무조건", "반드시", "always", "never")
        absolute_distractor_count = 0
        for choice in choices:
            choice_id = str(choice.get("id") or "").strip()
            text = str(choice.get("text") or "").strip().lower()
            if choice_id != answer_id and any(term in text for term in absolute_terms):
                absolute_distractor_count += 1
        if absolute_distractor_count >= 2:
            flags.append(QualityFlag.absolute_wording)
            issues.append("multiple distractors use absolute wording that may cue test-wise guessing")

        implausible_patterns = (
            "자료 내용과 관계없는",
            "자료와 관계없는",
            "설명 없이 암기",
            "근거 없이 암기",
            "암기만 하면",
            "반대 의미로만",
        )
        if any(
            choice.get("id") != answer_id
            and any(pattern in str(choice.get("text") or "") for pattern in implausible_patterns)
            for choice in choices
        ):
            flags.append(QualityFlag.implausible_distractor)
            issues.append("one or more distractors are visibly implausible rather than conceptually plausible")

        diagnostic_issues = self._choice_diagnostic_quality_issues(problem=problem, answer_id=answer_id)
        if diagnostic_issues:
            flags.append(QualityFlag.implausible_distractor)
            issues.extend(diagnostic_issues)

        return ChoiceQualityCheck(flags=list(dict.fromkeys(flags)), issues=list(dict.fromkeys(issues)))


    def _choice_diagnostic_quality_issues(self, *, problem: dict, answer_id: str) -> list[str]:
        diagnostics = [item for item in (problem.get("choice_diagnostics") or []) if isinstance(item, dict)]
        if not diagnostics:
            return []
        issues: list[str] = []
        giveaway_patterns = ("오답", "틀린", "틀림", "정답이 아님", "자료에 없는", "관계없는", "말이 안")
        generic_patterns = ("부족", "헷갈림", "잘못", "오류")
        for diagnostic in diagnostics:
            choice_id = str(diagnostic.get("choice_id") or "").strip()
            if choice_id == answer_id or diagnostic.get("is_correct") is True:
                continue
            why_plausible = str(diagnostic.get("why_plausible") or "").strip()
            repair_strategy = str(diagnostic.get("repair_strategy") or "").strip()
            if len(why_plausible) < 12:
                issues.append("incorrect choice diagnostic why_plausible is too thin")
            if len(repair_strategy) < 12:
                issues.append("incorrect choice diagnostic repair_strategy is too thin")
            if any(pattern in why_plausible for pattern in giveaway_patterns):
                issues.append("incorrect choice diagnostic reveals that the choice is merely wrong")
            if why_plausible in generic_patterns or repair_strategy in generic_patterns:
                issues.append("incorrect choice diagnostic is too generic")
        return list(dict.fromkeys(issues))

    def _rubric_quality_check(
        self,
        *,
        problem: dict,
        request: GenerateProblemRequest | None,
    ) -> RubricQualityCheck:
        if problem.get("type") != "short_answer" or request is None:
            return RubricQualityCheck(flags=[], issues=[])
        if request.depth != ProblemDepth.deep and request.target_rigor != TargetRigor.high:
            return RubricQualityCheck(flags=[], issues=[])

        rubric = [item for item in (problem.get("rubric") or []) if isinstance(item, dict)]
        if not rubric:
            return RubricQualityCheck(flags=[QualityFlag.weak_rubric_evidence], issues=["rubric is missing"])

        evidence_cues = ("근거", "자료", "관계", "조건", "분석", "비교", "적용", "영향", "이유", "판단")
        evidence_items = 0
        issues: list[str] = []
        for item in rubric:
            criterion = str(item.get("criterion") or "")
            expected_evidence = item.get("expected_evidence") or []
            for list_field in ("expected_evidence", "common_mistakes", "partial_credit_rules"):
                value = item.get(list_field)
                if value is not None and not isinstance(value, list):
                    issues.append(f"rubric.{list_field} must be a list when provided")

            if isinstance(expected_evidence, list) and any(str(value).strip() for value in expected_evidence):
                evidence_items += 1
                continue
            if any(cue in criterion for cue in evidence_cues):
                evidence_items += 1

        if request.depth == ProblemDepth.deep and evidence_items < 2:
            issues.append("deep short_answer rubric should include at least two evidence-aware criteria")
        elif request.target_rigor == TargetRigor.high and evidence_items < 1:
            issues.append("high-rigor short_answer rubric should include evidence-aware criteria")
        issues.extend(self._rubric_discriminability_issues(rubric))

        flags = [QualityFlag.weak_rubric_evidence] if issues else []
        return RubricQualityCheck(flags=flags, issues=list(dict.fromkeys(issues)))

    def _rubric_discriminability_issues(self, rubric: list[dict]) -> list[str]:
        if len(rubric) < 2:
            return []
        item_texts = [
            " ".join(
                [
                    str(item.get("criterion") or ""),
                    " ".join(str(value) for value in (item.get("expected_evidence") or [])),
                ]
            )
            for item in rubric
        ]
        evidence_texts = [
            " ".join(str(value) for value in (item.get("expected_evidence") or [])).strip()
            for item in rubric
        ]
        normalized_items = [self._normalize_quality_text(text) for text in item_texts if self._normalize_quality_text(text)]
        normalized_evidence = [
            self._normalize_quality_text(text) for text in evidence_texts if self._normalize_quality_text(text)
        ]
        issues: list[str] = []
        if normalized_items and len(set(normalized_items)) < len(normalized_items):
            issues.append("rubric_items_not_distinct")
        if normalized_evidence and len(set(normalized_evidence)) < len(normalized_evidence):
            issues.append("rubric_expected_evidence_too_overlapping")
        if self._max_quality_token_similarity(evidence_texts) > 0.84:
            issues.append("rubric_expected_evidence_too_overlapping")

        token_sets = [self._content_tokens(text) for text in item_texts]
        token_counts: dict[str, int] = {}
        for tokens in token_sets:
            for token in tokens:
                token_counts[token] = token_counts.get(token, 0) + 1
        if token_sets and all(not any(token_counts.get(token, 0) == 1 for token in tokens) for tokens in token_sets):
            issues.append("rubric_items_not_distinct")
        if self._condition_missing_rubric_proxy_scores_full(rubric):
            issues.append("condition_missing_answer_scores_too_high")
        return list(dict.fromkeys(issues))

    def _condition_missing_rubric_proxy_scores_full(self, rubric: list[dict]) -> bool:
        if len(rubric) < 2:
            return False
        evidence_texts = [
            " ".join(str(value) for value in (item.get("expected_evidence") or [])).strip()
            for item in rubric
        ]
        normalized_evidence = [
            self._normalize_quality_text(text) for text in evidence_texts if self._normalize_quality_text(text)
        ]
        has_overlapping_evidence = (
            bool(normalized_evidence)
            and (
                len(set(normalized_evidence)) < len(normalized_evidence)
                or self._max_quality_token_similarity(evidence_texts) > 0.84
            )
        )
        if not has_overlapping_evidence:
            return False
        largest_index = max(range(len(rubric)), key=lambda index: float(rubric[index].get("points") or 0))
        proxy_answer = " ".join(
            " ".join(str(value) for value in (item.get("expected_evidence") or []))
            or str(item.get("criterion") or "")
            for index, item in enumerate(rubric)
            if index != largest_index
        )
        if not proxy_answer.strip():
            return False
        return all(self._rubric_item_proxy_matches(item=item, answer_text=proxy_answer) for item in rubric)

    def _rubric_item_proxy_matches(self, *, item: dict, answer_text: str) -> bool:
        expected_evidence = [str(value).strip() for value in (item.get("expected_evidence") or []) if str(value).strip()]
        if expected_evidence:
            return any(self._quality_term_present(evidence, answer_text) for evidence in expected_evidence)
        criterion_tokens = self._content_tokens(str(item.get("criterion") or ""))
        answer_tokens = self._content_tokens(answer_text)
        return bool(criterion_tokens and len(criterion_tokens & answer_tokens) >= min(2, len(criterion_tokens)))

    def _quality_term_present(self, term: str, text: str) -> bool:
        normalized_term = self._normalize_quality_text(term)
        normalized_text = self._normalize_quality_text(text)
        if normalized_term and normalized_term in normalized_text:
            return True
        term_tokens = list(self._content_tokens(term))
        text_tokens = list(self._content_tokens(text))
        if not term_tokens:
            return False
        matched = sum(1 for token in term_tokens if any(token in other or other in token for other in text_tokens))
        return matched >= max(1, min(len(term_tokens), round(len(term_tokens) * 0.5)))

    def _max_quality_token_similarity(self, texts: list[str]) -> float:
        token_sets = [self._content_tokens(text) for text in texts if self._content_tokens(text)]
        max_similarity = 0.0
        for index, left in enumerate(token_sets):
            for right in token_sets[index + 1 :]:
                max_similarity = max(max_similarity, len(left & right) / max(1, len(left | right)))
        return max_similarity

    def _normalize_quality_text(self, text: str) -> str:
        return re.sub(r"\s+", " ", str(text or "").strip().lower())

    def _item_model_quality_check(
        self,
        *,
        problem: dict,
        request: GenerateProblemRequest | None,
        retrieved_chunks: list[RetrievedChunk] | None,
    ) -> ItemModelQualityCheck:
        if request is None or not self._strict_item_model_checks_enabled(request):
            return ItemModelQualityCheck(flags=[], issues=[])
        try:
            item_model_id = ItemModelId(str(problem.get("item_model_id") or ""))
        except ValueError:
            return ItemModelQualityCheck(flags=[], issues=[])

        issues: list[str] = []
        if item_model_id == ItemModelId.data_interpretation:
            issues.extend(self._data_interpretation_model_issues(problem, retrieved_chunks or []))
        elif item_model_id == ItemModelId.misconception_contrast:
            issues.extend(self._misconception_contrast_model_issues(problem))
        elif item_model_id == ItemModelId.error_detection:
            issues.extend(self._error_detection_model_issues(problem))
        elif item_model_id in {ItemModelId.case_based_application, ItemModelId.transfer_to_new_context}:
            issues.extend(self._transfer_model_issues(problem))
        elif item_model_id == ItemModelId.concept_comparison:
            issues.extend(self._comparison_model_issues(problem, retrieved_chunks or []))
        elif item_model_id == ItemModelId.evidence_selection:
            issues.extend(self._evidence_selection_model_issues(problem))

        flags = [QualityFlag.item_model_quality_violation] if issues else []
        return ItemModelQualityCheck(flags=flags, issues=list(dict.fromkeys(issues)))

    def _kernel_obligation_issues(
        self,
        *,
        problem: dict,
        request: GenerateProblemRequest | None,
        retrieved_chunks: list[RetrievedChunk] | None,
        content_atoms: list[ContentAtom],
        problem_kernel_plan: ProblemKernelPlan | None,
    ) -> list[str]:
        if problem_kernel_plan is None:
            return []
        report = EvidenceObligationEvaluator().evaluate(
            problem_data=problem,
            content_atoms=content_atoms,
            problem_kernel_plan=problem_kernel_plan,
            cited_chunks=retrieved_chunks or [],
        )
        return report.issues
        atom_by_id = {atom.atom_id: atom for atom in content_atoms}
        selected_atoms = [
            atom_by_id[atom_id]
            for atom_id in problem_kernel_plan.content_atom_ids
            if atom_id in atom_by_id
        ]
        if not selected_atoms and content_atoms:
            selected_atoms = content_atoms[:4]

        issues: list[str] = []
        if problem_kernel_plan.failure_reason:
            issues.append(f"kernel planning failed: {problem_kernel_plan.failure_reason}")
        if not selected_atoms:
            issues.append("kernel plan has no selected content atoms")
            return issues

        cited_ids = set(problem.get("source_chunk_ids") or [])
        if not cited_ids:
            issues.append("kernel plan requires cited source chunk ids")
        selected_cited = [atom for atom in selected_atoms if atom.source_chunk_id in cited_ids]
        if not selected_cited:
            issues.append("kernel plan selected atoms are not cited by source_chunk_ids")

        selected_atom_types = {atom.atom_type for atom in selected_atoms}
        for obligation in problem_kernel_plan.required_evidence_roles:
            if not obligation.required:
                continue
            role_atom_types = self._kernel_role_atom_types(obligation.role)
            role_atoms = [atom for atom in selected_atoms if atom.atom_type in role_atom_types]
            if not role_atoms:
                issues.append(f"kernel evidence obligation missing source atom for role={obligation.role.value}")
                continue
            if obligation.must_be_cited and not any(atom.source_chunk_id in cited_ids for atom in role_atoms):
                issues.append(f"kernel evidence role={obligation.role.value} must be cited")
            for placement in obligation.must_appear_in:
                placement_text = self._kernel_placement_text(problem, placement)
                if not self._kernel_atom_terms_appear(role_atoms, placement_text):
                    issues.append(
                        f"kernel evidence role={obligation.role.value} not linked in {placement}"
                    )

        if problem_kernel_plan.kernel_type == ProblemKernelType.compute_from_given:
            formula_or_rule_atoms = [
                atom
                for atom in selected_atoms
                if atom.atom_type in {ContentAtomType.formula, ContentAtomType.rule}
            ]
            if not formula_or_rule_atoms:
                issues.append("compute_from_given kernel requires a formula or rule atom")
            elif not self._kernel_atom_terms_appear(formula_or_rule_atoms, self._kernel_placement_text(problem, "explanation")):
                issues.append("compute_from_given kernel explanation must cite formula/rule evidence")

        if problem_kernel_plan.kernel_type == ProblemKernelType.diagnose_error:
            rule_atoms = [
                atom
                for atom in selected_atoms
                if atom.atom_type
                in {ContentAtomType.rule, ContentAtomType.procedure, ContentAtomType.formula, ContentAtomType.condition_exception}
            ]
            if self._error_detection_model_issues(problem):
                issues.append("diagnose_error kernel must identify and correct a violated source rule")
            elif rule_atoms and not self._kernel_atom_terms_appear(rule_atoms, self._kernel_placement_text(problem, "explanation")):
                issues.append("diagnose_error kernel explanation must identify the violated source rule/procedure")

        if problem_kernel_plan.kernel_type == ProblemKernelType.evidence_to_claim:
            text = self._calculation_solution_text(problem).lower()
            if not any(cue in text for cue in ("근거", "자료", "evidence", "source", "because", "supports", "뒷받침")):
                issues.append("evidence_to_claim kernel must explicitly connect claim to cited evidence")
            evidence_atoms = [
                atom
                for atom in selected_atoms
                if atom.atom_type
                in {ContentAtomType.evidence_claim, ContentAtomType.data_table, ContentAtomType.cause_effect, ContentAtomType.comparison}
            ]
            if evidence_atoms and not self._kernel_atom_terms_appear(evidence_atoms, self._kernel_placement_text(problem, "explanation")):
                issues.append("evidence_to_claim kernel explanation must use selected source evidence terms")

        if problem_kernel_plan.kernel_type == ProblemKernelType.compare_boundary:
            if len({atom.source_chunk_id for atom in selected_atoms}) < 2 and not any(
                atom.atom_type in {ContentAtomType.comparison, ContentAtomType.classification}
                for atom in selected_atoms
            ):
                issues.append("compare_boundary kernel needs contrast evidence or at least two cited concepts")
            boundary_atoms = [
                atom for atom in selected_atoms if atom.atom_type in {ContentAtomType.comparison, ContentAtomType.classification}
            ]
            if boundary_atoms and not self._kernel_atom_terms_appear(boundary_atoms, self._kernel_placement_text(problem, "explanation")):
                issues.append("compare_boundary kernel explanation must include boundary or contrast evidence terms")

        if problem_kernel_plan.kernel_type == ProblemKernelType.trace_process:
            procedure_atoms = [
                atom for atom in selected_atoms if atom.atom_type in {ContentAtomType.procedure, ContentAtomType.code_state}
            ]
            trace_text = " ".join(
                [
                    self._kernel_placement_text(problem, "answer"),
                    self._kernel_placement_text(problem, "rubric"),
                ]
            )
            if procedure_atoms and not self._kernel_atom_terms_appear(procedure_atoms, trace_text):
                issues.append("trace_process kernel answer/rubric must reference ordered procedure evidence")

        if problem_kernel_plan.requires_distinct_distractors:
            diagnostic_issues = self._choice_diagnostic_quality_issues(
                problem=problem,
                answer_id=str((problem.get("answer") or {}).get("choice_id") or ""),
            )
            issues.extend(diagnostic_issues)

        return list(dict.fromkeys(issues))

    def _kernel_role_atom_types(self, role: EvidenceRole) -> set[ContentAtomType]:
        return {
            EvidenceRole.definition: {ContentAtomType.definition, ContentAtomType.classification},
            EvidenceRole.rule: {ContentAtomType.rule, ContentAtomType.classification, ContentAtomType.condition_exception},
            EvidenceRole.formula: {ContentAtomType.formula},
            EvidenceRole.condition: {ContentAtomType.condition_exception, ContentAtomType.rule, ContentAtomType.cause_effect},
            EvidenceRole.exception: {ContentAtomType.condition_exception},
            EvidenceRole.contrast: {ContentAtomType.comparison, ContentAtomType.classification},
            EvidenceRole.example: {ContentAtomType.example_case},
            EvidenceRole.procedure_step: {ContentAtomType.procedure, ContentAtomType.code_state, ContentAtomType.rule},
            EvidenceRole.data_point: {ContentAtomType.data_table, ContentAtomType.formula},
            EvidenceRole.source_claim: {
                ContentAtomType.evidence_claim,
                ContentAtomType.cause_effect,
                ContentAtomType.comparison,
                ContentAtomType.procedure,
                ContentAtomType.rule,
            },
        }.get(role, set())

    def _kernel_atom_terms_appear(self, atoms: list[ContentAtom], text: str) -> bool:
        if not text.strip():
            return False
        atom_tokens: set[str] = set()
        for atom in atoms:
            atom_tokens.update(self._kernel_evidence_tokens(" ".join([atom.statement, atom.evidence_quote or ""])))
        if not atom_tokens:
            return True
        text_tokens = self._kernel_evidence_tokens(text)
        return bool(atom_tokens & text_tokens)

    def _kernel_evidence_tokens(self, text: str) -> set[str]:
        tokens = set(self._content_tokens(text))
        suffixes = (
            "입니다",
            "이다",
            "이며",
            "이고",
            "에서",
            "으로",
            "로",
            "은",
            "는",
            "이",
            "가",
            "을",
            "를",
            "의",
            "과",
            "와",
        )
        for token in list(tokens):
            for suffix in suffixes:
                if token.endswith(suffix) and len(token) > len(suffix) + 1:
                    tokens.add(token[: -len(suffix)])
        return {token for token in tokens if len(token) >= 2}

    def _kernel_placement_text(self, problem: dict, placement: str) -> str:
        if placement == "question":
            return str(problem.get("question") or "")
        if placement == "answer":
            return str((problem.get("answer") or {}).get("text") or "")
        if placement == "explanation":
            return str(problem.get("explanation") or "")
        if placement == "distractor":
            answer_id = str((problem.get("answer") or {}).get("choice_id") or "")
            return " ".join(
                str(choice.get("text") or "")
                for choice in (problem.get("choices") or [])
                if isinstance(choice, dict) and str(choice.get("id") or "") != answer_id
            )
        if placement == "rubric":
            return " ".join(
                " ".join(
                    [
                        str(item.get("criterion") or ""),
                        " ".join(str(value) for value in (item.get("expected_evidence") or [])),
                        " ".join(str(value) for value in (item.get("partial_credit_rules") or [])),
                    ]
                )
                for item in (problem.get("rubric") or [])
                if isinstance(item, dict)
            )
        return ""

    def _kernel_numeric_grounding_issues(
        self,
        *,
        problem: dict,
        retrieved_chunks: list[RetrievedChunk],
    ) -> list[str]:
        question_text = str(problem.get("question") or "")
        choices_text = " ".join(str(choice.get("text") or "") for choice in (problem.get("choices") or []) if isinstance(choice, dict))
        source_text = self._source_text(retrieved_chunks)
        solution_text = self._calculation_solution_text(problem)
        allowed = set(re.findall(r"-?\d+(?:\.\d+)?", f"{question_text} {choices_text} {source_text}"))
        for left, operator, right in self._arithmetic_expressions(solution_text):
            expected = self._evaluate_expression(left, operator, right)
            if expected is not None:
                allowed.add(f"{expected:g}")
        suspicious = [
            number
            for number in re.findall(r"-?\d+(?:\.\d+)?", solution_text)
            if number not in allowed and number not in {"0", "1", "2", "3", "4", "5"}
        ]
        if suspicious:
            return ["answer/explanation contains numbers not given in stem/source or derived: " + ", ".join(sorted(set(suspicious))[:5])]
        return []

    def _strict_item_model_checks_enabled(self, request: GenerateProblemRequest) -> bool:
        return (
            request.quality_mode == QualityMode.strict
            or request.target_rigor == TargetRigor.high
            or request.depth == ProblemDepth.deep
            or request.difficulty.value == "hard"
            or request.bloom_level in {BloomLevel.analyze, BloomLevel.evaluate, BloomLevel.create}
        )

    def _data_interpretation_model_issues(
        self,
        problem: dict,
        retrieved_chunks: list[RetrievedChunk],
    ) -> list[str]:
        text = self._all_problem_text(problem)
        source_text = self._source_text(retrieved_chunks)
        issues: list[str] = []
        source_has_values = bool(re.search(r"\d+(?:\.\d+)?", source_text))
        output_has_values = bool(re.search(r"\d+(?:\.\d+)?", text))
        data_label_cues = ("표", "그래프", "수치", "자료값", "데이터", "행", "열")
        if source_has_values and not output_has_values:
            issues.append("data_interpretation item must cite concrete source values")
        elif not any(cue in text for cue in data_label_cues):
            issues.append("data_interpretation item must cite a table, graph, or data label")
        conclusion_cues = (
            "비교",
            "차이",
            "증가",
            "감소",
            "높",
            "낮",
            "가장",
            "결론",
            "판단",
            "해석",
            "원인",
        )
        if not any(cue in text for cue in conclusion_cues):
            issues.append("data_interpretation item must require a comparison, interpretation, or conclusion")
        return issues

    def _misconception_contrast_model_issues(self, problem: dict) -> list[str]:
        if problem.get("type") != ProblemType.multiple_choice.value:
            return []
        diagnostics = [item for item in (problem.get("choice_diagnostics") or []) if isinstance(item, dict)]
        incorrect = [item for item in diagnostics if item.get("is_correct") is not True]
        if len(incorrect) < 2:
            return ["misconception_contrast item should include at least two diagnostic distractors"]

        misconception_keys = [
            self._normalize_for_overlap(
                str(item.get("misconception_id") or item.get("why_plausible") or item.get("mistake_type") or "")
            )
            for item in incorrect
        ]
        if len(set(misconception_keys)) < min(2, len(misconception_keys)):
            return ["misconception_contrast distractors should target distinct misconceptions"]
        return []

    def _error_detection_model_issues(self, problem: dict) -> list[str]:
        question_text = str(problem.get("question") or "")
        correction_text = self._calculation_solution_text(problem)
        error_cues = ("오류", "잘못", "틀린", "반례", "누락", "빠뜨", "error", "wrong")
        correction_cues = ("수정", "고쳐", "바로잡", "왜", "근거", "때문", "반대로", "누락")
        issues: list[str] = []
        if not any(cue in question_text.lower() for cue in error_cues):
            issues.append("error_detection item must explicitly ask learners to find an error")
        if not any(cue in correction_text.lower() for cue in error_cues + correction_cues):
            issues.append("error_detection answer or explanation must identify and correct the error")
        return issues

    def _transfer_model_issues(self, problem: dict) -> list[str]:
        question_text = str(problem.get("question") or "")
        transfer_cues = ("조건", "상황", "사례", "적용", "판단", "예측", "변화", "경우", "새로운")
        if not any(cue in question_text for cue in transfer_cues):
            return ["transfer/application item must include a concrete condition, case, or decision context"]
        return []

    def _comparison_model_issues(self, problem: dict, retrieved_chunks: list[RetrievedChunk]) -> list[str]:
        text = f"{self._all_problem_text(problem)} {self._source_text(retrieved_chunks)}"
        comparison_cues = ("비교", "차이", "공통", "반면", "대조", "구분", "같은", "다른")
        if not any(cue in text for cue in comparison_cues):
            return ["concept_comparison item must include an explicit comparison basis"]
        return []

    def _evidence_selection_model_issues(self, problem: dict) -> list[str]:
        question_text = str(problem.get("question") or "").lower()
        solution_text = self._calculation_solution_text(problem).lower()
        evidence_cues = (
            "근거",
            "자료",
            "지문",
            "문장",
            "부분",
            "인용",
            "evidence",
            "source",
            "source-aligned",
        )
        selection_cues = ("고르", "선택", "찾", "제시", "뒷받침", "support", "cite", "select")
        claim_eval_cues = (
            "판단",
            "평가",
            "타당",
            "일치",
            "적절",
            "결론",
            "주장",
            "근거와",
            "자료에 비추어",
            "가장 잘",
            "연결",
            "supported conclusion",
            "source-grounded",
            "consistent with",
        )
        claim_cues = (
            "주장",
            "결론",
            "판단",
            "설명",
            "이유",
            "때문",
            "연결",
            "뒷받침",
            "일치",
            "타당",
            "claim",
            "conclusion",
            "support",
        )
        issues: list[str] = []
        has_question_evidence = any(cue in question_text for cue in evidence_cues)
        asks_selection = any(cue in question_text for cue in selection_cues)
        asks_claim_evaluation = any(cue in question_text for cue in claim_eval_cues)
        if not (has_question_evidence and (asks_selection or asks_claim_evaluation)):
            issues.append(
                "evidence_analysis MCQ must ask for source-evidence selection or source-grounded claim evaluation"
            )
        if not any(cue in solution_text for cue in evidence_cues) or not any(cue in solution_text for cue in claim_cues):
            issues.append("evidence_analysis MCQ explanation must connect selected answer to source evidence")
        return issues

    def _max_verbatim_source_overlap(
        self,
        *,
        generated_text: str,
        cited_chunks: list[RetrievedChunk],
    ) -> int:
        generated = self._normalize_for_overlap(generated_text)
        if not generated:
            return 0
        max_overlap = 0
        window_size = 90
        for chunk in cited_chunks:
            source = self._normalize_for_overlap(chunk.content)
            if len(source) < window_size:
                continue
            for start in range(0, len(source) - window_size + 1, 15):
                window = source[start : start + window_size]
                if window in generated:
                    max_overlap = max(max_overlap, len(window))
        return max_overlap

    def _grounding_text(self, problem: dict) -> str:
        parts = [
            str(problem.get("question") or ""),
            str((problem.get("answer") or {}).get("text") or ""),
            str(problem.get("explanation") or ""),
        ]
        choices = problem.get("choices") or []
        parts.extend(str(choice.get("text") or "") for choice in choices if isinstance(choice, dict))
        choice_explanations = problem.get("choice_explanations") or {}
        parts.extend(str(value) for value in choice_explanations.values())
        rubric = problem.get("rubric") or []
        parts.extend(str(item.get("criterion") or "") for item in rubric if isinstance(item, dict))
        return " ".join(parts)

    def _content_tokens(self, text: str) -> set[str]:
        return {
            token
            for token in re.findall(r"[A-Za-z0-9가-힣]+", text.lower())
            if len(token) >= 2 and token not in self._stopwords()
        }

    def _normalize_for_overlap(self, text: str) -> str:
        return re.sub(r"\s+", " ", str(text or "")).strip().lower()

    def _token_jaccard(self, left: str, right: str) -> float:
        left_tokens = self._content_tokens(left)
        right_tokens = self._content_tokens(right)
        if not left_tokens or not right_tokens:
            return 0.0
        return len(left_tokens & right_tokens) / len(left_tokens | right_tokens)

    def _prompt_injection_leak(self, problem: dict) -> bool:
        text = self._all_problem_text(problem).lower()
        return contains_unsafe_instruction_text(text)

    def _answer_leak(self, problem: dict) -> bool:
        question = str(problem.get("question") or "").lower()
        answer = problem.get("answer") or {}
        answer_id = str(answer.get("choice_id") or "").strip().lower()
        if problem.get("type") == "multiple_choice" and answer_id:
            leak_patterns = (
                f"정답은 {answer_id}",
                f"{answer_id}가 정답",
                f"{answer_id}번이 정답",
                f"answer is {answer_id}",
                f"correct answer is {answer_id}",
            )
            if any(pattern in question for pattern in leak_patterns):
                return True
        answer_text = str(answer.get("text") or "").strip()
        if answer_text and len(answer_text) >= 12 and answer_text.lower() in question:
            return True
        return False

    def _invalid_latex(self, problem: dict) -> bool:
        text = self._all_problem_text(problem)
        normalized = re.sub(r"\\\$", "", text)
        if normalized.count("$$") % 2 != 0:
            return True
        if any(not match.strip() for match in re.findall(r"\$\$(.*?)\$\$", normalized, flags=re.DOTALL)):
            return True
        without_display_math = re.sub(r"\$\$.*?\$\$", "", normalized, flags=re.DOTALL)
        if without_display_math.count("$") % 2 != 0:
            return True
        return any(not match.strip() for match in re.findall(r"\$(.*?)\$", without_display_math, flags=re.DOTALL))

    def _shallow_deep_question(self, *, problem: dict, request: GenerateProblemRequest) -> bool:
        if request.depth != ProblemDepth.deep:
            return False
        if problem.get("type") != "short_answer":
            return True
        rubric = problem.get("rubric") or []
        if len(rubric) < 2:
            return True
        question = str(problem.get("question") or "").lower()
        deep_cues = (
            "분석",
            "비교",
            "적용",
            "평가",
            "판단",
            "예측",
            "왜",
            "어떻게",
            "조건",
            "상황",
            "관계",
            "영향",
            "근거",
        )
        return not any(cue in question for cue in deep_cues)

    def _all_problem_text(self, problem: dict) -> str:
        parts = [
            str(problem.get("question") or ""),
            str((problem.get("answer") or {}).get("text") or ""),
            str(problem.get("explanation") or ""),
            " ".join(str(concept) for concept in (problem.get("concepts") or [])),
        ]
        choices = problem.get("choices") or []
        parts.extend(str(choice.get("text") or "") for choice in choices if isinstance(choice, dict))
        choice_explanations = problem.get("choice_explanations") or {}
        parts.extend(str(value) for value in choice_explanations.values())
        rubric = problem.get("rubric") or []
        parts.extend(str(item.get("criterion") or "") for item in rubric if isinstance(item, dict))
        return " ".join(parts)

    def _calculation_solution_text(self, problem: dict) -> str:
        parts = [
            str((problem.get("answer") or {}).get("text") or ""),
            str(problem.get("explanation") or ""),
        ]
        choice_explanations = problem.get("choice_explanations") or {}
        parts.extend(str(value) for value in choice_explanations.values())
        rubric = problem.get("rubric") or []
        for item in rubric:
            if not isinstance(item, dict):
                continue
            parts.extend(
                [
                    str(item.get("criterion") or ""),
                    " ".join(str(value) for value in item.get("expected_evidence") or []),
                    " ".join(str(value) for value in item.get("partial_credit_rules") or []),
                ]
            )
        return " ".join(parts)

    def _arithmetic_expressions(self, text: str) -> list[tuple[float, str, float]]:
        expressions: list[tuple[float, str, float]] = []
        pattern = re.compile(r"(-?\d+(?:\.\d+)?)\s*([+\-*/x×÷])\s*(-?\d+(?:\.\d+)?)")
        for match in pattern.finditer(str(text or "")):
            expressions.append((float(match.group(1)), match.group(2), float(match.group(3))))
        return expressions

    def _evaluate_expression(self, left: float, operator: str, right: float) -> float | None:
        if operator == "+":
            return left + right
        if operator == "-":
            return left - right
        if operator in {"*", "x", "×"}:
            return left * right
        if operator in {"/", "÷"} and right != 0:
            return left / right
        return None

    def _stopwords(self) -> set[str]:
        return {
            "자료",
            "내용",
            "문제",
            "정답",
            "해설",
            "개념",
            "설명",
            "가장",
            "적절",
            "자신",
            "말로",
            "관련",
            "근거",
            "포함",
            "사용",
            "한다",
            "이다",
            "있는",
            "없는",
            "the",
            "and",
            "or",
            "for",
            "with",
        }

    def _reject_reason(self, report: ProblemQualityReport) -> str:
        flags = ", ".join(flag.value for flag in report.flags) or "quality policy"
        issues = list(
            dict.fromkeys(
                [
                    *report.item_model_quality_issues,
                    *report.rubric_quality_issues,
                    *report.choice_quality_issues,
                ]
            )
        )
        if not issues:
            return f"problem rejected by quality policy: {flags}"
        return f"problem rejected by quality policy: {flags}; " + "; ".join(issues)
