import pytest

from app.agents import ProblemQualityChecker
from app.models import Problem
from app.schemas.integration_contracts import RetrievedChunk
from app.schemas.problems import ItemModelId
from app.schemas.problems import GenerateProblemRequest
from app.services.problem_service import ProblemService
from app.services.professor_grade_item_service import ItemModelSelector, ProfessorGradeItemDesigner
from app.services.search_service import SearchAgentError


class FixedProblemAgent:
    def __init__(self, problems):
        self.problems = problems

    def generate(self, request, chunks, **kwargs):
        return self.problems


def build_service(db_session, fixed_search, problems):
    return ProblemService(
        db=db_session,
        search_service=fixed_search,
        problem_agent=FixedProblemAgent(problems),
        quality_checker=ProblemQualityChecker(),
    )


def test_rejects_multiple_choice_with_duplicate_choice_ids(db_session, fixed_search):
    problem = valid_multiple_choice_problem()
    problem["choices"][1]["id"] = "A"
    service = build_service(db_session, fixed_search, [problem])

    with pytest.raises(ValueError, match="Only 0 valid problems were generated"):
        service.generate_problems(user_id="user_001", request=generate_request("multiple_choice"))

    assert db_session.query(Problem).count() == 0


def test_rejects_multiple_choice_with_empty_choice_text(db_session, fixed_search):
    problem = valid_multiple_choice_problem()
    problem["choices"][2]["text"] = "   "
    service = build_service(db_session, fixed_search, [problem])

    with pytest.raises(ValueError, match="Only 0 valid problems were generated"):
        service.generate_problems(user_id="user_001", request=generate_request("multiple_choice"))

    assert db_session.query(Problem).count() == 0


def test_rejects_short_answer_with_invalid_rubric_points(db_session, fixed_search):
    problem = valid_short_answer_problem()
    problem["rubric"][0]["points"] = 0
    service = build_service(db_session, fixed_search, [problem])

    with pytest.raises(ValueError, match="Only 0 valid problems were generated"):
        service.generate_problems(user_id="user_001", request=generate_request("short_answer"))

    assert db_session.query(Problem).count() == 0


def test_rejects_problem_type_shape_mismatch(db_session, fixed_search):
    multiple_choice = valid_multiple_choice_problem()
    multiple_choice["rubric"] = [{"criterion": "객관식에는 rubric을 쓰지 않는다.", "points": 1}]
    short_answer = valid_short_answer_problem()
    short_answer["choices"] = [{"id": "A", "text": "주관식에는 보기를 쓰지 않는다."}]
    service = build_service(db_session, fixed_search, [multiple_choice, short_answer])

    with pytest.raises(ValueError, match="Only 0 valid problems were generated"):
        service.generate_problems(
            user_id="user_001",
            request=GenerateProblemRequest(
                document_id="doc_001",
                concepts=["뉴턴 제2법칙"],
                type="multiple_choice",
                count=2,
                difficulty="medium",
                bloom_level="understand",
            ),
        )

    assert db_session.query(Problem).count() == 0


def test_rejects_problem_when_source_chunk_was_not_retrieved(db_session, fixed_search):
    problem = valid_multiple_choice_problem()
    problem["source_chunk_ids"] = ["missing_chunk"]
    service = build_service(db_session, fixed_search, [problem])

    with pytest.raises(ValueError, match="Only 0 valid problems were generated"):
        service.generate_problems(user_id="user_001", request=generate_request("multiple_choice"))

    assert db_session.query(Problem).count() == 0


def test_rejects_duplicate_source_chunk_ids(db_session, fixed_search):
    problem = valid_multiple_choice_problem()
    problem["source_chunk_ids"] = ["chunk_001", "chunk_001"]
    service = build_service(db_session, fixed_search, [problem])

    with pytest.raises(ValueError, match="source_chunk_ids must be unique"):
        service.generate_problems(user_id="user_001", request=generate_request("multiple_choice"))

    assert db_session.query(Problem).count() == 0


def test_rejects_duplicate_choice_texts(db_session, fixed_search):
    problem = valid_multiple_choice_problem()
    problem["choices"][1]["text"] = problem["choices"][0]["text"]
    service = build_service(db_session, fixed_search, [problem])

    with pytest.raises(ValueError, match="choice texts must be unique"):
        service.generate_problems(user_id="user_001", request=generate_request("multiple_choice"))

    assert db_session.query(Problem).count() == 0


