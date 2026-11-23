from __future__ import annotations

from collections import Counter
import re

from app.schemas.problem_kernels import (
    AtomConfidenceLevel,
    ComputationScenarioSpec,
    ComputationScenarioValue,
    ContentAtom,
    ContentAtomType,
    EvidenceObligation,
    EvidenceRole,
    ProblemKernelPlan,
    ProblemKernelType,
)
from app.schemas.problems import GenerateProblemRequest, ProblemStyle, ProblemType
from app.schemas.quality import QualityMode, TargetRigor


class ProblemKernelPlanner:
    """Plan problems from source structure instead of subject-specific branches."""

    STRONG_ATOM_TYPES = {
        ContentAtomType.classification,
        ContentAtomType.rule,
        ContentAtomType.formula,
        ContentAtomType.procedure,
        ContentAtomType.comparison,
        ContentAtomType.cause_effect,
        ContentAtomType.condition_exception,
        ContentAtomType.evidence_claim,
        ContentAtomType.data_table,
        ContentAtomType.code_state,
    }

    def plan(self, *, request: GenerateProblemRequest, content_atoms: list[ContentAtom]) -> ProblemKernelPlan:
        atoms = self._rank_atoms(content_atoms)
        high_rigor = request.target_rigor == TargetRigor.high or request.quality_mode == QualityMode.strict
        if high_rigor and not self._has_strong_source_structure(atoms) and not self._has_style_fallback_source_structure(
            request=request,
            atoms=atoms,
        ):
            return self._failure_plan(
                request=request,
                atoms=atoms,
                failure_reason="insufficient_source_structure",
                desired_kernel=self._desired_kernel_for_style(request.problem_style),
            )

        style = request.problem_style
        if style == ProblemStyle.calculation_practice:
            return self._plan_from_atom_types(
                request=request,
                atoms=atoms,
                preferred_types=(ContentAtomType.formula, ContentAtomType.rule),
                kernel_type=ProblemKernelType.compute_from_given,
                roles=(EvidenceRole.formula, EvidenceRole.rule),
                allows_generated_scenario_values=True,
                requires_derivation_check=True,
                anti_patterns=("answer-only numbers", "formula not cited", "calculation without derivation"),
            )
        if style == ProblemStyle.error_detection:
            return self._plan_from_atom_types(
                request=request,
                atoms=atoms,
                preferred_types=(
                    ContentAtomType.rule,
                    ContentAtomType.procedure,
                    ContentAtomType.formula,
                    ContentAtomType.condition_exception,
                ),
                kernel_type=ProblemKernelType.diagnose_error,
                roles=(EvidenceRole.rule, EvidenceRole.procedure_step, EvidenceRole.condition),
                requires_distinct_distractors=request.type == ProblemType.multiple_choice,
                anti_patterns=("generic error", "uncited violated rule", "same misconception repeated"),
            )
        if style == ProblemStyle.evidence_analysis:
            return self._plan_from_atom_types(
                request=request,
                atoms=atoms,
                preferred_types=(
                    ContentAtomType.evidence_claim,
                    ContentAtomType.cause_effect,
                    ContentAtomType.procedure,
                    ContentAtomType.rule,
                ),
                kernel_type=ProblemKernelType.evidence_to_claim,
                roles=(EvidenceRole.source_claim, EvidenceRole.data_point, EvidenceRole.contrast),
                requires_source_claim_alignment=True,
                anti_patterns=("claim without evidence", "source quote copied as answer"),
                fallback_types=(ContentAtomType.data_table, ContentAtomType.example_case),
                fallback_caution="evidence_to_claim uses indirect data/example evidence because no explicit evidence_claim atom was found",
            )
        if style in {ProblemStyle.concept_comparison, ProblemStyle.concept_boundary}:
            return self._plan_from_atom_types(
                request=request,
                atoms=atoms,
                preferred_types=(ContentAtomType.comparison,),
                kernel_type=ProblemKernelType.compare_boundary,
                roles=(EvidenceRole.contrast, EvidenceRole.definition, EvidenceRole.rule),
                requires_distinct_distractors=request.type == ProblemType.multiple_choice,
                anti_patterns=("one-sided comparison", "definition-only boundary"),
                fallback_types=(ContentAtomType.classification, ContentAtomType.definition),
                fallback_caution="compare_boundary uses definitions/classifications for both concepts because no explicit comparison atom was found",
            )
        if style == ProblemStyle.condition_mutation:
            return self._plan_from_atom_types(
                request=request,
                atoms=atoms,
                preferred_types=(ContentAtomType.condition_exception, ContentAtomType.rule, ContentAtomType.cause_effect),
                kernel_type=ProblemKernelType.condition_mutation,
                roles=(EvidenceRole.condition, EvidenceRole.exception, EvidenceRole.rule),
                anti_patterns=("condition not changed", "unstated exception"),
            )
        if style == ProblemStyle.trace_and_explain:
            return self._plan_from_atom_types(
                request=request,
                atoms=atoms,
                preferred_types=(ContentAtomType.procedure, ContentAtomType.code_state, ContentAtomType.rule),
                kernel_type=ProblemKernelType.trace_process,
                roles=(EvidenceRole.procedure_step, EvidenceRole.rule),
                anti_patterns=("state jump", "missing ordered step"),
            )
        if style == ProblemStyle.design_under_constraint:
            return self._plan_from_atom_types(
                request=request,
                atoms=atoms,
                preferred_types=(ContentAtomType.rule, ContentAtomType.condition_exception, ContentAtomType.comparison),
                kernel_type=ProblemKernelType.design_under_constraints,
                roles=(EvidenceRole.rule, EvidenceRole.condition, EvidenceRole.contrast),
                anti_patterns=("constraint ignored", "unsupported design choice"),
            )
        if style in {ProblemStyle.exam_application, ProblemStyle.auto, ProblemStyle.misconception_drill}:
            return self._exam_application_plan(request=request, atoms=atoms)

        return self._definition_plan(request=request, atoms=atoms)

    def _exam_application_plan(
        self,
        *,
        request: GenerateProblemRequest,
        atoms: list[ContentAtom],
    ) -> ProblemKernelPlan:
        if len([concept for concept in request.concepts if str(concept or "").strip()]) >= 2:
            comparison_atoms = self._select_atoms(atoms, (ContentAtomType.comparison,))
            if comparison_atoms:
                return self._plan(
                    request=request,
                    selected_atoms=comparison_atoms,
                    kernel_type=ProblemKernelType.compare_boundary,
                    roles=(EvidenceRole.contrast,),
                    requires_distinct_distractors=request.type == ProblemType.multiple_choice,
                    anti_patterns=self._anti_patterns_for_kernel(ProblemKernelType.compare_boundary),
                    diagnostic_atoms=atoms,
                )
        priority = (
            (ContentAtomType.formula, ProblemKernelType.compute_from_given, EvidenceRole.formula),
            (ContentAtomType.rule, ProblemKernelType.apply_rule_to_case, EvidenceRole.rule),
            (ContentAtomType.procedure, ProblemKernelType.trace_process, EvidenceRole.procedure_step),
            (ContentAtomType.code_state, ProblemKernelType.trace_process, EvidenceRole.procedure_step),
            (ContentAtomType.evidence_claim, ProblemKernelType.evidence_to_claim, EvidenceRole.source_claim),
            (ContentAtomType.data_table, ProblemKernelType.evidence_to_claim, EvidenceRole.data_point),
            (ContentAtomType.comparison, ProblemKernelType.compare_boundary, EvidenceRole.contrast),
            (ContentAtomType.condition_exception, ProblemKernelType.condition_mutation, EvidenceRole.condition),
            (ContentAtomType.classification, ProblemKernelType.apply_rule_to_case, EvidenceRole.definition),
        )
        for atom_type, kernel_type, role in priority:
            selected = self._select_atoms(atoms, (atom_type,))
            if selected:
                return self._plan(
                    request=request,
                    selected_atoms=selected,
                    kernel_type=kernel_type,
                    roles=(role,),
                    allows_generated_scenario_values=kernel_type == ProblemKernelType.compute_from_given,
                    requires_derivation_check=kernel_type == ProblemKernelType.compute_from_given,
                    requires_distinct_distractors=request.type == ProblemType.multiple_choice,
                    requires_source_claim_alignment=kernel_type == ProblemKernelType.evidence_to_claim,
                    anti_patterns=self._anti_patterns_for_kernel(kernel_type),
                )
        return self._definition_plan(request=request, atoms=atoms)

    def _desired_kernel_for_style(self, style: ProblemStyle) -> ProblemKernelType | None:
        return {
            ProblemStyle.calculation_practice: ProblemKernelType.compute_from_given,
            ProblemStyle.error_detection: ProblemKernelType.diagnose_error,
            ProblemStyle.evidence_analysis: ProblemKernelType.evidence_to_claim,
            ProblemStyle.concept_comparison: ProblemKernelType.compare_boundary,
            ProblemStyle.concept_boundary: ProblemKernelType.compare_boundary,
            ProblemStyle.condition_mutation: ProblemKernelType.condition_mutation,
            ProblemStyle.trace_and_explain: ProblemKernelType.trace_process,
            ProblemStyle.design_under_constraint: ProblemKernelType.design_under_constraints,
        }.get(style)

    def _plan_from_atom_types(
        self,
        *,
        request: GenerateProblemRequest,
        atoms: list[ContentAtom],
        preferred_types: tuple[ContentAtomType, ...],
        kernel_type: ProblemKernelType,
        roles: tuple[EvidenceRole, ...],
        allows_generated_scenario_values: bool = False,
        requires_derivation_check: bool = False,
        requires_distinct_distractors: bool = False,
        requires_source_claim_alignment: bool = False,
        anti_patterns: tuple[str, ...] = (),
        fallback_types: tuple[ContentAtomType, ...] = (),
        fallback_caution: str | None = None,
    ) -> ProblemKernelPlan:
        high_rigor = request.target_rigor == TargetRigor.high or request.quality_mode == QualityMode.strict
        selected = self._select_atoms(atoms, preferred_types)
        caution = None
        if not selected and fallback_types:
            selected = self._fallback_atoms_for_kernel(
                request=request,
                atoms=atoms,
                fallback_types=fallback_types,
                kernel_type=kernel_type,
            )
            caution = fallback_caution if selected else None
        if not selected:
            if high_rigor:
                return self._failure_plan(
                    request=request,
                    atoms=atoms,
                    failure_reason="insufficient_source_structure",
                    desired_kernel=kernel_type,
                )
            return self._definition_plan(request=request, atoms=atoms)
        if high_rigor and not self._selection_sufficient_for_high_rigor(selected):
            return self._failure_plan(
                request=request,
                atoms=atoms,
                failure_reason="insufficient_source_structure",
                desired_kernel=kernel_type,
            )
        return self._plan(
            request=request,
            selected_atoms=selected,
            kernel_type=kernel_type,
            roles=tuple(self._roles_supported_by_atoms(roles=roles, atoms=selected)),
            allows_generated_scenario_values=allows_generated_scenario_values,
            requires_derivation_check=requires_derivation_check,
            requires_distinct_distractors=requires_distinct_distractors,
            requires_source_claim_alignment=requires_source_claim_alignment,
            anti_patterns=anti_patterns,
            caution=caution,
            diagnostic_atoms=atoms,
        )

    def _definition_plan(self, *, request: GenerateProblemRequest, atoms: list[ContentAtom]) -> ProblemKernelPlan:
        selected = self._select_atoms(atoms, (ContentAtomType.definition, ContentAtomType.example_case)) or atoms[:3]
        return self._plan(
            request=request,
            selected_atoms=selected,
            kernel_type=ProblemKernelType.explain_concept,
            roles=(EvidenceRole.definition,),
            anti_patterns=("definition-only high-rigor item", "uncited concept paraphrase"),
            diagnostic_atoms=atoms,
        )

    def _failure_plan(
        self,
        *,
        request: GenerateProblemRequest,
        atoms: list[ContentAtom],
        failure_reason: str,
        desired_kernel: ProblemKernelType | None = None,
    ) -> ProblemKernelPlan:
        selected = atoms[:3]
        return self._plan(
            request=request,
            selected_atoms=selected,
            kernel_type=desired_kernel or ProblemKernelType.recall_define,
            roles=(EvidenceRole.definition,),
            anti_patterns=("forced shallow generation",),
            failure_reason=failure_reason,
            diagnostic_atoms=atoms,
            missing_atom_types=self._missing_atom_types_for_kernel(desired_kernel or ProblemKernelType.recall_define),
            closest_alternative_kernel=self._closest_alternative_kernel(
                atoms=atoms,
                desired_kernel=desired_kernel,
            ),
        )

    def _plan(
        self,
        *,
        request: GenerateProblemRequest,
        selected_atoms: list[ContentAtom],
        kernel_type: ProblemKernelType,
        roles: tuple[EvidenceRole, ...],
        allows_generated_scenario_values: bool = False,
        requires_derivation_check: bool = False,
        requires_distinct_distractors: bool = False,
        requires_source_claim_alignment: bool = False,
        anti_patterns: tuple[str, ...] = (),
        failure_reason: str | None = None,
        caution: str | None = None,
        diagnostic_atoms: list[ContentAtom] | None = None,
        missing_atom_types: list[str] | None = None,
        closest_alternative_kernel: ProblemKernelType | None = None,
    ) -> ProblemKernelPlan:
        obligations = [
            EvidenceObligation(
                role=role,
                required=True,
                must_be_cited=True,
                must_appear_in=self._placements_for_role(role, request=request),
                notes=self._role_note(role),
            )
            for role in self._dedupe_roles(roles)
        ]
        computation_scenario = (
            self._build_computation_scenario(selected_atoms)
            if (
                kernel_type == ProblemKernelType.compute_from_given
                and failure_reason is None
                and request.problem_style == ProblemStyle.calculation_practice
            )
            else None
        )
        return ProblemKernelPlan(
            kernel_type=kernel_type,
            content_atom_ids=[atom.atom_id for atom in selected_atoms[:6]],
            target_cognitive_level=request.bloom_level.value,
            required_evidence_roles=obligations,
            allows_generated_scenario_values=allows_generated_scenario_values,
            requires_derivation_check=requires_derivation_check,
            requires_distinct_distractors=requires_distinct_distractors,
            requires_source_claim_alignment=requires_source_claim_alignment,
            anti_patterns=list(anti_patterns),
            failure_reason=failure_reason,
            caution=caution,
            available_atom_types=self._available_atom_types(diagnostic_atoms or selected_atoms),
            missing_atom_types=missing_atom_types or [],
            closest_alternative_kernel=closest_alternative_kernel,
            computation_scenario=computation_scenario,
        )

    def _build_computation_scenario(self, selected_atoms: list[ContentAtom]) -> ComputationScenarioSpec | None:
        formula_atoms = [atom for atom in selected_atoms if atom.atom_type == ContentAtomType.formula]
        rule_atoms = [atom for atom in selected_atoms if atom.atom_type == ContentAtomType.rule]
        formula_atom = (formula_atoms or rule_atoms or selected_atoms[:1])[0] if selected_atoms else None
        if formula_atom is None:
            return None
        quote = (formula_atom.evidence_quote or formula_atom.statement).strip()
        variables = self._formula_variables(formula_atom)
        generated_values = self._generated_values_for_variables(variables)
        return ComputationScenarioSpec(
            formula_atom_id=formula_atom.atom_id,
            source_chunk_id=formula_atom.source_chunk_id,
            formula_or_rule_quote=quote[:1200],
            variables_or_inputs=variables,
            generated_given_values=generated_values,
            required_derivation_steps=[
                "state the cited source formula or rule",
                "substitute every generated_given_value from the question stem",
                "show at least one calculation or algebraic derivation step",
                "state the final result with units or interpretation",
            ],
            required_interpretation="Explain what the computed value means under the stem conditions.",
            constraints=[
                "question stem must include every generated_given_value",
                "explanation must cite formula_or_rule_quote or its exact variable relation",
                "answer/explanation must not introduce answer-only numbers",
                "generated values are scenario inputs, not claimed source facts",
            ],
            prohibited_patterns=[
                "formula not cited",
                "answer-only number",
                "calculation without substitution",
                "new source factual number not present in source",
            ],
        )

    def _formula_variables(self, atom: ContentAtom) -> list[str]:
        explicit = [value for value in [*atom.variables, *atom.symbols] if str(value).strip()]
        if explicit:
            return list(dict.fromkeys(str(value).strip() for value in explicit))[:4]
        text = (atom.evidence_quote or atom.statement).strip()
        rhs_text = text
        if "=" in text:
            rhs_text = text.split("=", 1)[1]
        identifiers = re.findall(r"\b[A-Za-z][A-Za-z0-9_]*\b", rhs_text)
        ignore = {
            "and",
            "as",
            "by",
            "for",
            "from",
            "if",
            "in",
            "is",
            "log",
            "max",
            "min",
            "of",
            "or",
            "rule",
            "the",
            "then",
            "to",
            "when",
            "where",
            "with",
        }
        variables = [
            identifier
            for identifier in identifiers
            if identifier.lower() not in ignore and not identifier.lower().startswith("eq")
        ]
        if not variables and atom.concepts:
            variables = [re.sub(r"\W+", "_", concept).strip("_") for concept in atom.concepts[:2]]
        if not variables:
            variables = ["input_1", "input_2"]
        return list(dict.fromkeys(variable for variable in variables if variable))[:4]

    def _generated_values_for_variables(self, variables: list[str]) -> list[ComputationScenarioValue]:
        if not variables:
            variables = ["input_1", "input_2"]
        values: list[ComputationScenarioValue] = []
        used_names: set[str] = set()
        for index, variable in enumerate(variables[:4], start=1):
            name = str(variable).strip() or f"input_{index}"
            if name in used_names:
                continue
            used_names.add(name)
            value, unit, role = self._default_value_for_variable(name, index)
            values.append(
                ComputationScenarioValue(
                    name=name,
                    value=value,
                    unit=unit,
                    role=role,
                )
            )
        if len(values) == 1:
            values.append(
                ComputationScenarioValue(
                    name="given_condition",
                    value="2",
                    unit=None,
                    role="second generated scenario input needed for computation",
                )
            )
        return values

    def _default_value_for_variable(self, name: str, index: int) -> tuple[str, str | None, str]:
        lower = name.lower()
        if lower.startswith("c") and any(char.isdigit() for char in lower):
            return (str(index + 1), "uF", "given capacitance value")
        if lower in {"c", "ceq", "c_eq"} or "capacit" in lower:
            return (str(index + 1), "uF", "given capacitance-related value")
        if lower.startswith("q"):
            return (str(6 * index), "C", "given charge or quantity")
        if lower.startswith("v"):
            return (str(index + 1), "V", "given voltage")
        if lower.startswith("r"):
            return ("0.1", None, "given rate")
        if lower.startswith("p"):
            return ("10", None, "given price or parameter")
        if lower.startswith("n") or "month" in lower:
            return ("3", None, "given count or period")
        return (str(2 * index), None, "generated scenario input")

    def _rank_atoms(self, atoms: list[ContentAtom]) -> list[ContentAtom]:
        return sorted(
            atoms,
            key=lambda atom: (
                atom.atom_type in self.STRONG_ATOM_TYPES,
                self._confidence_rank(atom),
                atom.confidence,
                len(atom.concepts),
            ),
            reverse=True,
        )

    def _select_atoms(self, atoms: list[ContentAtom], atom_types: tuple[ContentAtomType, ...]) -> list[ContentAtom]:
        selected = [atom for atom in atoms if atom.atom_type in atom_types]
        if not selected:
            return []
        chunk_counts = Counter(atom.source_chunk_id for atom in selected)
        ranked = sorted(
            selected,
            key=lambda atom: (
                self._confidence_rank(atom),
                chunk_counts[atom.source_chunk_id],
                atom.confidence,
                len(atom.statement),
            ),
            reverse=True,
        )
        reliable = [atom for atom in ranked if self._confidence_level(atom) != AtomConfidenceLevel.low]
        return (reliable or ranked)[:6]

    def _has_strong_source_structure(self, atoms: list[ContentAtom]) -> bool:
        strong_atoms = [atom for atom in atoms if atom.atom_type in self.STRONG_ATOM_TYPES]
        reliable = [atom for atom in strong_atoms if self._confidence_level(atom) != AtomConfidenceLevel.low]
        low = [atom for atom in strong_atoms if self._confidence_level(atom) == AtomConfidenceLevel.low]
        return bool(reliable) or len(low) >= 2

    def _has_style_fallback_source_structure(
        self,
        *,
        request: GenerateProblemRequest,
        atoms: list[ContentAtom],
    ) -> bool:
        if request.problem_style in {ProblemStyle.concept_comparison, ProblemStyle.concept_boundary}:
            fallback_atoms = [
                atom
                for atom in atoms
                if atom.atom_type in {ContentAtomType.definition, ContentAtomType.classification}
            ]
            return len(self._covered_requested_concepts(request=request, atoms=fallback_atoms)) >= 2
        if request.problem_style == ProblemStyle.evidence_analysis:
            return any(atom.atom_type in {ContentAtomType.data_table, ContentAtomType.example_case} for atom in atoms)
        return False

    def _selection_sufficient_for_high_rigor(self, selected: list[ContentAtom]) -> bool:
        reliable = [atom for atom in selected if self._confidence_level(atom) != AtomConfidenceLevel.low]
        low = [atom for atom in selected if self._confidence_level(atom) == AtomConfidenceLevel.low]
        return bool(reliable) or len(low) >= 2

    def _fallback_atoms_for_kernel(
        self,
        *,
        request: GenerateProblemRequest,
        atoms: list[ContentAtom],
        fallback_types: tuple[ContentAtomType, ...],
        kernel_type: ProblemKernelType,
    ) -> list[ContentAtom]:
        selected = self._select_atoms(atoms, fallback_types)
        if kernel_type == ProblemKernelType.compare_boundary:
            if len(self._covered_requested_concepts(request=request, atoms=selected)) < 2:
                return []
            return selected
        if kernel_type == ProblemKernelType.evidence_to_claim:
            return selected[:6]
        return selected

    def _covered_requested_concepts(
        self,
        *,
        request: GenerateProblemRequest,
        atoms: list[ContentAtom],
    ) -> set[str]:
        requested = [str(concept or "").strip().lower() for concept in request.concepts if str(concept or "").strip()]
        covered: set[str] = set()
        for atom in atoms:
            searchable = " ".join([atom.statement, *atom.concepts]).lower()
            for concept in requested:
                if concept and concept in searchable:
                    covered.add(concept)
        return covered

    def _confidence_level(self, atom: ContentAtom) -> AtomConfidenceLevel:
        if atom.confidence >= 0.75:
            return AtomConfidenceLevel.high
        if atom.confidence >= 0.55:
            return AtomConfidenceLevel.medium
        return AtomConfidenceLevel.low

    def _confidence_rank(self, atom: ContentAtom) -> int:
        return {
            AtomConfidenceLevel.high: 3,
            AtomConfidenceLevel.medium: 2,
            AtomConfidenceLevel.low: 1,
        }[self._confidence_level(atom)]

    def _available_atom_types(self, atoms: list[ContentAtom]) -> list[str]:
        return sorted({atom.atom_type.value for atom in atoms})

    def _missing_atom_types_for_kernel(self, kernel_type: ProblemKernelType) -> list[str]:
        kernel_map = {
            ProblemKernelType.compute_from_given: ["formula", "rule"],
            ProblemKernelType.diagnose_error: ["rule", "procedure", "formula", "condition_exception"],
            ProblemKernelType.evidence_to_claim: ["evidence_claim", "data_table", "example_case"],
            ProblemKernelType.compare_boundary: ["comparison", "classification", "definition"],
            ProblemKernelType.trace_process: ["procedure", "code_state"],
            ProblemKernelType.condition_mutation: ["condition_exception", "rule"],
            ProblemKernelType.apply_rule_to_case: ["rule", "classification"],
        }
        return kernel_map.get(kernel_type, [])

    def _closest_alternative_kernel(
        self,
        *,
        atoms: list[ContentAtom],
        desired_kernel: ProblemKernelType | None,
    ) -> ProblemKernelType | None:
        atom_types = {atom.atom_type for atom in atoms}
        if desired_kernel == ProblemKernelType.compare_boundary and atom_types & {ContentAtomType.comparison}:
            return ProblemKernelType.compare_boundary
        if desired_kernel == ProblemKernelType.evidence_to_claim and atom_types & {ContentAtomType.evidence_claim}:
            return ProblemKernelType.evidence_to_claim
        if desired_kernel == ProblemKernelType.evidence_to_claim and atom_types & {ContentAtomType.comparison}:
            return ProblemKernelType.compare_boundary
        if desired_kernel == ProblemKernelType.compare_boundary:
            if atom_types & {ContentAtomType.classification, ContentAtomType.rule}:
                return ProblemKernelType.apply_rule_to_case
            if atom_types & {ContentAtomType.definition}:
                return ProblemKernelType.explain_concept
        priority = (
            ({ContentAtomType.formula}, ProblemKernelType.compute_from_given),
            ({ContentAtomType.rule, ContentAtomType.classification}, ProblemKernelType.apply_rule_to_case),
            ({ContentAtomType.procedure, ContentAtomType.code_state}, ProblemKernelType.trace_process),
            ({ContentAtomType.evidence_claim, ContentAtomType.data_table, ContentAtomType.example_case}, ProblemKernelType.evidence_to_claim),
            ({ContentAtomType.comparison}, ProblemKernelType.compare_boundary),
            ({ContentAtomType.condition_exception}, ProblemKernelType.condition_mutation),
            ({ContentAtomType.definition}, ProblemKernelType.explain_concept),
        )
        for types, kernel in priority:
            if atom_types & types and kernel != desired_kernel:
                return kernel
        return None

    def _dedupe_roles(self, roles: tuple[EvidenceRole, ...]) -> list[EvidenceRole]:
        return list(dict.fromkeys(roles))

    def _placements_for_role(self, role: EvidenceRole, *, request: GenerateProblemRequest) -> list[str]:
        if role in {EvidenceRole.formula, EvidenceRole.rule, EvidenceRole.procedure_step}:
            placements = ["explanation"]
        elif role in {EvidenceRole.condition, EvidenceRole.exception, EvidenceRole.contrast}:
            placements = ["question", "explanation"]
        else:
            placements = ["answer", "explanation"]
        return list(dict.fromkeys(placements))

    def _roles_supported_by_atoms(
        self,
        *,
        roles: tuple[EvidenceRole, ...],
        atoms: list[ContentAtom],
    ) -> list[EvidenceRole]:
        atom_types = {atom.atom_type for atom in atoms}
        supported: list[EvidenceRole] = []
        role_atom_types = {
            EvidenceRole.definition: {ContentAtomType.definition, ContentAtomType.classification},
            EvidenceRole.rule: {ContentAtomType.rule, ContentAtomType.classification, ContentAtomType.condition_exception},
            EvidenceRole.formula: {ContentAtomType.formula},
            EvidenceRole.condition: {ContentAtomType.condition_exception, ContentAtomType.rule, ContentAtomType.cause_effect},
            EvidenceRole.exception: {ContentAtomType.condition_exception},
            EvidenceRole.contrast: {ContentAtomType.comparison, ContentAtomType.classification},
            EvidenceRole.example: {ContentAtomType.example_case},
            EvidenceRole.procedure_step: {ContentAtomType.procedure, ContentAtomType.code_state, ContentAtomType.rule},
            EvidenceRole.data_point: {ContentAtomType.data_table, ContentAtomType.formula},
            EvidenceRole.example: {ContentAtomType.example_case},
            EvidenceRole.source_claim: {
                ContentAtomType.evidence_claim,
                ContentAtomType.cause_effect,
                ContentAtomType.comparison,
                ContentAtomType.procedure,
                ContentAtomType.rule,
                ContentAtomType.example_case,
            },
        }
        for role in roles:
            if atom_types & role_atom_types.get(role, set()):
                supported.append(role)
        return supported or list(roles[:1])

    def _role_note(self, role: EvidenceRole) -> str:
        notes = {
            EvidenceRole.formula: "Use the source formula/rule, and show a derivation when values are generated.",
            EvidenceRole.rule: "Cite the violated or applied rule in the explanation.",
            EvidenceRole.procedure_step: "Track the source procedure in order without skipping state changes.",
            EvidenceRole.condition: "Make the condition or exception explicit in the stem and explanation.",
            EvidenceRole.contrast: "Explain the boundary separating the compared concepts.",
            EvidenceRole.source_claim: "Connect the answer claim to cited source evidence.",
            EvidenceRole.data_point: "Use cited data/table evidence, not general knowledge.",
        }
        return notes.get(role, "Tie this required evidence role to cited source material.")

    def _anti_patterns_for_kernel(self, kernel_type: ProblemKernelType) -> tuple[str, ...]:
        return {
            ProblemKernelType.compute_from_given: (
                "answer-only numbers",
                "formula not cited",
                "calculation without derivation",
            ),
            ProblemKernelType.apply_rule_to_case: ("uncited source rule", "generic domain fact"),
            ProblemKernelType.trace_process: ("state jump", "missing ordered step"),
            ProblemKernelType.evidence_to_claim: ("claim without evidence", "source quote copied as answer"),
            ProblemKernelType.compare_boundary: ("one-sided comparison", "definition-only boundary"),
            ProblemKernelType.condition_mutation: ("condition not changed", "unstated exception"),
        }.get(kernel_type, ("shallow recall",))
