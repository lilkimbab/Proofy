"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";

import { TaskLaunchButton } from "@/components/task-launch-button";
import { ErrorState, LoadingState, Progress, taskKind } from "@/components/ui";
import { useAuthGuard } from "@/components/use-auth-guard";
import { api } from "@/lib/api";
import { buildTrackViews } from "@/lib/curriculum";
import type { DashboardResponse, Task } from "@/lib/types";

type Tab = "today" | "week" | "subjects";

const TABS: Array<{ id: Tab; label: string }> = [
  { id: "today", label: "오늘" },
  { id: "week", label: "이번 주" },
  { id: "subjects", label: "과목별 실력" },
];

const STATUS_LABEL: Record<string, { label: string; className: string }> = {
  ready: { label: "시작 가능", className: "badge-primary" },
  retry: { label: "재도전", className: "badge-warning" },
  done: { label: "완료", className: "badge-success" },
  locked: { label: "잠김", className: "" },
  planned: { label: "예정", className: "" },
};

/** "미적분 · 미분 개념 다시 보기" -> "미분 개념 다시 보기" */
function shortTitle(title: string) {
  return title.split(" · ").slice(1).join(" · ") || title;
}

function TodayStep({ task, index }: { task: Task; index: number }) {
  const kind = taskKind(task.type);
  const status = STATUS_LABEL[task.status] ?? { label: task.status, className: "" };
  const actionable = task.status === "ready" || task.status === "retry";
  return (
    <li className={`day-step is-${task.status}`}>
      <span className="day-step-no">{task.status === "done" ? "✓" : index + 1}</span>
      <div className="day-step-body">
        <span className={`day-step-kind ${kind.className}`}>{kind.label}</span>
        <strong>{shortTitle(task.title)}</strong>
        <span className="day-step-meta">
          {task.minutes}분 · <span className={`badge ${status.className}`}>{status.label}</span>
        </span>
      </div>
      {actionable ? <TaskLaunchButton task={task} className="btn btn-secondary btn-sm" /> : null}
    </li>
  );
}

export default function DashboardPage() {
  const { ready, session } = useAuthGuard();
  const [dashboard, setDashboard] = useState<DashboardResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<Tab>("today");

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
  const currentIndex = currentTask ? todayPlan.tasks.findIndex((task) => task.id === currentTask.id) : -1;
  const todayLabel = new Date().toLocaleDateString("ko-KR", { month: "long", day: "numeric", weekday: "long" });

  return (
    <div className="page">
      <header className="dash-head">
        <div>
          <span className="eyebrow">{todayLabel}</span>
          <h1>{name ? `${name}님, 안녕하세요` : "안녕하세요"}</h1>
        </div>
        <dl className="status-strip" aria-label="학습 현황">
          <div>
            <dt>시험</dt>
            <dd>D-{stats.daysLeft}</dd>
          </div>
          <div>
            <dt>수학 목표</dt>
            <dd>{stats.targetScore}점</dd>
          </div>
          <div>
            <dt>준비도</dt>
            <dd>{stats.readiness}%</dd>
          </div>
          {gamification?.streakDays ? (
            <div>
              <dt>연속 학습</dt>
              <dd>{gamification.streakDays}일</dd>
            </div>
          ) : null}
        </dl>
      </header>

      <nav className="page-tabs" role="tablist" aria-label="대시보드 보기">
        {TABS.map((item) => (
          <button
            key={item.id}
            type="button"
            role="tab"
            aria-selected={tab === item.id}
            className={tab === item.id ? "active" : ""}
            onClick={() => setTab(item.id)}
          >
            {item.label}
          </button>
        ))}
      </nav>

      {tab === "today" ? (
        <div className="stack-lg">
          <section className="now-card">
            <div className="now-main">
              <span className="now-label">
                지금 할 공부{currentIndex >= 0 ? ` · 오늘 ${currentIndex + 1}/${todayPlan.tasks.length}` : ""}
              </span>
              <h2>{currentTask ? shortTitle(currentTask.title) : activeContent?.lessonTitle ?? "오늘 학습을 모두 마쳤어요"}</h2>
              <p className="now-meta">
                {currentTask
                  ? `${todayMission.activeTrack} · ${taskKind(currentTask.type).label} ${currentTask.minutes}분`
                  : "내일 계획은 '이번 주' 탭에서 볼 수 있어요."}
              </p>
              <div className="row" style={{ marginTop: 20 }}>
                {currentTask ? (
                  <TaskLaunchButton task={currentTask} className="btn btn-primary btn-lg" />
                ) : (
                  <Link className="btn btn-primary btn-lg" href="/lesson">
                    강의실 가기
                  </Link>
                )}
                <Link className="btn btn-ghost" href="/practice">
                  문제만 풀기
                </Link>
              </div>
            </div>
            {dashboard.coachMessage ? (
              <aside className="sticky-note" aria-label="선생님 메모">
                <span className="sticky-note-label">선생님 메모</span>
                <p>{dashboard.coachMessage}</p>
              </aside>
            ) : null}
          </section>

          <section>
            <div className="section-head">
              <h2>오늘의 순서</h2>
              <span className="link">
                {doneCount}/{todayPlan.tasks.length} 완료 · 목표 {stats.todayMinutes}분
              </span>
            </div>
            <ol className="day-steps">
              {todayPlan.tasks.map((task, index) => (
                <TodayStep key={task.id} task={task} index={index} />
              ))}
            </ol>
          </section>
        </div>
      ) : null}

      {tab === "week" ? (
        <section className="card">
          <div className="card-header">
            <div>
              <h3>이번 주 계획</h3>
              <p>주 {stats.weeklyStudyHours}시간 기준으로 나눴어요</p>
            </div>
          </div>
          <ol className="week-table">
            {weeklyPlan.slice(0, 7).map((day) => (
              <li key={day.date} className={day.label === "오늘" ? "is-today" : ""}>
                <span className="week-label">{day.label}</span>
                <div>
                  <strong>{day.theme}</strong>
                  <span>{day.tasks.map((task) => shortTitle(task.title)).join(" → ")}</span>
                </div>
                <span className="week-min">
                  {day.minutesTarget ?? day.minutes_target ?? day.tasks.reduce((sum, t) => sum + t.minutes, 0)}분
                </span>
              </li>
            ))}
          </ol>
        </section>
      ) : null}

      {tab === "subjects" ? (
        <div className="stack-lg">
          <section className="weak-band">
            <strong>먼저 채울 단원</strong>
            <div className="weak-list">
              {todayMission.weakUnits.map((unit) => (
                <span key={unit} className="badge badge-danger">
                  {unit}
                </span>
              ))}
            </div>
            <Link className="btn btn-ghost btn-sm" href="/review" style={{ marginLeft: "auto" }}>
              오답노트 {dashboard.recentMistakes?.length ?? 0}개 →
            </Link>
          </section>
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
        </div>
      ) : null}
    </div>
  );
}
