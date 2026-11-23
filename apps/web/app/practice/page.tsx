"use client";

import { useEffect, useState } from "react";
import Link from "next/link";

import { PracticeForm } from "@/components/practice-form";
import { ErrorState, LoadingState } from "@/components/ui";
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
    return <LoadingState message="불러오는 중" />;
  }

  if (error) {
    return (
      <ErrorState
        title="문제를 불러오지 못했어요"
        message={error}
        action={
          <Link className="btn btn-secondary" href="/dashboard">
            대시보드로
          </Link>
        }
      />
    );
  }

  if (!session) {
    return <LoadingState message="문제를 불러오는 중" />;
  }

  return <PracticeForm session={session} participant="main" onSessionChange={setSession} />;
}
