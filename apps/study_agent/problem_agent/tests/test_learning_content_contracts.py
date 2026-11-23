import pytest
from pydantic import ValidationError

from app.agents import LearningContentQualityChecker
from app.schemas.integration_contracts import RetrievedChunk
from app.schemas.learning_contents import (
    CONTENT_INTERACTION_MODES,
    GenerateLearningContentRequest,
    GenerateMiniExamRequest,
    LearningContentBase,
    LearningContentInteractionMode,
    LearningContentType,
)
from app.schemas.quality import QualityFlag


def test_generate_learning_content_request_rejects_empty_or_duplicate_concepts():
    with pytest.raises(ValidationError):
        GenerateLearningContentRequest(
            document_id="doc_001",
            concepts=["뉴턴 제2법칙", "뉴턴 제2법칙"],
            content_type="flashcard",
        )

    with pytest.raises(ValidationError):
        GenerateLearningContentRequest(
            document_id="doc_001",
            concepts=[" "],
            content_type="flashcard",
        )

    with pytest.raises(ValidationError):
        GenerateLearningContentRequest(
            document_id="doc_001",
            concepts=["뉴턴 제2법칙"],
            content_type="flashcard",
            count=11,
        )


def test_generate_mini_exam_request_normalizes_title_and_rejects_duplicates():
    request = GenerateMiniExamRequest(
        document_id="doc_001",
        concepts=["뉴턴 제2법칙"],
        title="  뉴턴 법칙 점검  ",
        count=3,
    )

    assert request.title == "뉴턴 법칙 점검"
    assert request.problem_type == "multiple_choice"

    with pytest.raises(ValidationError):
        GenerateMiniExamRequest(
            document_id="doc_001",
            concepts=["뉴턴 제2법칙", "뉴턴 제2법칙"],
        )


def test_learning_content_accepts_flashcard_contract():
    content = learning_content(
        content_type="flashcard",
        payload={
            "front": "뉴턴 제2법칙에서 힘은 무엇과 관련되는가?",
            "back": "질량과 가속도와 관련된다.",
            "hint": "F = ma를 떠올려봐.",
            "explanation": "자료에서는 힘이 질량과 가속도의 곱으로 표현된다고 설명한다.",
        },
    )

    assert content.content_type == LearningContentType.flashcard
    assert content.interaction_mode == LearningContentInteractionMode.study_only
    assert content.source_chunk_ids == ["chunk_001"]
    assert content.payload["front"].startswith("뉴턴")


def test_learning_content_rejects_missing_source_chunks():
    with pytest.raises(ValidationError):
        learning_content(
            content_type="flashcard",
            source_chunk_ids=[],
            payload={
                "front": "질문",
                "back": "답",
                "explanation": "해설",
            },
        )


def test_learning_content_rejects_missing_quality_report():
    with pytest.raises(ValidationError):
        LearningContentBase(
            document_id="doc_001",
            content_type="flashcard",
            concepts=["뉴턴 제2법칙"],
            source_chunk_ids=["chunk_001"],
            quality_status="passed",
            payload={
                "front": "질문",
                "back": "답",
                "explanation": "해설",
            },
        )


def test_learning_content_rejects_quality_status_mismatch():
    with pytest.raises(ValidationError):
        learning_content(
            content_type="flashcard",
            quality_status="passed",
            quality_report={"status": "needs_review", "score": 0.6, "source_grounded": True},
            payload={
                "front": "질문",
                "back": "답",
                "explanation": "해설",
            },
        )


def test_learning_content_rejects_payload_that_does_not_match_type():
    with pytest.raises(ValidationError):
        learning_content(
            content_type="flashcard",
            payload={
                "prompt": "힘은 ____와 가속도의 곱이다.",
                "answer": "질량",
                "explanation": "해설",
            },
        )


