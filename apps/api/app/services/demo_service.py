from __future__ import annotations

from copy import deepcopy
from datetime import UTC, date, datetime, timedelta
import re
from typing import Any
from uuid import uuid4

from app.content.onboarding_diagnostic import DIFFICULTY_WEIGHTS, build_onboarding_diagnostic
from app.core.config import settings
from app.db.content_repository import (
    ContentRepository,
    MemoryContentRepository,
    PostgresContentRepository,
)
from app.db.repository import MemoryRepository, PostgresRepository, Repository, ensure_state
from app.domain.content import (
    TODAY,
    bundle_question_scene,
    default_mastery,
    score_to_label,
    seed_state,
    select_active_content,
)
from app.domain.evaluator import build_evaluator
from app.domain.models import (
    AppState,
    DailyFlowState,
    GamificationState,
    MasteryState,
    MistakeNote,
    PracticeAttempt,
    QuestionHistoryEntry,
    StrategyJob,
    to_jsonable,
)
from app.domain.planner import (
    apply_attempt_feedback,
    apply_lesson_completion,
    generate_plan,
    reflow_incomplete_days,
)
from app.services.content_review import review_generated_bundle
from app.services.llm_service import LessonLLMService


CURRICULUM_BUNDLE_ID = "suneung-math-curriculum-v1"
THEMES = [
    {
        "id": "chalk-amber",
        "name": "Chalk Amber",
        "description": "따뜻한 인강 칠판 톤",
        "xpRequired": 0,
    },
    {
        "id": "mint-lab",
        "name": "Mint Lab",
        "description": "시원한 실험실 노트 톤",
        "xpRequired": 120,
    },
    {
        "id": "sunset-coral",
        "name": "Sunset Coral",
        "description": "집중감 있는 저녁 자습실 톤",
        "xpRequired": 240,
    },
    {
        "id": "midnight-focus",
        "name": "Midnight Focus",
        "description": "심야 몰입형 다크 칠판 톤",
        "xpRequired": 420,
    },
]

MILESTONES = [
    {
        "id": "lesson-first",
        "title": "첫 강의 완주",
        "description": "한 장면씩 끝까지 따라간 첫 완주입니다.",
        "metric": "lesson_completions",
        "target": 1,
    },
    {
        "id": "question-five",
        "title": "질문 다섯 번",
        "description": "막힌 지점을 그냥 넘기지 않고 직접 물어본 기록입니다.",
        "metric": "question_count",
        "target": 5,
    },
    {
        "id": "review-three",
        "title": "오답 복기 세 번",
        "description": "틀린 문제를 다시 보는 습관이 자리 잡기 시작합니다.",
        "metric": "review_sessions",
        "target": 3,
    },
    {
        "id": "solve-five",
        "title": "정답 다섯 문제",
        "description": "맞히는 힘이 눈에 보이기 시작하는 구간입니다.",
        "metric": "solved_attempts",
        "target": 5,
    },
    {
        "id": "streak-five",
        "title": "다섯 날 이어가기",
        "description": "완벽함보다 이어가는 힘이 생겼다는 뜻입니다.",
        "metric": "streak_days",
        "target": 5,
    },
    {
        "id": "recovery-three",
        "title": "회복권 세 장",
        "description": "쉬는 날이 생겨도 다시 이어갈 준비가 된 상태입니다.",
        "metric": "recovery_tokens",
        "target": 3,
    },
]


def build_state_repository() -> Repository:
    if settings.storage_backend == "postgres":
        return PostgresRepository(settings.database_url)
    return MemoryRepository()


def build_content_repository() -> ContentRepository:
    if settings.storage_backend == "postgres":
        return PostgresContentRepository(settings.database_url)
    return MemoryContentRepository()


