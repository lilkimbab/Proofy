import sys
from types import SimpleNamespace

import pytest

from app.agents.feedback_agent import FeedbackAgent
from app.agents.problem_agent import PROBLEM_OUTPUT_SCHEMA, ProblemAgent
from app.config import Settings
from app.llm import LLMOutputValidationError, LLMServiceError, OpenAIClient, safety_identifier_for_user
from app.models import Problem, Submission
from app.schemas.integration_contracts import RetrievedChunk
from app.schemas.problem_kernels import (
    ContentAtom,
    ContentAtomType,
    EvidenceObligation,
    EvidenceRole,
    ProblemKernelPlan,
    ProblemKernelType,
)
from app.schemas.problems import ChoiceDiagnosticSpec, FOLLOWUP_PROBLEM_TYPE_SLUGS, GenerateProblemRequest
from app.schemas.quality import SourceGroundingMode, SourceGroundingProfile


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
        image_inputs=None,
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
                "image_inputs": image_inputs,
                "max_output_tokens": max_output_tokens,
                "reasoning_effort": reasoning_effort,
                "prompt_cache_key": prompt_cache_key,
                "safety_identifier": safety_identifier,
            }
        )
        return self.payloads.pop(0)


def test_openai_client_uses_strict_json_schema(monkeypatch):
    captured = {"client": {}}

    class FakeResponses:
        def create(self, **kwargs):
            captured["request"] = kwargs
            return SimpleNamespace(output_text='{"ok": true}')

    class FakeOpenAI:
        def __init__(self, api_key, timeout=None, max_retries=None):
            captured["client"] = {
                "api_key": api_key,
                "timeout": timeout,
                "max_retries": max_retries,
            }
            self.responses = FakeResponses()

    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(OpenAI=FakeOpenAI))
    client = OpenAIClient(
        Settings(
            LLM_PROVIDER="openai",
            OPENAI_API_KEY="test-key",
            OPENAI_TIMEOUT_SECONDS=12,
            OPENAI_MAX_RETRIES=2,
        )
    )

    payload = client.generate_json(
        model="gpt-test",
        prompt="return json",
        schema_name="test_schema",
        schema={"type": "object"},
        max_output_tokens=123,
        reasoning_effort="low",
        prompt_cache_key="test-cache",
        safety_identifier="user_safe",
    )

    assert payload == {"ok": True}
    assert captured["client"] == {
        "api_key": "test-key",
        "timeout": 12,
        "max_retries": 2,
    }
    request = captured["request"]
    assert request["model"] == "gpt-test"
    assert request["text"]["format"]["type"] == "json_schema"
    assert request["text"]["format"]["strict"] is True
    assert request["max_output_tokens"] == 123
    assert request["reasoning"] == {"effort": "low"}
    assert request["prompt_cache_key"] == "test-cache"
    assert request["safety_identifier"] == "user_safe"


def test_problem_output_schema_has_strict_mcq_plan_contract():
    problem_schema = PROBLEM_OUTPUT_SCHEMA["properties"]["problems"]["items"]
    assert "mcq_plan" in problem_schema["required"]

    mcq_plan_schema = problem_schema["properties"]["mcq_plan"]
    assert mcq_plan_schema["additionalProperties"] is False
    assert set(mcq_plan_schema["required"]) == {
        "kernel_type",
        "source_rule_or_evidence",
        "concrete_scenario",
        "correct_answer_claim",
        "correct_answer_evidence_link",
        "distractor_plans",
        "prohibited_patterns",
        "required_source_chunk_ids",
    }

    distractor_schema = mcq_plan_schema["properties"]["distractor_plans"]["items"]
    assert distractor_schema["additionalProperties"] is False


def test_openai_client_can_send_base64_image_inputs_with_structured_output(monkeypatch):
    captured = {"client": {}}

    class FakeResponses:
        def create(self, **kwargs):
            captured["request"] = kwargs
            return SimpleNamespace(output_text='{"ok": true}')

    class FakeOpenAI:
        def __init__(self, api_key, timeout=None, max_retries=None):
            self.responses = FakeResponses()

    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(OpenAI=FakeOpenAI))
    client = OpenAIClient(Settings(LLM_PROVIDER="openai", OPENAI_API_KEY="test-key"))

    payload = client.generate_json(
        model="gpt-test",
        prompt="return json",
        schema_name="test_schema",
        schema={"type": "object"},
        image_inputs=[
            {
                "label": "heap diagram",
                "chunk_id": "chunk_heap",
                "page": 6,
                "image": "iVBORw0KGgoAAAANSUhEUgAA",
                "detail": "low",
            }
        ],
    )

    assert payload == {"ok": True}
    request_input = captured["request"]["input"]
    assert request_input[0]["role"] == "user"
    content = request_input[0]["content"]
    assert content[0] == {"type": "input_text", "text": "return json"}
    assert "chunk_id=chunk_heap" in content[1]["text"]
    assert content[2] == {
        "type": "input_image",
        "image_url": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAA",
        "detail": "low",
    }


def test_gemini_provider_uses_native_structured_output(monkeypatch):
    captured = {}

    class FakeResponse:
        status_code = 200
        headers = {"x-request-id": "gemini-response-001"}

        def json(self):
            return {
                "candidates": [{"content": {"parts": [{"text": '{"ok": true}'}]}}],
                "usageMetadata": {
                    "promptTokenCount": 10,
                    "candidatesTokenCount": 3,
                    "totalTokenCount": 13,
                },
            }

    class FakeClient:
        def __init__(self, timeout=None):
            captured["timeout"] = timeout

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return None

        def post(self, url, *, headers, json):
            captured["url"] = url
            captured["headers"] = headers
            captured["request"] = json
            return FakeResponse()

    monkeypatch.setitem(sys.modules, "httpx", SimpleNamespace(Client=FakeClient))
    client = OpenAIClient(
        Settings(
            LLM_PROVIDER="gemini",
            GEMINI_API_KEY="gemini-key",
            GEMINI_OPENAI_BASE_URL="https://gemini.example/openai/",
            OPENAI_TIMEOUT_SECONDS=12,
            OPENAI_MAX_RETRIES=2,
        )
    )

    payload = client.generate_json(
        model="gemini-3.5-flash",
        prompt="return json",
        schema_name="test_schema",
        schema={
            "type": "object",
            "properties": {"ok": {"type": "boolean", "minLength": 1}},
            "required": ["ok"],
        },
        max_output_tokens=123,
        reasoning_effort="low",
        prompt_cache_key="ignored-for-gemini",
        safety_identifier="ignored-for-gemini",
    )

    assert payload == {"ok": True}
    assert captured["timeout"] == 12
    assert captured["url"] == "https://gemini.example/models/gemini-3.5-flash:generateContent"
    assert captured["headers"] == {
        "Content-Type": "application/json",
        "x-goog-api-key": "gemini-key",
    }
    request = captured["request"]
    assert request["contents"] == [{"role": "user", "parts": [{"text": "return json"}]}]
    assert request["generationConfig"] == {
        "responseFormat": {
            "text": {
                "mimeType": "APPLICATION_JSON",
                "schema": {
                    "type": "object",
                    "properties": {"ok": {"type": "boolean"}},
                    "required": ["ok"],
                },
            }
        },
        "maxOutputTokens": 123,
        "thinkingConfig": {"thinkingLevel": "MINIMAL"},
    }
    assert client.last_request_id == "gemini-response-001"
    assert client.last_usage == {"input_tokens": 10, "output_tokens": 3, "total_tokens": 13}


