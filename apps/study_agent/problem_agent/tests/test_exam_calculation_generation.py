import pytest

from app.agents import ProblemAgent, ProblemQualityChecker
from app.config import Settings
from app.models import Problem
from app.schemas.integration_contracts import RetrievedChunk
from app.schemas.problems import GenerateProblemRequest
from app.schemas.quality import QualityFlag, QualityMode, QualityStatus
from app.services.assessment_blueprint_service import AssessmentBlueprintPlanner
from app.services.learning_task_strategy_router import LearningTaskStrategyRouter
from app.services.material_readiness_service import MaterialReadinessAnalyzer
from app.services.problem_service import ProblemService


class FixedProblemAgent:
    def __init__(self, problems):
        self.problems = problems

    def generate(self, request, chunks, **kwargs):
        return self.problems


def test_high_rigor_exam_request_generates_formula_calculation_short_answer(db_session, fixed_search):
    service = ProblemService(
        db=db_session,
        search_service=fixed_search,
        problem_agent=ProblemAgent(settings=Settings(OPENAI_API_KEY=None, LLM_FALLBACK_ENABLED=True)),
        quality_checker=ProblemQualityChecker(),
    )

    result = service.generate_problem_batch(
        user_id="user_001",
        request=calculation_request(),
    )

    assert result.quality_summary.passed == 1
    problem = result.problems[0]
    assert "$F = ma$" in problem.answer["text"]
    assert "$a = F / m$" in problem.answer["text"]
    assert "$12 N$" in problem.question
    assert "$3 kg$" in problem.question
    assert len(problem.rubric) >= 3
    assert problem.source_chunk_ids == ["chunk_001"]


def test_exam_prep_user_requirements_promote_high_rigor_strict_generation(db_session, fixed_search):
    service = ProblemService(
        db=db_session,
        search_service=fixed_search,
        problem_agent=ProblemAgent(settings=Settings(OPENAI_API_KEY=None, LLM_FALLBACK_ENABLED=True)),
        quality_checker=ProblemQualityChecker(),
    )

    result = service.generate_problem_batch(
        user_id="user_001",
        request=GenerateProblemRequest(
            document_id="doc_001",
            concepts=["뉴턴 제2법칙"],
            type="short_answer",
            count=1,
            user_requirements="대학 시험 대비용 고난도 수식 계산 문제를 만들어줘.",
        ),
    )

    assert result.blueprint.goal == "exam_prep"
    assert result.blueprint.course_level == "university"
    assert result.blueprint.target_rigor == "high"
    problem = result.problems[0]
    assert problem.difficulty == "hard"
    assert problem.bloom_level == "analyze"
    assert "12 / 3 = 4" in problem.answer["text"]


def test_ui_problem_style_promotes_calculation_practice_without_free_text_prompt(db_session, fixed_search):
    service = ProblemService(
        db=db_session,
        search_service=fixed_search,
        problem_agent=ProblemAgent(settings=Settings(OPENAI_API_KEY=None, LLM_FALLBACK_ENABLED=True)),
        quality_checker=ProblemQualityChecker(),
    )

    result = service.generate_problem_batch(
        user_id="user_001",
        request=GenerateProblemRequest(
            document_id="doc_001",
            concepts=["뉴턴 제2법칙"],
            type="short_answer",
            count=1,
            problem_style="calculation_practice",
        ),
    )

    assert result.blueprint.goal == "exam_prep"
    assert result.blueprint.target_rigor == "high"
    problem = result.problems[0]
    assert problem.difficulty == "hard"
    assert problem.bloom_level == "analyze"
    assert "$F = ma$" in problem.answer["text"]
    assert "12 / 3 = 4" in problem.answer["text"]


def test_strict_calculation_request_rejects_explanation_only_problem(db_session, fixed_search):
    service = ProblemService(
        db=db_session,
        search_service=fixed_search,
        problem_agent=FixedProblemAgent([explanation_only_problem()]),
        quality_checker=ProblemQualityChecker(),
    )

    with pytest.raises(ValueError, match="weak_application_fit"):
        service.generate_problems(
            user_id="user_001",
            request=calculation_request(),
        )

    assert db_session.query(Problem).count() == 0


