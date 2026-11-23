"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";

import { TaskLaunchButton } from "@/components/task-launch-button";
import { ErrorState, LoadingState, Progress, taskKind } from "@/components/ui";
import { useAuthGuard } from "@/components/use-auth-guard";
import { api } from "@/lib/api";
import { buildTrackViews } from "@/lib/curriculum";
import type { DashboardResponse, Task } from "@/lib/types";

const STATUS_LABEL: Record<string, { label: string; className: string }> = {
  ready: { label: "시작 가능", className: "badge-primary" },
  retry: { label: "재도전", className: "badge-warning" },
  done: { label: "완료", className: "badge-success" },
  locked: { label: "잠김", className: "" },
  planned: { label: "예정", className: "" },
};

function TaskRow({ task }: { task: Task }) {
  const kind = taskKind(task.type);
  const status = STATUS_LABEL[task.status] ?? { label: task.status, className: "" };
  const actionable = task.status === "ready" || task.status === "retry";
  return (
    <div className={`task ${task.status === "done" ? "is-done" : ""}`}>
      <span className={`task-icon ${kind.className}`} aria-hidden="true">
        {kind.label}
      </span>
      <div>
        <div className="task-title">{task.title}</div>
        <div className="task-sub row" style={{ gap: 8 }}>
          <span>{task.minutes}분</span>
          <span className={`badge ${status.className}`}>{status.label}</span>
        </div>
      </div>
      {actionable ? (
        <TaskLaunchButton task={task} className={`btn btn-sm ${task.status === "ready" ? "btn-primary" : "btn-secondary"}`} />
      ) : null}
    </div>
  );
}

