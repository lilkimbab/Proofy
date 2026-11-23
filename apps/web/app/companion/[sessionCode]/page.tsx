"use client";

import { useEffect, useState } from "react";

import { PracticeForm } from "@/components/practice-form";
import { LoadingState } from "@/components/ui";
import { api } from "@/lib/api";
import type { LessonSessionResponse } from "@/lib/types";

export default function CompanionPage() {
  const [session, setSession] = useState<LessonSessionResponse | null>(null);

  useEffect(() => {
    api.lessonSession().then(setSession);
  }, []);

  if (!session) {
    return <LoadingState message="메인 화면과 연결하는 중" />;
  }

  return (
    <div className="stack-lg">
      <p className="alert alert-info">
        <span>
          <strong>보조 화면</strong>
          여기서 쓴 답이 메인 화면에도 바로 떠요.
        </span>
      </p>
      <PracticeForm session={session} participant="companion" />
    </div>
  );
}
