from __future__ import annotations

from copy import deepcopy
from datetime import date, timedelta
from typing import Any

from app.domain.models import LearnerProfile, MasteryState, StudyDay, StudyTask


DEFAULT_BUNDLE_ID = "suneung-math-curriculum-v1"


def _track_name(concept_id: str) -> str:
    if concept_id.startswith(("common1", "common2")):
        return "공통수학"
    if concept_id.startswith("algebra"):
        return "대수"
    if concept_id.startswith(("calc1", "calc2")):
        return "미적분"
    if concept_id.startswith("probstat"):
        return "확률과 통계"
    if concept_id.startswith("geometry"):
        return "기하"
    return "수학"


def _unit_name(item: MasteryState) -> str:
    if " - " in item.title:
        return item.title.split(" - ", 1)[1]
    return item.title


def _phase_name(days_left: int) -> str:
    if days_left > 210:
        return "개념 체력 구간"
    if days_left > 120:
        return "약점 정복 구간"
    if days_left > 60:
        return "실전 적응 구간"
    if days_left > 20:
        return "실전 압축 구간"
    return "파이널 구간"


def _phase_task_minutes(days_left: int) -> tuple[int, int, int]:
    if days_left > 210:
        return (28, 34, 16)
    if days_left > 120:
        return (24, 40, 18)
    if days_left > 60:
        return (20, 46, 20)
    if days_left > 20:
        return (16, 50, 22)
    return (12, 52, 24)


def _task_status(offset: int, index: int) -> str:
    if offset == 0:
        return "ready" if index == 0 else "locked"
    return "planned"


def _target_intensity(profile: LearnerProfile) -> int:
    target = profile.math_target_score
    if target >= 96:
        return 3
    if target >= 92:
        return 2
    if target >= 88:
        return 1
    return 0


def _urgency(profile: LearnerProfile, item: MasteryState) -> int:
    risk_bonus = {"매우 높음": 18, "높음": 12, "중간": 6, "낮음": 0}.get(item.risk, 0)
    weak_bonus = 0
    for weak in profile.weak_units:
        if weak and (weak in item.title or weak in item.id):
            weak_bonus = 10
            break
    return max(8, (100 - item.score) + risk_bonus + weak_bonus)


def _priority_score(profile: LearnerProfile, item: MasteryState, days_left: int) -> float:
    intensity = _target_intensity(profile)
    weakness = (100 - item.score) * 1.55
    risk_bonus = {"매우 높음": 20, "높음": 14, "중간": 7, "낮음": 1}.get(item.risk, 0)
    weak_bonus = 0
    for weak in profile.weak_units:
        if weak and (weak in item.title or weak in item.id):
            weak_bonus = 16
            break
    target_bonus = intensity * (10 if item.score < 72 else 5)
    deadline_bonus = 14 if days_left <= 45 and item.score < 70 else 0
    recovery_bonus = 8 if days_left <= 20 and item.score < 82 else 0
    return weakness + risk_bonus + weak_bonus + target_bonus + deadline_bonus + recovery_bonus


def _question_signal_maps(
    question_signals: list[dict[str, Any]] | None,
) -> tuple[dict[str, int], dict[str, dict[str, int]]]:
    unit_weights: dict[str, int] = {}
    unit_categories: dict[str, dict[str, int]] = {}
    for signal in question_signals or []:
        concept_id = str(signal.get("conceptId") or signal.get("concept_id") or "").strip()
        if not concept_id:
            continue
        weight = max(1, int(signal.get("weight") or 1))
        category = str(signal.get("category") or "concept").strip() or "concept"
        unit_weights[concept_id] = unit_weights.get(concept_id, 0) + weight
        category_map = unit_categories.setdefault(concept_id, {})
        category_map[category] = category_map.get(category, 0) + weight
    return unit_weights, unit_categories


def _question_bonus(
    item: MasteryState,
    unit_weights: dict[str, int],
    unit_categories: dict[str, dict[str, int]],
) -> float:
    base = unit_weights.get(item.id, 0)
    categories = unit_categories.get(item.id, {})
    return (
        base * 7
        + categories.get("basic", 0) * 4
        + categories.get("concept", 0) * 5
        + categories.get("process", 0) * 3
        + categories.get("application", 0) * 2
        + categories.get("killer", 0) * 4
    )