def test_rejects_answer_text_that_does_not_match_choice(db_session, fixed_search):
    problem = valid_multiple_choice_problem()
    problem["answer"]["text"] = "정답 ID와 다른 텍스트"
    service = build_service(db_session, fixed_search, [problem])

    with pytest.raises(ValueError, match="answer.text must match the selected choice text"):
        service.generate_problems(user_id="user_001", request=generate_request("multiple_choice"))

    assert db_session.query(Problem).count() == 0


def test_rejects_empty_concepts(db_session, fixed_search):
    problem = valid_multiple_choice_problem()
    problem["concepts"] = ["뉴턴 제2법칙", " "]
    service = build_service(db_session, fixed_search, [problem])

    with pytest.raises(ValueError, match="concepts must not include empty values"):
        service.generate_problems(user_id="user_001", request=generate_request("multiple_choice"))

    assert db_session.query(Problem).count() == 0


def test_rejects_unknown_choice_explanation_id(db_session, fixed_search):
    problem = valid_multiple_choice_problem()
    problem["choice_explanations"]["Z"] = "없는 보기의 해설이다."
    service = build_service(db_session, fixed_search, [problem])

    with pytest.raises(ValueError, match="unknown choice ids"):
        service.generate_problems(user_id="user_001", request=generate_request("multiple_choice"))

    assert db_session.query(Problem).count() == 0


def test_rejects_invalid_choice_diagnostic_mapping(db_session, fixed_search):
    problem = valid_multiple_choice_problem()
    problem["choice_diagnostics"] = [
        {
            "choice_id": "A",
            "is_correct": False,
            "misconception_id": "mis_wrong_a",
            "mistake_type": "concept_misunderstanding",
            "why_plausible": "정답 보기를 오답처럼 진단했다.",
            "repair_strategy": "정답 기준을 다시 확인한다.",
            "followup_problem_type": "misconception_contrast",
        },
        {
            "choice_id": "B",
            "is_correct": True,
            "misconception_id": None,
            "mistake_type": "none",
            "why_plausible": None,
            "repair_strategy": None,
            "followup_problem_type": None,
        },
        {
            "choice_id": "C",
            "is_correct": False,
            "misconception_id": "mis_c",
            "mistake_type": "concept_misunderstanding",
            "why_plausible": "가속도를 항상 0으로 보면 고를 수 있다.",
            "repair_strategy": "힘과 가속도의 관계를 다시 비교한다.",
            "followup_problem_type": "misconception_contrast",
        },
        {
            "choice_id": "D",
            "is_correct": False,
            "misconception_id": "mis_d",
            "mistake_type": "concept_misunderstanding",
            "why_plausible": "질량과 가속도의 관계를 반대로 보면 고를 수 있다.",
            "repair_strategy": "같은 힘 조건에서 질량 변화를 비교한다.",
            "followup_problem_type": "misconception_contrast",
        },
    ]
    service = build_service(db_session, fixed_search, [problem])

    with pytest.raises(ValueError, match="answer choice as correct"):
        service.generate_problems(user_id="user_001", request=generate_request("multiple_choice"))

    assert db_session.query(Problem).count() == 0


def test_saves_valid_problem_after_quality_checks(db_session, fixed_search):
    service = build_service(db_session, fixed_search, [valid_multiple_choice_problem()])

    problems = service.generate_problems(user_id="user_001", request=generate_request("multiple_choice"))

    assert len(problems) == 1
    assert problems[0].source_chunk_ids == ["chunk_001"]
    assert {item["choice_id"] for item in problems[0].choice_diagnostics} == {"A", "B", "C", "D"}
    assert [item["choice_id"] for item in problems[0].choice_diagnostics if item["is_correct"]] == ["A"]
    assert all(item["repair_strategy"] for item in problems[0].choice_diagnostics if not item["is_correct"])
    assert db_session.query(Problem).count() == 1


