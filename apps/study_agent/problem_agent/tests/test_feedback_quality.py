from app.agents.feedback_agent import FEEDBACK_SECTION_LABELS, FeedbackAgent
from app.config import Settings
from app.models import Problem, Submission
from app.schemas.problems import AnswerInput, SubmitAnswerRequest


class FakeLLM:
    available = True

    def __init__(self, payload):
        self.payload = payload

    def generate_json(self, **kwargs):
        return self.payload


def test_multiple_choice_correct_feedback_uses_fixed_structure():
    agent = FeedbackAgent()
    feedback = agent.multiple_choice_feedback(
        problem=multiple_choice_problem(),
        submission=Submission(answer={"choice_id": "A"}),
        is_correct=True,
    )

    assert feedback["is_correct"] is True
    assert feedback["mistake_type"] == "none"
    assert feedback["recommended_review"] == []
    assert_feedback_sections(feedback["feedback"])


def test_multiple_choice_wrong_feedback_uses_mistake_type_and_review():
    agent = FeedbackAgent()
    feedback = agent.multiple_choice_feedback(
        problem=multiple_choice_problem(),
        submission=Submission(answer={"choice_id": "C"}),
        is_correct=False,
    )

    assert feedback["is_correct"] is False
    assert feedback["mistake_type"] == "concept_misunderstanding"
    assert feedback["weak_concepts"] == ["뉴턴 제2법칙"]
    assert feedback["recommended_review"] == ["뉴턴 제2법칙"]
    assert_feedback_sections(feedback["feedback"])


def test_multiple_choice_wrong_feedback_uses_selected_choice_diagnostic():
    agent = FeedbackAgent()
    feedback = agent.multiple_choice_feedback(
        problem=diagnostic_multiple_choice_problem(),
        submission=Submission(answer={"choice_id": "C"}),
        is_correct=False,
    )

    assert feedback["is_correct"] is False
    assert "가속도를 항상 0으로 본 점" in feedback["feedback"]
    assert "$F = ma$ 관계로 다시 확인" in feedback["feedback"]
    assert feedback["summary"] == "선택한 보기에서 헷갈린 지점을 기준으로 다시 짚어볼게요."
    assert_feedback_sections(feedback["feedback"])


def test_multiple_choice_diagnostic_payload_exposes_selected_choice_intent():
    agent = FeedbackAgent()
    diagnostic = agent.multiple_choice_diagnostic_payload(
        problem=diagnostic_multiple_choice_problem(),
        submission=Submission(answer={"choice_id": "C"}),
    )

    assert diagnostic["selected_choice_id"] == "C"
    assert diagnostic["selected_choice_text"] == "가속도는 항상 0이다."
    assert diagnostic["correct_choice_id"] == "A"
    assert diagnostic["correct_choice_text"] == "힘은 질량과 가속도의 곱이다."
    assert "가속도를 항상 0으로 본 점" in diagnostic["misconception"]
    assert "$F = ma$ 관계로 다시 확인" in diagnostic["repair_strategy"]
    assert diagnostic["mistake_type"] == "concept_misunderstanding"
    assert diagnostic["misconception_id"] == "mis_newton_zero_acceleration"
    assert diagnostic["followup_problem_type"] == "misconception_contrast"


def test_multiple_choice_template_feedback_does_not_require_llm_fallback():
    agent = FeedbackAgent(settings=Settings(OPENAI_API_KEY=None, LLM_FALLBACK_ENABLED=False))

    feedback = agent.multiple_choice_feedback(
        problem=multiple_choice_problem(),
        submission=Submission(answer={"choice_id": "C"}),
        is_correct=False,
    )

    assert feedback["is_correct"] is False
    assert feedback["score"] == 0
    assert feedback["recommended_review"] == ["뉴턴 제2법칙"]
    assert_feedback_sections(feedback["feedback"])


def test_multiple_choice_llm_cannot_override_code_grade():
    agent = FeedbackAgent(
        llm=FakeLLM(
            {
                "is_correct": True,
                "score": 1,
                "max_score": 1,
                "mistake_type": "none",
                "weak_concepts": [],
                "summary": "정답이라고 잘못 판단했다.",
                "feedback": (
                    "정답 여부: 정답이야.\n"
                    "헷갈린 지점: 없어.\n"
                    "올바른 개념: 이미 맞았어.\n"
                    "복습 추천: 이번 문제는 넘어가도 괜찮아."
                ),
                "recommended_review": [],
            }
        ),
        settings=Settings(OPENAI_API_KEY="test-key", MULTIPLE_CHOICE_FEEDBACK_LLM_ENABLED=True),
    )

    feedback = agent.multiple_choice_feedback(
        problem=multiple_choice_problem(),
        submission=Submission(answer={"choice_id": "C"}),
        is_correct=False,
    )

    assert feedback["is_correct"] is False
    assert feedback["score"] == 0
    assert feedback["max_score"] == 1
    assert feedback["mistake_type"] == "concept_misunderstanding"
    assert feedback["recommended_review"] == ["뉴턴 제2법칙"]
    assert "아직 정답은 아니에요" in feedback["feedback"]


