from pathlib import Path

from app.services.eval_runner import (
    FeedbackToneEvalCase,
    ProblemGenerationEvalCase,
    evaluate_case,
    evaluate_feedback_tone_case,
    evaluate_fixture_tree,
    evaluate_problem_generation_case,
)


EVAL_ROOT = Path(__file__).resolve().parents[1] / "evals"


def test_eval_fixtures_pass_expected_outcomes():
    results = evaluate_fixture_tree(EVAL_ROOT)

    assert results
    assert all(result.passed for result in results), [
        (result.case_id, result.errors) for result in results if not result.passed
    ]


def test_eval_contains_required_case_types():
    results = evaluate_fixture_tree(EVAL_ROOT)
    case_types = {result.case_type for result in results}

    assert {"problem_generation", "feedback_grading", "feedback_tone"} <= case_types


def test_source_grounding_eval_rejects_external_knowledge():
    case = ProblemGenerationEvalCase.model_validate(
        {
            "case_type": "problem_generation",
            "id": "external_knowledge_unit",
            "description": "자료에 없는 외부 개념을 거부한다.",
            "request": {
                "document_id": "doc_001",
                "concepts": ["뉴턴 제2법칙"],
                "type": "multiple_choice",
                "count": 1,
                "difficulty": "medium",
                "bloom_level": "understand",
            },
            "chunks": [
                {
                    "chunk_id": "chunk_001",
                    "document_id": "doc_001",
                    "content": "뉴턴의 제2법칙은 F = ma이다.",
                    "page": 1,
                    "section_title": "운동 법칙",
                    "concepts": ["뉴턴 제2법칙"],
                }
            ],
            "candidate": {
                "document_id": "doc_001",
                "type": "multiple_choice",
                "difficulty": "medium",
                "bloom_level": "understand",
                "question": "뉴턴의 제2법칙과 상대성 이론을 함께 설명한 것은?",
                "choices": [
                    {"id": "A", "text": "F = ma이다."},
                    {"id": "B", "text": "상대성 이론이다."},
                    {"id": "C", "text": "힘과 무관하다."},
                    {"id": "D", "text": "가속도와 무관하다."},
                ],
                "answer": {"choice_id": "A", "text": "F = ma이다."},
                "explanation": "자료에는 F = ma만 있고 상대성 이론은 없다.",
                "choice_explanations": {
                    "A": "자료와 일치한다.",
                    "B": "자료에 없다.",
                    "C": "자료와 다르다.",
                    "D": "자료와 다르다.",
                },
                "rubric": None,
                "concepts": ["뉴턴 제2법칙"],
                "source_chunk_ids": ["chunk_001"],
            },
            "expected_valid": False,
            "forbidden_terms": ["상대성 이론"],
            "expected_error_substrings": ["forbidden term appears"],
        }
    )

    result = evaluate_problem_generation_case(case)

    assert result.passed is True
    assert result.actual_valid is False
    assert any("forbidden term" in error for error in result.errors)


def test_source_grounding_uses_cited_chunks_not_all_retrieved_chunks():
    row = {
        "case_type": "problem_generation",
        "id": "cited_chunk_unit",
        "description": "출처로 지정한 chunk에 근거가 있어야 한다.",
        "request": {
            "document_id": "doc_001",
            "concepts": ["운동량"],
            "type": "short_answer",
            "count": 1,
            "difficulty": "medium",
            "bloom_level": "understand",
        },
        "chunks": [
            {
                "chunk_id": "chunk_a",
                "document_id": "doc_001",
                "content": "힘은 물체의 운동 상태를 바꿀 수 있다.",
                "page": 1,
                "section_title": "힘",
                "concepts": ["힘"],
            },
            {
                "chunk_id": "chunk_b",
                "document_id": "doc_001",
                "content": "운동량은 질량과 속도의 곱이다.",
                "page": 2,
                "section_title": "운동량",
                "concepts": ["운동량"],
            },
        ],
        "candidate": {
            "document_id": "doc_001",
            "type": "short_answer",
            "difficulty": "medium",
            "bloom_level": "understand",
            "question": "운동량을 설명해줘.",
            "choices": None,
            "answer": {"choice_id": None, "text": "운동량은 질량과 속도의 곱이다."},
            "explanation": "운동량은 질량과 속도의 곱이다.",
            "choice_explanations": None,
            "rubric": [{"criterion": "운동량을 설명한다.", "points": 1}],
            "concepts": ["운동량"],
            "source_chunk_ids": ["chunk_a"],
        },
        "expected_valid": False,
        "required_source_terms": ["운동량", "질량", "속도"],
        "expected_error_substrings": ["required source term is not present in cited chunks"],
    }

    result = evaluate_case(row)

    assert result.passed is True
    assert result.actual_valid is False
    assert any("cited chunks" in error for error in result.errors)


def test_eval_fails_when_expected_error_reason_is_missing():
    row = {
        "case_type": "feedback_tone",
        "id": "missing_reason_unit",
        "description": "실패 이유까지 맞는지 검증한다.",
        "feedback": "정답 여부: 틀렸어.\n헷갈린 지점: 넌 못한다.\n올바른 개념: F = ma.\n복습 추천: 뉴턴 제2법칙",
        "expected_safe": False,
        "expected_error_substrings": ["missing section"],
    }

    result = evaluate_case(row)

    assert result.passed is False
    assert any("expected error substring not found" in error for error in result.errors)


