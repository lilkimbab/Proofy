from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import date, datetime
from typing import Any


@dataclass
class LearnerProfile:
    nickname: str
    exam_date: str
    subject_targets: dict[str, int]
    weekly_study_hours: int
    daily_minutes: int
    weak_units: list[str]
    study_mood: str

    @property
    def math_target_score(self) -> int:
        return int(self.subject_targets.get("math", 84))

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "LearnerProfile":
        legacy_target = int(data.get("target_score") or data.get("targetScore") or 84)
        raw_targets = data.get("subject_targets") or data.get("subjectTargets") or {}
        subject_targets = {
            "korean": int(raw_targets.get("korean") or 80),
            "math": int(raw_targets.get("math") or legacy_target),
            "english": int(raw_targets.get("english") or 78),
            "inquiry1": int(raw_targets.get("inquiry1") or 76),
            "inquiry2": int(raw_targets.get("inquiry2") or 76),
        }
        return cls(
            nickname=str(data.get("nickname") or data.get("name") or "홍길동"),
            exam_date=str(data.get("exam_date") or data.get("examDate") or "2026-11-19"),
            subject_targets=subject_targets,
            weekly_study_hours=int(
                data.get("weekly_study_hours") or data.get("weeklyStudyHours") or 18
            ),
            daily_minutes=int(data.get("daily_minutes") or data.get("dailyMinutes") or 120),
            weak_units=list(data.get("weak_units") or data.get("weakUnits") or ["미분"]),
            study_mood=str(data.get("study_mood") or data.get("studyMood") or "실전 위주"),
        )


@dataclass
class MasteryState:
    id: str
    title: str
    score: int
    trend: str
    risk: str
    lesson_pack_id: str | None = None
    problem_set_id: str | None = None
    course_id: str | None = None
    course_title: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MasteryState":
        return cls(
            id=str(data["id"]),
            title=str(data["title"]),
            score=int(data["score"]),
            trend=str(data["trend"]),
            risk=str(data["risk"]),
            lesson_pack_id=data.get("lesson_pack_id") or data.get("lessonPackId"),
            problem_set_id=data.get("problem_set_id") or data.get("problemSetId"),
            course_id=data.get("course_id") or data.get("courseId"),
            course_title=data.get("course_title") or data.get("courseTitle"),
        )


@dataclass
class StudyTask:
    id: str
    title: str
    type: str
    minutes: int
    status: str
    launch: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "StudyTask":
        return cls(
            id=str(data["id"]),
            title=str(data["title"]),
            type=str(data["type"]),
            minutes=int(data["minutes"]),
            status=str(data["status"]),
            launch=dict(data.get("launch") or {}),
        )


@dataclass
class StudyDay:
    date: str
    label: str
    theme: str
    focus: str
    tasks: list[StudyTask]
    minutes_target: int

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "StudyDay":
        return cls(
            date=str(data["date"]),
            label=str(data["label"]),
            theme=str(data["theme"]),
            focus=str(data["focus"]),
            tasks=[StudyTask.from_dict(task) for task in data.get("tasks", [])],
            minutes_target=int(data.get("minutes_target") or data.get("minutesTarget") or 0),
        )


@dataclass
class PracticeStepFeedback:
    id: str
    label: str
    accepted: bool
    reason: str
    expected: str
    error_type: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PracticeStepFeedback":
        return cls(
            id=str(data["id"]),
            label=str(data["label"]),
            accepted=bool(data["accepted"]),
            reason=str(data["reason"]),
            expected=str(data["expected"]),
            error_type=data.get("error_type") or data.get("errorType"),
        )


@dataclass
class PracticeAttempt:
    id: str
    problem_id: str
    solved: bool
    score: int
    evaluated_steps: list[PracticeStepFeedback]
    submitted: dict[str, str]
    summary: str
    recommended_scenes: list[str]
    recovery_plan: dict[str, Any]
    created_at: str

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PracticeAttempt":
        return cls(
            id=str(data["id"]),
            problem_id=str(data["problem_id"] or data["problemId"]),
            solved=bool(data["solved"]),
            score=int(data["score"]),
            evaluated_steps=[
                PracticeStepFeedback.from_dict(item)
                for item in data.get("evaluated_steps") or data.get("evaluatedSteps", [])
            ],
            submitted=dict(data.get("submitted", {})),
            summary=str(data["summary"]),
            recommended_scenes=list(
                data.get("recommended_scenes") or data.get("recommendedScenes", [])
            ),
            recovery_plan=dict(data.get("recovery_plan") or data.get("recoveryPlan") or {}),
            created_at=str(data.get("created_at") or data.get("createdAt") or ""),
        )