def test_generation_stores_professor_grade_item_metadata(db_session, fixed_search):
    service = build_service(db_session, fixed_search, [valid_multiple_choice_problem()])

    problems = service.generate_problems(user_id="user_001", request=generate_request("multiple_choice"))

    problem = problems[0]
    assert problem.item_model_id is not None
    assert problem.source_refs == [
        {"document_id": "doc_001", "chunk_id": "chunk_001", "page": 12, "section_title": "뉴턴의 운동 법칙"}
    ]
    assert problem.item_design_brief["target_concept"] == "뉴턴 제2법칙"
    assert problem.item_design_brief["observable_evidence"]
    assert problem.difficulty_profile["cognitive_demand_score"] > 0
    assert problem.teacher_review_checklist["decision"] == "approved"
    assert problem.professor_grade_score["final_score"] > 0


def test_generation_stores_student_response_simulation(db_session, fixed_search):
    service = build_service(db_session, fixed_search, [valid_multiple_choice_problem()])

    problems = service.generate_problems(user_id="user_001", request=generate_request("multiple_choice"))

    simulation = problems[0].student_response_simulation
    assert simulation["passed"] is True
    cases = {case["kind"]: case for case in simulation["cases"]}
    assert set(cases) == {"full_correct", "partial_correct", "misconception", "condition_missing"}
    assert cases["full_correct"]["observed_score_ratio"] == 1
    assert cases["misconception"]["observed_score_ratio"] == 0


def test_student_response_simulation_rejects_weak_constructed_response_rubric(db_session, fixed_search):
    problem = valid_short_answer_problem()
    problem["question"] = "뉴턴 제2법칙을 적용해 같은 힘 조건에서 질량 차이가 가속도에 미치는 영향을 근거와 함께 비교하시오."
    problem["bloom_level"] = "apply"
    problem["rubric"] = [
        {"criterion": f"근거 기준 {index}", "points": 1, "expected_evidence": ["자료 근거"]}
        for index in range(10)
    ]
    service = build_service(db_session, fixed_search, [problem])

    with pytest.raises(ValueError, match="student_simulation_condition_missing_scores_too_high"):
        service.generate_problems(
            user_id="user_001",
            request=GenerateProblemRequest(
                document_id="doc_001",
                concepts=["뉴턴 제2법칙"],
                type="short_answer",
                count=1,
                difficulty="medium",
                bloom_level="apply",
            ),
        )

    assert db_session.query(Problem).count() == 0


def test_student_response_simulation_confirms_full_correct_and_misconception_scores(fixed_search):
    result = ProfessorGradeItemDesigner().enrich(
        problem_data=valid_short_answer_problem(),
        request=generate_request("short_answer"),
        chunks=fixed_search.chunks,
    )

    cases = {case["kind"]: case for case in result.problem_data["student_response_simulation"]["cases"]}
    assert cases["full_correct"]["observed_score_ratio"] >= 0.8
    assert cases["full_correct"]["matched_rubric_indices"]
    assert cases["misconception"]["observed_score_ratio"] < 0.5
    assert cases["misconception"]["unmatched_rubric_indices"]


def test_short_answer_full_correct_simulation_uses_answer_plus_explanation():
    problem = evidence_based_short_answer_problem()
    problem["answer"]["text"] = "결론은 자료의 관계를 적용해 판단한다."
    problem["explanation"] = (
        "자료의 핵심 관계는 F = ma이며 힘, 질량, 가속도가 함께 연결된다. "
        "같은 힘 조건에서는 질량이 클수록 가속도는 작아진다."
    )

    simulation = ProfessorGradeItemDesigner()._student_response_simulation(problem_data=problem)
    cases = {case.kind.value: case for case in simulation.cases}

    assert cases["full_correct"].observed_score_ratio >= 0.8
    assert cases["full_correct"].unmatched_rubric_indices == []


def test_short_answer_full_correct_simulation_still_fails_when_explanation_misses_evidence():
    problem = evidence_based_short_answer_problem()
    problem["answer"]["text"] = "힘은 어떤 물리량과 관련된다."
    problem["explanation"] = "자료를 참고해 결론을 쓰면 된다."

    simulation = ProfessorGradeItemDesigner()._student_response_simulation(problem_data=problem)

    assert "student_simulation_full_correct_scores_too_low" in simulation.flags


