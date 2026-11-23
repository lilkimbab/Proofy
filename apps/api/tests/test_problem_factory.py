from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from app.domain.problem_verifier import evaluate_spec
from app.services.llm_client import LLMResult, ModelUnavailable
from app.services.problem_factory import (
    GENERATOR_SYSTEM,
    REFUTER_SYSTEM,
    FactoryConfig,
    ProblemFactory,
    ProblemStore,
    export_approved,
    set_review,
    to_app_notation,
)

GOOD_DRAFT = {
    "statement": "최고차항의 계수가 1인 삼차함수 $f(x)$에 대하여 $g(x) = |f(x) - f(1)|$, $h(x) = (x-4)g(x)$라 하자.\n"
    "(가) g(x)가 미분가능하지 않은 점의 개수는 1이다.\n(나) h(x)는 실수 전체의 집합에서 미분가능하다.\n"
    "(다) f(x)의 극솟값은 0이다.\nf(6)의 값을 구하시오.",
    "answer": 54,
    "solution": ["x = 1이 중근이어야 한다", "β = 4", "f(6) = 54"],
    "cases": ["x = 1이 단일근 → (나)에서 탈락"],
    "trap": "x = 1을 단일근으로 두는 경우",
    "whyHard": "근의 위치 케이스 분기",
    "verify": {
        "f": "x**3 - 6*x**2 + 9*x",
        "define": [["g", "Abs(f - at(f, 1))"], ["h", "(x - 4)*g"]],
        "checks": [
            {"condition": "(가)", "expr": "len(nondiff_points(g)) == 1"},
            {"condition": "(나)", "expr": "is_differentiable(h)"},
            {"condition": "(다)", "expr": "same(local_min_values(f), [0])"},
        ],
        "answer": "at(f, 6)",
    },
}

BAD_DRAFT = {**GOOD_DRAFT, "answer": 55}

# Generated on 2026-11-23 and marked "verified" before the refuter existed. The intended
# f gives 158, but f(x) - k = (x - t)^3 with t = 1 - 8*3^(1/4)/3 also meets every condition.
AMBIGUOUS_DRAFT = {
    "statement": "최고차항의 계수가 1인 삼차함수 f(x)와 실수 k에 대하여 함수 g(x) = (x - 1)|f(x) - k| 라 하자.\n"
    "(가) 함수 g(x)는 실수 전체의 집합에서 미분가능하다.\n(나) 함수 g(x)의 극댓값은 0이고, 극솟값은 -16이다.\n"
    "(다) f(0) = 2\nf(4)의 값을 구하시오.",
    "answer": 158,
    "solution": ["f(x) - k = (x - 1)(x - a)^2", "a = -3, k = 11", "f(4) = 158"],
    "verify": {
        "f": "x**3 + 5*x**2 + 3*x + 2",
        "define": [["k", "11"], ["g", "(x - 1)*Abs(f - k)"]],
        "checks": [
            {"condition": "(가)", "expr": "is_differentiable(g)"},
            {"condition": "(나)", "expr": "same(local_max_values(g), [0]) and same(local_min_values(g), [-16])"},
            {"condition": "(다)", "expr": "same(at(f, 0), 2)"},
        ],
        "answer": "at(f, 4)",
    },
}
TRIPLE_ROOT_T = "(1 - 8*3**Rational(1, 4)/3)"
REAL_COUNTEREXAMPLE = {
    "counterexample": {
        "f": f"(x - {TRIPLE_ROOT_T})**3 + 2 + {TRIPLE_ROOT_T}**3",
        "define": [["k", f"2 + {TRIPLE_ROOT_T}**3"]],
        "note": "삼중근",
    },
    "statementIssue": "",
}
NO_OBJECTION = {"counterexample": None, "statementIssue": ""}


class FakeClient:
    """Scripted stand-in for LLMClient: generator replies and solver answers by role."""

    def __init__(self, generator_replies, strong_answers, weak_answers, second_answers=(), unavailable=(), refuter_replies=()):
        self.generator_replies = list(generator_replies)
        self.solver_answers = {"strong": list(strong_answers), "weak": list(weak_answers), "second": list(second_answers)}
        self.refuter_replies = list(refuter_replies)
        self.unavailable = set(unavailable)
        self.prompts: list[tuple[str, str]] = []

    def complete_json(self, model, system, user, **_kwargs):
        if model in self.unavailable:
            raise ModelUnavailable(f"{model} 503")
        self.prompts.append((model, user))
        if system == REFUTER_SYSTEM:
            data = self.refuter_replies.pop(0) if self.refuter_replies else NO_OBJECTION
            return LLMResult(model=model, text=json.dumps(data, ensure_ascii=False), data=data, elapsed=1.0)
        if system == GENERATOR_SYSTEM:
            data = self.generator_replies.pop(0)
            if isinstance(data, Exception):
                raise data
            return LLMResult(model=model, text=json.dumps(data, ensure_ascii=False), data=data, elapsed=1.0, reasoning_tokens=100)
        role = "strong" if model.endswith("120b") else ("weak" if model.endswith("-20b") else "second")
        answer = self.solver_answers[role].pop(0)
        data = {"answer": answer, "unique": True, "issue": "", "keyStep": "중근 위치"}
        return LLMResult(model=model, text=json.dumps(data), data=data, elapsed=1.0, reasoning_tokens=5000 if role == "strong" else 800)