class DemoService:
    def __init__(
        self,
        repository: Repository,
        content_repository: ContentRepository,
        llm_service: LessonLLMService | None = None,
    ):
        self.repository = repository
        self.content_repository = content_repository
        self.llm = llm_service or LessonLLMService()

    def _bundle(self, bundle_id: str | None = None) -> dict:
        if bundle_id:
            bundle = self.content_repository.load_bundle(bundle_id)
            if bundle is not None:
                return bundle
        return self.content_repository.load_default_bundle()

    def _curriculum_bundle(self) -> dict:
        return self._bundle(CURRICULUM_BUNDLE_ID)

    def _diagnostic_priority_terms(self, state: AppState) -> list[str]:
        weakest = sorted(state.mastery, key=lambda item: item.score)[:5]
        terms = list(state.profile.weak_units)
        for item in weakest:
            terms.append(item.title)
            terms.append(item.id)
            if item.course_title:
                terms.append(item.course_title)
        deduped: list[str] = []
        for term in terms:
            clean = str(term or "").strip()
            if clean and clean not in deduped:
                deduped.append(clean)
        return deduped

    def _diagnostic_seed(self, state: AppState) -> str:
        weakest_ids = [item.id for item in sorted(state.mastery, key=lambda item: item.score)[:5]]
        return "|".join(
            [
                state.user_id,
                state.profile.exam_date,
                str(state.profile.math_target_score),
                state.profile.study_mood,
                ",".join(state.profile.weak_units),
                ",".join(weakest_ids),
                state.diagnostic_session_id,
            ]
        )

    def _required_route(self, state: AppState) -> str:
        if not state.survey_completed:
            return "/survey"
        if not state.diagnostic_completed:
            return "/diagnostic"
        return "/dashboard"

    def _should_build_plan_strategy(self, state: AppState) -> bool:
        return bool(state.survey_completed and state.diagnostic_completed and state.plan)

    def _latest_strategy_job(self, state: AppState) -> StrategyJob | None:
        return state.strategy_jobs[-1] if state.strategy_jobs else None

    def _strategy_status(self, state: AppState) -> str:
        latest = self._latest_strategy_job(state)
        if latest is not None:
            return latest.status
        return "ready" if state.plan_strategy else "idle"

    def _queue_plan_strategy_job(self, state: AppState, reason: str) -> None:
        if not self._should_build_plan_strategy(state):
            state.strategy_jobs = []
            state.plan_strategy = {}
            return
        latest = self._latest_strategy_job(state)
        if latest and latest.status in {"pending", "running"}:
            latest.reason = reason
            return
        state.strategy_jobs.append(
            StrategyJob(
                id=f"strategy-{uuid4().hex[:8]}",
                status="pending",
                reason=reason,
                queued_at=self._utcnow_iso(),
            )
        )
        state.strategy_jobs = state.strategy_jobs[-20:]

    def _question_category(self, question: str) -> str:
        text = question.strip()
        if any(token in text for token in ("기초", "처음", "천천히", "다시")):
            return "basic"
        if any(token in text for token in ("왜", "원리", "개념", "의미", "이해")):
            return "concept"
        if any(token in text for token in ("어떻게", "순서", "풀이", "접근", "과정")):
            return "process"
        if any(token in text for token in ("응용", "실전", "연결", "변형")):
            return "application"
        if any(token in text for token in ("킬러", "30번", "고난도", "최상")):
            return "killer"
        return "concept"

    def _question_weight(self, question: str, response_mode: str) -> int:
        weight = 1
        if len(question.strip()) >= 18:
            weight += 1
        if response_mode == "branch":
            weight += 1
        if any(token in question for token in ("기초", "다시", "왜", "원리", "킬러", "고난도")):
            weight += 1
        return min(weight, 4)

    def _lesson_primary_concept_id(self, bundle: dict, lesson_id: str) -> str:
        lesson_pack = self._find_lesson_pack(bundle, lesson_id)
        if lesson_pack and lesson_pack.get("conceptIds"):
            return str(lesson_pack["conceptIds"][0])
        return str(sorted(self._curriculum_bundle().get("concepts", []), key=lambda item: item.get("baselineScore", 60))[0].get("id", ""))

    def _question_signal_payloads(self, state: AppState) -> list[dict[str, Any]]:
        signals: list[dict[str, Any]] = []
        for entry in state.question_history[-24:]:
            signals.append(
                {
                    "conceptId": entry.concept_id,
                    "unitTitle": entry.unit_title,
                    "category": entry.category,
                    "weight": entry.weight,
                    "lessonId": entry.lesson_id,
                    "responseMode": entry.response_mode,
                    "createdAt": entry.created_at,
                }
            )
        return signals

    def _question_signal_summary(self, state: AppState) -> list[dict[str, Any]]:
        aggregated: dict[tuple[str, str], dict[str, Any]] = {}
        for entry in state.question_history[-24:]:
            key = (entry.concept_id, entry.category)
            bucket = aggregated.setdefault(
                key,
                {
                    "conceptId": entry.concept_id,
                    "unitTitle": entry.unit_title,
                    "category": entry.category,
                    "weight": 0,
                    "count": 0,
                },
            )
            bucket["weight"] += entry.weight
            bucket["count"] += 1
        ranked = sorted(
            aggregated.values(),
            key=lambda item: (-int(item["weight"]), -int(item["count"]), str(item["unitTitle"])),
        )
        return ranked[:8]

    def _rebuild_plan(self, state: AppState) -> None:
        state.plan = generate_plan(
            state.profile,
            state.mastery,
            TODAY,
            bundle_id=state.content_bundle_id,
        )

    def _record_question_history(
        self,
        state: AppState,
        *,
        bundle: dict,
        question: str,
        scene_id: str | None,
        response_mode: str,
    ) -> None:
        concept_id = self._lesson_primary_concept_id(bundle, state.active_lesson_id)
        entry = QuestionHistoryEntry(
            id=f"question-{uuid4().hex[:8]}",
            question=question.strip(),
            category=self._question_category(question),
            weight=self._question_weight(question, response_mode),
            concept_id=concept_id,
            unit_title=self._active_lesson_title(state),
            lesson_id=state.active_lesson_id,
            scene_id=str(scene_id or ""),
            response_mode=response_mode,
            created_at=self._utcnow_iso(),
        )
        state.question_history.append(entry)
        state.question_history = state.question_history[-80:]

    def _refresh_plan_strategy(self, state: AppState) -> None:
        if not self._should_build_plan_strategy(state):
            state.plan_strategy = {}
            return
        today_plan = to_jsonable(state.plan[0]) if state.plan else {"tasks": []}
        weekly_plan = to_jsonable(state.plan[:7]) if state.plan else []
        days_left = (datetime.fromisoformat(state.profile.exam_date).date() - TODAY).days
        strategy = self.llm.build_plan_strategy(
            profile=to_jsonable(state.profile),
            mastery_snapshot=to_jsonable(state.mastery),
            today_plan=today_plan,
            weekly_plan=weekly_plan,
            days_left=days_left,
        )
        state.plan_strategy = {
            "headline": strategy.headline,
            "coachMessage": strategy.coach_message,
            "weeklyFocus": strategy.weekly_focus,
            "monthlyFocus": strategy.monthly_focus,
            "adaptationRules": strategy.adaptation_rules,
            "provider": strategy.provider,
        }

    def process_strategy_jobs(
        self,
        *,
        user_id: str | None = None,
        limit: int = 10,
    ) -> dict[str, Any]:
        processed: list[dict[str, Any]] = []
        candidates = [user_id] if user_id else self.repository.list_user_ids()
        for candidate_user_id in candidates:
            if len(processed) >= limit:
                break
            state = self._state(candidate_user_id, refresh_strategy=False)
            pending_job = next((job for job in state.strategy_jobs if job.status == "pending"), None)
            if pending_job is None:
                continue
            pending_job.status = "running"
            pending_job.started_at = self._utcnow_iso()
            self.repository.save_state(state)
            try:
                self._refresh_plan_strategy(state)
                pending_job.status = "completed"
                pending_job.finished_at = self._utcnow_iso()
                pending_job.provider = str(state.plan_strategy.get("provider") or "fallback")
                pending_job.error = ""
            except Exception as exc:
                pending_job.status = "failed"
                pending_job.finished_at = self._utcnow_iso()
                pending_job.error = str(exc)
            self.repository.save_state(state)
            processed.append(
                {
                    "userId": state.user_id,
                    "jobId": pending_job.id,
                    "status": pending_job.status,
                    "reason": pending_job.reason,
                    "provider": pending_job.provider,
                }
            )
        return {
            "processed": processed,
            "processedCount": len(processed),
        }

    def _ensure_diagnostic_questions(
        self,
        state: AppState,
        *,
        refresh: bool = False,
    ) -> list[dict[str, Any]]:
        if not state.survey_completed:
            state.diagnostic_questions = []
            state.diagnostic_answers = {}
            return []
        if state.diagnostic_questions and not refresh:
            return deepcopy(state.diagnostic_questions)
        state.diagnostic_session_id = f"diag-{uuid4().hex[:10]}"
        state.diagnostic_answers = {}
        state.diagnostic_questions = build_onboarding_diagnostic(
            size=12,
            seed=self._diagnostic_seed(state),
            prioritized_terms=self._diagnostic_priority_terms(state),
        )
        return deepcopy(state.diagnostic_questions)

    def _seed_state(self, user_id: str) -> AppState:
        return seed_state(user_id, self._bundle())

    def _state(self, user_id: str, *, refresh_strategy: bool = False) -> AppState:
        state = ensure_state(self.repository, user_id, self._seed_state)
        bundle = self._bundle(state.content_bundle_id)
        refreshed_plan = reflow_incomplete_days(
            state.profile,
            state.mastery,
            state.plan,
            TODAY,
            bundle_id=state.content_bundle_id,
        )
        if to_jsonable(refreshed_plan) != to_jsonable(state.plan):
            state.plan = refreshed_plan
            self._queue_plan_strategy_job(state, "reflow")
        if not state.practice_problem_set or not state.lesson_scenes:
            self._apply_content_selection(state, bundle)
        if refresh_strategy and not state.plan_strategy and self._should_build_plan_strategy(state):
            self._refresh_plan_strategy(state)
        self._ensure_diagnostic_questions(state)
        self.repository.save_state(state)
        return state

    def _apply_content_selection(self, state: AppState, bundle: dict) -> None:
        lesson_pack, problem_set, primary_problem = select_active_content(bundle, state.mastery)
        state.content_bundle_id = bundle["bundleId"]
        state.active_lesson_id = lesson_pack["id"]
        state.active_problem_set_id = problem_set["id"]
        state.lesson_scenes = deepcopy(lesson_pack.get("scenes", []))
        state.practice_problem_set = deepcopy(problem_set)
        state.practice_problem = deepcopy(primary_problem)

    def _active_content_summary(self, state: AppState) -> dict:
        lesson_title = self._active_lesson_title(state)
        return {
            "bundleId": state.content_bundle_id,
            "lessonId": state.active_lesson_id,
            "lessonTitle": lesson_title,
            "problemSetId": state.active_problem_set_id,
            "problemSetTitle": state.practice_problem_set.get("title", "문제 묶음"),
            "problemCount": len(state.practice_problem_set.get("problems", [])),
            "currentProblemId": state.practice_problem.get("id"),
            "currentProblemTitle": state.practice_problem.get("title"),
            "evaluationType": state.practice_problem.get("evaluationType", "tangent-line"),
        }

    def _active_lesson_title(self, state: AppState) -> str:
        bundle = self._bundle(state.content_bundle_id)
        lesson_pack = self._find_lesson_pack(bundle, state.active_lesson_id)
        if lesson_pack and lesson_pack.get("title"):
            return str(lesson_pack["title"])
        return str(state.practice_problem_set.get("lessonTitle") or "오늘의 추천 단원")

    def _track_label_from_title(self, title: str) -> str:
        if "공통수학" in title:
            return "공통수학"
        if "대수" in title:
            return "대수"
        if "미적분" in title:
            return "미적분"
        if "확률과 통계" in title:
            return "확률과 통계"
        if "기하" in title:
            return "기하"
        return "수학"

    def _today_mission(self, state: AppState, today_plan: Any) -> dict[str, Any]:
        tasks = list(today_plan.tasks)
        current_task = next(
            (task for task in tasks if task.status in {"ready", "planned"}),
            tasks[0] if tasks else None,
        )
        remaining_tasks = [task for task in tasks if task.status != "done"]
        weak_units = [item.title for item in sorted(state.mastery, key=lambda item: item.score)[:3]]
        current_title = current_task.title if current_task else state.practice_problem_set.get("title", "오늘의 학습 흐름")
        recommended_unit = self._active_lesson_title(state)
        return {
            "headline": f"오늘은 {current_title}부터 시작합니다.",
            "summary": (
                "강의에서 구조를 잡고, 바로 문제를 풀고, 오답은 다음 날 계획에 자동 반영됩니다."
            ),
            "activeTrack": self._track_label_from_title(current_title),
            "recommendedUnit": recommended_unit,
            "currentTask": to_jsonable(current_task) if current_task else None,
            "queue": to_jsonable(remaining_tasks[:3]),
            "weakUnits": weak_units,
        }

    def _find_lesson_pack(self, bundle: dict, lesson_id: str) -> dict | None:
        return next(
            (lesson for lesson in bundle.get("lessonPacks", []) if lesson["id"] == lesson_id),
            None,
        )

    def _find_problem_set(self, bundle: dict, problem_set_id: str) -> dict | None:
        return next(
            (problem_set for problem_set in bundle.get("problemSets", []) if problem_set["id"] == problem_set_id),
            None,
        )

    def _lookup_problem_by_id(self, problem_id: str) -> dict[str, Any] | None:
        for bundle_meta in self.content_repository.list_catalog():
            bundle = self._bundle(bundle_meta["bundleId"])
            for problem_set in bundle.get("problemSets", []):
                for problem in problem_set.get("problems", []):
                    if problem.get("id") == problem_id:
                        return problem
        return None

    def _step_guide_for_problem(self, problem: dict[str, Any]) -> list[dict[str, str]]:
        if problem.get("evaluationType") == "maxmin-points":
            return list(
                problem.get("stepGuide")
                or [
                    {"label": "Step 1. 도함수", "placeholder": ""},
                    {"label": "Step 2. 극값 후보", "placeholder": ""},
                    {"label": "Step 3. 부호 변화 판정", "placeholder": ""},
                ]
            )
        return list(
            problem.get("stepGuide")
            or [
                {"label": "Step 1. 도함수", "placeholder": ""},
                {"label": "Step 2. 기울기", "placeholder": ""},
                {"label": "Step 3. 접점", "placeholder": ""},
            ]
        )

    def _final_prompt_for_problem(self, problem: dict[str, Any]) -> str:
        prompt = str(problem.get("finalPrompt") or "")
        if prompt.startswith("예:"):
            return ""
        return prompt

    def _problem_payload(self, problem: dict[str, Any]) -> dict[str, Any]:
        return {
            **problem,
            "evaluationType": problem.get("evaluationType", "tangent-line"),
            "stepGuide": self._step_guide_for_problem(problem),
            "finalPrompt": self._final_prompt_for_problem(problem),
            "difficulty": problem.get("difficulty", "core"),
            "problemType": problem.get("problemType", problem.get("title", "대표 유형")),
            "isKiller": bool(problem.get("isKiller", False)),
        }

    def _build_evaluator(self, state: AppState):
        return build_evaluator(state.practice_problem)

    def _activate_content(
        self,
        state: AppState,
        *,
        bundle_id: str,
        lesson_id: str,
        problem_set_id: str,
        problem_id: str | None = None,
    ) -> None:
        bundle = self._bundle(bundle_id)
        lesson_pack = self._find_lesson_pack(bundle, lesson_id)
        problem_set = self._find_problem_set(bundle, problem_set_id)
        if lesson_pack is None or problem_set is None or not problem_set.get("problems"):
            raise ValueError("invalid content selection")
        state.content_bundle_id = bundle["bundleId"]
        state.active_lesson_id = lesson_pack["id"]
        state.active_problem_set_id = problem_set["id"]
        state.lesson_scenes = deepcopy(lesson_pack.get("scenes", []))
        state.practice_problem_set = deepcopy(problem_set)
        selected_problem = next(
            (
                problem
                for problem in problem_set.get("problems", [])
                if problem.get("id") == problem_id
            ),
            problem_set["problems"][0],
        )
        state.practice_problem = deepcopy(selected_problem)

    def _recommended_follow_up_problem(self, state: AppState, solved: bool) -> dict | None:
        if not solved:
            return None
        problems = state.practice_problem_set.get("problems", [])
        current_id = state.practice_problem.get("id")
        for index, problem in enumerate(problems):
            if problem.get("id") == current_id and index + 1 < len(problems):
                return {
                    "nextProblemId": problems[index + 1]["id"],
                    "nextProblemTitle": problems[index + 1]["title"],
                }
        return None

    def _advance_to_next_problem(self, state: AppState, next_problem: dict | None) -> None:
        if not next_problem:
            return
        next_id = next_problem.get("nextProblemId")
        if not next_id:
            return
        for problem in state.practice_problem_set.get("problems", []):
            if problem.get("id") == next_id:
                state.practice_problem = deepcopy(problem)
                return

    def _manual_next_problem(self, state: AppState) -> dict | None:
        problems = state.practice_problem_set.get("problems", [])
        current_id = state.practice_problem.get("id")
        for index, problem in enumerate(problems):
            if problem.get("id") == current_id and index + 1 < len(problems):
                next_problem = problems[index + 1]
                state.practice_problem = deepcopy(next_problem)
                return {
                    "nextProblemId": next_problem["id"],
                    "nextProblemTitle": next_problem["title"],
                }
        return None

    def _current_activity_date(self) -> str:
        return date.today().isoformat()

    def _utcnow_iso(self) -> str:
        return datetime.now(UTC).isoformat()

    def _find_daily_flow(
        self,
        state: AppState,
        activity_date: str | None = None,
    ) -> DailyFlowState | None:
        target = activity_date or self._current_activity_date()
        for flow in state.gamification.daily_flows:
            if flow.date == target:
                return flow
        return None

    def _ensure_daily_flow(
        self,
        state: AppState,
        activity_date: str | None = None,
    ) -> DailyFlowState:
        target = activity_date or self._current_activity_date()
        existing = self._find_daily_flow(state, target)
        if existing is not None:
            return existing
        flow = DailyFlowState(date=target)
        state.gamification.daily_flows.append(flow)
        state.gamification.daily_flows = sorted(
            state.gamification.daily_flows,
            key=lambda item: item.date,
        )[-21:]
        return flow

    def _touch_learning_day(self, state: AppState, activity_date: str) -> DailyFlowState:
        gamification = state.gamification
        if gamification.last_activity_date != activity_date:
            if gamification.last_activity_date:
                expected_previous = (
                    date.fromisoformat(activity_date) - timedelta(days=1)
                ).isoformat()
                if gamification.last_activity_date == expected_previous:
                    gamification.streak_days = max(1, gamification.streak_days + 1)
                elif gamification.recovery_tokens > 0:
                    gamification.recovery_tokens = max(0, gamification.recovery_tokens - 1)
                    gamification.streak_days = max(1, gamification.streak_days + 1)
                else:
                    gamification.streak_days = 1
            else:
                gamification.streak_days = 1
            gamification.last_activity_date = activity_date
            gamification.best_streak_days = max(
                gamification.best_streak_days,
                gamification.streak_days,
            )
        return self._ensure_daily_flow(state, activity_date)

    def _milestone_metric_value(self, state: AppState, metric: str) -> int:
        gamification = state.gamification
        return int(getattr(gamification, metric, 0))

    def _milestone_payloads(self, state: AppState) -> list[dict[str, Any]]:
        unlocked = set(state.gamification.milestone_ids)
        payloads: list[dict[str, Any]] = []
        for definition in MILESTONES:
            progress = min(
                self._milestone_metric_value(state, str(definition["metric"])),
                int(definition["target"]),
            )
            payloads.append(
                {
                    "id": definition["id"],
                    "title": definition["title"],
                    "description": definition["description"],
                    "progress": progress,
                    "target": int(definition["target"]),
                    "unlocked": definition["id"] in unlocked,
                }
            )
        return payloads

    def _current_goal_payload(self, state: AppState) -> dict[str, Any] | None:
        milestones = self._milestone_payloads(state)
        locked = [item for item in milestones if not item["unlocked"]]
        if not locked:
            return {
                "title": "오늘 흐름 유지",
                "description": "강의, 문제, 복습을 차분하게 이어가 보세요.",
                "progress": 3,
                "target": 3,
            }
        locked.sort(
            key=lambda item: (
                -(int(item["progress"]) / max(1, int(item["target"]))),
                int(item["target"]),
            )
        )
        return locked[0]

    def _weekly_rhythm_payload(self, state: AppState) -> dict[str, Any]:
        recent = sorted(state.gamification.daily_flows, key=lambda item: item.date)[-7:]
        active_days = sum(
            1
            for flow in recent
            if flow.lesson_done or flow.practice_done or flow.review_done or flow.question_done
        )
        strong_days = sum(
            1 for flow in recent if flow.lesson_done and flow.practice_done and flow.review_done
        )
        return {
            "activeDays": active_days,
            "strongDays": strong_days,
            "totalPoints": sum(flow.points_earned for flow in recent),
            "bestStreakDays": state.gamification.best_streak_days,
        }

    def _flow_payload(self, state: AppState, flow: DailyFlowState | None = None) -> dict[str, Any]:
        current = flow or self._find_daily_flow(state) or DailyFlowState(date=self._current_activity_date())
        steps = [
            {"id": "lesson", "title": "강의", "done": current.lesson_done},
            {"id": "practice", "title": "문제", "done": current.practice_done},
            {"id": "review", "title": "복습", "done": current.review_done},
            {"id": "question", "title": "질문", "done": current.question_done},
        ]
        completed_count = sum(1 for step in steps if step["done"])
        return {
            "date": current.date,
            "steps": steps,
            "completedCount": completed_count,
            "coreCompleted": bool(current.lesson_done and current.practice_done and current.review_done),
            "pointsEarned": current.points_earned,
        }

    def _gamification_payload(self, state: AppState) -> dict:
        unlocked = [
            theme for theme in THEMES if theme["id"] in set(state.gamification.unlocked_theme_ids)
        ]
        next_theme = next(
            (theme for theme in THEMES if theme["id"] not in state.gamification.unlocked_theme_ids),
            None,
        )
        today_flow = self._flow_payload(state)
        return {
            "streakDays": state.gamification.streak_days,
            "bestStreakDays": state.gamification.best_streak_days,
            "lastActivityDate": state.gamification.last_activity_date,
            "xp": state.gamification.xp,
            "level": state.gamification.level,
            "focusPoints": state.gamification.xp,
            "focusLevel": state.gamification.level,
            "recoveryTokens": state.gamification.recovery_tokens,
            "lessonCompletions": state.gamification.lesson_completions,
            "practiceAttempts": state.gamification.practice_attempts,
            "solvedAttempts": state.gamification.solved_attempts,
            "reviewSessions": state.gamification.review_sessions,
            "questionCount": state.gamification.question_count,
            "todayFlow": today_flow,
            "weeklyRhythm": self._weekly_rhythm_payload(state),
            "milestones": self._milestone_payloads(state),
            "currentGoal": self._current_goal_payload(state),
            "activeThemeId": state.gamification.active_theme_id,
            "unlockedThemes": unlocked,
            "recentUnlocks": state.gamification.recent_unlocks,
            "nextTheme": next_theme,
        }

    def _unlock_progress_rewards(
        self,
        state: AppState,
        flow: DailyFlowState,
        *,
        just_completed_core: bool,
    ) -> None:
        gamification = state.gamification
        new_unlocks: list[str] = []
        if just_completed_core:
            gamification.recovery_tokens = min(5, gamification.recovery_tokens + 1)
            new_unlocks.append("회복권 +1")

        for milestone in MILESTONES:
            milestone_id = str(milestone["id"])
            if milestone_id in gamification.milestone_ids:
                continue
            if self._milestone_metric_value(state, str(milestone["metric"])) >= int(milestone["target"]):
                gamification.milestone_ids.append(milestone_id)
                new_unlocks.append(str(milestone["title"]))

        unlocked_themes = set(gamification.unlocked_theme_ids)
        for theme in THEMES:
            if gamification.xp >= theme["xpRequired"] and theme["id"] not in unlocked_themes:
                gamification.unlocked_theme_ids.append(theme["id"])
                unlocked_themes.add(theme["id"])
                new_unlocks.append(theme["name"])
        if new_unlocks:
            gamification.recent_unlocks = (new_unlocks + gamification.recent_unlocks)[:4]

    def _record_gamification_event(self, state: AppState, event_type: str, amount: int) -> None:
        today = self._current_activity_date()
        flow = self._touch_learning_day(state, today)
        gamification = state.gamification
        before_core = flow.lesson_done and flow.practice_done and flow.review_done

        gamification.xp += max(0, amount)
        gamification.level = 1 + gamification.xp // 180

        if event_type == "lesson-complete":
            if not flow.lesson_done:
                flow.lesson_done = True
                gamification.lesson_completions += 1
        elif event_type == "lesson-question":
            flow.question_done = True
            gamification.question_count += 1
        elif event_type == "practice-solved":
            flow.practice_done = True
            gamification.practice_attempts += 1
            gamification.solved_attempts += 1
        elif event_type == "practice-retry":
            flow.practice_done = True
            gamification.practice_attempts += 1
        elif event_type == "review-opened":
            if not flow.review_done:
                flow.review_done = True
                gamification.review_sessions += 1
        elif event_type == "diagnostic-complete":
            flow.question_done = True

        flow.points_earned += max(0, amount)
        gamification.best_streak_days = max(gamification.best_streak_days, gamification.streak_days)

        after_core = flow.lesson_done and flow.practice_done and flow.review_done
        self._unlock_progress_rewards(
            state,
            flow,
            just_completed_core=bool(after_core and not before_core),
        )

    def _grant_xp(self, state: AppState, amount: int) -> None:
        self._record_gamification_event(state, "generic", amount)

    def _theme_payload(self, state: AppState) -> dict:
        return {
            "gamification": self._gamification_payload(state),
            "themeCatalog": THEMES,
        }

    def _recent_mistake_notes(self, state: AppState, limit: int = 4) -> list[dict[str, Any]]:
        notes = sorted(state.mistake_notes, key=lambda item: item.created_at, reverse=True)
        return to_jsonable(notes[:limit])

    def _find_scene(self, state: AppState, scene_id: str | None) -> dict[str, Any]:
        if scene_id:
            for scene in state.lesson_scenes:
                if scene.get("id") == scene_id:
                    return scene
        return state.lesson_scenes[0]

    def _find_focus_object_id(self, scene: dict[str, Any], question: str) -> str | None:
        normalized = question.replace(" ", "")
        preferred_types = ["equation", "graph", "table", "checklist", "callout", "text"]
        if "그래프" in question:
            preferred_types = ["graph", "equation", "callout", "table", "text"]
        elif "표" in question or "체크" in question:
            preferred_types = ["table", "checklist", "callout", "equation"]
        elif "기울기" in question or "도함수" in question or "slope" in normalized:
            preferred_types = ["equation", "callout", "graph", "table", "text"]

        for preferred in preferred_types:
            for obj in scene.get("objects", []):
                if obj.get("type") == preferred:
                    return str(obj.get("id"))
        return None

    def _annotated_interrupt_scene(
        self,
        scene: dict[str, Any],
        answer: str,
        focus_object_id: str | None,
        *,
        board_title: str = "같이 다시 볼 포인트",
        board_points: list[str] | None = None,
        resume_label: str = "이어서 같이 볼게요",
    ) -> dict[str, Any]:
        next_scene = deepcopy(scene)
        support_object = self._build_support_object(scene, focus_object_id)

        next_scene["title"] = board_title
        next_scene["narration"] = answer
        next_scene["resumeLabel"] = resume_label
        next_scene["teachingGoal"] = "질문한 부분만 다시 선명하게 정리합니다."
        next_scene["takeaway"] = answer
        next_scene["examCue"] = "지금 이해한 내용을 다시 문제에 연결하면 됩니다."
        next_scene["practiceBridge"] = "돌아가기를 누르면 원래 강의 흐름으로 바로 이어집니다."
        next_scene["autoAdvanceSeconds"] = 0
        next_scene["objects"] = [
            {
                "id": f"answer-{uuid4().hex[:8]}",
                "type": "answer",
                "x": 8,
                "y": 18,
                "w": 56 if support_object else 82,
                "h": 56 if support_object else 60,
                "content": answer,
                "delayMs": 0,
            },
        ]
        if support_object:
            next_scene["objects"].append(support_object)
        return next_scene

    def _build_support_object(
        self,
        scene: dict[str, Any],
        focus_object_id: str | None,
    ) -> dict[str, Any] | None:
        focus_object = next(
            (obj for obj in scene.get("objects", []) if str(obj.get("id")) == str(focus_object_id)),
            None,
        )
        if not focus_object or str(focus_object.get("type")) not in {"graph", "table"}:
            return None
        support_object = deepcopy(focus_object)
        support_object["id"] = f"support-{uuid4().hex[:8]}"
        support_object["x"] = 67
        support_object["y"] = 18
        support_object["w"] = 23
        support_object["h"] = 30 if str(focus_object.get("type")) == "graph" else 34
        support_object["delayMs"] = 0
        return support_object

    def _question_full_board_scene(
        self,
        question: str,
        *,
        resume_label: str = "이어서 같이 볼게요",
    ) -> dict[str, Any]:
        return {
            "id": f"question-scene-{uuid4().hex[:8]}",
            "title": "질문부터 같이 볼게요",
            "narration": question,
            "resumeLabel": resume_label,
            "teachingGoal": "질문을 먼저 분명하게 잡고 그 질문 기준으로 흐름을 바꿉니다.",
            "takeaway": question,
            "examCue": "지금 궁금한 지점을 정확히 짚는 게 가장 중요합니다.",
            "practiceBridge": "이 질문 기준으로 짧은 보충 강의를 이어갑니다.",
            "autoAdvanceSeconds": 2,
            "objects": [
                {
                    "id": f"question-{uuid4().hex[:8]}",
                    "type": "question",
                    "x": 8,
                    "y": 16,
                    "w": 84,
                    "h": 60,
                    "content": question,
                    "delayMs": 0,
                }
            ],
        }

    def _question_connection_scene(
        self,
        *,
        question: str,
        practice_problem: dict[str, Any],
        branch_outline: list[str] | None,
        board_points: list[str] | None,
        resume_label: str,
    ) -> dict[str, Any]:
        next_steps = [item for item in (branch_outline or board_points or []) if item][:3]
        if not next_steps:
            next_steps = list(practice_problem.get("expectedOutline", [])[:3]) or [
                "조건을 다시 짧게 읽기",
                "첫 줄 기준 식 적기",
                "마지막 답 형식 확인하기",
            ]
        return {
            "id": f"question-connect-{uuid4().hex[:8]}",
            "title": "이제 문제에 다시 얹어볼게요",
            "narration": (
                "질문으로 다시 본 내용을 바로 현재 문제에 얹어보겠습니다. "
                "이 장면을 보고 나면 원래 강의로 돌아가도 흐름이 끊기지 않습니다."
            ),
            "resumeLabel": resume_label,
            "teachingGoal": "질문에서 얻은 답을 현재 문제 풀이 순서로 연결합니다.",
            "takeaway": "질문은 따로 끝나는 게 아니라 지금 문제의 첫 줄을 더 선명하게 만들어 줍니다.",
            "examCue": "다시 문제를 볼 때 지금 체크리스트를 먼저 떠올려 보세요.",
            "practiceBridge": "원래 강의로 돌아가도 되고, 바로 문제에 적용해도 좋습니다.",
            "autoAdvanceSeconds": 0,
            "objects": [
                {
                    "id": f"question-connect-problem-{uuid4().hex[:8]}",
                    "type": "callout",
                    "x": 8,
                    "y": 18,
                    "w": 40,
                    "content": practice_problem.get("statement", question),
                    "delayMs": 0,
                },
                {
                    "id": f"question-connect-check-{uuid4().hex[:8]}",
                    "type": "checklist",
                    "x": 54,
                    "y": 18,
                    "w": 34,
                    "h": 42,
                    "label": "다시 시작할 순서",
                    "items": next_steps,
                    "delayMs": 0,
                },
            ],
        }

    def _question_branch_scenes(
        self,
        *,
        question: str,
        answer: str,
        base_scene: dict[str, Any],
        practice_problem: dict[str, Any],
        focus_object_id: str | None,
        board_title: str,
        board_points: list[str] | None,
        branch_outline: list[str] | None,
        resume_label: str,
        include_connection: bool,
    ) -> list[dict[str, Any]]:
        scenes = [
            self._question_full_board_scene(question, resume_label=resume_label),
            self._annotated_interrupt_scene(
                base_scene,
                answer,
                focus_object_id,
                board_title=board_title,
                board_points=board_points,
                resume_label=resume_label,
            ),
        ]
        if include_connection:
            scenes.append(
                self._question_connection_scene(
                    question=question,
                    practice_problem=practice_problem,
                    branch_outline=branch_outline,
                    board_points=board_points,
                    resume_label=resume_label,
                )
            )
        return scenes

    def _scene_family(self, scene: dict[str, Any]) -> str:
        title = str(scene.get("title") or "")
        if any(keyword in title for keyword in ("학습목표", "정의", "직관", "한 판 정리")):
            return "concept"
        if any(keyword in title for keyword in ("전략", "문제 읽기", "스캐폴드", "풀이 완성")):
            return "process"
        if any(keyword in title for keyword in ("오개념", "체크포인트", "형성 확인")):
            return "checkpoint"
        if any(keyword in title for keyword in ("응용", "심화", "실전", "비교", "킬러")):
            return "application"
        if scene.get("sceneGroup") == "problem-branch":
            return "problem-branch"
        object_types = {str(obj.get("type")) for obj in scene.get("objects", [])}
        if "graph" in object_types:
            return "graph"
        if "table" in object_types or "checklist" in object_types:
            return "structured"
        return "general"

    def _scene_signature(self, scene: dict[str, Any]) -> tuple[str, str]:
        title = re.sub(r"\s+", " ", str(scene.get("title") or "")).strip().lower()
        narration = re.sub(r"\s+", " ", str(scene.get("narration") or "")).strip().lower()
        narration = narration[:140]
        return title, narration

    def _curate_lesson_scenes(self, scenes: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if len(scenes) <= 8:
            return list(scenes)
        curated: list[dict[str, Any]] = []
        family_run = 0
        last_family = ""
        recent_signatures: list[tuple[str, str]] = []
        for index, scene in enumerate(scenes):
            family = self._scene_family(scene)
            signature = self._scene_signature(scene)
            duplicate_signature = signature in recent_signatures[-3:]
            same_family = family == last_family
            if duplicate_signature and family not in {"application", "problem-branch"}:
                continue
            if same_family:
                family_run += 1
            else:
                family_run = 1
            if family_run >= 3 and family in {"concept", "checkpoint", "structured", "general"}:
                continue
            curated.append(scene)
            last_family = family
            recent_signatures.append(signature)
        if len(curated) < max(10, len(scenes) // 2):
            return list(scenes)
        return curated

    def _student_scene(self, scene: dict[str, Any]) -> dict[str, Any]:
        clean_scene = deepcopy(scene)
        for key in ("source", "sourcePdf", "pdfPages", "achievementCodes"):
            clean_scene.pop(key, None)
        return clean_scene

    def _scene_object_summary(self, scene: dict[str, Any]) -> list[dict[str, str]]:
        summary: list[dict[str, str]] = []
        for obj in scene.get("objects", []):
            content = str(obj.get("content") or "").replace("\n", " ").strip()
            if not content and obj.get("label"):
                content = str(obj.get("label")).strip()
            if not content and obj.get("items"):
                content = " / ".join(str(item).strip() for item in obj.get("items", [])[:3])
            if not content and obj.get("table"):
                headers = obj["table"].get("headers", [])
                first_row = obj["table"].get("rows", [[], [], []])[0] if obj["table"].get("rows") else []
                content = " | ".join([*headers[:2], *first_row[:1]]).strip()
            summary.append(
                {
                    "id": str(obj.get("id")),
                    "type": str(obj.get("type")),
                    "summary": content[:120] or str(obj.get("type")),
                }
            )
        return summary

    def _resolve_runtime_scenes(
        self,
        state: AppState,
        runtime_scene_ids: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        base_scenes = list(state.lesson_scenes)
        if not runtime_scene_ids:
            return self._curate_lesson_scenes(base_scenes)
        by_id = {str(scene.get("id")): scene for scene in base_scenes}
        ordered: list[dict[str, Any]] = []
        seen: set[str] = set()
        for scene_id in runtime_scene_ids:
            scene = by_id.get(str(scene_id))
            if scene is None or str(scene.get("id")) in seen:
                continue
            ordered.append(scene)
            seen.add(str(scene.get("id")))
        return ordered or self._curate_lesson_scenes(base_scenes)

    def _question_keywords(self, question: str) -> list[str]:
        cleaned = re.sub(r"[^0-9A-Za-z가-힣\\s]", " ", question)
        raw_tokens = [token.strip() for token in cleaned.split() if len(token.strip()) >= 2]
        expansions: list[str] = []
        keyword_map = {
            "기초": ["학습목표", "정의", "직관", "교실 판서", "한 판 정리"],
            "처음": ["학습목표", "정의", "직관", "오프닝"],
            "다시": ["학습목표", "정의", "한 판 정리", "강의 체크포인트"],
            "왜": ["직관", "정의", "개념 연결 지도", "의미"],
            "원리": ["직관", "정의", "개념 연결 지도"],
            "의미": ["직관", "정의", "개념 연결 지도"],
            "어떻게": ["전략", "스캐폴드", "문제 읽기", "풀이 완성"],
            "풀이": ["전략", "스캐폴드", "문제 읽기", "풀이 완성"],
            "순서": ["전략", "문제 읽기", "판서", "체크포인트"],
            "응용": ["응용", "심화", "예제 비교", "실전"],
            "심화": ["응용", "심화", "예제 비교", "실전"],
            "킬러": ["응용", "실전", "문제 읽기", "풀이 완성"],
            "실전": ["실전", "문제 읽기", "응용", "비교"],
            "문제": ["대표 적용", "문제 읽기", "풀이 완성", "문제 언어 번역"],
        }
        for key, related in keyword_map.items():
            if key in question:
                expansions.extend(related)
        ordered: list[str] = []
        for item in [*raw_tokens, *expansions]:
            if item and item not in ordered:
                ordered.append(item)
        return ordered

    def _scene_text_blob(self, scene: dict[str, Any]) -> str:
        parts = [
            str(scene.get("title") or ""),
            str(scene.get("narration") or ""),
            str(scene.get("teachingGoal") or ""),
            str(scene.get("takeaway") or ""),
            str(scene.get("examCue") or ""),
            str(scene.get("practiceBridge") or ""),
        ]
        for obj in scene.get("objects", []):
            parts.append(str(obj.get("content") or ""))
            parts.append(str(obj.get("label") or ""))
            if obj.get("items"):
                parts.extend(str(item) for item in obj.get("items", []))
            table = obj.get("table") or {}
            parts.extend(str(item) for item in table.get("headers", []))
            for row in table.get("rows", []):
                parts.extend(str(cell) for cell in row)
        return " ".join(part for part in parts if part).lower()

    def _scene_question_score(self, scene: dict[str, Any], question: str, keywords: list[str]) -> int:
        blob = self._scene_text_blob(scene)
        title = str(scene.get("title") or "")
        score = 0
        for keyword in keywords:
            lowered = keyword.lower()
            if lowered and lowered in blob:
                score += 3
            if lowered and lowered in title.lower():
                score += 2
        if any(token in question for token in ("기초", "처음", "다시", "천천히")):
            if any(mark in title for mark in ("학습목표", "정의", "직관", "한 판 정리", "오프닝")):
                score += 6
        if any(token in question for token in ("왜", "원리", "의미", "개념", "이해")):
            if any(mark in title for mark in ("정의", "직관", "개념 연결 지도", "학습목표")):
                score += 5
        if any(token in question for token in ("어떻게", "풀이", "순서", "접근")):
            if any(mark in title for mark in ("전략", "스캐폴드", "문제 읽기", "풀이 완성", "체크포인트")):
                score += 5
        if any(token in question for token in ("응용", "심화", "킬러", "실전")):
            if any(mark in title for mark in ("응용", "심화", "예제 비교", "실전", "문제 읽기", "풀이 완성")):
                score += 5
        if "문제" in question and any(mark in title for mark in ("대표 적용", "문제 읽기", "문제 언어 번역", "풀이 완성")):
            score += 4
        if scene.get("sceneGroup") == "problem-branch" and any(token in question for token in ("기초", "처음")):
            score -= 2
        return score

    def _build_lesson_continuation_plan(
        self,
        *,
        runtime_scenes: list[dict[str, Any]],
        current_scene_id: str | None,
        question: str,
    ) -> dict[str, Any]:
        if not runtime_scenes:
            return {"mode": "original", "orderedSceneIds": [], "prioritizedSceneIds": []}
        current_index = next(
            (index for index, scene in enumerate(runtime_scenes) if scene.get("id") == current_scene_id),
            0,
        )
        prefix = runtime_scenes[: current_index + 1]
        remaining = runtime_scenes[current_index + 1 :]
        if not remaining:
            return {
                "mode": "original",
                "orderedSceneIds": [str(scene.get("id")) for scene in runtime_scenes],
                "prioritizedSceneIds": [],
            }
        keywords = self._question_keywords(question)
        scored: list[tuple[int, int, dict[str, Any]]] = []
        for offset, scene in enumerate(remaining):
            score = self._scene_question_score(scene, question, keywords)
            if score > 0:
                scored.append((score, offset, scene))
        if not scored:
            return {
                "mode": "original",
                "orderedSceneIds": [str(scene.get("id")) for scene in runtime_scenes],
                "prioritizedSceneIds": [],
            }
        scored.sort(key=lambda item: (-item[0], item[1]))
        prioritized_ids: list[str] = []
        used_families: list[str] = []
        for score, _, scene in scored:
            scene_id = str(scene.get("id"))
            family = self._scene_family(scene)
            if family in used_families[-2:] and len(prioritized_ids) < 4:
                continue
            prioritized_ids.append(scene_id)
            used_families.append(family)
            if len(prioritized_ids) >= min(6, len(scored)):
                break
        if len(prioritized_ids) < min(4, len(scored)):
            for _, _, scene in scored:
                scene_id = str(scene.get("id"))
                if scene_id not in prioritized_ids:
                    prioritized_ids.append(scene_id)
                if len(prioritized_ids) >= min(6, len(scored)):
                    break
        ordered_ids = [str(scene.get("id")) for scene in prefix]
        ordered_ids.extend(prioritized_ids)
        ordered_ids.extend(
            str(scene.get("id"))
            for scene in remaining
            if str(scene.get("id")) not in prioritized_ids
        )
        return {
            "mode": "adaptive",
            "orderedSceneIds": ordered_ids,
            "prioritizedSceneIds": prioritized_ids,
        }

    def _build_mistake_notes(self, state: AppState, evaluated_steps: list[Any]) -> list[MistakeNote]:
        created_at = self._utcnow_iso()
        notes: list[MistakeNote] = []
        for step in evaluated_steps:
            if step.accepted:
                continue
            mistake_type = step.error_type or "개념 보정"
            notes.append(
                MistakeNote(
                    id=f"mistake-{uuid4().hex[:8]}",
                    problem_id=str(state.practice_problem.get("id", "")),
                    problem_title=str(state.practice_problem.get("title", "현재 문제")),
                    mistake_type=mistake_type,
                    trigger_step=step.label,
                    summary=step.reason,
                    correction=f"{step.label} 단계에서는 {step.expected} 구조를 먼저 고정하세요.",
                    retry_prompt=f"{mistake_type}을 피하려면 같은 문제를 3줄 구조로 다시 적어보세요.",
                    created_at=created_at,
                )
            )
        return notes

    def content_catalog(self) -> dict:
        return {"bundles": self.content_repository.list_catalog()}

    def import_content_bundle(self, bundle: dict) -> dict:
        self.content_repository.import_bundle(bundle)
        return self.content_catalog()

    def delete_content_bundle(self, bundle_id: str) -> dict:
        deleted = self.content_repository.delete_bundle(bundle_id)
        return {
            "deleted": deleted,
            "bundleId": bundle_id,
            "contentCatalog": self.content_catalog(),
        }

    def review_generated_content_bundle(
        self,
        bundle: dict,
        *,
        source_provider: str = "gemini",
        import_approved: bool = False,
    ) -> dict:
        report = review_generated_bundle(bundle, source_provider=source_provider)
        self.content_repository.save_review_report(report)
        if import_approved and report.get("approvedProblemCount", 0) > 0:
            self.content_repository.import_bundle(report["approvedBundle"])
        return {
            "review": report,
            "contentCatalog": self.content_catalog(),
        }

    def list_review_reports(self) -> dict:
        return {"reviews": self.content_repository.list_review_reports()}

    def get_review_report(self, review_job_id: str) -> dict:
        report = self.content_repository.get_review_report(review_job_id)
        if report is None:
            return {"empty": True, "message": "검수 이력을 찾지 못했습니다."}
        return {"empty": False, "review": report}

    def activate_content_selection(
        self,
        user_id: str,
        *,
        bundle_id: str,
        lesson_id: str,
        problem_set_id: str,
        problem_id: str | None = None,
    ) -> dict:
        state = self._state(user_id, refresh_strategy=False)
        self._activate_content(
            state,
            bundle_id=bundle_id,
            lesson_id=lesson_id,
            problem_set_id=problem_set_id,
            problem_id=problem_id,
        )
        self.repository.save_state(state)
        return {
            "dashboard": self.dashboard(user_id),
            "lessonSession": self.lesson_session(user_id),
        }

    def bootstrap(self, user_id: str) -> dict:
        state = self._state(user_id)
        return {
            "app": {
                "name": "Proofy",
                "tagline": "강의부터 문제까지 한 흐름으로 이어지는 맞춤 학습",
            },
            "profile": to_jsonable(state.profile),
            "diagnosticQuestions": self._ensure_diagnostic_questions(state),
            "onboarding": {
                "surveyCompleted": state.survey_completed,
                "surveyStep": state.survey_step,
                "diagnosticCompleted": state.diagnostic_completed,
                "diagnosticAnswers": state.diagnostic_answers,
                "requiredRoute": self._required_route(state),
            },
        }

    def dashboard(self, user_id: str) -> dict:
        state = self._state(user_id)
        days_left = (datetime.fromisoformat(state.profile.exam_date).date() - TODAY).days
        readiness = int(sum(item.score for item in state.mastery) / len(state.mastery))
        today_plan = state.plan[0]
        completed = sum(1 for task in today_plan.tasks if task.status == "done")
        weekly_slice = state.plan[:7]
        plan_strategy = state.plan_strategy or {}
        return {
            "headline": plan_strategy.get("headline") or "오늘은 개념-질문-문제풀이-오답노트가 한 번에 이어지는 날입니다.",
            "stats": {
                "daysLeft": days_left,
                "targetScore": state.profile.math_target_score,
                "todayMinutes": today_plan.minutes_target,
                "completedTasks": completed,
                "readiness": readiness,
                "weeklyStudyHours": state.profile.weekly_study_hours,
            },
            "mastery": [
                {
                    **to_jsonable(item),
                    "label": score_to_label(item.score),
                }
                for item in state.mastery
            ],
            "todayPlan": to_jsonable(today_plan),
            "weeklyPlan": to_jsonable(weekly_slice),
            "planHorizonDays": len(state.plan),
            "todayMission": self._today_mission(state, today_plan),
            "activeContent": {
                **self._active_content_summary(state),
                "lessonTitle": self._active_lesson_title(state),
            },
            "contentLibrary": self.content_catalog(),
            "gamification": self._gamification_payload(state),
            "recentMistakes": self._recent_mistake_notes(state),
            "alerts": plan_strategy.get("weeklyFocus")
            or [
                "질문 답변은 현재 장면과 현재 문제를 같이 읽는 LLM 경로로 생성됩니다.",
                "오늘 강의를 끝내면 문제 풀이가 자동으로 열리고 계획도 즉시 갱신됩니다.",
                "문제를 제출하면 오답 원인과 다음날 복습 일정이 자동으로 다시 짜입니다.",
                "대시보드에서 단원을 바꾸면 강의와 evaluator가 함께 전환됩니다.",
            ],
            "coachMessage": plan_strategy.get("coachMessage")
            or "오늘은 계획표를 따라 강의와 문제만 수행하면 됩니다. 막히는 질문은 그 장면 위에서 바로 풀어드립니다.",
            "planStrategy": plan_strategy,
            "planStrategyStatus": self._strategy_status(state),
            "strategyJobs": [
                {
                    "id": job.id,
                    "status": job.status,
                    "reason": job.reason,
                    "queuedAt": job.queued_at,
                    "finishedAt": job.finished_at,
                    "provider": job.provider,
                }
                for job in state.strategy_jobs[-5:]
            ],
            "diagnosticCompleted": state.diagnostic_completed,
            "session": {
                "sessionId": "lesson-session-001",
                "companionCode": "math-p0",
                "eventStreamPath": "/ws/sessions/lesson-session-001",
            },
        }

    def update_profile(self, user_id: str, payload: dict) -> dict:
        state = self._state(user_id)
        state.profile = state.profile.from_dict(payload)
        state.survey_step = max(0, min(int(payload.get("surveyStep") or payload.get("survey_step") or state.survey_step or 0), 5))
        final_submit = bool(payload.get("surveyCompleted") or payload.get("survey_completed") or False)
        if final_submit:
            state.survey_completed = True
            state.diagnostic_completed = False
            self._ensure_diagnostic_questions(state, refresh=True)
        self._rebuild_plan(state)
        state.plan_strategy = {}
        state.strategy_jobs = []
        self.repository.save_state(state)
        return {
            "profile": to_jsonable(state.profile),
            "onboarding": {
                "surveyCompleted": state.survey_completed,
                "surveyStep": state.survey_step,
                "diagnosticCompleted": state.diagnostic_completed,
                "diagnosticAnswers": state.diagnostic_answers,
                "requiredRoute": self._required_route(state),
            },
            "dashboard": self.dashboard(user_id) if state.diagnostic_completed else None,
        }

    def save_diagnostic_progress(self, user_id: str, answers: dict[str, int]) -> dict:
        state = self._state(user_id)
        if not state.survey_completed:
            raise ValueError("설문을 먼저 완료해 주세요.")
        question_ids = {str(question["id"]) for question in self._ensure_diagnostic_questions(state)}
        state.diagnostic_answers = {
            str(key): int(value)
            for key, value in answers.items()
            if str(key) in question_ids
        }
        self.repository.save_state(state)
        return {
            "saved": True,
            "answerCount": len(state.diagnostic_answers),
            "requiredRoute": self._required_route(state),
        }

    def submit_diagnostic(self, user_id: str, answers: dict) -> dict:
        state = self._state(user_id)
        if not state.survey_completed:
            raise ValueError("설문을 먼저 완료해 주세요.")
        bundle = self._curriculum_bundle()
        question_bank = self._ensure_diagnostic_questions(state)
        submitted_answers = {
            **state.diagnostic_answers,
            **{str(key): int(value) for key, value in answers.items()},
        }
        missing_numbers = [
            index + 1
            for index, question in enumerate(question_bank)
            if question["id"] not in submitted_answers
        ]
        if missing_numbers:
            preview = ", ".join(str(number) for number in missing_numbers[:4])
            if len(missing_numbers) > 4:
                preview = f"{preview} 외 {len(missing_numbers) - 4}문항"
            raise ValueError(f"아직 답하지 않은 문항이 있어요. {preview}번을 먼저 확인해 주세요.")
        per_concept: dict[str, list[tuple[bool, float]]] = {}
        correct_count = 0
        for question in question_bank:
            answered = submitted_answers.get(question["id"])
            is_correct = answered == question["answer"]
            weight = DIFFICULTY_WEIGHTS.get(str(question.get("difficulty", "medium")), 1.0)
            per_concept.setdefault(question["concept"], []).append((is_correct, weight))
            if is_correct:
                correct_count += 1

        next_mastery: list[MasteryState] = []
        previous_scores = {item.id: item.score for item in state.mastery}
        for current in default_mastery(bundle):
            results = per_concept.get(current.id, [])
            if results:
                total_weight = sum(weight for _, weight in results)
                correct_weight = sum(weight for passed, weight in results if passed)
                ratio = correct_weight / total_weight if total_weight else 0.5
                score = max(35, min(94, int(current.score + (ratio - 0.55) * 58)))
            else:
                score = current.score
            trend = f"{score - previous_scores.get(current.id, current.score):+d}"
            risk = (
                "매우 높음"
                if score < 50
                else "높음"
                if score < 65
                else "중간"
                if score < 80
                else "낮음"
            )
            next_mastery.append(
                MasteryState(
                    id=current.id,
                    title=current.title,
                    score=score,
                    trend=trend,
                    risk=risk,
                    lesson_pack_id=current.lesson_pack_id,
                    problem_set_id=current.problem_set_id,
                    course_id=current.course_id,
                    course_title=current.course_title,
                )
            )
        state.mastery = next_mastery
        self._rebuild_plan(state)
        self._apply_content_selection(state, bundle)
        state.diagnostic_completed = True
        state.diagnostic_answers = submitted_answers
        self._queue_plan_strategy_job(state, "diagnostic-complete")
        self._record_gamification_event(state, "diagnostic-complete", 42)
        self.repository.save_state(state)

        weakest = min(state.mastery, key=lambda item: item.score)
        next_two = sorted(state.mastery, key=lambda item: item.score)[:2]
        return {
            "score": int((correct_count / len(question_bank)) * 100) if question_bank else 0,
            "summary": (
                f"진단 결과를 바탕으로 {weakest.title}를 가장 먼저 잡고, "
                f"{next_two[1].title if len(next_two) > 1 else weakest.title}까지 이어서 회복하는 계획으로 다시 짰습니다."
            ),
            "topRisks": [
                f"{weakest.title} 개념이 가장 먼저 보강되어야 합니다.",
                "고난도 문항일수록 첫 줄을 어떻게 시작할지 정리하는 연습이 필요합니다.",
                "오늘 못 끝낸 일정은 다음 날 자동으로 다시 끌어옵니다.",
            ],
            "recommendedTrack": state.practice_problem_set.get("title", "기본 공부 흐름"),
            "mastery": to_jsonable(state.mastery),
            "dashboard": self.dashboard(user_id),
        }

    def lesson_session(self, user_id: str) -> dict:
        state = self._state(user_id)
        bundle = self._bundle(state.content_bundle_id)
        lesson_pack = next(
            lesson for lesson in bundle.get("lessonPacks", []) if lesson["id"] == state.active_lesson_id
        )
        curated_scenes = self._curate_lesson_scenes(state.lesson_scenes)
        student_scenes = [self._student_scene(scene) for scene in curated_scenes]
        return {
            "sessionId": "lesson-session-001",
            "unitTitle": lesson_pack["unitTitle"],
            "teacherName": lesson_pack["teacherName"],
            "scenes": student_scenes,
            "outline": [{"id": scene["id"], "title": scene["title"]} for scene in student_scenes],
            "branchScenes": [
                {
                    "id": scene["id"],
                    "title": scene["title"],
                    "branchLabel": scene.get("branchLabel"),
                    "problemId": scene.get("problemId"),
                }
                for scene in student_scenes
                if scene.get("sceneGroup") == "problem-branch"
            ],
            "questionStarters": lesson_pack.get("questionStarters", []),
            "practiceProblem": self._problem_payload(state.practice_problem),
            "problemSet": {
                "id": state.active_problem_set_id,
                "bundleId": state.content_bundle_id,
                "lessonPackId": state.active_lesson_id,
                "title": state.practice_problem_set.get("title", "문제 묶음"),
                "problemCount": len(state.practice_problem_set.get("problems", [])),
                "problemTitles": [
                    problem["title"] for problem in state.practice_problem_set.get("problems", [])
                ],
                "evaluationTypes": sorted(
                    {
                        problem.get("evaluationType", "tangent-line")
                        for problem in state.practice_problem_set.get("problems", [])
                    }
                ),
                "problems": [
                    self._problem_payload(problem)
                    for problem in state.practice_problem_set.get("problems", [])
                ],
            },
            "realtime": {
                "wsPath": "/ws/sessions/lesson-session-001",
                "companionCode": "math-p0",
            },
            "experience": {
                "immersiveDefault": True,
                "llmAnswering": self.llm.configured,
                "autoAdvanceSeconds": 20,
            },
        }

    def complete_lesson(self, user_id: str) -> dict:
        state = self._state(user_id)
        state.plan = apply_lesson_completion(state.plan)
        self._queue_plan_strategy_job(state, "lesson-complete")
        self._record_gamification_event(state, "lesson-complete", 18)
        self.repository.save_state(state)
        return {
            "dashboard": self.dashboard(user_id),
            "lessonSession": self.lesson_session(user_id),
        }

    def answer_question(
        self,
        user_id: str,
        question: str,
        scene_id: str | None = None,
        selected_object_id: str | None = None,
        runtime_scene_ids: list[str] | None = None,
    ) -> dict:
        state = self._state(user_id, refresh_strategy=False)
        bundle = self._bundle(state.content_bundle_id)
        runtime_scenes = self._resolve_runtime_scenes(state, runtime_scene_ids)
        current_scene = next(
            (scene for scene in runtime_scenes if scene.get("id") == scene_id),
            self._find_scene(state, scene_id),
        )
        scene_objects = self._scene_object_summary(current_scene)
        interruption = self.llm.plan_lesson_interruption(
            question=question,
            unit_title=str(state.practice_problem_set.get("lessonTitle") or state.active_lesson_id),
            scene_title=str(current_scene.get("title") or state.active_lesson_id),
            narration=str(current_scene.get("narration", "")),
            scene_goal=str(current_scene.get("teachingGoal", "")),
            scene_takeaway=str(current_scene.get("takeaway", "")),
            scene_exam_cue=str(current_scene.get("examCue", "")),
            practice_statement=str(state.practice_problem.get("statement", "")),
            mastery_snapshot=to_jsonable(state.mastery),
            scene_objects=scene_objects,
            available_micro_scenes=list(bundle.get("microScenes", {}).keys()),
            selected_object_id=selected_object_id,
        )
        direct_reply = self.llm.answer_lesson_question(
            question=question,
            unit_title=str(state.practice_problem_set.get("lessonTitle") or state.active_lesson_id),
            scene_title=str(current_scene.get("title") or state.active_lesson_id),
            narration=str(current_scene.get("narration", "")),
            scene_goal=str(current_scene.get("teachingGoal", "")),
            scene_takeaway=str(current_scene.get("takeaway", "")),
            scene_exam_cue=str(current_scene.get("examCue", "")),
            practice_statement=str(state.practice_problem.get("statement", "")),
            mastery_snapshot=to_jsonable(state.mastery),
            scene_objects=scene_objects,
            selected_object_id=selected_object_id,
        )
        teacher_reply = direct_reply.text.strip() or interruption.teacher_reply
        base_scene = (
            bundle_question_scene(bundle, interruption.micro_scene_key or "recap")
            if interruption.scene_strategy == "micro"
            else current_scene
        )
        focus_object_id = (
            selected_object_id
            or interruption.focus_object_id
            or self._find_focus_object_id(current_scene, question)
        )
        interrupt_scene = self._annotated_interrupt_scene(
            base_scene,
            teacher_reply,
            focus_object_id,
            board_title=interruption.board_title,
            board_points=interruption.board_points,
            resume_label=interruption.resume_label,
        )
        branch_scenes = self._question_branch_scenes(
            question=question,
            answer=teacher_reply,
            base_scene=base_scene,
            practice_problem=state.practice_problem,
            focus_object_id=focus_object_id,
            board_title=interruption.board_title,
            board_points=interruption.board_points,
            branch_outline=interruption.branch_outline,
            resume_label=interruption.resume_label,
            include_connection=interruption.response_mode == "branch",
        )
        continuation_plan = self._build_lesson_continuation_plan(
            runtime_scenes=runtime_scenes,
            current_scene_id=str(current_scene.get("id")) if current_scene.get("id") else None,
            question=question,
        )
        student_interrupt_scene = self._student_scene(interrupt_scene)
        student_branch_scenes = [self._student_scene(scene) for scene in branch_scenes]
        self._record_gamification_event(state, "lesson-question", 6)
        self.repository.save_state(state)
        return {
            "mode": "branch-lesson" if interruption.response_mode == "branch" else "question-answer",
            "responseMode": interruption.response_mode,
            "scene": student_branch_scenes[0] if student_branch_scenes else student_interrupt_scene,
            "branchScenes": student_branch_scenes,
            "teacherReply": teacher_reply,
            "focusObjectId": focus_object_id,
            "llmSource": direct_reply.provider or interruption.provider,
            "resumeLabel": interruption.resume_label,
            "continuationPlan": continuation_plan,
            "syncEvent": {
                "type": "lesson.branch",
                "actor": "teacher",
                "sceneId": student_branch_scenes[0]["id"] if student_branch_scenes else student_interrupt_scene["id"],
                "sceneTitle": student_branch_scenes[0]["title"] if student_branch_scenes else student_interrupt_scene["title"],
                "scene": student_branch_scenes[0] if student_branch_scenes else student_interrupt_scene,
                "branchScenes": student_branch_scenes,
                "continuationPlan": continuation_plan,
                "teacherReply": teacher_reply,
            },
        }

    def submit_practice(self, user_id: str, payload: dict) -> dict:
        state = self._state(user_id)
        submitted_problem_id = state.practice_problem["id"]
        evaluation_type = str(state.practice_problem.get("evaluationType", "tangent-line"))
        evaluator = self._build_evaluator(state)
        evaluated = evaluator.evaluate(payload)
        answer_only_mode = bool(str(payload.get("finalAnswer", "")).strip()) and not any(
            str(payload.get(key, "")).strip() for key in ("stepOne", "stepTwo", "stepThree")
        )
        accepted_count = sum(1 for item in evaluated if item.accepted)
        solved = evaluated[-1].accepted if answer_only_mode and evaluated else accepted_count >= 3 and evaluated[-1].accepted
        state.plan = apply_attempt_feedback(
            state.plan,
            solved,
            state.practice_problem,
            bundle_id=state.content_bundle_id,
            lesson_id=state.active_lesson_id,
            problem_set_id=state.active_problem_set_id,
            problem_id=state.practice_problem.get("id"),
        )
        self._queue_plan_strategy_job(state, "practice-feedback")
        next_problem = self._recommended_follow_up_problem(state, solved)
        if solved and next_problem:
            self._advance_to_next_problem(state, next_problem)
        recovery_plan = {
            "today": to_jsonable(state.plan[0]),
            "tomorrow": to_jsonable(state.plan[1]) if len(state.plan) > 1 else None,
            "coachMessage": (
                "정답을 맞히면 다음 문제로 자동 이동합니다. 같은 구조를 더 높은 난도로 바로 이어가세요."
                if solved
                else "오늘은 복습 흐름을 열어두고, 내일은 같은 구조를 더 짧은 문제 묶음으로 다시 잡겠습니다."
            ),
            "nextProblem": next_problem,
        }
        attempt = PracticeAttempt(
            id=f"attempt-{uuid4().hex[:8]}",
            problem_id=submitted_problem_id,
            solved=solved,
            score=int((accepted_count / max(1, len(evaluated))) * 100),
            evaluated_steps=evaluated,
            submitted={
                "stepOne": str(payload.get("stepOne", "")),
                "stepTwo": str(payload.get("stepTwo", "")),
                "stepThree": str(payload.get("stepThree", "")),
                "scratchNote": str(payload.get("scratchNote", "")),
                "finalAnswer": str(payload.get("finalAnswer", "")),
            },
            summary=(
                "최종 답안만 제출했지만 구조가 맞았습니다. 다음 문제로 자동 이어지니 같은 흐름을 유지하세요."
                if answer_only_mode and solved
                else "최종 답안은 제출됐지만 정답 조건을 아직 못 맞췄습니다. 강의의 유형 분기 장면을 다시 보고 같은 문제를 재도전하세요."
                if answer_only_mode
                else
                "극대극소 공부 흐름이 안정됐습니다. 다음 문제에서도 후보점-부호변화-좌표 순서를 유지하세요."
                if evaluation_type == "maxmin-points" and solved
                else "극대극소 판정은 보였지만, 부호 변화와 좌표 마무리를 한 번 더 고정해야 합니다."
                if evaluation_type == "maxmin-points"
                else "핵심 구조는 거의 잡혔습니다. 다음 문제로 자동 이동하니 같은 풀이 흐름을 더 높은 난도로 이어가면 됩니다."
                if solved and next_problem
                else "핵심 구조는 거의 잡혔습니다. 이제 부호와 접점 계산을 같은 풀이 흐름으로 묶으면 안정됩니다."
                if solved
                else "접선 문제의 순서는 보였지만, 기울기와 접점을 분리해서 적는 습관이 더 필요합니다."
            ),
            recommended_scenes=["scene-slope", "scene-point"],
            recovery_plan=recovery_plan,
            created_at=self._utcnow_iso(),
        )
        state.mistake_notes = (
            self._build_mistake_notes(state, evaluated) + state.mistake_notes
        )[:18]
        self._record_gamification_event(
            state,
            "practice-solved" if solved else "practice-retry",
            34 if solved else 18,
        )
        self.repository.append_attempt(user_id, attempt)
        self.repository.save_state(state)
        return {
            "attempt": to_jsonable(attempt),
            "dashboard": self.dashboard(user_id),
            "lessonSession": self.lesson_session(user_id),
            "review": self.review_latest(user_id, track_progress=False),
            "mistakeNotes": self._recent_mistake_notes(state, limit=6),
            "syncEvent": {
                "type": "practice.submitted",
                "actor": "student",
                "attemptId": attempt.id,
                "solved": solved,
                "problemId": submitted_problem_id,
            },
        }

    def advance_practice(self, user_id: str) -> dict:
        state = self._state(user_id)
        moved = self._manual_next_problem(state)
        self.repository.save_state(state)
        return {
            "moved": bool(moved),
            "nextProblem": moved,
            "dashboard": self.dashboard(user_id),
            "lessonSession": self.lesson_session(user_id),
            "syncEvent": {
                "type": "practice.advanced",
                "actor": "student",
                "problemId": state.practice_problem.get("id"),
                "problemTitle": state.practice_problem.get("title"),
                "moved": bool(moved),
            },
        }

    def mistake_notes(self, user_id: str) -> dict:
        state = self._state(user_id)
        return {"notes": to_jsonable(state.mistake_notes)}

    def set_active_theme(self, user_id: str, theme_id: str) -> dict:
        state = self._state(user_id)
        if theme_id in state.gamification.unlocked_theme_ids:
            state.gamification.active_theme_id = theme_id
            self.repository.save_state(state)
        return self._theme_payload(state)

    def review_latest(self, user_id: str, *, track_progress: bool = True) -> dict:
        attempt = self.repository.latest_attempt(user_id)
        state = self._state(user_id)
        if attempt is None:
            return {
                "empty": True,
                "headline": "아직 풀이 기록이 없습니다.",
                "message": "강의를 들은 뒤 문제를 풀면 이곳에 내 풀이와 추천 풀이 비교가 생깁니다.",
            }
        attempted_problem = self._lookup_problem_by_id(attempt.problem_id) or {}
        evaluation_type = attempted_problem.get("evaluationType", "tangent-line")
        wrong_steps = [step for step in attempt.evaluated_steps if not step.accepted]
        good_steps = [step for step in attempt.evaluated_steps if step.accepted]
        if track_progress:
            self._record_gamification_event(state, "review-opened", 12)
            self.repository.save_state(state)
        return {
            "empty": False,
            "headline": "내 풀이를 추천 풀이 흐름과 비교합니다.",
            "attemptId": attempt.id,
            "solved": attempt.solved,
            "summary": attempt.summary,
            "wrongSteps": to_jsonable(wrong_steps),
            "goodSteps": to_jsonable(good_steps),
            "retrySet": [
                "극값 후보 재확인 문제 2문항",
                "부호 변화 판정 미니 퀴즈 1문항",
                "극대점/극소점 좌표화 3분 복기",
            ]
            if evaluation_type == "maxmin-points"
            else [
                "도함수 부호 재확인 문제 2문항",
                "접점 좌표 계산 미니 퀴즈 1문항",
                "직선식 정리 3분 복기",
            ],
            "tomorrowPlan": attempt.recovery_plan.get("tomorrow"),
            "nextProblem": attempt.recovery_plan.get("nextProblem"),
            "mistakeNotes": self._recent_mistake_notes(state, limit=6),
        }

    def list_session_events(self, session_id: str) -> list[dict]:
        return self.repository.list_session_events(session_id)

    def register_session_event(self, session_id: str, actor: str, payload: dict) -> dict:
        event = {
            "id": uuid4().hex,
            "type": payload.get("type", "session.event"),
            "actor": actor,
            "payload": deepcopy(payload.get("payload", payload)),
            "timestamp": self._utcnow_iso(),
            "sessionId": session_id,
        }
        self.repository.append_session_event(session_id, event)
        return event


service = DemoService(build_state_repository(), build_content_repository())