def test_student_response_simulation_matches_structured_evidence_with_wording_variation(fixed_search):
    problem = heapsort_trace_short_answer_problem()

    result = ProfessorGradeItemDesigner().enrich(
        problem_data=problem,
        request=GenerateProblemRequest(
            document_id="doc_001",
            concepts=["heapsort", "max heap"],
            type="short_answer",
            count=1,
            difficulty="hard",
            bloom_level="apply",
        ),
        chunks=fixed_search.chunks,
    )

    simulation = result.problem_data["student_response_simulation"]
    cases = {case["kind"]: case for case in simulation["cases"]}
    assert simulation["passed"] is True
    assert cases["full_correct"]["observed_score_ratio"] >= 0.8
    assert cases["full_correct"]["unmatched_rubric_indices"] == []


def test_student_response_simulation_rejects_condition_missing_when_rubric_not_discriminative():
    problem = evidence_based_short_answer_problem()
    problem["rubric"] = [
        {
            "criterion": f"자료 근거 기준 {index}",
            "points": 1,
            "expected_evidence": ["자료 근거"],
            "common_mistakes": ["자료 근거를 쓰지 않음"],
            "partial_credit_rules": ["자료 근거 일부를 쓰면 부분점수"],
        }
        for index in range(3)
    ]

    simulation = ProfessorGradeItemDesigner()._student_response_simulation(problem_data=problem)

    assert "student_simulation_condition_missing_scores_too_high" in simulation.flags


def test_student_response_simulation_rejects_model_answer_missing_rubric_evidence(db_session, fixed_search):
    problem = evidence_based_short_answer_problem()
    problem["answer"]["text"] = "힘은 어떤 물리량과 관련된다."
    service = build_service(db_session, fixed_search, [problem])

    with pytest.raises(ValueError, match="student_simulation_full_correct_scores_too_low"):
        service.generate_problems(
            user_id="user_001",
            request=GenerateProblemRequest(
                document_id="doc_001",
                concepts=["뉴턴 제2법칙"],
                type="short_answer",
                count=1,
                difficulty="medium",
                bloom_level="apply",
            ),
        )

    assert db_session.query(Problem).count() == 0


def test_student_response_simulation_rejects_misconception_that_scores_like_correct_answer(db_session, fixed_search):
    problem = evidence_based_short_answer_problem()
    problem["rubric"][0]["common_mistakes"] = [
        "F = ma, 같은 힘, 질량이 클수록, 가속도는 작아진다라고만 외우고 조건의 방향을 착각함"
    ]
    service = build_service(db_session, fixed_search, [problem])

    with pytest.raises(ValueError, match="student_simulation_misconception_scores_too_high"):
        service.generate_problems(
            user_id="user_001",
            request=GenerateProblemRequest(
                document_id="doc_001",
                concepts=["뉴턴 제2법칙"],
                type="short_answer",
                count=1,
                difficulty="medium",
                bloom_level="apply",
            ),
        )

    assert db_session.query(Problem).count() == 0


def test_rejects_hard_pure_recall_item(db_session, fixed_search):
    problem = valid_multiple_choice_problem()
    problem["difficulty"] = "hard"
    problem["bloom_level"] = "remember"
    service = build_service(db_session, fixed_search, [problem])

    with pytest.raises(ValueError, match="hard item must require application"):
        service.generate_problems(
            user_id="user_001",
            request=GenerateProblemRequest(
                document_id="doc_001",
                concepts=["뉴턴 제2법칙"],
                type="multiple_choice",
                count=1,
                difficulty="hard",
                bloom_level="remember",
            ),
        )

    assert db_session.query(Problem).count() == 0


def test_rejects_vague_high_rigor_short_answer_prompt(db_session, fixed_search):
    problem = valid_short_answer_problem()
    problem["difficulty"] = "hard"
    problem["bloom_level"] = "analyze"
    service = build_service(db_session, fixed_search, [problem])

    with pytest.raises(ValueError, match="constructed-response prompt"):
        service.generate_problems(
            user_id="user_001",
            request=GenerateProblemRequest(
                document_id="doc_001",
                concepts=["뉴턴 제2법칙"],
                type="short_answer",
                count=1,
                difficulty="hard",
                bloom_level="analyze",
            ),
        )

    assert db_session.query(Problem).count() == 0


