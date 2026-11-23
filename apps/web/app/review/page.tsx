"use client";

import { useEffect, useState } from "react";
import Link from "next/link";

import { ErrorState, LoadingState, MathText } from "@/components/ui";
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
    return <LoadingState message="불러오는 중" />;
  }

  if (error) {
    return (
      <ErrorState
        title="채점 결과를 불러오지 못했어요"
        message={error}
        action={
          <Link className="btn btn-secondary" href="/dashboard">
            대시보드로
          </Link>
        }
      />
    );
  }

  if (!review) {
    return <LoadingState message="채점 결과를 불러오는 중" />;
  }

  if (review.empty) {
    return (
      <ErrorState
        title={review.headline || "아직 채점한 문제가 없어요"}
        message={review.message ?? "문제를 풀면 여기에 쌓여요."}
        action={
          <Link className="btn btn-primary" href="/practice">
            문제 풀러 가기
          </Link>
        }
      />
    );
  }

  const answerOnlyReview = (review.goodSteps?.length ?? 0) + (review.wrongSteps?.length ?? 0) <= 1;
  const tomorrow = review.tomorrowPlan;

  return (
    <div className="page">
      <header className="page-header">
        <div>
          <h1>채점 결과</h1>
          {review.headline ? <p>{review.headline}</p> : null}
        </div>
        <div className="row">
          <Link className="btn btn-secondary" href="/lesson">
            강의 다시 보기
          </Link>
          <Link className="btn btn-primary" href="/practice">
            {review.solved ? "다음 문제 풀기" : "다시 풀기"}
          </Link>
        </div>
      </header>

      <div className="grid-main">
        <div className="stack">
          <section className={`card result-hero ${review.solved ? "success" : "retry"}`}>
            <span className="result-icon" aria-hidden="true">
              {review.solved ? "✓" : "!"}
            </span>
            <div>
              <h2 style={{ fontSize: 20 }}>{review.solved ? "정답이에요" : "아쉽게 틀렸어요"}</h2>
              <p>
                {review.summary ??
                  (review.solved
                    ? "다음 문제로 가요."
                    : "어디서 틀렸는지 보고 한 번 더.")}
              </p>
            </div>
          </section>

          <section className="card">
            <div className="card-header">
              <div>
                <h3>풀이 단계별 피드백</h3>
              </div>
            </div>
            <div className="card-body stack-sm" style={{ gap: 10 }}>
              {answerOnlyReview ? (
                <article className={`feedback ${review.solved ? "good" : "bad"}`}>
                  <h4>
                    <span className={`badge ${review.solved ? "badge-success" : "badge-danger"}`}>
                      {review.solved ? "맞음" : "틀림"}
                    </span>
                    최종 답
                  </h4>
                  <p>
                    {review.solved
                      ? "맞았어요."
                      : "답이 달라요. 강의에서 이 부분만 다시 보고 오기."}
                  </p>
                </article>
              ) : null}
              {!answerOnlyReview &&
                review.wrongSteps?.map((step) => (
                  <article key={step.id} className="feedback bad">
                    <h4>
                      <span className="badge badge-danger">틀림</span>
                      {step.label}
                    </h4>
                    <p>{step.reason}</p>
                    <span className="expected">
                      기준 답 <b><MathText text={String(step.expected)} /></b>
                    </span>
                  </article>
                ))}
              {!answerOnlyReview &&
                review.goodSteps?.map((step) => (
                  <article key={step.id} className="feedback good">
                    <h4>
                      <span className="badge badge-success">맞음</span>
                      {step.label}
                    </h4>
                    <p>{step.reason}</p>
                    <span className="expected">
                      기준 답 <b><MathText text={String(step.expected)} /></b>
                    </span>
                  </article>
                ))}
            </div>
          </section>

          {review.mistakeNotes?.length ? (
            <section className="card">
              <div className="card-header">
                <div>
                  <h3>오답노트</h3>
                </div>
                <span className="badge">{review.mistakeNotes.length}개</span>
              </div>
              <div className="card-body">
                {review.mistakeNotes.map((note) => (
                  <div key={note.id} className="note">
                    <strong>{note.problemTitle}</strong>
                    <p>
                      <MathText text={note.summary} />
                    </p>
                    {note.correction ? (
                      <p className="fix">
                        고칠 점 · <MathText text={note.correction} />
                      </p>
                    ) : null}
                  </div>
                ))}
              </div>
            </section>
          ) : null}
        </div>

        <aside className="stack">
          {tomorrow ? (
            <section className="card card-pad-sm stack-sm">
              <div className="row-between">
                <span className="eyebrow">{tomorrow.label} 계획</span>
                <span className="badge">{tomorrow.minutesTarget ?? tomorrow.minutes_target}분</span>
              </div>
              <h3 style={{ fontSize: 16 }}>{tomorrow.theme}</h3>
              <p className="muted" style={{ fontSize: 14 }}>
                {tomorrow.focus}
              </p>
            </section>
          ) : null}

          {review.nextProblem ? (
            <section className="card card-pad-sm stack-sm">
              <span className="eyebrow">다음 문제</span>
              <strong>{review.nextProblem.nextProblemTitle}</strong>
              <Link className="btn btn-soft btn-sm" href="/practice" style={{ justifySelf: "start" }}>
                풀러 가기
              </Link>
            </section>
          ) : null}

          {review.retrySet?.length ? (
            <section className="card card-pad-sm">
              <h3 style={{ fontSize: 15, marginBottom: 12 }}>추천 복습</h3>
              <ul className="list-plain">
                {review.retrySet.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            </section>
          ) : null}

          <Link className="btn btn-ghost" href="/dashboard">
            대시보드로 돌아가기
          </Link>
        </aside>
      </div>
    </div>
  );
}
