from __future__ import annotations

import unittest

from app.content.onboarding_diagnostic import build_onboarding_diagnostic
from app.db.content_repository import MemoryContentRepository
from app.db.repository import MemoryRepository
from app.domain.content import default_mastery, select_active_content
from app.services.demo_service import DemoService


class ContentSelectionTest(unittest.TestCase):
    def setUp(self) -> None:
        self.content_repository = MemoryContentRepository()
        self.bundle = self.content_repository.load_bundle("suneung-math-p0-v1")

    def test_selects_sign_repair_for_lowest_sign_accuracy(self) -> None:
        mastery = default_mastery(self.bundle)
        for item in mastery:
            if item.id == "sign-accuracy":
                item.score = 35
        lesson_pack, problem_set, problem = select_active_content(self.bundle, mastery)
        self.assertEqual(lesson_pack["id"], "lesson-sign-repair")
        self.assertEqual(problem_set["id"], "set-sign-repair")
        self.assertTrue(problem["id"].startswith("problem-sign"))

    def test_service_updates_active_content_after_diagnostic(self) -> None:
        service = DemoService(MemoryRepository(), self.content_repository)
        service.update_profile(
            "demo-user",
            {
                "nickname": "홍길동",
                "examDate": "2026-11-19",
                "subjectTargets": {
                    "korean": 84,
                    "math": 92,
                    "english": 82,
                    "inquiry1": 80,
                    "inquiry2": 80,
                },
                "weeklyStudyHours": 24,
                "dailyMinutes": 180,
                "studyMood": "실전 위주",
                "weakUnits": ["미분", "확률"],
                "surveyStep": 5,
                "surveyCompleted": True,
            },
        )
        diagnostic = service.bootstrap("demo-user")["diagnosticQuestions"]
        answers = {question["id"]: question["answer"] for question in diagnostic}
        result = service.submit_diagnostic("demo-user", answers)
        active_content = result["dashboard"]["activeContent"]
        self.assertEqual(active_content["bundleId"], "suneung-math-curriculum-v1")
        self.assertTrue(active_content["problemSetId"].startswith("set-"))
        self.assertTrue(active_content["lessonId"].startswith("lesson-"))

    def test_seeded_diagnostic_contains_killer_questions(self) -> None:
        diagnostic = build_onboarding_diagnostic(
            size=12,
            seed="demo-seed",
            prioritized_terms=["미분", "확률", "기하"],
        )
        killer_count = sum(1 for question in diagnostic if question["difficulty"] == "killer")
        self.assertGreaterEqual(killer_count, 2)
        self.assertEqual(len(diagnostic), 12)
        self.assertEqual(len({question["id"] for question in diagnostic}), 12)

    def test_diagnostic_changes_with_new_seed(self) -> None:
        first = build_onboarding_diagnostic(
            size=12,
            seed="demo-seed-a",
            prioritized_terms=["미분", "확률", "기하"],
        )
        second = build_onboarding_diagnostic(
            size=12,
            seed="demo-seed-b",
            prioritized_terms=["미분", "확률", "기하"],
        )
        self.assertNotEqual(
            [question["id"] for question in first],
            [question["id"] for question in second],
        )


if __name__ == "__main__":
    unittest.main()