def _question_lesson_bonus(unit_categories: dict[str, int]) -> int:
    return unit_categories.get("basic", 0) * 4 + unit_categories.get("concept", 0) * 3


def _question_practice_bonus(unit_categories: dict[str, int]) -> int:
    return (
        unit_categories.get("process", 0) * 4
        + unit_categories.get("application", 0) * 4
        + unit_categories.get("killer", 0) * 5
    )


def _question_review_bonus(unit_categories: dict[str, int]) -> int:
    return max(0, sum(unit_categories.values()) * 2)


def _question_focus_line(primary: MasteryState, categories: dict[str, int]) -> str:
    if not categories:
        return f"{_unit_name(primary)}를 먼저 잡고 바로 문제에 이어 붙입니다."
    if categories.get("basic", 0) + categories.get("concept", 0) >= categories.get("process", 0) + categories.get("application", 0):
        return f"{_unit_name(primary)}에서 자주 멈춘 개념 질문을 먼저 정리하고 설명을 더 촘촘하게 다시 밟습니다."
    if categories.get("killer", 0):
        return f"{_unit_name(primary)}의 고난도 질문이 많아 오늘은 킬러 접근 순서를 먼저 고정합니다."
    return f"{_unit_name(primary)}에서 자주 막힌 풀이 순서를 다시 세우고 바로 문제로 연결합니다."


def _pick_question_aware_unit(
    profile: LearnerProfile,
    mastery: list[MasteryState],
    *,
    days_left: int,
    recent_units: list[str],
    recent_tracks: list[str],
    unit_weights: dict[str, int],
    unit_categories: dict[str, dict[str, int]],
    excluded_ids: set[str] | None = None,
    due_review_ids: set[str] | None = None,
) -> MasteryState:
    excluded = excluded_ids or set()
    due_review_ids = due_review_ids or set()
    scored: list[tuple[float, MasteryState]] = []
    for item in mastery:
        if item.id in excluded:
            continue
        score = _priority_score(profile, item, days_left)
        score += _question_bonus(item, unit_weights, unit_categories)
        if item.id in due_review_ids:
            score += 12
        score -= recent_tracks[-2:].count(_track_name(item.id)) * 7
        score -= recent_units[-3:].count(item.id) * 18
        scored.append((score, item))
    scored.sort(key=lambda pair: (-pair[0], pair[1].score))
    return scored[0][1] if scored else mastery[0]


def _review_offsets(item: MasteryState, profile: LearnerProfile, days_left: int) -> list[int]:
    intensity = _target_intensity(profile)
    if item.score < 45:
        return [1, 2, 4, 7, 14]
    if item.score < 60:
        return [1, 3, 6, 10 + intensity]
    if item.score < 75:
        return [2, 5, 9 + intensity]
    if days_left <= 45:
        return [2, 4, 7]
    return [3, 7, 14]


def _pick_priority_unit(
    profile: LearnerProfile,
    mastery: list[MasteryState],
    *,
    days_left: int,
    recent_units: list[str],
    recent_tracks: list[str],
    excluded_ids: set[str] | None = None,
    due_review_ids: set[str] | None = None,
) -> MasteryState:
    excluded = excluded_ids or set()
    due_review_ids = due_review_ids or set()
    scored: list[tuple[float, MasteryState]] = []
    for item in mastery:
        if item.id in excluded:
            continue
        score = _priority_score(profile, item, days_left)
        if item.id in due_review_ids:
            score += 12
        score -= recent_tracks[-2:].count(_track_name(item.id)) * 7
        score -= recent_units[-3:].count(item.id) * 18
        scored.append((score, item))
    scored.sort(key=lambda pair: (-pair[0], pair[1].score))
    return scored[0][1] if scored else mastery[0]


