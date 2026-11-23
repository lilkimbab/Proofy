from datetime import datetime, timezone
from types import SimpleNamespace

from app.agents.feedback_agent import FeedbackAgent
from app.agents.problem_agent import ProblemAgent
from app.agents.quality_checker import ProblemQualityChecker
from app.api.problems import to_problem_response
from app.config import Settings
from app.schemas.integration_contracts import RetrievedChunk
from app.schemas.problem_kernels import (
    ContentAtom,
    ContentAtomType,
    EvidenceLink,
    EvidenceObligation,
    EvidenceRole,
    ProblemKernelPlan,
    ProblemKernelType,
)
from app.schemas.problems import CognitiveLevel, GenerateProblemRequest, ItemDesignBrief, MistakeType
from app.services.problem_answer_verifier import ProblemAnswerVerifier
from app.services.evidence_obligation_evaluator import EvidenceObligationEvaluator


def kernel_atom(atom_type: ContentAtomType = ContentAtomType.formula) -> ContentAtom:
    return ContentAtom(
        atom_id=f"atom_{atom_type.value}",
        atom_type=atom_type,
        source_chunk_id="chunk_1",
        statement="Net amount = gross amount - discount.",
        evidence_quote="Net amount = gross amount - discount.",
        concepts=["net amount"],
        confidence=0.9,
    )


def kernel_plan(kernel_type: ProblemKernelType = ProblemKernelType.compute_from_given) -> ProblemKernelPlan:
    return ProblemKernelPlan(
        kernel_type=kernel_type,
        content_atom_ids=["atom_formula"],
        target_cognitive_level="analyze",
        required_evidence_roles=[
            EvidenceObligation(
                role=EvidenceRole.formula,
                must_appear_in=["explanation", "rubric"],
            )
        ],
        allows_generated_scenario_values=kernel_type == ProblemKernelType.compute_from_given,
        requires_derivation_check=kernel_type == ProblemKernelType.compute_from_given,
    )


def test_kernel_metadata_validates_inside_item_design_brief_and_is_hidden_from_student_response():
    atom = kernel_atom()
    plan = kernel_plan()
    design = ItemDesignBrief(
        target_concept="net amount",
        prerequisite_concepts=[],
        learning_objective="Apply a formula to a stated scenario.",
        cognitive_level=CognitiveLevel.apply,
        assessment_claim="Learner can compute from source formula.",
        observable_evidence=["Uses formula"],
        expected_reasoning_steps=["Identify formula", "Substitute values"],
        item_type="short_answer",
        difficulty="hard",
        context_strategy="Use scenario values stated in the question.",
        scoring_strategy="Award for formula, substitution, and result.",
        content_atoms=[atom],
        problem_kernel_plan=plan,
        evidence_links=[
            EvidenceLink(
                atom_id=atom.atom_id,
                source_chunk_id=atom.source_chunk_id,
                evidence_role="formula",
                evidence_quote=atom.evidence_quote or atom.statement,
                used_in=["answer", "explanation"],
                supported_claim="The answer applies the formula.",
            )
        ],
    )
    problem = SimpleNamespace(
        id="problem_1",
        document_id="doc_1",
        type="short_answer",
        difficulty="hard",
        bloom_level="analyze",
        question="Question",
        choices=None,
        concepts=["net amount"],
        source_chunk_ids=["chunk_1"],
        source_refs=None,
        source_grounding_notes=[],
        quality_status="passed",
        created_at=datetime.now(timezone.utc),
        item_model_id=None,
        item_design_brief=design.model_dump(mode="json"),
        difficulty_profile=None,
        teacher_review_checklist=None,
        professor_grade_score=None,
        student_response_simulation=None,
        explanation="Explanation",
        answer={"choice_id": None, "text": "Answer"},
        choice_explanations=None,
        choice_diagnostics=None,
        rubric=[{"criterion": "Uses formula", "points": 1}],
    )

    student_response = to_problem_response(problem, include_solution=True, include_internal=False)
    internal_response = to_problem_response(problem, include_solution=True, include_internal=True)

    assert student_response.item_design_brief is None
    assert internal_response.item_design_brief is not None
    assert internal_response.item_design_brief.problem_kernel_plan.kernel_type == ProblemKernelType.compute_from_given
    assert internal_response.item_design_brief.evidence_links


