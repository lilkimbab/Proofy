from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, Field

from app.schemas.integration_contracts import RetrievedChunk
from app.schemas.problem_kernels import (
    ContentAtom,
    ContentAtomType,
    EvidenceLink,
    EvidencePlacement,
    EvidenceRole,
    ProblemKernelPlan,
    ProblemKernelType,
)


class EvidenceObligationReport(BaseModel):
    required_link_count: int = 0
    satisfied_link_count: int = 0
    missing_roles: list[str] = Field(default_factory=list)
    answer_supported: bool = False
    explanation_supported: bool = False
    distractors_supported: bool = True
    rubric_supported: bool = True
    source_formula_or_rule_cited: bool = True
    generated_scenario_values_declared: bool = True
    issues: list[str] = Field(default_factory=list)
    suggested_fix: list[str] = Field(default_factory=list)
    evidence_links: list[EvidenceLink] = Field(default_factory=list)

    @property
    def satisfaction_ratio(self) -> float:
        if self.required_link_count <= 0:
            return 1.0
        return min(1.0, self.satisfied_link_count / self.required_link_count)


class EvidenceObligationEvaluator:
    def evaluate(
        self,
        *,
        problem_data: dict[str, Any],
        content_atoms: list[ContentAtom],
        problem_kernel_plan: ProblemKernelPlan | None,
        cited_chunks: list[RetrievedChunk] | None = None,
    ) -> EvidenceObligationReport:
        if problem_kernel_plan is None:
            return EvidenceObligationReport()

        selected_atoms = self._selected_atoms(content_atoms, problem_kernel_plan)
        cited_chunk_ids = {str(chunk_id) for chunk_id in (problem_data.get("source_chunk_ids") or [])}
        selected_cited_atoms = [atom for atom in selected_atoms if atom.source_chunk_id in cited_chunk_ids]
        required_roles = [
            obligation.role
            for obligation in problem_kernel_plan.required_evidence_roles
            if obligation.required
        ]
        required_link_count = max(2, len(required_roles) + 2) if selected_atoms else 0

        issues: list[str] = []
        suggested_fix: list[str] = []
        if problem_kernel_plan.failure_reason:
            issues.append(f"kernel planning failed: {problem_kernel_plan.failure_reason}")
        if not selected_atoms:
            issues.append("evidence contract has no selected content atoms")
            suggested_fix.append("Select source atoms before generation and cite their chunks.")
            return EvidenceObligationReport(
                required_link_count=required_link_count,
                satisfied_link_count=0,
                missing_roles=[role.value for role in required_roles],
                answer_supported=False,
                explanation_supported=False,
                issues=issues,
                suggested_fix=suggested_fix,
            )
        if not cited_chunk_ids:
            issues.append("evidence contract requires source_chunk_ids")
        if not selected_cited_atoms:
            issues.append("source_chunk_ids do not match selected atoms")
            suggested_fix.append("Include selected atom source_chunk_id values in source_chunk_ids.")

        links = self._build_links(
            problem_data=problem_data,
            atoms=selected_cited_atoms or selected_atoms,
        )
        answer_supported = any("answer" in link.used_in for link in links)
        explanation_supported = any("explanation" in link.used_in for link in links)
        distractors_supported = self._distractors_supported(problem_data)
        rubric_required = any(
            obligation.required and "rubric" in obligation.must_appear_in
            for obligation in problem_kernel_plan.required_evidence_roles
        )
        rubric_supported = (
            self._rubric_supported(problem_data, selected_cited_atoms or selected_atoms)
            if rubric_required
            else True
        )
        source_formula_or_rule_cited = self._source_formula_or_rule_cited(
            problem_kernel_plan=problem_kernel_plan,
            cited_atoms=selected_cited_atoms,
        )
        generated_values_declared = self._generated_scenario_values_declared(
            problem_data=problem_data,
            atoms=selected_atoms,
            cited_chunks=cited_chunks or [],
            problem_kernel_plan=problem_kernel_plan,
        )
        if (
            not answer_supported
            and problem_kernel_plan.kernel_type == ProblemKernelType.compute_from_given
            and explanation_supported
            and generated_values_declared
            and self._numbers(self._placement_text(problem_data, "answer"))
        ):
            answer_supported = True
        if (
            not answer_supported
            and problem_data.get("type") == "multiple_choice"
            and explanation_supported
        ):
            answer_supported = True

        if not answer_supported:
            issues.append("answer is not linked to selected atom evidence")
            suggested_fix.append("Make the correct answer use terms or relations from a selected atom.")
        if not explanation_supported:
            issues.append("explanation does not connect to selected atom evidence")
            suggested_fix.append("State how the selected evidence quote supports the answer.")
        if not distractors_supported:
            issues.append("MCQ distractor diagnostics do not name distinct evidence failures")
            suggested_fix.append("Map each distractor to a violated rule, ignored condition, confused concept, or unsupported claim.")
        if not rubric_supported:
            issues.append("short_answer rubric is not tied to selected evidence roles")
            suggested_fix.append("Add rubric criteria that reference the source rule, formula, procedure, condition, or claim.")
        if not source_formula_or_rule_cited:
            issues.append("kernel evidence rule/formula/procedure is not cited")
            suggested_fix.append("Cite the selected formula/rule/procedure atom in source_chunk_ids and explanation.")
        if not generated_values_declared:
            issues.append("compute_from_given generated scenario values must be declared in the question stem")
            suggested_fix.append("Put all scenario values in the stem and show the derivation in the explanation.")

        missing_roles: list[str] = []
        for role in required_roles:
            role_atoms = [
                atom for atom in selected_atoms if atom.atom_type in self._role_atom_types(role)
            ]
            if not role_atoms:
                missing_roles.append(role.value)
                issues.append(f"missing source atom for evidence role={role.value}")
                continue
            if not any(atom.source_chunk_id in cited_chunk_ids for atom in role_atoms):
                missing_roles.append(role.value)
                issues.append(f"evidence role={role.value} citation/link failure")
                continue
            placements = [
                placement
                for obligation in problem_kernel_plan.required_evidence_roles
                if obligation.role == role
                for placement in obligation.must_appear_in
            ]
            for placement in placements:
                placement_text = self._placement_text(problem_data, placement)
                if not self._atoms_appear(role_atoms, placement_text):
                    missing_roles.append(role.value)
                    issues.append(f"evidence role={role.value} not linked in {placement}")

        kernel_issues = self._kernel_specific_issues(
            problem_data=problem_data,
            selected_atoms=selected_cited_atoms or selected_atoms,
            plan=problem_kernel_plan,
        )
        issues.extend(kernel_issues)

        satisfied = sum(
            [
                answer_supported,
                explanation_supported,
                distractors_supported,
                rubric_supported,
                source_formula_or_rule_cited,
                generated_values_declared,
            ]
        )
        role_satisfied = max(0, len(required_roles) - len(set(missing_roles)))
        satisfied_link_count = min(required_link_count, satisfied + role_satisfied)
        return EvidenceObligationReport(
            required_link_count=required_link_count,
            satisfied_link_count=satisfied_link_count,
            missing_roles=list(dict.fromkeys(missing_roles)),
            answer_supported=answer_supported,
            explanation_supported=explanation_supported,
            distractors_supported=distractors_supported,
            rubric_supported=rubric_supported,
            source_formula_or_rule_cited=source_formula_or_rule_cited,
            generated_scenario_values_declared=generated_values_declared,
            issues=list(dict.fromkeys(issues)),
            suggested_fix=list(dict.fromkeys(suggested_fix)),
            evidence_links=links,
        )

    def _selected_atoms(self, atoms: list[ContentAtom], plan: ProblemKernelPlan) -> list[ContentAtom]:
        atom_by_id = {atom.atom_id: atom for atom in atoms}
        selected = [atom_by_id[atom_id] for atom_id in plan.content_atom_ids if atom_id in atom_by_id]
        return selected or atoms[:4]

    def _build_links(self, *, problem_data: dict[str, Any], atoms: list[ContentAtom]) -> list[EvidenceLink]:
        links: list[EvidenceLink] = []
        for atom in atoms:
            used_in = [
                placement
                for placement in ("question", "answer", "explanation", "distractor", "rubric")
                if self._atoms_appear([atom], self._placement_text(problem_data, placement))
            ]
            if not used_in:
                continue
            links.append(
                EvidenceLink(
                    atom_id=atom.atom_id,
                    source_chunk_id=atom.source_chunk_id,
                    evidence_role=self._role_for_atom(atom),
                    evidence_quote=(atom.evidence_quote or atom.statement)[:1200],
                    used_in=used_in,
                    supported_claim=self._supported_claim(problem_data, used_in[0]),
                )
            )
        return links

    def _role_for_atom(self, atom: ContentAtom) -> EvidenceRole:
        return {
            ContentAtomType.definition: EvidenceRole.definition,
            ContentAtomType.classification: EvidenceRole.definition,
            ContentAtomType.rule: EvidenceRole.rule,
            ContentAtomType.formula: EvidenceRole.formula,
            ContentAtomType.procedure: EvidenceRole.procedure_step,
            ContentAtomType.comparison: EvidenceRole.contrast,
            ContentAtomType.cause_effect: EvidenceRole.source_claim,
            ContentAtomType.condition_exception: EvidenceRole.condition,
            ContentAtomType.evidence_claim: EvidenceRole.source_claim,
            ContentAtomType.data_table: EvidenceRole.data_point,
            ContentAtomType.code_state: EvidenceRole.procedure_step,
            ContentAtomType.example_case: EvidenceRole.example,
        }.get(atom.atom_type, EvidenceRole.source_claim)

    def _role_atom_types(self, role: EvidenceRole) -> set[ContentAtomType]:
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

    def _placement_text(self, problem_data: dict[str, Any], placement: EvidencePlacement | str) -> str:
        if placement == "question":
            return str(problem_data.get("question") or "")
        if placement == "answer":
            answer = problem_data.get("answer") or {}
            return " ".join(str(value) for value in answer.values())
        if placement == "explanation":
            parts = [str(problem_data.get("explanation") or "")]
            answer_id = str((problem_data.get("answer") or {}).get("choice_id") or "")
            choice_explanations = problem_data.get("choice_explanations") or {}
            if answer_id and isinstance(choice_explanations, dict):
                parts.append(str(choice_explanations.get(answer_id) or ""))
            return " ".join(parts)
        if placement == "distractor":
            answer_id = str((problem_data.get("answer") or {}).get("choice_id") or "")
            parts: list[str] = []
            for choice in problem_data.get("choices") or []:
                if str(choice.get("id") or "") != answer_id:
                    parts.append(str(choice.get("text") or ""))
            for diagnostic in problem_data.get("choice_diagnostics") or []:
                if not diagnostic.get("is_correct"):
                    parts.extend(
                        [
                            str(diagnostic.get("misconception_id") or ""),
                            str(diagnostic.get("mistake_type") or ""),
                            str(diagnostic.get("why_plausible") or ""),
                            str(diagnostic.get("repair_strategy") or ""),
                        ]
                    )
            for key, explanation in (problem_data.get("choice_explanations") or {}).items():
                if str(key) != answer_id:
                    parts.append(str(explanation or ""))
            return " ".join(parts)
        if placement == "rubric":
            parts: list[str] = []
            for item in problem_data.get("rubric") or []:
                parts.extend(str(value) for value in item.values() if not isinstance(value, list))
                for value in item.values():
                    if isinstance(value, list):
                        parts.extend(str(entry) for entry in value)
            return " ".join(parts)
        return ""

    def _supported_claim(self, problem_data: dict[str, Any], placement: str) -> str:
        text = self._placement_text(problem_data, placement)
        return text[:300] or str(problem_data.get("question") or "")[:300] or "selected evidence supports generated problem"

    def _source_formula_or_rule_cited(
        self,
        *,
        problem_kernel_plan: ProblemKernelPlan,
        cited_atoms: list[ContentAtom],
    ) -> bool:
        if problem_kernel_plan.kernel_type not in {
            ProblemKernelType.compute_from_given,
            ProblemKernelType.diagnose_error,
            ProblemKernelType.apply_rule_to_case,
        }:
            return True
        return any(
            atom.atom_type
            in {
                ContentAtomType.formula,
                ContentAtomType.rule,
                ContentAtomType.procedure,
                ContentAtomType.condition_exception,
                ContentAtomType.classification,
            }
            for atom in cited_atoms
        )

    def _generated_scenario_values_declared(
        self,
        *,
        problem_data: dict[str, Any],
        atoms: list[ContentAtom],
        cited_chunks: list[RetrievedChunk],
        problem_kernel_plan: ProblemKernelPlan,
    ) -> bool:
        if problem_kernel_plan.kernel_type != ProblemKernelType.compute_from_given:
            return True
        question_numbers = self._numbers(self._placement_text(problem_data, "question"))
        scenario = problem_kernel_plan.computation_scenario
        if scenario is None:
            return True
        if not question_numbers:
            return False
        for given in scenario.generated_given_values:
            given_numbers = self._numbers(str(given.value))
            if given_numbers and not given_numbers <= question_numbers:
                return False
        source_numbers = self._numbers(" ".join([atom.statement + " " + (atom.evidence_quote or "") for atom in atoms]))
        source_numbers.update(self._numbers(" ".join(chunk.content for chunk in cited_chunks)))
        solution_text = " ".join(
            [
                self._placement_text(problem_data, "answer"),
                self._placement_text(problem_data, "explanation"),
                self._placement_text(problem_data, "rubric"),
            ]
        )
        solution_numbers = self._numbers(solution_text)
        new_solution_numbers = solution_numbers - question_numbers - source_numbers
        if not new_solution_numbers:
            return True
        has_trace = bool(re.search(r"(=|\+|-|/|\*|×|÷|\\frac|\d+\s*/\s*\d+)", solution_text))
        return has_trace and bool(question_numbers)

    def _kernel_specific_issues(
        self,
        *,
        problem_data: dict[str, Any],
        selected_atoms: list[ContentAtom],
        plan: ProblemKernelPlan,
    ) -> list[str]:
        issues: list[str] = []
        question = self._placement_text(problem_data, "question")
        explanation = self._placement_text(problem_data, "explanation")
        answer_text = self._placement_text(problem_data, "answer")
        rubric_text = self._placement_text(problem_data, "rubric")
        if plan.kernel_type == ProblemKernelType.compute_from_given:
            formula_atoms = [atom for atom in selected_atoms if atom.atom_type in {ContentAtomType.formula, ContentAtomType.rule}]
            question_numbers = self._numbers(question)
            scenario = plan.computation_scenario
            cited_chunk_ids = {str(chunk_id) for chunk_id in (problem_data.get("source_chunk_ids") or [])}
            if scenario is not None:
                if not question_numbers:
                    issues.append("missing_concrete_context")
                missing_values = self._missing_scenario_value_names(question=question, scenario=plan.computation_scenario)
                if missing_values:
                    issues.append("number_not_given_in_stem: " + ", ".join(missing_values))
                    issues.append("missing_concrete_context")
                if scenario.source_chunk_id not in cited_chunk_ids:
                    issues.append("compute_from_given source formula/rule chunk must be cited")
            if not formula_atoms:
                issues.append("compute_from_given requires formula/rule evidence link")
            elif not self._atoms_appear(formula_atoms, explanation) and not self._scenario_quote_appears(
                explanation=explanation,
                plan=plan,
            ):
                issues.append("compute_from_given explanation must link to formula/rule evidence")
            if scenario is not None and not self._has_derivation_trace(f"{answer_text} {explanation}"):
                issues.append("compute_from_given explanation must show derivation/substitution")
            source_numbers = self._numbers(" ".join(atom.statement + " " + (atom.evidence_quote or "") for atom in selected_atoms))
            solution_numbers = self._numbers(f"{answer_text} {explanation} {rubric_text}")
            new_solution_numbers = solution_numbers - question_numbers - source_numbers
            if scenario is not None and new_solution_numbers and not self._has_derivation_trace(f"{answer_text} {explanation}"):
                issues.append("number_not_derivable_from_given_conditions: " + ", ".join(sorted(new_solution_numbers)))
        if plan.kernel_type == ProblemKernelType.diagnose_error:
            rule_atoms = [
                atom
                for atom in selected_atoms
                if atom.atom_type in {ContentAtomType.rule, ContentAtomType.procedure, ContentAtomType.formula, ContentAtomType.condition_exception}
            ]
            if rule_atoms and not self._atoms_appear(rule_atoms, explanation):
                issues.append("diagnose_error explanation must name the violated rule/procedure/formula")
        if plan.kernel_type == ProblemKernelType.evidence_to_claim:
            evidence_atoms = [
                atom
                for atom in selected_atoms
                if atom.atom_type in {ContentAtomType.evidence_claim, ContentAtomType.data_table, ContentAtomType.cause_effect, ContentAtomType.comparison}
            ]
            if evidence_atoms and not self._atoms_appear(evidence_atoms, explanation):
                issues.append("evidence_to_claim explanation must link to source evidence terms")
        if plan.kernel_type == ProblemKernelType.compare_boundary:
            boundary_atoms = [
                atom
                for atom in selected_atoms
                if atom.atom_type in {ContentAtomType.comparison, ContentAtomType.classification, ContentAtomType.definition}
            ]
            if boundary_atoms and not self._atoms_appear(boundary_atoms, explanation):
                issues.append("compare_boundary explanation must cite boundary/contrast evidence")
        if plan.kernel_type == ProblemKernelType.trace_process:
            procedure_atoms = [
                atom for atom in selected_atoms if atom.atom_type in {ContentAtomType.procedure, ContentAtomType.code_state}
            ]
            if procedure_atoms and not self._atoms_appear(procedure_atoms, f"{answer_text} {rubric_text} {explanation}"):
                issues.append("trace_process answer/rubric must follow ordered procedure evidence")
        if plan.kernel_type == ProblemKernelType.apply_rule_to_case:
            rule_atoms = [
                atom for atom in selected_atoms if atom.atom_type in {ContentAtomType.rule, ContentAtomType.classification, ContentAtomType.condition_exception}
            ]
            if rule_atoms and not self._atoms_appear(rule_atoms, f"{answer_text} {explanation}"):
                issues.append("apply_rule_to_case answer must explain why the case meets or fails the source condition")
        return issues

    def _missing_scenario_value_names(self, *, question: str, scenario: object) -> list[str]:
        question_numbers = self._numbers(question)
        missing: list[str] = []
        for given in getattr(scenario, "generated_given_values", []) or []:
            given_numbers = self._numbers(str(getattr(given, "value", "")))
            if given_numbers and not given_numbers <= question_numbers:
                missing.append(str(getattr(given, "name", "") or getattr(given, "value", "")))
        return missing

    def _scenario_quote_appears(self, *, explanation: str, plan: ProblemKernelPlan) -> bool:
        scenario = plan.computation_scenario
        if scenario is None:
            return False
        quote = scenario.formula_or_rule_quote
        quote_tokens = self._tokens(quote)
        explanation_tokens = self._tokens(explanation)
        if quote_tokens and quote_tokens & explanation_tokens:
            return True
        variables = set(scenario.variables_or_inputs)
        return bool(variables and any(variable and variable in explanation for variable in variables))

    def _has_derivation_trace(self, text: str) -> bool:
        numbers = self._numbers(text)
        if len(numbers) >= 2 and re.search(r"(=|\+|-|/|\*|×|÷|\\frac|\d+\s*/\s*\d+)", text):
            return True
        return bool(
            numbers
            and re.search(r"(substitut|derive|calculate|대입|계산|유도|나누|곱하|더하|빼)", text, re.IGNORECASE)
        )

    def _distractors_supported(self, problem_data: dict[str, Any]) -> bool:
        if problem_data.get("type") != "multiple_choice":
            return True
        diagnostics = [item for item in (problem_data.get("choice_diagnostics") or []) if not item.get("is_correct")]
        if not diagnostics:
            return False
        why_values = [str(item.get("why_plausible") or "").strip() for item in diagnostics]
        repair_values = [str(item.get("repair_strategy") or "").strip() for item in diagnostics]
        mistake_values = [str(item.get("misconception_id") or item.get("mistake_type") or "").strip() for item in diagnostics]
        generic_cues = ("헷갈릴 수 있다", "다시 확인한다", "review again", "confusing", "check again")
        if any(not value for value in [*why_values, *repair_values, *mistake_values]):
            return False
        if any(any(cue in value.lower() for cue in generic_cues) for value in [*why_values, *repair_values]):
            return False
        return len(set(mistake_values)) == len(mistake_values)

    def _rubric_supported(self, problem_data: dict[str, Any], atoms: list[ContentAtom]) -> bool:
        if problem_data.get("type") != "short_answer":
            return True
        rubric = problem_data.get("rubric") or []
        if not rubric:
            return False
        return all(self._atoms_appear(atoms, self._rubric_item_text(item)) for item in rubric)

    def _rubric_item_text(self, item: dict[str, Any]) -> str:
        parts: list[str] = []
        for value in item.values():
            if isinstance(value, list):
                parts.extend(str(entry) for entry in value)
            else:
                parts.append(str(value))
        return " ".join(parts)

    def _atoms_appear(self, atoms: list[ContentAtom], text: str) -> bool:
        if not text.strip():
            return False
        text_tokens = self._tokens(text)
        for atom in atoms:
            atom_tokens = self._atom_tokens(atom)
            if atom_tokens and atom_tokens & text_tokens:
                return True
            quote = (atom.evidence_quote or atom.statement).strip()
            if len(quote) >= 12 and quote[:40] in text:
                return True
            if atom.atom_type == ContentAtomType.formula and any(symbol and symbol in text for symbol in [*atom.symbols, *atom.variables]):
                return True
        return False

    def _atom_tokens(self, atom: ContentAtom) -> set[str]:
        text = " ".join(
            [
                atom.statement,
                atom.evidence_quote or "",
                " ".join(atom.concepts),
                " ".join(atom.symbols),
                " ".join(atom.variables),
                " ".join(atom.conditions),
                " ".join(atom.exceptions),
            ]
        )
        return self._tokens(text)

    def _tokens(self, text: str) -> set[str]:
        raw_tokens = re.findall(r"[A-Za-z가-힣][A-Za-z가-힣0-9_+\-/]*|\d+(?:\.\d+)?%?", str(text).lower())
        stopwords = {
            "the",
            "and",
            "with",
            "that",
            "this",
            "from",
            "자료",
            "근거",
            "문제",
            "보기",
            "정답",
            "해설",
            "조건",
        }
        return {token for token in raw_tokens if len(token) >= 2 and token not in stopwords}

    def _numbers(self, text: str) -> set[str]:
        numbers: set[str] = set()
        number_pattern = r"(?<![A-Za-z_])[-+]?\d[\d,]*(?:\.\d+)?%?(?![A-Za-z_])"
        fraction_pattern = r"(?<![A-Za-z_])\d+\s*/\s*\d+(?![A-Za-z_])"
        for match in re.findall(f"{fraction_pattern}|{number_pattern}", text):
            normalized = match.replace(",", "").replace(" ", "")
            if normalized.endswith("%"):
                try:
                    numbers.add(str(float(normalized[:-1]) / 100))
                except ValueError:
                    pass
            numbers.add(normalized)
        return numbers