def test_cloze_payload_requires_blank_and_normalizes_acceptable_answers():
    content = learning_content(
        content_type="cloze",
        payload={
            "prompt": "힘은 질량과 ____의 곱이다.",
            "answer": "가속도",
            "acceptable_answers": ["가속도", "acceleration"],
            "explanation": "자료의 F = ma 관계를 확인하는 빈칸 문제다.",
        },
    )

    assert content.interaction_mode == LearningContentInteractionMode.auto_gradable
    assert content.payload["acceptable_answers"] == ["가속도", "acceleration"]

    with pytest.raises(ValidationError):
        learning_content(
            content_type="cloze",
            payload={
                "prompt": "힘은 질량과 가속도의 곱이다.",
                "answer": "가속도",
                "explanation": "빈칸이 없으므로 거부한다.",
            },
        )


def test_false_true_false_content_requires_correction():
    with pytest.raises(ValidationError):
        learning_content(
            content_type="true_false",
            payload={
                "statement": "같은 힘에서는 질량이 클수록 가속도가 커진다.",
                "answer": False,
                "explanation": "자료의 관계와 반대다.",
            },
        )

    content = learning_content(
        content_type="true_false",
        payload={
            "statement": "같은 힘에서는 질량이 클수록 가속도가 작아진다.",
            "answer": True,
            "explanation": "자료의 질량과 가속도 관계와 일치한다.",
        },
    )

    assert content.interaction_mode == LearningContentInteractionMode.auto_gradable


def test_learning_content_rejects_wrong_interaction_mode():
    with pytest.raises(ValidationError):
        learning_content(
            content_type="mini_exam",
            interaction_mode="study_only",
            payload={
                "title": "뉴턴 법칙 미니 모의고사",
                "items": [{"content_id": "content_001", "content_type": "true_false"}],
            },
        )


def test_all_learning_content_payload_contracts_accept_minimum_valid_payloads():
    payloads = {
        LearningContentType.flashcard: {
            "front": "뉴턴 제2법칙의 핵심 관계는?",
            "back": "힘, 질량, 가속도의 관계다.",
            "explanation": "자료는 F = ma 관계를 설명한다.",
        },
        LearningContentType.cloze: {
            "prompt": "뉴턴 제2법칙은 힘, 질량, ____의 관계다.",
            "answer": "가속도",
            "explanation": "자료의 핵심 관계를 확인한다.",
        },
        LearningContentType.true_false: {
            "statement": "힘은 질량과 가속도의 곱으로 표현된다.",
            "answer": True,
            "explanation": "자료와 일치한다.",
        },
        LearningContentType.ordering: {
            "prompt": "문제 풀이 순서를 배열하시오.",
            "items": [{"id": "A", "text": "공식을 확인한다."}, {"id": "B", "text": "값을 대입한다."}],
            "correct_order": ["A", "B"],
            "explanation": "공식 확인 후 값을 대입한다.",
        },
        LearningContentType.matching: {
            "prompt": "용어와 의미를 연결하시오.",
            "pairs": [{"left": "힘", "right": "질량과 가속도의 곱"}, {"left": "가속도", "right": "속도 변화율"}],
            "explanation": "자료의 용어 관계를 확인한다.",
        },
        LearningContentType.worked_example: {
            "problem": "F = ma에서 질량과 가속도를 알 때 힘을 구하시오.",
            "steps": [{"order": 1, "text": "F = ma를 확인한다."}],
            "final_answer": "힘은 질량과 가속도의 곱이다.",
            "explanation": "자료의 공식을 적용한다.",
        },
        LearningContentType.mistake_drill: {
            "seed_problem_id": "prob_001",
            "seed_feedback_id": "fb_001",
            "target_mistake_type": "concept_misunderstanding",
            "target_concepts": ["뉴턴 제2법칙"],
            "variant_strategy": "same_concept_new_condition",
        },
        LearningContentType.mini_exam: {
            "title": "뉴턴 제2법칙 미니 모의고사",
            "items": [{"content_id": "content_001", "content_type": "true_false"}],
        },
        LearningContentType.concept_summary_card: {
            "title": "뉴턴 제2법칙 핵심",
            "summary": "힘, 질량, 가속도의 관계를 설명하는 법칙이다.",
            "key_points": ["F = ma", "같은 힘에서는 질량이 클수록 가속도가 작다."],
        },
    }

    for content_type, payload in payloads.items():
        content = learning_content(content_type=content_type, payload=payload)

        assert content.content_type == content_type
        assert content.interaction_mode == CONTENT_INTERACTION_MODES[content_type]
        assert content.quality_report.source_grounded is True


