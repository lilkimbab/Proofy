"use client";

import { useEffect, useState } from "react";

import { PracticeForm } from "@/components/practice-form";
import { api } from "@/lib/api";
import type { LessonSessionResponse } from "@/lib/types";

export default function CompanionPage() {
  const [session, setSession] = useState<LessonSessionResponse | null>(null);

  useEffect(() => {
    api.lessonSession().then(setSession);
  }, []);

  if (!session) {
    return (
      <section className="loading-state">
        <div className="spinner" />
        <p>보조 화면을 연결하는 중입니다.</p>
      </section>
    );
  }

  return (
    <section className="page">
      <article className="panel">
        <p className="eyebrow">보조 화면</p>
        <h2 className="section-title">메인 화면과 같이 움직이는 입력 화면</h2>
        <p className="muted">
          메인 화면과 보조 화면은 같은 웹소켓을 구독하며, 입력한 내용이 실시간으로 함께 반영됩니다.
        </p>
      </article>
      <PracticeForm session={session} participant="companion" />
    </section>
  );
}
