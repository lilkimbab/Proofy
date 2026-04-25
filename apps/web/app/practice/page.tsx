"use client";

import { useEffect, useState } from "react";

import { PracticeForm } from "@/components/practice-form";
import { useAuthGuard } from "@/components/use-auth-guard";
import { api } from "@/lib/api";
import type { LessonSessionResponse } from "@/lib/types";

export default function PracticePage() {
  const { ready } = useAuthGuard();
  const [session, setSession] = useState<LessonSessionResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!ready) return;
    api.lessonSession().then(setSession).catch((reason) => setError(reason.message));
  }, [ready]);

  if (!ready) {
    return (
      <section className="loading-state">
        <div className="spinner" />
        <p>계정을 확인하는 중입니다.</p>
      </section>
    );
  }

  if (error) {
    return (
      <section className="empty-card">
        <h2>문제 묶음을 불러오지 못했습니다.</h2>
        <p className="muted">{error}</p>
      </section>
    );
  }

  if (!session) {
    return (
      <section className="loading-state">
        <div className="spinner" />
        <p>문제 묶음을 준비하는 중입니다.</p>
      </section>
    );
  }

  return (
    <PracticeForm
      session={session}
      participant="main"
      onSessionChange={setSession}
    />
  );
}