def test_evidence_link_v2_schema_validates_list_placements_and_link_id():
    link = EvidenceLink(
        atom_id="atom_formula",
        source_chunk_id="chunk_1",
        evidence_role="formula",
        evidence_quote="Net amount = gross amount - discount.",
        used_in=["answer", "explanation"],
        supported_claim="The answer uses the net amount formula.",
    )

    assert link.link_id.startswith("link_atom_formula_formula")
    assert link.used_in == ["answer", "explanation"]


def test_problem_prompt_includes_kernel_plan_when_enabled_and_omits_when_disabled():
    chunk = RetrievedChunk(chunk_id="chunk_1", document_id="doc_1", content="Net = gross - discount.")
    atom = kernel_atom()
    plan = kernel_plan()
    request_json = {
        "document_id": "doc_1",
        "concepts": ["net amount"],
        "type": "short_answer",
        "count": 1,
        "problem_style": "calculation_practice",
    }

    enabled_prompt = ProblemAgent(settings=Settings(OPENAI_API_KEY=None))._build_prompt(
        GenerateProblemRequest(**request_json),
        [chunk],
        content_atoms=[atom],
        problem_kernel_plan=plan,
    )
    disabled_prompt = ProblemAgent(
        settings=Settings(OPENAI_API_KEY=None, PROBLEM_AGENT_USE_DOMAIN_GENERAL_KERNELS=False)
    )._build_prompt(
        GenerateProblemRequest(**request_json),
        [chunk],
        content_atoms=[atom],
        problem_kernel_plan=plan,
    )

    assert "Problem Kernel Plan" in enabled_prompt
    assert "Evidence Contract" in enabled_prompt
    assert "answer_supported_by" in enabled_prompt
    assert "새 숫자/시나리오 값을 만들 수 있다" in enabled_prompt
    assert "Problem Kernel Plan" not in disabled_prompt


def test_quality_checker_flags_uncited_kernel_obligation():
    rule_atom = kernel_atom(ContentAtomType.rule)
    plan = ProblemKernelPlan(
        kernel_type=ProblemKernelType.diagnose_error,
        content_atom_ids=[rule_atom.atom_id],
        target_cognitive_level="analyze",
        required_evidence_roles=[EvidenceObligation(role=EvidenceRole.rule, must_appear_in=["explanation"])],
    )
    problem = {
        "document_id": "doc_1",
        "type": "short_answer",
        "difficulty": "hard",
        "bloom_level": "analyze",
        "question": "Which step violates the rule?",
        "choices": None,
        "answer": {"choice_id": None, "text": "The step violates the rule."},
        "explanation": "The violated rule is not tied to the cited source.",
        "choice_explanations": None,
        "choice_diagnostics": None,
        "rubric": [{"criterion": "Identify the violated rule", "points": 1, "expected_evidence": ["rule"]}],
        "concepts": ["net amount"],
        "source_chunk_ids": ["other_chunk"],
    }
    chunks = [
        RetrievedChunk(chunk_id="chunk_1", document_id="doc_1", content="Net amount = gross amount - discount."),
        RetrievedChunk(chunk_id="other_chunk", document_id="doc_1", content="Unrelated context."),
    ]
    request = GenerateProblemRequest(
        document_id="doc_1",
        concepts=["net amount"],
        type="short_answer",
        count=1,
        difficulty="hard",
        bloom_level="analyze",
        target_rigor="high",
        quality_mode="strict",
        problem_style="error_detection",
    )

    is_valid, _errors, report = ProblemQualityChecker().validate_with_quality_report(
        problem,
        retrieved_chunks=chunks,
        request=request,
        content_atoms=[rule_atom],
        problem_kernel_plan=plan,
    )

    assert is_valid is False
    assert any("source_chunk_ids do not match selected atoms" in issue for issue in report.item_model_quality_issues)


def test_quality_checker_requires_atom_evidence_terms_in_explanation():
    atom = kernel_atom(ContentAtomType.formula)
    plan = kernel_plan()
    problem = {
        "document_id": "doc_1",
        "type": "short_answer",
        "difficulty": "hard",
        "bloom_level": "analyze",
        "question": "Compute the net amount when gross amount is 100 and discount is 20.",
        "choices": None,
        "answer": {"choice_id": None, "text": "80"},
        "explanation": "Use the cited source to compute the result.",
        "choice_explanations": None,
        "choice_diagnostics": None,
        "rubric": [{"criterion": "Uses the source relation", "points": 1}],
        "concepts": ["net amount"],
        "source_chunk_ids": ["chunk_1"],
    }

    is_valid, _errors, report = ProblemQualityChecker().validate_with_quality_report(
        problem,
        retrieved_chunks=[RetrievedChunk(chunk_id="chunk_1", document_id="doc_1", content=atom.statement)],
        request=GenerateProblemRequest(
            document_id="doc_1",
            concepts=["net amount"],
            type="short_answer",
            count=1,
            quality_mode="strict",
        ),
        content_atoms=[atom],
        problem_kernel_plan=plan,
    )

    assert is_valid is False
    assert any("not linked in explanation" in issue for issue in report.item_model_quality_issues)


