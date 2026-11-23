"use client";

import { useEffect, useRef, useState } from "react";
import type { CSSProperties } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";

import { api, wsUrl } from "@/lib/api";
import type { LessonQuestionResponse, LessonSessionResponse, Scene, SceneObject } from "@/lib/types";
import { BoardScene } from "./board-scene";
import { Progress, initials } from "./ui";

type LessonRoomProps = {
  session: LessonSessionResponse;
};

type LessonFlowMode = "normal" | "interrupt" | "branch";
type SideTab = "outline" | "ask";

function objectSummary(object: SceneObject): string {
  if (object.label) return object.label;
  if (object.content) return object.content.split("\n")[0];
  if (object.items?.length) return object.items[0];
  if (object.table?.headers?.length) return object.table.headers.join(" · ");
  return "선택한 판서";
}

export function LessonRoom({ session }: LessonRoomProps) {
  const router = useRouter();
  const [lessonScenes, setLessonScenes] = useState<Scene[]>(session.scenes);
  const [sceneIndex, setSceneIndex] = useState(0);
  const [lessonMode, setLessonMode] = useState<LessonFlowMode>("normal");
  const [interruptScene, setInterruptScene] = useState<Scene | null>(null);
  const [branchScenes, setBranchScenes] = useState<Scene[]>([]);
  const [branchIndex, setBranchIndex] = useState(0);
  const [visibleObjects, setVisibleObjects] = useState<SceneObject[]>([]);
  const [question, setQuestion] = useState("");
  const [questionError, setQuestionError] = useState<string | null>(null);
  const [selectedObject, setSelectedObject] = useState<SceneObject | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [paused, setPaused] = useState(false);
  const [sideTab, setSideTab] = useState<SideTab>("outline");
  const [secondsLeft, setSecondsLeft] = useState(
    session.scenes[0]?.autoAdvanceSeconds ?? session.experience.autoAdvanceSeconds ?? 20,
  );
  const [boardRenderMode, setBoardRenderMode] = useState<"animated" | "instant">("animated");
  const socketRef = useRef<WebSocket | null>(null);
  const pausedSecondsRef = useRef<number | null>(null);
  const outlineRef = useRef<HTMLDivElement | null>(null);
  const branchScene = branchScenes[branchIndex] ?? null;
  const activeScene =
    lessonMode === "branch"
      ? branchScene ?? lessonScenes[sceneIndex]
      : lessonMode === "interrupt"
        ? interruptScene ?? lessonScenes[sceneIndex]
        : lessonScenes[sceneIndex];
  const questionFlowActive = lessonMode !== "normal";
  const sceneDuration =
    lessonScenes[sceneIndex]?.autoAdvanceSeconds ?? session.experience.autoAdvanceSeconds ?? 20;

  useEffect(() => {
    setLessonScenes(session.scenes);
    setSceneIndex(0);
    setLessonMode("normal");
    setInterruptScene(null);
    setBranchScenes([]);
    setBranchIndex(0);
    setSecondsLeft(session.scenes[0]?.autoAdvanceSeconds ?? session.experience.autoAdvanceSeconds ?? 20);
  }, [session]);

  useEffect(() => {
    const socket = new WebSocket(wsUrl(session.realtime.wsPath, "main"));
    socketRef.current = socket;
    return () => socket.close();
  }, [session.realtime.wsPath]);

  useEffect(() => {
    setSelectedObject((current) => {
      if (!current) return null;
      return activeScene.objects.find((object) => object.id === current.id) ?? null;
    });
    if (questionFlowActive || boardRenderMode === "instant") {
      setVisibleObjects(activeScene.objects);
      return;
    }
    setVisibleObjects([]);
    const timers = activeScene.objects.map((object) =>
      window.setTimeout(() => {
        setVisibleObjects((current) => [...current, object]);
      }, object.delayMs ?? 0),
    );
    return () => {
      timers.forEach((timer) => window.clearTimeout(timer));
    };
  }, [activeScene, boardRenderMode, questionFlowActive]);

  useEffect(() => {
    if (questionFlowActive || submitting || paused) {
      return;
    }
    const countdown = window.setInterval(() => {
      setSecondsLeft((current) => Math.max(current - 1, 0));
    }, 1000);
    return () => {
      window.clearInterval(countdown);
    };
  }, [sceneIndex, questionFlowActive, submitting, paused]);

  useEffect(() => {
    if (questionFlowActive || submitting || paused || secondsLeft !== 0) {
      return;
    }
    advanceScene();
    // advanceScene reads the latest state on each render; re-running on secondsLeft is intended.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [questionFlowActive, secondsLeft, submitting, paused]);

  useEffect(() => {
    if (lessonMode !== "branch" || submitting) {
      return;
    }
    const autoAdvanceSeconds = branchScene?.autoAdvanceSeconds ?? 0;
    if (!autoAdvanceSeconds || autoAdvanceSeconds <= 0) {
      return;
    }
    const timer = window.setTimeout(() => {
      if (branchIndex >= branchScenes.length - 1) {
        resumeLessonFromQuestion();
        return;
      }
      setBoardRenderMode("instant");
      setBranchIndex((current) => Math.min(current + 1, branchScenes.length - 1));
    }, autoAdvanceSeconds * 1000);
    return () => {
      window.clearTimeout(timer);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [branchIndex, branchScene, branchScenes.length, lessonMode, submitting]);

  // keep the current scene visible in the outline
  useEffect(() => {
    if (sideTab !== "outline") return;
    const current = outlineRef.current?.querySelector<HTMLButtonElement>("button.current");
    current?.scrollIntoView({ block: "nearest" });
  }, [sceneIndex, sideTab]);

  // ← / → to move between scenes, space to pause (ignored while typing)
  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      const target = event.target as HTMLElement | null;
      if (target && (target.tagName === "TEXTAREA" || target.tagName === "INPUT" || target.isContentEditable)) return;
      if (event.key === "ArrowRight") {
        event.preventDefault();
        advanceScene();
      } else if (event.key === "ArrowLeft") {
        event.preventDefault();
        prevScene();
      } else if (event.key === " " && lessonMode === "normal") {
        event.preventDefault();
        setPaused((value) => !value);
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  function emit(payload: Record<string, unknown>) {
    if (socketRef.current?.readyState === WebSocket.OPEN) {
      socketRef.current.send(JSON.stringify(payload));
    }
  }

  function resetSceneCountdown(targetScene: Scene) {
    setSecondsLeft(targetScene.autoAdvanceSeconds ?? session.experience.autoAdvanceSeconds ?? 20);
  }

  function resumeLessonFromQuestion() {
    const currentScene = lessonScenes[sceneIndex];
    setSelectedObject(null);
    setBoardRenderMode("instant");
    setLessonMode("normal");
    setInterruptScene(null);
    setBranchScenes([]);
    setBranchIndex(0);
    if (pausedSecondsRef.current !== null) {
      setSecondsLeft(pausedSecondsRef.current);
      pausedSecondsRef.current = null;
    } else {
      resetSceneCountdown(currentScene);
    }
    emit({
      type: "lesson.resume",
      payload: { sceneId: currentScene.id, sceneTitle: currentScene.title },
    });
  }

  function advanceScene() {
    if (lessonMode === "branch") {
      if (branchIndex >= branchScenes.length - 1) {
        resumeLessonFromQuestion();
        return;
      }
      setBoardRenderMode("instant");
      setBranchIndex((current) => current + 1);
      return;
    }
    if (lessonMode === "interrupt") {
      resumeLessonFromQuestion();
      return;
    }
    if (sceneIndex >= lessonScenes.length - 1) {
      emit({
        type: "lesson.complete",
        payload: { sceneId: lessonScenes[sceneIndex].id, sceneTitle: lessonScenes[sceneIndex].title },
      });
      api
        .completeLesson()
        .catch(() => null)
        .finally(() => router.push("/practice"));
      return;
    }
    const nextIndex = sceneIndex + 1;
    resetSceneCountdown(lessonScenes[nextIndex]);
    setBoardRenderMode("animated");
    setSceneIndex(nextIndex);
    emit({
      type: "lesson.scene.changed",
      payload: {
        sceneId: lessonScenes[nextIndex].id,
        sceneTitle: lessonScenes[nextIndex].title,
      },
    });
  }

  function jumpToScene(targetSceneId: string) {
    setLessonMode("normal");
    setInterruptScene(null);
    setBranchScenes([]);
    setBranchIndex(0);
    const index = lessonScenes.findIndex((scene) => scene.id === targetSceneId);
    if (index < 0) return;
    resetSceneCountdown(lessonScenes[index]);
    setBoardRenderMode("animated");
    setSceneIndex(index);
    emit({
      type: "lesson.scene.changed",
      payload: {
        sceneId: lessonScenes[index].id,
        sceneTitle: lessonScenes[index].title,
      },
    });
  }

  function prevScene() {
    if (lessonMode === "branch") {
      if (branchIndex <= 0) {
        resumeLessonFromQuestion();
        return;
      }
      setBoardRenderMode("instant");
      setBranchIndex((current) => Math.max(0, current - 1));
      return;
    }
    if (lessonMode === "interrupt") {
      resumeLessonFromQuestion();
      return;
    }
    const nextIndex = Math.max(0, sceneIndex - 1);
    resetSceneCountdown(lessonScenes[nextIndex]);
    setBoardRenderMode("animated");
    setSceneIndex(nextIndex);
    emit({
      type: "lesson.scene.changed",
      payload: {
        sceneId: lessonScenes[nextIndex].id,
        sceneTitle: lessonScenes[nextIndex].title,
      },
    });
  }

  async function submitQuestion() {
    if (!question.trim()) return;
    setSubmitting(true);
    setQuestionError(null);
    const userQuestion = question.trim();
    pausedSecondsRef.current = secondsLeft;
    try {
      const response: LessonQuestionResponse = await api.lessonQuestion({
        question: userQuestion,
        sceneId: activeScene.id,
        selectedObjectId: selectedObject?.id ?? null,
        runtimeSceneIds: lessonScenes.map((scene) => scene.id),
      });
      if (response.continuationPlan?.orderedSceneIds?.length) {
        const currentSceneId = lessonScenes[sceneIndex]?.id;
        const byId = new Map(lessonScenes.map((scene) => [scene.id, scene]));
        const reordered = response.continuationPlan.orderedSceneIds
          .map((sceneId) => byId.get(sceneId))
          .filter((scene): scene is Scene => Boolean(scene));
        if (reordered.length === lessonScenes.length) {
          setLessonScenes(reordered);
          if (currentSceneId) {
            const reorderedIndex = reordered.findIndex((scene) => scene.id === currentSceneId);
            if (reorderedIndex >= 0) {
              setSceneIndex(reorderedIndex);
            }
          }
        }
      }
      setSelectedObject(null);
      setBoardRenderMode("instant");
      if (response.branchScenes?.length) {
        setLessonMode("branch");
        setInterruptScene(null);
        setBranchScenes(response.branchScenes);
        setBranchIndex(0);
      } else {
        setLessonMode("interrupt");
        setBranchScenes([]);
        setBranchIndex(0);
        setInterruptScene(response.scene);
      }
      emit(response.syncEvent);
      setQuestion("");
    } catch (reason) {
      setQuestionError(reason instanceof Error ? reason.message : "질문 답변을 불러오지 못했어요.");
    } finally {
      setSubmitting(false);
    }
  }

  const totalScenes = lessonScenes.length;
  const lessonProgress = totalScenes ? ((sceneIndex + 1) / totalScenes) * 100 : 0;
  const ringProgress = sceneDuration > 0 ? Math.round((1 - secondsLeft / sceneDuration) * 100) : 0;
  const scenePoints = [
    { key: "goal", label: "학습 목표", text: activeScene.teachingGoal },
    { key: "takeaway", label: "핵심 정리", text: activeScene.takeaway },
    { key: "exam", label: "시험장 포인트", text: activeScene.examCue },
  ].filter((point) => Boolean(point.text));

  const narrationText = activeScene.narration || activeScene.takeaway || "";
  // Answer scenes often write the narration onto the board itself; don't repeat it as a subtitle.
  const boardText = activeScene.objects.map((object) => object.content ?? "").join(" ");
  const subtitleText =
    narrationText && !boardText.includes(narrationText.slice(0, 40)) ? narrationText : "";
  const nextLabel =
    lessonMode === "branch"
      ? branchIndex >= branchScenes.length - 1
        ? "강의로 돌아가기"
        : "다음 설명"
      : lessonMode === "interrupt"
        ? "강의로 돌아가기"
        : sceneIndex >= totalScenes - 1
          ? "문제 풀러 가기"
          : "다음 장면";

  return (
    <div className="player">
      <header className="player-header">
        <Link className="player-back" href="/dashboard" aria-label="대시보드로 나가기">
          ←
        </Link>
        <div className="player-title">
          <span>{session.unitTitle}</span>
          <strong>{activeScene.title}</strong>
        </div>
        <div className="player-progress">
          <span>
            강의 진도 {Math.round(lessonProgress)}%
          </span>
          <Progress value={lessonProgress} size="sm" label="강의 진행률" />
        </div>
      </header>

      <div className="player-body">
        <main className="player-stage">
          {questionFlowActive ? (
            <div className="mode-banner" role="status">
              <span>
                {lessonMode === "branch"
                  ? `질문 답변 ${branchIndex + 1}/${branchScenes.length} · 강의는 잠시 멈춰 있어요`
                  : "질문 답변 · 강의는 잠시 멈춰 있어요"}
              </span>
              <button className="btn btn-sm btn-secondary" type="button" onClick={resumeLessonFromQuestion}>
                강의로 돌아가기
              </button>
            </div>
          ) : null}

          <section className="video" aria-label="AI 칠판 강의">
            <div className="video-screen">
              <BoardScene
                objects={visibleObjects}
                activeObjectId={selectedObject?.id ?? null}
                onObjectSelect={
                  lessonMode === "normal"
                    ? (object) => {
                        setSelectedObject(object);
                        setSideTab("ask");
                      }
                    : undefined
                }
                instantRender={Boolean(questionFlowActive || boardRenderMode === "instant")}
              />
            </div>

            {subtitleText ? (
              <div className="subtitle" aria-live="polite">
                <span className="speaker">
                  <span className="avatar" aria-hidden="true">
                    {initials(session.teacherName)}
                  </span>
                  {session.teacherName}
                </span>
                <p>{subtitleText}</p>
              </div>
            ) : null}

            <div className="video-controls">
              <button className="icon-btn" type="button" onClick={prevScene} aria-label="이전 장면" title="이전 (←)">
                <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 6h2v12H6zM9.5 12 18 6v12z" fill="currentColor" /></svg>
              </button>
              {lessonMode === "normal" ? (
                <button
                  className="icon-btn icon-btn-main"
                  type="button"
                  onClick={() => setPaused((value) => !value)}
                  aria-label={paused ? "재생" : "일시정지"}
                  title="재생/일시정지 (스페이스)"
                >
                  {paused ? (
                    <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M8 5v14l11-7z" fill="currentColor" /></svg>
                  ) : (
                    <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M7 5h4v14H7zM13 5h4v14h-4z" fill="currentColor" /></svg>
                  )}
                </button>
              ) : null}
              <button className="icon-btn" type="button" onClick={advanceScene} aria-label={nextLabel} title="다음 (→)">
                <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M16 6h2v12h-2zM6 6l8.5 6L6 18z" fill="currentColor" /></svg>
              </button>

              <span className="video-time">
                {sceneIndex + 1} / {totalScenes}
              </span>

              <div className="scrubber" role="group" aria-label="장면 이동">
                {lessonScenes.map((scene, index) => (
                  <button
                    key={scene.id}
                    type="button"
                    className={index < sceneIndex ? "done" : index === sceneIndex ? "current" : ""}
                    style={index === sceneIndex ? ({ "--p": `${paused || questionFlowActive ? 0 : ringProgress}%` } as CSSProperties) : undefined}
                    onClick={() => jumpToScene(scene.id)}
                    aria-label={`${index + 1}. ${scene.title}`}
                    title={`${index + 1}. ${scene.title}`}
                  />
                ))}
              </div>

              {lessonMode === "normal" ? (
                <span className="video-auto">{paused ? "일시정지" : `${secondsLeft}초 뒤 다음`}</span>
              ) : null}
              <button className="btn btn-primary btn-sm" type="button" onClick={advanceScene}>
                {nextLabel} →
              </button>
            </div>
          </section>

          {scenePoints.length ? (
            <section className="lecture-notes" aria-label="강의 노트">
              {scenePoints.map((point) => (
                <div key={point.key} className={`lecture-note ${point.key}`}>
                  <b>{point.label}</b>
                  <p>{point.text}</p>
                </div>
              ))}
            </section>
          ) : null}
        </main>

        <aside className="player-side" aria-label="강의 목차와 질문">
          <div className="segmented" role="tablist">
            <button
              type="button"
              role="tab"
              aria-selected={sideTab === "outline"}
              className={sideTab === "outline" ? "active" : ""}
              onClick={() => setSideTab("outline")}
            >
              강의 목차
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={sideTab === "ask"}
              className={sideTab === "ask" ? "active" : ""}
              onClick={() => setSideTab("ask")}
            >
              질문하기
            </button>
          </div>

          <div className="side-scroll">
            {sideTab === "outline" ? (
              <div className="outline" ref={outlineRef}>
                {lessonScenes.map((scene, index) => {
                  const state = index === sceneIndex ? "current" : index < sceneIndex ? "done" : "";
                  return (
                    <button
                      key={scene.id}
                      type="button"
                      className={state}
                      onClick={() => jumpToScene(scene.id)}
                      aria-current={index === sceneIndex ? "step" : undefined}
                    >
                      <span className="n">{index < sceneIndex ? "✓" : String(index + 1).padStart(2, "0")}</span>
                      <span>{scene.title}</span>
                    </button>
                  );
                })}
              </div>
            ) : (
              <div className="ask">
                {questionFlowActive ? (
                  <div className="alert alert-info">
                    <div>
                      <strong>답변을 보는 중이에요</strong>
                      강의는 멈춰 있어요.
                    </div>
                  </div>
                ) : (
                  <>
                    <p className="muted" style={{ fontSize: 14 }}>
                      칠판에서 모르는 줄을 누르면 그 줄로 질문돼요.
                    </p>
                    {selectedObject ? (
                      <div className="selected-object row-between">
                        <span>선택한 판서: {objectSummary(selectedObject).slice(0, 60)}</span>
                        <button type="button" className="link-button" onClick={() => setSelectedObject(null)}>
                          해제
                        </button>
                      </div>
                    ) : null}
                    <div className="field">
                      <label htmlFor="question">질문</label>
                      <textarea
                        id="question"
                        value={question}
                        onChange={(event) => {
                          setQuestion(event.target.value);
                          if (questionError) {
                            setQuestionError(null);
                          }
                        }}
                        onKeyDown={(event) => {
                          if (event.key === "Enter" && (event.metaKey || event.ctrlKey)) {
                            event.preventDefault();
                            void submitQuestion();
                          }
                        }}
                        placeholder="예: 여기서 왜 이 식을 먼저 세워요?"
                      />
                    </div>
                    {questionError ? (
                      <p className="alert alert-error" role="alert">
                        {questionError}
                      </p>
                    ) : null}
                    <button
                      className="btn btn-primary btn-block"
                      type="button"
                      onClick={submitQuestion}
                      disabled={submitting || !question.trim()}
                    >
                      {submitting ? "답변 생성 중..." : "질문하기"}
                    </button>
                    {session.questionStarters?.length ? (
                      <div className="starters">
                        <span className="field-label" style={{ fontSize: 13 }}>
                          자주 하는 질문
                        </span>
                        {session.questionStarters.slice(0, 5).map((starter) => (
                          <button key={starter} type="button" onClick={() => setQuestion(starter)}>
                            {starter}
                          </button>
                        ))}
                      </div>
                    ) : null}
                  </>
                )}
              </div>
            )}
          </div>
        </aside>
      </div>
    </div>
  );
}
