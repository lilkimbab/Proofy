"use client";

import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";

import { OnboardingHeader } from "@/components/onboarding-header";
import { MathText, Progress } from "@/components/ui";
import { useAuthGuard } from "@/components/use-auth-guard";
import { api } from "@/lib/api";

const OPTION_KEYS = ["①", "②", "③", "④", "⑤"];

export default function DiagnosticPage() {
  const router = useRouter();
  const { ready, bootstrap } = useAuthGuard({
    requireDiagnostic: false,
    redirectIfDiagnosticDone: true,
  });
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [timeLeft, setTimeLeft] = useState(600);
  const [answers, setAnswers] = useState<Record<string, number>>({});
  const formRef = useRef<HTMLFormElement | null>(null);

  const questions = useMemo(() => bootstrap?.diagnosticQuestions ?? [], [bootstrap]);
  const answeredCount = questions.filter((question) => answers[question.id] !== undefined).length;
  const missingNumbers = questions
    .map((question, index) => (answers[question.id] === undefined ? index + 1 : null))
    .filter((value): value is number => value !== null);

  useEffect(() => {
    setTimeLeft(600);
  }, [questions]);

  useEffect(() => {
    setAnswers(bootstrap?.onboarding?.diagnosticAnswers ?? {});
  }, [bootstrap?.onboarding?.diagnosticAnswers]);

  useEffect(() => {
    if (!ready || !bootstrap || submitting || timeLeft <= 0) {
      return;
    }
    const timer = window.setTimeout(() => {
      setTimeLeft((current) => Math.max(current - 1, 0));
    }, 1000);
    return () => window.clearTimeout(timer);
  }, [bootstrap, ready, submitting, timeLeft]);

  useEffect(() => {
    if (!ready || !bootstrap || submitting || timeLeft !== 0) {
      return;
    }
    if (missingNumbers.length > 0) {
      const preview = missingNumbers.slice(0, 4).join(", ");
      setError(`아직 ${missingNumbers.length}문항이 남아 있어요. ${preview}번부터 확인해 주세요.`);
      return;
    }
    formRef.current?.requestSubmit();
  }, [bootstrap, missingNumbers, ready, submitting, timeLeft]);

  useEffect(() => {
    if (!ready || !bootstrap) {
      return;
    }
    const timer = window.setTimeout(() => {
      api.saveDiagnosticProgress(answers).catch(() => null);
    }, 250);
    return () => window.clearTimeout(timer);
  }, [answers, bootstrap, ready]);

  useEffect(() => {
    if (!error) {
      return;
    }
    if (missingNumbers.length === 0) {
      setError(null);
    }
  }, [error, missingNumbers.length]);

  function timeLabel(totalSeconds: number) {
    const minutes = Math.floor(totalSeconds / 60);
    const seconds = totalSeconds % 60;
    return `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
  }

  function scrollToQuestion(questionId: string) {
    document.getElementById(`q-${questionId}`)?.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  async function submitDiagnostic(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (missingNumbers.length > 0) {
      const preview = missingNumbers.slice(0, 4).join(", ");
      setError(`아직 ${missingNumbers.length}문항이 남아 있어요. ${preview}번부터 확인해 주세요.`);
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      await api.submitDiagnostic(answers);
      router.replace("/dashboard");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "진단 제출에 실패했습니다.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="onboarding">
      <OnboardingHeader current={1} />
      {!ready || !bootstrap ? (
        <div className="state" role="status">
          <div className="spinner" />
          <p>불러오는 중</p>
        </div>
      ) : (
        <main className="exam-wrap">
          <div className="exam-intro">
            <div>
              <span className="eyebrow">{questions.length}문항 · 제한 시간 10분</span>
              <h1 style={{ marginTop: 6 }}>진단 평가</h1>
              <p>모르는 문제는 가장 가깝다고 생각하는 답을 고르세요. 답은 자동으로 저장돼요.</p>
            </div>
          </div>

          <form id="diagnostic-form" ref={formRef} className="question-list" onSubmit={submitDiagnostic}>
            {questions.map((question, index) => (
              <fieldset key={question.id} id={`q-${question.id}`} className="card question" style={{ margin: 0 }}>
                <legend className="sr-only">{index + 1}번 문항</legend>
                <div className="question-meta">
                  <span className="question-no">{index + 1}</span>
                  {question.unitTitle ? <span className="badge">{question.unitTitle}</span> : null}
                </div>
                <p className="question-prompt">
                  <MathText text={question.prompt} />
                </p>
                <div className="options">
                  {question.options.map((option, optionIndex) => (
                    <label key={option} className="option">
                      <input
                        type="radio"
                        name={question.id}
                        value={optionIndex}
                        checked={answers[question.id] === optionIndex}
                        onChange={() => setAnswers((current) => ({ ...current, [question.id]: optionIndex }))}
                      />
                      <span className="option-key" aria-hidden="true">
                        {OPTION_KEYS[optionIndex] ?? optionIndex + 1}
                      </span>
                      <span>
                        <MathText text={option} />
                      </span>
                    </label>
                  ))}
                </div>
              </fieldset>
            ))}
          </form>

          <aside className="card exam-aside" aria-label="진단 진행 상황">
            <div className={`exam-timer ${timeLeft <= 60 ? "is-urgent" : ""}`}>
              <span className="muted">남은 시간</span>
              <strong aria-live="off">{timeLabel(timeLeft)}</strong>
            </div>
            <div className="meter">
              <div className="meter-label">
                <span>답한 문항</span>
                <strong>
                  {answeredCount} / {questions.length}
                </strong>
              </div>
              <Progress value={questions.length ? (answeredCount / questions.length) * 100 : 0} />
            </div>
            <div className="qnav" role="list" aria-label="문항 이동">
              {questions.map((question, index) => {
                const answered = answers[question.id] !== undefined;
                return (
                  <button
                    key={question.id}
                    type="button"
                    role="listitem"
                    className={answered ? "answered" : error ? "missing" : ""}
                    onClick={() => scrollToQuestion(question.id)}
                    aria-label={`${index + 1}번 ${answered ? "답함" : "안 답함"}`}
                  >
                    {index + 1}
                  </button>
                );
              })}
            </div>
            {error ? (
              <p className="alert alert-error" role="alert">
                {error}
              </p>
            ) : null}
            <button className="btn btn-primary btn-lg btn-block" type="submit" form="diagnostic-form" disabled={submitting}>
              {submitting ? "제출 중..." : "제출하기"}
            </button>
          </aside>
        </main>
      )}
    </div>
  );
}