def test_quality_checker_accepts_atom_evidence_terms_in_explanation():
    atom = kernel_atom(ContentAtomType.formula)
    plan = kernel_plan()
    problem = {
        "document_id": "doc_1",
        "type": "short_answer",
        "difficulty": "hard",
        "bloom_level": "analyze",
        "question": "Compute the net amount when gross amount is 100 and discount is 20.",
        "choices": None,
        "answer": {"choice_id": None, "text": "80"},
        "explanation": "The source formula says Net amount = gross amount - discount, so 100 - 20 = 80.",
        "choice_explanations": None,
        "choice_diagnostics": None,
        "rubric": [
            {
                "criterion": "Uses Net amount = gross amount - discount.",
                "points": 1,
                "expected_evidence": ["Net amount", "gross amount", "discount"],
            }
        ],
        "concepts": ["net amount"],
        "source_chunk_ids": ["chunk_1"],
    }

    is_valid, _errors, report = ProblemQualityChecker().validate_with_quality_report(
        problem,
        retrieved_chunks=[RetrievedChunk(chunk_id="chunk_1", document_id="doc_1", content=atom.statement)],
        content_atoms=[atom],
        problem_kernel_plan=plan,
    )

    assert is_valid is True
    assert not [
        issue
        for issue in report.item_model_quality_issues
        if "kernel" in issue or "not linked" in issue
    ]


def test_evidence_obligation_evaluator_fails_when_citation_lacks_atom_evidence():
    atom = kernel_atom(ContentAtomType.rule)
    plan = ProblemKernelPlan(
        kernel_type=ProblemKernelType.apply_rule_to_case,
        content_atom_ids=[atom.atom_id],
        target_cognitive_level="apply",
        required_evidence_roles=[EvidenceObligation(role=EvidenceRole.rule, must_appear_in=["explanation"])],
    )
    problem = {
        "type": "short_answer",
        "question": "Apply the rule to the case.",
        "answer": {"choice_id": None, "text": "It applies."},
        "explanation": "This follows from the cited material.",
        "rubric": [{"criterion": "Apply the rule", "points": 1}],
        "source_chunk_ids": ["chunk_1"],
    }

    report = EvidenceObligationEvaluator().evaluate(
        problem_data=problem,
        content_atoms=[atom],
        problem_kernel_plan=plan,
        cited_chunks=[RetrievedChunk(chunk_id="chunk_1", document_id="doc_1", content=atom.statement)],
    )

    assert report.answer_supported is False
    assert report.explanation_supported is False
    assert "explanation does not connect to selected atom evidence" in report.issues


def test_evidence_obligation_evaluator_passes_formula_scenario_numbers_when_declared():
    atom = kernel_atom(ContentAtomType.formula)
    plan = kernel_plan()
    problem = {
        "type": "short_answer",
        "question": "Gross amount is 100 and discount is 20. Use Net amount = gross amount - discount.",
        "answer": {"choice_id": None, "text": "Net amount is 80."},
        "explanation": "Net amount = gross amount - discount, so 100 - 20 = 80.",
        "rubric": [
            {
                "criterion": "Uses Net amount = gross amount - discount.",
                "points": 1,
                "expected_evidence": ["Net amount", "gross amount", "discount"],
            }
        ],
        "source_chunk_ids": ["chunk_1"],
    }

    report = EvidenceObligationEvaluator().evaluate(
        problem_data=problem,
        content_atoms=[atom],
        problem_kernel_plan=plan,
        cited_chunks=[RetrievedChunk(chunk_id="chunk_1", document_id="doc_1", content=atom.statement)],
    )

    assert report.answer_supported is True
    assert report.explanation_supported is True
    assert report.source_formula_or_rule_cited is True
    assert report.generated_scenario_values_declared is True
    assert not report.issues