def test_strict_calculation_request_rejects_missing_solution_work(db_session, fixed_search):
    problem = calculation_problem()
    problem["answer"] = {
        "choice_id": None,
        "text": "공식을 사용하면 가속도를 구할 수 있고, 질량이 커지면 가속도는 작아진다.",
    }
    problem["explanation"] = "문제의 조건을 공식에 넣어 판단하면 된다."
    problem["rubric"][1]["expected_evidence"] = ["값을 대입함"]
    service = ProblemService(
        db=db_session,
        search_service=fixed_search,
        problem_agent=FixedProblemAgent([problem]),
        quality_checker=ProblemQualityChecker(),
    )

    with pytest.raises(ValueError, match="weak_application_fit"):
        service.generate_problems(
            user_id="user_001",
            request=calculation_request(),
        )

    assert db_session.query(Problem).count() == 0


def test_quality_checker_allows_controlled_synthetic_numbers_for_formula_problem(fixed_search):
    request = calculation_request()
    chunks = fixed_search.chunks
    profile = LearningTaskStrategyRouter().route(request=request, chunks=chunks)
    readiness = MaterialReadinessAnalyzer().analyze(
        request=request,
        chunks=chunks,
        strategy_profile=profile,
    )
    blueprint = AssessmentBlueprintPlanner().plan(
        request=request,
        strategy_profile=profile,
        material_readiness=readiness,
    )

    is_valid, errors, report = ProblemQualityChecker().validate_with_quality_report(
        calculation_problem(),
        retrieved_chunks=chunks,
        request=request,
        blueprint=blueprint,
        material_readiness=readiness,
        learning_task_strategy=profile,
    )

    assert is_valid is True
    assert errors == []
    assert report.status in {QualityStatus.passed, QualityStatus.limited_source}
    assert report.unsupported_numbers == []
    assert QualityFlag.weak_application_fit not in report.flags


def test_strict_calculation_request_rejects_synthetic_numbers_without_formula_source():
    chunks = [
        RetrievedChunk(
            chunk_id="chunk_relation_only",
            document_id="doc_001",
            content="가속도는 힘에 비례하고 질량에 반비례한다.",
            page=1,
            section_title="힘과 운동",
            concepts=["뉴턴 제2법칙"],
        )
    ]
    request = calculation_request()
    problem = calculation_problem()
    problem["source_chunk_ids"] = ["chunk_relation_only"]
    profile = LearningTaskStrategyRouter().route(request=request, chunks=chunks)
    readiness = MaterialReadinessAnalyzer().analyze(
        request=request,
        chunks=chunks,
        strategy_profile=profile,
    )
    blueprint = AssessmentBlueprintPlanner().plan(
        request=request,
        strategy_profile=profile,
        material_readiness=readiness,
    )

    is_valid, errors, report = ProblemQualityChecker().validate_with_quality_report(
        problem,
        retrieved_chunks=chunks,
        request=request,
        blueprint=blueprint,
        material_readiness=readiness,
        learning_task_strategy=profile,
    )

    assert is_valid is False
    assert QualityFlag.weak_application_fit in report.flags
    assert any("weak_application_fit" in error for error in errors)


def test_strict_problem_quality_rejects_malformed_latex(fixed_search):
    request = calculation_request()
    problem = calculation_problem()
    problem["question"] = "질량이 $3 kg$인 물체에 $12 N$의 힘이 작용할 때 $F = ma를 사용해 가속도를 구하시오."
    profile = LearningTaskStrategyRouter().route(request=request, chunks=fixed_search.chunks)
    readiness = MaterialReadinessAnalyzer().analyze(
        request=request,
        chunks=fixed_search.chunks,
        strategy_profile=profile,
    )
    blueprint = AssessmentBlueprintPlanner().plan(
        request=request,
        strategy_profile=profile,
        material_readiness=readiness,
    )

    is_valid, errors, report = ProblemQualityChecker().validate_with_quality_report(
        problem,
        retrieved_chunks=fixed_search.chunks,
        request=request,
        blueprint=blueprint,
        material_readiness=readiness,
        learning_task_strategy=profile,
    )

    assert is_valid is False
    assert QualityFlag.invalid_latex in report.flags
    assert any("invalid_latex" in error for error in errors)