def test_gemini_provider_can_send_base64_image_inputs(monkeypatch):
    captured = {}

    class FakeResponse:
        status_code = 200
        headers = {}

        def json(self):
            return {"candidates": [{"content": {"parts": [{"text": '{"ok": true}'}]}}]}

    class FakeClient:
        def __init__(self, timeout=None):
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return None

        def post(self, url, *, headers, json):
            captured["request"] = json
            return FakeResponse()

    monkeypatch.setitem(sys.modules, "httpx", SimpleNamespace(Client=FakeClient))
    client = OpenAIClient(
        Settings(
            LLM_PROVIDER="gemini",
            GEMINI_API_KEY="gemini-key",
        )
    )

    payload = client.generate_json(
        model="gemini-3.5-flash",
        prompt="return json",
        schema_name="test_schema",
        schema={"type": "object"},
        image_inputs=[
            {
                "label": "heap diagram",
                "chunk_id": "chunk_heap",
                "page": 6,
                "image": "iVBORw0KGgoAAAANSUhEUgAA",
                "detail": "low",
            }
        ],
    )

    assert payload == {"ok": True}
    parts = captured["request"]["contents"][0]["parts"]
    assert parts[0] == {"text": "return json"}
    assert "chunk_id=chunk_heap" in parts[1]["text"]
    assert parts[2] == {
        "inline_data": {"mime_type": "image/png", "data": "iVBORw0KGgoAAAANSUhEUgAA"},
    }


def test_gemini_json_parser_repairs_raw_newlines_inside_strings():
    client = OpenAIClient(Settings(LLM_PROVIDER="gemini", GEMINI_API_KEY="gemini-key"))

    payload = client._loads_gemini_json('{"question": "첫 줄\n둘째 줄", "ok": true}')

    assert payload == {"question": "첫 줄\n둘째 줄", "ok": True}


def test_openai_client_requires_api_key():
    client = OpenAIClient(Settings(LLM_PROVIDER="openai", OPENAI_API_KEY=None))

    with pytest.raises(LLMServiceError):
        client.generate_json(
            model="gpt-test",
            prompt="return json",
            schema_name="test_schema",
            schema={"type": "object"},
        )


def test_gemini_provider_requires_api_key():
    client = OpenAIClient(Settings(LLM_PROVIDER="gemini", GEMINI_API_KEY=None))

    with pytest.raises(LLMServiceError, match="GEMINI_API_KEY"):
        client.generate_json(
            model="gemini-3.5-flash",
            prompt="return json",
            schema_name="test_schema",
            schema={"type": "object"},
        )


def test_safety_identifier_for_user_is_stable_and_does_not_expose_raw_user_id():
    identifier = safety_identifier_for_user("student@example.com")

    assert identifier == safety_identifier_for_user("student@example.com")
    assert identifier.startswith("user_")
    assert "student" not in identifier
    assert "@" not in identifier


def test_openai_client_reports_invalid_json_as_output_validation_error(monkeypatch):
    class FakeResponses:
        def create(self, **kwargs):
            return SimpleNamespace(output_text="not-json")

    class FakeOpenAI:
        def __init__(self, api_key, timeout=None, max_retries=None):
            self.responses = FakeResponses()

    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(OpenAI=FakeOpenAI))
    client = OpenAIClient(Settings(LLM_PROVIDER="openai", OPENAI_API_KEY="test-key"))

    with pytest.raises(LLMOutputValidationError):
        client.generate_json(
            model="gpt-test",
            prompt="return json",
            schema_name="test_schema",
            schema={"type": "object"},
        )


def test_problem_agent_routes_models_by_problem_type_and_difficulty():
    payloads = [
        problem_payload(problem_type="multiple_choice", difficulty="medium"),
        problem_payload(problem_type="short_answer", difficulty="medium"),
        problem_payload(problem_type="multiple_choice", difficulty="hard"),
    ]
    fake_llm = FakeLLM(payloads)
    agent = ProblemAgent(
        llm=fake_llm,
        settings=Settings(
            OPENAI_API_KEY="test-key",
            PROBLEM_MODEL="gpt-mini",
            PROBLEM_QUALITY_MODEL="gpt-large",
            PROBLEM_AGENT_COST_PROFILE="full",
            LLM_REASONING_EFFORT_PROBLEM="low",
            LLM_REASONING_EFFORT_PROBLEM_QUALITY="medium",
        ),
    )

    agent.generate(
        request=GenerateProblemRequest(
            document_id="doc_001",
            concepts=["뉴턴 제2법칙"],
            type="multiple_choice",
            count=1,
            difficulty="medium",
        ),
        chunks=[retrieved_chunk()],
    )
    agent.generate(
        request=GenerateProblemRequest(
            document_id="doc_001",
            concepts=["뉴턴 제2법칙"],
            type="short_answer",
            count=1,
            difficulty="medium",
        ),
        chunks=[retrieved_chunk()],
    )
    agent.generate(
        request=GenerateProblemRequest(
            document_id="doc_001",
            concepts=["뉴턴 제2법칙"],
            type="multiple_choice",
            count=1,
            difficulty="hard",
        ),
        chunks=[retrieved_chunk()],
    )

    assert [call["model"] for call in fake_llm.calls] == ["gpt-mini", "gpt-mini", "gpt-large"]
    assert [call["reasoning_effort"] for call in fake_llm.calls] == ["low", "low", "medium"]


def test_problem_agent_routes_high_rigor_request_to_quality_model():
    fake_llm = FakeLLM([problem_payload(problem_type="short_answer", difficulty="medium")])
    agent = ProblemAgent(
        llm=fake_llm,
        settings=Settings(
            OPENAI_API_KEY="test-key",
            PROBLEM_MODEL="gpt-mini",
            PROBLEM_QUALITY_MODEL="gpt-large",
            PROBLEM_AGENT_COST_PROFILE="full",
            LLM_REASONING_EFFORT_PROBLEM="low",
            LLM_REASONING_EFFORT_PROBLEM_QUALITY="medium",
        ),
    )

    agent.generate(
        request=GenerateProblemRequest(
            document_id="doc_001",
            concepts=["뉴턴 제2법칙"],
            type="short_answer",
            count=1,
            difficulty="medium",
            target_rigor="high",
        ),
        chunks=[retrieved_chunk()],
    )

    assert [call["model"] for call in fake_llm.calls] == ["gpt-large"]
    assert [call["reasoning_effort"] for call in fake_llm.calls] == ["medium"]


def test_problem_agent_keeps_simple_short_answer_on_standard_model():
    fake_llm = FakeLLM([problem_payload(problem_type="short_answer", difficulty="medium")])
    agent = ProblemAgent(
        llm=fake_llm,
        settings=Settings(
            OPENAI_API_KEY="test-key",
            PROBLEM_MODEL="gpt-mini",
            PROBLEM_QUALITY_MODEL="gpt-large",
            PROBLEM_AGENT_COST_PROFILE="full",
            LLM_REASONING_EFFORT_PROBLEM="low",
            LLM_REASONING_EFFORT_PROBLEM_QUALITY="medium",
        ),
    )

    agent.generate(
        request=GenerateProblemRequest(
            document_id="doc_001",
            concepts=["뉴턴 제2법칙"],
            type="short_answer",
            count=1,
            difficulty="medium",
            user_requirements="정의를 짧고 간단한 주관식으로 물어봐줘.",
        ),
        chunks=[retrieved_chunk()],
        source_grounding_profile=SourceGroundingProfile(mode=SourceGroundingMode.source_grounded),
    )

    assert [call["model"] for call in fake_llm.calls] == ["gpt-mini"]
    assert [call["reasoning_effort"] for call in fake_llm.calls] == ["low"]


