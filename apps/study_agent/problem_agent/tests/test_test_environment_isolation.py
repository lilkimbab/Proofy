import os

import pytest

from app.config import Settings, get_settings


def test_non_live_tests_do_not_use_real_llm_or_rag_env():
    settings = Settings()

    assert os.getenv("OPENAI_API_KEY") == ""
    assert os.getenv("GEMINI_API_KEY") == ""
    assert os.getenv("RAG_AGENT_URL") == ""
    assert os.getenv("SEARCH_AGENT_URL") == ""
    assert settings.openai_api_key in {None, ""}
    assert settings.gemini_api_key in {None, ""}
    assert settings.rag_agent_url in {None, ""}
    assert settings.search_agent_url in {None, ""}


def test_non_live_tests_enable_deterministic_fallback_and_disable_external_publish():
    settings = Settings()

    assert settings.llm_fallback_enabled is True
    assert settings.demo_search_enabled is False
    assert settings.generated_artifact_publish_enabled is False
    assert settings.generated_artifact_index_url in {None, ""}
    assert settings.generated_artifact_add_url in {None, ""}


def test_get_settings_cache_starts_each_non_live_test_with_isolated_env(monkeypatch):
    assert get_settings().openai_api_key in {None, ""}

    monkeypatch.setenv("OPENAI_API_KEY", "fake-real-key")
    get_settings.cache_clear()

    assert get_settings().openai_api_key == "fake-real-key"


def test_get_settings_cache_does_not_retain_previous_api_key_value():
    assert get_settings().openai_api_key in {None, ""}


@pytest.mark.llm
def test_llm_marked_tests_are_detected_as_live(request):
    from tests.conftest import _is_live_test

    assert _is_live_test(request.node) is True