def test_professor_grade_gate_rejects_mcq_without_diagnostics(fixed_search):
    problem = valid_multiple_choice_problem()

    result = ProfessorGradeItemDesigner().enrich(
        problem_data=problem,
        request=generate_request("multiple_choice"),
        chunks=fixed_search.chunks,
    )

    assert "distractors must be plausible" in result.rejection_errors
    assert "distractors must include diagnostic feedback" in result.rejection_errors


def test_rejects_partial_problem_generation_without_saving(db_session, fixed_search):
    invalid_problem = valid_multiple_choice_problem()
    invalid_problem["choices"][0]["text"] = ""
    service = build_service(db_session, fixed_search, [valid_multiple_choice_problem(), invalid_problem])

    with pytest.raises(ValueError, match="Only 1 valid problems were generated out of 2"):
        service.generate_problems(
            user_id="user_001",
            request=GenerateProblemRequest(
                document_id="doc_001",
                concepts=["뉴턴 제2법칙"],
                type="multiple_choice",
                count=2,
                difficulty="medium",
                bloom_level="understand",
            ),
        )

    assert db_session.query(Problem).count() == 0


def test_rejects_duplicate_generated_problem_candidates_without_saving(db_session, fixed_search):
    problem = valid_multiple_choice_problem()
    service = build_service(db_session, fixed_search, [problem, problem.copy()])

    with pytest.raises(ValueError, match="duplicate generated problem"):
        service.generate_problems(
            user_id="user_001",
            request=GenerateProblemRequest(
                document_id="doc_001",
                concepts=["뉴턴 제2법칙"],
                type="multiple_choice",
                count=2,
                difficulty="medium",
                bloom_level="understand",
            ),
        )

    assert db_session.query(Problem).count() == 0


def test_rejects_source_chunk_from_different_document(db_session, fixed_search):
    problem = valid_multiple_choice_problem()
    problem["document_id"] = "other_doc"
    service = build_service(db_session, fixed_search, [problem])

    with pytest.raises(SearchAgentError, match="different document"):
        service.generate_problems(user_id="user_001", request=generate_request("multiple_choice", document_id="other_doc"))

    assert db_session.query(Problem).count() == 0


def test_rejects_generated_problem_that_does_not_match_request(db_session, fixed_search):
    problem = valid_multiple_choice_problem()
    problem["type"] = "short_answer"
    service = build_service(db_session, fixed_search, [problem])

    with pytest.raises(ValueError, match="type does not match request"):
        service.generate_problems(user_id="user_001", request=generate_request("multiple_choice"))

    assert db_session.query(Problem).count() == 0


def test_item_model_selector_does_not_use_source_error_words_for_error_detection():
    problem = evidence_based_short_answer_problem()
    problem["question"] = "주어진 조건에서 뉴턴 제2법칙을 적용해 가속도의 변화를 분석하시오."
    chunks = [
        RetrievedChunk(
            chunk_id="chunk_error_word",
            document_id="doc_001",
            content="학생은 질량과 가속도의 관계를 잘못 이해할 수 있다.",
            page=1,
            section_title="오개념",
            concepts=["뉴턴 제2법칙"],
        )
    ]

    item_model_id = ItemModelSelector().select(
        request=GenerateProblemRequest(
            document_id="doc_001",
            concepts=["뉴턴 제2법칙"],
            type="short_answer",
            count=1,
            difficulty="hard",
            bloom_level="apply",
        ),
        problem_data=problem,
        chunks=chunks,
    )

    assert item_model_id != ItemModelId.error_detection


def generate_request(problem_type, *, document_id="doc_001"):
    return GenerateProblemRequest(
        document_id=document_id,
        concepts=["뉴턴 제2법칙"],
        type=problem_type,
        count=1,
        difficulty="medium",
        bloom_level="understand",
    )