def test_problem_agent_prompt_allows_contextual_extension_without_subject_specific_mode():
    fake_llm = FakeLLM([problem_payload(problem_type="short_answer", difficulty="hard")])
    agent = ProblemAgent(
        llm=fake_llm,
        settings=Settings(OPENAI_API_KEY="test-key"),
    )

    agent.generate(
        request=GenerateProblemRequest(
            document_id="doc_001",
            concepts=["뉴턴 제2법칙"],
            type="short_answer",
            count=1,
            difficulty="hard",
            bloom_level="analyze",
            user_requirements="평가 대비용으로 새 조건을 만들고 분석하게 해줘.",
        ),
        chunks=[retrieved_chunk()],
        source_grounding_profile=SourceGroundingProfile(
            mode=SourceGroundingMode.model_extension,
            allow_synthetic_context=True,
            allow_external_knowledge=True,
            strict_source_rejection=False,
        ),
    )

    prompt = fake_llm.calls[0]["prompt"]
    assert "source_grounding_policy=model_extension" in prompt
    assert "일반 도메인 지식" in prompt
    assert "context에 없는 개념, 수치, 사례, 외부 지식은 추가하지 마라" not in prompt


def test_problem_agent_routes_ui_style_to_quality_model():
    fake_llm = FakeLLM([problem_payload(problem_type="short_answer", difficulty="medium")])
    agent = ProblemAgent(
        llm=fake_llm,
        settings=Settings(
            OPENAI_API_KEY="test-key",
            PROBLEM_MODEL="gpt-mini",
            PROBLEM_QUALITY_MODEL="gpt-large",
            PROBLEM_AGENT_COST_PROFILE="full",
            LLM_REASONING_EFFORT_PROBLEM="low",
            LLM_REASONING_EFFORT_PROBLEM_QUALITY="medium",
        ),
    )

    agent.generate(
        request=GenerateProblemRequest(
            document_id="doc_001",
            concepts=["뉴턴 제2법칙"],
            type="short_answer",
            count=1,
            difficulty="medium",
            problem_style="calculation_practice",
        ),
        chunks=[retrieved_chunk()],
    )

    assert [call["model"] for call in fake_llm.calls] == ["gpt-large"]
    assert [call["reasoning_effort"] for call in fake_llm.calls] == ["medium"]


def test_high_rigor_prompt_requires_thinking_operations():
    fake_llm = FakeLLM([problem_payload(problem_type="short_answer", difficulty="hard")])
    agent = ProblemAgent(llm=fake_llm, settings=Settings(OPENAI_API_KEY="test-key"))

    agent.generate(
        request=GenerateProblemRequest(
            document_id="doc_001",
            concepts=["뉴턴 제2법칙"],
            type="short_answer",
            count=1,
            difficulty="hard",
            bloom_level="analyze",
        ),
        chunks=[retrieved_chunk()],
    )

    prompt = fake_llm.calls[0]["prompt"]
    assert "고난도 문항은 어려운 단어를 쓰는 것이 아니라" in prompt
    assert "condition_mutation" in prompt
    assert "error_diagnosis" in prompt
    assert "evidence_interpretation" in prompt
    assert "counterexample_or_limitation" in prompt


def test_high_rigor_multiple_choice_prompt_requires_diagnostic_distractors():
    fake_llm = FakeLLM([problem_payload(problem_type="multiple_choice", difficulty="hard")])
    agent = ProblemAgent(llm=fake_llm, settings=Settings(OPENAI_API_KEY="test-key"))

    agent.generate(
        request=GenerateProblemRequest(
            document_id="doc_001",
            concepts=["뉴턴 제2법칙"],
            type="multiple_choice",
            count=1,
            difficulty="hard",
            bloom_level="analyze",
        ),
        chunks=[retrieved_chunk()],
    )

    prompt = fake_llm.calls[0]["prompt"]
    assert "객관식 고난도 문항의 stem" in prompt
    assert "서로 다른 misconception 또는 reasoning failure" in prompt
    assert "choice_diagnostics에는 각 오답이 왜 그럴듯한지" in prompt
    assert "followup_problem_type must be one of these exact short slug values" in prompt
    assert "High-Rigor MCQPlan Contract" in prompt
    assert "mcq_plan must include these fields exactly" in prompt
    assert "distractor_plans must contain exactly 3 entries" in prompt
    assert "required_source_chunk_ids" in prompt
    for slug in FOLLOWUP_PROBLEM_TYPE_SLUGS:
        assert slug in prompt
    assert "다음 중 옳은 것은?" in prompt


def test_choice_diagnostic_followup_problem_type_accepts_slug():
    diagnostic = ChoiceDiagnosticSpec(
        choice_id="B",
        is_correct=False,
        misconception_id="mis_b",
        mistake_type="concept_misunderstanding",
        why_plausible="조건 변화를 놓치면 고를 수 있다.",
        repair_strategy="조건이 바뀔 때 결과를 다시 비교한다.",
        followup_problem_type="condition_change",
    )

    assert diagnostic.followup_problem_type == "condition_change"


def test_choice_diagnostic_followup_problem_type_normalizes_long_text():
    diagnostic = ChoiceDiagnosticSpec(
        choice_id="B",
        is_correct=False,
        misconception_id="mis_b",
        mistake_type="concept_misunderstanding",
        why_plausible="유전체가 빠질 때 전기장 조건을 놓치면 고를 수 있다.",
        repair_strategy="배터리 연결 조건과 유전체 제거 조건을 구분한다.",
        followup_problem_type="condition_mutation 비교 조건을 바꾸어 유전체 제거 상황을 다시 판단하는 후속 문항",
    )

    assert diagnostic.followup_problem_type == "condition_change"


def test_choice_diagnostic_followup_problem_type_rejects_unknown_text():
    with pytest.raises(ValueError, match="followup_problem_type must be one of"):
        ChoiceDiagnosticSpec(
            choice_id="B",
            is_correct=False,
            misconception_id="mis_b",
            mistake_type="concept_misunderstanding",
            why_plausible="보기의 표현만 보고 고를 수 있다.",
            repair_strategy="근거 문장을 다시 확인한다.",
            followup_problem_type="unmapped free-form remediation sentence",
        )


def test_problem_agent_normalizes_dielectric_style_long_followup_problem_type():
    payload = problem_payload(problem_type="multiple_choice", difficulty="hard")
    payload["problems"][0]["choice_diagnostics"][1][
        "followup_problem_type"
    ] = "condition_mutation 비교 조건을 바꾸어 유전체 제거 상황을 다시 판단하는 후속 문항"
    fake_llm = FakeLLM([payload])
    agent = ProblemAgent(llm=fake_llm, settings=Settings(OPENAI_API_KEY="test-key"))

    problems = agent.generate(
        request=GenerateProblemRequest(
            document_id="doc_001",
            concepts=["유전체"],
            type="multiple_choice",
            count=1,
            difficulty="hard",
            bloom_level="analyze",
        ),
        chunks=[retrieved_chunk()],
    )

    assert problems[0]["choice_diagnostics"][1]["followup_problem_type"] == "condition_change"


