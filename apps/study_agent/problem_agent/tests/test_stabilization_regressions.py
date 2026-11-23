import pytest

from app.agents import ProblemAgent, ProblemQualityChecker
from app.config import Settings
from app.models import Problem, UsageLedger
from app.schemas.integration_contracts import RetrievedChunk
from app.schemas.problems import GenerateProblemRequest
from app.schemas.quality import ContentForm, SubjectDomain
from app.services.learning_task_strategy_router import LearningTaskStrategyRouter
from app.services.problem_service import ProblemService


class FixedProblemAgent:
    def __init__(self, problems):
        self.problems = problems

    def generate(self, request, chunks, **kwargs):
        return self.problems


class ModeReportingProblemAgent(FixedProblemAgent):
    def __init__(self, problems, *, generation_mode):
        super().__init__(problems)
        self.generation_mode = generation_mode
        self.last_generation_mode = None

    def generate(self, request, chunks, **kwargs):
        self.last_generation_mode = self.generation_mode
        return super().generate(request, chunks, **kwargs)


def test_problem_agent_deterministic_fallback_still_works_in_test_mode():
    agent = ProblemAgent(
        settings=Settings(
            _env_file=None,
            LLM_PROVIDER="openai",
            OPENAI_API_KEY=None,
            GEMINI_API_KEY=None,
            LLM_FALLBACK_ENABLED=True,
        )
    )

    problems = agent.generate(
        request=GenerateProblemRequest(
            document_id="doc_001",
            concepts=["뉴턴 제2법칙"],
            type="multiple_choice",
            count=1,
        ),
        chunks=[
            RetrievedChunk(
                chunk_id="chunk_001",
                document_id="doc_001",
                content="뉴턴의 제2법칙은 F = ma이다. 같은 힘이 작용할 때 질량이 클수록 가속도는 작아진다.",
                page=12,
                section_title="뉴턴의 운동 법칙",
                concepts=["뉴턴 제2법칙", "질량과 가속도"],
            )
        ],
    )

    assert len(problems) == 1
    assert agent.last_generation_mode == ProblemAgent.GENERATION_MODE_DETERMINISTIC_FALLBACK


def test_high_rigor_deterministic_fallback_is_marked_needs_review(db_session, fixed_search):
    request = high_rigor_newton_request()
    service = ProblemService(
        db=db_session,
        search_service=fixed_search,
        problem_agent=ModeReportingProblemAgent(
            [valid_high_rigor_newton_problem(request)],
            generation_mode=ProblemAgent.GENERATION_MODE_DETERMINISTIC_FALLBACK,
        ),
        quality_checker=ProblemQualityChecker(),
    )

    result = service.generate_problem_batch(user_id="user_001", request=request)

    assert result.problems[0].quality_status == "needs_review"
    assert "deterministic fallback high-rigor generation requires review" in result.quality_summary.warnings
    assert db_session.query(UsageLedger).count() == 0


def test_high_rigor_llm_backed_generation_status_is_not_downgraded(db_session, fixed_search):
    request = high_rigor_newton_request()
    service = ProblemService(
        db=db_session,
        search_service=fixed_search,
        problem_agent=ModeReportingProblemAgent(
            [valid_high_rigor_newton_problem(request)],
            generation_mode=ProblemAgent.GENERATION_MODE_LLM,
        ),
        quality_checker=ProblemQualityChecker(),
    )

    result = service.generate_problem_batch(user_id="user_001", request=request)

    assert result.problems[0].quality_status == "passed"


def test_router_does_not_treat_korean_expression_as_table():
    profile = route_for_chunk(
        concepts=["시적 표현"],
        content="이 지문에서 화자는 비유적 표현을 통해 그리움이라는 정서를 드러낸다.",
        section_title="현대시 감상",
    )

    assert profile.subject_domain == SubjectDomain.korean_language
    assert ContentForm.data_table not in profile.content_forms
    assert ContentForm.formula not in profile.content_forms
    assert ContentForm.code not in profile.content_forms


def test_router_does_not_treat_policy_hyphen_as_formula():
    profile = route_for_chunk(
        concepts=["정책과 제도"],
        content="정책-제도 관계는 사회적 요구와 역사적 맥락에 따라 변화한다.",
        section_title="사회 제도 변화",
    )

    assert profile.subject_domain in {SubjectDomain.social_studies, SubjectDomain.general_concept}
    assert ContentForm.formula not in profile.content_forms
    assert ContentForm.concept_relation in profile.content_forms


