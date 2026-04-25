from __future__ import annotations

import unittest

from app.domain.evaluator import (
    MaxMinProblemSpec,
    SymPyMaxMinEvaluator,
    SymPyTangentEvaluator,
    TangentProblemSpec,
    build_evaluator,
)


class SymPyEvaluatorTest(unittest.TestCase):
    def setUp(self) -> None:
        self.evaluator = SymPyTangentEvaluator(
            TangentProblemSpec(function_expression="x**2 - 4*x + 3", point_x=1)
        )

    def test_accepts_correct_solution(self) -> None:
        result = self.evaluator.evaluate(
            {
                "stepOne": "f'(x) = 2x - 4",
                "stepTwo": "m = f'(1) = -2",
                "stepThree": "f(1) = 0, 접점은 (1, 0)",
                "finalAnswer": "y - 0 = -2(x - 1)",
            }
        )
        self.assertTrue(all(step.accepted for step in result))

    def test_catches_derivative_sign_error(self) -> None:
        result = self.evaluator.evaluate(
            {
                "stepOne": "f'(x) = 2x + 4",
                "stepTwo": "m = -2",
                "stepThree": "(1, 0)",
                "finalAnswer": "y = -2x + 2",
            }
        )
        self.assertFalse(result[0].accepted)
        self.assertEqual(result[0].error_type, "sign-error")

    def test_accepts_equivalent_final_line(self) -> None:
        result = self.evaluator.evaluate(
            {
                "stepOne": "2x - 4",
                "stepTwo": "2(1) - 4 = -2",
                "stepThree": "0",
                "finalAnswer": "2y = -4x + 4",
            }
        )
        self.assertTrue(result[-1].accepted)

    def test_maxmin_evaluator_accepts_correct_solution(self) -> None:
        evaluator = SymPyMaxMinEvaluator(MaxMinProblemSpec(function_expression="2*x**3 - 9*x**2 + 12*x"))
        result = evaluator.evaluate(
            {
                "stepOne": "f'(x) = 6x^2 - 18x + 12",
                "stepTwo": "f'(x)=0 -> x=1, 2",
                "stepThree": "x=1은 극대, x=2는 극소",
                "finalAnswer": "극대점 (1, 5), 극소점 (2, 4)",
            }
        )
        self.assertTrue(all(step.accepted for step in result))

    def test_structured_generic_evaluator_accepts_equivalent_expression(self) -> None:
        evaluator = build_evaluator(
            {
                "evaluationType": "structured-generic",
                "gradingSpec": {
                    "steps": [
                        {
                            "label": "Step 1. 식 세우기",
                            "mode": "expression",
                            "expected": ["(x+1)**2"],
                            "hint": "식을 먼저 세우세요.",
                        },
                        {
                            "label": "Step 2. 전개",
                            "mode": "expression",
                            "expected": ["x**2+2*x+1"],
                            "hint": "전개하세요.",
                        },
                        {
                            "label": "Step 3. 수치 확인",
                            "mode": "numeric",
                            "expected": ["4"],
                            "hint": "값을 계산하세요.",
                        },
                    ],
                    "final": {
                        "label": "최종 답",
                        "mode": "expression",
                        "expected": ["x**2+2*x+1"],
                        "hint": "최종 답을 적으세요.",
                    },
                },
            }
        )
        result = evaluator.evaluate(
            {
                "stepOne": "(x+1)^2",
                "stepTwo": "x^2 + 2x + 1",
                "stepThree": "4",
                "finalAnswer": "(x+1)^2",
            }
        )
        self.assertTrue(all(step.accepted for step in result))


if __name__ == "__main__":
    unittest.main()