def calculation_request() -> GenerateProblemRequest:
    return GenerateProblemRequest(
        document_id="doc_001",
        concepts=["뉴턴 제2법칙"],
        type="short_answer",
        count=1,
        difficulty="hard",
        bloom_level="analyze",
        goal="exam_prep",
        course_level="university",
        target_rigor="high",
        quality_mode=QualityMode.strict,
        depth="deep",
        user_requirements="실제 수식을 대입해서 계산하는 대학 시험 대비 문제를 만들어줘.",
    )


def calculation_problem() -> dict:
    return {
        "document_id": "doc_001",
        "type": "short_answer",
        "difficulty": "hard",
        "bloom_level": "analyze",
        "question": (
            "질량이 $3 kg$인 물체에 $12 N$의 힘이 작용할 때 $F = ma$를 사용해 "
            "가속도를 구하고, 질량이 $6 kg$이면 어떻게 달라지는지 설명하시오."
        ),
        "choices": None,
        "answer": {
            "choice_id": None,
            "text": (
                "$a = F / m$이므로 처음에는 $12 / 3 = 4 m/s^2$이고, "
                "질량이 $6 kg$이면 $12 / 6 = 2 m/s^2$이다."
            ),
        },
        "explanation": "자료의 $F = ma$를 $a = F / m$으로 바꾸어 각 조건에 대입한다.",
        "choice_explanations": None,
        "rubric": [
            {
                "criterion": "$F = ma$에서 $a = F / m$ 관계를 세웠다.",
                "points": 2,
                "expected_evidence": ["$F = ma$", "$a = F / m$"],
                "common_mistakes": ["공식의 분자와 분모를 바꿈"],
                "partial_credit_rules": ["공식만 맞으면 부분 점수"],
            },
            {
                "criterion": "각 조건의 값을 대입해 계산했다.",
                "points": 2,
                "expected_evidence": ["$12 / 3 = 4$", "$12 / 6 = 2$"],
                "common_mistakes": ["힘과 질량을 곱함"],
                "partial_credit_rules": ["한 조건만 계산하면 부분 점수"],
            },
            {
                "criterion": "단위와 질량 변화의 의미를 함께 해석했다.",
                "points": 1,
                "expected_evidence": ["$m/s^2$", "절반"],
                "common_mistakes": ["단위를 쓰지 않음"],
                "partial_credit_rules": ["방향만 맞으면 부분 점수"],
            },
        ],
        "concepts": ["뉴턴 제2법칙"],
        "source_chunk_ids": ["chunk_001"],
    }


def explanation_only_problem() -> dict:
    problem = calculation_problem()
    problem["question"] = "같은 힘 조건에서 질량 차이가 가속도에 미치는 영향을 분석하시오."
    problem["answer"] = {
        "choice_id": None,
        "text": "자료에 따르면 같은 힘에서는 질량이 클수록 가속도가 작아진다.",
    }
    problem["explanation"] = "힘, 질량, 가속도의 관계를 말로 설명하면 된다."
    problem["rubric"] = [
        {
            "criterion": "같은 힘 조건을 자료 근거로 제시했다.",
            "points": 2,
            "expected_evidence": ["같은 힘"],
            "common_mistakes": ["힘 조건을 빠뜨림"],
            "partial_credit_rules": ["조건만 언급하면 부분 점수"],
        },
        {
            "criterion": "질량과 가속도의 관계를 분석했다.",
            "points": 2,
            "expected_evidence": ["질량", "가속도", "작아진다"],
            "common_mistakes": ["관계를 반대로 설명함"],
            "partial_credit_rules": ["관계 방향만 맞으면 부분 점수"],
        },
    ]
    return problem
