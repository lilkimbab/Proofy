import os

import pytest

from app.agents.feedback_agent import FeedbackAgent
from app.agents.problem_agent import ProblemAgent
from app.config import Settings
from app.llm import LLMServiceError
from app.models import Problem, Submission
from app.schemas.integration_contracts import RetrievedChunk
from app.schemas.problems import GenerateProblemRequest


pytestmark = pytest.mark.llm


def live_settings() -> Settings:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        pytest.skip("OPENAI_API_KEY is not configured")
    return Settings(
        OPENAI_API_KEY=api_key,
        LLM_FALLBACK_ENABLED=False,
        PROBLEM_MODEL=os.getenv("OPENAI_SMOKE_PROBLEM_MODEL", "gpt-5.4-mini"),
        GRADING_MODEL=os.getenv("OPENAI_SMOKE_GRADING_MODEL", "gpt-5.4-mini"),
        LLM_MAX_OUTPUT_TOKENS_PROBLEM=1800,
        LLM_MAX_OUTPUT_TOKENS_FEEDBACK=700,
        OPENAI_TIMEOUT_SECONDS=45,
        OPENAI_MAX_RETRIES=0,
    )


def test_live_openai_problem_generation_smoke():
    settings = live_settings()
    agent = ProblemAgent(settings=settings)

    try:
        problems = agent.generate(
            request=GenerateProblemRequest(
                document_id="smoke_doc_001",
                concepts=["뉴턴 제2법칙"],
                type="multiple_choice",
                count=1,
                difficulty="medium",
                bloom_level="understand",
            ),
            chunks=[
                RetrievedChunk(
                    chunk_id="smoke_chunk_001",
                    document_id="smoke_doc_001",
                    content=(
                        "뉴턴의 제2법칙은 힘이 질량과 가속도의 곱과 같다는 법칙이며 "
                        "F = ma로 표현된다. 같은 힘에서는 질량이 클수록 가속도는 작아진다."
                    ),
                    page=1,
                    section_title="운동 법칙",
                    concepts=["뉴턴 제2법칙", "힘", "질량", "가속도"],
                )
            ],
        )
    except LLMServiceError as exc:
        pytest.fail(f"Live OpenAI problem generation failed: {exc}")

    assert len(problems) == 1
    problem = problems[0]
    assert problem["document_id"] == "smoke_doc_001"
    assert problem["type"] == "multiple_choice"
    assert problem["source_chunk_ids"]
    assert "smoke_chunk_001" in problem["source_chunk_ids"]
    assert len(problem["choices"]) == 4
    assert problem["answer"]["choice_id"] in {choice["id"] for choice in problem["choices"]}


def test_live_openai_short_answer_feedback_smoke():
    settings = live_settings()
    agent = FeedbackAgent(settings=settings)

    try:
        feedback = agent.grade_short_answer(
            problem=short_answer_problem(),
            submission=Submission(
                id="smoke_sub_001",
                problem_id="smoke_prob_001",
                user_id="smoke_user_001",
                answer={"text": "뉴턴 제2법칙은 힘이 질량과 가속도의 곱이라는 뜻이고 F=ma로 나타낸다."},
            ),
            chunks=[
                RetrievedChunk(
                    chunk_id="smoke_chunk_001",
                    document_id="smoke_doc_001",
                    content="뉴턴의 제2법칙은 F = ma로 표현되며 힘, 질량, 가속도의 관계를 설명한다.",
                    page=1,
                    section_title="운동 법칙",
                    concepts=["뉴턴 제2법칙"],
                )
            ],
        )
    except LLMServiceError as exc:
        pytest.fail(f"Live OpenAI short-answer feedback failed: {exc}")

    assert feedback["max_score"] == 2
    assert 0 <= feedback["score"] <= feedback["max_score"]
    assert feedback["mistake_type"]
    assert feedback["summary"]
    assert feedback["feedback"]
    assert "recommended_review" in feedback


def short_answer_problem() -> Problem:
    return Problem(
        id="smoke_prob_001",
        user_id="smoke_user_001",
        document_id="smoke_doc_001",
        type="short_answer",
        difficulty="medium",
        bloom_level="understand",
        question="뉴턴의 제2법칙을 설명하시오.",
        choices=None,
        answer={"choice_id": None, "text": "뉴턴의 제2법칙은 힘이 질량과 가속도의 곱이라는 법칙이며 F = ma로 표현된다."},
        explanation="힘, 질량, 가속도의 관계를 설명하면 된다.",
        choice_explanations=None,
        rubric=[{"criterion": "F = ma와 힘, 질량, 가속도의 관계를 설명한다.", "points": 2}],
        concepts=["뉴턴 제2법칙"],
        source_chunk_ids=["smoke_chunk_001"],
        quality_status="passed",
    )
