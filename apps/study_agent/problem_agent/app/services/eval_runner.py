from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.agents import ProblemQualityChecker
from app.schemas.integration_contracts import RetrievedChunk
from app.schemas.llm_outputs import FeedbackGenerationOutput, GeneratedProblem
from app.schemas.problems import BloomLevel, GenerateProblemRequest, MistakeType, ProblemType
from app.services.professor_grade_item_service import ProfessorGradeItemDesigner


FEEDBACK_SECTION_LABELS = ("정답 여부:", "헷갈린 지점:", "올바른 개념:", "복습 추천:")
FORBIDDEN_FEEDBACK_PHRASES = (
    "넌 못한다",
    "기초가 없다",
    "이해력이 부족하다",
    "그냥 틀렸다",
    "왜 이것도 모르니",
    "틀렸어",
    "아직 정답은 아니야",
)
FRIENDLY_POLITE_MARKERS = (
    "요",
    "세요",
    "볼까요",
    "해볼게요",
    "좋아요",
    "괜찮아요",
)
KOREAN_STOPWORDS = {
    "자료",
    "문제",
    "정답",
    "해설",
    "개념",
    "설명",
    "가장",
    "다음",
    "대한",
    "것은",
    "것이다",
    "한다",
    "있다",
    "없다",
}
DEEP_BLOOM_LEVELS = {BloomLevel.apply, BloomLevel.analyze, BloomLevel.evaluate, BloomLevel.create}


@dataclass(frozen=True)
class EvalCaseResult:
    case_id: str
    case_type: str
    passed: bool
    actual_valid: bool
    errors: list[str]


class ProblemGenerationEvalCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_type: Literal["problem_generation"]
    id: str = Field(min_length=1)
    description: str = Field(min_length=1)
    request: GenerateProblemRequest
    chunks: list[RetrievedChunk] = Field(min_length=1)
    candidate: dict[str, Any]
    expected_valid: bool = True
    depth: Literal["standard", "deep"] = "standard"
    user_requirements: str | None = None
    required_source_terms: list[str] = Field(default_factory=list)
    required_output_terms: list[str] = Field(default_factory=list)
    required_rubric_terms: list[str] = Field(default_factory=list)
    forbidden_terms: list[str] = Field(default_factory=list)
    expected_item_model_id: str | None = None
    min_rubric_items: int | None = None
    min_source_chunks: int | None = None
    min_distinct_concepts: int | None = None
    min_choice_diagnostics: int | None = None
    require_latex: bool = False
    expected_error_substrings: list[str] = Field(default_factory=list)


class FeedbackGradingEvalCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_type: Literal["feedback_grading"]
    id: str = Field(min_length=1)
    description: str = Field(min_length=1)
    payload: dict[str, Any]
    expected_valid: bool = True
    expected_score: float | None = None
    expected_mistake_type: MistakeType | None = None
    recommended_review_contains: list[str] = Field(default_factory=list)
    expected_error_substrings: list[str] = Field(default_factory=list)


class FeedbackToneEvalCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_type: Literal["feedback_tone"]
    id: str = Field(min_length=1)
    description: str = Field(min_length=1)
    feedback: str = Field(min_length=1)
    expected_safe: bool = True
    forbidden_phrases: list[str] = Field(default_factory=list)
    require_sections: bool = True
    expected_error_substrings: list[str] = Field(default_factory=list)


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                rows.append(json.loads(stripped))
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_number} is not valid JSON: {exc}") from exc
    return rows


def evaluate_fixture_tree(root: Path) -> list[EvalCaseResult]:
    results: list[EvalCaseResult] = []
    for path in sorted(root.rglob("*.jsonl")):
        relative_parts = path.relative_to(root).parts
        if "live_materials" in relative_parts or "reports" in relative_parts or path.name.endswith("_seed.jsonl"):
            continue
        results.extend(evaluate_fixture_file(path))
    return results


def evaluate_fixture_file(path: Path) -> list[EvalCaseResult]:
    return [evaluate_case(row) for row in load_jsonl(path)]


