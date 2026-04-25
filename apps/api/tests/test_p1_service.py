from __future__ import annotations

import unittest

from app.db.content_repository import MemoryContentRepository
from app.db.repository import MemoryRepository
from app.services.demo_service import DemoService


class P1ServiceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.service = DemoService(MemoryRepository(), MemoryContentRepository())

    def test_lesson_question_returns_answer_scene(self) -> None:
        result = self.service.answer_question(
            "demo-user",
            "왜 접선의 기울기가 도함수값이 되는 거야?",
            scene_id="scene-tangent-1",
        )

        self.assertEqual(result["mode"], "branch-lesson")
        self.assertTrue(result["teacherReply"])
        self.assertGreaterEqual(len(result["branchScenes"]), 3)
        self.assertTrue(any(obj["type"] == "question" for obj in result["branchScenes"][0]["objects"]))
        self.assertTrue(any(obj["type"] == "answer" for obj in result["branchScenes"][1]["objects"]))
        self.assertEqual(result["branchScenes"][0]["autoAdvanceSeconds"], 2)

    def test_lesson_session_contains_richer_scene_metadata(self) -> None:
        session = self.service.lesson_session("demo-user")

        self.assertGreaterEqual(len(session["scenes"]), 40)
        self.assertTrue(session["scenes"][0]["teachingGoal"])
        self.assertTrue(any(obj["type"] in {"table", "checklist"} for obj in session["scenes"][2]["objects"]))
        self.assertGreaterEqual(len(session["questionStarters"]), 3)

    def test_question_can_reprioritize_remaining_lesson_scenes(self) -> None:
        session = self.service.lesson_session("demo-user")
        runtime_scene_ids = [scene["id"] for scene in session["scenes"]]
        current_index = 18
        result = self.service.answer_question(
            "demo-user",
            "기초부터 다시 설명해줘",
            scene_id=runtime_scene_ids[current_index],
            runtime_scene_ids=runtime_scene_ids,
        )

        continuation = result["continuationPlan"]
        self.assertEqual(continuation["mode"], "adaptive")
        self.assertEqual(len(continuation["orderedSceneIds"]), len(runtime_scene_ids))
        self.assertTrue(continuation["prioritizedSceneIds"])
        self.assertNotEqual(continuation["orderedSceneIds"], runtime_scene_ids)

    def test_questions_do_not_adjust_plan_or_queue_strategy(self) -> None:
        session = self.service.lesson_session("demo-user")
        runtime_scene_ids = [scene["id"] for scene in session["scenes"]]
        before_state = self.service.repository.load_state("demo-user")
        self.assertIsNotNone(before_state)
        assert before_state is not None
        before_plan = [day.focus for day in before_state.plan[:3]]
        before_job_count = len(before_state.strategy_jobs)

        self.service.answer_question(
            "demo-user",
            "기초부터 다시 설명해줘",
            scene_id=runtime_scene_ids[0],
            runtime_scene_ids=runtime_scene_ids,
        )
        self.service.answer_question(
            "demo-user",
            "왜 이런 원리로 푸는지 다시 설명해줘",
            scene_id=runtime_scene_ids[1],
            runtime_scene_ids=runtime_scene_ids,
        )
        self.service.answer_question(
            "demo-user",
            "풀이 순서를 다시 잡아줘",
            scene_id=runtime_scene_ids[2],
            runtime_scene_ids=runtime_scene_ids,
        )

        after_state = self.service.repository.load_state("demo-user")
        self.assertIsNotNone(after_state)
        assert after_state is not None
        after_plan = [day.focus for day in after_state.plan[:3]]
        self.assertEqual(before_plan, after_plan)
        self.assertEqual(before_job_count, len(after_state.strategy_jobs))

    def test_strategy_jobs_are_queued_and_processed_asynchronously(self) -> None:
        self.service.update_profile(
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
        diagnostic = self.service.bootstrap("demo-user")["diagnosticQuestions"]
        answers = {question["id"]: question["answer"] for question in diagnostic}
        self.service.submit_diagnostic("demo-user", answers)

        state = self.service.repository.load_state("demo-user")
        self.assertIsNotNone(state)
        assert state is not None
        self.assertTrue(state.strategy_jobs)
        self.assertEqual(state.strategy_jobs[-1].status, "pending")
        self.assertEqual(state.plan_strategy, {})

        result = self.service.process_strategy_jobs(user_id="demo-user", limit=1)

        self.assertEqual(result["processedCount"], 1)
        refreshed = self.service.repository.load_state("demo-user")
        self.assertIsNotNone(refreshed)
        assert refreshed is not None
        self.assertTrue(refreshed.plan_strategy)
        self.assertEqual(refreshed.strategy_jobs[-1].status, "completed")

    def test_practice_submission_creates_mistake_notes_and_xp(self) -> None:
        result = self.service.submit_practice(
            "demo-user",
            {
                "stepOne": "f'(x) = 2x + 4",
                "stepTwo": "m = 2",
                "stepThree": "점은 (1, 0)",
                "finalAnswer": "y = 2x",
            },
        )

        self.assertFalse(result["attempt"]["solved"])
        self.assertGreaterEqual(len(result["mistakeNotes"]), 1)
        self.assertGreater(result["dashboard"]["gamification"]["xp"], 0)
        self.assertEqual(
            result["dashboard"]["gamification"]["focusPoints"],
            result["dashboard"]["gamification"]["xp"],
        )
        self.assertIn("todayFlow", result["dashboard"]["gamification"])

    def test_complete_lesson_unlocks_practice(self) -> None:
        result = self.service.complete_lesson("demo-user")

        today_plan = result["dashboard"]["todayPlan"]
        lesson_task = next(task for task in today_plan["tasks"] if task["type"] == "lesson")
        practice_task = next(task for task in today_plan["tasks"] if task["type"] == "practice")

        self.assertEqual(lesson_task["status"], "done")
        self.assertEqual(practice_task["status"], "ready")
        self.assertEqual(practice_task["launch"]["mode"], "practice")

    def test_can_activate_maxmin_bundle_and_get_matching_session(self) -> None:
        result = self.service.activate_content_selection(
            "demo-user",
            bundle_id="suneung-math-maxmin-core-v1",
            lesson_id="lesson-maxmin-core",
            problem_set_id="set-maxmin-core",
        )

        dashboard = result["dashboard"]
        session = result["lessonSession"]
        self.assertEqual(dashboard["activeContent"]["bundleId"], "suneung-math-maxmin-core-v1")
        self.assertEqual(dashboard["activeContent"]["evaluationType"], "maxmin-points")
        self.assertEqual(session["practiceProblem"]["evaluationType"], "maxmin-points")
        self.assertEqual(session["practiceProblem"]["stepGuide"][1]["label"], "Step 2. 극값 후보")
        self.assertEqual(session["experience"]["autoAdvanceSeconds"], 20)

    def test_answer_only_submission_advances_to_next_problem(self) -> None:
        self.service.activate_content_selection(
            "demo-user",
            bundle_id="suneung-math-curriculum-v1",
            lesson_id="lesson-calc1-diff",
            problem_set_id="set-calc1-diff",
            problem_id="curr-diff-002",
        )

        result = self.service.submit_practice(
            "demo-user",
            {
                "finalAnswer": "y=-x+1",
                "scratchNote": "접점과 기울기를 종이에 따로 계산함",
            },
        )

        self.assertTrue(result["attempt"]["solved"])
        self.assertEqual(len(result["attempt"]["evaluated_steps"]), 1)
        self.assertEqual(result["dashboard"]["activeContent"]["currentProblemId"], "curr-diff-003")
        self.assertEqual(result["review"]["nextProblem"]["nextProblemId"], "curr-diff-003")
        self.assertEqual(result["lessonSession"]["practiceProblem"]["id"], "curr-diff-003")

    def test_diff_problem_set_contains_killer_problem(self) -> None:
        result = self.service.activate_content_selection(
            "demo-user",
            bundle_id="suneung-math-curriculum-v1",
            lesson_id="lesson-calc1-diff",
            problem_set_id="set-calc1-diff",
        )

        problems = result["lessonSession"]["problemSet"]["problems"]
        self.assertGreaterEqual(len(problems), 10)
        self.assertTrue(any(problem["isKiller"] for problem in problems))
        self.assertTrue(any("킬러 문제" in problem["title"] for problem in problems))

    def test_manual_next_problem_moves_even_without_solving(self) -> None:
        self.service.activate_content_selection(
            "demo-user",
            bundle_id="suneung-math-curriculum-v1",
            lesson_id="lesson-calc1-diff",
            problem_set_id="set-calc1-diff",
            problem_id="curr-diff-002",
        )

        result = self.service.advance_practice("demo-user")

        self.assertTrue(result["moved"])
        self.assertEqual(result["nextProblem"]["nextProblemId"], "curr-diff-003")
        self.assertEqual(result["lessonSession"]["practiceProblem"]["id"], "curr-diff-003")
        self.assertEqual(result["dashboard"]["activeContent"]["currentProblemId"], "curr-diff-003")

    def test_problem_payload_hides_answer_examples(self) -> None:
        result = self.service.activate_content_selection(
            "demo-user",
            bundle_id="suneung-math-curriculum-v1",
            lesson_id="lesson-track-calculus-killer",
            problem_set_id="set-track-calculus-killer",
        )

        practice_problem = result["lessonSession"]["practiceProblem"]
        self.assertEqual(practice_problem["finalPrompt"], "")

    def test_onboarding_route_progresses_from_survey_to_diagnostic_to_dashboard(self) -> None:
        bootstrap = self.service.bootstrap("demo-user")
        self.assertEqual(bootstrap["onboarding"]["requiredRoute"], "/survey")
        self.assertEqual(bootstrap["diagnosticQuestions"], [])

        updated = self.service.update_profile(
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
        self.assertEqual(updated["onboarding"]["requiredRoute"], "/diagnostic")

        diagnostic = self.service.bootstrap("demo-user")["diagnosticQuestions"]
        answers = {question["id"]: question["answer"] for question in diagnostic}
        result = self.service.submit_diagnostic("demo-user", answers)
        self.assertEqual(result["dashboard"]["diagnosticCompleted"], True)

        final_bootstrap = self.service.bootstrap("demo-user")
        self.assertEqual(final_bootstrap["onboarding"]["requiredRoute"], "/dashboard")

    def test_plan_strategy_is_deferred_until_diagnostic_is_complete(self) -> None:
        self.service.bootstrap("demo-user")
        initial_state = self.service.repository.load_state("demo-user")
        self.assertEqual(initial_state.plan_strategy, {})

        updated = self.service.update_profile(
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
        self.assertIsNone(updated["dashboard"])

        before_diagnostic = self.service.repository.load_state("demo-user")
        self.assertEqual(before_diagnostic.plan_strategy, {})

        diagnostic = self.service.bootstrap("demo-user")["diagnosticQuestions"]
        answers = {question["id"]: question["answer"] for question in diagnostic}
        self.service.submit_diagnostic("demo-user", answers)

        after_diagnostic = self.service.repository.load_state("demo-user")
        self.assertEqual(after_diagnostic.plan_strategy, {})
        self.assertTrue(after_diagnostic.strategy_jobs)
        self.assertEqual(after_diagnostic.strategy_jobs[-1].status, "pending")

    def test_diagnostic_progress_is_saved_per_session(self) -> None:
        self.service.update_profile(
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
        diagnostic = self.service.bootstrap("demo-user")["diagnosticQuestions"]
        first_question = diagnostic[0]
        self.service.save_diagnostic_progress("demo-user", {first_question["id"]: 1})
        persisted = self.service.bootstrap("demo-user")["onboarding"]["diagnosticAnswers"]
        self.assertIn(first_question["id"], persisted)

    def test_diagnostic_submit_requires_all_answers(self) -> None:
        self.service.update_profile(
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
        diagnostic = self.service.bootstrap("demo-user")["diagnosticQuestions"]
        partial_answers = {
            question["id"]: question["answer"] for question in diagnostic[:-2]
        }
        with self.assertRaisesRegex(ValueError, "아직 답하지 않은 문항"):
            self.service.submit_diagnostic("demo-user", partial_answers)

    def test_gamification_tracks_daily_flow_recovery_and_milestones(self) -> None:
        self.service.activate_content_selection(
            "demo-user",
            bundle_id="suneung-math-curriculum-v1",
            lesson_id="lesson-calc1-diff",
            problem_set_id="set-calc1-diff",
            problem_id="curr-diff-002",
        )

        self.service.complete_lesson("demo-user")
        self.service.answer_question(
            "demo-user",
            "왜 여기서 접선의 기울기를 먼저 봐요?",
            scene_id="scene-diff-core-map",
        )
        self.service.submit_practice(
            "demo-user",
            {
                "finalAnswer": "y=-x+1",
            },
        )
        self.service.review_latest("demo-user")

        dashboard = self.service.dashboard("demo-user")
        gamification = dashboard["gamification"]
        today_flow = gamification["todayFlow"]

        self.assertTrue(any(step["id"] == "lesson" and step["done"] for step in today_flow["steps"]))
        self.assertTrue(any(step["id"] == "practice" and step["done"] for step in today_flow["steps"]))
        self.assertTrue(any(step["id"] == "review" and step["done"] for step in today_flow["steps"]))
        self.assertTrue(any(step["id"] == "question" and step["done"] for step in today_flow["steps"]))
        self.assertTrue(today_flow["coreCompleted"])
        self.assertGreaterEqual(gamification["recoveryTokens"], 1)
        self.assertTrue(gamification["milestones"])
        self.assertIsNotNone(gamification["currentGoal"])


if __name__ == "__main__":
    unittest.main()
