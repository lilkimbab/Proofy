"use client";

import { FormEvent, useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { Brand, LoadingState, initials } from "@/components/ui";
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
      openAuth("login");
      return;
    }
    await routeWithBootstrap(session);
  }

  function startFreshAuth() {
    clearStoredSession();
    setSession(null);
    openAuth("login");
  }

  function openAuth(nextMode: AuthMode) {
    setMode(nextMode);
    setError(null);
    setStage("auth");
    window.scrollTo({ top: 0 });
  }

  if (loading) {
    return <LoadingState message="학습 정보를 불러오는 중이에요" />;
  }

  if (stage === "auth") {
    return (
      <div className="auth-page">
        <aside className="auth-aside">
          <Brand tone="light" />
          <blockquote>
            <p>모르는 줄, 콕.</p>
            <footer>Proofy 칠판 강의</footer>
          </blockquote>
          <div className="chalk-eq">f′(a) = lim(h→0) [f(a+h) − f(a)] / h</div>
        </aside>

        <main className="auth-main">
          <div className="auth-card">
            <button className="btn btn-ghost btn-sm auth-back" type="button" onClick={() => setStage("intro")}>
              ← 처음으로
            </button>
            <div>
              <h1>{mode === "login" ? "로그인" : "회원가입"}</h1>
              <p className="lead">
                {mode === "login"
                  ? "이메일로 로그인"
                  : "가입하고 바로 진단 12문제."}
              </p>
            </div>

            <div className="segmented" role="tablist" aria-label="로그인 또는 회원가입">
              <button
                type="button"
                role="tab"
                aria-selected={mode === "login"}
                className={mode === "login" ? "active" : ""}
                onClick={() => {
                  setMode("login");
                  setError(null);
                }}
              >
                로그인
              </button>
              <button
                type="button"
                role="tab"
                aria-selected={mode === "signup"}
                className={mode === "signup" ? "active" : ""}
                onClick={() => {
                  setMode("signup");
                  setError(null);
                }}
              >
                회원가입
              </button>
            </div>

            <form className="auth-form" onSubmit={submitAuth}>
              {mode === "signup" ? (
                <div className="field">
                  <label htmlFor="displayName">이름</label>
                  <input id="displayName" name="displayName" placeholder="예: 홍길동" autoComplete="nickname" required />
                </div>
              ) : null}
              <div className="field">
                <label htmlFor="email">이메일</label>
                <input
                  id="email"
                  name="email"
                  type="email"
                  placeholder="you@example.com"
                  autoComplete="email"
                  required
                />
              </div>
              <div className="field">
                <label htmlFor="password">비밀번호</label>
                <input
                  id="password"
                  name="password"
                  type="password"
                  placeholder={mode === "signup" ? "8자 이상 입력해 주세요" : "비밀번호"}
                  autoComplete={mode === "signup" ? "new-password" : "current-password"}
                  required
                />
              </div>
              {error ? (
                <p className="alert alert-error" role="alert">
                  {error}
                </p>
              ) : null}
              <button className="btn btn-primary btn-lg btn-block" type="submit" disabled={authLoading}>
                {authLoading ? "처리 중..." : mode === "login" ? "로그인" : "가입하기"}
              </button>
            </form>

            <p className="auth-switch">
              {mode === "login" ? "아직 계정이 없나요? " : "이미 계정이 있나요? "}
              <button
                type="button"
                className="link-button"
                onClick={() => {
                  setMode(mode === "login" ? "signup" : "login");
                  setError(null);
                }}
              >
                {mode === "login" ? "회원가입" : "로그인"}
              </button>
            </p>
          </div>
        </main>
      </div>
    );
  }

  return (
    <div className="landing">
      <header className="landing-header">
        <div className="container">
          <Brand />
          <div className="row">
            <button className="btn btn-ghost" type="button" onClick={() => openAuth("login")}>
              로그인
            </button>
            <button className="btn btn-primary" type="button" onClick={() => openAuth("signup")}>
              시작하기
            </button>
          </div>
        </div>
      </header>

      <section className="hero2 graph-paper">
        <div className="container hero2-inner">
          <div className="hero2-copy">
            <h1 className="hero2-title">
              해설지 봐도
              <br />
              모르겠던{" "}
              <span className="circled">
                그 한 줄
                <svg viewBox="0 0 300 110" preserveAspectRatio="none" aria-hidden="true">
                  <path d="M18 62 C 20 18, 150 6, 252 20 C 300 28, 296 84, 214 96 C 140 108, 30 100, 14 66 C 8 50, 40 34, 70 30" />
                </svg>
              </span>
            </h1>
            <p className="hero2-sub">그 줄만 콕 집어서 물어보세요.</p>

            {session ? (
              <div className="resume-box">
                <span className="avatar avatar-lg" aria-hidden="true">
                  {initials(session.displayName)}
                </span>
                <div>
                  <strong>{session.displayName}님</strong>
                  <span>{session.email}</span>
                </div>
                <button className="btn btn-primary" type="button" onClick={resumeStoredSession}>
                  이어서 하기
                </button>
              </div>
            ) : null}

            <div className="hero-actions">
              {session ? (
                <button className="btn btn-ghost" type="button" onClick={startFreshAuth}>
                  다른 계정으로
                </button>
              ) : (
                <>
                  <button className="btn btn-primary btn-lg" type="button" onClick={() => openAuth("signup")}>
                    진단부터 풀어보기
                  </button>
                  <button className="btn btn-ghost btn-lg" type="button" onClick={() => openAuth("login")}>
                    로그인
                  </button>
                </>
              )}
            </div>
            {error ? (
              <p className="alert alert-error" role="alert" style={{ marginTop: 20, maxWidth: 460 }}>
                {error}
              </p>
            ) : null}
          </div>

          <figure className="notebook taped" aria-label="오답노트 예시">
            <div className="notebook-head">
              <b>오답노트</b>
              <span>미적분Ⅰ · 접선</span>
            </div>
            <p className="nb-problem">
              곡선 y = x³ − 3x 위의 점 (2, 2)에서
              <br />
              그은 접선의 방정식을 구하시오.
            </p>
            <div className="nb-line">
              <span className="mark-ok" aria-label="맞음">✓</span>
              y′ = 3x² − 3
            </div>
            <div className="nb-line">
              <span className="mark-ok" aria-label="맞음">✓</span>
              기울기 y′(2) = 9
            </div>
            <div className="nb-line">
              <span className="mark-ng" aria-label="틀림">✗</span>
              y = 9x <s>+ 16</s>
              <span className="pen-note">−18 + 2 = −16 !!</span>
            </div>
            <div className="nb-line">
              <span className="pen-note" style={{ marginLeft: 0 }}>이항할 때 부호 또 틀림</span>
            </div>
            <span className="nb-stamp">다시 풀기</span>
          </figure>
        </div>
      </section>

      <section className="scene">
        <div className="container scene-inner">
          <h2 className="big-type">
            오늘 뭐 하지?
            <br />
            <span className="mark">고민은 여기서 끝.</span>
          </h2>
          <div className="scene-visual">
            <div className="mock-card" aria-hidden="true">
              <div className="mock-card-head">
                <b>오늘의 학습</b>
                <span>D-223</span>
              </div>
              <div className="mock-task done">
                <span className="task-icon lesson">강의</span>
                <div>
                  <strong>미분 · 개념 다시 보기</strong>
                  <small>32분</small>
                </div>
                <span className="badge badge-success">완료</span>
              </div>
              <div className="mock-task">
                <span className="task-icon practice">문제</span>
                <div>
                  <strong>미분 · 기본 문제 11문항</strong>
                  <small>38분</small>
                </div>
                <span className="badge badge-primary">4/11</span>
              </div>
              <div className="mock-task">
                <span className="task-icon review">복습</span>
                <div>
                  <strong>수열 · 어제 틀린 2문항</strong>
                  <small>16분</small>
                </div>
                <span className="badge">대기</span>
              </div>
            </div>
            <span className="hand-note note-plan" aria-hidden="true">
              ↖ 진단 결과대로 매일 알아서
            </span>
          </div>
        </div>
      </section>

      <section className="scene scene-dark">
        <div className="container scene-inner flip">
          <h2 className="big-type">
            모르는 줄,
            <br />
            콕.
          </h2>
          <div className="scene-visual">
            <div className="mock-board" aria-hidden="true">
              <h4>미분계수의 정의</h4>
              <div className="eq">
                f′(a) = lim (h→0) [f(a+h) − f(a)] / h
                <svg className="cursor" viewBox="0 0 24 24" aria-hidden="true">
                  <path d="M4 2l14 9-6 1.5 3.5 7-2.5 1.2-3.4-7L4 18z" />
                </svg>
              </div>
              <ul>
                <li>평균변화율에서 h를 0으로 보낸 값</li>
                <li>x = a에서 그은 접선의 기울기</li>
              </ul>
              <div className="mock-ask">
                <div className="q">왜 h를 0으로 보내요?</div>
                <div className="a">두 점을 한 점으로 붙여야 &lsquo;그 순간&rsquo;의 기울기가 되거든요.</div>
              </div>
            </div>
            <span className="hand-note note-board" aria-hidden="true">
              여기 누르면 끝 ↗
            </span>
          </div>
        </div>
      </section>

      <section className="finale graph-paper">
        <div className="container finale-inner">
          <h2 className="big-type">일단 12문제만 풀어봐요.</h2>
          <button className="btn btn-primary btn-lg" type="button" onClick={() => openAuth("signup")}>
            진단 시작
          </button>
          <span className="hand-note">10분이면 끝나요</span>
        </div>
      </section>

      <footer className="landing-footer">
        <div className="container row-between">
          <Brand />
          <span>© Proofy</span>
        </div>
      </footer>
    </div>
  );
}
