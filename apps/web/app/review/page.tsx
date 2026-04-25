"use client";

import { useEffect, useState } from "react";
import Link from "next/link";

import { useAuthGuard } from "@/components/use-auth-guard";
import { api } from "@/lib/api";
import type { ReviewResponse } from "@/lib/types";

export default function ReviewPage() {
  const { ready } = useAuthGuard();
  const [review, setReview] = useState<ReviewResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!ready) return;
    api.reviewLatest().then(setReview).catch((reason) => setError(reason.message));
  }, [ready]);

  if (!ready) {
    return (
      <section className="loading-state">
        <div className="spinner" />
        <p>복습 화면 권한을 확인하는 중입니다.</p>
      </section>
    );
  }

  if (error) {
    return (
      <section className="empty-card">
        <h2>복습 데이터를 불러오지 못했습니다.</h2>
        <p className="muted">{error}</p>
      </section>
    );
  }

  if (!review) {
    return (
      <section className="loading-state">
        <div className="spinner" />
        <p>복습 데이터를 가져오는 중입니다.</p>
      </section>
    );
  }

  if (review.empty) {
    return (
      <section className="empty-card">
        <h2>{review.headline}</h2>
        <p className="muted">{review.message}</p>
        <div className="button-row" style={{ justifyContent: "center", marginTop: 12 }}>
          <Link className="button primary" href="/practice">
            문제 풀러 가기
          </Link>
        </div>
      </section>
    );
  }

  const answerOnlyReview =
    (review.goodSteps?.length ?? 0) + (review.wrongSteps?.length ?? 0) <= 1;

  return (
    <section className="page review-layout">
      <article className="panel">
        <h2 className="review-title">{review.headline}</h2>
        <div className={`result-banner ${review.solved ? "success" : "retry"}`}>
          {review.solved
            ? "좋아요. 풀이 흐름이 거의 완성됐어요."
            : "괜찮아요. 여기서부터 다시 잡아가면 됩니다."}
        </div>
        <div className="review-list">
          {answerOnlyReview ? (
            <article className={`feedback-card ${review.solved ? "good" : "bad"}`}>
              <h4>최종 답 판정</h4>
              <p>{review.solved ? "최종 답이 맞았어요. 같은 문제 묶음에서 더 어려운 문제로 이어가면 됩니다." : "최종 답이 아직 맞지 않아요. 해당 유형 장면을 다시 보고 한 번 더 도전해봐요."}</p>
            </article>
          ) : null}
          {!answerOnlyReview && review.goodSteps?.map((step) => (
            <article key={step.id} className="feedback-card good">
              <h4>{step.label}</h4>
              <p>{step.reason}</p>
              <span className="review-tag">기준 답: {step.expected}</span>
            </article>
          ))}
          {!answerOnlyReview && review.wrongSteps?.map((step) => (
            <article key={step.id} className="feedback-card bad">
              <h4>{step.label}</h4>
              <p>{step.reason}</p>
              <span className="review-tag">기준 답: {step.expected}</span>
            </article>
          ))}
        </div>
      </article>

      <article className="panel">
        <h2 className="review-title">다음 학습</h2>
        {review.tomorrowPlan ? (
          <article className="review-card">
            <header>
              <div>
                <h4>
                  {review.tomorrowPlan.label} · {review.tomorrowPlan.theme}
                </h4>
                <p className="muted">{review.tomorrowPlan.focus}</p>
              </div>
              <span className="chip">
                {review.tomorrowPlan.minutesTarget ?? review.tomorrowPlan.minutes_target}분
              </span>
            </header>
          </article>
        ) : null}
        {review.nextProblem ? (
          <article className="review-card" style={{ marginTop: 12 }}>
            <h4>다음 문제</h4>
            <p>{review.nextProblem.nextProblemTitle}</p>
          </article>
        ) : null}
        <article className="review-card" style={{ marginTop: 12 }}>
          <h4>추천 복습 문제 묶음</h4>
          {review.retrySet?.map((item) => <p key={item}>{item}</p>)}
        </article>
        {review.mistakeNotes?.length ? (
          <article className="review-card" style={{ marginTop: 12 }}>
            <h4>자동 오답노트</h4>
            {review.mistakeNotes.map((note) => (
              <div key={note.id} style={{ marginTop: 10 }}>
                <strong>{note.problemTitle}</strong>
                <p>{note.summary}</p>
                <p className="muted">{note.correction}</p>
              </div>
            ))}
          </article>
        ) : null}
        <div className="button-row">
          <Link className="button primary" href="/dashboard">
            대시보드로
          </Link>
          <Link className="button secondary" href="/practice">
            다시 풀기
          </Link>
          <Link className="button ghost" href="/lesson">
            강의 보기
          </Link>
        </div>
      </article>
    </section>
  );
}