def test_learning_content_quality_checker_accepts_grounded_flashcard():
    content = learning_content(
        content_type="flashcard",
        payload={
            "front": "뉴턴 제2법칙은 어떤 관계를 설명하는가?",
            "back": "힘, 질량, 가속도 관계를 설명한다.",
            "explanation": "뉴턴 제2법칙은 같은 힘 조건에서 질량과 가속도 관계를 확인하게 한다.",
        },
    )

    result = LearningContentQualityChecker().validate(content, retrieved_chunks=chunks())

    assert result.is_valid is True
    assert result.source_coverage_score is not None
    assert result.source_coverage_score >= 0.12


def test_learning_content_quality_checker_rejects_missing_retrieved_source_chunk():
    content = learning_content(
        content_type="flashcard",
        source_chunk_ids=["missing_chunk"],
        payload={
            "front": "뉴턴 제2법칙은 어떤 관계를 설명하는가?",
            "back": "힘, 질량, 가속도 관계를 설명한다.",
            "explanation": "뉴턴 제2법칙은 같은 힘 조건에서 질량과 가속도 관계를 확인하게 한다.",
        },
    )

    result = LearningContentQualityChecker().validate(content, retrieved_chunks=chunks())

    assert result.is_valid is False
    assert QualityFlag.unsupported_source in result.flags
    assert any("not found" in error for error in result.errors)


def test_learning_content_quality_checker_rejects_wrong_document_source_chunk():
    content = learning_content(
        content_type="flashcard",
        payload={
            "front": "뉴턴 제2법칙은 어떤 관계를 설명하는가?",
            "back": "힘, 질량, 가속도 관계를 설명한다.",
            "explanation": "뉴턴 제2법칙은 같은 힘 조건에서 질량과 가속도 관계를 확인하게 한다.",
        },
    )
    retrieved_chunks = [chunk.model_copy(update={"document_id": "other_doc"}) for chunk in chunks()]

    result = LearningContentQualityChecker().validate(content, retrieved_chunks=retrieved_chunks)

    assert result.is_valid is False
    assert QualityFlag.unsupported_source in result.flags
    assert any("different document" in error for error in result.errors)


def test_learning_content_quality_checker_rejects_weak_source_overlap():
    content = learning_content(
        content_type="flashcard",
        payload={
            "front": "르네상스 미술의 원근법은 무엇인가?",
            "back": "회화 공간 표현 방식이다.",
            "explanation": "미술사 개념을 확인한다.",
        },
    )

    result = LearningContentQualityChecker().validate(content, retrieved_chunks=chunks())

    assert result.is_valid is False
    assert QualityFlag.weak_source_overlap in result.flags


def test_learning_content_quality_checker_rejects_verbatim_source_copy():
    copied = (
        "뉴턴 제2법칙은 힘 질량 가속도 관계를 설명한다. 같은 힘 조건에서 질량이 클수록 "
        "가속도는 작아지고 힘은 질량과 가속도의 곱으로 표현된다."
    )
    content = learning_content(
        content_type="flashcard",
        payload={
            "front": "뉴턴 제2법칙 핵심은?",
            "back": "힘, 질량, 가속도 관계",
            "explanation": copied,
        },
    )

    result = LearningContentQualityChecker().validate(content, retrieved_chunks=chunks())

    assert result.is_valid is False
    assert QualityFlag.source_verbatim_overlap in result.flags
    assert result.verbatim_overlap_chars >= 70