def evaluate_case(row: dict[str, Any]) -> EvalCaseResult:
    case_type = row.get("case_type")
    if case_type == "problem_generation":
        return evaluate_problem_generation_case(ProblemGenerationEvalCase.model_validate(row))
    if case_type == "feedback_grading":
        return evaluate_feedback_grading_case(FeedbackGradingEvalCase.model_validate(row))
    if case_type == "feedback_tone":
        return evaluate_feedback_tone_case(FeedbackToneEvalCase.model_validate(row))
    raise ValueError(f"Unknown eval case_type: {case_type}")


def evaluate_problem_generation_case(case: ProblemGenerationEvalCase) -> EvalCaseResult:
    errors: list[str] = []

    try:
        problem = GeneratedProblem.model_validate(case.candidate)
    except Exception as exc:
        errors.append(f"candidate schema invalid: {exc}")
        return _finish_expected_result(
            case_id=case.id,
            case_type=case.case_type,
            expected_valid=case.expected_valid,
            errors=errors,
            expected_error_substrings=case.expected_error_substrings,
        )

    problem_data = problem.model_dump(mode="json")
    errors.extend(_problem_matches_request_errors(problem_data, case.request))
    if case.expected_item_model_id:
        design_result = ProfessorGradeItemDesigner().enrich(
            problem_data=problem_data,
            request=case.request,
            chunks=case.chunks,
        )
        problem_data = design_result.problem_data
        actual_item_model_id = str(problem_data.get("item_model_id") or "")
        if actual_item_model_id != case.expected_item_model_id:
            errors.append(
                f"item_model_id expected {case.expected_item_model_id}, got {actual_item_model_id or 'none'}"
            )
        errors.extend(f"item model designer rejected: {error}" for error in design_result.rejection_errors)
    is_valid, quality_errors, quality_report = ProblemQualityChecker().validate_with_quality_report(
        problem_data,
        retrieved_chunks=case.chunks,
        request=case.request,
    )
    if not is_valid:
        errors.extend(quality_errors)
    if quality_report.action == "reject" and is_valid:
        errors.append("quality report rejected the problem")
    errors.extend(_source_grounding_errors(problem_data=problem_data, case=case))
    errors.extend(_high_rigor_contract_errors(problem_data=problem_data, case=case))
    errors.extend(_deep_short_answer_errors(problem=problem, case=case))

    return _finish_expected_result(
        case_id=case.id,
        case_type=case.case_type,
        expected_valid=case.expected_valid,
        errors=errors,
        expected_error_substrings=case.expected_error_substrings,
    )


def evaluate_feedback_grading_case(case: FeedbackGradingEvalCase) -> EvalCaseResult:
    errors: list[str] = []
    try:
        payload = FeedbackGenerationOutput.model_validate(case.payload)
    except Exception as exc:
        errors.append(f"feedback schema invalid: {exc}")
        return _finish_expected_result(
            case_id=case.id,
            case_type=case.case_type,
            expected_valid=case.expected_valid,
            errors=errors,
            expected_error_substrings=case.expected_error_substrings,
        )

    if case.expected_score is not None and payload.score != case.expected_score:
        errors.append(f"score expected {case.expected_score}, got {payload.score}")
    if case.expected_mistake_type is not None and payload.mistake_type != case.expected_mistake_type:
        errors.append(f"mistake_type expected {case.expected_mistake_type}, got {payload.mistake_type}")
    missing_reviews = [
        concept for concept in case.recommended_review_contains if concept not in payload.recommended_review
    ]
    if missing_reviews:
        errors.append(f"recommended_review missing: {', '.join(missing_reviews)}")

    errors.extend(_feedback_tone_errors(payload.feedback, forbidden_phrases=[]))

    return _finish_expected_result(
        case_id=case.id,
        case_type=case.case_type,
        expected_valid=case.expected_valid,
        errors=errors,
        expected_error_substrings=case.expected_error_substrings,
    )


