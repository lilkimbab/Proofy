from __future__ import annotations

from collections import Counter
import unittest

from app.content.curriculum_seed import build_curriculum_bundle
from app.db.content_repository import DATA_CONTENT_ROOT, MemoryContentRepository, sync_seed_bundles_to_data
from app.services.content_review import review_generated_bundle


class CurriculumReviewTest(unittest.TestCase):
    def test_curriculum_bundle_is_loaded_with_course_tree(self) -> None:
        repository = MemoryContentRepository()
        bundle = repository.load_bundle("suneung-math-curriculum-v1")

        self.assertIsNotNone(bundle)
        self.assertEqual(bundle["source"]["path"], "[별책8] 수학과 교육과정.pdf")
        self.assertGreaterEqual(len(bundle["curriculum"]["courses"]), 7)
        self.assertGreaterEqual(len(bundle["problemSets"]), 20)
        self.assertGreaterEqual(len(bundle["curriculum"].get("killerTracks", [])), 3)

    def test_killer_tracks_expand_to_ten_problem_story_sets(self) -> None:
        bundle = build_curriculum_bundle()
        killer_tracks = bundle["curriculum"].get("killerTracks", [])
        self.assertEqual(len(killer_tracks), 3)
        for track in killer_tracks:
            problem_set = next(
                item for item in bundle["problemSets"] if item["id"] == track["problemSetId"]
            )
            self.assertGreaterEqual(len(problem_set["problems"]), 10)
            self.assertLessEqual(len(problem_set["problems"]), 15)

    def test_killer_tracks_do_not_use_numbered_or_bayes_titles(self) -> None:
        bundle = build_curriculum_bundle()
        killer_tracks = bundle["curriculum"].get("killerTracks", [])
        for track in killer_tracks:
            problem_set = next(
                item for item in bundle["problemSets"] if item["id"] == track["problemSetId"]
            )
            for problem in problem_set["problems"]:
                self.assertNotIn("베이즈", problem["title"])
                self.assertFalse(problem["title"].startswith("최상위 킬러 "))

    def test_killer_track_statements_are_long_condition_style(self) -> None:
        bundle = build_curriculum_bundle()
        killer_tracks = bundle["curriculum"].get("killerTracks", [])
        for track in killer_tracks:
            problem_set = next(
                item for item in bundle["problemSets"] if item["id"] == track["problemSetId"]
            )
            for problem in problem_set["problems"]:
                self.assertGreaterEqual(len(problem["statement"]), 80)
                self.assertIn("(가)", problem["statement"])
                self.assertTrue(problem.get("isKiller"))
                self.assertEqual(problem.get("difficulty"), "apex")

    def test_curated_drill_sets_do_not_repeat_problem_types(self) -> None:
        bundle = build_curriculum_bundle()
        curated_problem_set_ids = {
            "set-common1-polynomial-drill",
            "set-common1-equation-drill",
            "set-common1-counting-drill",
            "set-common1-matrix-drill",
            "set-common2-coordinate-drill",
            "set-common2-set-drill",
            "set-common2-function-drill",
            "set-algebra-exp-log-drill",
            "set-algebra-trig-drill",
            "set-calc1-limit-drill",
            "set-calc1-diff-drill",
            "set-calc1-integral-drill",
            "set-probstat-counting-drill",
            "set-probstat-probability-drill",
            "set-probstat-statistics-drill",
            "set-calc2-seq-limit-drill",
            "set-calc2-diff-drill",
            "set-calc2-integral-drill",
            "set-geometry-conic-drill",
            "set-geometry-space-drill",
            "set-geometry-vector-drill",
        }
        for problem_set in bundle["problemSets"]:
            if problem_set["id"] not in curated_problem_set_ids:
                continue
            all_types = [
                str(problem.get("problemType") or "")
                for problem in problem_set.get("problems", [])
            ]
            duplicates = {
                value: count
                for value, count in Counter(all_types).items()
                if value and count > 1
            }
            self.assertFalse(duplicates, f"{problem_set['id']} duplicated problem types: {duplicates}")

    def test_seed_bundles_sync_to_data_directory(self) -> None:
        written = sync_seed_bundles_to_data(overwrite=True)
        self.assertTrue(DATA_CONTENT_ROOT.exists())
        self.assertGreaterEqual(len(list(DATA_CONTENT_ROOT.glob("*.json"))), 4)
        self.assertGreaterEqual(len(written), 4)

    def test_review_pipeline_keeps_only_auto_scorable_problems(self) -> None:
        raw_bundle = {
            "bundleId": "generated-test-bundle",
            "title": "Generated Test Bundle",
            "version": "generated",
            "domain": "suneung-math",
            "concepts": [
                {
                    "id": "test-concept",
                    "title": "테스트 개념",
                    "lessonPackId": "lesson-test",
                    "problemSetId": "set-test",
                    "baselineScore": 60,
                    "baselineTrend": "+0",
                    "baselineRisk": "중간",
                }
            ],
            "diagnosticQuestions": [],
            "microScenes": {},
            "lessonPacks": [
                {
                    "id": "lesson-test",
                    "title": "테스트 레슨",
                    "unitTitle": "테스트 레슨",
                    "teacherName": "AI",
                    "conceptIds": ["test-concept"],
                    "questionStarters": [],
                    "scenes": [],
                }
            ],
            "problemSets": [
                {
                    "id": "set-test",
                    "title": "테스트 세트",
                    "lessonPackId": "lesson-test",
                    "conceptIds": ["test-concept"],
                    "problems": [
                        {
                            "id": "approved-problem",
                            "title": "승인 문제",
                            "statement": "x^2+2x+1을 인수분해하시오.",
                            "functionSpec": {},
                            "evaluationType": "structured-generic",
                            "gradingSpec": {
                                "steps": [
                                    {
                                        "label": "Step 1",
                                        "mode": "expression",
                                        "expected": ["x**2+2*x+1"],
                                        "hint": "전개식을 적으세요.",
                                    },
                                    {
                                        "label": "Step 2",
                                        "mode": "expression",
                                        "expected": ["(x+1)**2"],
                                        "hint": "인수분해하세요.",
                                    },
                                    {
                                        "label": "Step 3",
                                        "mode": "exact-match",
                                        "expected": ["(x+1)^2"],
                                        "hint": "형태를 정리하세요.",
                                    },
                                ],
                                "final": {
                                    "label": "최종 답",
                                    "mode": "expression",
                                    "expected": ["(x+1)**2"],
                                    "hint": "최종 답을 적으세요.",
                                },
                            },
                        },
                        {
                            "id": "rejected-problem",
                            "title": "반려 문제",
                            "statement": "설명형 문제",
                            "functionSpec": {},
                            "evaluationType": "reflection-open",
                        },
                    ],
                }
            ],
        }

        report = review_generated_bundle(raw_bundle, source_provider="gemini")

        self.assertEqual(report["approvedProblemCount"], 1)
        self.assertEqual(report["rejectedProblemCount"], 1)
        self.assertEqual(len(report["approvedBundle"]["problemSets"]), 1)
        self.assertEqual(
            report["approvedBundle"]["problemSets"][0]["problems"][0]["id"],
            "approved-problem",
        )

    def test_curriculum_bundle_self_review_passes_without_rejections(self) -> None:
        bundle = build_curriculum_bundle()
        report = review_generated_bundle(bundle, source_provider="curriculum-seed")

        self.assertEqual(report["status"], "approved")
        self.assertEqual(report["rejectedProblemCount"], 0)
        self.assertGreaterEqual(report["approvedProblemCount"], 60)

    def test_core_lessons_are_substantially_richer(self) -> None:
        bundle = build_curriculum_bundle()
        core_lessons = [
            lesson
            for lesson in bundle["lessonPacks"]
            if not lesson["id"].startswith("lesson-track-") and not lesson["id"].endswith("-drill")
        ]

        self.assertTrue(core_lessons)
        self.assertGreaterEqual(min(len(lesson["scenes"]) for lesson in core_lessons), 28)
        self.assertGreaterEqual(
            sum(len(lesson["scenes"]) for lesson in core_lessons) / len(core_lessons),
            39,
        )
        for lesson in core_lessons:
            titles = {scene["title"] for scene in lesson["scenes"]}
            self.assertIn("대표 예제 접근", titles)
            self.assertIn("대표 예제 해설", titles)
            self.assertIn("대표 예제 문제 읽기", titles)
            self.assertIn("대표 예제 첫 줄 선택", titles)
            self.assertIn("대표 예제 중간 전개", titles)
            self.assertIn("대표 예제 끝줄 검산", titles)
            self.assertIn("킬러 읽기 기준", titles)
            self.assertIn("킬러 스킬 정리", titles)
            self.assertIn("킬러 예제 구조 읽기", titles)
            self.assertIn("킬러 예제 첫 줄 선택", titles)
            self.assertIn("킬러 예제 중간 전환", titles)
            self.assertIn("킬러 예제 끝줄 정리", titles)


if __name__ == "__main__":
    unittest.main()