def test_router_detects_code_only_when_code_evidence_is_present():
    profile = route_for_chunk(
        concepts=["반복문"],
        content="다음 코드는 배열을 순회한다.\nfor item in items:\n    return item",
        section_title="파이썬 반복문",
    )

    assert profile.subject_domain == SubjectDomain.computer_science
    assert ContentForm.code in profile.content_forms


def test_router_detects_formula_and_relation_from_formula_source():
    profile = route_for_chunk(
        concepts=["뉴턴 제2법칙"],
        content="뉴턴의 제2법칙은 F = ma이다. 같은 힘에서는 질량이 클수록 가속도는 작아진다.",
        section_title="뉴턴의 운동 법칙",
    )

    assert ContentForm.formula in profile.content_forms
    assert ContentForm.concept_relation in profile.content_forms


def test_router_synthesizes_topic_from_multiple_chunks_when_request_is_generic():
    request = GenerateProblemRequest(
        document_id="doc_multi",
        concepts=["전체 범위"],
        type="multiple_choice",
        count=1,
    )
    chunks = [
        RetrievedChunk(
            chunk_id="chunk_supply_1",
            document_id="doc_multi",
            content="수요가 증가하면 가격과 거래량에 영향을 준다.",
            page=1,
            section_title="수요와 공급",
            concepts=["수요와 공급", "수요 변화"],
        ),
        RetrievedChunk(
            chunk_id="chunk_supply_2",
            document_id="doc_multi",
            content="공급이 감소하면 시장 균형이 변하고 가격은 상승할 수 있다.",
            page=2,
            section_title="수요와 공급",
            concepts=["수요와 공급", "시장 균형"],
        ),
        RetrievedChunk(
            chunk_id="chunk_noise",
            document_id="doc_multi",
            content="다음 코드는 예시일 뿐이다.\nfor item in items:\n    return item",
            page=99,
            section_title="부록",
            concepts=["부록"],
        ),
    ]

    profile = LearningTaskStrategyRouter().route(request=request, chunks=chunks)

    assert profile.topic_label == "수요와 공급"
    assert "수요와 공급" in profile.core_keywords
    assert ContentForm.concept_relation in profile.content_forms
    assert ContentForm.code not in profile.content_forms


def test_router_keeps_relevant_formula_when_other_chunks_are_context():
    request = GenerateProblemRequest(
        document_id="doc_physics",
        concepts=["뉴턴 제2법칙"],
        type="multiple_choice",
        count=1,
    )
    chunks = [
        RetrievedChunk(
            chunk_id="chunk_force",
            document_id="doc_physics",
            content="뉴턴의 제2법칙은 F = ma이며 질량과 가속도의 관계를 설명한다.",
            page=1,
            section_title="뉴턴의 운동 법칙",
            concepts=["뉴턴 제2법칙", "질량과 가속도"],
        ),
        RetrievedChunk(
            chunk_id="chunk_history",
            document_id="doc_physics",
            content="고전 역학은 여러 운동 현상을 설명하는 이론 체계다.",
            page=2,
            section_title="고전 역학",
            concepts=["고전 역학"],
        ),
        RetrievedChunk(
            chunk_id="chunk_note",
            document_id="doc_physics",
            content="시험에서는 용어의 의미와 조건을 함께 확인한다.",
            page=3,
            section_title="학습 안내",
            concepts=["학습 안내"],
        ),
    ]

    profile = LearningTaskStrategyRouter().route(request=request, chunks=chunks)

    assert profile.topic_label == "뉴턴 제2법칙"
    assert ContentForm.formula in profile.content_forms
    assert ContentForm.concept_relation in profile.content_forms


def test_strict_mode_rejects_multiple_choice_answer_leak(db_session, fixed_search):
    problem = valid_multiple_choice_problem()
    problem["question"] = "뉴턴 제2법칙 문제다. 정답은 A이다. 가장 적절한 것은?"
    service = ProblemService(
        db=db_session,
        search_service=fixed_search,
        problem_agent=FixedProblemAgent([problem]),
        quality_checker=ProblemQualityChecker(),
    )

    with pytest.raises(ValueError, match="answer_leak"):
        service.generate_problems(
            user_id="user_001",
            request=GenerateProblemRequest(
                document_id="doc_001",
                concepts=["뉴턴 제2법칙"],
                type="multiple_choice",
                count=1,
                quality_mode="strict",
            ),
        )

    assert db_session.query(Problem).count() == 0


