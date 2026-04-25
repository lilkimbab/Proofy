"use client";

import { FormEvent, useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { api } from "@/lib/api";
import {
  clearStoredSession,
  readStoredSession,
  writeStoredSession,
  type AuthSession,
} from "@/lib/auth";

type Stage = "intro" | "auth";
type AuthMode = "login" | "signup";

export default function WelcomePage() {
  const router = useRouter();
  const [stage, setStage] = useState<Stage>("intro");
  const [mode, setMode] = useState<AuthMode>("login");
  const [session, setSession] = useState<AuthSession | null>(null);
  const [loading, setLoading] = useState(false);
  const [authLoading, setAuthLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setSession(readStoredSession());
  }, []);

  async function routeWithBootstrap(nextSession: AuthSession) {
    writeStoredSession(nextSession);
    setSession(nextSession);
    setLoading(true);
    setError(null);

    try {
      const response = await api.bootstrap();
      router.replace(response.onboarding?.requiredRoute ?? "/survey");
    } catch (reason) {
      clearStoredSession();
      setSession(null);
      setStage("auth");
      setError(reason instanceof Error ? reason.message : "학습 정보를 불러오지 못했습니다.");
    } finally {
      setLoading(false);
    }
  }

  async function submitAuth(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formData = new FormData(event.currentTarget);
    setAuthLoading(true);
    setError(null);

    try {
      if (mode === "signup") {
        const response = await api.signup({
          displayName: String(formData.get("displayName") ?? ""),
          email: String(formData.get("email") ?? ""),
          password: String(formData.get("password") ?? ""),
        });
        await routeWithBootstrap(response.session);
      } else {
        const response = await api.login({
          email: String(formData.get("email") ?? ""),
          password: String(formData.get("password") ?? ""),
        });
        await routeWithBootstrap(response.session);
      }
    } catch (reason) {
      setError(
        reason instanceof Error
          ? reason.message
          : mode === "login"
            ? "로그인에 실패했습니다."
            : "회원가입에 실패했습니다.",
      );
    } finally {
      setAuthLoading(false);
    }
  }

  async function resumeStoredSession() {
    if (!session) {
      setStage("auth");
      return;
    }
    await routeWithBootstrap(session);
  }

  function startFreshAuth() {
    clearStoredSession();
    setSession(null);
    setError(null);
    setStage("auth");
  }

  if (loading) {
    return (
      <section className="loading-state">
        <div className="spinner" />
        <p>불러오는 중</p>
      </section>
    );
  }

  if (stage === "intro") {
    return (
      <section className="landing-stage">
        <div className="landing-backdrop" aria-hidden="true">
          <div className="landing-ring landing-ring-one" />
          <div className="landing-ring landing-ring-two" />
          <div className="floating-equation eq-one">막히는 순간, 주저없이 질문</div>
          <div className="floating-equation eq-two">우리만 믿고 따라와</div>
          <div className="floating-equation eq-three">강의와 문제풀이를 한 흐름으로</div>
        </div>

        <article className="landing-card">
          <p className="eyebrow">포기하지 않는 수학 메이트</p>
          <h1>수능까지 함께하는 러닝 메이트 Proofy</h1>

          {session ? (
            <div className="landing-return-panel">
              <span className="session-chip compact">
                <strong>{session.displayName}</strong>
                <span>{session.email}</span>
              </span>
              <div className="button-row">
                <button className="button primary button-large" type="button" onClick={resumeStoredSession}>
                  이어서 시작하기
                </button>
                <button className="button ghost" type="button" onClick={startFreshAuth}>
                  다른 계정으로 시작
                </button>
              </div>
            </div>
          ) : (
            <div className="button-row">
              <button className="button primary button-large" type="button" onClick={() => setStage("auth")}>
                시작하기
              </button>
            </div>
          )}

          {error ? <p className="inline-error">{error}</p> : null}
        </article>
      </section>
    );
  }

  return (
    <section className="landing-stage auth-stage">
      <article className="auth-sheet">
        <div className="auth-sheet-header">
          <div>
            <p className="eyebrow">계정</p>
            <h2>{mode === "login" ? "다시 시작할까요?" : "계정을 만들까요?"}</h2>
          </div>
          <button className="button ghost" type="button" onClick={() => setStage("intro")}>
            뒤로
          </button>
        </div>

        <div className="auth-toggle">
          <button
            type="button"
            className={`auth-toggle-button ${mode === "login" ? "active" : ""}`}
            onClick={() => setMode("login")}
          >
            로그인
          </button>
          <button
            type="button"
            className={`auth-toggle-button ${mode === "signup" ? "active" : ""}`}
            onClick={() => setMode("signup")}
          >
            회원가입
          </button>
        </div>

        <form className="field-grid" onSubmit={submitAuth}>
          {mode === "signup" ? (
            <div className="field">
              <label htmlFor="displayName">별명</label>
              <input id="displayName" name="displayName" placeholder="예: 홍길동" required />
            </div>
          ) : null}
          <div className="field">
            <label htmlFor="email">이메일</label>
            <input id="email" name="email" type="email" placeholder="you@example.com" required />
          </div>
          <div className="field">
            <label htmlFor="password">비밀번호</label>
            <input id="password" name="password" type="password" placeholder="8자 이상" required />
          </div>
          {error ? <p className="inline-error">{error}</p> : null}
          <div className="button-row">
            <button className="button primary" type="submit" disabled={authLoading}>
              {authLoading ? "처리 중..." : mode === "login" ? "로그인" : "회원가입"}
            </button>
          </div>
        </form>
      </article>
    </section>
  );
}