def evaluate_feedback_tone_case(case: FeedbackToneEvalCase) -> EvalCaseResult:
    errors = _feedback_tone_errors(
        case.feedback,
        forbidden_phrases=case.forbidden_phrases,
        require_sections=case.require_sections,
    )
    return _finish_expected_result(
        case_id=case.id,
        case_type=case.case_type,
        expected_valid=case.expected_safe,
        errors=errors,
        expected_error_substrings=case.expected_error_substrings,
    )


def _finish_expected_result(
    *,
    case_id: str,
    case_type: str,
    expected_valid: bool,
    errors: list[str],
    expected_error_substrings: list[str],
) -> EvalCaseResult:
    actual_valid = not errors
    expectation_errors: list[str] = []
    if not actual_valid:
        expectation_errors.extend(_missing_expected_error_substrings(errors, expected_error_substrings))
    elif expected_error_substrings:
        expectation_errors.append("expected error substrings were provided, but evaluator accepted the case")

    if actual_valid == expected_valid and not expectation_errors:
        return EvalCaseResult(
            case_id=case_id,
            case_type=case_type,
            passed=True,
            actual_valid=actual_valid,
            errors=errors,
        )
    expectation_error = []
    if actual_valid != expected_valid:
        expectation_error.append(
            "expected case to be valid, but evaluator rejected it"
            if expected_valid
            else "expected case to be invalid, but evaluator accepted it"
        )
    return EvalCaseResult(
        case_id=case_id,
        case_type=case_type,
        passed=False,
        actual_valid=actual_valid,
        errors=[*expectation_error, *expectation_errors, *errors],
    )


def _missing_expected_error_substrings(errors: list[str], expected_error_substrings: list[str]) -> list[str]:
    combined_errors = "\n".join(errors)
    return [
        f"expected error substring not found: {substring}"
        for substring in expected_error_substrings
        if substring not in combined_errors
    ]


def _problem_matches_request_errors(problem_data: dict[str, Any], request: GenerateProblemRequest) -> list[str]:
    expected = {
        "document_id": request.document_id,
        "type": request.type.value,
        "difficulty": request.difficulty.value,
        "bloom_level": request.bloom_level.value,
    }
    return [
        f"{field} does not match request"
        for field, expected_value in expected.items()
        if problem_data.get(field) != expected_value
    ]


def _source_grounding_errors(*, problem_data: dict[str, Any], case: ProblemGenerationEvalCase) -> list[str]:
    errors: list[str] = []
    combined_output = _problem_text(problem_data)
    chunk_by_id = {chunk.chunk_id: chunk for chunk in case.chunks}
    source_chunk_ids = problem_data.get("source_chunk_ids") or []
    cited_chunks = [chunk_by_id[chunk_id] for chunk_id in source_chunk_ids if chunk_id in chunk_by_id]
    source_text = " ".join(chunk.content for chunk in cited_chunks)

    for term in case.required_source_terms:
        if term not in combined_output:
            errors.append(f"required source term not used: {term}")
        if term not in source_text:
            errors.append(f"required source term is not present in cited chunks: {term}")

    for term in case.forbidden_terms:
        if term in combined_output:
            errors.append(f"forbidden term appears in generated problem: {term}")

    output_keywords = _keywords(combined_output)
    source_keywords = _keywords(source_text)
    if output_keywords and source_keywords and output_keywords.isdisjoint(source_keywords):
        errors.append("generated problem has no meaningful keyword overlap with source chunks")

    return errors