@dataclass
class HighlightThreadMessage:
    id: str
    role: str
    content: str
    created_at: str

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "HighlightThreadMessage":
        return cls(
            id=str(data["id"]),
            role=str(data["role"]),
            content=str(data["content"]),
            created_at=str(data.get("created_at") or data.get("createdAt") or ""),
        )


@dataclass
class DocumentChunk:
    id: str
    page: int
    order: int
    text: str

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DocumentChunk":
        return cls(
            id=str(data["id"]),
            page=int(data["page"]),
            order=int(data.get("order", 0)),
            text=str(data["text"]),
        )


@dataclass
class DocumentHighlight:
    id: str
    chunk_id: str
    text: str
    note: str
    messages: list[HighlightThreadMessage]
    created_at: str

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DocumentHighlight":
        return cls(
            id=str(data["id"]),
            chunk_id=str(data.get("chunk_id") or data.get("chunkId")),
            text=str(data["text"]),
            note=str(data.get("note", "")),
            messages=[
                HighlightThreadMessage.from_dict(item) for item in data.get("messages", [])
            ],
            created_at=str(data.get("created_at") or data.get("createdAt") or ""),
        )


@dataclass
class DocumentRecord:
    id: str
    title: str
    filename: str
    content_type: str
    file_path: str
    page_count: int
    status: str
    chunks: list[DocumentChunk]
    highlights: list[DocumentHighlight]
    uploaded_at: str

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DocumentRecord":
        return cls(
            id=str(data["id"]),
            title=str(data.get("title") or data.get("filename") or "문서"),
            filename=str(data.get("filename") or data.get("title") or "document.pdf"),
            content_type=str(data.get("content_type") or data.get("contentType") or "application/pdf"),
            file_path=str(data.get("file_path") or data.get("filePath") or ""),
            page_count=int(data.get("page_count") or data.get("pageCount") or 0),
            status=str(data.get("status", "ready")),
            chunks=[DocumentChunk.from_dict(item) for item in data.get("chunks", [])],
            highlights=[
                DocumentHighlight.from_dict(item) for item in data.get("highlights", [])
            ],
            uploaded_at=str(data.get("uploaded_at") or data.get("uploadedAt") or ""),
        )


@dataclass
class MistakeNote:
    id: str
    problem_id: str
    problem_title: str
    mistake_type: str
    trigger_step: str
    summary: str
    correction: str
    retry_prompt: str
    created_at: str

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MistakeNote":
        return cls(
            id=str(data["id"]),
            problem_id=str(data.get("problem_id") or data.get("problemId")),
            problem_title=str(data.get("problem_title") or data.get("problemTitle")),
            mistake_type=str(data.get("mistake_type") or data.get("mistakeType")),
            trigger_step=str(data.get("trigger_step") or data.get("triggerStep")),
            summary=str(data["summary"]),
            correction=str(data["correction"]),
            retry_prompt=str(data.get("retry_prompt") or data.get("retryPrompt")),
            created_at=str(data.get("created_at") or data.get("createdAt") or ""),
        )


@dataclass
class QuestionHistoryEntry:
    id: str
    question: str
    category: str
    weight: int
    concept_id: str
    unit_title: str
    lesson_id: str
    scene_id: str
    response_mode: str
    created_at: str

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "QuestionHistoryEntry":
        return cls(
            id=str(data["id"]),
            question=str(data.get("question") or ""),
            category=str(data.get("category") or "concept"),
            weight=int(data.get("weight") or 1),
            concept_id=str(data.get("concept_id") or data.get("conceptId") or ""),
            unit_title=str(data.get("unit_title") or data.get("unitTitle") or ""),
            lesson_id=str(data.get("lesson_id") or data.get("lessonId") or ""),
            scene_id=str(data.get("scene_id") or data.get("sceneId") or ""),
            response_mode=str(data.get("response_mode") or data.get("responseMode") or "answer"),
            created_at=str(data.get("created_at") or data.get("createdAt") or ""),
        )


