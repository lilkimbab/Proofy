import re
import unittest
from unittest import mock

from app.content import curriculum_seed
from app.content.lecture_copy import SENTENCE_REWRITES, fix_josa, josa, polish_title

_PAREN_JOSA = re.compile(r"(은|는|이|가|을|를|과|와)\((은|는|이|가|을|를|과|와)\)|\(으\)로")
_TEXT_FIELDS = ["narration", "teachingGoal", "takeaway", "examCue", "practiceBridge"]


class JosaTest(unittest.TestCase):
    def test_picks_particle_from_final_consonant(self) -> None:
        self.assertEqual(josa("미분", "를"), "미분을")
        self.assertEqual(josa("벡터", "을"), "벡터를")
        self.assertEqual(josa("수열", "가"), "수열이")
        self.assertEqual(josa("극한", "로"), "극한으로")
        self.assertEqual(josa("미적분Ⅰ - 미분", "는"), "미적분Ⅰ - 미분은")

    def test_rieul_final_takes_ro(self) -> None:
        self.assertEqual(josa("수열", "으로"), "수열로")
        self.assertEqual(josa("1", "으로"), "1로")

    def test_fix_josa_resolves_template_particles(self) -> None:
        self.assertEqual(fix_josa("도형의 방정식은(는) 평면도형을"), "도형의 방정식은 평면도형을")
        self.assertEqual(fix_josa("함수은(는)"), "함수는")
        self.assertEqual(fix_josa("f(x)은(는) 연속"), "f(x)는 연속")
        self.assertEqual(fix_josa("이미 맞는 문장"), "이미 맞는 문장")

    def test_titles(self) -> None:
        self.assertEqual(polish_title("오늘의 논지"), "오늘 배울 내용")
        self.assertEqual(polish_title("미분계수 오개념 교정"), "미분계수: 자주 하는 실수")


class CurriculumCopyTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.bundle = curriculum_seed.build_curriculum_bundle()
        with mock.patch.object(curriculum_seed, "_polish_lesson_pack", lambda pack: pack):
            cls.raw_bundle = curriculum_seed.build_curriculum_bundle()

    def test_every_rewrite_key_still_comes_from_the_templates(self) -> None:
        raw_texts = {
            scene.get(field)
            for pack in self.raw_bundle["lessonPacks"]
            for scene in pack["scenes"]
            for field in _TEXT_FIELDS
        }
        stale = [key for key in SENTENCE_REWRITES if key not in raw_texts]
        self.assertEqual(stale, [], "SENTENCE_REWRITES keys no longer produced by curriculum_seed")

    def test_shipped_lessons_have_no_template_particles(self) -> None:
        offenders = []
        for pack in self.bundle["lessonPacks"]:
            for scene in pack["scenes"]:
                for field in ["title", *_TEXT_FIELDS]:
                    value = scene.get(field)
                    if isinstance(value, str) and _PAREN_JOSA.search(value):
                        offenders.append(value)
        self.assertEqual(offenders[:5], [])

    def test_rewrites_are_applied(self) -> None:
        shipped = {
            scene.get(field)
            for pack in self.bundle["lessonPacks"]
            for scene in pack["scenes"]
            for field in _TEXT_FIELDS
        }
        self.assertFalse(set(SENTENCE_REWRITES) & shipped)


if __name__ == "__main__":
    unittest.main()
