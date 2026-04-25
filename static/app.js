const state = {
  bootstrap: null,
  dashboard: null,
  lesson: null,
  diagnosticResult: null,
  review: null,
  attempt: null,
  route: "welcome",
  lessonPlayback: {
    sceneIndex: 0,
    interrupt: null,
    timers: [],
  },
};

const routes = [
  { id: "welcome", label: "온보딩" },
  { id: "dashboard", label: "대시보드" },
  { id: "lesson", label: "AI 칠판 강의" },
  { id: "practice", label: "문제 풀이" },
  { id: "review", label: "복습" },
];

const api = {
  async get(path) {
    const response = await fetch(path);
    if (!response.ok) {
      throw new Error(`GET ${path} failed`);
    }
    return response.json();
  },
  async post(path, payload) {
    const response = await fetch(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!response.ok) {
      throw new Error(`POST ${path} failed`);
    }
    return response.json();
  },
};

const app = document.getElementById("app");
const topnav = document.getElementById("topnav");

document.addEventListener("DOMContentLoaded", init);
window.addEventListener("hashchange", handleRouteChange);

async function init() {
  try {
    state.bootstrap = await api.get("/api/bootstrap");
    state.dashboard = state.bootstrap.dashboard;
    state.review = state.bootstrap.latestAttempt ? await api.get("/api/review/latest") : null;
    state.route = parseRoute();
    renderTopnav();
    renderRoute();
  } catch (error) {
    app.innerHTML = `
      <section class="empty-card">
        <h2>데모를 불러오지 못했습니다.</h2>
        <p class="muted">${escapeHtml(String(error.message || error))}</p>
      </section>
    `;
  }
}

