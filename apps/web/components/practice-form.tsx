"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";

import { MathText, difficultyLabel } from "@/components/ui";
import { api, wsUrl } from "@/lib/api";
import type { LessonSessionResponse } from "@/lib/types";

type PracticeFormProps = {
  session: LessonSessionResponse;
  participant: "main" | "companion";
  onSessionChange?: (session: LessonSessionResponse) => void;
};

export function PracticeForm({ session, participant, onSessionChange }: PracticeFormProps) {
  const router = useRouter();
  const [finalAnswer, setFinalAnswer] = useState("");
  const [scratchNote, setScratchNote] = useState("");
  const [connectionState, setConnectionState] = useState<"connecting" | "live" | "offline">("connecting");
  const [submitting, setSubmitting] = useState(false);
  const [movingNext, setMovingNext] = useState(false);
  const [submitSummary, setSubmitSummary] = useState<string | null>(null);
  const [solved, setSolved] = useState<boolean | null>(null);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const socketRef = useRef<WebSocket | null>(null);

  const selectedProblem = session.practiceProblem;
  const problems = session.problemSet?.problems ?? [];

  const selectedIndex = useMemo(
    () => problems.findIndex((problem) => problem.id === selectedProblem.id),
    [problems, selectedProblem.id],
  );

  useEffect(() => {
    setFinalAnswer("");
    setScratchNote("");
    setSubmitSummary(null);
    setSolved(null);
    setSubmitError(null);
  }, [selectedProblem.id]);

  useEffect(() => {
    const socket = new WebSocket(wsUrl(session.realtime.wsPath, participant));
    socketRef.current = socket;
    socket.onopen = () => setConnectionState("live");
    socket.onerror = () => setConnectionState("offline");
    socket.onclose = () => setConnectionState("offline");
    return () => socket.close();
  }, [participant, session.realtime.wsPath]);

  function emit(type: string, payload: Record<string, unknown>) {
    if (socketRef.current?.readyState === WebSocket.OPEN) {
      socketRef.current.send(JSON.stringify({ type, payload }));
    }
  }

  async function submit() {
    if (!finalAnswer.trim()) return;
    setSubmitting(true);
    setSubmitError(null);
    try {
      const response = await api.submitPractice({
        finalAnswer,
        scratchNote,
      });
      emit(response.syncEvent.type as string, response.syncEvent);
      onSessionChange?.(response.lessonSession);
      const attempt = response.attempt as { summary?: string; solved?: boolean } | undefined;
      setSolved(typeof attempt?.solved === "boolean" ? attempt.solved : null);
      setSubmitSummary(
        attempt?.summary ??
          (attempt?.solved ? "정답이에요. 다음 문제로 넘어가세요." : "아쉽지만 틀렸어요. 다시 풀어 보거나 채점 결과를 확인하세요."),
      );
    } catch (reason) {
      setSubmitError(reason instanceof Error ? reason.message : "제출하지 못했어요. 다시 시도해 주세요.");
    } finally {
      setSubmitting(false);
    }
  }

  async function moveNext() {
    setMovingNext(true);
    try {
      const response = await api.nextPractice();
      emit(response.syncEvent.type as string, response.syncEvent);
      onSessionChange?.(response.lessonSession);
      if (response.moved) {
        setSubmitSummary(null);
        setSolved(null);
      }
    } finally {
      setMovingNext(false);
    }
  }

  const hasNextProblem = selectedIndex >= 0 && selectedIndex + 1 < problems.length;
  const total = problems.length || 1;
  const position = selectedIndex >= 0 ? selectedIndex + 1 : 1;

  return (
    <div className="page">
      <header className="page-header">
        <div>
          <span className="eyebrow">{session.unitTitle}</span>
          <h1 style={{ marginTop: 4 }}>{session.problemSet?.title ?? "문제 풀기"}</h1>
        </div>
        <span className="connection" title="보조 화면과 실시간으로 연결돼요">
          <span
            className={`dot ${connectionState === "live" ? "dot-success" : connectionState === "connecting" ? "dot-warning" : "dot-danger"}`}
            aria-hidden="true"
          />
          {connectionState === "live" ? "실시간 연결됨" : connectionState === "connecting" ? "연결 중" : "연결 끊김"}
        </span>
      </header>

      {problems.length > 1 ? (
        <nav className="problem-nav" aria-label={`전체 ${total}문항 중 ${position}번`}>
          {problems.map((problem, index) => (
            <span
              key={problem.id}
              className={index === selectedIndex ? "current" : index < selectedIndex ? "done" : ""}
              title={problem.title}
            >
              {index + 1}
            </span>
          ))}
        </nav>
      ) : null}

      <div className="grid-main">
        <article className="card problem-card">
          <div className="head">
            <span className="badge">
              {position} / {total}
            </span>
            <span className="badge badge-outline">{selectedProblem.problemType ?? "대표 유형"}</span>
            <span className="badge badge-outline">난이도 {difficultyLabel(selectedProblem.difficulty)}</span>
            {selectedProblem.isKiller ? <span className="badge badge-danger">킬러</span> : null}
          </div>
          <h2>{selectedProblem.title}</h2>
          <div className="problem-statement">
            <MathText text={selectedProblem.statement} />
          </div>

          {selectedProblem.isKiller ? (
            <p className="alert alert-warning" style={{ marginTop: 18 }}>
              조건을 어떻게 해석하느냐가 핵심인 문제예요. 계산하기 전에 어떤 식을 세울지부터 정해 보세요.
            </p>
          ) : null}

          {selectedProblem.coachHint || selectedProblem.expectedOutline.length ? (
            <details className="hint">
              <summary>힌트</summary>
              <div className="hint-body">
                {selectedProblem.coachHint ? <p>{selectedProblem.coachHint}</p> : null}
                {selectedProblem.expectedOutline.length ? (
                  <div className="stack-sm">
                    <span className="field-label" style={{ fontSize: 13 }}>
                      풀이 순서
                    </span>
                    <ol className="outline-steps">
                      {selectedProblem.expectedOutline.map((item) => (
                        <li key={item}>
                          <MathText text={item} />
                        </li>
                      ))}
                    </ol>
                  </div>
                ) : null}
              </div>
            </details>
          ) : null}
        </article>

        <aside className="card answer-card" aria-label="답안 작성">
          <div className="field">
            <label htmlFor="final-answer">정답</label>
            <input
              id="final-answer"
              className="input-lg"
              value={finalAnswer}
              autoComplete="off"
              onChange={(event) => {
                setFinalAnswer(event.target.value);
                emit("practice.answer.changed", {
                  problemId: selectedProblem.id,
                  value: event.target.value,
                });
              }}
              onKeyDown={(event) => {
                if (event.key === "Enter") {
                  event.preventDefault();
                  void submit();
                }
              }}
              placeholder={selectedProblem.finalPrompt || "답을 입력하세요"}
            />
          </div>

          <div className="field">
            <label htmlFor="scratch-note">풀이 메모</label>
            <textarea
              id="scratch-note"
              value={scratchNote}
              onChange={(event) => setScratchNote(event.target.value)}
              placeholder="채점에는 들어가지 않아요. 풀이 과정을 간단히 적어 두면 복습할 때 도움이 돼요."
            />
          </div>

          {submitSummary ? (
            <div className={`alert ${solved === true ? "alert-success" : solved === false ? "alert-error" : "alert-info"}`} role="status">
              <div>
                <strong>{solved === true ? "정답" : solved === false ? "오답" : "채점 완료"}</strong>
                {submitSummary}
              </div>
            </div>
          ) : null}
          {submitError ? (
            <p className="alert alert-error" role="alert">
              {submitError}
            </p>
          ) : null}

          <button className="btn btn-primary btn-lg btn-block" type="button" onClick={submit} disabled={submitting || !finalAnswer.trim()}>
            {submitting ? "채점 중..." : participant === "main" ? "제출하기" : "이 화면에서 제출하기"}
          </button>
          {participant === "main" ? (
            <div className="grid-2" style={{ gap: 8 }}>
              <button className="btn btn-secondary" type="button" onClick={moveNext} disabled={movingNext || !hasNextProblem}>
                {movingNext ? "이동 중..." : hasNextProblem ? "다음 문제" : "마지막 문제"}
              </button>
              <button className="btn btn-secondary" type="button" onClick={() => router.push("/review")}>
                채점 결과
              </button>
            </div>
          ) : null}
        </aside>
      </div>
    </div>
  );
}
