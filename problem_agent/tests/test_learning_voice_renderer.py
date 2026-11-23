from app.schemas.learning_contents import LearningContentBase
from app.schemas.learning_voice import FeedbackCopyInput, FeedbackCopyOutput, FeedbackSituation, NextActionType
from app.services.learning_copy_quality_checker import LearningCopyQualityChecker
from app.services.learning_voice_renderer import LearningVoiceRenderer


def test_wrong_feedback_copy_is_soft_and_actionable():
    renderer = LearningVoiceRenderer()

    output = renderer.render_feedback(
        FeedbackCopyInput(
            situation=FeedbackSituation.wrong,
            concept="원인과 결과의 순서",
            evidence_summary="자료에서는 A가 먼저 나오고, 그 다음 B가 이어진다고 설명해요.",
            next_action=NextActionType.retry,
        )
    )

    assert output.tone_status == "passed"
    assert output.title == "원인과 결과의 순서가 조금 헷갈리셨군요 🤔"
    assert "오답입니다" not in output.title + output.body
    assert "사용자" not in output.title + output.body
    assert output.next_action_type == NextActionType.retry
    assert output.next_action_label == "힌트만 보고 다시 풀기"
    assert output.secondary_action_type == NextActionType.review_concept_card
    assert "🤔" in output.title


def test_correct_feedback_copy_uses_specific_praise():
    renderer = LearningVoiceRenderer()

    output = renderer.render_feedback(
        FeedbackCopyInput(
            situation=FeedbackSituation.correct,
            concept="조건 비교",
            evidence_summary="특히 조건을 비교해서 고른 점이 좋아요.",
        )
    )

    assert output.tone_status == "passed"
    assert output.title == "좋아요, 잘하셨어요 👍"
    assert "완벽" not in output.body
    assert "조건" in output.body
    assert output.next_action_type == NextActionType.solve_similar
    assert "👍" in output.title


def test_correct_feedback_default_mentions_reasoning_not_empty_praise():
    renderer = LearningVoiceRenderer()

    output = renderer.render_feedback(
        FeedbackCopyInput(
            situation=FeedbackSituation.correct,
            concept="조건 비교",
        )
    )

    assert output.tone_status == "passed"
    assert "그냥 외운 게 아니라" in output.body
    assert "기준" in output.body


def test_copy_checker_rejects_robotic_wrong_feedback():
    checker = LearningCopyQualityChecker()

    result = checker.check_text("오답입니다. 이해도가 부족합니다.", situation=FeedbackSituation.wrong)

    assert result.status == "failed"
    assert any("robotic" in error or "blames" in error for error in result.errors)


def test_copy_checker_rejects_cold_but_safe_feedback():
    checker = LearningCopyQualityChecker()
    output = FeedbackCopyOutput(
        title="조건을 확인했습니다",
        body="질량과 가속도의 관계를 다시 보십시오.",
        next_action_label="재학습",
    )

    result = checker.check_output(output, situation=FeedbackSituation.wrong)

    assert result.status == "failed"
    assert any("friendly education-site tone" in error for error in result.errors)


def test_wrong_feedback_uses_chatgpt_like_coaching_tone():
    renderer = LearningVoiceRenderer()

    output = renderer.render_feedback(
        FeedbackCopyInput(
            situation=FeedbackSituation.wrong,
            concept="수요와 가격의 관계",
            mistake_type="concept_misunderstanding",
        )
    )

    assert output.tone_status == "passed"
    assert "헷갈리셨군요" in output.title
    assert "이건 헷갈릴 만해요" in output.body
    assert "기준 문장" in output.body
    assert output.next_action_type == NextActionType.review_concept_card
    assert output.secondary_action_type == NextActionType.solve_similar


