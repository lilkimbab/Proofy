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
          메인 화면과 실시간으로 연결돼 있어요. 여기서 입력한 답은 메인 화면에도 바로 보여요.
        </span>
      </p>
      <PracticeForm session={session} participant="companion" />
    </div>
  );
}