export default function DashboardPage() {
  const { ready, session } = useAuthGuard();
  const [dashboard, setDashboard] = useState<DashboardResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!ready) return;
    api.dashboard().then(setDashboard).catch((reason) => setError(reason.message));
  }, [ready]);

  const tracks = useMemo(() => (dashboard ? buildTrackViews(dashboard) : []), [dashboard]);

  if (!ready) {
    return <LoadingState message="불러오는 중" />;
  }

  if (error) {
    return (
      <ErrorState
        title="대시보드를 불러오지 못했어요"
        message={error}
        action={
          <button className="btn btn-primary" type="button" onClick={() => window.location.reload()}>
            다시 시도
          </button>
        }
      />
    );
  }

  if (!dashboard) {
    return <LoadingState message="불러오는 중" />;
  }

  const { stats, todayMission, todayPlan, weeklyPlan, activeContent, gamification } = dashboard;
  const currentTask = todayMission.currentTask ?? null;
  const name = session?.displayName ?? "";
  const doneCount = todayPlan.tasks.filter((task) => task.status === "done").length;
  // The card describes the plan's next task when there is one; otherwise the loaded lesson.
  const nextLessonName = currentTask
    ? currentTask.title.split(" · ").slice(1).join(" · ") || currentTask.title
    : activeContent?.lessonTitle ?? todayMission.recommendedUnit;
  const todayLabel = new Date().toLocaleDateString("ko-KR", { month: "long", day: "numeric", weekday: "long" });

  return (
    <div className="page">
      <header className="page-header greeting">
        <div>
          <span className="eyebrow">{todayLabel}</span>
          <h1 style={{ marginTop: 4 }}>{name ? `안녕하세요, ${name}님` : "안녕하세요"}</h1>
          <p>{todayMission.headline}</p>
        </div>
        {gamification?.streakDays ? (
          <span className="badge badge-warning" style={{ height: 30, fontSize: 13 }}>
            <span className="dot dot-warning" aria-hidden="true" />
            {gamification.streakDays}일 연속 학습
          </span>
        ) : null}
      </header>

      <section className="stats-grid" aria-label="학습 현황">
        <div className="card stat">
          <span className="stat-label">수능까지</span>
          <span className="stat-value">D-{stats.daysLeft}</span>
          <span className="stat-foot">주 {stats.weeklyStudyHours}시간 계획</span>
        </div>
        <div className="card stat">
          <span className="stat-label">수학 목표</span>
          <span className="stat-value">
            {stats.targetScore}
            <small>점</small>
          </span>
          <span className="stat-foot">원점수 기준</span>
        </div>
        <div className="card stat">
          <span className="stat-label">오늘 학습</span>
          <span className="stat-value">
            {doneCount}
            <small>/ {todayPlan.tasks.length}개</small>
          </span>
          <span className="stat-foot">목표 {stats.todayMinutes}분</span>
        </div>
        <div className="card stat">
          <span className="stat-label">수능 준비도</span>
          <span className="stat-value">
            {stats.readiness}
            <small>%</small>
          </span>
          <Progress value={stats.readiness} size="sm" tone="auto" label="수능 준비도" />
        </div>
      </section>

      <div className="grid-main">
        <div className="stack-lg">
          <section>
            <div className="section-head">
              <h2>이어서 학습</h2>
            </div>
            <article className="card continue-card">
              <div className="continue-thumb" aria-hidden="true">
                <span>AI 칠판 강의</span>
                <strong>{nextLessonName}</strong>
                <span className="eq">f′(x) = lim (h→0) …</span>
              </div>
              <div className="continue-body">
                <div>
                  <span className="badge badge-primary">{todayMission.activeTrack || "오늘 강의"}</span>
                  <h3 style={{ marginTop: 10 }}>{currentTask?.title ?? activeContent?.lessonTitle ?? "추천 강의를 준비하고 있어요"}</h3>
                </div>
                <div className="meta">
                  {currentTask ? <span>{currentTask.minutes}분</span> : null}
                  {!currentTask && activeContent ? (
                    <span>
                      {activeContent.problemSetTitle} · {activeContent.problemCount}문항
                    </span>
                  ) : null}
                </div>
                <div className="row">
                  {currentTask ? (
                    <TaskLaunchButton task={currentTask} className="btn btn-primary" />
                  ) : (
                    <Link className="btn btn-primary" href="/lesson">
                      강의 시작
                    </Link>
                  )}
                  <Link className="btn btn-secondary" href="/practice">
                    문제 풀기
                  </Link>
                </div>
              </div>
            </article>
          </section>

          <section className="card">
            <div className="card-header">
              <div>
                <h3>오늘의 학습</h3>
                <p>{todayPlan.focus}</p>
              </div>
              <span className="muted" style={{ fontSize: 13, whiteSpace: "nowrap" }}>
                {doneCount}/{todayPlan.tasks.length} 완료
              </span>
            </div>
            <div className="task-list" style={{ marginTop: 12 }}>
              {todayPlan.tasks.map((task) => (
                <TaskRow key={task.id} task={task} />
              ))}
            </div>
          </section>

          <section>
            <div className="section-head">
              <h2>과목별 학습</h2>
              <span className="link">숙련도 점수 기준</span>
            </div>
            <div className="grid-3">
              {tracks.map((track) => (
                <Link key={track.id} href={`/dashboard/${track.id}`} className="card card-link course-card">
                  <div className="course-card-top">
                    <div>
                      <h3>{track.title}</h3>
                      <p className="sub">{track.subtitle}</p>
                    </div>
                    <span className="course-score">
                      {track.averageScore}
                      <small>점</small>
                    </span>
                  </div>
                  <Progress value={track.averageScore} size="sm" tone="auto" label={`${track.title} 숙련도`} />
                  <div className="course-card-foot">
                    <span className="weak">
                      약점 <b>{track.weakUnitTitle}</b>
                    </span>
                    <span>{track.units.length}개 단원</span>
                  </div>
                </Link>
              ))}
            </div>
          </section>
        </div>

        <aside className="stack">
          {dashboard.coachMessage ? (
            <section className="card card-pad-sm">
              <div className="row" style={{ marginBottom: 8 }}>
                <span className="avatar" aria-hidden="true">
                  AI
                </span>
                <strong style={{ fontSize: 14 }}>오늘의 코멘트</strong>
              </div>
              <p className="text-secondary" style={{ fontSize: 14 }}>
                {dashboard.coachMessage}
              </p>
            </section>
          ) : null}

          <section className="card card-pad-sm">
            <h3 style={{ fontSize: 15, marginBottom: 12 }}>약점 단원</h3>
            <div className="weak-list">
              {todayMission.weakUnits.map((unit) => (
                <span key={unit} className="badge badge-danger">
                  {unit}
                </span>
              ))}
            </div>
          </section>

          <section className="card card-pad-sm">
            <h3 style={{ fontSize: 15, marginBottom: 12 }}>이번 주 계획</h3>
            <div className="week-list">
              {weeklyPlan.slice(0, 7).map((day) => (
                <div key={day.date} className="week-day">
                  <span className={`date ${day.label === "오늘" ? "today" : ""}`}>{day.label}</span>
                  <div>
                    <strong>{day.theme}</strong>
                    <span>
                      학습 {day.tasks.length}개 · {day.minutesTarget ?? day.minutes_target ?? day.tasks.reduce((sum, t) => sum + t.minutes, 0)}분
                    </span>
                  </div>
                </div>
              ))}
            </div>
          </section>

          <Link className="card card-link card-pad-sm" href="/review">
            <div className="row-between">
            <div>
              <strong style={{ fontSize: 15 }}>오답노트</strong>
              <p className="muted" style={{ fontSize: 13 }}>
                최근 틀린 문제 {dashboard.recentMistakes?.length ?? 0}개
              </p>
            </div>
            <span aria-hidden="true">→</span>
            </div>
          </Link>
        </aside>
      </div>
    </div>
  );
}
