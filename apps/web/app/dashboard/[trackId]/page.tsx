"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";

import { TaskLaunchButton } from "@/components/task-launch-button";
import { ErrorState, LoadingState, Progress } from "@/components/ui";
import { useAuthGuard } from "@/components/use-auth-guard";
import { api } from "@/lib/api";
import { buildTrackViews, buildTrackWeeklyPlan, findTrackView } from "@/lib/curriculum";
import type { DashboardResponse } from "@/lib/types";

function riskBadge(risk: string) {
  if (risk.includes("높")) return "badge-danger";
  if (risk.includes("중")) return "badge-warning";
  if (risk.includes("낮")) return "badge-success";
  return "";
}

export default function DashboardTrackPage() {
  const params = useParams<{ trackId: string }>();
  const router = useRouter();
  const { ready } = useAuthGuard();
  const [dashboard, setDashboard] = useState<DashboardResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [activatingId, setActivatingId] = useState<string | null>(null);

  useEffect(() => {
    if (!ready) return;
    api.dashboard().then(setDashboard).catch((reason) => setError(reason.message));
  }, [ready]);

  const track = useMemo(
    () => (dashboard ? findTrackView(dashboard, params.trackId) : null),
    [dashboard, params.trackId],
  );
  const siblingTracks = useMemo(() => (dashboard ? buildTrackViews(dashboard) : []), [dashboard]);
  const trackPlan = useMemo(
    () => (dashboard ? buildTrackWeeklyPlan(dashboard, params.trackId) : []),
    [dashboard, params.trackId],
  );

  async function activateUnit(
    unitId: string,
    options?: {
      lessonId?: string;
      problemSetId?: string;
      href?: string;
      activatingKey?: string;
    },
  ) {
    const activatingKey = options?.activatingKey ?? unitId;
    setActivatingId(activatingKey);
    try {
      await api.activateContent({
        bundleId: "suneung-math-curriculum-v1",
        lessonId: options?.lessonId ?? `lesson-${unitId}`,
        problemSetId: options?.problemSetId ?? `set-${unitId}`,
      });
      router.push(options?.href ?? "/lesson");
    } finally {
      setActivatingId(null);
    }
  }

  if (!ready) {
    return <LoadingState message="불러오는 중" />;
  }

  if (error) {
    return (
      <ErrorState
        title="과목 정보를 불러오지 못했어요"
        message={error}
        action={
          <Link className="btn btn-secondary" href="/dashboard">
            대시보드로
          </Link>
        }
      />
    );
  }

  if (!dashboard || !track) {
    return <LoadingState message="불러오는 중" />;
  }

  const weakest = track.units[0];
  const hasKiller = Boolean(track.killerLessonPackId && track.killerProblemSetId);

  return (
    <div className="page">
      <nav className="row" aria-label="이동 경로" style={{ fontSize: 14 }}>
        <Link href="/dashboard" className="muted">
          대시보드
        </Link>
        <span className="muted">/</span>
        <span>{track.title}</span>
      </nav>

      <section className="card course-hero">
        <div>
          <span className="eyebrow">{track.subtitle}</span>
          <h1 style={{ marginTop: 6 }}>{track.title}</h1>
          <p className="desc">{track.description}</p>
          <div className="facts">
            <span>
              단원 <b>{track.units.length}개</b>
            </span>
            <span>
              한계돌파 <b>{track.breakthroughProblemCount}문항</b>
            </span>
            {track.killerProblemCount ? (
              <span>
                최상위 킬러 <b>{track.killerProblemCount}문항</b>
              </span>
            ) : null}
          </div>
        </div>
        <div className="course-hero-side">
          <div className="meter">
            <div className="meter-label">
              <span>평균 숙련도</span>
              <strong>{track.averageScore}점</strong>
            </div>
            <Progress value={track.averageScore} tone="auto" label="평균 숙련도" />
          </div>
          {weakest ? (
            <button
              className="btn btn-primary btn-block"
              type="button"
              disabled={activatingId === `${weakest.unitId}-core`}
              onClick={() => activateUnit(weakest.unitId, { activatingKey: `${weakest.unitId}-core` })}
            >
              {activatingId === `${weakest.unitId}-core` ? "불러오는 중..." : `${weakest.domainTitle} 강의 듣기`}
            </button>
          ) : null}
          <Link className="btn btn-secondary btn-block" href="/practice">
            문제 이어 풀기
          </Link>
        </div>
      </section>

      <nav className="tabs" aria-label="과목 선택">
        {siblingTracks.map((item) => (
          <Link
            key={item.id}
            href={`/dashboard/${item.id}`}
            className={item.id === track.id ? "active" : ""}
            aria-current={item.id === track.id ? "page" : undefined}
          >
            {item.title}
          </Link>
        ))}
      </nav>

      <div className="grid-main">
        <section className="card">
          <div className="card-header">
            <div>
              <h3>커리큘럼</h3>
              <p>숙련도가 낮은 순서</p>
            </div>
          </div>
          <div className="unit-list" style={{ marginTop: 12 }}>
            {track.units.map((unit, index) => {
              const active = dashboard.activeContent?.lessonId === `lesson-${unit.unitId}`;
              const hasBreakthrough = Boolean(unit.breakthroughLessonPackId && unit.breakthroughProblemSetId);
              return (
                <article key={unit.unitId} className={`unit-row ${active ? "is-active" : ""}`}>
                  <span className="unit-index">{index + 1}</span>
                  <div className="unit-main">
                    <h3>{unit.domainTitle}</h3>
                    <div className="sub">
                      <span>{unit.courseTitle}</span>
                      <span className={`badge ${riskBadge(unit.risk)}`}>위험도 {unit.risk}</span>
                      {active ? <span className="badge badge-primary">학습 중</span> : null}
                    </div>
                    {unit.contentElements.length ? (
                      <div className="unit-tags">
                        {unit.contentElements.slice(0, 4).map((element) => (
                          <span key={element}>{element}</span>
                        ))}
                      </div>
                    ) : null}
                  </div>
                  <div className="meter">
                    <div className="meter-label">
                      <span>{unit.masteryLabel}</span>
                      <strong>{unit.masteryScore}</strong>
                    </div>
                    <Progress value={unit.masteryScore} size="sm" tone="auto" label={`${unit.domainTitle} 숙련도`} />
                  </div>
                  <div className="unit-actions">
                    <button
                      className="btn btn-sm btn-primary"
                      type="button"
                      disabled={activatingId === `${unit.unitId}-core`}
                      onClick={() => activateUnit(unit.unitId, { activatingKey: `${unit.unitId}-core` })}
                    >
                      {activatingId === `${unit.unitId}-core` ? "전환 중..." : active ? "이어 보기" : "강의"}
                    </button>
                    {hasBreakthrough ? (
                      <button
                        className="btn btn-secondary btn-sm"
                        type="button"
                        disabled={activatingId === `${unit.unitId}-breakthrough`}
                        onClick={() =>
                          activateUnit(unit.unitId, {
                            lessonId: unit.breakthroughLessonPackId,
                            problemSetId: unit.breakthroughProblemSetId,
                            href: "/practice",
                            activatingKey: `${unit.unitId}-breakthrough`,
                          })
                        }
                        title={`한계돌파 ${unit.breakthroughProblemCount}문항`}
                      >
                        {activatingId === `${unit.unitId}-breakthrough` ? "전환 중..." : "한계돌파"}
                      </button>
                    ) : null}
                  </div>
                </article>
              );
            })}
          </div>
        </section>

        <aside className="stack">
          {hasKiller ? (
            <section className="card card-pad-sm stack-sm">
              <span className="badge badge-danger" style={{ justifySelf: "start" }}>
                최상위
              </span>
              <h3 style={{ fontSize: 16 }}>{track.killerTitle ?? `${track.title} 킬러`}</h3>
              <p className="muted" style={{ fontSize: 14 }}>
                1등급을 가르는 고난도 문제 {track.killerProblemCount}문항
              </p>
              <button
                className="btn btn-secondary btn-block"
                type="button"
                disabled={activatingId === `${track.id}-killer`}
                onClick={() =>
                  activateUnit(track.units[0]?.unitId ?? track.id, {
                    lessonId: track.killerLessonPackId,
                    problemSetId: track.killerProblemSetId,
                    href: "/practice",
                    activatingKey: `${track.id}-killer`,
                  })
                }
              >
                {activatingId === `${track.id}-killer` ? "불러오는 중..." : "킬러 문제 풀기"}
              </button>
            </section>
          ) : null}

          <section className="card card-pad-sm">
            <h3 style={{ fontSize: 15, marginBottom: 12 }}>이번 주 계획</h3>
            {trackPlan.length > 0 ? (
              <div className="week-list">
                {trackPlan.slice(0, 5).map((day) => {
                  const primaryTask = day.tasks[0] ?? null;
                  return (
                    <div key={day.date} className="week-day">
                      <span className={`date ${day.label === "오늘" ? "today" : ""}`}>{day.label}</span>
                      <div className="stack-sm" style={{ gap: 6 }}>
                        <div>
                          <strong>{primaryTask?.title ?? day.theme}</strong>
                          <span>
                            {day.tasks.length}개 학습 · {day.minutesTarget}분
                          </span>
                        </div>
                        {primaryTask ? (
                          <TaskLaunchButton
                            task={primaryTask}
                            className={`btn btn-sm ${primaryTask.status === "ready" ? "btn-soft" : "btn-ghost"}`}
                          />
                        ) : null}
                      </div>
                    </div>
                  );
                })}
              </div>
            ) : (
              <p className="muted" style={{ fontSize: 14 }}>
                이번 주에는 이 과목 일정이 없어요.
              </p>
            )}
          </section>
        </aside>
      </div>
    </div>
  );
}
