from __future__ import annotations

import unittest

from app.domain.problem_verifier import UnsafeExpression, evaluate_spec, safe_eval, verify_problem

# Problems Gemini Flash produced in the 2026-11-23 probe, checked by hand.
ABS_KINK = {
    "f": "x**3 - 6*x**2 + 9*x",
    "define": [["g", "Abs(f - at(f, 1))"], ["h", "(x - 4)*g"]],
    "checks": [
        {"condition": "(가)", "expr": "len(nondiff_points(g)) == 1"},
        {"condition": "(나)", "expr": "is_differentiable(h)"},
        {"condition": "(다)", "expr": "same(local_min_values(f), [0])"},
    ],
    "answer": "at(f, 6)",
}

LEVEL_JUMPS = {
    "f": "x**3 - 3*x - 2",
    "define": [["g2", "(x - 2)*Abs(f)"], ["g0", "x*Abs(f)"]],
    "checks": [
        {"condition": "(가)", "expr": "same(level_jumps(f), [-4, 0])"},
        {"condition": "(나) a = 2", "expr": "is_differentiable(g2)"},
        {"condition": "(나) a = 0 은 안 됨", "expr": "not is_differentiable(g0)"},
    ],
    "answer": "at(f, 5)",
}

PIECEWISE = {
    "f": "x**3 - 3*x**2 - 9*x + 27",
    "define": [["k", "0"], ["g", "Piecewise((f, x < 1), (Abs(f - k), True))"]],
    "checks": [
        {"condition": "(가)", "expr": "is_differentiable(g)"},
        {"condition": "(나)", "expr": "same(at(f, 3), 0) and same(at(f, 0) + at(d(f), 0)*3, 0)"},
    ],
    "answer": "at(f, 5)",
}


class VerifierHelpersTest(unittest.TestCase):
    def test_known_good_problems_pass(self) -> None:
        for spec, answer in ((ABS_KINK, 54), (LEVEL_JUMPS, 108), (PIECEWISE, 32)):
            report = evaluate_spec(spec, answer)
            self.assertTrue(report.ok, report.failure_summary())

    def test_wrong_declared_answer_fails(self) -> None:
        report = evaluate_spec(ABS_KINK, 55)
        self.assertFalse(report.ok)
        self.assertFalse(report.answer_matches)

    def test_false_condition_fails(self) -> None:
        # The old bundle generator claimed this quartic has a local max at x = 1/2; it has none.
        spec = {
            "f": "4*x**4 - 8*x**3 + 5*x**2 - 2*x + 7",
            "checks": [{"condition": "극대", "expr": "same([p for p, v in local_max(f)], [Rational(1, 2)])"}],
            "answer": "1",
        }
        report = evaluate_spec(spec, 1)
        self.assertFalse(report.ok)
        self.assertFalse(report.checks[0].ok)

    def test_answer_must_be_natural_number_up_to_999(self) -> None:
        spec = {"f": "x**2", "checks": [{"condition": "-", "expr": "True"}], "answer": "Rational(1, 2)"}
        self.assertFalse(evaluate_spec(spec, 0).answer_is_natural)
        spec["answer"] = "1000"
        self.assertFalse(evaluate_spec(spec, 1000).answer_is_natural)

    def test_integral_and_tangent_helpers(self) -> None:
        spec = {
            "f": "x**2 - 4",
            "define": [["g", "prim(f, 0)"]],
            "checks": [
                {"condition": "넓이", "expr": "same(definite(Abs(f), 0, 3), Rational(23, 3))"},
                {"condition": "정적분 함수", "expr": "same(at(g, 3), -3)"},
                {"condition": "구간 최대", "expr": "same(max_on(f, -1, 3), 5)"},
                {"condition": "접선 개수", "expr": "tangent_count(x**3 - 3*x, 2, 0) == 3"},
                {"condition": "중복도", "expr": "multiplicity((x - 1)**2*(x + 2), 1) == 2"},
            ],
            "answer": "3",
        }
        report = evaluate_spec(spec, 3)
        self.assertTrue(report.ok, report.failure_summary())

    def test_irrational_kink_points(self) -> None:
        # 2x^3 - 9x^2 + 12x - 6 has one irrational real root; sympy.limit fails there.
        points = safe_eval("nondiff_points(Abs(2*x**3 - 9*x**2 + 12*x - 6))", {})
        self.assertEqual(len(points), 1)
        self.assertTrue(safe_eval("is_differentiable(Abs(2*x**3 - 9*x**2 + 12*x - 6)**2)", {}))
        self.assertEqual(safe_eval("nondiff_points(Abs(x**2 - 2))", {}), safe_eval("[-sqrt(2), sqrt(2)]", {}))

    def test_piecewise_jump_and_corner(self) -> None:
        self.assertEqual(safe_eval("discontinuities(Piecewise((x, x < 1), (x + 1, True)))", {}), [1])
        self.assertEqual(safe_eval("nondiff_points(Piecewise((x**2, x < 1), (2*x - 1, True)))", {}), [])
        self.assertEqual(safe_eval("nondiff_points(Max(x**2, 2*x))", {}), [0, 2])

    def test_extrema_of_kinked_functions(self) -> None:
        # |x^2 - 4|: minima at the kinks x = ±2 (value 0), maximum at x = 0 (value 4)
        self.assertEqual(safe_eval("local_min(Abs(x**2 - 4))", {}), [(-2, 0), (2, 0)])
        self.assertEqual(safe_eval("local_max_values(Abs(x**2 - 4))", {}), [4])
        # x|x - 3| has a local max at x = 3/2 and a local min at the kink x = 3
        self.assertTrue(safe_eval("same(local_max(x*Abs(x - 3)), [(Rational(3, 2), Rational(9, 4))])", {}))
        self.assertTrue(safe_eval("same(local_min(x*Abs(x - 3)), [(3, 0)])", {}))

    def test_triple_root_is_differentiable_under_abs(self) -> None:
        self.assertEqual(safe_eval("nondiff_points(Abs((x - 1)**3))", {}), [])
        self.assertEqual(len(safe_eval("nondiff_points(Abs((x - 1)*(x**2 + 1)))", {})), 1)


class VerifierSafetyTest(unittest.TestCase):
    def test_rejects_private_attributes_and_imports(self) -> None:
        for source in ("().__class__", "__import__('os')", "f.__dict__", "[c for c in ().__class__.__mro__]"):
            with self.assertRaises(UnsafeExpression):
                safe_eval(source, {"f": 1})

    def test_rejects_lambda_and_strings(self) -> None:
        for source in ("(lambda: 1)()", "'abc'"):
            with self.assertRaises(UnsafeExpression):
                safe_eval(source, {})

    def test_child_process_reports_instead_of_hanging(self) -> None:
        spec = {"f": "x", "checks": [{"condition": "폭주", "expr": "same(2**(10**10), 1)"}], "answer": "1"}
        report = verify_problem(spec, 1, timeout_seconds=20)
        self.assertFalse(report.ok)

    def test_child_process_passes_good_problem(self) -> None:
        report = verify_problem(ABS_KINK, 54, timeout_seconds=60)
        self.assertTrue(report.ok, report.failure_summary())


if __name__ == "__main__":
    unittest.main()