def test_problem_agent_normalizes_raw_mcq_diagnostic_semantics_before_returning():
    payload = problem_payload(problem_type="multiple_choice", difficulty="hard")
    diagnostics = payload["problems"][0]["choice_diagnostics"]
    diagnostics[0]["mistake_type"] = "logic_error"
    diagnostics[0]["why_plausible"] = "정답도 오류 진단처럼 잘못 작성되었다."
    diagnostics[0]["repair_strategy"] = "정답 보정"
    diagnostics[0]["followup_problem_type"] = "error_diagnosis"
    for diagnostic in diagnostics[1:]:
        diagnostic["mistake_type"] = "none"
        diagnostic["misconception_id"] = None
        diagnostic["why_plausible"] = None
        diagnostic["repair_strategy"] = None
        diagnostic["followup_problem_type"] = None
    fake_llm = FakeLLM([payload])
    agent = ProblemAgent(llm=fake_llm, settings=Settings(OPENAI_API_KEY="test-key"))

    problems = agent.generate(
        request=GenerateProblemRequest(
            document_id="doc_001",
            concepts=["heap destructor"],
            type="multiple_choice",
            count=1,
            difficulty="hard",
            bloom_level="analyze",
        ),
        chunks=[retrieved_chunk()],
    )

    normalized = problems[0]["choice_diagnostics"]
    assert normalized[0]["is_correct"] is True
    assert normalized[0]["mistake_type"] == "none"
    assert normalized[0]["why_plausible"] is None
    for diagnostic in normalized[1:]:
        assert diagnostic["is_correct"] is False
        assert diagnostic["mistake_type"] != "none"
        assert diagnostic["misconception_id"]
        assert diagnostic["why_plausible"]
        assert diagnostic["repair_strategy"]
        ChoiceDiagnosticSpec.model_validate(diagnostic)


def test_problem_agent_fills_missing_choice_diagnostic():
    payload = problem_payload(problem_type="multiple_choice", difficulty="hard")
    payload["problems"][0]["choice_diagnostics"] = payload["problems"][0]["choice_diagnostics"][:3]
    fake_llm = FakeLLM([payload])
    agent = ProblemAgent(llm=fake_llm, settings=Settings(OPENAI_API_KEY="test-key"))

    problems = agent.generate(
        request=GenerateProblemRequest(
            document_id="doc_001",
            concepts=["뉴턴 제2법칙"],
            type="multiple_choice",
            count=1,
            difficulty="hard",
            bloom_level="analyze",
        ),
        chunks=[retrieved_chunk()],
    )

    assert {diagnostic["choice_id"] for diagnostic in problems[0]["choice_diagnostics"]} == {"A", "B", "C", "D"}
    ChoiceDiagnosticSpec.model_validate(problems[0]["choice_diagnostics"][3])


def test_problem_agent_deduplicates_choice_diagnostics_and_keeps_informative_one():
    payload = problem_payload(problem_type="multiple_choice", difficulty="hard")
    payload["problems"][0]["choice_diagnostics"] = [
        payload["problems"][0]["choice_diagnostics"][0],
        {
            "choice_id": "B",
            "is_correct": False,
            "misconception_id": None,
            "mistake_type": "none",
            "why_plausible": None,
            "repair_strategy": None,
            "followup_problem_type": None,
        },
        {
            "choice_id": "B",
            "is_correct": False,
            "misconception_id": "specific_b",
            "mistake_type": "term_confusion",
            "why_plausible": "질량과 힘의 용어를 혼동하면 고를 수 있다.",
            "repair_strategy": "식의 각 항이 무엇을 뜻하는지 구분한다.",
            "followup_problem_type": "comparison_drill",
        },
    ]
    fake_llm = FakeLLM([payload])
    agent = ProblemAgent(llm=fake_llm, settings=Settings(OPENAI_API_KEY="test-key"))

    problems = agent.generate(
        request=GenerateProblemRequest(
            document_id="doc_001",
            concepts=["뉴턴 제2법칙"],
            type="multiple_choice",
            count=1,
            difficulty="hard",
            bloom_level="analyze",
        ),
        chunks=[retrieved_chunk()],
    )

    by_id = {diagnostic["choice_id"]: diagnostic for diagnostic in problems[0]["choice_diagnostics"]}
    assert by_id["B"]["misconception_id"] == "specific_b"
    assert by_id["B"]["mistake_type"] == "term_confusion"
    assert set(by_id) == {"A", "B", "C", "D"}


def test_problem_agent_uses_mcq_plan_when_raw_diagnostics_are_weak():
    payload = problem_payload(problem_type="multiple_choice", difficulty="hard")
    payload["problems"][0]["mcq_plan"] = {
        "kernel_type": "diagnose_error",
        "source_rule_or_evidence": "A destructor must release heap memory exactly once.",
        "concrete_scenario": "A class owns a heap pointer and copies it incorrectly.",
        "correct_answer_claim": "The flawed option double-deletes the heap pointer.",
        "correct_answer_evidence_link": "chunk_001",
        "distractor_plans": [
            {
                "misconception_id": "plan_b",
                "mistake_type": "logic_error",
                "why_plausible": "It confuses ownership transfer with deletion order.",
                "violated_or_ignored_evidence_role": "rule",
                "repair_strategy": "Trace which object owns the pointer before deletion.",
            },
            {
                "misconception_id": "plan_c",
                "mistake_type": "term_confusion",
                "why_plausible": "It treats stack and heap lifetime as the same.",
                "violated_or_ignored_evidence_role": "definition",
                "repair_strategy": "Separate automatic storage from heap allocation.",
            },
            {
                "misconception_id": "plan_d",
                "mistake_type": "misread_question",
                "why_plausible": "It ignores the question's copy step.",
                "violated_or_ignored_evidence_role": "condition",
                "repair_strategy": "Underline the copy operation before judging deletion.",
            },
        ],
        "prohibited_patterns": [],
        "required_source_chunk_ids": ["chunk_001"],
    }
    for diagnostic in payload["problems"][0]["choice_diagnostics"][1:]:
        diagnostic["mistake_type"] = "none"
        diagnostic["why_plausible"] = None
        diagnostic["repair_strategy"] = None
    fake_llm = FakeLLM([payload])
    agent = ProblemAgent(llm=fake_llm, settings=Settings(OPENAI_API_KEY="test-key"))

    problems = agent.generate(
        request=GenerateProblemRequest(
            document_id="doc_001",
            concepts=["heap destructor"],
            type="multiple_choice",
            count=1,
            difficulty="hard",
            bloom_level="analyze",
        ),
        chunks=[retrieved_chunk()],
    )

    by_id = {diagnostic["choice_id"]: diagnostic for diagnostic in problems[0]["choice_diagnostics"]}
    assert by_id["B"]["misconception_id"] == "plan_b"
    assert by_id["C"]["mistake_type"] == "term_confusion"
    assert by_id["D"]["repair_strategy"] == "Underline the copy operation before judging deletion."


def test_problem_agent_keeps_short_answer_choice_diagnostics_null():
    fake_llm = FakeLLM([problem_payload(problem_type="short_answer", difficulty="hard")])
    agent = ProblemAgent(llm=fake_llm, settings=Settings(OPENAI_API_KEY="test-key"))

    problems = agent.generate(
        request=GenerateProblemRequest(
            document_id="doc_001",
            concepts=["뉴턴 제2법칙"],
            type="short_answer",
            count=1,
            difficulty="hard",
            bloom_level="analyze",
        ),
        chunks=[retrieved_chunk()],
    )

    assert problems[0]["choice_diagnostics"] is None