def _high_rigor_contract_errors(*, problem_data: dict[str, Any], case: ProblemGenerationEvalCase) -> list[str]:
    errors: list[str] = []
    combined_output = _problem_text(problem_data)
    rubric_text = _rubric_text(problem_data)
    source_chunk_ids = problem_data.get("source_chunk_ids") or []
    concepts = {str(concept).strip() for concept in problem_data.get("concepts") or [] if str(concept).strip()}
    choice_diagnostics = problem_data.get("choice_diagnostics") or []

    missing_output_terms = [term for term in case.required_output_terms if term not in combined_output]
    if missing_output_terms:
        errors.append(f"required output terms missing: {', '.join(missing_output_terms)}")

    missing_rubric_terms = [term for term in case.required_rubric_terms if term not in rubric_text]
    if missing_rubric_terms:
        errors.append(f"required rubric terms missing: {', '.join(missing_rubric_terms)}")

    if case.min_source_chunks is not None and len(set(source_chunk_ids)) < case.min_source_chunks:
        errors.append(f"expected at least {case.min_source_chunks} cited source chunks")

    if case.min_distinct_concepts is not None and len(concepts) < case.min_distinct_concepts:
        errors.append(f"expected at least {case.min_distinct_concepts} distinct generated concepts")

    if case.min_choice_diagnostics is not None and len(choice_diagnostics) < case.min_choice_diagnostics:
        errors.append(f"expected at least {case.min_choice_diagnostics} choice diagnostics")

    if case.require_latex and not re.search(r"\$[^$]+\$", combined_output):
        errors.append("expected LaTeX math expression in generated problem")

    return errors


def _deep_short_answer_errors(*, problem: GeneratedProblem, case: ProblemGenerationEvalCase) -> list[str]:
    if case.depth != "deep":
        return []

    errors: list[str] = []
    if case.request.type != ProblemType.short_answer:
        errors.append("depth=deep is only allowed for short_answer eval cases")
    if case.request.bloom_level not in DEEP_BLOOM_LEVELS:
        errors.append("depth=deep requires apply/analyze/evaluate/create bloom_level")
    min_rubric_items = case.min_rubric_items or 2
    if not problem.rubric or len(problem.rubric) < min_rubric_items:
        errors.append(f"deep short_answer requires at least {min_rubric_items} rubric items")
    if case.user_requirements and not case.user_requirements.strip():
        errors.append("user_requirements must not be empty when provided")
    return errors


def _feedback_tone_errors(
    feedback: str,
    *,
    forbidden_phrases: list[str],
    require_sections: bool = True,
) -> list[str]:
    errors: list[str] = []
    if require_sections:
        missing_sections = [label for label in FEEDBACK_SECTION_LABELS if label not in feedback]
        if missing_sections:
            errors.append(f"feedback missing sections: {', '.join(missing_sections)}")

    blocked = [phrase for phrase in (*FORBIDDEN_FEEDBACK_PHRASES, *forbidden_phrases) if phrase in feedback]
    if blocked:
        errors.append(f"feedback includes unsafe phrase: {', '.join(dict.fromkeys(blocked))}")
    if not any(marker in feedback for marker in FRIENDLY_POLITE_MARKERS):
        errors.append("feedback should use friendly polite education-site tone")
    return errors


def _problem_text(problem_data: dict[str, Any]) -> str:
    parts: list[str] = [
        str(problem_data.get("question") or ""),
        str(problem_data.get("explanation") or ""),
        str((problem_data.get("answer") or {}).get("text") or ""),
        " ".join(str(concept) for concept in problem_data.get("concepts") or []),
    ]
    for choice in problem_data.get("choices") or []:
        parts.append(str(choice.get("text") or ""))
    for explanation in (problem_data.get("choice_explanations") or {}).values():
        parts.append(str(explanation))
    for item in problem_data.get("rubric") or []:
        parts.append(str(item.get("criterion") or ""))
    return " ".join(parts)


def _rubric_text(problem_data: dict[str, Any]) -> str:
    parts: list[str] = []
    for item in problem_data.get("rubric") or []:
        if not isinstance(item, dict):
            continue
        parts.append(str(item.get("criterion") or ""))
        for field in ("expected_evidence", "common_mistakes", "partial_credit_rules"):
            values = item.get(field) or []
            if isinstance(values, list):
                parts.extend(str(value) for value in values)
    return " ".join(parts)


def _keywords(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[A-Za-z0-9가-힣]+", text)
        if len(token) >= 2 and token not in KOREAN_STOPWORDS
    }
