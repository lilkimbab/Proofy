from __future__ import annotations

import json
import re
from typing import Any

from app.config import Settings, get_settings
from app.llm.openai_client import OpenAIClient
from app.models import Problem
from app.schemas.integration_contracts import RetrievedChunk
from app.schemas.problem_kernels import ContentAtom, ContentAtomType, ProblemKernelPlan, ProblemKernelType
from app.schemas.problems import GenerateProblemRequest, ProblemType
from app.schemas.quality import ProblemAnswerVerificationReport


class ProblemAnswerVerifier:
    """Independent answer-correctness checks for generated problems.

    The deterministic checks are intentionally conservative. They catch common
    answer-shape, arithmetic, ambiguity, and evidence-link issues without making
    network calls. Optional LLM verification is enabled only by settings.
    """

    def __init__(self, *, settings: Settings | None = None, llm: OpenAIClient | None = None):
        self.settings = settings or get_settings()
        self.llm = llm

    def verify(
        self,
        *,
        problem: dict[str, Any] | Problem,
        request: GenerateProblemRequest | None = None,
        chunks: list[RetrievedChunk] | None = None,
        content_atoms: list[ContentAtom] | None = None,
        problem_kernel_plan: ProblemKernelPlan | None = None,
    ) -> ProblemAnswerVerificationReport:
        problem_data = self._problem_data(problem)
        deterministic = self._deterministic_verify(
            problem_data=problem_data,
            request=request,
            chunks=chunks or [],
            content_atoms=content_atoms or [],
            problem_kernel_plan=problem_kernel_plan,
        )
        if not self.settings.problem_agent_answer_verification_llm_enabled:
            return deterministic
        if not self.settings.openai_api_key and self.llm is None:
            return deterministic.model_copy(update={"issues": [*deterministic.issues, "LLM verifier skipped: OPENAI_API_KEY missing"]})
        try:
            return self._llm_verify(
                problem_data=problem_data,
                request=request,
                chunks=chunks or [],
                content_atoms=content_atoms or [],
                problem_kernel_plan=problem_kernel_plan,
            )
        except Exception as exc:
            return deterministic.model_copy(
                update={
                    "issues": [*deterministic.issues, f"LLM verifier failed: {type(exc).__name__}"],
                    "confidence": "medium" if deterministic.confidence == "high" else deterministic.confidence,
                }
            )

    def _deterministic_verify(
        self,
        *,
        problem_data: dict[str, Any],
        request: GenerateProblemRequest | None,
        chunks: list[RetrievedChunk],
        content_atoms: list[ContentAtom],
        problem_kernel_plan: ProblemKernelPlan | None,
    ) -> ProblemAnswerVerificationReport:
        issues: list[str] = []
        correctness_score = 1.0
        ambiguity_score = 0.0
        grounding_score = 1.0
        problem_type = str(problem_data.get("type") or "")
        numeric_grounding = self._number_grounding_categories(
            problem_data=problem_data,
            chunks=chunks,
            content_atoms=content_atoms,
            problem_kernel_plan=problem_kernel_plan,
        )

        if problem_type == ProblemType.multiple_choice.value:
            mcq_result = self._verify_multiple_choice(problem_data=problem_data, request=request, chunks=chunks)
            issues.extend(mcq_result["issues"])
            correctness_score = min(correctness_score, mcq_result["correctness_score"])
            ambiguity_score = max(ambiguity_score, mcq_result["ambiguity_score"])
            grounding_score = min(grounding_score, mcq_result["grounding_score"])
        elif problem_type == ProblemType.short_answer.value:
            short_result = self._verify_short_answer(
                problem_data=problem_data,
                chunks=chunks,
                numeric_grounding=numeric_grounding,
                content_atoms=content_atoms,
                problem_kernel_plan=problem_kernel_plan,
            )
            issues.extend(short_result["issues"])
            correctness_score = min(correctness_score, short_result["correctness_score"])
            ambiguity_score = max(ambiguity_score, short_result["ambiguity_score"])
            grounding_score = min(grounding_score, short_result["grounding_score"])

        if numeric_grounding.get("number_not_given_in_stem"):
            issues.append(
                "number_not_given_in_stem: "
                + ", ".join(numeric_grounding["number_not_given_in_stem"][:5])
            )
            grounding_score = min(grounding_score, 0.6)
        if numeric_grounding.get("number_not_derivable_from_given_conditions"):
            issues.append(
                "number_not_derivable_from_given_conditions: "
                + ", ".join(numeric_grounding["number_not_derivable_from_given_conditions"][:5])
            )
            grounding_score = min(grounding_score, 0.6)
        if numeric_grounding.get("suspicious_answer_number"):
            issues.append(
                "suspicious_answer_number: "
                + ", ".join(numeric_grounding["suspicious_answer_number"][:5])
            )
            grounding_score = min(grounding_score, 0.65)
        if numeric_grounding.get("ungrounded_source_fact_number"):
            issues.append(
                "ungrounded source fact number: "
                + ", ".join(numeric_grounding["ungrounded_source_fact_number"][:5])
            )
            grounding_score = min(grounding_score, 0.55)
        if numeric_grounding.get("source_formula_missing"):
            issues.append("source_formula_missing: compute_from_given requires a source formula or rule atom")
            grounding_score = min(grounding_score, 0.55)
        if numeric_grounding.get("arithmetic_inconsistency"):
            issues.extend(numeric_grounding["arithmetic_inconsistency"])
            correctness_score = min(correctness_score, 0.35)

        arithmetic_issues = self._arithmetic_issues(problem_data)
        if arithmetic_issues:
            issues.extend(arithmetic_issues)
            correctness_score = min(correctness_score, 0.35)

        if any("suspicious_answer_number" in issue for issue in issues):
            grounding_score = min(grounding_score, 0.65)

        score = min(correctness_score, grounding_score, 1.0 - (0.4 * ambiguity_score))
        if any("wrong arithmetic" in issue or "arithmetic_inconsistency" in issue or "answer.choice_id" in issue for issue in issues):
            action = "reject"
        elif score < 0.7 or issues:
            action = "needs_review"
        else:
            action = "pass"
        confidence = "high" if not issues else ("medium" if score >= 0.7 else "low")
        return ProblemAnswerVerificationReport(
            verified=True,
            confidence=confidence,
            answer_correctness_score=max(0.0, min(1.0, score)),
            ambiguity_score=max(0.0, min(1.0, ambiguity_score)),
            grounding_score=max(0.0, min(1.0, grounding_score)),
            issues=list(dict.fromkeys(issues)),
            recommended_action=action,
            numeric_grounding=numeric_grounding,
        )

    def _verify_multiple_choice(
        self,
        *,
        problem_data: dict[str, Any],
        request: GenerateProblemRequest | None,
        chunks: list[RetrievedChunk],
    ) -> dict[str, Any]:
        issues: list[str] = []
        choices = list(problem_data.get("choices") or [])
        answer = dict(problem_data.get("answer") or {})
        answer_choice_id = str(answer.get("choice_id") or "").strip()
        choice_by_id = {str(choice.get("id") or "").strip(): str(choice.get("text") or "").strip() for choice in choices}
        correct_text = choice_by_id.get(answer_choice_id, "")
        explanation_text = str(problem_data.get("explanation") or "")
        choice_explanations = problem_data.get("choice_explanations") or {}

        if not answer_choice_id or answer_choice_id not in choice_by_id:
            issues.append("answer.choice_id must identify exactly one existing option")
        if correct_text and str(answer.get("text") or "").strip() != correct_text:
            issues.append("answer.text does not match selected option")
        if correct_text and not self._text_supports_choice(correct_text, explanation_text, choice_explanations.get(answer_choice_id)):
            issues.append("explanation does not clearly support the selected option")

        duplicate_correct_choices = [
            choice_id
            for choice_id, choice_text in choice_by_id.items()
            if choice_id != answer_choice_id and self._text_similarity(correct_text, choice_text) >= 0.82
        ]
        ambiguity_score = 0.0
        if duplicate_correct_choices:
            ambiguity_score = 0.85
            issues.append("multiple-choice item has another option semantically equivalent to the correct answer")

        grounding_score = 1.0
        if self._is_evidence_analysis(problem_data=problem_data, request=request):
            evidence_text = self._chunk_text(chunks) or self._source_snapshot_text(problem_data)
            answer_terms = self._content_terms(" ".join([correct_text, explanation_text]))
            if evidence_text and answer_terms and self._term_overlap_ratio(answer_terms, evidence_text) < 0.25:
                grounding_score = 0.55
                issues.append("evidence_analysis correct answer is weakly supported by cited source evidence")

        correctness_score = 0.35 if any("answer.choice_id" in issue for issue in issues) else 1.0
        if duplicate_correct_choices:
            correctness_score = min(correctness_score, 0.65)
        return {
            "issues": issues,
            "correctness_score": correctness_score,
            "ambiguity_score": ambiguity_score,
            "grounding_score": grounding_score,
        }

    def _verify_short_answer(
        self,
        *,
        problem_data: dict[str, Any],
        chunks: list[RetrievedChunk],
        numeric_grounding: dict[str, list[str]],
        content_atoms: list[ContentAtom],
        problem_kernel_plan: ProblemKernelPlan | None,
    ) -> dict[str, Any]:
        issues: list[str] = []
        answer_text = json.dumps(problem_data.get("answer") or {}, ensure_ascii=False)
        rubric = list(problem_data.get("rubric") or [])
        rubric_evidence_terms = self._content_terms(
            " ".join(
                " ".join(str(item) for item in rubric_item.get("expected_evidence", []))
                for rubric_item in rubric
                if isinstance(rubric_item, dict)
            )
        )
        if rubric_evidence_terms and self._term_overlap_ratio(rubric_evidence_terms, answer_text) < 0.35:
            issues.append("short-answer answer does not cover enough rubric expected evidence")

        unsupported_numbers = numeric_grounding.get("suspicious_answer_number", [])
        if problem_kernel_plan is not None and problem_kernel_plan.requires_derivation_check:
            has_formula_or_rule = any(
                atom.atom_type in {ContentAtomType.formula, ContentAtomType.rule}
                for atom in content_atoms
            )
            if not has_formula_or_rule:
                issues.append("source_formula_missing: compute_from_given requires a source formula or rule atom")
            if unsupported_numbers and not numeric_grounding.get("derived_number"):
                issues.append("calculation trace is missing for answer-only numbers")

        return {
            "issues": issues,
            "correctness_score": 0.75 if issues else 1.0,
            "ambiguity_score": 0.0,
            "grounding_score": 0.65 if unsupported_numbers else 1.0,
        }

    def _arithmetic_issues(self, problem_data: dict[str, Any]) -> list[str]:
        question_text = str(problem_data.get("question") or "")
        answer_text = " ".join(
            [
                json.dumps(problem_data.get("answer") or {}, ensure_ascii=False),
                str(problem_data.get("explanation") or ""),
            ]
        )
        issues: list[str] = []
        for left, operator, right in self._arithmetic_expressions(question_text):
            expected = self._evaluate_expression(left, operator, right)
            if expected is None:
                continue
            answer_numbers = [float(number) for number in self._numbers(answer_text)]
            if not any(abs(number - expected) <= 1e-6 for number in answer_numbers):
                issues.append(f"wrong arithmetic: {left:g} {operator} {right:g} should be {expected:g}")
        return issues

    def _unsupported_numbers(self, *, problem_data: dict[str, Any], chunks: list[RetrievedChunk]) -> list[str]:
        answer_text = " ".join(
            [
                json.dumps(problem_data.get("answer") or {}, ensure_ascii=False),
                str(problem_data.get("explanation") or ""),
            ]
        )
        question_text = str(problem_data.get("question") or "")
        source_text = self._chunk_text(chunks) or self._source_snapshot_text(problem_data)
        allowed = set(self._numbers(question_text)) | set(self._numbers(source_text))
        for left, operator, right in self._arithmetic_expressions(question_text):
            expected = self._evaluate_expression(left, operator, right)
            if expected is not None:
                allowed.add(f"{expected:g}")
        unsupported = []
        for number in self._numbers(answer_text):
            if number not in allowed:
                unsupported.append(number)
        return list(dict.fromkeys(unsupported))

    def _number_grounding_categories(
        self,
        *,
        problem_data: dict[str, Any],
        chunks: list[RetrievedChunk],
        content_atoms: list[ContentAtom],
        problem_kernel_plan: ProblemKernelPlan | None,
    ) -> dict[str, list[str]]:
        question_text = str(problem_data.get("question") or "")
        choices_text = " ".join(
            str(choice.get("text") or "")
            for choice in (problem_data.get("choices") or [])
            if isinstance(choice, dict)
        )
        solution_text = " ".join(
            [
                json.dumps(problem_data.get("answer") or {}, ensure_ascii=False),
                str(problem_data.get("explanation") or ""),
                json.dumps(problem_data.get("choice_explanations") or {}, ensure_ascii=False),
                json.dumps(problem_data.get("rubric") or [], ensure_ascii=False),
            ]
        )
        source_text = self._chunk_text(chunks) or self._source_snapshot_text(problem_data)
        source_numbers = set(self._numbers(source_text))
        question_numbers = set(self._numbers(f"{question_text} {choices_text}"))
        allowed = set(source_numbers) | set(question_numbers)
        scenario_numbers: set[str] = set()
        number_not_given_in_stem: list[str] = []
        if problem_kernel_plan is not None and problem_kernel_plan.computation_scenario is not None:
            for given in problem_kernel_plan.computation_scenario.generated_given_values:
                given_numbers = set(self._numbers(str(given.value)))
                scenario_numbers.update(given_numbers)
                if given_numbers and not given_numbers <= question_numbers:
                    number_not_given_in_stem.extend(sorted(given_numbers - question_numbers))
            allowed |= scenario_numbers & question_numbers
        derived_numbers: set[str] = set()
        arithmetic_inconsistencies: list[str] = []

        for expression_text in (question_text, solution_text):
            for left, operator, right in self._arithmetic_expressions(expression_text):
                expected = self._evaluate_expression(left, operator, right)
                if expected is None:
                    continue
                operands_grounded = f"{left:g}" in allowed and f"{right:g}" in allowed
                if expression_text == question_text or operands_grounded:
                    derived_numbers.add(f"{expected:g}")
            derived_from_equations, equation_issues = self._equation_derived_numbers(
                expression_text,
                grounded_numbers=allowed | derived_numbers,
            )
            derived_numbers.update(derived_from_equations)
            arithmetic_inconsistencies.extend(equation_issues)
        allowed |= derived_numbers

        solution_numbers = list(dict.fromkeys(self._numbers(solution_text)))
        suspicious = [
            number
            for number in solution_numbers
            if number not in allowed and number not in {"0", "1", "2", "3", "4", "5"}
        ]
        number_not_derivable: list[str] = []
        if (
            problem_kernel_plan is not None
            and problem_kernel_plan.kernel_type == ProblemKernelType.compute_from_given
        ):
            number_not_derivable = [
                number for number in suspicious if number not in set(number_not_given_in_stem)
            ]
        source_fact_cues = ("source says", "source states", "자료에 따르면", "자료는", "문헌은", "source")
        source_fact_numbers = suspicious if any(cue in solution_text.lower() for cue in source_fact_cues) else []
        source_formula_missing: list[str] = []
        if problem_kernel_plan is not None and problem_kernel_plan.requires_derivation_check:
            has_formula_or_rule = any(
                atom.atom_type in {ContentAtomType.formula, ContentAtomType.rule}
                for atom in content_atoms
            )
            if not has_formula_or_rule:
                source_formula_missing.append("formula_or_rule_atom")
        return {
            "source_number": sorted(source_numbers, key=self._number_sort_key),
            "question_given_number": sorted(question_numbers, key=self._number_sort_key),
            "generated_scenario_number": sorted(question_numbers - source_numbers, key=self._number_sort_key),
            "derived_number": sorted(derived_numbers, key=self._number_sort_key),
            "suspicious_answer_number": suspicious,
            "number_not_given_in_stem": list(dict.fromkeys(number_not_given_in_stem)),
            "number_not_derivable_from_given_conditions": list(dict.fromkeys(number_not_derivable)),
            "ungrounded_source_fact_number": source_fact_numbers,
            "arithmetic_inconsistency": list(dict.fromkeys(arithmetic_inconsistencies)),
            "source_formula_missing": source_formula_missing,
        }

    def _llm_verify(
        self,
        *,
        problem_data: dict[str, Any],
        request: GenerateProblemRequest | None,
        chunks: list[RetrievedChunk],
        content_atoms: list[ContentAtom],
        problem_kernel_plan: ProblemKernelPlan | None,
    ) -> ProblemAnswerVerificationReport:
        client = self.llm or OpenAIClient(self.settings.model_copy(update={"llm_provider": "openai"}))
        payload = client.generate_json(
            model=self.settings.problem_agent_answer_verification_model or self.settings.problem_quality_model,
            prompt=self._llm_prompt(
                problem_data=problem_data,
                request=request,
                chunks=chunks,
                content_atoms=content_atoms,
                problem_kernel_plan=problem_kernel_plan,
            ),
            schema_name="ProblemAnswerVerificationReport",
            schema=self._llm_schema(),
            max_output_tokens=900,
            reasoning_effort="low",
        )
        return ProblemAnswerVerificationReport.model_validate(payload)

    def _llm_prompt(
        self,
        *,
        problem_data: dict[str, Any],
        request: GenerateProblemRequest | None,
        chunks: list[RetrievedChunk],
        content_atoms: list[ContentAtom],
        problem_kernel_plan: ProblemKernelPlan | None,
    ) -> str:
        payload = {
            "request": request.model_dump(mode="json") if request is not None else None,
            "problem": problem_data,
            "source_chunks": [chunk.model_dump(mode="json") for chunk in chunks],
            "content_atoms": [atom.model_dump(mode="json") for atom in content_atoms[:12]],
            "problem_kernel_plan": problem_kernel_plan.model_dump(mode="json") if problem_kernel_plan else None,
        }
        return (
            "Independently verify the generated problem's answer correctness. "
            "Check arithmetic, ambiguity, answer/rubric alignment, and source support. "
            "Return strict JSON matching the schema. Scores must be 0.0 to 1.0. "
            "recommended_action must be pass, needs_review, or reject.\n\n"
            + json.dumps(payload, ensure_ascii=False, indent=2)
        )

    def _llm_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "verified": {"type": "boolean"},
                "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
                "answer_correctness_score": {"type": "number", "minimum": 0, "maximum": 1},
                "ambiguity_score": {"type": "number", "minimum": 0, "maximum": 1},
                "grounding_score": {"type": "number", "minimum": 0, "maximum": 1},
                "issues": {"type": "array", "items": {"type": "string"}},
                "recommended_action": {"type": "string", "enum": ["pass", "needs_review", "reject"]},
            },
            "required": [
                "verified",
                "confidence",
                "answer_correctness_score",
                "ambiguity_score",
                "grounding_score",
                "issues",
                "recommended_action",
            ],
        }

    def _problem_data(self, problem: dict[str, Any] | Problem) -> dict[str, Any]:
        if isinstance(problem, dict):
            return dict(problem)
        return {
            "id": problem.id,
            "document_id": problem.document_id,
            "type": problem.type,
            "difficulty": problem.difficulty,
            "bloom_level": problem.bloom_level,
            "question": problem.question,
            "choices": problem.choices,
            "answer": problem.answer,
            "explanation": problem.explanation,
            "choice_explanations": problem.choice_explanations,
            "choice_diagnostics": problem.choice_diagnostics,
            "rubric": problem.rubric,
            "concepts": problem.concepts,
            "source_chunk_ids": problem.source_chunk_ids,
            "source_evidence_snapshot": problem.source_evidence_snapshot,
            "item_model_id": problem.item_model_id,
        }

    def _arithmetic_expressions(self, text: str) -> list[tuple[float, str, float]]:
        expressions = []
        pattern = re.compile(r"(-?\d+(?:\.\d+)?)\s*([+\-*/x×÷])\s*(-?\d+(?:\.\d+)?)")
        for match in pattern.finditer(text):
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

    def _equation_derived_numbers(self, text: str, *, grounded_numbers: set[str]) -> tuple[set[str], list[str]]:
        derived: set[str] = set()
        issues: list[str] = []
        normalized = self._normalize_numeric_text(text)
        equation_pattern = re.compile(
            r"(?P<expr>[0-9.\s+\-*/x×÷()%]+?)\s*=\s*(?P<rhs>-?\d+(?:\.\d+)?%?)"
        )
        for match in equation_pattern.finditer(normalized):
            expression = match.group("expr").strip()
            rhs_numbers = self._numbers(match.group("rhs"))
            if not rhs_numbers:
                continue
            rhs = float(rhs_numbers[0])
            operands = set(self._numbers(expression))
            if operands and not operands <= grounded_numbers:
                continue
            expected = self._safe_numeric_eval(expression)
            if expected is None:
                continue
            if abs(expected - rhs) <= max(1e-6, abs(expected) * 1e-4):
                derived.add(f"{rhs:g}")
            else:
                issues.append(
                    f"arithmetic_inconsistency: {expression} should be {expected:g}, not {rhs:g}"
                )
        return derived, issues

    def _safe_numeric_eval(self, expression: str) -> float | None:
        expr = self._normalize_numeric_text(expression)
        expr = expr.replace("×", "*").replace("x", "*").replace("÷", "/")
        expr = re.sub(r"(\d+(?:\.\d+)?)%", lambda m: str(float(m.group(1)) / 100), expr)
        if not re.fullmatch(r"[0-9.\s+\-*/()]+", expr):
            return None
        try:
            value = eval(expr, {"__builtins__": {}}, {})  # noqa: S307 - numeric-only regex gate above.
        except Exception:
            return None
        if isinstance(value, int | float):
            return float(value)
        return None

    def _numbers(self, text: str) -> list[str]:
        normalized = self._normalize_numeric_text(text)
        numbers: list[str] = []
        consumed: set[tuple[int, int]] = set()
        for match in re.finditer(r"(?<![A-Za-z_])(-?\d+(?:\.\d+)?)\s*/\s*(-?\d+(?:\.\d+)?)(?![A-Za-z_])", normalized):
            denominator = float(match.group(2))
            if denominator != 0:
                numbers.append(f"{float(match.group(1)) / denominator:g}")
                consumed.add(match.span())
        for match in re.finditer(r"(?<![A-Za-z_])-?\d+(?:\.\d+)?%?(?![A-Za-z_])", normalized):
            if any(start <= match.start() and match.end() <= end for start, end in consumed):
                continue
            raw = match.group(0)
            value = float(raw.rstrip("%"))
            if raw.endswith("%"):
                value /= 100
            numbers.append(f"{value:g}")
        return numbers

    def _normalize_numeric_text(self, text: str) -> str:
        normalized = re.sub(r"(?<=\d),(?=\d)", "", str(text or ""))
        normalized = normalized.replace("￦", "").replace("₩", "").replace("$", "")
        return normalized

    def _number_sort_key(self, value: str) -> float:
        try:
            return float(value)
        except ValueError:
            return 0.0

    def _text_supports_choice(self, correct_text: str, explanation: str, correct_explanation: object) -> bool:
        support_text = " ".join([str(explanation or ""), str(correct_explanation or "")])
        if not support_text.strip():
            return False
        return self._term_overlap_ratio(self._content_terms(correct_text), support_text) >= 0.2

    def _text_similarity(self, left: str, right: str) -> float:
        left_terms = self._content_terms(left)
        right_terms = self._content_terms(right)
        if not left_terms or not right_terms:
            return 0.0
        return len(left_terms & right_terms) / len(left_terms | right_terms)

    def _content_terms(self, text: str) -> set[str]:
        stopwords = {
            "the",
            "and",
            "or",
            "is",
            "are",
            "with",
            "that",
            "this",
            "것은",
            "이는",
            "이다",
            "한다",
            "있다",
            "없다",
        }
        return {
            token
            for token in re.findall(r"[0-9a-zA-Z가-힣_+]+", str(text or "").lower())
            if len(token) > 1 and token not in stopwords
        }

    def _term_overlap_ratio(self, terms: set[str], text: str) -> float:
        if not terms:
            return 1.0
        normalized_text = str(text or "").lower()
        matched = sum(1 for term in terms if term in normalized_text)
        return matched / len(terms)

    def _is_evidence_analysis(self, *, problem_data: dict[str, Any], request: GenerateProblemRequest | None) -> bool:
        if request is not None and request.problem_style and request.problem_style.value == "evidence_analysis":
            return True
        item_model_id = str(problem_data.get("item_model_id") or "")
        return item_model_id in {"evidence_selection", "data_interpretation"}

    def _chunk_text(self, chunks: list[RetrievedChunk]) -> str:
        return " ".join(chunk.content or "" for chunk in chunks)

    def _source_snapshot_text(self, problem_data: dict[str, Any]) -> str:
        return json.dumps(problem_data.get("source_evidence_snapshot") or [], ensure_ascii=False)