def test_evidence_obligation_evaluator_flags_compute_without_formula_citation():
    atom = kernel_atom(ContentAtomType.formula)
    plan = kernel_plan()
    problem = {
        "type": "short_answer",
        "question": "Gross amount is 100 and discount is 20.",
        "answer": {"choice_id": None, "text": "80"},
        "explanation": "100 - 20 = 80.",
        "rubric": [{"criterion": "Computes the result", "points": 1}],
        "source_chunk_ids": ["other_chunk"],
    }

    report = EvidenceObligationEvaluator().evaluate(
        problem_data=problem,
        content_atoms=[atom],
        problem_kernel_plan=plan,
        cited_chunks=[RetrievedChunk(chunk_id="other_chunk", document_id="doc_1", content="Unrelated.")],
    )

    assert report.source_formula_or_rule_cited is False
    assert "kernel evidence rule/formula/procedure is not cited" in report.issues


def test_evidence_obligation_evaluator_flags_generic_mcq_diagnostics():
    atom = kernel_atom(ContentAtomType.rule)
    plan = ProblemKernelPlan(
        kernel_type=ProblemKernelType.diagnose_error,
        content_atom_ids=[atom.atom_id],
        target_cognitive_level="analyze",
        required_evidence_roles=[EvidenceObligation(role=EvidenceRole.rule, must_appear_in=["explanation"])],
        requires_distinct_distractors=True,
    )
    problem = {
        "type": "multiple_choice",
        "question": "Which option violates Net amount = gross amount - discount?",
        "choices": [
            {"id": "A", "text": "Net amount subtracts discount."},
            {"id": "B", "text": "Discount is added."},
            {"id": "C", "text": "Gross is ignored."},
            {"id": "D", "text": "Net equals discount."},
        ],
        "answer": {"choice_id": "A", "text": "Net amount subtracts discount."},
        "explanation": "Net amount = gross amount - discount supports A.",
        "choice_explanations": {"A": "Correct.", "B": "Wrong.", "C": "Wrong.", "D": "Wrong."},
        "choice_diagnostics": [
            {"choice_id": "A", "is_correct": True, "mistake_type": "none"},
            {
                "choice_id": "B",
                "is_correct": False,
                "mistake_type": "logic_error",
                "misconception_id": "same",
                "why_plausible": "헷갈릴 수 있다",
                "repair_strategy": "다시 확인한다",
            },
            {
                "choice_id": "C",
                "is_correct": False,
                "mistake_type": "logic_error",
                "misconception_id": "same",
                "why_plausible": "헷갈릴 수 있다",
                "repair_strategy": "다시 확인한다",
            },
            {
                "choice_id": "D",
                "is_correct": False,
                "mistake_type": "logic_error",
                "misconception_id": "same",
                "why_plausible": "헷갈릴 수 있다",
                "repair_strategy": "다시 확인한다",
            },
        ],
        "source_chunk_ids": ["chunk_1"],
    }

    report = EvidenceObligationEvaluator().evaluate(
        problem_data=problem,
        content_atoms=[atom],
        problem_kernel_plan=plan,
        cited_chunks=[RetrievedChunk(chunk_id="chunk_1", document_id="doc_1", content=atom.statement)],
    )

    assert report.distractors_supported is False
    assert "MCQ distractor diagnostics do not name distinct evidence failures" in report.issues


def test_evidence_to_claim_without_source_link_fails():
    atom = ContentAtom(
        atom_id="atom_claim",
        atom_type=ContentAtomType.evidence_claim,
        source_chunk_id="chunk_1",
        statement="The image contrast supports the claim that hope remains.",
        evidence_quote="contrast supports the claim that hope remains",
        concepts=["contrast", "hope"],
        confidence=0.9,
    )
    plan = ProblemKernelPlan(
        kernel_type=ProblemKernelType.evidence_to_claim,
        content_atom_ids=[atom.atom_id],
        target_cognitive_level="analyze",
        required_evidence_roles=[EvidenceObligation(role=EvidenceRole.source_claim, must_appear_in=["explanation"])],
        requires_source_claim_alignment=True,
    )
    problem = {
        "type": "short_answer",
        "question": "Evaluate the claim.",
        "answer": {"choice_id": None, "text": "The claim is valid."},
        "explanation": "The answer is reasonable.",
        "rubric": [{"criterion": "Judges the claim", "points": 1}],
        "source_chunk_ids": ["chunk_1"],
    }

    report = EvidenceObligationEvaluator().evaluate(
        problem_data=problem,
        content_atoms=[atom],
        problem_kernel_plan=plan,
        cited_chunks=[RetrievedChunk(chunk_id="chunk_1", document_id="doc_1", content=atom.statement)],
    )

    assert report.explanation_supported is False
    assert any("evidence_to_claim" in issue for issue in report.issues)