def test_deep_short_answer_eval_requires_multiple_rubric_items():
    row = {
        "case_type": "problem_generation",
        "id": "deep_short_answer_rubric_unit",
        "description": "심층 주관식은 rubric 항목을 2개 이상 요구한다.",
        "request": {
            "document_id": "doc_001",
            "concepts": ["광합성"],
            "type": "short_answer",
            "count": 1,
            "difficulty": "hard",
            "bloom_level": "analyze",
        },
        "depth": "deep",
        "chunks": [
            {
                "chunk_id": "chunk_001",
                "document_id": "doc_001",
                "content": "광합성은 엽록체에서 빛에너지를 이용하는 과정이다.",
                "page": 1,
                "section_title": "광합성",
                "concepts": ["광합성"],
            }
        ],
        "candidate": {
            "document_id": "doc_001",
            "type": "short_answer",
            "difficulty": "hard",
            "bloom_level": "analyze",
            "question": "광합성을 분석해줘.",
            "choices": None,
            "answer": {"choice_id": None, "text": "광합성은 엽록체에서 일어난다."},
            "explanation": "자료에 근거한다.",
            "choice_explanations": None,
            "rubric": [{"criterion": "광합성을 설명한다.", "points": 1}],
            "concepts": ["광합성"],
            "source_chunk_ids": ["chunk_001"],
        },
        "expected_valid": False,
        "min_rubric_items": 2,
        "expected_error_substrings": ["deep short_answer requires"],
    }

    result = evaluate_case(row)

    assert result.passed is True
    assert result.actual_valid is False
    assert any("deep short_answer requires" in error for error in result.errors)


def test_high_rigor_eval_requires_extra_contract_fields():
    row = {
        "case_type": "problem_generation",
        "id": "high_rigor_contract_unit",
        "description": "고난도 eval은 source chunk 수, 수식, rubric 용어까지 확인한다.",
        "request": {
            "document_id": "doc_001",
            "concepts": ["뉴턴 제2법칙", "질량과 가속도"],
            "type": "short_answer",
            "count": 1,
            "difficulty": "hard",
            "bloom_level": "analyze",
            "goal": "exam_prep",
            "target_rigor": "high",
            "quality_mode": "strict",
            "depth": "deep",
        },
        "depth": "deep",
        "chunks": [
            {
                "chunk_id": "chunk_formula",
                "document_id": "doc_001",
                "content": "뉴턴의 제2법칙은 F = ma이다.",
                "page": 1,
                "section_title": "운동 법칙",
                "concepts": ["뉴턴 제2법칙"],
            },
            {
                "chunk_id": "chunk_relation",
                "document_id": "doc_001",
                "content": "같은 힘에서 질량이 커지면 가속도는 작아진다.",
                "page": 2,
                "section_title": "질량과 가속도",
                "concepts": ["질량과 가속도"],
            },
        ],
        "candidate": {
            "document_id": "doc_001",
            "type": "short_answer",
            "difficulty": "hard",
            "bloom_level": "analyze",
            "question": "같은 힘에서 질량 변화가 가속도에 미치는 영향을 분석하시오.",
            "choices": None,
            "answer": {"choice_id": None, "text": "$F = ma$에서 $a = F/m$이다."},
            "explanation": "$F = ma$ 관계를 적용한다.",
            "choice_explanations": None,
            "choice_diagnostics": None,
            "rubric": [
                {
                    "criterion": "공식 관계를 세운다.",
                    "points": 2,
                    "expected_evidence": ["$F = ma$"],
                    "common_mistakes": ["질량과 가속도 관계를 반대로 씀"],
                    "partial_credit_rules": ["공식만 쓰면 부분 점수"],
                },
                {
                    "criterion": "질량 변화와 가속도 변화를 분석한다.",
                    "points": 2,
                    "expected_evidence": ["질량", "가속도", "분석"],
                    "common_mistakes": ["반비례 관계를 빠뜨림"],
                    "partial_credit_rules": ["방향만 맞으면 부분 점수"],
                },
            ],
            "concepts": ["뉴턴 제2법칙", "질량과 가속도"],
            "source_chunk_ids": ["chunk_formula", "chunk_relation"],
        },
        "expected_valid": True,
        "required_output_terms": ["$F = ma$", "질량", "가속도"],
        "required_rubric_terms": ["공식", "분석"],
        "min_source_chunks": 2,
        "min_distinct_concepts": 2,
        "require_latex": True,
        "min_rubric_items": 2,
    }

    result = evaluate_case(row)

    assert result.passed is True
    assert result.actual_valid is True


def test_feedback_tone_eval_rejects_shaming_phrases():
    case = FeedbackToneEvalCase(
        case_type="feedback_tone",
        id="tone_unit",
        description="비난 표현을 거부한다.",
        feedback="정답 여부: 틀렸어.\n헷갈린 지점: 넌 못한다.\n올바른 개념: F = ma.\n복습 추천: 뉴턴 제2법칙",
        expected_safe=False,
        expected_error_substrings=["unsafe phrase"],
    )

    result = evaluate_feedback_tone_case(case)

    assert result.passed is True
    assert result.actual_valid is False
    assert any("unsafe phrase" in error for error in result.errors)


def test_feedback_tone_eval_rejects_safe_but_too_casual_copy():
    case = FeedbackToneEvalCase(
        case_type="feedback_tone",
        id="too_casual_tone_unit",
        description="상업용 일반 사용자 피드백은 안전해도 반말이면 거부한다.",
        feedback=(
            "정답 여부: 아직 정답은 아니야.\n"
            "헷갈린 지점: 질량과 가속도의 관계를 반대로 생각한 것 같아.\n"
            "올바른 개념: 같은 힘에서는 질량이 클수록 가속도는 작아져.\n"
            "복습 추천: 뉴턴 제2법칙"
        ),
        expected_safe=False,
        expected_error_substrings=["unsafe phrase"],
    )

    result = evaluate_feedback_tone_case(case)

    assert result.passed is True
    assert result.actual_valid is False
