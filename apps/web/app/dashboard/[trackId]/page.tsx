"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";

import { api } from "@/lib/api";
import { TaskLaunchButton } from "@/components/task-launch-button";
import { useAuthGuard } from "@/components/use-auth-guard";
import { buildTrackViews, buildTrackWeeklyPlan, findTrackView } from "@/lib/curriculum";
import type { DashboardResponse } from "@/lib/types";

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
    return (
      <section className="loading-state">
        <div className="spinner" />
        <p>영역 정보를 준비하는 중입니다.</p>
      </section>
    );
  }

  if (error) {
    return (
      <section className="empty-card">
        <h2>영역 정보를 불러오지 못했습니다.</h2>
        <p className="muted">{error}</p>
      </section>
    );
  }

  if (!dashboard || !track) {
    return (
      <section className="loading-state">
        <div className="spinner" />
        <p>영역 정보를 정리하는 중입니다.</p>
      </section>
    );
  }

  return (
    <section className="page track-detail-page">
      <article className="panel hero-banner hero-banner-clean">
        <div>
          <h2 className="section-title">{track.title}</h2>
          <div className="inline-stat-list">
            <span>평균 숙련도 {track.averageScore}</span>
            <span>약한 단원 {track.weakUnitTitle}</span>
            <span>{track.units.length}개 단원</span>
            {track.killerProblemCount ? <span>최상위 킬러 {track.killerProblemCount}문항</span> : null}
          </div>
        </div>
        <div className="button-row">
          <Link className="button ghost" href="/dashboard">
            영역 목록으로
          </Link>
          <Link className="button secondary" href="/practice">
            현재 문제 풀기
          </Link>
          {track.killerLessonPackId && track.killerProblemSetId ? (
            <button
              className="button primary"
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
              {activatingId === `${track.id}-killer` ? "불러오는 중..." : "최상위 킬러 시작"}
            </button>
          ) : null}
        </div>
      </article>

      <section className="track-switcher">
        {siblingTracks.map((item) => (
          <Link
            key={item.id}
            href={`/dashboard/${item.id}`}
            className={`track-switch-pill ${item.id === track.id ? "active" : ""}`}
          >
            {item.title}
          </Link>
        ))}
      </section>

      <section className="mission-grid">
        <article className="panel mission-side-panel">
          <h3 className="section-title">추천 시작</h3>
          <strong className="track-focus-title">{track.weakUnitTitle}</strong>
          <div className="button-row" style={{ marginTop: 16 }}>
            <button
              className="button primary"
              type="button"
              disabled={activatingId === `${track.units[0]?.unitId}-core`}
              onClick={() =>
                track.units[0] &&
                activateUnit(track.units[0].unitId, {
                  activatingKey: `${track.units[0].unitId}-core`,
                })
              }
            >
                  {activatingId === `${track.units[0]?.unitId}-core` ? "불러오는 중..." : "가장 약한 단원 강의 시작"}
            </button>
            {track.killerLessonPackId && track.killerProblemSetId ? (
              <button
                className="button ghost"
                type="button"
                disabled={activatingId === `${track.id}-killer-side`}
                onClick={() =>
                  activateUnit(track.units[0]?.unitId ?? track.id, {
                    lessonId: track.killerLessonPackId,
                    problemSetId: track.killerProblemSetId,
                    href: "/practice",
                    activatingKey: `${track.id}-killer-side`,
                  })
                }
              >
                {activatingId === `${track.id}-killer-side`
                  ? "불러오는 중..."
                  : `${track.killerTitle ?? "최상위 킬러"} ${track.killerProblemCount}문항`}
              </button>
            ) : null}
            {track.units[0]?.breakthroughLessonPackId && track.units[0]?.breakthroughProblemSetId ? (
              <button
                className="button secondary"
                type="button"
                disabled={activatingId === `${track.units[0]?.unitId}-breakthrough`}
                onClick={() =>
                  track.units[0] &&
                  activateUnit(track.units[0].unitId, {
                    lessonId: track.units[0].breakthroughLessonPackId,
                    problemSetId: track.units[0].breakthroughProblemSetId,
                    href: "/practice",
                    activatingKey: `${track.units[0].unitId}-breakthrough`,
                  })
                }
              >
                {activatingId === `${track.units[0]?.unitId}-breakthrough`
                  ? "불러오는 중..."
                  : `한계돌파 ${track.units[0]?.breakthroughProblemCount ?? 0}문항`}
              </button>
            ) : null}
          </div>
        </article>

        <article className="panel glass-panel plan-strip-panel">
          <h3 className="section-title">이번 주 계획</h3>
          {trackPlan.length > 0 ? (
            <div className="track-week-list">
              {trackPlan.slice(0, 4).map((day) => {
                const primaryTask = day.tasks[0] ?? null;
                return (
                  <article key={day.date} className="track-week-row">
                    <div className="track-week-meta">
                      <span>{day.label}</span>
                      <span>{day.minutesTarget}분</span>
                    </div>
                    <div className="track-week-main">
                      <strong>{primaryTask?.title ?? day.theme}</strong>
                      {day.tasks.length > 1 ? <span>{day.tasks.length}개 학습</span> : null}
                    </div>
                    <div className="track-week-action">
                      {primaryTask ? <TaskLaunchButton task={primaryTask} className="button ghost" /> : null}
                    </div>
                  </article>
                );
              })}
            </div>
          ) : (
            <p className="muted">아직 잡힌 계획이 없어요.</p>
          )}
        </article>
      </section>

      <section className="unit-grid">
        {track.units.map((unit) => {
          const active = dashboard.activeContent?.lessonId === `lesson-${unit.unitId}`;
          return (
            <article key={unit.unitId} className="unit-card">
              <div className="unit-card-head">
                <div>
                  <p className="eyebrow">{unit.courseTitle}</p>
                  <h3>{unit.domainTitle}</h3>
                </div>
                <span className="track-score small">{unit.masteryScore}</span>
              </div>
              <div className="inline-stat-list">
                <span>{unit.masteryLabel}</span>
                <span>위험도 {unit.risk}</span>
                {unit.breakthroughProblemCount ? <span>한계돌파 {unit.breakthroughProblemCount}문항</span> : null}
              </div>
              <div className="unit-tag-list">
                {unit.contentElements.slice(0, 3).map((element) => (
                  <span key={element} className="unit-tag">
                    {element}
                  </span>
                ))}
              </div>
              <div className="button-row" style={{ marginTop: 14 }}>
                <button
                  className={`button ${active ? "secondary" : "primary"}`}
                  type="button"
                  disabled={active || activatingId === `${unit.unitId}-core`}
                  onClick={() =>
                    activateUnit(unit.unitId, {
                      activatingKey: `${unit.unitId}-core`,
                    })
                  }
                >
                  {active ? "현재 학습 중" : activatingId === `${unit.unitId}-core` ? "전환 중..." : "개념 강의 시작"}
                </button>
                {unit.breakthroughLessonPackId && unit.breakthroughProblemSetId ? (
                  <button
                    className="button ghost"
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
                  >
                    {activatingId === `${unit.unitId}-breakthrough` ? "전환 중..." : "한계돌파 시작"}
                  </button>
                ) : null}
              </div>
            </article>
          );
        })}
      </section>
    </section>
  );
}
