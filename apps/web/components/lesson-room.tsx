"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";

import { api, wsUrl } from "@/lib/api";
import type { LessonQuestionResponse, LessonSessionResponse, Scene, SceneObject } from "@/lib/types";
import { BoardScene } from "./board-scene";

type LessonRoomProps = {
  session: LessonSessionResponse;
};

type LessonFlowMode = "normal" | "interrupt" | "branch";

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
  const [secondsLeft, setSecondsLeft] = useState(
    session.scenes[0]?.autoAdvanceSeconds ?? session.experience.autoAdvanceSeconds ?? 20,
  );
  const [boardRenderMode, setBoardRenderMode] = useState<"animated" | "instant">("animated");
  const socketRef = useRef<WebSocket | null>(null);
  const pausedSecondsRef = useRef<number | null>(null);
  const branchScene = branchScenes[branchIndex] ?? null;
  const activeScene =
    lessonMode === "branch"
      ? branchScene ?? lessonScenes[sceneIndex]
      : lessonMode === "interrupt"
        ? interruptScene ?? lessonScenes[sceneIndex]
        : lessonScenes[sceneIndex];
  const questionFlowActive = lessonMode !== "normal";

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
      }, object.delayMs ?? 0)
    );
    return () => {
      timers.forEach((timer) => window.clearTimeout(timer));
    };
  }, [activeScene, boardRenderMode, questionFlowActive]);

  useEffect(() => {
    if (questionFlowActive || submitting) {
      return;
    }
    const countdown = window.setInterval(() => {
      setSecondsLeft((current) => Math.max(current - 1, 0));
    }, 1000);
    return () => {
      window.clearInterval(countdown);
    };
  }, [sceneIndex, questionFlowActive, submitting]);

  useEffect(() => {
    if (questionFlowActive || submitting || secondsLeft !== 0) {
      return;
    }
    advanceScene();
  }, [questionFlowActive, secondsLeft, submitting]);

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
  }, [branchIndex, branchScene, branchScenes.length, lessonMode, submitting]);

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
        payload: { sceneId: lessonScenes[sceneIndex].id, sceneTitle: lessonScenes[sceneIndex].title }
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
        sceneTitle: lessonScenes[nextIndex].title
      }
    });
  }

  function nextScene() {
    advanceScene();
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
        sceneTitle: lessonScenes[index].title
      }
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
        sceneTitle: lessonScenes[nextIndex].title
      }
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

  return (
    <section className="page lesson-page immersive lesson-page-full">
      <article className="panel lesson-main lesson-main-immersive">
        <div className="lesson-toolbar glass lesson-toolbar-minimal">
          <div>
            <h3 className="lesson-heading">{activeScene.title}</h3>
          </div>
          <div className="button-row">
            {lessonMode === "normal" ? (
              <>
                <button className="button secondary" onClick={prevScene}>
                  이전 장면
                </button>
                <button className="button primary" onClick={nextScene}>
                  다음 장면
                </button>
              </>
            ) : lessonMode === "branch" ? (
              <>
                <button className="button secondary" onClick={prevScene}>
                  {branchIndex <= 0 ? "강의로 돌아가기" : "이전 설명"}
                </button>
                <button className="button primary" onClick={nextScene}>
                  {branchIndex >= branchScenes.length - 1 ? "강의로 돌아가기" : "다음 설명"}
                </button>
              </>
            ) : (
              <button className="button primary" onClick={resumeLessonFromQuestion}>
                강의로 돌아가기
              </button>
            )}
          </div>
        </div>

        <div className="lesson-stage lesson-stage-hero">
          <BoardScene
            objects={visibleObjects}
            activeObjectId={selectedObject?.id ?? null}
            onObjectSelect={lessonMode === "normal" ? setSelectedObject : undefined}
            instantRender={Boolean(questionFlowActive || boardRenderMode === "instant")}
          />
          {!questionFlowActive ? (
            <section className="lesson-question-dock">
              <textarea
                id="question"
                value={question}
                onChange={(event) => {
                  setQuestion(event.target.value);
                  if (questionError) {
                    setQuestionError(null);
                  }
                }}
                placeholder="예: 왜 여기서 이 식부터 세워?"
              />
              {questionError ? <p className="inline-error">{questionError}</p> : null}
              <div className="button-row">
                <button className="button primary" type="button" onClick={submitQuestion} disabled={submitting}>
                  {submitting ? "답변 정리 중..." : "질문 보내기"}
                </button>
              </div>
            </section>
          ) : null}
        </div>

        {questionFlowActive ? (
          <div className="lesson-interrupt-panel">
            <div className="button-row lesson-return-row">
              <button className="button primary" type="button" onClick={resumeLessonFromQuestion}>
                강의로 돌아가기
              </button>
            </div>
          </div>
        ) : null}
      </article>

    </section>
  );
}