def _killer_task_title(primary: MasteryState, killer: MasteryState) -> str:
    if killer.id == primary.id:
        return f"{_track_name(killer.id)} · {_unit_name(killer)} 고난도 연결 문제"
    return (
        f"{_track_name(primary.id)} · {_unit_name(primary)}에서 "
        f"{_track_name(killer.id)} · {_unit_name(killer)}까지 킬러 연결"
    )


def _phase_settings(days_left: int, intensity: int) -> dict[str, int | bool]:
    if days_left > 210:
        return {"checkpointEvery": 7, "killerSpacing": 6, "killerEnabled": intensity >= 2}
    if days_left > 120:
        return {"checkpointEvery": 7, "killerSpacing": 5, "killerEnabled": intensity >= 1}
    if days_left > 60:
        return {"checkpointEvery": 6, "killerSpacing": 4, "killerEnabled": True}
    if days_left > 20:
        return {"checkpointEvery": 5, "killerSpacing": 3, "killerEnabled": True}
    return {"checkpointEvery": 4, "killerSpacing": 2, "killerEnabled": True}


def _focus_rotation(profile: LearnerProfile, mastery: list[MasteryState]) -> list[MasteryState]:
    weighted: list[MasteryState] = []
    ranked = sorted(mastery, key=lambda item: (_urgency(profile, item) * -1, item.score))
    for item in ranked:
        weighted.extend([item] * max(1, min(4, _urgency(profile, item) // 18)))
    return weighted or mastery


def _pick_distinct(
    rotation: list[MasteryState],
    start_index: int,
    excluded_ids: set[str] | None = None,
) -> MasteryState:
    excluded = excluded_ids or set()
    for offset in range(len(rotation)):
        candidate = rotation[(start_index + offset) % len(rotation)]
        if candidate.id not in excluded:
            return candidate
    return rotation[start_index % len(rotation)]


def _daily_target_minutes(profile: LearnerProfile, days_left: int) -> int:
    weekly_budget = max(360, profile.weekly_study_hours * 60)
    base_daily = max(70, round(weekly_budget / 6))
    base_daily += _target_intensity(profile) * 10
    if days_left <= 60:
        base_daily += 12
    if days_left <= 20:
        base_daily += 8
    return min(profile.daily_minutes, base_daily)


def _lesson_title(profile: LearnerProfile, item: MasteryState, days_left: int) -> str:
    track = _track_name(item.id)
    unit = _unit_name(item)
    if item.score < 50:
        return f"{track} · {unit} 개념 회복 강의"
    if item.score < 65:
        return f"{track} · {unit} 빈칸 메우기 강의"
    if _target_intensity(profile) >= 2 and days_left <= 180:
        return f"{track} · {unit} 고난도 구조 강의"
    return f"{track} · {unit} AI 칠판 강의"


def _practice_title(profile: LearnerProfile, primary: MasteryState) -> str:
    track = _track_name(primary.id)
    unit = _unit_name(primary)
    if primary.score < 50:
        return f"{track} · {unit} 진단 보정 문제 묶음"
    if _target_intensity(profile) >= 2 and primary.score >= 60:
        return f"{track} · {unit} 한계돌파 연결 문제 묶음"
    return f"{track} · {unit} 핵심 문제 묶음"


def _review_title(primary: MasteryState, review: MasteryState) -> str:
    return (
        f"{_track_name(primary.id)} · {_unit_name(primary)} 오답 복기 + "
        f"{_track_name(review.id)} · {_unit_name(review)} 다시 보기"
    )


def _launch_payload(
    mode: str,
    item: MasteryState | None = None,
    *,
    bundle_id: str = DEFAULT_BUNDLE_ID,
    lesson_id: str | None = None,
    problem_set_id: str | None = None,
    problem_id: str | None = None,
) -> dict[str, str]:
    if mode == "review":
        return {
            "mode": "review",
            "href": "/review",
            "ctaLabel": "복습 보기",
        }

    resolved_lesson_id = lesson_id or (item.lesson_pack_id if item else None)
    resolved_problem_set_id = problem_set_id or (item.problem_set_id if item else None)
    payload = {
        "mode": mode,
        "href": "/lesson" if mode == "lesson" else "/practice",
        "ctaLabel": "강의 시작" if mode == "lesson" else "문제 풀기",
    }
    if bundle_id:
        payload["bundleId"] = bundle_id
    if resolved_lesson_id:
        payload["lessonId"] = resolved_lesson_id
    if resolved_problem_set_id:
        payload["problemSetId"] = resolved_problem_set_id
    if problem_id:
        payload["problemId"] = problem_id
    return payload


def _build_standard_tasks(
    profile: LearnerProfile,
    current_date: date,
    offset: int,
    primary: MasteryState,
    secondary: MasteryState,
    review: MasteryState,
    days_left: int,
    *,
    bundle_id: str,
) -> list[StudyTask]:
    lesson_minutes, practice_minutes, review_minutes = _phase_task_minutes(days_left)
    intensity = _target_intensity(profile)
    return [
        StudyTask(
            id=f"{current_date.isoformat()}-lesson",
            title=_lesson_title(profile, primary, days_left),
            type="lesson",
            minutes=lesson_minutes + (4 if primary.score < 55 else 0),
            status=_task_status(offset, 0),
            launch=_launch_payload("lesson", primary, bundle_id=bundle_id),
        ),
        StudyTask(
            id=f"{current_date.isoformat()}-practice",
            title=_practice_title(profile, primary),
            type="practice",
            minutes=practice_minutes + (4 if intensity >= 2 else 0),
            status=_task_status(offset, 1),
            launch=_launch_payload("practice", primary, bundle_id=bundle_id),
        ),
        StudyTask(
            id=f"{current_date.isoformat()}-review",
            title=_review_title(primary, review),
            type="review",
            minutes=review_minutes,
            status=_task_status(offset, 2),
            launch=_launch_payload("review"),
        ),
    ]


def _build_checkpoint_tasks(
    profile: LearnerProfile,
    current_date: date,
    offset: int,
    primary: MasteryState,
    secondary: MasteryState,
    days_left: int,
    *,
    bundle_id: str,
) -> list[StudyTask]:
    lesson_minutes, practice_minutes, review_minutes = _phase_task_minutes(days_left)
    return [
        StudyTask(
            id=f"{current_date.isoformat()}-lesson",
            title=f"{_track_name(primary.id)} · {_unit_name(primary)} 주간 리캡 강의",
            type="lesson",
            minutes=max(12, lesson_minutes - 4),
            status=_task_status(offset, 0),
            launch=_launch_payload("lesson", primary, bundle_id=bundle_id),
        ),
        StudyTask(
            id=f"{current_date.isoformat()}-practice",
            title=(
                f"{_track_name(primary.id)} · {_unit_name(primary)} + "
                f"{_track_name(secondary.id)} · {_unit_name(secondary)} 혼합 점검 문제 묶음"
            ),
            type="practice",
            minutes=practice_minutes + 6,
            status=_task_status(offset, 1),
            launch=_launch_payload("practice", primary, bundle_id=bundle_id),
        ),
        StudyTask(
            id=f"{current_date.isoformat()}-review",
            title="수학 · 주간 오답 정리와 취약 개념 다시 보기",
            type="review",
            minutes=review_minutes + 6,
            status=_task_status(offset, 2),
            launch=_launch_payload("review"),
        ),
    ]


def generate_plan(
    profile: LearnerProfile,
    mastery: list[MasteryState],
    today: date,
    bundle_id: str = DEFAULT_BUNDLE_ID,
    question_signals: list[dict[str, Any]] | None = None,
) -> list[StudyDay]:
    exam_date = date.fromisoformat(profile.exam_date)
    horizon = max(1, (exam_date - today).days + 1)
    daily_target = _daily_target_minutes(profile, horizon)
    intensity = _target_intensity(profile)
    unit_weights, unit_categories = _question_signal_maps(question_signals)
    plan: list[StudyDay] = []
    review_schedule: dict[int, list[MasteryState]] = {}
    recent_units: list[str] = []
    recent_tracks: list[str] = []

    for offset in range(horizon):
        current = today + timedelta(days=offset)
        days_left = max(0, (exam_date - current).days)
        due_reviews = review_schedule.pop(offset, [])
        due_review_ids = {item.id for item in due_reviews}
        primary = _pick_question_aware_unit(
            profile,
            mastery,
            days_left=days_left,
            recent_units=recent_units,
            recent_tracks=recent_tracks,
            unit_weights=unit_weights,
            unit_categories=unit_categories,
            due_review_ids=due_review_ids,
        )
        secondary = _pick_question_aware_unit(
            profile,
            mastery,
            days_left=days_left,
            recent_units=recent_units,
            recent_tracks=recent_tracks,
            unit_weights=unit_weights,
            unit_categories=unit_categories,
            excluded_ids={primary.id},
            due_review_ids=due_review_ids,
        )
        review = next(
            (item for item in due_reviews if item.id not in {primary.id, secondary.id}),
            _pick_question_aware_unit(
                profile,
                mastery,
                days_left=days_left,
                recent_units=recent_units,
                recent_tracks=recent_tracks,
                unit_weights=unit_weights,
                unit_categories=unit_categories,
                excluded_ids={primary.id, secondary.id},
                due_review_ids=due_review_ids,
            ),
        )
        label = "오늘" if offset == 0 else f"D+{offset}"
        phase_config = _phase_settings(days_left, intensity)
        checkpoint_day = (offset + 1) % int(phase_config["checkpointEvery"]) == 0
        primary_question_categories = unit_categories.get(primary.id, {})
        tasks = (
            _build_checkpoint_tasks(profile, current, offset, primary, secondary, days_left, bundle_id=bundle_id)
            if checkpoint_day
            else _build_standard_tasks(
                profile,
                current,
                offset,
                primary,
                secondary,
                review,
                days_left,
                bundle_id=bundle_id,
            )
        )
        for task in tasks:
            if task.type == "lesson":
                task.minutes += _question_lesson_bonus(primary_question_categories)
                if primary_question_categories.get("basic", 0):
                    task.title = f"{_track_name(primary.id)} · {_unit_name(primary)} 기초 다시 세우기 강의"
                elif primary_question_categories.get("concept", 0):
                    task.title = f"{_track_name(primary.id)} · {_unit_name(primary)} 질문 회복 강의"
            elif task.type == "practice":
                task.minutes += _question_practice_bonus(primary_question_categories)
                if primary_question_categories.get("killer", 0):
                    task.title = f"{_track_name(primary.id)} · {_unit_name(primary)} 킬러 접근 문제 묶음"
                elif primary_question_categories.get("process", 0) or primary_question_categories.get("application", 0):
                    task.title = f"{_track_name(primary.id)} · {_unit_name(primary)} 질문 반영 문제 묶음"
            elif task.type == "review":
                task.minutes += min(16, _question_review_bonus(primary_question_categories))
        phase = _phase_name(days_left)
        if due_reviews:
            review_unit = due_reviews[0]
            tasks.append(
                StudyTask(
                    id=f"{current.isoformat()}-spaced-review",
                    title=f"{_track_name(review_unit.id)} · {_unit_name(review_unit)} 간격 복습",
                    type="review",
                    minutes=12 if review_unit.score >= 60 else 16,
                    status=_task_status(offset, len(tasks)),
                    launch=_launch_payload("review"),
                )
            )
        if phase_config["killerEnabled"] and (offset % int(phase_config["killerSpacing"]) == 0 or days_left <= 45):
            killer_unit = _pick_question_aware_unit(
                profile,
                mastery,
                days_left=days_left,
                recent_units=recent_units,
                recent_tracks=recent_tracks,
                unit_weights=unit_weights,
                unit_categories=unit_categories,
                excluded_ids={review.id},
                due_review_ids=due_review_ids,
            )
            tasks.append(
                StudyTask(
                    id=f"{current.isoformat()}-killer",
                    title=_killer_task_title(primary, killer_unit),
                    type="practice",
                    minutes=14 + intensity * 4,
                    status=_task_status(offset, len(tasks)),
                    launch=_launch_payload("practice", killer_unit, bundle_id=bundle_id),
                )
            )

        minutes_target = min(profile.daily_minutes, max(daily_target, sum(task.minutes for task in tasks)))
        theme = (
            f"{phase} · {primary.title} 중심 회복"
            if not checkpoint_day
            else f"{phase} · 주간 점검"
        )
        focus = (
            f"{_question_focus_line(primary, primary_question_categories)} "
            f"다음으로 {_unit_name(secondary)} 문제를 붙여 연습하고, "
            f"오늘 막힌 내용은 {_unit_name(review)} 간격 복습으로 다시 회수합니다."
            if not checkpoint_day
            else f"이번 주 약점인 {_unit_name(primary)}와 {_unit_name(secondary)}를 한 번에 섞어 실전 감각을 점검합니다."
        )
        plan.append(
            StudyDay(
                date=current.isoformat(),
                label=label,
                theme=theme,
                focus=focus,
                tasks=tasks,
                minutes_target=minutes_target,
            )
        )
        for revisit in _review_offsets(primary, profile, days_left):
            review_schedule.setdefault(offset + revisit, []).append(primary)
        if intensity >= 2 and secondary.score < 70:
            for revisit in (3, 8):
                review_schedule.setdefault(offset + revisit, []).append(secondary)
        recent_units.append(primary.id)
        recent_tracks.append(_track_name(primary.id))
        if len(recent_units) > 6:
            recent_units = recent_units[-6:]
        if len(recent_tracks) > 6:
            recent_tracks = recent_tracks[-6:]

    return plan


def apply_lesson_completion(plan: list[StudyDay]) -> list[StudyDay]:
    next_plan = deepcopy(plan)
    if not next_plan:
        return next_plan
    today = next_plan[0]
    for task in today.tasks:
        if task.type == "lesson":
            task.status = "done"
        elif task.type == "practice" and task.status == "locked":
            task.status = "ready"
        elif task.type == "review":
            task.status = "locked"
    today.focus = "개념 흐름은 잡혔습니다. 이제 바로 같은 단원 문제로 감각을 붙여볼까요?"
    return next_plan


def _insert_tomorrow_task(
    plan: list[StudyDay],
    title: str,
    task_type: str,
    minutes: int,
    *,
    launch: dict[str, str] | None = None,
) -> None:
    if len(plan) < 2:
        return
    tomorrow = plan[1]
    tomorrow.tasks.insert(
        0,
        StudyTask(
            id=f"{tomorrow.date}-{task_type}-carry",
            title=title,
            type=task_type,
            minutes=minutes,
            status="planned",
            launch=launch or {},
        ),
    )
    tomorrow.minutes_target = min(max(tomorrow.minutes_target, 0) + minutes, tomorrow.minutes_target + 25)


def reflow_incomplete_days(
    profile: LearnerProfile,
    mastery: list[MasteryState],
    current_plan: list[StudyDay],
    today: date,
    bundle_id: str = DEFAULT_BUNDLE_ID,
    question_signals: list[dict[str, Any]] | None = None,
) -> list[StudyDay]:
    if not current_plan:
        return generate_plan(profile, mastery, today, bundle_id=bundle_id, question_signals=question_signals)

    try:
        first_day = date.fromisoformat(current_plan[0].date)
    except ValueError:
        return generate_plan(profile, mastery, today, bundle_id=bundle_id, question_signals=question_signals)

    if first_day >= today:
        return deepcopy(current_plan)

    rebuilt = generate_plan(profile, mastery, today, bundle_id=bundle_id, question_signals=question_signals)
    carryover_tasks: list[StudyTask] = []
    carryover_titles: list[str] = []

    for day in current_plan:
        try:
            day_date = date.fromisoformat(day.date)
        except ValueError:
            continue
        if day_date >= today:
            continue
        for task in day.tasks:
            if task.status == "done":
                continue
            carryover_tasks.append(
                StudyTask(
                    id=f"{today.isoformat()}-{task.id}-carry",
                    title=f"{task.title} · 미완료 재배치",
                    type=task.type,
                    minutes=max(10, task.minutes),
                    status="ready" if not carryover_tasks else "planned",
                    launch=deepcopy(task.launch),
                )
            )
            if len(carryover_titles) < 3:
                carryover_titles.append(task.title)

    if not carryover_tasks or not rebuilt:
        return rebuilt

    rebuilt[0].tasks = carryover_tasks + rebuilt[0].tasks
    rebuilt[0].minutes_target += sum(task.minutes for task in carryover_tasks)
    rebuilt[0].theme = f"{rebuilt[0].theme} · 미완료 회복"
    rebuilt[0].focus = (
        "어제 끝내지 못한 공부 흐름부터 다시 이어서 잡습니다. "
        + ", ".join(carryover_titles)
        + " 순서로 회복한 뒤 오늘 계획으로 넘어갑니다."
    )
    return rebuilt


def apply_attempt_feedback(
    plan: list[StudyDay],
    solved: bool,
    problem: dict[str, str] | None = None,
    *,
    bundle_id: str = DEFAULT_BUNDLE_ID,
    lesson_id: str | None = None,
    problem_set_id: str | None = None,
    problem_id: str | None = None,
) -> list[StudyDay]:
    next_plan = deepcopy(plan)
    if not next_plan:
        return next_plan

    today = next_plan[0]
    problem_title = str((problem or {}).get("title") or "현재 단원")
    lesson_seen = False
    practice_seen = False
    carryover_review: list[str] = []

    for task in today.tasks:
        if task.type == "lesson":
            task.status = "done"
            lesson_seen = True
        elif task.type == "practice":
            task.status = "done" if solved else "retry"
            practice_seen = True
        elif task.type == "review":
            task.status = "ready"
            task.title = (
                f"{problem_title} 10분 압축 복기"
                if solved
                else f"{problem_title} 오답 원인 3줄 정리"
            )
            task.launch = _launch_payload("review")
            carryover_review.append(task.title)

    if not lesson_seen and today.tasks:
        today.tasks[0].status = "done"
    if not practice_seen and len(today.tasks) > 1:
        today.tasks[1].status = "done" if solved else "retry"

    if solved:
        today.focus = "오늘 문제는 잘 풀렸습니다. 내일은 같은 구조를 한 단계 더 섞어 적용해볼까요?"
        _insert_tomorrow_task(
            next_plan,
            f"{problem_title} 변형 적용 문제 묶음",
            "practice",
            18,
            launch=_launch_payload(
                "practice",
                bundle_id=bundle_id,
                lesson_id=lesson_id,
                problem_set_id=problem_set_id,
                problem_id=problem_id,
            ),
        )
        if len(next_plan) > 2:
            day_after = next_plan[2]
            day_after.tasks.append(
                StudyTask(
                    id=f"{day_after.date}-review-spaced",
                    title=f"{problem_title} 간격 복습 1묶음",
                    type="review",
                    minutes=14,
                    status="planned",
                    launch=_launch_payload("review"),
                )
            )
            day_after.minutes_target += 10
    else:
        today.focus = "오늘은 오답 원인을 나눠 보고, 내일 같은 단원을 더 짧은 문제 묶음으로 다시 잡아볼게요."
        _insert_tomorrow_task(
            next_plan,
            f"{problem_title} 재도전 문제 묶음",
            "practice",
            24,
            launch=_launch_payload(
                "practice",
                bundle_id=bundle_id,
                lesson_id=lesson_id,
                problem_set_id=problem_set_id,
                problem_id=problem_id,
            ),
        )
        _insert_tomorrow_task(
            next_plan,
            f"{problem_title} 핵심 개념 재강의",
            "lesson",
            16,
            launch=_launch_payload(
                "lesson",
                bundle_id=bundle_id,
                lesson_id=lesson_id,
                problem_set_id=problem_set_id,
                problem_id=problem_id,
            ),
        )

    for title in carryover_review[1:]:
        _insert_tomorrow_task(next_plan, title, "review", 12, launch=_launch_payload("review"))

    return next_plan