def test_short_answer_partial_score_feedback():
    agent = FeedbackAgent()
    feedback = agent.grade_short_answer(
        problem=short_answer_problem(),
        submission=Submission(answer={"text": "뉴턴 제2법칙"}),
        chunks=[],
    )

    assert feedback["is_correct"] is False
    assert 0 < feedback["score"] < feedback["max_score"]
    assert feedback["mistake_type"] == "incomplete_answer"
    assert feedback["recommended_review"] == ["뉴턴 제2법칙"]
    assert len(feedback["rubric_results"]) == len(short_answer_problem().rubric)
    assert feedback["score"] == sum(item["awarded_points"] for item in feedback["rubric_results"])
    assert any(not item["matched"] for item in feedback["rubric_results"])
    assert_feedback_sections(feedback["feedback"])


def test_calculation_short_answer_wrong_numeric_result_returns_calculation_error():
    agent = FeedbackAgent()
    feedback = agent.grade_short_answer(
        problem=calculation_short_answer_problem(),
        submission=Submission(
            answer={"text": "$F = ma$이므로 $a = F / m$이고 $a = 12 / 3 = 5 m/s^2$이다."}
        ),
        chunks=[],
    )

    assert feedback["is_correct"] is False
    assert feedback["mistake_type"] == "calculation_error"
    assert 0 < feedback["score"] < feedback["max_score"]
    assert_feedback_sections(feedback["feedback"])


def test_calculation_short_answer_missing_unit_returns_unit_error():
    agent = FeedbackAgent()
    feedback = agent.grade_short_answer(
        problem=calculation_short_answer_problem(),
        submission=Submission(
            answer={"text": "$F = ma$이므로 $a = F / m$이고 $a = 12 / 3 = 4$이다."}
        ),
        chunks=[],
    )

    assert feedback["is_correct"] is False
    assert feedback["mistake_type"] == "unit_error"
    assert 0 < feedback["score"] < feedback["max_score"]
    assert_feedback_sections(feedback["feedback"])


def test_typed_short_answer_input_is_accepted():
    request = SubmitAnswerRequest(answer={"input_mode": "typed", "text": "뉴턴 제2법칙은 F=ma이다."})

    assert request.answer.input_mode == "typed"
    assert request.answer.text == "뉴턴 제2법칙은 F=ma이다."


def test_tablet_ocr_answer_uses_ocr_text_for_grading():
    answer = AnswerInput(
        input_mode="tablet_ocr",
        ocr_text="뉴턴 제2법칙은 힘이 질량과 가속도의 곱이라는 법칙이다.",
        ocr_confidence=0.93,
        tablet_image_url="https://example.test/submissions/sub_001.png",
    )
    agent = FeedbackAgent()
    feedback = agent.grade_short_answer(
        problem=short_answer_problem(),
        submission=Submission(answer=answer.model_dump(exclude_none=True)),
        chunks=[],
    )

    assert answer.text == answer.ocr_text
    assert feedback["is_correct"] is True
    assert feedback["mistake_type"] == "none"
    assert "recommended_review" in feedback
    assert_feedback_sections(feedback["feedback"])


def assert_feedback_sections(feedback_text):
    for label in FEEDBACK_SECTION_LABELS:
        assert f"{label}:" in feedback_text


def multiple_choice_problem():
    return Problem(
        id="prob_001",
        user_id="user_001",
        document_id="doc_001",
        type="multiple_choice",
        difficulty="medium",
        bloom_level="understand",
        question="뉴턴의 제2법칙에 대한 설명으로 가장 적절한 것은?",
        choices=[
            {"id": "A", "text": "힘은 질량과 가속도의 곱이다."},
            {"id": "B", "text": "힘은 질량과 무관하다."},
            {"id": "C", "text": "가속도는 항상 0이다."},
            {"id": "D", "text": "질량이 클수록 같은 힘에서 가속도는 커진다."},
        ],
        answer={"choice_id": "A", "text": "힘은 질량과 가속도의 곱이다."},
        explanation="자료에는 뉴턴의 제2법칙이 F = ma라고 설명되어 있다.",
        choice_explanations={
            "A": "자료 내용과 일치한다.",
            "B": "질량은 식에 포함된다.",
            "C": "자료에 없는 설명이다.",
            "D": "같은 힘에서는 질량이 클수록 가속도가 작아진다.",
        },
        rubric=None,
        concepts=["뉴턴 제2법칙"],
        source_chunk_ids=["chunk_001"],
        quality_status="passed",
    )


