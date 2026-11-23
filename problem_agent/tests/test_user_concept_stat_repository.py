import pytest

from app.models import UserConceptStat
from app.repositories.user_concept_stat_repository import UserConceptStatRepository
from app.schemas.problems import LearningState


def test_mastery_increases_and_decreases(db_session):
    repo = UserConceptStatRepository(db_session)

    correct_result = repo.update_for_feedback(
        user_id="user_001",
        concepts=["뉴턴 제2법칙"],
        is_correct=True,
        mistake_type="none",
    )
    wrong_result = repo.update_for_feedback(
        user_id="user_001",
        concepts=["뉴턴 제2법칙"],
        is_correct=False,
        mistake_type="concept_misunderstanding",
    )

    stat = db_session.get(UserConceptStat, {"user_id": "user_001", "concept": "뉴턴 제2법칙"})
    assert stat.attempts == 2
    assert stat.correct_count == 1
    assert stat.wrong_count == 1
    assert stat.mastery == pytest.approx(0.47)
    assert correct_result.mastery_updates[0].mastery == pytest.approx(0.55)
    assert wrong_result.mastery_updates[0].mastery == pytest.approx(0.47)


def test_mastery_is_clamped_between_zero_and_one(db_session):
    repo = UserConceptStatRepository(db_session)
    high = UserConceptStat(user_id="user_001", concept="상한 개념", mastery=0.98)
    low = UserConceptStat(user_id="user_001", concept="하한 개념", mastery=0.02)
    db_session.add_all([high, low])
    db_session.commit()

    repo.update_for_feedback(
        user_id="user_001",
        concepts=["상한 개념"],
        is_correct=True,
        mistake_type="none",
    )
    repo.update_for_feedback(
        user_id="user_001",
        concepts=["하한 개념"],
        is_correct=False,
        mistake_type="missing_key_concept",
    )

    assert db_session.get(UserConceptStat, {"user_id": "user_001", "concept": "상한 개념"}).mastery == 1.0
    assert db_session.get(UserConceptStat, {"user_id": "user_001", "concept": "하한 개념"}).mastery == 0.0


def test_correct_answer_with_hints_increases_mastery_less(db_session):
    repo = UserConceptStatRepository(db_session)

    no_hint = repo.update_for_feedback(
        user_id="user_001",
        concepts=["힌트 없는 개념"],
        is_correct=True,
        mistake_type="none",
        hint_count=0,
    )
    with_hints = repo.update_for_feedback(
        user_id="user_001",
        concepts=["힌트 사용 개념"],
        is_correct=True,
        mistake_type="none",
        hint_count=3,
    )

    assert no_hint.mastery_updates[0].mastery == pytest.approx(0.55)
    assert with_hints.mastery_updates[0].mastery == pytest.approx(0.52)


def test_low_confidence_correct_answer_increases_mastery_less(db_session):
    repo = UserConceptStatRepository(db_session)

    result = repo.update_for_feedback(
        user_id="user_001",
        concepts=["확신 낮은 정답"],
        is_correct=True,
        mistake_type="none",
        confidence_level=1,
        learning_state=LearningState.fragile_mastery,
    )

    assert result.mastery_updates[0].mastery == pytest.approx(0.535)


def test_high_confidence_wrong_answer_decreases_mastery_more(db_session):
    repo = UserConceptStatRepository(db_session)

    result = repo.update_for_feedback(
        user_id="user_001",
        concepts=["확신 높은 오답"],
        is_correct=False,
        mistake_type="concept_misunderstanding",
        confidence_level=4,
        learning_state=LearningState.high_confidence_misconception,
    )

    assert result.mastery_updates[0].mastery == pytest.approx(0.4)


def test_partial_understanding_reduces_wrong_answer_penalty(db_session):
    repo = UserConceptStatRepository(db_session)

    result = repo.update_for_feedback(
        user_id="user_001",
        concepts=["부분 이해"],
        is_correct=False,
        mistake_type="incomplete_answer",
        confidence_level=2,
        score=3,
        max_score=5,
        learning_state=LearningState.partial_understanding,
    )

    assert result.mastery_updates[0].mastery == pytest.approx(0.444)


def test_repeated_wrong_answer_adds_concept_to_review_queue(db_session):
    repo = UserConceptStatRepository(db_session)

    first_result = repo.update_for_feedback(
        user_id="user_001",
        concepts=["뉴턴 제2법칙"],
        is_correct=False,
        mistake_type="concept_misunderstanding",
    )
    second_result = repo.update_for_feedback(
        user_id="user_001",
        concepts=["뉴턴 제2법칙"],
        is_correct=False,
        mistake_type="concept_misunderstanding",
    )

    assert first_result.recommended_review == []
    assert second_result.recommended_review == ["뉴턴 제2법칙"]
    assert second_result.mastery_updates[0].should_review is True


def test_update_deduplicates_concepts_and_mistake_types(db_session):
    repo = UserConceptStatRepository(db_session)

    result = repo.update_for_feedback(
        user_id="user_001",
        concepts=["뉴턴 제2법칙", "뉴턴 제2법칙", " "],
        is_correct=False,
        mistake_type="concept_misunderstanding",
    )
    repo.update_for_feedback(
        user_id="user_001",
        concepts=["뉴턴 제2법칙"],
        is_correct=False,
        mistake_type="concept_misunderstanding",
    )

    stat = db_session.get(UserConceptStat, {"user_id": "user_001", "concept": "뉴턴 제2법칙"})
    assert stat.attempts == 2
    assert stat.mistake_types == ["concept_misunderstanding"]
    assert [update.concept for update in result.mastery_updates] == ["뉴턴 제2법칙"]
