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

const FEATURES = [
  {
    icon: "◎",
    title: "10분 진단",
    body: "12문항으로 단원별 실력을 확인하고, 수능까지 남은 기간에 맞춰 하루·주간 계획을 짜 드려요.",
  },
  {
    icon: "✎",
    title: "AI 칠판 강의",
    body: "판서를 보면서 개념을 한 장면씩 정리해요. 모르는 부분은 칠판을 눌러 바로 질문할 수 있어요.",
  },
  {
    icon: "✓",
    title: "풀이 과정 채점",
    body: "답만 맞았는지 보지 않고 풀이 과정을 단계별로 확인해요. 어디서 틀렸는지 알려 드려요.",
  },
  {
    icon: "↺",
    title: "오답노트 자동 정리",
    body: "틀린 문제는 오답노트에 자동으로 모이고, 다음 날 계획에 복습 문제로 다시 나와요.",
  },
];

const STEPS = [
  { title: "진단", body: "단원별 실력과 약점을 확인해요." },
  { title: "강의", body: "약한 단원부터 AI 칠판 강의를 들어요." },
  { title: "문제 풀이", body: "배운 내용을 바로 문제로 확인해요." },
  { title: "복습", body: "틀린 문제를 오답노트로 다시 풀어요." },
];

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
            <p>모르는 부분은 칠판을 눌러서 바로 질문하세요.</p>
            <footer>Proofy AI 칠판 강의</footer>
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
                  ? "이메일과 비밀번호를 입력해 주세요."
                  : "가입하면 바로 진단 평가를 볼 수 있어요."}
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
              무료로 시작하기
            </button>
          </div>
        </div>
      </header>

      <section className="hero">
        <div className="container hero-grid">
          <div className="hero-copy">
            <span className="eyebrow">고3 수능 수학</span>
            <h1>
              <em>내 약점</em>부터 채우는
              <br />
              수능 수학 강의
            </h1>
            <p>
              10분 진단으로 어디서부터 공부할지 정하고, 강의를 듣다 막히면 바로 질문하세요. 틀린 문제는 오답노트에 자동으로 쌓여요.
            </p>

            {session ? (
              <div className="resume-box">
                <span className="avatar avatar-lg" aria-hidden="true">
                  {initials(session.displayName)}
                </span>
                <div>
                  <strong>{session.displayName}님으로 로그인되어 있어요</strong>
                  <span>{session.email}</span>
                </div>
                <button className="btn btn-primary" type="button" onClick={resumeStoredSession}>
                  학습 이어하기
                </button>
              </div>
            ) : null}

            <div className="hero-actions">
              {session ? (
                <button className="btn btn-secondary btn-lg" type="button" onClick={startFreshAuth}>
                  다른 계정으로 로그인
                </button>
              ) : (
                <>
                  <button className="btn btn-primary btn-lg" type="button" onClick={() => openAuth("signup")}>
                    무료로 시작하기
                  </button>
                  <button className="btn btn-secondary btn-lg" type="button" onClick={() => openAuth("login")}>
                    로그인
                  </button>
                </>
              )}
            </div>

            <div className="hero-points">
              <span>진단 10분</span>
              <span>맞춤 학습 계획</span>
              <span>오답노트 자동 정리</span>
            </div>
            {error ? (
              <p className="alert alert-error" role="alert" style={{ marginTop: 20, maxWidth: 460 }}>
                {error}
              </p>
            ) : null}
          </div>

          <div className="preview" aria-hidden="true">
            <div className="preview-bar">
              <i />
              <i />
              <i />
              <span>미적분 · 미분계수의 뜻</span>
            </div>
            <div className="preview-board">
              <h4>미분계수의 뜻</h4>
              <p>
                f′(a) = lim<sub>h→0</sub> <span className="mark">[f(a+h) − f(a)]</span> / h
              </p>
              <ul>
                <li>평균변화율에서 간격 h를 0으로 보낸 값</li>
                <li>그래프 위 x = a에서 접선의 기울기</li>
              </ul>
            </div>
            <div className="preview-ask">
              <div className="q">Q. 왜 h를 0으로 보내요?</div>
              <div className="a">한 점에서의 순간 기울기를 구하려면 두 점 사이 간격을 없애야 해서예요.</div>
            </div>
          </div>
        </div>
      </section>

      <section className="landing-section alt">
        <div className="container">
          <div className="landing-section-head">
            <span className="eyebrow">주요 기능</span>
            <h2>강의부터 오답노트까지 한 곳에서</h2>
            <p>인강 따로, 문제집 따로 볼 필요 없어요. 진단 결과에 맞춰 강의와 문제가 정해져요.</p>
          </div>
          <div className="feature-grid">
            {FEATURES.map((feature) => (
              <article key={feature.title} className="card feature">
                <div className="feature-icon" aria-hidden="true">
                  {feature.icon}
                </div>
                <h3>{feature.title}</h3>
                <p>{feature.body}</p>
              </article>
            ))}
          </div>
        </div>
      </section>

      <section className="landing-section">
        <div className="container">
          <div className="landing-section-head">
            <span className="eyebrow">학습 방법</span>
            <h2>매일 네 단계로 공부해요</h2>
          </div>
          <div className="steps">
            {STEPS.map((step) => (
              <div key={step.title} className="step">
                <h3>{step.title}</h3>
                <p>{step.body}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="landing-section" style={{ paddingTop: 0 }}>
        <div className="container">
          <div className="cta-band">
            <div>
              <h2>진단 평가부터 받아 보세요</h2>
              <p>10분이면 오늘 들을 강의와 풀 문제가 정해져요.</p>
            </div>
            <button className="btn btn-primary btn-lg" type="button" onClick={() => openAuth("signup")}>
              무료로 시작하기
            </button>
          </div>
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