def test_trace_process_with_ordered_procedure_evidence_passes():
    atom = ContentAtom(
        atom_id="atom_proc",
        atom_type=ContentAtomType.procedure,
        source_chunk_id="chunk_1",
        statement="Step 1 compare the middle value; Step 2 discard half of the range.",
        evidence_quote="compare the middle value; discard half",
        concepts=["binary search"],
        confidence=0.9,
    )
    plan = ProblemKernelPlan(
        kernel_type=ProblemKernelType.trace_process,
        content_atom_ids=[atom.atom_id],
        target_cognitive_level="analyze",
        required_evidence_roles=[EvidenceObligation(role=EvidenceRole.procedure_step, must_appear_in=["answer", "rubric"])],
    )
    problem = {
        "type": "short_answer",
        "question": "Trace binary search using Step 1 compare the middle value and Step 2 discard half.",
        "answer": {"choice_id": None, "text": "First compare the middle value, then discard half of the range."},
        "explanation": "The procedure says to compare the middle value before discarding half.",
        "rubric": [{"criterion": "Mentions compare the middle value and discard half", "points": 1}],
        "source_chunk_ids": ["chunk_1"],
    }

    report = EvidenceObligationEvaluator().evaluate(
        problem_data=problem,
        content_atoms=[atom],
        problem_kernel_plan=plan,
        cited_chunks=[RetrievedChunk(chunk_id="chunk_1", document_id="doc_1", content=atom.statement)],
    )

    assert report.answer_supported is True
    assert report.rubric_supported is True
    assert not report.issues


def test_short_answer_rubric_without_evidence_link_fails():
    atom = kernel_atom(ContentAtomType.rule)
    plan = ProblemKernelPlan(
        kernel_type=ProblemKernelType.apply_rule_to_case,
        content_atom_ids=[atom.atom_id],
        target_cognitive_level="apply",
        required_evidence_roles=[EvidenceObligation(role=EvidenceRole.rule, must_appear_in=["explanation", "rubric"])],
    )
    problem = {
        "type": "short_answer",
        "question": "Apply Net amount = gross amount - discount.",
        "answer": {"choice_id": None, "text": "It applies because of net amount."},
        "explanation": "Net amount = gross amount - discount applies.",
        "rubric": [{"criterion": "Clear writing", "points": 1}],
        "source_chunk_ids": ["chunk_1"],
    }

    report = EvidenceObligationEvaluator().evaluate(
        problem_data=problem,
        content_atoms=[atom],
        problem_kernel_plan=plan,
        cited_chunks=[RetrievedChunk(chunk_id="chunk_1", document_id="doc_1", content=atom.statement)],
    )

    assert report.rubric_supported is False
    assert "short_answer rubric is not tied to selected evidence roles" in report.issues


def test_diagnose_error_without_violated_rule_evidence_link_fails():
    atom = kernel_atom(ContentAtomType.rule)
    plan = ProblemKernelPlan(
        kernel_type=ProblemKernelType.diagnose_error,
        content_atom_ids=[atom.atom_id],
        target_cognitive_level="analyze",
        required_evidence_roles=[EvidenceObligation(role=EvidenceRole.rule, must_appear_in=["explanation"])],
    )
    problem = {
        "document_id": "doc_1",
        "type": "short_answer",
        "difficulty": "hard",
        "bloom_level": "analyze",
        "question": "A solution contains an error. Identify it.",
        "choices": None,
        "answer": {"choice_id": None, "text": "The step is wrong."},
        "explanation": "The cited rule is violated, but the rule itself is not described.",
        "choice_explanations": None,
        "choice_diagnostics": None,
        "rubric": [{"criterion": "Identify the error", "points": 1}],
        "concepts": ["net amount"],
        "source_chunk_ids": ["chunk_1"],
    }

    is_valid, _errors, report = ProblemQualityChecker().validate_with_quality_report(
        problem,
        retrieved_chunks=[RetrievedChunk(chunk_id="chunk_1", document_id="doc_1", content=atom.statement)],
        request=GenerateProblemRequest(
            document_id="doc_1",
            concepts=["net amount"],
            type="short_answer",
            count=1,
            quality_mode="strict",
            problem_style="error_detection",
        ),
        content_atoms=[atom],
        problem_kernel_plan=plan,
    )

    assert is_valid is False
    assert any("violated source rule" in issue or "not linked" in issue for issue in report.item_model_quality_issues)


