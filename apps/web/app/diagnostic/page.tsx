"use client";

import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";

import { useAuthGuard } from "@/components/use-auth-guard";
import { api } from "@/lib/api";

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

  if (!ready || !bootstrap) {
    return (
      <section className="loading-state onboarding-screen">
        <div className="spinner" />
        <p>불러오는 중</p>
      </section>
    );
  }

  return (
    <section className="onboarding-screen">
      <div className="landing-backdrop" aria-hidden="true">
        <div className="landing-ring landing-ring-one" />
        <div className="landing-ring landing-ring-two" />
      </div>

      <article className="assessment-shell">
        <header className="assessment-header">
          <div>
            <p className="eyebrow">진단 평가</p>
            <h1>실력의 시작점을 잡아볼게요</h1>
          </div>
          <div className="assessment-timer">{timeLabel(timeLeft)}</div>
        </header>

        <article className="assessment-card">
          <form ref={formRef} className="question-list" onSubmit={submitDiagnostic}>
            {questions.map((question, index) => (
              <article key={question.id} className="question-card question-card-clean question-card-large">
                <div className="inline-stat-list" style={{ marginBottom: 10 }}>
                  <span>{index + 1}번</span>
                  {question.unitTitle ? <span>{question.unitTitle}</span> : null}
                </div>
                <h4>{question.prompt}</h4>
                <div className="option-list">
                  {question.options.map((option, optionIndex) => (
                    <label key={option} className="option">
                      <input
                        type="radio"
                        name={question.id}
                        value={optionIndex}
                        checked={answers[question.id] === optionIndex}
                        onChange={() =>
                          setAnswers((current) => ({ ...current, [question.id]: optionIndex }))
                        }
                      />
                      <span>{option}</span>
                    </label>
                  ))}
                </div>
              </article>
            ))}
            {error ? <p className="inline-error">{error}</p> : null}
            <div className="survey-footer">
              <div className="inline-stat-list" style={{ marginBottom: 12 }}>
                <span>{answeredCount}/{questions.length}</span>
              </div>
              <div className="button-row">
                <button className="button primary" type="submit" disabled={submitting}>
                  {submitting ? "제출 중..." : "진단 제출"}
                </button>
              </div>
            </div>
          </form>
        </article>
      </article>
    </section>
  );
}