def valid_multiple_choice_problem():
    return {
        "document_id": "doc_001",
        "type": "multiple_choice",
        "difficulty": "medium",
        "bloom_level": "understand",
        "question": "뉴턴의 제2법칙에 대한 설명으로 가장 적절한 것은?",
        "choices": [
            {"id": "A", "text": "힘은 질량과 가속도의 곱이다."},
            {"id": "B", "text": "힘은 질량과 무관하다."},
            {"id": "C", "text": "가속도는 항상 0이다."},
            {"id": "D", "text": "질량이 클수록 같은 힘에서 가속도는 커진다."},
        ],
        "answer": {"choice_id": "A", "text": "힘은 질량과 가속도의 곱이다."},
        "explanation": "자료에는 뉴턴의 제2법칙이 F = ma라고 설명되어 있다.",
        "choice_explanations": {
            "A": "자료 내용과 일치한다.",
            "B": "자료에서는 힘이 질량과 가속도와 관련된다고 설명한다.",
            "C": "자료에 없는 설명이다.",
            "D": "같은 힘에서는 질량이 클수록 가속도가 작아진다.",
        },
        "rubric": None,
        "concepts": ["뉴턴 제2법칙"],
        "source_chunk_ids": ["chunk_001"],
        "mcq_plan": {
            "kernel_type": "compute_from_given",
            "source_rule_or_evidence": "F = ma connects force, mass, and acceleration.",
            "concrete_scenario": "같은 힘 조건에서 질량과 가속도의 관계를 판단하는 사례",
            "correct_answer_claim": "힘은 질량과 가속도의 곱이다.",
            "correct_answer_evidence_link": "F = ma",
            "distractor_plans": [
                {
                    "misconception_id": "mass_irrelevant",
                    "mistake_type": "missing_key_concept",
                    "why_plausible": "질량 변수를 식에서 누락하면 그럴듯하다.",
                    "violated_or_ignored_evidence_role": "formula",
                    "repair_strategy": "F = ma에서 질량과 가속도가 모두 포함되는지 확인한다.",
                },
                {
                    "misconception_id": "zero_acceleration_assumption",
                    "mistake_type": "concept_misunderstanding",
                    "why_plausible": "힘이 작용해도 가속도가 없다고 오해할 수 있다.",
                    "violated_or_ignored_evidence_role": "rule",
                    "repair_strategy": "힘과 가속도가 연결되는 조건을 식으로 다시 비교한다.",
                },
                {
                    "misconception_id": "reversed_mass_acceleration",
                    "mistake_type": "logic_error",
                    "why_plausible": "질량 증가와 가속도 변화를 반대로 연결하면 그럴듯하다.",
                    "violated_or_ignored_evidence_role": "condition",
                    "repair_strategy": "같은 힘 조건에서 질량과 가속도의 방향을 따로 표시한다.",
                },
            ],
            "prohibited_patterns": ["definition-only", "generic diagnostics"],
            "required_source_chunk_ids": ["chunk_001"],
        },
    }


def valid_short_answer_problem():
    return {
        "document_id": "doc_001",
        "type": "short_answer",
        "difficulty": "medium",
        "bloom_level": "understand",
        "question": "뉴턴의 제2법칙을 설명해줘.",
        "choices": None,
        "answer": {"choice_id": None, "text": "뉴턴의 제2법칙은 힘이 질량과 가속도의 곱이라는 법칙이다."},
        "explanation": "자료에는 뉴턴의 제2법칙이 F = ma라고 설명되어 있다.",
        "choice_explanations": None,
        "rubric": [{"criterion": "F = ma의 의미를 설명한다.", "points": 2}],
        "concepts": ["뉴턴 제2법칙"],
        "source_chunk_ids": ["chunk_001"],
    }


def evidence_based_short_answer_problem():
    return {
        "document_id": "doc_001",
        "type": "short_answer",
        "difficulty": "medium",
        "bloom_level": "apply",
        "question": "뉴턴 제2법칙을 적용해 같은 힘 조건에서 질량 차이가 가속도에 미치는 영향을 설명하시오.",
        "choices": None,
        "answer": {
            "choice_id": None,
            "text": "뉴턴 제2법칙은 F = ma이고, 같은 힘에서는 질량이 클수록 가속도는 작아진다.",
        },
        "explanation": "같은 힘 조건에서는 질량과 가속도의 관계를 반대로 해석하지 않아야 한다.",
        "choice_explanations": None,
        "rubric": [
            {
                "criterion": "F = ma의 변수 관계를 설명한다.",
                "points": 2,
                "expected_evidence": ["F = ma", "힘", "질량", "가속도"],
                "common_mistakes": ["공식만 쓰고 질량과 가속도의 관계를 빠뜨림"],
                "partial_credit_rules": ["공식을 쓰면 1점"],
            },
            {
                "criterion": "같은 힘 조건에서 질량이 클수록 가속도는 작아진다고 설명한다.",
                "points": 2,
                "expected_evidence": ["같은 힘", "질량이 클수록", "가속도는 작아진다"],
                "common_mistakes": ["질량이 클수록 가속도가 커진다고 반대로 설명함"],
                "partial_credit_rules": ["관계 방향만 맞으면 1점"],
            },
        ],
        "concepts": ["뉴턴 제2법칙"],
        "source_chunk_ids": ["chunk_001"],
    }