def test_high_rigor_multiple_choice_prompt_includes_evidence_analysis_template():
    fake_llm = FakeLLM([problem_payload(problem_type="multiple_choice", difficulty="hard")])
    agent = ProblemAgent(llm=fake_llm, settings=Settings(OPENAI_API_KEY="test-key"))

    agent.generate(
        request=GenerateProblemRequest(
            document_id="doc_001",
            concepts=["Concept A"],
            type="multiple_choice",
            count=1,
            difficulty="hard",
            bloom_level="analyze",
            problem_style="evidence_analysis",
        ),
        chunks=[retrieved_chunk()],
    )

    prompt = fake_llm.calls[0]["prompt"]
    assert "고난도 객관식 구조 템플릿" in prompt
    assert "evidence_analysis 구조" in prompt
    assert "자료의 설명 R과 조건 X를 바탕으로 할 때, claim C" in prompt
    assert "ignores_condition_x" in prompt


def test_high_rigor_multiple_choice_prompt_includes_error_detection_template():
    fake_llm = FakeLLM([problem_payload(problem_type="multiple_choice", difficulty="hard")])
    agent = ProblemAgent(llm=fake_llm, settings=Settings(OPENAI_API_KEY="test-key"))

    agent.generate(
        request=GenerateProblemRequest(
            document_id="doc_001",
            concepts=["Concept A"],
            type="multiple_choice",
            count=1,
            difficulty="hard",
            problem_style="error_detection",
        ),
        chunks=[retrieved_chunk()],
    )

    prompt = fake_llm.calls[0]["prompt"]
    assert "error_detection 구조" in prompt
    assert "source rule R을 적용하는 과정에서 오류" in prompt
    assert "flawed step을 정확히 찾고" in prompt


def test_high_rigor_multiple_choice_prompt_includes_template_anti_patterns():
    fake_llm = FakeLLM([problem_payload(problem_type="multiple_choice", difficulty="hard")])
    agent = ProblemAgent(llm=fake_llm, settings=Settings(OPENAI_API_KEY="test-key"))

    agent.generate(
        request=GenerateProblemRequest(
            document_id="doc_001",
            concepts=["Concept A"],
            type="multiple_choice",
            count=1,
            target_rigor="high",
        ),
        chunks=[retrieved_chunk()],
    )

    prompt = fake_llm.calls[0]["prompt"]
    assert "고난도 객관식 anti-pattern" in prompt
    assert '"다음 중 옳은 것은?"만 묻지 마라' in prompt
    assert "모든 distractor가 같은 misconception을 반복" in prompt
    assert "source 문장 하나를 그대로 복사해서" in prompt


def test_short_answer_prompt_does_not_include_high_rigor_mcq_template_examples():
    fake_llm = FakeLLM([problem_payload(problem_type="short_answer", difficulty="hard")])
    agent = ProblemAgent(llm=fake_llm, settings=Settings(OPENAI_API_KEY="test-key"))

    agent.generate(
        request=GenerateProblemRequest(
            document_id="doc_001",
            concepts=["뉴턴 제2법칙"],
            type="short_answer",
            count=1,
            difficulty="hard",
            bloom_level="analyze",
        ),
        chunks=[retrieved_chunk()],
    )

    prompt = fake_llm.calls[0]["prompt"]
    assert "고난도 객관식 구조 템플릿" not in prompt
    assert "evidence_analysis 구조" not in prompt


def test_normal_medium_multiple_choice_prompt_does_not_include_high_rigor_mcq_template_examples():
    fake_llm = FakeLLM([problem_payload(problem_type="multiple_choice", difficulty="medium")])
    agent = ProblemAgent(llm=fake_llm, settings=Settings(OPENAI_API_KEY="test-key"))

    agent.generate(
        request=GenerateProblemRequest(
            document_id="doc_001",
            concepts=["뉴턴 제2법칙"],
            type="multiple_choice",
            count=1,
            difficulty="medium",
            bloom_level="understand",
        ),
        chunks=[retrieved_chunk()],
    )

    prompt = fake_llm.calls[0]["prompt"]
    assert "고난도 객관식 구조 템플릿" not in prompt
    assert "condition_mutation 구조" not in prompt


def test_compressed_prompt_is_shorter_and_keeps_evidence_contract():
    request = GenerateProblemRequest(
        document_id="doc_001",
        concepts=["capacitance"],
        type="short_answer",
        count=1,
        difficulty="hard",
        problem_style="calculation_practice",
        target_rigor="high",
        quality_mode="strict",
    )
    long_context = "Capacitance rule: C_eq = C1 + C2 for parallel capacitors. " * 80
    chunks = [retrieved_chunk(chunk_id="chunk_formula", content=long_context)]
    atom = ContentAtom(
        atom_id="atom_formula",
        atom_type=ContentAtomType.formula,
        source_chunk_id="chunk_formula",
        statement="C_eq = C1 + C2 for parallel capacitors.",
        evidence_quote="C_eq = C1 + C2",
        concepts=["capacitance"],
        confidence=0.95,
    )
    plan = ProblemKernelPlan(
        kernel_type=ProblemKernelType.compute_from_given,
        content_atom_ids=["atom_formula"],
        target_cognitive_level="analyze",
        required_evidence_roles=[EvidenceObligation(role=EvidenceRole.formula, must_appear_in=["explanation"])],
        allows_generated_scenario_values=True,
        requires_derivation_check=True,
    )

    compressed_agent = ProblemAgent(
        settings=Settings(OPENAI_API_KEY=None, PROBLEM_AGENT_PROMPT_COMPRESSION_ENABLED=True)
    )
    uncompressed_agent = ProblemAgent(
        settings=Settings(OPENAI_API_KEY=None, PROBLEM_AGENT_PROMPT_COMPRESSION_ENABLED=False)
    )

    compressed_prompt = compressed_agent._build_prompt(request, chunks, content_atoms=[atom], problem_kernel_plan=plan)
    uncompressed_prompt = uncompressed_agent._build_prompt(request, chunks, content_atoms=[atom], problem_kernel_plan=plan)

    assert len(compressed_prompt) < len(uncompressed_prompt)
    assert "EvidencePack JSON" in compressed_prompt
    assert "Evidence Contract" in compressed_prompt
    assert "source_chunk_ids" in compressed_prompt
    assert "chunk_formula" in compressed_prompt
    assert "atom_formula" in compressed_prompt
    assert compressed_agent.last_compressed_prompt_enabled is True
    assert compressed_agent.last_evidence_pack_atom_count == 1
    assert compressed_agent.last_raw_context_char_count == len(long_context)


def test_evidence_pack_includes_selected_atom_source_chunk_ids():
    agent = ProblemAgent(settings=Settings(OPENAI_API_KEY=None))
    chunk = retrieved_chunk(chunk_id="chunk_rule", content="If memory is allocated on the heap, it must be released.")
    atom = ContentAtom(
        atom_id="atom_rule",
        atom_type=ContentAtomType.rule,
        source_chunk_id="chunk_rule",
        statement="Heap allocations must be released.",
        evidence_quote="must be released",
        concepts=["heap"],
        confidence=0.9,
    )
    plan = ProblemKernelPlan(
        kernel_type=ProblemKernelType.diagnose_error,
        content_atom_ids=["atom_rule"],
        target_cognitive_level="analyze",
        required_evidence_roles=[EvidenceObligation(role=EvidenceRole.rule, must_appear_in=["explanation"])],
    )

    pack = agent._build_evidence_pack(content_atoms=[atom], problem_kernel_plan=plan, chunks=[chunk])

    assert [pack_atom.source_chunk_id for pack_atom in pack.selected_atoms] == ["chunk_rule"]
    assert pack.source_chunk_id_whitelist[0] == "chunk_rule"
    assert pack.selected_atoms[0].roles == ["rule"]


