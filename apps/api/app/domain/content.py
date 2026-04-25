from __future__ import annotations

from datetime import date

from app.domain.models import AppState, GamificationState, LearnerProfile, MasteryState
from app.domain.planner import generate_plan


TODAY = date(2026, 4, 10)


def score_to_label(score: int) -> str:
    if score >= 85:
        return "안정권"
    if score >= 70:
        return "상승권"
    if score >= 55:
        return "교정 필요"
    return "기초 재정비"


def default_profile() -> LearnerProfile:
    return LearnerProfile(
        nickname="홍길동",
        exam_date="2026-11-19",
        subject_targets={
            "korean": 82,
            "math": 88,
            "english": 80,
            "inquiry1": 78,
            "inquiry2": 78,
        },
        weekly_study_hours=18,
        daily_minutes=120,
        weak_units=["미분", "함수의 증가와 감소", "접선"],
        study_mood="실전 위주",
    )


def default_mastery(bundle: dict) -> list[MasteryState]:
    return [
        MasteryState(
            id=concept["id"],
            title=concept["title"],
            score=int(concept.get("baselineScore", 60)),
            trend=str(concept.get("baselineTrend", "+0")),
            risk=str(concept.get("baselineRisk", "중간")),
            lesson_pack_id=concept.get("lessonPackId"),
            problem_set_id=concept.get("problemSetId"),
            course_id=concept.get("courseId"),
            course_title=concept.get("courseTitle"),
        )
        for concept in bundle.get("concepts", [])
    ]


def _first_lesson_pack(bundle: dict) -> dict:
    return bundle["lessonPacks"][0]


def _first_problem_set(bundle: dict) -> dict:
    return bundle["problemSets"][0]


def bundle_question_scene(bundle: dict, kind: str) -> dict:
    return bundle.get("microScenes", {}).get(kind) or bundle.get("microScenes", {}).get("recap")


def _find_lesson_pack(bundle: dict, lesson_pack_id: str) -> dict | None:
    for lesson_pack in bundle.get("lessonPacks", []):
        if lesson_pack["id"] == lesson_pack_id:
            return lesson_pack
    return None


def _find_problem_set(bundle: dict, problem_set_id: str) -> dict | None:
    for problem_set in bundle.get("problemSets", []):
        if problem_set["id"] == problem_set_id:
            return problem_set
    return None


def select_active_content(bundle: dict, mastery: list[MasteryState]) -> tuple[dict, dict, dict]:
    concept_map = {concept["id"]: concept for concept in bundle.get("concepts", [])}
    weakest_first = sorted(mastery, key=lambda item: item.score)

    for mastery_state in weakest_first:
        concept = concept_map.get(mastery_state.id)
        if concept is None:
            continue
        lesson_pack = _find_lesson_pack(bundle, concept["lessonPackId"])
        problem_set = _find_problem_set(bundle, concept["problemSetId"])
        if lesson_pack and problem_set and problem_set.get("problems"):
            return lesson_pack, problem_set, problem_set["problems"][0]

    lesson_pack = _first_lesson_pack(bundle)
    problem_set = _first_problem_set(bundle)
    return lesson_pack, problem_set, problem_set["problems"][0]


def seed_state(user_id: str, bundle: dict) -> AppState:
    profile = default_profile()
    mastery = default_mastery(bundle)
    lesson_pack, problem_set, primary_problem = select_active_content(bundle, mastery)
    return AppState(
        user_id=user_id,
        profile=profile,
        mastery=mastery,
        plan=generate_plan(profile, mastery, TODAY, bundle_id=bundle["bundleId"]),
        content_bundle_id=bundle["bundleId"],
        active_lesson_id=lesson_pack["id"],
        active_problem_set_id=problem_set["id"],
        lesson_scenes=lesson_pack.get("scenes", []),
        practice_problem_set=problem_set,
        practice_problem=primary_problem,
        plan_strategy={},
        survey_completed=False,
        survey_step=0,
        diagnostic_session_id="",
        diagnostic_answers={},
        attempts=[],
        documents=[],
        mistake_notes=[],
        gamification=GamificationState(
            streak_days=0,
            last_activity_date="",
            xp=0,
            level=1,
            active_theme_id="chalk-amber",
            unlocked_theme_ids=["chalk-amber"],
            recent_unlocks=[],
            best_streak_days=0,
            recovery_tokens=0,
            lesson_completions=0,
            practice_attempts=0,
            solved_attempts=0,
            review_sessions=0,
            question_count=0,
            daily_flows=[],
            milestone_ids=[],
        ),
    )
