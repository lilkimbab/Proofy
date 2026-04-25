from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Protocol

from app.domain.models import AppState, PracticeAttempt, to_jsonable


class Repository(Protocol):
    def load_state(self, user_id: str) -> AppState | None: ...
    def save_state(self, state: AppState) -> None: ...
    def list_user_ids(self) -> list[str]: ...
    def append_attempt(self, user_id: str, attempt: PracticeAttempt) -> None: ...
    def latest_attempt(self, user_id: str) -> PracticeAttempt | None: ...
    def list_session_events(self, session_id: str) -> list[dict]: ...
    def append_session_event(self, session_id: str, payload: dict) -> None: ...


@dataclass
class MemoryRepository:
    states: dict[str, AppState] = field(default_factory=dict)
    attempts: dict[str, list[PracticeAttempt]] = field(default_factory=dict)
    session_events: dict[str, list[dict]] = field(default_factory=dict)

    def load_state(self, user_id: str) -> AppState | None:
        return self.states.get(user_id)

    def save_state(self, state: AppState) -> None:
        self.states[state.user_id] = state

    def list_user_ids(self) -> list[str]:
        return sorted(self.states.keys())

    def append_attempt(self, user_id: str, attempt: PracticeAttempt) -> None:
        self.attempts.setdefault(user_id, []).append(attempt)
        state = self.states.get(user_id)
        if state is not None:
            state.attempts.append(attempt)

    def latest_attempt(self, user_id: str) -> PracticeAttempt | None:
        attempts = self.attempts.get(user_id, [])
        return attempts[-1] if attempts else None

    def list_session_events(self, session_id: str) -> list[dict]:
        return list(self.session_events.get(session_id, []))

    def append_session_event(self, session_id: str, payload: dict) -> None:
        self.session_events.setdefault(session_id, []).append(payload)


class PostgresRepository:
    def __init__(self, database_url: str):
        self.database_url = database_url

    def _connect(self):
        import psycopg

        return psycopg.connect(self.database_url)

    def load_state(self, user_id: str) -> AppState | None:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT payload
                FROM app_state
                WHERE user_id = %s
                """,
                (user_id,),
            )
            row = cursor.fetchone()
            if row is None:
                return None
            return AppState.from_dict(row[0])

    def save_state(self, state: AppState) -> None:
        payload = json.dumps(to_jsonable(state))
        profile = json.dumps(to_jsonable(state.profile))
        mastery = json.dumps(to_jsonable(state.mastery))
        plan = json.dumps(to_jsonable(state.plan))
        lesson = json.dumps(to_jsonable(state.lesson_scenes))
        problem_set = json.dumps(to_jsonable(state.practice_problem_set))
        problem = json.dumps(to_jsonable(state.practice_problem))
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO app_state (
                    user_id,
                    display_name,
                    content_bundle_id,
                    active_lesson_id,
                    active_problem_set_id,
                    payload,
                    profile,
                    mastery,
                    plan,
                    lesson,
                    practice_problem_set,
                    practice_problem
                )
                VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s::jsonb, %s::jsonb, %s::jsonb, %s::jsonb, %s::jsonb)
                ON CONFLICT (user_id)
                DO UPDATE SET
                    display_name = EXCLUDED.display_name,
                    content_bundle_id = EXCLUDED.content_bundle_id,
                    active_lesson_id = EXCLUDED.active_lesson_id,
                    active_problem_set_id = EXCLUDED.active_problem_set_id,
                    payload = EXCLUDED.payload,
                    profile = EXCLUDED.profile,
                    mastery = EXCLUDED.mastery,
                    plan = EXCLUDED.plan,
                    lesson = EXCLUDED.lesson,
                    practice_problem_set = EXCLUDED.practice_problem_set,
                    practice_problem = EXCLUDED.practice_problem,
                    updated_at = NOW()
                """,
                (
                    state.user_id,
                    state.profile.nickname,
                    state.content_bundle_id,
                    state.active_lesson_id,
                    state.active_problem_set_id,
                    payload,
                    profile,
                    mastery,
                    plan,
                    lesson,
                    problem_set,
                    problem,
                ),
            )
            connection.commit()

    def list_user_ids(self) -> list[str]:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT user_id
                FROM app_state
                ORDER BY user_id ASC
                """
            )
            return [str(row[0]) for row in cursor.fetchall()]

    def append_attempt(self, user_id: str, attempt: PracticeAttempt) -> None:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO problem_attempts (
                    attempt_id,
                    user_id,
                    problem_id,
                    solved,
                    score,
                    summary,
                    submitted,
                    evaluated_steps,
                    recovery_plan,
                    created_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s::jsonb, %s)
                """,
                (
                    attempt.id,
                    user_id,
                    attempt.problem_id,
                    attempt.solved,
                    attempt.score,
                    attempt.summary,
                    json.dumps(attempt.submitted),
                    json.dumps(to_jsonable(attempt.evaluated_steps)),
                    json.dumps(attempt.recovery_plan),
                    attempt.created_at,
                ),
            )
            connection.commit()

    def latest_attempt(self, user_id: str) -> PracticeAttempt | None:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT attempt_id, problem_id, solved, score, summary, submitted, evaluated_steps, recovery_plan, created_at
                FROM problem_attempts
                WHERE user_id = %s
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (user_id,),
            )
            row = cursor.fetchone()
            if row is None:
                return None
            return PracticeAttempt.from_dict(
                {
                    "id": row[0],
                    "problem_id": row[1],
                    "solved": row[2],
                    "score": row[3],
                    "summary": row[4],
                    "submitted": row[5],
                    "evaluated_steps": row[6],
                    "recovery_plan": row[7],
                    "recommended_scenes": ["scene-slope", "scene-point"],
                    "created_at": row[8].isoformat()
                    if isinstance(row[8], datetime)
                    else str(row[8]),
                }
            )

    def list_session_events(self, session_id: str) -> list[dict]:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT payload
                FROM session_events
                WHERE session_id = %s
                ORDER BY created_at ASC
                LIMIT 100
                """,
                (session_id,),
            )
            return [row[0] for row in cursor.fetchall()]

    def append_session_event(self, session_id: str, payload: dict) -> None:
        with self._connect() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO session_events (session_id, event_type, actor, payload)
                VALUES (%s, %s, %s, %s::jsonb)
                """,
                (
                    session_id,
                    payload.get("type", "session.event"),
                    payload.get("actor", "system"),
                    json.dumps(payload),
                ),
            )
            connection.commit()


def ensure_state(
    repository: Repository,
    user_id: str,
    seed_factory: Callable[[str], AppState],
) -> AppState:
    existing = repository.load_state(user_id)
    if existing is not None:
        return existing
    state = seed_factory(user_id)
    repository.save_state(state)
    return state
