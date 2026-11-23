from app.schemas.problem_kernels import ContentAtom, ContentAtomType, ProblemKernelType
from app.schemas.problems import GenerateProblemRequest
from app.services.problem_kernel_planner import ProblemKernelPlanner


def atom(
    atom_type: ContentAtomType,
    statement: str = "source statement",
    *,
    concepts: list[str] | None = None,
    confidence: float = 0.9,
) -> ContentAtom:
    return ContentAtom(
        atom_id=f"atom_{atom_type.value}_{abs(hash(statement))}",
        atom_type=atom_type,
        source_chunk_id="chunk_1",
        statement=statement,
        evidence_quote=statement,
        concepts=concepts or ["concept"],
        confidence=confidence,
    )


def request(**overrides) -> GenerateProblemRequest:
    payload = {
        "document_id": "doc_1",
        "concepts": ["concept"],
        "type": "short_answer",
        "count": 1,
    }
    payload.update(overrides)
    return GenerateProblemRequest(**payload)


def test_formula_calculation_selects_compute_from_given():
    plan = ProblemKernelPlanner().plan(
        request=request(problem_style="calculation_practice", difficulty="hard", bloom_level="analyze"),
        content_atoms=[atom(ContentAtomType.formula, "C = Q / V")],
    )

    assert plan.kernel_type == ProblemKernelType.compute_from_given
    assert plan.allows_generated_scenario_values is True
    assert plan.requires_derivation_check is True
    assert plan.required_evidence_roles


def test_compute_from_given_plan_builds_computation_scenario_spec():
    plan = ProblemKernelPlanner().plan(
        request=request(problem_style="calculation_practice", difficulty="hard", bloom_level="analyze"),
        content_atoms=[atom(ContentAtomType.formula, "C_eq = C1 + C2", concepts=["capacitance"])],
    )

    scenario = plan.computation_scenario
    assert scenario is not None
    assert scenario.formula_atom_id in plan.content_atom_ids
    assert scenario.source_chunk_id == "chunk_1"
    assert "C_eq = C1 + C2" in scenario.formula_or_rule_quote
    assert scenario.generated_given_values
    assert any("question stem" in constraint for constraint in scenario.constraints)
    assert any("substitute" in step for step in scenario.required_derivation_steps)


def test_rule_error_detection_selects_diagnose_error():
    plan = ProblemKernelPlanner().plan(
        request=request(type="multiple_choice", problem_style="error_detection"),
        content_atoms=[atom(ContentAtomType.rule, "If memory is allocated on the heap, a destructor should release it.")],
    )

    assert plan.kernel_type == ProblemKernelType.diagnose_error
    assert plan.requires_distinct_distractors is True


def test_evidence_text_selects_evidence_to_claim():
    plan = ProblemKernelPlanner().plan(
        request=request(problem_style="evidence_analysis"),
        content_atoms=[atom(ContentAtomType.evidence_claim, "This evidence supports the claim.")],
    )

    assert plan.kernel_type == ProblemKernelType.evidence_to_claim
    assert plan.requires_source_claim_alignment is True


def test_procedure_hard_request_selects_trace_process():
    plan = ProblemKernelPlanner().plan(
        request=request(problem_style="trace_and_explain", target_rigor="high", quality_mode="strict"),
        content_atoms=[atom(ContentAtomType.procedure, "Step 1 encode, step 2 decode.")],
    )

    assert plan.kernel_type == ProblemKernelType.trace_process
    assert plan.failure_reason is None


def test_definition_only_high_rigor_returns_insufficient_source_structure():
    plan = ProblemKernelPlanner().plan(
        request=request(target_rigor="high", quality_mode="strict", problem_style="exam_application"),
        content_atoms=[atom(ContentAtomType.definition, "A token is defined as a unit of text.")],
    )

    assert plan.failure_reason == "insufficient_source_structure"


def test_concept_comparison_populates_evidence_obligations():
    plan = ProblemKernelPlanner().plan(
        request=request(problem_style="concept_comparison"),
        content_atoms=[atom(ContentAtomType.comparison, "RNNs differ from CNNs in sequence state handling.")],
    )

    assert plan.kernel_type == ProblemKernelType.compare_boundary
    assert [role.role.value for role in plan.required_evidence_roles]


def test_concept_comparison_falls_back_to_two_definitions_with_caution():
    plan = ProblemKernelPlanner().plan(
        request=request(
            concepts=["RNN", "CNN"],
            problem_style="concept_comparison",
            target_rigor="high",
            quality_mode="strict",
        ),
        content_atoms=[
            atom(ContentAtomType.definition, "RNN keeps hidden state across sequence positions.", concepts=["RNN"]),
            atom(ContentAtomType.definition, "CNN applies convolutional filters to local windows.", concepts=["CNN"]),
        ],
    )

    assert plan.kernel_type == ProblemKernelType.compare_boundary
    assert plan.failure_reason is None
    assert plan.caution is not None
    assert {"definition"} <= set(plan.available_atom_types)


def test_evidence_analysis_falls_back_to_example_case_with_caution():
    plan = ProblemKernelPlanner().plan(
        request=request(problem_style="evidence_analysis", target_rigor="high", quality_mode="strict"),
        content_atoms=[
            atom(
                ContentAtomType.example_case,
                "Example: a register shift changes how the same statement is interpreted in context.",
                confidence=0.7,
            )
        ],
    )

    assert plan.kernel_type == ProblemKernelType.evidence_to_claim
    assert plan.failure_reason is None
    assert plan.caution is not None


def test_insufficient_evidence_analysis_reports_closest_alternative_kernel():
    plan = ProblemKernelPlanner().plan(
        request=request(problem_style="evidence_analysis", target_rigor="high", quality_mode="strict"),
        content_atoms=[
            atom(ContentAtomType.comparison, "Genre differs from register in how context is used."),
        ],
    )

    assert plan.failure_reason == "insufficient_source_structure"
    assert plan.closest_alternative_kernel == ProblemKernelType.compare_boundary
    assert "comparison" in plan.available_atom_types
    assert "evidence_claim" in plan.missing_atom_types


def test_high_rigor_plan_cannot_rely_on_single_low_confidence_atom():
    plan = ProblemKernelPlanner().plan(
        request=request(problem_style="concept_comparison", target_rigor="high", quality_mode="strict"),
        content_atoms=[
            atom(
                ContentAtomType.comparison,
                "RNN and CNN are both sequence model terms.",
                confidence=0.3,
            )
        ],
    )

    assert plan.failure_reason == "insufficient_source_structure"
    assert plan.closest_alternative_kernel == ProblemKernelType.compare_boundary
    assert "comparison" in plan.available_atom_types
    assert "comparison" in plan.missing_atom_types


def test_failure_diagnostics_include_available_and_missing_atom_types():
    plan = ProblemKernelPlanner().plan(
        request=request(problem_style="calculation_practice", target_rigor="high", quality_mode="strict"),
        content_atoms=[
            atom(ContentAtomType.definition, "Capacitance is the ability to store charge."),
        ],
    )

    assert plan.failure_reason == "insufficient_source_structure"
    assert plan.available_atom_types == ["definition"]
    assert plan.missing_atom_types == ["formula", "rule"]
    assert plan.closest_alternative_kernel == ProblemKernelType.explain_concept