def _verifier(spec, answer, timeout_seconds=60):
    return evaluate_spec(spec, answer)


class ProblemFactoryTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.store = ProblemStore(Path(self.tmp.name))
        self.config = FactoryConfig(
            generator_models=["gemini:main", "gemini:backup"],
            strong_solver="groq:gpt-oss-120b",
            weak_solver="groq:gpt-oss-20b",
        )

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _factory(self, client) -> ProblemFactory:
        return ProblemFactory(self.config, client=client, store=self.store, verifier=_verifier)

    def test_verified_and_hard_when_weak_solver_fails(self) -> None:
        client = FakeClient([GOOD_DRAFT], strong_answers=[54], weak_answers=[12])
        record = self._factory(client).run("calc1-diff", archetype_id="diff-abs-kink")
        self.assertEqual(record["status"], "verified")
        self.assertEqual(record["difficulty"]["verdict"], "hard")
        self.assertNotIn("$", record["problem"]["statement"])
        self.assertEqual(record["review"]["state"], "pending")
        self.assertTrue((Path(self.tmp.name) / "problems" / "calc1-diff" / f"{record['id']}.json").exists())

    def test_wrong_answer_is_sent_back_for_repair(self) -> None:
        client = FakeClient([BAD_DRAFT, GOOD_DRAFT], strong_answers=[54], weak_answers=[1])
        record = self._factory(client).run("calc1-diff", archetype_id="diff-abs-kink")
        self.assertEqual([item["kind"] for item in record["rounds"]], ["generate", "repair"])
        self.assertIn("적어 낸 정답과 다름", client.prompts[1][1])
        self.assertEqual(record["status"], "verified")

    def test_rejected_after_repairs_run_out(self) -> None:
        client = FakeClient([BAD_DRAFT, BAD_DRAFT, BAD_DRAFT], strong_answers=[], weak_answers=[])
        record = self._factory(client).run("calc1-diff", archetype_id="diff-abs-kink")
        self.assertEqual(record["status"], "rejected")
        with self.assertRaises(ValueError):
            set_review(self.store, record["id"], approve=True)

    def test_too_easy_problem_is_hardened(self) -> None:
        client = FakeClient([GOOD_DRAFT, GOOD_DRAFT], strong_answers=[54, 54], weak_answers=[54, 3])
        record = self._factory(client).run("calc1-diff", archetype_id="diff-abs-kink")
        self.assertEqual([item["kind"] for item in record["rounds"]], ["generate", "harden"])
        self.assertTrue(any("약한 풀이 모델도 정답 54" in text for _, text in client.prompts))
        self.assertEqual(record["difficulty"]["verdict"], "hard")

    def test_failed_hardening_keeps_previous_problem(self) -> None:
        self.config.max_repairs = 0
        client = FakeClient([GOOD_DRAFT, BAD_DRAFT], strong_answers=[54], weak_answers=[54])
        record = self._factory(client).run("calc1-diff", archetype_id="diff-abs-kink")
        self.assertEqual(record["status"], "verified")
        self.assertEqual(record["problem"]["answer"], 54)
        self.assertEqual(record["difficulty"]["verdict"], "too-easy")

    def test_strong_disagreement_asks_second_opinion(self) -> None:
        client = FakeClient([GOOD_DRAFT], strong_answers=[None], weak_answers=[2], second_answers=[54])
        record = self._factory(client).run("calc1-diff", archetype_id="diff-abs-kink")
        self.assertEqual(record["status"], "verified")
        client = FakeClient([GOOD_DRAFT], strong_answers=[10], weak_answers=[2], second_answers=[11])
        record = self._factory(client).run("calc1-diff", archetype_id="diff-abs-kink")
        self.assertEqual(record["status"], "disputed")

    def test_falls_back_to_next_generator_on_503(self) -> None:
        client = FakeClient([GOOD_DRAFT], strong_answers=[54], weak_answers=[2], unavailable={"gemini:main"})
        record = self._factory(client).run("calc1-diff", archetype_id="diff-abs-kink")
        self.assertEqual(record["rounds"][0]["model"], "gemini:backup")

    def test_confirmed_counterexample_sends_problem_back(self) -> None:
        client = FakeClient(
            [AMBIGUOUS_DRAFT, GOOD_DRAFT],
            strong_answers=[54],
            weak_answers=[2],
            refuter_replies=[REAL_COUNTEREXAMPLE, NO_OBJECTION],
        )
        record = self._factory(client).run("calc1-diff", archetype_id="diff-abs-kink")
        self.assertEqual([item["kind"] for item in record["rounds"]], ["generate", "repair"])
        self.assertTrue(record["rounds"][0]["refuter"]["confirmed"])
        repair_prompt_text = next(text for model, text in client.prompts if "SymPy로 검산했더니" in text)
        self.assertIn("답이 하나로 정해지지 않음", repair_prompt_text)
        self.assertEqual(record["status"], "verified")
        self.assertEqual(record["problem"]["answer"], 54)

    def test_ambiguous_problem_is_rejected_when_repairs_run_out(self) -> None:
        self.config.max_repairs = 0
        client = FakeClient([AMBIGUOUS_DRAFT], strong_answers=[], weak_answers=[], refuter_replies=[REAL_COUNTEREXAMPLE])
        record = self._factory(client).run("calc1-diff", archetype_id="diff-abs-kink")
        self.assertEqual(record["status"], "rejected")
        self.assertTrue(any("답이 하나로 정해지지 않음" in line for line in record["verification"]["errors"]))

    def test_unconfirmed_objection_is_flagged_for_review(self) -> None:
        bogus = {"counterexample": {"f": "x**3", "define": [], "note": "아무 함수"}, "statementIssue": ""}
        client = FakeClient([GOOD_DRAFT], strong_answers=[54], weak_answers=[2], refuter_replies=[bogus])
        record = self._factory(client).run("calc1-diff", archetype_id="diff-abs-kink")
        self.assertEqual(record["status"], "disputed")
        self.assertFalse(record["refuter"]["confirmed"])
        self.assertTrue(record["flags"])

        issue = {"counterexample": None, "statementIssue": "삼차함수는 최솟값이 없다"}
        client = FakeClient([GOOD_DRAFT], strong_answers=[54], weak_answers=[2], refuter_replies=[issue])
        record = self._factory(client).run("calc1-diff", archetype_id="diff-abs-kink")
        self.assertEqual(record["status"], "disputed")
        self.assertIn("최솟값", record["flags"][0])

    def test_rejected_request_during_hardening_keeps_verified_problem(self) -> None:
        from app.services.llm_client import LLMError

        too_large = LLMError("HTTP 413 Request too large")
        client = FakeClient([GOOD_DRAFT, too_large, too_large], strong_answers=[54], weak_answers=[54])
        factory = self._factory(client)
        waits: list[int] = []
        factory.sleep = waits.append
        record = factory.run("calc1-diff", archetype_id="diff-abs-kink")
        self.assertEqual(record["status"], "verified")
        self.assertEqual(record["difficulty"]["verdict"], "too-easy")
        self.assertEqual(waits, [])
        self.assertEqual(len(self.store.all()), 1)

    def test_waits_and_gives_up_when_every_generator_is_busy(self) -> None:
        from app.services.problem_factory import GeneratorUnavailable

        client = FakeClient([], strong_answers=[], weak_answers=[], unavailable={"gemini:main", "gemini:backup"})
        factory = self._factory(client)
        waits: list[int] = []
        factory.sleep = waits.append
        with self.assertRaises(GeneratorUnavailable):
            factory.run("calc1-diff", archetype_id="diff-abs-kink")
        self.assertEqual(waits, [self.config.busy_wait_seconds] * self.config.busy_retries)
        self.assertEqual(self.store.all(), [])

    def test_export_only_approved(self) -> None:
        client = FakeClient([GOOD_DRAFT, GOOD_DRAFT], strong_answers=[54, 54], weak_answers=[2, 2])
        factory = self._factory(client)
        approved = factory.run("calc1-diff", archetype_id="diff-abs-kink")
        factory.run("calc1-diff", archetype_id="diff-abs-kink")
        set_review(self.store, approved["id"], approve=True, note="ok")
        written = export_approved(self.store)
        problems = json.loads(written["calc1-diff"].read_text(encoding="utf-8"))
        self.assertEqual([item["id"] for item in problems], [approved["id"]])
        self.assertEqual(problems[0]["gradingSpec"]["final"]["expected"], ["54"])
        self.assertEqual(problems[0]["difficulty"], "apex")

    def test_archetypes_rotate(self) -> None:
        client = FakeClient([GOOD_DRAFT, GOOD_DRAFT], strong_answers=[54, 54], weak_answers=[2, 2])
        factory = self._factory(client)
        first = factory.run("calc1-diff")
        second = factory.run("calc1-diff")
        self.assertNotEqual(first["archetype"], second["archetype"])


class NotationTest(unittest.TestCase):
    def test_latex_becomes_app_notation(self) -> None:
        text, issues = to_app_notation(
            r"$g(x) = \begin{cases} f(x) & (x < 1) \\ |f(x) - k| & (x \geq 1) \end{cases}$, $\frac{1}{2}$, $\sqrt{3}$, $x^{2}$"
        )
        self.assertEqual(issues, [])
        self.assertIn("{ f(x) (x < 1), |f(x) - k| (x ≥ 1) }", text)
        self.assertIn("1/2", text)
        self.assertIn("√3", text)
        self.assertIn("x^2", text)

    def test_unknown_latex_is_reported(self) -> None:
        _, issues = to_app_notation(r"$\overline{AB}$")
        self.assertTrue(issues)


if __name__ == "__main__":
    unittest.main()