def test_partial_feedback_sounds_like_tutor_not_report():
    renderer = LearningVoiceRenderer()

    output = renderer.render_feedback(
        FeedbackCopyInput(
            situation=FeedbackSituation.partially_correct,
            concept="조건 비교",
        )
    )

    assert output.tone_status == "passed"
    assert output.title == "방향은 좋아요 👏"
    assert "큰 흐름은 맞게 잡으셨어요" in output.body
    assert "세부 조건" in output.body
    assert "부분적으로 맞았습니다" not in output.body


def test_copy_checker_requires_next_action_for_wrong_feedback():
    checker = LearningCopyQualityChecker()
    output = FeedbackCopyOutput(
        title="여기서 헷갈린 건 원인과 결과예요.",
        body="자료에서는 A가 먼저 나오고 B가 이어진다고 설명해요.",
    )

    result = checker.check_output(output, situation=FeedbackSituation.wrong)

    assert result.status == "failed"
    assert any("next action" in error for error in result.errors)


def test_learning_content_copy_is_attached_for_true_false():
    renderer = LearningVoiceRenderer()
    content = LearningContentBase(
        document_id="doc_001",
        content_type="true_false",
        concepts=["수요와 가격의 관계"],
        source_chunk_ids=["chunk_001"],
        difficulty="medium",
        bloom_level="understand",
        quality_status="passed",
        quality_report={"status": "passed", "score": 0.9, "source_grounded": True},
        payload={
            "statement": "수요가 늘면 가격 상승 압력이 생긴다.",
            "answer": True,
            "explanation": "수요가 증가하면 가격이 오를 수 있다.",
        },
    )

    copy = renderer.render_learning_content_copy(content)

    assert copy.intro == "⭕ 자료의 설명과 맞는지 같이 판단해볼까요?"
    assert copy.success is not None
    assert copy.failure is not None
    assert copy.success.next_action_type == NextActionType.solve_similar
    assert copy.failure.next_action_type == NextActionType.retry
    assert copy.failure.next_action_label == "힌트만 보고 다시 풀기"


def test_renderer_can_remove_emoji_for_stricter_tone_profile():
    renderer = LearningVoiceRenderer()

    output = renderer.render_feedback(
        FeedbackCopyInput(
            situation=FeedbackSituation.correct,
            concept="조건 비교",
            tone_profile={"emoji_policy": "none"},
        )
    )

    assert "👍" not in output.title
    assert output.title == "좋아요, 잘하셨어요"


def test_low_confidence_feedback_uses_cautious_copy():
    renderer = LearningVoiceRenderer()

    output = renderer.render_feedback(
        FeedbackCopyInput(
            situation=FeedbackSituation.partially_correct,
            concept="뉴턴 제2법칙",
            evidence_summary="힘과 질량 관계는 잡았지만 가속도 조건이 빠졌어요.",
            confidence="low",
        )
    )

    assert output.tone_status == "passed"
    assert "조금 애매할 수 있어요" in output.body
    assert "지금 보이는 답안" in output.body
    assert "low_confidence_feedback_copy" in output.warnings


def test_mistake_type_changes_feedback_action():
    renderer = LearningVoiceRenderer()

    misread = renderer.render_feedback(
        FeedbackCopyInput(
            situation=FeedbackSituation.wrong,
            concept="뉴턴 제2법칙",
            mistake_type="misread_question",
        )
    )
    unit_error = renderer.render_feedback(
        FeedbackCopyInput(
            situation=FeedbackSituation.wrong,
            concept="속도 단위",
            mistake_type="unit_error",
        )
    )

    assert misread.title == "문제 조건이 조금 헷갈리셨군요 🤔"
    assert misread.next_action_type == NextActionType.mark_conditions
    assert misread.next_action_label == "조건 표시하고 다시 풀기"
    assert misread.secondary_action_type == NextActionType.retry
    assert "조건" in misread.body
    assert unit_error.title == "단위가 조금 헷갈리셨군요 🤔"
    assert unit_error.next_action_type == NextActionType.check_units
    assert unit_error.next_action_label == "단위만 체크하기"
    assert unit_error.secondary_action_type == NextActionType.split_steps
