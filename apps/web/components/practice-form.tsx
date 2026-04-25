"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";

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
    try {
      const response = await api.submitPractice({
        finalAnswer,
        scratchNote,
      });
      emit(response.syncEvent.type as string, response.syncEvent);
      onSessionChange?.(response.lessonSession);
      const attempt = response.attempt as { summary?: string; solved?: boolean } | undefined;
      setSubmitSummary(
        attempt?.summary ??
          (attempt?.solved ? "채점이 완료됐습니다. 원하면 바로 다음 문항으로 넘어갈 수 있습니다." : "채점이 완료됐습니다. 다시 시도하거나 다음 문항으로 넘어갈 수 있습니다."),
      );
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
      }
    } finally {
      setMovingNext(false);
    }
  }

  const hasNextProblem = selectedIndex >= 0 && selectedIndex + 1 < problems.length;

  return (
    <section className="page practice-layout">
      <article className="panel problem-panel">
        <div className="inline-stat-list">
          <span>{selectedIndex >= 0 ? `${selectedIndex + 1} / ${problems.length}` : `1 / ${problems.length || 1}`}</span>
          <span>{selectedProblem.problemType ?? "대표 유형"}</span>
          <span>{selectedProblem.difficulty ?? "advanced"}</span>
          {selectedProblem.isKiller ? <span>킬러 문제</span> : null}
        </div>

        <div className="problem-statement" style={{ marginTop: 16 }}>
          <strong>
            {selectedIndex >= 0 ? `${selectedIndex + 1}번 문제` : "현재 문제"} · {selectedProblem.title}
          </strong>
          <p style={{ marginTop: 10 }}>{selectedProblem.statement}</p>
        </div>

        <div className="panel" style={{ marginTop: 16, padding: 16 }}>
          <p className="muted">{selectedProblem.coachHint}</p>
          <div className="outline-pill-list">
            {selectedProblem.expectedOutline.map((item) => (
              <span key={item} className="chip">
                {item}
              </span>
            ))}
          </div>
          {selectedProblem.isKiller ? (
            <div className="answer-card" style={{ marginTop: 14 }}>
              <strong>킬러 문제</strong>
              <p>조건 해석과 구조 전환이 중요한 문제예요. 계산보다 먼저 어떤 구조를 만들지부터 잡아보세요.</p>
            </div>
          ) : null}
        </div>
      </article>

      <article className="panel response-panel">
        <div className="input-stack">
          <div className="input-card">
            <label htmlFor="final-answer">
              <strong>최종 답 입력</strong>
            </label>
            <textarea
              id="final-answer"
              value={finalAnswer}
              onChange={(event) => {
                setFinalAnswer(event.target.value);
                emit("practice.answer.changed", {
                  problemId: selectedProblem.id,
                  value: event.target.value,
                });
              }}
              placeholder={selectedProblem.finalPrompt || ""}
            />
          </div>

          <div className="input-card">
            <label htmlFor="scratch-note">
              <strong>풀이 메모</strong>
            </label>
            <textarea
              id="scratch-note"
              value={scratchNote}
              onChange={(event) => setScratchNote(event.target.value)}
              placeholder="채점되지 않아요. 종이에 푼 핵심만 짧게 적어둬도 충분합니다."
            />
          </div>

          {submitSummary ? (
            <div className="answer-card">
              <strong>채점 결과</strong>
              <p>{submitSummary}</p>
            </div>
          ) : null}

          <div className="button-row">
            <button className="button primary" type="button" onClick={submit} disabled={submitting || !finalAnswer.trim()}>
              {submitting ? "제출 중..." : participant === "main" ? "답 제출하기" : "보조 화면에서 제출"}
            </button>
            {participant === "main" ? (
              <>
                <button className="button secondary" type="button" onClick={moveNext} disabled={movingNext || !hasNextProblem}>
                  {movingNext ? "이동 중..." : hasNextProblem ? "다음 문항으로 이동" : "마지막 문항"}
                </button>
                <button className="button ghost" type="button" onClick={() => router.push("/review")}>
                  채점 보기
                </button>
              </>
            ) : null}
            <span className="chip">
              {connectionState === "live"
                ? "세션 연결됨"
                : connectionState === "connecting"
                  ? "세션 연결 중"
                  : "세션 오프라인"}
            </span>
          </div>
        </div>
      </article>
    </section>
  );
}