def diagnostic_multiple_choice_problem():
    problem = multiple_choice_problem()
    problem.choice_explanations = {
        **problem.choice_explanations,
        "C": (
            "헷갈린 지점: 가속도를 항상 0으로 본 점이에요. "
            "복습 방법: 힘이 작용할 때 가속도가 어떻게 변하는지 $F = ma$ 관계로 다시 확인하세요."
        ),
    }
    problem.choice_diagnostics = [
        {
            "choice_id": "A",
            "is_correct": True,
            "misconception_id": None,
            "mistake_type": "none",
            "why_plausible": None,
            "repair_strategy": None,
            "followup_problem_type": None,
        },
        {
            "choice_id": "B",
            "is_correct": False,
            "misconception_id": "mis_newton_mass_irrelevant",
            "mistake_type": "concept_misunderstanding",
            "why_plausible": "질량을 힘의 관계에서 빼고 보면 고를 수 있는 보기예요.",
            "repair_strategy": "$F = ma$에서 질량이 식에 포함된다는 점을 다시 확인하세요.",
            "followup_problem_type": "misconception_contrast",
        },
        {
            "choice_id": "C",
            "is_correct": False,
            "misconception_id": "mis_newton_zero_acceleration",
            "mistake_type": "concept_misunderstanding",
            "why_plausible": "가속도를 항상 0으로 본 점이에요.",
            "repair_strategy": "힘이 작용할 때 가속도가 어떻게 변하는지 $F = ma$ 관계로 다시 확인하세요.",
            "followup_problem_type": "misconception_contrast",
        },
        {
            "choice_id": "D",
            "is_correct": False,
            "misconception_id": "mis_newton_mass_inverse",
            "mistake_type": "concept_misunderstanding",
            "why_plausible": "같은 힘에서 질량이 커질수록 가속도도 커진다고 보면 고를 수 있는 보기예요.",
            "repair_strategy": "같은 힘 조건에서 질량과 가속도의 반비례 관계를 비교하세요.",
            "followup_problem_type": "misconception_contrast",
        },
    ]
    return problem


def short_answer_problem():
    return Problem(
        id="prob_002",
        user_id="user_001",
        document_id="doc_001",
        type="short_answer",
        difficulty="medium",
        bloom_level="understand",
        question="뉴턴의 제2법칙을 설명해줘.",
        choices=None,
        answer={"choice_id": None, "text": "뉴턴 제2법칙은 힘이 질량과 가속도의 곱이라는 법칙이다."},
        explanation="자료에는 힘, 질량, 가속도의 관계가 F = ma로 제시되어 있다.",
        choice_explanations=None,
        rubric=[
            {"criterion": "핵심 개념을 포함한다.", "points": 2},
            {"criterion": "의미를 자신의 말로 설명한다.", "points": 1},
            {"criterion": "관련 용어를 정확히 사용한다.", "points": 1},
        ],
        concepts=["뉴턴 제2법칙"],
        source_chunk_ids=["chunk_001"],
        quality_status="passed",
    )


def calculation_short_answer_problem():
    return Problem(
        id="prob_calc_001",
        user_id="user_001",
        document_id="doc_001",
        type="short_answer",
        difficulty="hard",
        bloom_level="analyze",
        question=(
            "질량이 $3 kg$인 물체에 $12 N$의 힘이 작용할 때 가속도를 구하고, "
            "같은 힘에서 질량이 $6 kg$이면 가속도가 어떻게 달라지는지 설명하시오."
        ),
        choices=None,
        answer={
            "choice_id": None,
            "text": (
                "$F = ma$에서 $a = F / m$이다. 처음 조건에서는 "
                "$a = 12 / 3 = 4 m/s^2$이고, 질량이 $6 kg$이면 "
                "$a = 12 / 6 = 2 m/s^2$이다."
            ),
        },
        explanation="공식에 값을 대입하고 단위까지 확인한다.",
        choice_explanations=None,
        rubric=[
            {
                "criterion": "$F = ma$에서 $a = F / m$ 관계를 세웠다.",
                "points": 2,
                "expected_evidence": ["$F = ma$", "$a = F / m$"],
                "common_mistakes": ["공식을 바꿔 씀"],
                "partial_credit_rules": ["공식만 맞으면 부분 점수"],
            },
            {
                "criterion": "각 조건의 값을 대입해 계산했다.",
                "points": 2,
                "expected_evidence": ["$12 / 3 = 4$", "$12 / 6 = 2$"],
                "common_mistakes": ["분자와 분모를 바꿈"],
                "partial_credit_rules": ["한 조건만 맞으면 부분 점수"],
            },
            {
                "criterion": "단위를 포함해 결과를 해석했다.",
                "points": 1,
                "expected_evidence": ["$m/s^2$"],
                "common_mistakes": ["단위를 빠뜨림"],
                "partial_credit_rules": ["단위가 일부 맞으면 부분 점수"],
            },
        ],
        concepts=["뉴턴 제2법칙"],
        source_chunk_ids=["chunk_001"],
        quality_status="passed",
    )
