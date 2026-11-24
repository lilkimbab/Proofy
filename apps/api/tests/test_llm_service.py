from __future__ import annotations

import threading
import time
import unittest
from types import SimpleNamespace
from unittest import mock

from app.db.content_repository import MemoryContentRepository
from app.db.repository import MemoryRepository
from app.services import llm_service
from app.services.demo_service import DemoService
from app.services.llm_service import (
    FALLBACK_TIMEOUT_SECONDS,
    QUESTION_TIMEOUT_SECONDS,
    LessonInterruptionPlan,
    LessonLLMService,
    LLMReply,
)


def _settings(timeout_seconds: int = 60) -> SimpleNamespace:
    return SimpleNamespace(
        llm_provider="gemini",
        llm_api_url="https://fallback.invalid/v1/chat/completions",
        llm_api_key="fallback-key",
        llm_model="fallback-model",
        gemini_api_key="gemini-key",
        gemini_model="gemini-model",
        llm_timeout_seconds=timeout_seconds,
    )


class QuestionTimeoutTest(unittest.TestCase):
    def setUp(self) -> None:
        llm_service._gemini_cooldown_until[0] = 0.0
        self.addCleanup(llm_service._gemini_cooldown_until.__setitem__, 0, 0.0)
        with mock.patch.object(llm_service, "settings", _settings()):
            self.llm = LessonLLMService()
        self.fallback_timeouts: list[int | None] = []
        self.llm._chat_gemini = lambda *args, **kwargs: None

        def fallback(system_prompt, user_prompt, *, timeout_seconds=None):
            self.fallback_timeouts.append(timeout_seconds)
            return "fallback answer"

        self.llm._chat_generic = fallback

    def test_question_waits_long_enough_for_gemini(self) -> None:
        # Gemini needs 12-17 s on harder questions.
        self.assertEqual(self.llm.question_timeout_seconds, QUESTION_TIMEOUT_SECONDS)
        self.assertGreaterEqual(self.llm.question_timeout_seconds, 18)

    def test_short_global_timeout_still_wins(self) -> None:
        with mock.patch.object(llm_service, "settings", _settings(timeout_seconds=6)):
            self.assertEqual(LessonLLMService().question_timeout_seconds, 6)

    def test_fallback_after_gemini_failure_gets_a_short_timeout(self) -> None:
        reply = self.llm._chat("system", "user", timeout_seconds=self.llm.question_timeout_seconds)

        self.assertEqual(reply, "fallback answer")
        self.assertEqual(self.fallback_timeouts, [FALLBACK_TIMEOUT_SECONDS])

    def test_fallback_during_cooldown_gets_the_full_timeout(self) -> None:
        llm_service._gemini_cooldown_until[0] = time.monotonic() + 60

        self.llm._chat("system", "user", timeout_seconds=self.llm.question_timeout_seconds)

        self.assertEqual(self.fallback_timeouts, [QUESTION_TIMEOUT_SECONDS])


class BothCallsMustRunTogetherLLM(LessonLLMService):
    """Each call waits for the other one; run one after the other and the barrier breaks."""

    def __init__(self) -> None:
        super().__init__()
        self.api_key = ""
        self.gemini_api_key = ""
        self.barrier = threading.Barrier(2, timeout=5)

    def plan_lesson_interruption(self, **kwargs) -> LessonInterruptionPlan:
        self.barrier.wait()
        return LessonInterruptionPlan(teacher_reply="계획 쪽 답", provider="fake")

    def answer_lesson_question(self, **kwargs) -> LLMReply:
        self.barrier.wait()
        return LLMReply(text="직접 답", provider="fake")


class LessonQuestionConcurrencyTest(unittest.TestCase):
    def test_lesson_question_runs_both_llm_calls_at_once(self) -> None:
        service = DemoService(MemoryRepository(), MemoryContentRepository(), llm_service=BothCallsMustRunTogetherLLM())

        result = service.answer_question(
            "demo-user",
            "왜 접선의 기울기가 도함수값이 되는 거야?",
            scene_id="scene-tangent-1",
        )

        self.assertIn("직접 답", result["teacherReply"])


if __name__ == "__main__":
    unittest.main()
