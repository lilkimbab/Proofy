from app.agents.korean_style import korean_tone_issues
from app.agents.learning_content_quality_checker import LearningContentQualityChecker
from app.agents.problem_agent import ProblemAgent
from app.agents.quality_checker import ProblemQualityChecker
from app.config import Settings
from app.schemas.integration_contracts import RetrievedChunk
from app.schemas.learning_contents import LearningContentBase
from app.schemas.problems import GenerateProblemRequest
from app.schemas.quality import QualityFlag


def test_korean_tone_issues_detects_ai_like_phrasing():
    issues = korean_tone_issues("자료에서 어떤 관계를 중심으로 설명되는가? 핵심 개념을 확인하는 개념이다.")

    assert any("자료에서 어떤 관계" in issue for issue in issues)
    assert any("핵심 개념" in issue for issue in issues)


def test_learning_content_quality_checker_rejects_ai_like_learning_content():
    content = LearningContentBase(
        document_id="doc_001",
        content_type="flashcard",
        concepts=["뉴턴 제2법칙"],
        source_chunk_ids=["chunk_001"],
        difficulty="medium",
        bloom_level="understand",
        quality_status="passed",
        quality_report={"status": "passed", "score": 0.9, "source_grounded": True},
        payload={
            "front": "뉴턴 제2법칙은 자료에서 어떤 관계를 중심으로 설명되는가?",
            "back": "힘, 질량, 가속도의 관계다.",
            "explanation": "핵심 개념을 확인하는 개념이다.",
        },
    )

    result = LearningContentQualityChecker().validate(content, retrieved_chunks=[retrieved_chunk()])

    assert result.is_valid is False
    assert QualityFlag.ai_like_wording in result.flags
    assert any("tone issue" in error for error in result.errors)


def test_problem_quality_checker_rejects_ai_like_wording_in_strict_mode():
    problem = {
        "document_id": "doc_001",
        "type": "multiple_choice",
        "difficulty": "medium",
        "bloom_level": "understand",
        "question": "뉴턴 제2법칙은 자료에서 어떤 관계를 중심으로 설명되는가?",
        "choices": [
            {"id": "A", "text": "힘, 질량, 가속도의 관계다."},
            {"id": "B", "text": "힘과 질량은 서로 무관하다."},
            {"id": "C", "text": "가속도는 조건과 무관하게 늘 같다."},
            {"id": "D", "text": "질량이 커지면 같은 힘에서 가속도도 커진다."},
        ],
        "answer": {"choice_id": "A", "text": "힘, 질량, 가속도의 관계다."},
        "explanation": "핵심 개념을 확인하는 개념이다.",
        "choice_explanations": {
            "A": "힘, 질량, 가속도의 관계와 맞다.",
            "B": "질량은 식에 포함된다.",
            "C": "조건 변화가 빠져 있다.",
            "D": "같은 힘 조건에서는 반대로 판단해야 한다.",
        },
        "rubric": None,
        "concepts": ["뉴턴 제2법칙"],
        "source_chunk_ids": ["chunk_001"],
    }

    is_valid, _errors, report = ProblemQualityChecker().validate_with_quality_report(
        problem,
        retrieved_chunks=[retrieved_chunk()],
        request=GenerateProblemRequest(
            document_id="doc_001",
            concepts=["뉴턴 제2법칙"],
            type="multiple_choice",
            count=1,
            quality_mode="strict",
        ),
    )

    assert is_valid is False
    assert QualityFlag.ai_like_wording in report.flags


def test_problem_agent_uses_exam_style_for_problem_text():
    agent = ProblemAgent(settings=Settings(OPENAI_API_KEY=None, LLM_FALLBACK_ENABLED=True))

    problems = agent.generate(
        GenerateProblemRequest(
            document_id="doc_001",
            concepts=["뉴턴 제2법칙"],
            type="multiple_choice",
            count=1,
        ),
        [
            RetrievedChunk(
                chunk_id="chunk_formula",
                document_id="doc_001",
                content="뉴턴의 제2법칙은 F = ma이다. 힘은 질량과 가속도의 곱이다.",
                page=1,
                section_title="뉴턴의 운동 법칙",
                concepts=["뉴턴 제2법칙"],
            )
        ],
    )

    question_and_choices = " ".join(
        [
            problems[0]["question"],
            *(choice["text"] for choice in problems[0]["choices"]),
        ]
    )
    assert "해볼까요" not in question_and_choices
    assert "잘하셨어요" not in question_and_choices
    assert "헷갈리셨군요" not in question_and_choices
    assert "?" in problems[0]["question"]
    assert "$F = ma$" in problems[0]["choices"][0]["text"]


def retrieved_chunk():
    return RetrievedChunk(
        chunk_id="chunk_001",
        document_id="doc_001",
        content="뉴턴 제2법칙은 힘, 질량, 가속도의 관계를 다룬다. 힘은 질량과 가속도의 곱이다.",
        page=1,
        section_title="뉴턴의 운동 법칙",
        concepts=["뉴턴 제2법칙", "힘", "질량", "가속도"],
    )
