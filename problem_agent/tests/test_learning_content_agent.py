import pytest

from app.agents import LearningContentAgent, LearningContentQualityChecker
from app.config import Settings
from app.llm import LLMOutputValidationError, LLMServiceError
from app.schemas.integration_contracts import RetrievedChunk
from app.schemas.learning_contents import GenerateLearningContentRequest, LearningContentBase, LearningContentType


class FakeLLM:
    def __init__(self, payloads, *, available=True):
        self.payloads = list(payloads)
        self.available = available
        self.calls = []

    def generate_json(
        self,
        *,
        model,
        prompt,
        schema_name,
        schema,
        max_output_tokens=None,
        reasoning_effort=None,
        prompt_cache_key=None,
        safety_identifier=None,
    ):
        self.calls.append(
            {
                "model": model,
                "prompt": prompt,
                "schema_name": schema_name,
                "schema": schema,
                "max_output_tokens": max_output_tokens,
                "reasoning_effort": reasoning_effort,
                "prompt_cache_key": prompt_cache_key,
                "safety_identifier": safety_identifier,
            }
        )
        return self.payloads.pop(0)


def test_learning_content_agent_deterministic_candidates_pass_quality_checker():
    agent = LearningContentAgent(settings=Settings(OPENAI_API_KEY=None, LLM_FALLBACK_ENABLED=True))
    checker = LearningContentQualityChecker()

    for content_type in (
        LearningContentType.flashcard,
        LearningContentType.cloze,
        LearningContentType.true_false,
        LearningContentType.ordering,
        LearningContentType.matching,
        LearningContentType.worked_example,
        LearningContentType.concept_summary_card,
    ):
        generated = agent.generate(
            request=GenerateLearningContentRequest(
                document_id="doc_001",
                concepts=["뉴턴 제2법칙"],
                content_type=content_type,
                count=2,
            ),
            chunks=[retrieved_chunk()],
        )

        assert len(generated) == 2
        for content_data in generated:
            content = LearningContentBase.model_validate(content_data)
            quality = checker.validate(content, retrieved_chunks=[retrieved_chunk()])

            assert content.content_type == content_type
            assert content.quality_report.action == "validate_before_save"
            assert quality.is_valid is True


def test_learning_content_agent_rejects_empty_chunks():
    agent = LearningContentAgent(settings=Settings(OPENAI_API_KEY=None, LLM_FALLBACK_ENABLED=True))

    with pytest.raises(ValueError, match="retrieved chunk"):
        agent.generate(
            request=GenerateLearningContentRequest(
                document_id="doc_001",
                concepts=["뉴턴 제2법칙"],
                content_type="flashcard",
            ),
            chunks=[],
        )


def test_learning_content_agent_rejects_workflow_content_types_for_direct_generation():
    agent = LearningContentAgent(settings=Settings(OPENAI_API_KEY=None, LLM_FALLBACK_ENABLED=True))

    with pytest.raises(ValueError, match="later-phase workflow"):
        agent.generate(
            request=GenerateLearningContentRequest(
                document_id="doc_001",
                concepts=["뉴턴 제2법칙"],
                content_type="mistake_drill",
            ),
            chunks=[retrieved_chunk()],
        )


def test_learning_content_agent_requires_llm_when_fallback_disabled():
    agent = LearningContentAgent(
        llm=FakeLLM([], available=False),
        settings=Settings(OPENAI_API_KEY=None, LLM_FALLBACK_ENABLED=False),
    )

    with pytest.raises(LLMServiceError):
        agent.generate(
            request=GenerateLearningContentRequest(
                document_id="doc_001",
                concepts=["뉴턴 제2법칙"],
                content_type="flashcard",
            ),
            chunks=[retrieved_chunk()],
        )


def test_learning_content_agent_routes_models_by_difficulty():
    fake_llm = FakeLLM(
        [
            learning_content_payload(difficulty="medium"),
            learning_content_payload(difficulty="hard"),
        ]
    )
    agent = LearningContentAgent(
        llm=fake_llm,
        settings=Settings(
            OPENAI_API_KEY="test-key",
            LEARNING_CONTENT_MODEL="gpt-mini",
            LEARNING_CONTENT_QUALITY_MODEL="gpt-large",
        ),
    )

    agent.generate(
        request=GenerateLearningContentRequest(
            document_id="doc_001",
            concepts=["뉴턴 제2법칙"],
            content_type="flashcard",
            difficulty="medium",
        ),
        chunks=[retrieved_chunk()],
        safety_identifier="user_safe",
    )
    agent.generate(
        request=GenerateLearningContentRequest(
            document_id="doc_001",
            concepts=["뉴턴 제2법칙"],
            content_type="flashcard",
            difficulty="hard",
        ),
        chunks=[retrieved_chunk()],
    )

    assert [call["model"] for call in fake_llm.calls] == ["gpt-mini", "gpt-large"]
    assert fake_llm.calls[0]["schema_name"] == "learning_content_generation_v1"
    assert fake_llm.calls[0]["safety_identifier"] == "user_safe"


def test_learning_content_agent_rejects_invalid_llm_schema():
    payload = learning_content_payload()
    payload["contents"][0]["payload"]["extra"] = "flashcard payload must reject this"
    agent = LearningContentAgent(llm=FakeLLM([payload]), settings=Settings(OPENAI_API_KEY="test-key"))

    with pytest.raises(LLMOutputValidationError):
        agent.generate(
            request=GenerateLearningContentRequest(
                document_id="doc_001",
                concepts=["뉴턴 제2법칙"],
                content_type="flashcard",
            ),
            chunks=[retrieved_chunk()],
        )


def retrieved_chunk():
    return RetrievedChunk(
        chunk_id="chunk_001",
        document_id="doc_001",
        content=(
            "뉴턴 제2법칙은 힘 질량 가속도 관계를 설명한다. 같은 힘 조건에서 질량이 클수록 "
            "가속도는 작아지고 힘은 질량과 가속도의 곱으로 표현된다."
        ),
        page=1,
        section_title="뉴턴의 운동 법칙",
        concepts=["뉴턴 제2법칙", "힘", "질량", "가속도"],
    )


def learning_content_payload(*, difficulty="medium"):
    return {
        "contents": [
            {
                "document_id": "doc_001",
                "content_type": "flashcard",
                "difficulty": difficulty,
                "bloom_level": "understand",
                "concepts": ["뉴턴 제2법칙"],
                "source_chunk_ids": ["chunk_001"],
                "payload": {
                    "front": "뉴턴 제2법칙은 어떤 관계를 설명하는가?",
                    "back": "힘, 질량, 가속도의 관계를 설명한다.",
                    "explanation": "자료에서는 뉴턴 제2법칙을 힘, 질량, 가속도의 관계로 다룬다.",
                },
            }
        ]
    }