def heapsort_trace_short_answer_problem():
    return {
        "document_id": "doc_001",
        "type": "short_answer",
        "difficulty": "hard",
        "bloom_level": "apply",
        "question": (
            "1-indexed 배열 A=[4,1,3,2,16,9,10,14,8,7]에 대해 Build-Max-Heap의 "
            "i=4,3,2,1 단계와 Heap-Extract-Max 1회를 추적하고, heap property 복구 방식을 설명하시오."
        ),
        "choices": None,
        "answer": {
            "choice_id": None,
            "text": (
                "Build-Max-Heap 결과는 i=4: [4,1,3,14,16,9,10,2,8,7], "
                "i=3: [4,1,10,14,16,9,3,2,8,7], "
                "i=2: [4,16,10,14,7,9,3,2,8,1], "
                "i=1: [16,14,10,8,7,9,3,2,4,1]이다. "
                "Heap-Extract-Max는 16을 제거하고 heap-size를 9로 줄인 뒤 "
                "[14,8,10,4,7,9,3,2,1,16]을 만든다. "
                "Max-Heapify는 루트에서 더 큰 자식 방향으로 내려가는 한 경로를 고치며, "
                "전체 배열을 다시 힙으로 만들지 않으므로 추출은 O(log n)이다."
            ),
        },
        "explanation": "각 단계는 Max-Heapify의 하향 교환으로 부모가 자식보다 크거나 같도록 회복한다.",
        "choice_explanations": None,
        "rubric": [
            {
                "criterion": "Build-Max-Heap 중간 상태를 정확히 추적한다.",
                "points": 4,
                "expected_evidence": [
                    "i=4 후 [4,1,3,14,16,9,10,2,8,7]을 제시한다.",
                    "i=3 후 [4,1,10,14,16,9,3,2,8,7]을 제시한다.",
                    "i=2 후 [4,16,10,14,7,9,3,2,8,1]을 제시한다.",
                    "i=1 후 [16,14,10,8,7,9,3,2,4,1]을 제시한다.",
                ],
                "common_mistakes": ["Build-Max-Heap을 삽입식 heap 만들기처럼 처리함"],
                "partial_credit_rules": ["중간 배열 하나당 1점"],
            },
            {
                "criterion": "Heap-Extract-Max 1회의 결과를 설명한다.",
                "points": 3,
                "expected_evidence": [
                    "제거된 최댓값 16을 밝힌다.",
                    "추출 후 배열 [14,8,10,4,7,9,3,2,1,16]을 제시한다.",
                    "heap-size가 9로 줄어든다고 설명한다.",
                ],
                "common_mistakes": ["마지막 원소 1을 루트로 옮긴 뒤 Max-Heapify하지 않음"],
                "partial_credit_rules": ["제거값, 배열, heap-size를 각각 부분점수로 인정"],
            },
            {
                "criterion": "heap property 복구와 시간복잡도를 연결해 설명한다.",
                "points": 3,
                "expected_evidence": [
                    "루트와 마지막 원소를 교환한 뒤 heap-size를 줄인다.",
                    "Max-Heapify는 루트에서 하향 경로를 따라 heap property를 회복한다.",
                    "Extract-Max는 전체 배열을 다시 힙으로 만들지 않으므로 O(log n)이다.",
                ],
                "common_mistakes": ["Extract-Max마다 Build-Max-Heap을 다시 수행한다고 설명함"],
                "partial_credit_rules": ["복구 경로와 시간복잡도 중 하나만 맞으면 부분점수"],
            },
        ],
        "concepts": ["heapsort", "max heap"],
        "source_chunk_ids": ["chunk_001"],
    }