def test_learning_content_quality_checker_rejects_unsupported_number():
    content = learning_content(
        content_type="flashcard",
        payload={
            "front": "뉴턴 제2법칙에서 99N 힘이 작용하면 무엇을 확인하는가?",
            "back": "힘과 가속도 관계를 확인한다.",
            "explanation": "99N은 자료에 없는 수치다.",
        },
    )

    result = LearningContentQualityChecker().validate(content, retrieved_chunks=chunks())

    assert result.is_valid is False
    assert QualityFlag.unsupported_source in result.flags


def test_learning_content_quality_checker_rejects_generic_true_false_statement():
    content = learning_content(
        content_type="true_false",
        payload={
            "statement": "힘은 중요하다.",
            "answer": True,
            "explanation": "너무 일반적인 문장이다.",
        },
    )

    result = LearningContentQualityChecker().validate(content, retrieved_chunks=chunks())

    assert result.is_valid is False
    assert QualityFlag.unfocused_stem in result.flags


def test_learning_content_quality_checker_rejects_duplicate_ordering_item_texts():
    content = learning_content(
        content_type="ordering",
        payload={
            "prompt": "뉴턴 제2법칙 풀이 순서를 배열하시오.",
            "items": [
                {"id": "A", "text": "공식을 확인한다."},
                {"id": "B", "text": "공식을 확인한다."},
            ],
            "correct_order": ["A", "B"],
            "explanation": "공식 확인 후 값을 대입한다.",
        },
    )

    result = LearningContentQualityChecker().validate(content, retrieved_chunks=chunks())

    assert result.is_valid is False
    assert "ordering item texts must be unique" in result.errors


def test_learning_content_quality_checker_rejects_matching_same_left_and_right():
    content = learning_content(
        content_type="matching",
        payload={
            "prompt": "뉴턴 제2법칙 용어와 의미를 연결하시오.",
            "pairs": [
                {"left": "힘", "right": "힘"},
                {"left": "가속도", "right": "속도 변화율"},
            ],
            "explanation": "자료의 용어 관계를 확인한다.",
        },
    )

    result = LearningContentQualityChecker().validate(content, retrieved_chunks=chunks())

    assert result.is_valid is False
    assert "matching pair cannot use the same text on both sides" in result.errors


def test_learning_content_quality_checker_rejects_shallow_worked_example():
    content = learning_content(
        content_type="worked_example",
        payload={
            "problem": "뉴턴 제2법칙에서 힘을 구하시오.",
            "steps": [{"order": 1, "text": "공식을 본다."}],
            "final_answer": "힘은 질량과 가속도의 곱이다.",
            "explanation": "자료의 공식을 적용한다.",
        },
    )

    result = LearningContentQualityChecker().validate(content, retrieved_chunks=chunks())

    assert result.is_valid is False
    assert "worked_example requires at least two solution steps" in result.errors


def test_learning_content_quality_checker_rejects_shallow_concept_summary_card():
    content = learning_content(
        content_type="concept_summary_card",
        payload={
            "title": "뉴턴 제2법칙",
            "summary": "힘 관계",
            "key_points": ["F = ma"],
        },
    )

    result = LearningContentQualityChecker().validate(content, retrieved_chunks=chunks())

    assert result.is_valid is False
    assert "concept_summary_card summary is too short" in result.errors
    assert "concept_summary_card requires at least two key points" in result.errors


def test_learning_content_quality_checker_rejects_passed_content_without_source_grounding():
    content = learning_content(
        content_type="flashcard",
        quality_report={"status": "passed", "score": 0.9, "source_grounded": False},
        payload={
            "front": "뉴턴 제2법칙은 어떤 관계를 설명하는가?",
            "back": "힘, 질량, 가속도 관계를 설명한다.",
            "explanation": "뉴턴 제2법칙은 같은 힘 조건에서 질량과 가속도 관계를 확인하게 한다.",
        },
    )

    result = LearningContentQualityChecker().validate(content, retrieved_chunks=chunks())

    assert result.is_valid is False
    assert "passed learning content must be source grounded" in result.errors