def test_rejects_generated_problem_without_requested_concept_overlap(db_session, fixed_search):
    problem = valid_multiple_choice_problem()
    problem["concepts"] = ["세포 분열"]
    service = ProblemService(
        db=db_session,
        search_service=fixed_search,
        problem_agent=FixedProblemAgent([problem]),
        quality_checker=ProblemQualityChecker(),
    )

    with pytest.raises(ValueError, match="generated concepts must overlap request concepts"):
        service.generate_problems(
            user_id="user_001",
            request=GenerateProblemRequest(
                document_id="doc_001",
                concepts=["뉴턴 제2법칙"],
                type="multiple_choice",
                count=1,
                quality_mode="strict",
            ),
        )

    assert db_session.query(Problem).count() == 0


def test_strict_mode_rejects_unsupported_number_in_choice(db_session, fixed_search):
    problem = valid_multiple_choice_problem()
    problem["choices"][1]["text"] = "광속은 초속 299792458m이다."
    problem["choice_explanations"]["B"] = "자료에 없는 광속 수치를 사용한 보기다."
    service = ProblemService(
        db=db_session,
        search_service=fixed_search,
        problem_agent=FixedProblemAgent([problem]),
        quality_checker=ProblemQualityChecker(),
    )

    with pytest.raises(ValueError, match="unsupported_source"):
        service.generate_problems(
            user_id="user_001",
            request=GenerateProblemRequest(
                document_id="doc_001",
                concepts=["뉴턴 제2법칙"],
                type="multiple_choice",
                count=1,
                quality_mode="strict",
            ),
        )

    assert db_session.query(Problem).count() == 0


def route_for_chunk(*, concepts: list[str], content: str, section_title: str):
    request = GenerateProblemRequest(
        document_id="doc_router",
        concepts=concepts,
        type="multiple_choice",
        count=1,
    )
    chunk = RetrievedChunk(
        chunk_id="chunk_router",
        document_id="doc_router",
        content=content,
        page=1,
        section_title=section_title,
        concepts=concepts,
    )
    return LearningTaskStrategyRouter().route(request=request, chunks=[chunk])


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
    }


def high_rigor_newton_request():
    return GenerateProblemRequest(
        document_id="doc_001",
        concepts=["뉴턴 제2법칙", "질량과 가속도"],
        type="short_answer",
        count=1,
        difficulty="hard",
        bloom_level="analyze",
        target_rigor="high",
        user_requirements="조건을 바꾼 상황에서 근거를 적용해 분석하는 고난도 문제를 만들어줘.",
    )


def valid_high_rigor_newton_problem(request):
    return {
        "document_id": request.document_id,
        "type": request.type.value,
        "difficulty": request.difficulty.value,
        "bloom_level": request.bloom_level.value,
        "question": (
            "같은 힘이 작용하는 상황에서 질량이 더 큰 물체와 작은 물체를 비교하고, "
            "F = ma 관계를 근거로 가속도가 어떻게 달라지는지 분석하시오."
        ),
        "choices": None,
        "answer": {
            "choice_id": None,
            "text": (
                "F = ma에서 같은 힘이면 질량이 커질수록 가속도는 작아진다. "
                "따라서 질량이 더 큰 물체는 작은 물체보다 가속도가 작고, 이는 자료의 질량과 가속도 관계에 근거한다."
            ),
        },
        "explanation": "자료의 F = ma 관계와 같은 힘 조건을 함께 적용해 질량 변화의 영향을 비교한다.",
        "choice_explanations": None,
        "rubric": [
            {
                "criterion": "같은 힘 조건을 명시했다.",
                "points": 1,
                "expected_evidence": ["같은 힘"],
                "common_mistakes": ["힘 조건을 바꾸어 해석함"],
                "partial_credit_rules": ["힘 조건을 암시하면 부분 점수"],
            },
            {
                "criterion": "F = ma 관계를 근거로 사용했다.",
                "points": 2,
                "expected_evidence": ["F = ma"],
                "common_mistakes": ["공식 없이 결론만 제시함"],
                "partial_credit_rules": ["공식을 언급하되 적용이 부족하면 부분 점수"],
            },
            {
                "criterion": "질량 변화가 가속도에 미치는 영향을 비교했다.",
                "points": 2,
                "expected_evidence": ["질량이 클수록 가속도는 작아진다"],
                "common_mistakes": ["질량이 클수록 가속도도 커진다고 설명함"],
                "partial_credit_rules": ["방향은 맞지만 비교 설명이 부족하면 부분 점수"],
            },
        ],
        "concepts": request.concepts,
        "source_chunk_ids": ["chunk_001"],
        "difficulty_profile": {
            "cognitive_demand_score": 0.72,
            "reasoning_steps_required": 3,
        },
    }