@dataclass
class StrategyJob:
    id: str
    status: str
    reason: str
    queued_at: str
    started_at: str = ""
    finished_at: str = ""
    provider: str = ""
    error: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "StrategyJob":
        return cls(
            id=str(data["id"]),
            status=str(data.get("status") or "pending"),
            reason=str(data.get("reason") or "plan-change"),
            queued_at=str(data.get("queued_at") or data.get("queuedAt") or ""),
            started_at=str(data.get("started_at") or data.get("startedAt") or ""),
            finished_at=str(data.get("finished_at") or data.get("finishedAt") or ""),
            provider=str(data.get("provider") or ""),
            error=str(data.get("error") or ""),
        )


@dataclass
class DailyFlowState:
    date: str
    lesson_done: bool = False
    practice_done: bool = False
    review_done: bool = False
    question_done: bool = False
    points_earned: int = 0

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DailyFlowState":
        return cls(
            date=str(data.get("date") or ""),
            lesson_done=bool(data.get("lesson_done") or data.get("lessonDone") or False),
            practice_done=bool(data.get("practice_done") or data.get("practiceDone") or False),
            review_done=bool(data.get("review_done") or data.get("reviewDone") or False),
            question_done=bool(data.get("question_done") or data.get("questionDone") or False),
            points_earned=int(data.get("points_earned") or data.get("pointsEarned") or 0),
        )


@dataclass
class GamificationState:
    streak_days: int
    last_activity_date: str
    xp: int
    level: int
    active_theme_id: str
    unlocked_theme_ids: list[str]
    recent_unlocks: list[str]
    best_streak_days: int = 0
    recovery_tokens: int = 0
    lesson_completions: int = 0
    practice_attempts: int = 0
    solved_attempts: int = 0
    review_sessions: int = 0
    question_count: int = 0
    daily_flows: list[DailyFlowState] = field(default_factory=list)
    milestone_ids: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "GamificationState":
        return cls(
            streak_days=int(data.get("streak_days") or data.get("streakDays") or 0),
            last_activity_date=str(
                data.get("last_activity_date") or data.get("lastActivityDate") or ""
            ),
            xp=int(data.get("xp") or 0),
            level=int(data.get("level") or 1),
            best_streak_days=int(data.get("best_streak_days") or data.get("bestStreakDays") or 0),
            recovery_tokens=int(data.get("recovery_tokens") or data.get("recoveryTokens") or 0),
            lesson_completions=int(
                data.get("lesson_completions") or data.get("lessonCompletions") or 0
            ),
            practice_attempts=int(
                data.get("practice_attempts") or data.get("practiceAttempts") or 0
            ),
            solved_attempts=int(
                data.get("solved_attempts") or data.get("solvedAttempts") or 0
            ),
            review_sessions=int(
                data.get("review_sessions") or data.get("reviewSessions") or 0
            ),
            question_count=int(data.get("question_count") or data.get("questionCount") or 0),
            daily_flows=[
                DailyFlowState.from_dict(item)
                for item in data.get("daily_flows") or data.get("dailyFlows") or []
            ],
            milestone_ids=list(data.get("milestone_ids") or data.get("milestoneIds") or []),
            active_theme_id=str(
                data.get("active_theme_id") or data.get("activeThemeId") or "chalk-amber"
            ),
            unlocked_theme_ids=list(
                data.get("unlocked_theme_ids")
                or data.get("unlockedThemeIds")
                or ["chalk-amber"]
            ),
            recent_unlocks=list(data.get("recent_unlocks") or data.get("recentUnlocks") or []),
        )