def test_cheap_profile_omits_mcq_fewshot_templates_but_full_includes_compact_template():
    request = GenerateProblemRequest(
        document_id="doc_001",
        concepts=["heap"],
        type="multiple_choice",
        count=1,
        difficulty="hard",
        problem_style="error_detection",
        target_rigor="high",
    )
    chunk = retrieved_chunk(chunk_id="chunk_rule", content="If memory is allocated on the heap, it must be released.")
    atom = ContentAtom(
        atom_id="atom_rule",
        atom_type=ContentAtomType.rule,
        source_chunk_id="chunk_rule",
        statement="Heap allocations must be released.",
        evidence_quote="must be released",
        concepts=["heap"],
        confidence=0.9,
    )
    plan = ProblemKernelPlan(
        kernel_type=ProblemKernelType.diagnose_error,
        content_atom_ids=["atom_rule"],
        target_cognitive_level="analyze",
        required_evidence_roles=[EvidenceObligation(role=EvidenceRole.rule, must_appear_in=["explanation"])],
        requires_distinct_distractors=True,
    )

    cheap_prompt = ProblemAgent(
        settings=Settings(OPENAI_API_KEY=None, PROBLEM_AGENT_COST_PROFILE="cheap")
    )._build_prompt(request, [chunk], content_atoms=[atom], problem_kernel_plan=plan, cost_profile="cheap")
    full_prompt = ProblemAgent(
        settings=Settings(OPENAI_API_KEY=None, PROBLEM_AGENT_COST_PROFILE="full")
    )._build_prompt(request, [chunk], content_atoms=[atom], problem_kernel_plan=plan, cost_profile="full")

    assert "High-Rigor MCQPlan Contract" in cheap_prompt
    assert "고난도 객관식 compact template" not in cheap_prompt
    assert "omitted for this cost profile/request" in cheap_prompt
    assert "고난도 객관식 compact template" in full_prompt


def test_stable_policy_prefix_excludes_dynamic_request_payload():
    agent = ProblemAgent(settings=Settings(OPENAI_API_KEY=None))

    prefix = agent._stable_policy_prefix("cheap")

    assert "Request JSON" not in prefix
    assert "doc_001" not in prefix
    assert "뉴턴 제2법칙" not in prefix
    assert "cost_profile=cheap" in prefix


def test_repair_prompt_includes_invalid_candidate_and_concise_errors():
    request = GenerateProblemRequest(
        document_id="doc_001",
        concepts=["heap"],
        type="multiple_choice",
        count=1,
        difficulty="hard",
        problem_style="error_detection",
        target_rigor="high",
    )
    chunk = retrieved_chunk(chunk_id="chunk_rule", content="If memory is allocated on the heap, it must be released.")
    atom = ContentAtom(
        atom_id="atom_rule",
        atom_type=ContentAtomType.rule,
        source_chunk_id="chunk_rule",
        statement="Heap allocations must be released.",
        evidence_quote="must be released",
        concepts=["heap"],
        confidence=0.9,
    )
    plan = ProblemKernelPlan(
        kernel_type=ProblemKernelType.diagnose_error,
        content_atom_ids=["atom_rule"],
        target_cognitive_level="analyze",
        required_evidence_roles=[EvidenceObligation(role=EvidenceRole.rule, must_appear_in=["explanation"])],
        requires_distinct_distractors=True,
    )
    invalid_candidate = {
        "question": "Which answer is correct?",
        "source_chunk_ids": [],
        "mcq_plan": None,
    }

    prompt = ProblemAgent(settings=Settings(OPENAI_API_KEY=None))._build_repair_prompt(
        request=request,
        invalid_candidate=invalid_candidate,
        validation_errors=["missing_mcq_plan", "missing_source_evidence", "missing_source_evidence"],
        chunks=[chunk],
        learning_task_strategy=None,
        material_readiness=None,
        blueprint=None,
        high_rigor_profile=None,
        source_grounding_profile=None,
        content_atoms=[atom],
        problem_kernel_plan=plan,
        cost_profile="balanced",
    )

    assert "Repair exactly one invalid candidate" in prompt
    assert "Invalid candidate JSON" in prompt
    assert "Which answer is correct?" in prompt
    assert "missing_mcq_plan" in prompt
    assert "EvidencePack JSON" in prompt
    assert "chunk_rule" in prompt
    assert "Return only schema-valid JSON with one problem" in prompt


def test_calculation_practice_prompt_warns_against_number_only_variants():
    fake_llm = FakeLLM([problem_payload(problem_type="short_answer", difficulty="medium")])
    agent = ProblemAgent(llm=fake_llm, settings=Settings(OPENAI_API_KEY="test-key"))

    agent.generate(
        request=GenerateProblemRequest(
            document_id="doc_001",
            concepts=["뉴턴 제2법칙"],
            type="short_answer",
            count=1,
            problem_style="calculation_practice",
        ),
        chunks=[retrieved_chunk()],
    )

    prompt = fake_llm.calls[0]["prompt"]
    assert "calculation_practice는 자료에 공식/변수 관계가 있을 때만 계산을 요구한다" in prompt
    assert "공식 대입만 가능한 자료라도 단위 확인" in prompt
    assert "숫자, 변수명, 순서만 바꾼 후보" in prompt
    assert "공식/변수 관계가 없으면 계산을 억지로 만들지 말고" in prompt


def test_error_detection_prompt_requires_flawed_claim_and_correction():
    fake_llm = FakeLLM([problem_payload(problem_type="multiple_choice", difficulty="medium")])
    agent = ProblemAgent(llm=fake_llm, settings=Settings(OPENAI_API_KEY="test-key"))

    agent.generate(
        request=GenerateProblemRequest(
            document_id="doc_001",
            concepts=["뉴턴 제2법칙"],
            type="multiple_choice",
            count=1,
            problem_style="error_detection",
        ),
        chunks=[retrieved_chunk()],
    )

    prompt = fake_llm.calls[0]["prompt"]
    assert "error_detection은 flawed claim" in prompt
    assert "학생에게 오류를 찾고 고치게" in prompt
    assert "서로 다른 잘못된 진단" in prompt


def test_high_rigor_prompt_contains_cs_related_operation_guidance():
    fake_llm = FakeLLM([problem_payload(problem_type="short_answer", difficulty="hard")])
    agent = ProblemAgent(llm=fake_llm, settings=Settings(OPENAI_API_KEY="test-key"))

    agent.generate(
        request=GenerateProblemRequest(
            document_id="doc_001",
            concepts=["heapsort"],
            type="short_answer",
            count=1,
            difficulty="hard",
            bloom_level="analyze",
        ),
        chunks=[
            retrieved_chunk(
                content=(
                    "Heapsort is an algorithm. Build-Max-Heap runs Max-Heapify and its "
                    "time complexity is O(n)."
                )
            )
        ],
    )

    prompt = fake_llm.calls[0]["prompt"]
    assert "CS-like 자료 규칙" in prompt
    assert "trace_and_explain" in prompt
    assert "complexity reasoning" in prompt
    assert "state transition" in prompt
    assert "순수 정의 대신" not in prompt


