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
          <div className="chalk-doodles" aria-hidden="true">
            <span style={{ top: "14%", left: "58%", transform: "rotate(-6deg)" }}>sin²θ + cos²θ = 1</span>
            <span style={{ top: "24%", left: "8%", transform: "rotate(4deg)" }}>Σₖ₌₁ⁿ k² = n(n+1)(2n+1)/6</span>
            <span style={{ top: "78%", left: "60%", transform: "rotate(-3deg)" }}>P(A|B) = P(A∩B) / P(B)</span>
            <span style={{ top: "86%", left: "10%", transform: "rotate(2deg)" }}>|a⃗ + b⃗|² = |a⃗|² + 2a⃗·b⃗ + |b⃗|²</span>
            <span style={{ top: "40%", left: "70%", transform: "rotate(8deg)" }}>logₐ b = log b / log a</span>
          </div>

          <Brand tone="light" />

          <div className="auth-stage">
            <p className="auth-line">모르는 줄, 콕.</p>

            <div className="auth-board">
              <span className="auth-board-tag">미적분 · 4점</span>
              <p className="auth-board-q">
                lim (x→2) {"{"}f(x) − 3{"}"} / (x − 2) = 5 일 때
                <br />
                lim (x→2) {"{"}x²f(x) − 12{"}"} / (x − 2) 의 값은?
              </p>
              <p className="auth-board-step">
                g(x) = x²f(x) 로 두면 …{" "}
                <mark>= g′(2)</mark>
              </p>
              <div className="auth-bubble">
                <b>Q.</b> 왜 갑자기 g′(2)?
                <span className="auth-bubble-a">분자가 g(x) − g(2) 꼴이라서!</span>
              </div>
            </div>

            <div className="auth-sticky" aria-hidden="true">
              <span>오늘</span>
              <p>
                미분 강의 32분
                <br />→ 문제 11개
                <br />→ 어제 틀린 2개
              </p>
            </div>
          </div>

          <ul className="auth-subjects" aria-label="과목">
            {["공통수학", "대수", "미적분", "확률과 통계", "기하"].map((subject) => (
              <li key={subject}>{subject}</li>
            ))}
          </ul>
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
              <span>수학Ⅱ · 정적분으로 정의된 함수 · 4점</span>
            </div>
            <p className="nb-problem">
              모든 실수 x에 대하여 ∫₁ˣ f(t)dt = x³ + ax² − 2
              <br />
              를 만족시킬 때, f(a)의 값은?
            </p>
            <div className="nb-line">
              <span className="mark-ok" aria-label="맞음">✓</span>
              양변 미분 → f(x) = 3x² + 2ax
            </div>
            <div className="nb-line">
              <span className="mark-ng" aria-label="틀림">✗</span>
              <s>x = 0 대입 → 0 = −2</s>
              <span className="pen-note">아래끝은 1 !!</span>
            </div>
            <div className="nb-line">
              <span className="pen-note" style={{ marginLeft: 0 }}>x = 1 대입 → 1 + a − 2 = 0, a = 1</span>
            </div>
            <div className="nb-line">
              <span className="pen-note" style={{ marginLeft: 0 }}>f(1) = 3 + 2 = 5</span>
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
              <h4>미분계수의 정의 활용</h4>
              <div className="board-lines">
                <span>lim (x→2) {"{"}f(x) − 3{"}"} / (x − 2) = 5</span>
                <span className="dim">⇒ f(2) = 3, f′(2) = 5</span>
                <span className="dim">g(x) = x²f(x) 로 두면 g(2) = 12</span>
                <span className="eq">
                  lim (x→2) {"{"}x²f(x) − 12{"}"} / (x − 2) = g′(2)
                  <svg className="cursor" viewBox="0 0 24 24" aria-hidden="true">
                    <path d="M4 2l14 9-6 1.5 3.5 7-2.5 1.2-3.4-7L4 18z" />
                  </svg>
                </span>
                <span className="dim">= 2·2·f(2) + 2²·f′(2) = 32</span>
              </div>
              <div className="mock-ask">
                <div className="q">왜 갑자기 g′(2)가 돼요?</div>
                <div className="a">분자가 g(x) − g(2) 꼴이라서요. 미분계수 정의 그대로예요.</div>
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
