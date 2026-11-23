import pytest

from app.schemas.integration_contracts import RetrievedChunk
from app.schemas.problem_kernels import ContentAtom, ContentAtomType
from app.schemas.problems import GenerateProblemRequest
from app.services.problem_answer_verifier import ProblemAnswerVerifier
from app.services.problem_kernel_planner import ProblemKernelPlanner


def _compute_plan(formula: str, *, variables: list[str] | None = None):
    request = GenerateProblemRequest(
        document_id="doc_formula",
        concepts=["formula"],
        type="short_answer",
        count=1,
        problem_style="calculation_practice",
        difficulty="hard",
        bloom_level="analyze",
        target_rigor="high",
        quality_mode="strict",
    )
    atom = ContentAtom(
        atom_id="atom_formula",
        atom_type=ContentAtomType.formula,
        source_chunk_id="formula_chunk",
        statement=formula,
        evidence_quote=formula,
        concepts=["formula"],
        variables=variables or [],
        confidence=0.95,
    )
    chunk = RetrievedChunk(
        chunk_id="formula_chunk",
        document_id="doc_formula",
        content=formula,
        page=1,
        section_title="Formula",
        concepts=["formula"],
    )
    plan = ProblemKernelPlanner().plan(request=request, content_atoms=[atom])
    return request, atom, chunk, plan


@pytest.mark.parametrize(
    "formula",
    [
        "C_eq = C1 + C2",
        "profit = revenue - cost",
        "net_sales = gross_sales - returns",
    ],
)
def test_generated_stem_values_are_allowed_across_formula_styles(formula):
    request, atom, chunk, plan = _compute_plan(formula, variables=["x", "y"])
    given_values = plan.computation_scenario.generated_given_values
    left = given_values[0].value
    right = given_values[1].value
    result = f"{float(left) + float(right):g}"
    problem = {
        "document_id": "doc_formula",
        "type": "short_answer",
        "question": f"x = {left}, y = {right}일 때 source formula를 적용해 결과를 구하시오.",
        "answer": {"choice_id": None, "text": f"결과는 {result}이다."},
        "explanation": (
            f"자료의 공식 {formula}를 사용한다. x = {left}와 y = {right}을 대입하면 "
            f"{left} + {right} = {result}이다."
        ),
        "rubric": [
            {"criterion": "공식 사용", "points": 1, "expected_evidence": [formula]},
            {"criterion": "대입 계산", "points": 1, "expected_evidence": [f"{left} + {right} = {result}"]},
        ],
        "source_chunk_ids": ["formula_chunk"],
    }

    report = ProblemAnswerVerifier().verify(
        problem=problem,
        request=request,
        chunks=[chunk],
        content_atoms=[atom],
        problem_kernel_plan=plan,
    )

    assert left in report.numeric_grounding["generated_scenario_number"]
    assert right in report.numeric_grounding["generated_scenario_number"]
    assert not any("unsupported" in issue for issue in report.issues)
    assert not any("number_not_given_in_stem" in issue for issue in report.issues)


def test_answer_only_number_is_classified_as_not_derivable_from_given_conditions():
    request, atom, chunk, plan = _compute_plan("C_eq = C1 + C2", variables=["C1", "C2"])
    problem = {
        "document_id": "doc_formula",
        "type": "short_answer",
        "question": "C1 = 2 uF, C2 = 3 uF일 때 C_eq를 구하시오.",
        "answer": {"choice_id": None, "text": "C_eq = 999 uF이다."},
        "explanation": "자료의 공식 C_eq = C1 + C2를 적용한다.",
        "rubric": [{"criterion": "공식 사용", "points": 1, "expected_evidence": ["C_eq = C1 + C2"]}],
        "source_chunk_ids": ["formula_chunk"],
    }

    report = ProblemAnswerVerifier().verify(
        problem=problem,
        request=request,
        chunks=[chunk],
        content_atoms=[atom],
        problem_kernel_plan=plan,
    )

    assert "999" in report.numeric_grounding["number_not_derivable_from_given_conditions"]
    assert any("number_not_derivable_from_given_conditions" in issue for issue in report.issues)


def test_computation_scenario_value_missing_from_stem_is_classified_precisely():
    request, atom, chunk, plan = _compute_plan("C_eq = C1 + C2", variables=["C1", "C2"])
    problem = {
        "document_id": "doc_formula",
        "type": "short_answer",
        "question": "C1 = 2 uF일 때 C_eq를 구하시오.",
        "answer": {"choice_id": None, "text": "C_eq = 5 uF이다."},
        "explanation": "자료의 공식 C_eq = C1 + C2를 적용한다. C1 = 2, C2 = 3이므로 2 + 3 = 5이다.",
        "rubric": [{"criterion": "공식 사용", "points": 1, "expected_evidence": ["C_eq = C1 + C2"]}],
        "source_chunk_ids": ["formula_chunk"],
    }

    report = ProblemAnswerVerifier().verify(
        problem=problem,
        request=request,
        chunks=[chunk],
        content_atoms=[atom],
        problem_kernel_plan=plan,
    )

    assert "3" in report.numeric_grounding["number_not_given_in_stem"]
    assert any("number_not_given_in_stem" in issue for issue in report.issues)