def test_problem_agent_passes_preserved_rag_images_to_llm():
    fake_llm = FakeLLM([problem_payload()])
    agent = ProblemAgent(
        llm=fake_llm,
        settings=Settings(OPENAI_API_KEY="test-key"),
    )

    agent.generate(
        request=GenerateProblemRequest(
            document_id="doc_001",
            concepts=["힙 정렬"],
            type="multiple_choice",
            count=1,
            user_requirements="그림 기반 문제를 만들어줘",
        ),
        chunks=[
            retrieved_chunk(
                chunk_id="chunk_heap",
                content="힙 정렬은 max heap을 이용한다.",
                metadata={
                    "image_available": True,
                    "image": "iVBORw0KGgoAAAANSUhEUgAA",
                },
            )
        ],
    )

    call = fake_llm.calls[0]
    assert call["image_inputs"] == [
        {
            "label": "뉴턴의 운동 법칙",
            "chunk_id": "chunk_heap",
            "page": 12,
            "image": "iVBORw0KGgoAAAANSUhEUgAA",
            "detail": "low",
        }
    ]
    assert "visual_source: attached image is available" in call["prompt"]
    assert "그림을 보고" in call["prompt"]


def test_problem_agent_adds_compact_json_rules_for_gemini_provider():
    fake_llm = FakeLLM([problem_payload(problem_type="short_answer")])
    agent = ProblemAgent(
        llm=fake_llm,
        settings=Settings(LLM_PROVIDER="gemini", GEMINI_API_KEY="gemini-key"),
    )

    agent.generate(
        request=GenerateProblemRequest(
            document_id="doc_001",
            concepts=["힙 정렬"],
            type="short_answer",
            count=1,
            difficulty="hard",
        ),
        chunks=[retrieved_chunk()],
    )

    prompt = fake_llm.calls[0]["prompt"]
    assert "JSON 문자열 안에 실제 줄바꿈을 넣지 말고" in prompt
    assert "350자 이내" in prompt
    assert "rubric.expected_evidence의 문구를 answer.text 안에 글자 그대로 포함" in prompt
    assert "rubric.common_mistakes를 빈 배열 []로 둬라" in prompt


def test_problem_agent_does_not_pass_images_when_payload_was_not_preserved():
    fake_llm = FakeLLM([problem_payload()])
    agent = ProblemAgent(
        llm=fake_llm,
        settings=Settings(OPENAI_API_KEY="test-key"),
    )

    agent.generate(
        request=GenerateProblemRequest(
            document_id="doc_001",
            concepts=["힙 정렬"],
            type="multiple_choice",
            count=1,
        ),
        chunks=[
            retrieved_chunk(
                metadata={
                    "image_available": True,
                    "image_omitted": "text_only",
                }
            )
        ],
    )

    assert fake_llm.calls[0]["image_inputs"] is None


def test_problem_agent_rejects_invalid_llm_schema():
    payload = problem_payload()
    payload["problems"][0]["answer"]["extra"] = "not allowed"
    agent = ProblemAgent(llm=FakeLLM([payload]), settings=Settings(OPENAI_API_KEY="test-key"))

    with pytest.raises(LLMOutputValidationError):
        agent.generate(
            request=GenerateProblemRequest(
                document_id="doc_001",
                concepts=["뉴턴 제2법칙"],
                type="multiple_choice",
                count=1,
            ),
            chunks=[retrieved_chunk()],
        )


def test_problem_agent_rejects_missing_api_key_when_fallback_disabled():
    agent = ProblemAgent(
        llm=FakeLLM([], available=False),
        settings=Settings(OPENAI_API_KEY=None, LLM_FALLBACK_ENABLED=False),
    )

    with pytest.raises(LLMServiceError):
        agent.generate(
            request=GenerateProblemRequest(
                document_id="doc_001",
                concepts=["뉴턴 제2법칙"],
                type="multiple_choice",
                count=1,
            ),
            chunks=[retrieved_chunk()],
        )


def test_feedback_agent_rejects_invalid_llm_schema():
    fake_llm = FakeLLM(
        [
            {
                "is_correct": False,
                "score": 2,
                "max_score": 1,
                "mistake_type": "none",
                "weak_concepts": ["뉴턴 제2법칙"],
                "summary": "점수가 max_score를 넘는다.",
                "feedback": "schema validation에서 거부되어야 한다.",
                "recommended_review": ["뉴턴 제2법칙"],
            }
        ]
    )
    agent = FeedbackAgent(llm=fake_llm, settings=Settings(OPENAI_API_KEY="test-key"))

    with pytest.raises(LLMOutputValidationError):
        agent.grade_short_answer(problem=short_answer_problem(), submission=submission(), chunks=[retrieved_chunk()])


def test_feedback_agent_preserves_structured_llm_feedback():
    structured_feedback = (
        "정답 여부: 아직 정답은 아니야.\n"
        "헷갈린 지점: 핵심 개념이 부족해.\n"
        "올바른 개념: F = ma를 기준으로 설명해야 해.\n"
        "복습 추천: 뉴턴 제2법칙"
    )
    fake_llm = FakeLLM(
        [
            {
                "is_correct": False,
                "score": 0,
                "max_score": 2,
                "mistake_type": "missing_key_concept",
                "weak_concepts": ["뉴턴 제2법칙"],
                "summary": "핵심 개념이 부족해.",
                "feedback": structured_feedback,
                "recommended_review": ["뉴턴 제2법칙"],
                "rubric_results": [
                    {
                        "criterion": "F = ma의 의미를 설명한다.",
                        "max_points": 2,
                        "awarded_points": 0,
                        "matched": False,
                        "evidence_from_answer": None,
                        "missing_point": "F = ma의 의미가 빠졌다.",
                        "next_action": "F = ma를 한 문장으로 다시 써보기",
                        "confidence": "high",
                    }
                ],
                "confidence": "high",
            }
        ]
    )
    agent = FeedbackAgent(llm=fake_llm, settings=Settings(OPENAI_API_KEY="test-key"))

    feedback = agent.grade_short_answer(problem=short_answer_problem(), submission=submission(), chunks=[retrieved_chunk()])

    assert feedback["feedback"] == structured_feedback


def test_feedback_agent_rejects_short_answer_max_score_that_differs_from_rubric():
    fake_llm = FakeLLM(
        [
            {
                "is_correct": False,
                "score": 1,
                "max_score": 10,
                "mistake_type": "incomplete_answer",
                "weak_concepts": ["뉴턴 제2법칙"],
                "summary": "점수 기준이 rubric과 다르다.",
                "feedback": (
                    "정답 여부: 아직 정답은 아니야.\n"
                    "헷갈린 지점: 기준 점수가 달라.\n"
                    "올바른 개념: rubric 총점과 맞아야 해.\n"
                    "복습 추천: 뉴턴 제2법칙"
                ),
                "recommended_review": ["뉴턴 제2법칙"],
                "rubric_results": [
                    {
                        "criterion": "F = ma의 의미를 설명한다.",
                        "max_points": 2,
                        "awarded_points": 1,
                        "matched": True,
                        "evidence_from_answer": "힘과 질량의 관계를 설명한다.",
                        "missing_point": None,
                        "next_action": None,
                        "confidence": "medium",
                    }
                ],
                "confidence": "medium",
            }
        ]
    )
    agent = FeedbackAgent(llm=fake_llm, settings=Settings(OPENAI_API_KEY="test-key"))

    with pytest.raises(LLMOutputValidationError, match="rubric total points"):
        agent.grade_short_answer(problem=short_answer_problem(), submission=submission(), chunks=[retrieved_chunk()])