def test_answer_verifier_allows_stem_given_values_and_flags_answer_only_numbers():
    atom = kernel_atom()
    plan = kernel_plan()
    chunks = [RetrievedChunk(chunk_id="chunk_1", document_id="doc_1", content="Net amount = gross amount - discount.")]
    verifier = ProblemAnswerVerifier(settings=Settings(PROBLEM_AGENT_ANSWER_VERIFICATION_ENABLED=True))
    good = {
        "document_id": "doc_1",
        "type": "short_answer",
        "question": "Gross amount is 100 and discount is 20. Compute the net amount.",
        "answer": {"choice_id": None, "text": "80"},
        "explanation": "Use the source formula: 100 - 20 = 80.",
        "rubric": [{"criterion": "Substitute 100 and 20", "points": 1}],
    }
    bad = {
        **good,
        "question": "Use the source formula to compute the net amount.",
        "answer": {"choice_id": None, "text": "999"},
        "explanation": "The net amount is 999.",
        "rubric": [{"criterion": "Use the formula", "points": 1}],
    }

    good_report = verifier.verify(problem=good, chunks=chunks, content_atoms=[atom], problem_kernel_plan=plan)
    bad_report = verifier.verify(problem=bad, chunks=chunks, content_atoms=[atom], problem_kernel_plan=plan)

    assert good_report.numeric_grounding["generated_scenario_number"] == ["20", "100"]
    assert good_report.numeric_grounding["suspicious_answer_number"] == []
    assert bad_report.recommended_action == "needs_review"
    assert bad_report.numeric_grounding["suspicious_answer_number"] == ["999"]
    assert any("suspicious_answer_number" in issue for issue in bad_report.issues)


def test_answer_verifier_normalizes_currency_percent_and_fraction_formats():
    verifier = ProblemAnswerVerifier(settings=Settings(PROBLEM_AGENT_ANSWER_VERIFICATION_ENABLED=True))
    atom = kernel_atom()
    plan = kernel_plan()
    chunks = [RetrievedChunk(chunk_id="chunk_1", document_id="doc_1", content=atom.statement)]
    problem = {
        "document_id": "doc_1",
        "type": "short_answer",
        "question": "Principal is ￦100,000, rate is 10%, and period is 3/12 year. Compute interest.",
        "answer": {"choice_id": None, "text": "2500"},
        "explanation": "Use 100000 * 0.1 * 0.25 = 2500.",
        "rubric": [{"criterion": "Substitute principal, rate, and period.", "points": 1}],
    }

    report = verifier.verify(problem=problem, chunks=chunks, content_atoms=[atom], problem_kernel_plan=plan)

    assert report.recommended_action == "pass"
    assert "100000" in report.numeric_grounding["question_given_number"]
    assert "0.1" in report.numeric_grounding["question_given_number"]
    assert "0.25" in report.numeric_grounding["question_given_number"]
    assert "2500" in report.numeric_grounding["derived_number"]


def test_answer_verifier_flags_source_fact_number_hallucination():
    verifier = ProblemAnswerVerifier(settings=Settings(PROBLEM_AGENT_ANSWER_VERIFICATION_ENABLED=True))
    problem = {
        "document_id": "doc_1",
        "type": "short_answer",
        "question": "What value does the source state?",
        "answer": {"choice_id": None, "text": "999"},
        "explanation": "The source says 999.",
        "rubric": [{"criterion": "Use the source value.", "points": 1}],
    }

    report = verifier.verify(
        problem=problem,
        chunks=[RetrievedChunk(chunk_id="chunk_1", document_id="doc_1", content="The source states 100.")],
    )

    assert report.recommended_action == "needs_review"
    assert report.numeric_grounding["ungrounded_source_fact_number"] == ["999"]


def test_feedback_agent_exposes_universal_mistake_taxonomy_mapping():
    agent = FeedbackAgent(settings=Settings(OPENAI_API_KEY=None))

    assert agent.infer_universal_mistake_type("계산 과정에서 대입을 잘못했다") == MistakeType.calculation_or_derivation_error
    assert agent.infer_universal_mistake_type("문헌 근거 없는 해석 주장") == MistakeType.evidence_mismatch
    assert agent.infer_universal_mistake_type("procedure step order is reversed") == MistakeType.procedure_order_error