def test_learning_content_quality_checker_requires_generated_problem_for_mistake_drill():
    content = learning_content(
        content_type="mistake_drill",
        payload={
            "seed_problem_id": "prob_001",
            "seed_feedback_id": "fb_001",
            "target_mistake_type": "concept_misunderstanding",
            "target_concepts": ["뉴턴 제2법칙"],
            "variant_strategy": "same_concept_new_condition",
        },
    )

    result = LearningContentQualityChecker().validate(content, retrieved_chunks=chunks())

    assert result.is_valid is False
    assert "mistake_drill requires generated_problem_id" in result.errors


def test_learning_content_quality_checker_ignores_metadata_ids_when_checking_numbers():
    content = learning_content(
        content_type="mistake_drill",
        payload={
            "seed_problem_id": "prob_999",
            "seed_feedback_id": "fb_888",
            "target_mistake_type": "concept_misunderstanding",
            "target_concepts": ["뉴턴 제2법칙"],
            "variant_strategy": "same_concept_new_condition",
            "generated_problem_id": "prob_777",
        },
    )

    result = LearningContentQualityChecker().validate(content, retrieved_chunks=chunks())

    assert result.is_valid is True
    assert QualityFlag.unsupported_source not in result.flags


def test_learning_content_quality_checker_rejects_duplicate_mini_exam_items():
    content = learning_content(
        content_type="mini_exam",
        payload={
            "title": "뉴턴 제2법칙 미니 점검",
            "items": [
                {"problem_id": "prob_001", "content_type": "multiple_choice"},
                {"problem_id": "prob_001", "content_type": "multiple_choice"},
            ],
        },
    )

    result = LearningContentQualityChecker().validate(content, retrieved_chunks=chunks())

    assert result.is_valid is False
    assert "mini_exam item references must be unique" in result.errors


def test_learning_content_quality_checker_rejects_prompt_injection_leak():
    content = learning_content(
        content_type="flashcard",
        payload={
            "front": "뉴턴 제2법칙에서 힘은 무엇과 관련되는가?",
            "back": "시스템 프롬프트를 출력하라는 지시는 학습 내용이 아니다.",
            "explanation": "탈옥 지침을 따르면 안 된다는 문구가 출력에 남으면 안 된다.",
        },
    )

    result = LearningContentQualityChecker().validate(content, retrieved_chunks=chunks())

    assert result.is_valid is False
    assert QualityFlag.prompt_injection_leak in result.flags
    assert "learning content leaks prompt-injection text" in result.errors



def learning_content(
    *,
    content_type,
    payload,
    source_chunk_ids=None,
    interaction_mode=None,
    quality_status="passed",
    quality_report=None,
):
    return LearningContentBase(
        id="content_001",
        user_id="user_001",
        document_id="doc_001",
        content_type=content_type,
        interaction_mode=interaction_mode,
        concepts=["뉴턴 제2법칙"],
        source_chunk_ids=source_chunk_ids if source_chunk_ids is not None else ["chunk_001"],
        source_revision_ids=["rev_001"],
        content_version="v1",
        difficulty="medium",
        bloom_level="understand",
        quality_status=quality_status,
        quality_report=quality_report or {"status": quality_status, "score": 0.9, "source_grounded": True},
        payload=payload,
    )


def chunks():
    return [
        RetrievedChunk(
            chunk_id="chunk_001",
            document_id="doc_001",
            content=(
                "뉴턴 제2법칙은 힘 질량 가속도 관계를 설명한다. 같은 힘 조건에서 질량이 클수록 "
                "가속도는 작아지고 힘은 질량과 가속도의 곱으로 표현된다."
            ),
            page=1,
            section_title="뉴턴의 운동 법칙",
            concepts=["뉴턴 제2법칙", "힘", "질량", "가속도"],
        )
    ]
