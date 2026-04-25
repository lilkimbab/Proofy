"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";

import { api } from "@/lib/api";
import { useAuthGuard } from "@/components/use-auth-guard";
import { TaskLaunchButton } from "@/components/task-launch-button";
import { buildTrackViews } from "@/lib/curriculum";
import type { DashboardResponse } from "@/lib/types";

export default function DashboardPage() {
  const { ready } = useAuthGuard();
  const [dashboard, setDashboard] = useState<DashboardResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!ready) return;
    api.dashboard().then(setDashboard).catch((reason) => setError(reason.message));
  }, [ready]);

  const tracks = useMemo(() => (dashboard ? buildTrackViews(dashboard) : []), [dashboard]);

  if (!ready) {
    return (
      <section className="loading-state">
        <div className="spinner" />
        <p>계정 상태를 확인하는 중입니다.</p>
      </section>
    );
  }

  if (error) {
    return (
      <section className="empty-card">
        <h2>대시보드를 불러오지 못했습니다.</h2>
        <p className="muted">{error}</p>
      </section>
    );
  }

  if (!dashboard) {
    return (
      <section className="loading-state">
        <div className="spinner" />
        <p>수학 영역을 정리하는 중입니다.</p>
      </section>
    );
  }

  return (
    <section className="page dashboard-root">
      <article className="panel hero-banner hero-banner-clean dashboard-hero dashboard-hero-slim">
        <div>
          <h2 className="section-title">{dashboard.todayMission.recommendedUnit}</h2>
          <div className="inline-stat-list">
            <span>D-{dashboard.stats.daysLeft}</span>
            <span>수학 목표 {dashboard.stats.targetScore}</span>
            <span>오늘 {dashboard.stats.todayMinutes}분</span>
          </div>
        </div>
        <div className="dashboard-action-stack">
          <div className="focus-card">
            <strong>{dashboard.activeContent?.lessonTitle ?? "추천 강의 준비 중"}</strong>
            {dashboard.activeContent ? (
              <span className="muted">
                {dashboard.activeContent.problemSetTitle} · {dashboard.activeContent.problemCount}문항
              </span>
            ) : null}
          </div>
          <div className="button-row">
            {dashboard.todayMission.currentTask ? (
              <TaskLaunchButton task={dashboard.todayMission.currentTask} className="button primary" />
            ) : (
              <Link className="button primary" href="/lesson">
                오늘 학습 시작
              </Link>
            )}
            <Link className="button ghost" href="/review">
              오답 복습
            </Link>
          </div>
        </div>
      </article>

      <article className="panel glass-panel">
        <h3 className="section-title">과목 선택</h3>
        <section className="track-grid" style={{ marginTop: 16 }}>
        {tracks.map((track) => (
          <Link key={track.id} href={`/dashboard/${track.id}`} className="track-card track-card-clean">
            <div className="track-card-top">
              <div>
                <p className="eyebrow">{track.subtitle}</p>
                <h3>{track.title}</h3>
              </div>
              <span className="track-score">{track.averageScore}</span>
            </div>
            <div className="inline-stat-list">
              <span>{track.weakUnitTitle}</span>
              <span>{track.units.length}개 단원</span>
              <span>한계돌파 {track.breakthroughProblemCount}문항</span>
            </div>
          </Link>
        ))}
        </section>
      </article>
    </section>
  );
}