@dataclass
class AppState:
    user_id: str
    profile: LearnerProfile
    mastery: list[MasteryState]
    plan: list[StudyDay]
    content_bundle_id: str
    active_lesson_id: str
    active_problem_set_id: str
    lesson_scenes: list[dict[str, Any]]
    practice_problem_set: dict[str, Any]
    practice_problem: dict[str, Any]
    plan_strategy: dict[str, Any] = field(default_factory=dict)
    strategy_jobs: list[StrategyJob] = field(default_factory=list)
    survey_completed: bool = False
    survey_step: int = 0
    diagnostic_session_id: str = ""
    diagnostic_questions: list[dict[str, Any]] = field(default_factory=list)
    diagnostic_answers: dict[str, int] = field(default_factory=dict)
    diagnostic_completed: bool = False
    question_history: list[QuestionHistoryEntry] = field(default_factory=list)
    attempts: list[PracticeAttempt] = field(default_factory=list)
    documents: list[DocumentRecord] = field(default_factory=list)
    mistake_notes: list[MistakeNote] = field(default_factory=list)
    gamification: GamificationState = field(
        default_factory=lambda: GamificationState(
            streak_days=0,
            last_activity_date="",
            xp=0,
            level=1,
            best_streak_days=0,
            recovery_tokens=0,
            lesson_completions=0,
            practice_attempts=0,
            solved_attempts=0,
            review_sessions=0,
            question_count=0,
            daily_flows=[],
            milestone_ids=[],
            active_theme_id="chalk-amber",
            unlocked_theme_ids=["chalk-amber"],
            recent_unlocks=[],
        )
    )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AppState":
        return cls(
            user_id=str(data.get("user_id") or data.get("userId") or "demo-user"),
            profile=LearnerProfile.from_dict(data["profile"]),
            mastery=[MasteryState.from_dict(item) for item in data.get("mastery", [])],
            plan=[StudyDay.from_dict(item) for item in data.get("plan", [])],
            survey_completed=bool(
                data.get("survey_completed") or data.get("surveyCompleted") or False
            ),
            survey_step=int(data.get("survey_step") or data.get("surveyStep") or 0),
            diagnostic_session_id=str(
                data.get("diagnostic_session_id") or data.get("diagnosticSessionId") or ""
            ),
            diagnostic_questions=list(
                data.get("diagnostic_questions") or data.get("diagnosticQuestions") or []
            ),
            diagnostic_answers={
                str(key): int(value)
                for key, value in (
                    data.get("diagnostic_answers") or data.get("diagnosticAnswers") or {}
                ).items()
            },
            diagnostic_completed=bool(
                data.get("diagnostic_completed") or data.get("diagnosticCompleted") or False
            ),
            question_history=[
                QuestionHistoryEntry.from_dict(item)
                for item in data.get("question_history") or data.get("questionHistory") or []
            ],
            content_bundle_id=str(
                data.get("content_bundle_id")
                or data.get("contentBundleId")
                or "suneung-math-curriculum-v1"
            ),
            active_lesson_id=str(
                data.get("active_lesson_id")
                or data.get("activeLessonId")
                or "lesson-common1-polynomial"
            ),
            active_problem_set_id=str(
                data.get("active_problem_set_id")
                or data.get("activeProblemSetId")
                or "set-common1-polynomial"
            ),
            lesson_scenes=list(data.get("lesson_scenes") or data.get("lessonScenes") or []),
            practice_problem_set=dict(
                data.get("practice_problem_set") or data.get("practiceProblemSet") or {}
            ),
            practice_problem=dict(
                data.get("practice_problem") or data.get("practiceProblem") or {}
            ),
            plan_strategy=dict(data.get("plan_strategy") or data.get("planStrategy") or {}),
            strategy_jobs=[
                StrategyJob.from_dict(item)
                for item in data.get("strategy_jobs") or data.get("strategyJobs") or []
            ],
            attempts=[
                PracticeAttempt.from_dict(item) for item in data.get("attempts", [])
            ],
            documents=[DocumentRecord.from_dict(item) for item in data.get("documents", [])],
            mistake_notes=[
                MistakeNote.from_dict(item)
                for item in data.get("mistake_notes") or data.get("mistakeNotes", [])
            ],
            gamification=GamificationState.from_dict(data.get("gamification", {})),
        )


def to_jsonable(value: Any) -> Any:
    if is_dataclass(value):
        return to_jsonable(asdict(value))
    if isinstance(value, dict):
        return {key: to_jsonable(inner) for key, inner in value.items()}
    if isinstance(value, list):
        return [to_jsonable(inner) for inner in value]
    if isinstance(value, tuple):
        return [to_jsonable(inner) for inner in value]
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value