def test_feedback_agent_rejects_short_answer_rubric_result_criterion_mismatch():
    payload = feedback_payload(is_correct=False)
    payload["rubric_results"][0]["criterion"] = "다른 기준으로 채점한다."
    fake_llm = FakeLLM([payload])
    agent = FeedbackAgent(llm=fake_llm, settings=Settings(OPENAI_API_KEY="test-key"))

    with pytest.raises(LLMOutputValidationError, match="criterion must match rubric criterion"):
        agent.grade_short_answer(problem=short_answer_problem(), submission=submission(), chunks=[retrieved_chunk()])


def test_feedback_agent_uses_quality_model_only_for_risky_short_answer_grading():
    payloads = [feedback_payload(is_correct=False), feedback_payload(is_correct=False)]
    fake_llm = FakeLLM(payloads)
    agent = FeedbackAgent(
        llm=fake_llm,
        settings=Settings(
            OPENAI_API_KEY="test-key",
            GRADING_MODEL="gpt-cheap",
            GRADING_QUALITY_MODEL="gpt-quality",
        ),
    )
    normal_problem = short_answer_problem()
    hard_problem = short_answer_problem()
    hard_problem.difficulty = "hard"

    agent.grade_short_answer(problem=normal_problem, submission=submission(), chunks=[retrieved_chunk()])
    agent.grade_short_answer(problem=hard_problem, submission=submission(), chunks=[retrieved_chunk()])

    assert [call["model"] for call in fake_llm.calls] == ["gpt-cheap", "gpt-quality"]
    assert all(call["max_output_tokens"] for call in fake_llm.calls)
    assert all(call["reasoning_effort"] == "low" for call in fake_llm.calls)


def feedback_payload(*, is_correct: bool):
    return {
        "is_correct": is_correct,
        "score": 2 if is_correct else 1,
        "max_score": 2,
        "mistake_type": "none" if is_correct else "incomplete_answer",
        "weak_concepts": [] if is_correct else ["뉴턴 제2법칙"],
        "summary": "채점 결과",
        "feedback": (
            "정답 여부: 정답이야.\n"
            if is_correct
            else "정답 여부: 아직 정답은 아니야.\n"
        )
        + "헷갈린 지점: 핵심 설명을 확인해.\n"
        + "올바른 개념: F = ma를 기준으로 설명해야 해.\n"
        + "복습 추천: 뉴턴 제2법칙",
        "recommended_review": [] if is_correct else ["뉴턴 제2법칙"],
        "rubric_results": [
            {
                "criterion": "F = ma의 의미를 설명한다.",
                "max_points": 2,
                "awarded_points": 2 if is_correct else 1,
                "matched": True,
                "evidence_from_answer": "힘과 질량의 관계를 설명한다.",
                "missing_point": None,
                "next_action": None,
                "confidence": "high" if is_correct else "medium",
            }
        ],
        "confidence": "high" if is_correct else "medium",
    }


def retrieved_chunk(
    *,
    chunk_id="chunk_001",
    content="뉴턴의 제2법칙은 F = ma이다.",
    metadata=None,
):
    return RetrievedChunk(
        chunk_id=chunk_id,
        document_id="doc_001",
        content=content,
        page=12,
        section_title="뉴턴의 운동 법칙",
        concepts=["뉴턴 제2법칙"],
        metadata=metadata or {},
    )


def problem_payload(*, problem_type="multiple_choice", difficulty="medium"):
    problem = {
        "document_id": "doc_001",
        "type": problem_type,
        "difficulty": difficulty,
        "bloom_level": "understand",
        "question": "뉴턴의 제2법칙에 대한 설명으로 맞는 것은?",
        "concepts": ["뉴턴 제2법칙"],
        "source_chunk_ids": ["chunk_001"],
    }
    if problem_type == "multiple_choice":
        problem.update(
            {
                "choices": [
                    {"id": "A", "text": "힘은 질량과 가속도의 곱이다."},
                    {"id": "B", "text": "힘은 질량과 무관하다."},
                    {"id": "C", "text": "가속도는 항상 0이다."},
                    {"id": "D", "text": "질량이 클수록 같은 힘에서 가속도는 커진다."},
                ],
                "answer": {"choice_id": "A", "text": "힘은 질량과 가속도의 곱이다."},
                "explanation": "자료에 F = ma라고 제시되어 있다.",
                "choice_explanations": {
                    "A": "자료 내용과 일치한다.",
                    "B": "질량은 식에 포함된다.",
                    "C": "자료에 없는 설명이다.",
                    "D": "같은 힘에서는 질량이 클수록 가속도가 작다.",
                },
                "choice_diagnostics": [
                    {
                        "choice_id": "A",
                        "is_correct": True,
                        "misconception_id": None,
                        "mistake_type": "none",
                        "why_plausible": None,
                        "repair_strategy": None,
                        "followup_problem_type": None,
                    },
                    {
                        "choice_id": "B",
                        "is_correct": False,
                        "misconception_id": "mis_newton_b",
                        "mistake_type": "concept_misunderstanding",
                        "why_plausible": "질량을 힘의 관계에서 제외하면 고를 수 있다.",
                        "repair_strategy": "$F = ma$에서 질량이 포함된다는 점을 다시 확인한다.",
                        "followup_problem_type": "misconception_contrast",
                    },
                    {
                        "choice_id": "C",
                        "is_correct": False,
                        "misconception_id": "mis_newton_c",
                        "mistake_type": "concept_misunderstanding",
                        "why_plausible": "가속도를 항상 0으로 보면 고를 수 있다.",
                        "repair_strategy": "힘이 작용할 때 가속도가 생길 수 있음을 확인한다.",
                        "followup_problem_type": "misconception_contrast",
                    },
                    {
                        "choice_id": "D",
                        "is_correct": False,
                        "misconception_id": "mis_newton_d",
                        "mistake_type": "concept_misunderstanding",
                        "why_plausible": "질량과 가속도의 관계를 반대로 보면 고를 수 있다.",
                        "repair_strategy": "같은 힘에서 질량이 커질 때 가속도 변화를 비교한다.",
                        "followup_problem_type": "misconception_contrast",
                    },
                ],
                "rubric": None,
            }
        )
    else:
        problem.update(
            {
                "choices": None,
                "answer": {"choice_id": None, "text": "뉴턴의 제2법칙은 힘이 질량과 가속도의 곱이라는 법칙이다."},
                "explanation": "자료에 F = ma라고 제시되어 있다.",
                "choice_explanations": None,
                "choice_diagnostics": None,
                "rubric": [{"criterion": "F = ma의 의미를 설명한다.", "points": 2}],
            }
        )
    return {"problems": [problem]}


def short_answer_problem():
    return Problem(
        id="prob_001",
        user_id="user_001",
        document_id="doc_001",
        type="short_answer",
        difficulty="medium",
        bloom_level="understand",
        question="뉴턴의 제2법칙을 설명해줘.",
        choices=None,
        answer={"choice_id": None, "text": "힘은 질량과 가속도의 곱이다."},
        explanation="F = ma를 설명하면 된다.",
        choice_explanations=None,
        rubric=[{"criterion": "F = ma의 의미를 설명한다.", "points": 2}],
        concepts=["뉴턴 제2법칙"],
        source_chunk_ids=["chunk_001"],
        quality_status="passed",
    )


def submission():
    return Submission(
        id="sub_001",
        problem_id="prob_001",
        user_id="user_001",
        answer={"text": "힘과 질량의 관계를 설명한다."},
        solution_steps=None,
    )