function parseRoute() {
  const raw = window.location.hash.replace(/^#\//, "").trim();
  return routes.some((route) => route.id === raw) ? raw : "welcome";
}

function handleRouteChange() {
  state.route = parseRoute();
  renderTopnav();
  renderRoute();
}

function navigate(route) {
  window.location.hash = `#/${route}`;
}

function renderTopnav() {
  topnav.innerHTML = routes
    .map(
      (route) => `
        <button class="nav-link ${state.route === route.id ? "active" : ""}" data-route="${route.id}">
          ${route.label}
        </button>
      `,
    )
    .join("");

  topnav.querySelectorAll("[data-route]").forEach((button) => {
    button.addEventListener("click", () => navigate(button.dataset.route));
  });
}

function renderRoute() {
  clearLessonTimers();
  if (!state.bootstrap) {
    app.innerHTML = `
      <section class="loading-state">
        <div class="spinner"></div>
        <p>데모 데이터를 준비 중입니다.</p>
      </section>
    `;
    return;
  }

  switch (state.route) {
    case "dashboard":
      renderDashboard();
      break;
    case "lesson":
      renderLessonShell();
      break;
    case "practice":
      renderPractice();
      break;
    case "review":
      renderReview();
      break;
    case "welcome":
    default:
      renderWelcome();
      break;
  }
  renderTopnav();
}

function renderWelcome() {
  const profile = state.bootstrap.profile;
  const diagnostic = state.diagnosticResult;
  app.innerHTML = `
    <section class="page">
      <article class="hero-card">
        <div class="hero-copy">
          <p class="eyebrow">Proofy Demo</p>
          <h2>수능 수학 한 루프를<br />Proofy로 직접 보여줍니다.</h2>
          <p>
            이 데모는 “진단 → 계획 → AI 칠판 강의 → 질문 인터럽트 → 단계별 풀이 평가 → 회복 루틴”
            을 하나의 웹앱으로 묶어 둔 최소 제품입니다.
          </p>
          <div class="bullet-stack">
            <div class="bullet"><span>1</span><div>강의는 정적인 슬라이드가 아니라 Scene 객체가 순차적으로 써 내려가는 칠판으로 동작합니다.</div></div>
            <div class="bullet"><span>2</span><div>학생 질문이 들어오면 현재 판서를 지우고 보충 설명 Scene으로 잠시 전환한 뒤 다시 본 강의로 돌아갑니다.</div></div>
            <div class="bullet"><span>3</span><div>문제는 종이에 풀고, 컴퓨터에는 핵심 단계만 입력해서 오답 원인과 회복 계획을 받습니다.</div></div>
          </div>
        </div>
        <aside class="hero-aside">
          <div class="mini-tape">
            <strong>오늘 데모 단원</strong>
            <p class="muted">미분 · 접선의 방정식</p>
          </div>
          <div class="mini-tape">
            <strong>AI 역할</strong>
            <p class="muted">AI Professor / AI TA / AI Coach</p>
          </div>
          <div class="mini-tape">
            <strong>현재 목표</strong>
            <p class="muted">오늘 한 문제를 정확하게 푸는 루틴 완성</p>
          </div>
        </aside>
      </article>

      <section class="two-up">
        <article class="panel">
          <h3 class="section-title">1. 목표 설정</h3>
          <p class="muted">데모용 기본값이 들어가 있지만, 실제로 값을 바꾸면 계획과 D-day가 함께 다시 계산됩니다.</p>
          <form id="profile-form" class="field-grid">
            <div class="field-row">
              <div class="field">
                <label for="name">이름</label>
                <input id="name" name="name" value="${escapeHtml(profile.name)}" required />
              </div>
              <div class="field">
                <label for="examDate">시험일</label>
                <input id="examDate" name="examDate" type="date" value="${escapeHtml(profile.examDate)}" required />
              </div>
            </div>
            <div class="field-row">
              <div class="field">
                <label for="targetScore">목표 점수</label>
                <input id="targetScore" name="targetScore" type="number" min="0" max="100" value="${escapeHtml(String(profile.targetScore))}" required />
              </div>
              <div class="field">
                <label for="dailyMinutes">하루 공부 가능 시간(분)</label>
                <input id="dailyMinutes" name="dailyMinutes" type="number" min="30" max="600" value="${escapeHtml(String(profile.dailyMinutes))}" required />
              </div>
            </div>
            <div class="field">
              <label for="studyMood">학습 톤</label>
              <select id="studyMood" name="studyMood">
                ${["실전 위주", "기본기 재정비", "짧고 압축된 설명", "천천히 반복"]
                  .map(
                    (mood) => `
                    <option ${profile.studyMood === mood ? "selected" : ""}>${mood}</option>
                  `,
                  )
                  .join("")}
              </select>
            </div>
            <div class="field">
              <label for="weakUnits">약한 단원</label>
              <input id="weakUnits" name="weakUnits" value="${escapeHtml(profile.weakUnits.join(", "))}" />
              <p class="helper">쉼표로 구분해 입력하세요. 예: 미분, 접선, 극값</p>
            </div>
            <div class="button-row">
              <button class="button primary" type="submit">목표 저장하고 진단 보기</button>
              <button class="button secondary" type="button" id="go-dashboard">현재 상태로 대시보드 보기</button>
            </div>
          </form>
        </article>

        <article class="panel">
          <h3 class="section-title">2. 미니 진단</h3>
          <p class="muted">3문항만으로 접선 루프에 필요한 핵심 상태를 빠르게 추정합니다.</p>
          <form id="diagnostic-form" class="question-list">
            ${state.bootstrap.diagnosticQuestions
              .map(
                (question) => `
                  <article class="question-card">
                    <h4>${escapeHtml(question.prompt)}</h4>
                    <div class="option-list">
                      ${question.options
                        .map(
                          (option, index) => `
                            <label class="option">
                              <input type="radio" name="${question.id}" value="${index}" />
                              <span>${escapeHtml(option)}</span>
                            </label>
                          `,
                        )
                        .join("")}
                    </div>
                  </article>
                `,
              )
              .join("")}
            <div class="button-row">
              <button class="button primary" type="submit">진단 제출하고 계획 생성</button>
            </div>
          </form>
          ${
            diagnostic
              ? `
                <div class="diagnostic-summary">
                  <h4>최근 진단 결과</h4>
                  <p><strong>${escapeHtml(String(diagnostic.score))}점</strong> · ${escapeHtml(diagnostic.summary)}</p>
                  <p class="helper">추천 트랙: ${escapeHtml(diagnostic.recommendedTrack)}</p>
                </div>
              `
              : ""
          }
        </article>
      </section>
    </section>
  `;

  document.getElementById("profile-form").addEventListener("submit", submitProfile);
  document.getElementById("diagnostic-form").addEventListener("submit", submitDiagnostic);
  document.getElementById("go-dashboard").addEventListener("click", () => navigate("dashboard"));
}

async function submitProfile(event) {
  event.preventDefault();
  const form = new FormData(event.currentTarget);
  const payload = {
    name: form.get("name"),
    examDate: form.get("examDate"),
    targetScore: Number(form.get("targetScore")),
    dailyMinutes: Number(form.get("dailyMinutes")),
    studyMood: form.get("studyMood"),
    weakUnits: String(form.get("weakUnits") || "")
      .split(",")
      .map((item) => item.trim())
      .filter(Boolean),
  };

  const response = await api.post("/api/profile", payload);
  state.bootstrap.profile = response.profile;
  state.dashboard = response.dashboard;
  toast("목표가 저장됐습니다. 진단을 제출하면 첫 7일 계획이 보강됩니다.");
  renderWelcome();
}

async function submitDiagnostic(event) {
  event.preventDefault();
  const form = new FormData(event.currentTarget);
  const answers = {};
  state.bootstrap.diagnosticQuestions.forEach((question) => {
    const value = form.get(question.id);
    if (value !== null) {
      answers[question.id] = Number(value);
    }
  });
  const result = await api.post("/api/diagnostic/submit", { answers });
  state.diagnosticResult = result;
  state.dashboard = result.dashboard;
  toast("진단이 반영됐습니다. 대시보드에서 오늘의 강의를 바로 시작할 수 있습니다.");
  navigate("dashboard");
}

function renderDashboard() {
  const dashboard = state.dashboard || state.bootstrap.dashboard;
  const stats = dashboard.stats;

  app.innerHTML = `
    <section class="page">
      <article class="panel">
        <p class="eyebrow">AI Coach</p>
        <h2 class="section-title">${escapeHtml(dashboard.headline)}</h2>
        <p class="muted">${escapeHtml(dashboard.coachMessage)}</p>
      </article>

      <section class="stat-grid">
        <article class="stat-card"><span>수능 D-day</span><strong>${formatDday(stats.daysLeft)}</strong></article>
        <article class="stat-card"><span>목표 점수</span><strong>${escapeHtml(String(stats.targetScore))}</strong></article>
        <article class="stat-card"><span>오늘 목표 시간</span><strong>${escapeHtml(String(stats.todayMinutes))}분</strong></article>
        <article class="stat-card"><span>현재 준비도</span><strong>${escapeHtml(String(stats.readiness))}</strong></article>
      </section>

      <section class="dashboard-grid">
        <div class="stack">
          <article class="panel">
            <div class="split-actions">
              <div>
                <p class="eyebrow">Today Plan</p>
                <h3 class="section-title">${escapeHtml(dashboard.todayPlan.theme)}</h3>
                <p class="muted">${escapeHtml(dashboard.todayPlan.focus)}</p>
              </div>
              <div class="button-row">
                <button class="button primary" id="start-lesson">오늘 수업 시작</button>
                <button class="button secondary" id="go-practice">문제 바로 풀기</button>
              </div>
            </div>
            <div class="task-list">
              ${dashboard.todayPlan.tasks.map(renderTaskCard).join("")}
            </div>
          </article>

          <article class="panel">
            <p class="eyebrow">Mastery Map</p>
            <h3 class="section-title">단원별 상태</h3>
            <div class="mastery-list">
              ${dashboard.mastery
                .map(
                  (item) => `
                    <article class="mastery-card">
                      <header>
                        <div>
                          <h4>${escapeHtml(item.title)}</h4>
                          <p class="muted">${escapeHtml(scoreToLabel(item.score))}</p>
                        </div>
                        <span class="risk-pill">${escapeHtml(item.risk)} · ${escapeHtml(item.trend)}</span>
                      </header>
                      <div class="mastery-bar"><span class="mastery-fill" style="width:${item.score}%"></span></div>
                    </article>
                  `,
                )
                .join("")}
            </div>
          </article>
        </div>

        <div class="stack">
          <article class="panel">
            <p class="eyebrow">Weekly Plan</p>
            <h3 class="section-title">7일 재계산 흐름</h3>
            <div class="week-list">
              ${dashboard.weeklyPlan
                .map(
                  (day) => `
                    <article class="week-card">
                      <header>
                        <div>
                          <h4>${escapeHtml(day.label)} · ${escapeHtml(day.theme)}</h4>
                          <p class="muted">${escapeHtml(day.focus)}</p>
                        </div>
                        <span class="chip">${escapeHtml(String(day.minutesTarget))}분</span>
                      </header>
                      <div class="task-list">
                        ${day.tasks
                          .map(
                            (task) => `
                              <div class="task-card">
                                <header>
                                  <div>
                                    <h4>${escapeHtml(task.title)}</h4>
                                    <p class="muted">${escapeHtml(task.type)} · ${escapeHtml(String(task.minutes))}분</p>
                                  </div>
                                  <span class="task-status ${escapeHtml(task.status)}">${escapeHtml(task.status)}</span>
                                </header>
                              </div>
                            `,
                          )
                          .join("")}
                      </div>
                    </article>
                  `,
                )
                .join("")}
            </div>
          </article>

          <article class="panel">
            <p class="eyebrow">Risk Alerts</p>
            <h3 class="section-title">오늘 놓치면 안 되는 포인트</h3>
            <div class="alert-list">
              ${dashboard.alerts
                .map(
                  (alert) => `
                    <article class="review-card">
                      <p>${escapeHtml(alert)}</p>
                    </article>
                  `,
                )
                .join("")}
            </div>
            <div class="button-row">
              <button class="button ghost" id="go-review">최근 풀이 복습</button>
            </div>
          </article>
        </div>
      </section>
    </section>
  `;

  document.getElementById("start-lesson").addEventListener("click", startLesson);
  document.getElementById("go-practice").addEventListener("click", () => navigate("practice"));
  document.getElementById("go-review").addEventListener("click", async () => {
    state.review = await api.get("/api/review/latest");
    navigate("review");
  });
}

function renderTaskCard(task) {
  return `
    <article class="task-card">
      <header>
        <div>
          <h4>${escapeHtml(task.title)}</h4>
          <p class="muted">${escapeHtml(task.type)} · ${escapeHtml(String(task.minutes))}분</p>
        </div>
        <span class="task-status ${escapeHtml(task.status)}">${escapeHtml(task.status)}</span>
      </header>
    </article>
  `;
}

async function startLesson() {
  await ensureLessonLoaded();
  state.lessonPlayback.sceneIndex = 0;
  state.lessonPlayback.interrupt = null;
  navigate("lesson");
}

async function ensureLessonLoaded() {
  if (!state.lesson) {
    state.lesson = await api.get("/api/lesson/session");
  }
}

function renderLessonShell() {
  if (!state.lesson) {
    app.innerHTML = `
      <section class="loading-state">
        <div class="spinner"></div>
        <p>강의 장면을 준비 중입니다.</p>
      </section>
    `;
    ensureLessonLoaded().then(() => renderRoute());
    return;
  }

  const activeScene = getActiveScene();
  const outlineHtml = state.lesson.outline
    .map((scene, index) => {
      const isActive = !state.lessonPlayback.interrupt && index === state.lessonPlayback.sceneIndex;
      return `
        <div class="outline-item ${isActive ? "active" : ""}">
          <strong>${index + 1}. ${escapeHtml(scene.title)}</strong>
        </div>
      `;
    })
    .join("");

  app.innerHTML = `
    <section class="page lesson-page">
      <aside class="panel lesson-sidebar">
        <p class="eyebrow">AI Professor</p>
        <h2 class="section-title">${escapeHtml(state.lesson.unitTitle)}</h2>
        <p class="muted">강의 장면은 전부 Scene 객체로 내려갑니다. 질문이 들어오면 별도 Scene으로 잠시 분기합니다.</p>
        <div class="progress-bar">
          <span style="width:${sceneProgressPercent()}%"></span>
        </div>
        <div class="outline-list">${outlineHtml}</div>
      </aside>

      <article class="panel lesson-main">
        <div class="lesson-stage">
          <div class="lesson-toolbar">
            <div>
              <p class="eyebrow">${state.lessonPlayback.interrupt ? "Question Interrupt" : "Lecture Scene"}</p>
              <h3 class="lesson-heading">${escapeHtml(activeScene.title)}</h3>
            </div>
            <div class="button-row">
              <button class="button secondary" id="prev-scene">이전 장면</button>
              <button class="button primary" id="next-scene">${state.lessonPlayback.interrupt ? "질문 장면 다시 보기" : "다음 장면"}</button>
              <button class="button ghost" id="go-practice-from-lesson">문제 풀기</button>
            </div>
          </div>
          <div class="board" id="board"></div>
        </div>
      </article>

      <aside class="panel lesson-sidepanel">
        <div class="stack">
          <section class="narration-card">
            <p class="eyebrow">교수 멘트</p>
            <p id="teacher-copy">${escapeHtml(activeScene.narration)}</p>
          </section>

          <section class="question-box">
            <p class="eyebrow">학생 질문</p>
            <p class="muted">질문을 보내면 현재 판서를 비우고, 질문에 대한 설명 Scene을 먼저 재생합니다.</p>
            <div class="prompt-list">
              ${state.lesson.questionStarters
                .map(
                  (starter) => `
                    <button class="prompt-chip" data-prompt="${escapeHtmlAttribute(starter)}">${escapeHtml(starter)}</button>
                  `,
                )
                .join("")}
            </div>
            <form id="question-form" class="field-grid" style="margin-top:12px;">
              <div class="field">
                <label for="question-text">질문 입력</label>
                <textarea id="question-text" name="question" placeholder="예: 왜 접선 기울기가 도함수값이 되는 거야?"></textarea>
              </div>
              <div class="button-row">
                <button class="button primary" type="submit">질문 보내기</button>
                ${
                  state.lessonPlayback.interrupt
                    ? `<button class="button secondary" type="button" id="resume-lesson">${escapeHtml(activeScene.resumeLabel || "강의로 돌아가기")}</button>`
                    : ""
                }
              </div>
            </form>
          </section>

          <section class="question-box">
            <p class="eyebrow">오늘 풀 문제</p>
            <p><strong>${escapeHtml(state.lesson.practiceProblem.title)}</strong></p>
            <p class="muted">${escapeHtml(state.lesson.practiceProblem.coachHint)}</p>
          </section>
        </div>
      </aside>
    </section>
  `;

  document.getElementById("prev-scene").addEventListener("click", goPrevScene);
  document.getElementById("next-scene").addEventListener("click", replayOrAdvanceScene);
  document.getElementById("go-practice-from-lesson").addEventListener("click", () => navigate("practice"));
  document.getElementById("question-form").addEventListener("submit", submitQuestion);

  app.querySelectorAll("[data-prompt]").forEach((button) => {
    button.addEventListener("click", () => {
      document.getElementById("question-text").value = button.dataset.prompt || "";
    });
  });

  const resumeButton = document.getElementById("resume-lesson");
  if (resumeButton) {
    resumeButton.addEventListener("click", resumeLesson);
  }

  playScene(activeScene);
}

function getActiveScene() {
  if (state.lessonPlayback.interrupt) {
    return state.lessonPlayback.interrupt.scene;
  }
  return state.lesson.scenes[state.lessonPlayback.sceneIndex];
}

function sceneProgressPercent() {
  if (!state.lesson || !state.lesson.scenes.length) {
    return 0;
  }
  return Math.round(((state.lessonPlayback.sceneIndex + 1) / state.lesson.scenes.length) * 100);
}

function clearLessonTimers() {
  state.lessonPlayback.timers.forEach((timer) => window.clearTimeout(timer));
  state.lessonPlayback.timers = [];
}

function playScene(scene) {
  clearLessonTimers();
  const board = document.getElementById("board");
  const teacherCopy = document.getElementById("teacher-copy");
  if (!board || !teacherCopy) {
    return;
  }
  board.innerHTML = "";
  teacherCopy.textContent = scene.narration;
  scene.objects.forEach((object) => {
    const delay = Number(object.delayMs || 0);
    const timer = window.setTimeout(() => {
      board.appendChild(renderBoardObject(object));
    }, delay);
    state.lessonPlayback.timers.push(timer);
  });
}

function renderBoardObject(object) {
  const node = document.createElement("div");
  node.className = `board-object board-${object.type}`;
  if (object.x !== undefined) node.style.left = `${object.x}%`;
  if (object.y !== undefined) node.style.top = `${object.y}%`;
  if (object.w !== undefined) node.style.width = `${object.w}%`;
  if (object.h !== undefined) node.style.height = `${object.h}%`;

  switch (object.type) {
    case "graph":
      node.innerHTML = renderGraphSvg(object.graph);
      break;
    case "arrow":
      node.innerHTML = "";
      break;
    default:
      node.textContent = object.content;
      break;
  }
  return node;
}

function renderGraphSvg(graph) {
  const width = 420;
  const height = 280;
  const padding = 24;
  const toSvgX = (value) =>
    padding + ((value - graph.xMin) / (graph.xMax - graph.xMin)) * (width - padding * 2);
  const toSvgY = (value) =>
    height - padding - ((value - graph.yMin) / (graph.yMax - graph.yMin)) * (height - padding * 2);
  const xAxis = toSvgY(0);
  const yAxis = toSvgX(0);

  const curveMarkup = graph.curves
    .map((curve) => {
      const points = curve.points.map((point) => `${toSvgX(point[0])},${toSvgY(point[1])}`).join(" ");
      return `<polyline fill="none" stroke="${curve.color}" stroke-width="3.4" stroke-linecap="round" stroke-linejoin="round" points="${points}" />`;
    })
    .join("");

  const marksMarkup = (graph.marks || [])
    .map((mark) => {
      const x = toSvgX(mark.x);
      const y = toSvgY(mark.y);
      return `
        <circle cx="${x}" cy="${y}" r="5.5" fill="#ffd78d" />
        <text x="${x + 8}" y="${y - 8}" fill="#f7ebbe" font-size="14" font-family="sans-serif">${escapeHtml(mark.label)}</text>
      `;
    })
    .join("");

  return `
    <svg viewBox="0 0 ${width} ${height}" aria-hidden="true">
      <rect width="${width}" height="${height}" fill="transparent"></rect>
      <line x1="${padding}" y1="${xAxis}" x2="${width - padding}" y2="${xAxis}" stroke="rgba(247,235,190,0.35)" stroke-width="1.2"></line>
      <line x1="${yAxis}" y1="${padding}" x2="${yAxis}" y2="${height - padding}" stroke="rgba(247,235,190,0.35)" stroke-width="1.2"></line>
      ${curveMarkup}
      ${marksMarkup}
    </svg>
  `;
}

function goPrevScene() {
  if (state.lessonPlayback.interrupt) {
    renderLessonShell();
    return;
  }
  state.lessonPlayback.sceneIndex = Math.max(0, state.lessonPlayback.sceneIndex - 1);
  renderLessonShell();
}

function replayOrAdvanceScene() {
  if (state.lessonPlayback.interrupt) {
    renderLessonShell();
    return;
  }
  state.lessonPlayback.sceneIndex = Math.min(
    state.lesson.scenes.length - 1,
    state.lessonPlayback.sceneIndex + 1,
  );
  renderLessonShell();
}

async function submitQuestion(event) {
  event.preventDefault();
  const questionField = document.getElementById("question-text");
  const question = questionField.value.trim();
  if (!question) {
    toast("질문을 입력하면 보충 판서로 전환됩니다.");
    return;
  }

  const response = await api.post("/api/lesson/question", { question });
  state.lessonPlayback.interrupt = {
    scene: response.scene,
    resumeIndex: state.lessonPlayback.sceneIndex,
  };
  renderLessonShell();
}

function resumeLesson() {
  state.lessonPlayback.interrupt = null;
  renderLessonShell();
}

function renderPractice() {
  if (!state.lesson) {
    app.innerHTML = `
      <section class="loading-state">
        <div class="spinner"></div>
        <p>문제 데이터를 준비 중입니다.</p>
      </section>
    `;
    ensureLessonLoaded().then(() => renderRoute());
    return;
  }
  const problem = state.lesson ? state.lesson.practiceProblem : state.bootstrap.lessonPreview;
  const currentAttempt = state.attempt;
  app.innerHTML = `
    <section class="page practice-layout">
      <article class="panel problem-panel">
        <p class="eyebrow">AI TA</p>
        <h2 class="practice-title">종이에 풀고 핵심 단계만 입력하세요</h2>
        <p class="muted">P0에서는 자유필기 OCR 대신 구조화된 단계 입력으로 풀이 과정을 봅니다.</p>
        <div class="problem-statement">${escapeHtml(problem.statement || "문제 데이터를 준비 중입니다.")}</div>
        <div class="panel" style="margin-top:16px; padding:16px;">
          <p class="eyebrow">권장 루틴</p>
          <div class="outline-pill-list">
            ${(state.lesson?.practiceProblem.expectedOutline || [])
              .map((item) => `<span class="chip">${escapeHtml(item)}</span>`)
              .join("")}
          </div>
          <p class="helper" style="margin-top:12px;">종이에는 자유롭게 풀고, 아래 칸에는 핵심 식만 적어도 충분합니다.</p>
        </div>
      </article>

      <article class="panel response-panel">
        <form id="practice-form" class="input-stack">
          <div class="input-card">
            <label for="stepOne"><strong>Step 1. 도함수</strong></label>
            <textarea id="stepOne" name="stepOne" placeholder="예: f'(x) = 2x - 4">${escapeHtml(currentAttempt?.submitted?.stepOne || "")}</textarea>
          </div>
          <div class="input-card">
            <label for="stepTwo"><strong>Step 2. 기울기</strong></label>
            <textarea id="stepTwo" name="stepTwo" placeholder="예: f'(1) = -2">${escapeHtml(currentAttempt?.submitted?.stepTwo || "")}</textarea>
          </div>
          <div class="input-card">
            <label for="stepThree"><strong>Step 3. 접점</strong></label>
            <textarea id="stepThree" name="stepThree" placeholder="예: f(1) = 0, 접점은 (1, 0)">${escapeHtml(currentAttempt?.submitted?.stepThree || "")}</textarea>
          </div>
          <div class="input-card">
            <label for="finalAnswer"><strong>Final Answer</strong></label>
            <input id="finalAnswer" name="finalAnswer" placeholder="예: y = -2x + 2" value="${escapeHtml(currentAttempt?.submitted?.finalAnswer || "")}" />
          </div>
          <div class="button-row">
            <button class="button primary" type="submit">AI TA에게 제출</button>
            <button class="button secondary" type="button" id="back-lesson">강의 다시 보기</button>
          </div>
        </form>
      </article>
    </section>
  `;

  document.getElementById("practice-form").addEventListener("submit", submitPractice);
  document.getElementById("back-lesson").addEventListener("click", () => navigate("lesson"));
}

async function submitPractice(event) {
  event.preventDefault();
  const form = new FormData(event.currentTarget);
  const payload = Object.fromEntries(form.entries());
  const response = await api.post("/api/practice/submit", payload);
  state.attempt = response.attempt;
  state.review = response.review;
  state.dashboard = response.dashboard;
  toast("풀이 분석이 끝났습니다. 어떤 단계가 흔들렸는지 복습 화면에서 바로 확인하세요.");
  navigate("review");
}

function renderReview() {
  const review = state.review;
  if (!review || review.empty) {
    app.innerHTML = `
      <section class="empty-card">
        <h2>${escapeHtml(review?.headline || "복습 데이터가 없습니다.")}</h2>
        <p class="muted">${escapeHtml(review?.message || "문제를 풀면 이곳에 내 풀이와 권장 루틴의 차이가 정리됩니다.")}</p>
        <div class="button-row" style="justify-content:center; margin-top:14px;">
          <button class="button primary" id="retry-practice-empty">문제 풀러 가기</button>
        </div>
      </section>
    `;
    document.getElementById("retry-practice-empty").addEventListener("click", () => navigate("practice"));
    return;
  }

  app.innerHTML = `
    <section class="page review-layout">
      <article class="panel">
        <p class="eyebrow">AI Coach Review</p>
        <h2 class="review-title">${escapeHtml(review.headline)}</h2>
        <p class="muted">${escapeHtml(review.summary)}</p>

        <div class="result-banner ${review.solved ? "success" : "retry"}">
          ${review.solved ? "풀이 루프가 거의 완성됐습니다. 같은 구조를 내일 한 번 더 자동화하세요." : "오답 회복 루틴이 열렸습니다. 오늘은 부호와 접점 계산을 다시 묶어야 합니다."}
        </div>

        <div class="review-list">
          ${review.goodSteps
            .map(
              (step) => `
                <article class="feedback-card good">
                  <h4>${escapeHtml(step.label)}</h4>
                  <p>${escapeHtml(step.reason)}</p>
                  <span class="review-tag">expected: ${escapeHtml(step.expected)}</span>
                </article>
              `,
            )
            .join("")}
          ${review.wrongSteps
            .map(
              (step) => `
                <article class="feedback-card bad">
                  <h4>${escapeHtml(step.label)}</h4>
                  <p>${escapeHtml(step.reason)}</p>
                  <span class="review-tag">expected: ${escapeHtml(step.expected)}</span>
                </article>
              `,
            )
            .join("")}
        </div>
      </article>

      <article class="panel">
        <p class="eyebrow">Recovery Plan</p>
        <h2 class="review-title">내일 계획이 바로 다시 계산됩니다</h2>
        <div class="review-list">
          <article class="review-card">
            <header>
              <div>
                <h4>${escapeHtml(review.tomorrowPlan.label)} · ${escapeHtml(review.tomorrowPlan.theme)}</h4>
                <p class="muted">${escapeHtml(review.tomorrowPlan.focus)}</p>
              </div>
              <span class="chip">${escapeHtml(String(review.tomorrowPlan.minutesTarget))}분</span>
            </header>
          </article>
          <article class="review-card">
            <h4>추천 회복 세트</h4>
            ${review.retrySet.map((item) => `<p>${escapeHtml(item)}</p>`).join("")}
          </article>
        </div>
        <div class="button-row">
          <button class="button primary" id="review-dashboard">대시보드로 돌아가기</button>
          <button class="button secondary" id="review-practice">같은 문제 다시 풀기</button>
          <button class="button ghost" id="review-lesson">강의 다시 보기</button>
        </div>
      </article>
    </section>
  `;

  document.getElementById("review-dashboard").addEventListener("click", () => navigate("dashboard"));
  document.getElementById("review-practice").addEventListener("click", () => navigate("practice"));
  document.getElementById("review-lesson").addEventListener("click", () => navigate("lesson"));
}

function toast(message) {
  const existing = document.querySelector(".toast");
  if (existing) existing.remove();
  const node = document.createElement("div");
  node.className = "toast";
  node.textContent = message;
  node.style.position = "fixed";
  node.style.right = "22px";
  node.style.bottom = "22px";
  node.style.zIndex = "9999";
  document.body.appendChild(node);
  window.setTimeout(() => node.remove(), 2800);
}

function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function escapeHtmlAttribute(value) {
  return escapeHtml(value).replace(/"/g, "&quot;");
}

function formatDday(daysLeft) {
  if (daysLeft === 0) return "D-Day";
  if (daysLeft > 0) return `D-${daysLeft}`;
  return `D+${Math.abs(daysLeft)}`;
}

function scoreToLabel(score) {
  if (score >= 85) return "안정권";
  if (score >= 70) return "상승권";
  if (score >= 55) return "교정 필요";
  return "기초 재정비";
}
