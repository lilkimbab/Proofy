"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { getSupabaseBrowserClient } from "@/lib/supabaseBrowser";

const sampleDocs = [
  { id: "sample-1", title: "미적분 - 미분의 개념", subject: "수학", createdAt: "2026.05.04", progress: 60, status: "학습 가능", color: "blue", sections: [] },
  { id: "sample-2", title: "확률과 통계 - 조건부 확률", subject: "수학", createdAt: "2026.05.03", progress: 40, status: "학습 가능", color: "violet", sections: [] },
  { id: "sample-3", title: "수학 II - 적분", subject: "수학", createdAt: "2026.05.02", progress: 20, status: "분석 중", color: "purple", sections: [] }
];

const menuItems = [
  ["home", "홈", "⌂"],
  ["documents", "내 문서", "□"],
  ["roadmap", "학습 로드맵", "◇"],
  ["questions", "질문 기록", "◌"],
  ["quiz", "문제 풀이", "✎"],
  ["analytics", "학습 분석", "▥"],
  ["upload", "자료 업로드", "⇧"],
  ["settings", "설정", "⚙"]
];

export default function Home({ initialPage = "login" }) {
  const [page, setPage] = useState(initialPage);
  const [documents, setDocuments] = useState(sampleDocs);
  const [selectedDocId, setSelectedDocId] = useState("sample-1");
  const [questions, setQuestions] = useState([]);
  const [annotations, setAnnotations] = useState([]);
  const [authReady, setAuthReady] = useState(false);
  const [currentUser, setCurrentUser] = useState(null);
  const [authToken, setAuthToken] = useState("");
  const [authMessage, setAuthMessage] = useState("");
  const [uploadState, setUploadState] = useState({ loading: false, message: "" });
  const [quizSession, setQuizSession] = useState({ quizzes: [], currentIndex: 0, loading: false, message: "" });
  const [feedback, setFeedback] = useState(null);
  const [roadmap, setRoadmap] = useState(null);
  const [analytics, setAnalytics] = useState(null);

  const selectedDoc = useMemo(
    () => documents.find((doc) => doc.id === selectedDocId) || documents[0],
    [documents, selectedDocId]
  );

  const apiFetch = useCallback((url, options = {}) => {
    const headers = new Headers(options.headers || {});
    if (authToken) headers.set("Authorization", `Bearer ${authToken}`);
    return fetch(url, { ...options, headers });
  }, [authToken]);

  useEffect(() => {
    let mounted = true;
    let subscription = null;

    async function initializeAuth() {
      try {
        const supabase = await getSupabaseBrowserClient();
        const { data } = await supabase.auth.getSession();
        if (!mounted) return;

        const session = data?.session;
        setCurrentUser(session?.user || null);
        setAuthToken(session?.access_token || "");
        setPage(session?.user ? (initialPage === "login" ? "home" : initialPage) : "login");
        setAuthReady(true);

        const listener = supabase.auth.onAuthStateChange((event, nextSession) => {
          setCurrentUser(nextSession?.user || null);
          setAuthToken(nextSession?.access_token || "");
          if (event === "SIGNED_IN") setPage("home");
          if (event === "SIGNED_OUT") setPage("login");
        });
        subscription = listener.data.subscription;
      } catch (error) {
        setAuthMessage(error.message || "로그인 설정을 불러오지 못했습니다.");
        setAuthReady(true);
      }
    }

    initializeAuth();
    return () => {
      mounted = false;
      subscription?.unsubscribe?.();
    };
  }, [initialPage]);

  useEffect(() => {
    if (!authReady || page === "login") return;
    refreshDocuments();
    refreshQuestions();
    refreshAnnotations(selectedDocId);
    refreshRoadmap();
    refreshAnalytics();
  }, [authReady, authToken, page]);

  async function refreshDocuments() {
    const response = await apiFetch("/api/documents");
    if (!response.ok) return;
    const data = await response.json();
    if (data.documents?.length) {
      setDocuments([...data.documents, ...sampleDocs]);
      setSelectedDocId(data.documents[0].id);
      refreshAnnotations(data.documents[0].id);
    }
  }

  async function refreshQuestions() {
    const response = await apiFetch("/api/questions");
    if (!response.ok) return;
    const data = await response.json();
    setQuestions(data.questions || []);
  }

  async function refreshAnnotations(documentId = selectedDocId) {
    if (!documentId) return;
    const response = await apiFetch(`/api/annotations?documentId=${encodeURIComponent(documentId)}`);
    if (!response.ok) return;
    const data = await response.json();
    setAnnotations(data.annotations || []);
  }

  async function loadDocument(documentId) {
    setSelectedDocId(documentId);
    const response = await apiFetch(`/api/documents/${encodeURIComponent(documentId)}`);
    if (response.ok) {
      const data = await response.json();
      if (data.document) {
        setDocuments((current) => current.map((doc) => doc.id === documentId ? data.document : doc));
      }
    }
    await refreshAnnotations(documentId);
    setPage("learn");
  }

  async function refreshRoadmap() {
    const response = await apiFetch("/api/roadmap");
    if (!response.ok) return;
    const data = await response.json();
    setRoadmap(data.roadmap);
  }

  async function refreshAnalytics() {
    const response = await apiFetch("/api/analytics");
    if (!response.ok) return;
    const data = await response.json();
    setAnalytics(data.analytics);
  }

  async function handleUpload(event) {
    event.preventDefault();
    const form = event.currentTarget;
    const formData = new FormData(form);
    setUploadState({ loading: true, message: "자료를 업로드하고 섹션별 설명을 생성하는 중입니다." });
    const response = await apiFetch("/api/documents", { method: "POST", body: formData });
    const data = await response.json();
    if (!response.ok) {
      setUploadState({ loading: false, message: data.error || "업로드에 실패했습니다." });
      return;
    }
    await refreshDocuments();
    setSelectedDocId(data.document.id);
    setDocuments((current) => current.map((doc) => doc.id === data.document.id ? data.document : doc));
    await refreshAnnotations(data.document.id);
    setUploadState({ loading: false, message: "분석 완료: 섹션별 설명과 학습 흐름이 준비되었습니다." });
    setPage("learn");
    form.reset();
  }

  async function handleLogout() {
    const supabase = await getSupabaseBrowserClient();
    await supabase.auth.signOut();
    setDocuments(sampleDocs);
    setQuestions([]);
    setAnnotations([]);
    setSelectedDocId("sample-1");
  }

  if (page === "login") {
    return <LoginScreen authReady={authReady} authMessage={authMessage} setAuthMessage={setAuthMessage} setPage={setPage} />;
  }

  return (
    <div className="app-shell">
      <Sidebar page={page} setPage={setPage} />
      <main className="main">
        <Header title={titleForPage(page)} subtitle={subtitleForPage(page)} user={currentUser} onLogout={handleLogout} setPage={setPage} />
        {page === "home" && <Dashboard documents={documents} setPage={setPage} selectDocument={loadDocument} />}
        {page === "documents" && <Documents documents={documents} setPage={setPage} selectDocument={loadDocument} />}
        {page === "upload" && <Upload onUpload={handleUpload} uploadState={uploadState} />}
        {page === "learn" && <Learn doc={selectedDoc} apiFetch={apiFetch} annotations={annotations} refreshAnnotations={refreshAnnotations} questions={questions} refreshQuestions={refreshQuestions} setDocuments={setDocuments} setPage={setPage} />}
        {page === "ask" && <Ask doc={selectedDoc} apiFetch={apiFetch} refreshQuestions={refreshQuestions} />}
        {page === "questions" && <Questions questions={questions} setPage={setPage} />}
        {page === "roadmap" && <Roadmap roadmap={roadmap} setPage={setPage} />}
        {page === "quiz" && <Quiz doc={selectedDoc} apiFetch={apiFetch} quizSession={quizSession} setQuizSession={setQuizSession} setFeedback={setFeedback} setPage={setPage} />}
        {page === "feedback" && <Feedback feedback={feedback} setPage={setPage} />}
        {page === "analytics" && <Analytics analytics={analytics} />}
        {page === "settings" && <Settings />}
      </main>
      <MobileNav page={page} setPage={setPage} />
    </div>
  );
}

function titleForPage(page) {
  return {
    home: "홈 대시보드",
    documents: "내 문서 목록",
    upload: "자료 업로드",
    learn: "문서 학습 화면",
    ask: "질문하기",
    questions: "질문 기록",
    roadmap: "학습 로드맵",
    quiz: "문제 풀이",
    feedback: "피드백",
    analytics: "학습 분석",
    settings: "설정"
  }[page] || "홈 대시보드";
}

function subtitleForPage(page) {
  return {
    upload: "자료를 섹션별로 나누고, 각 섹션 설명을 생성해 컨텍스트 한계를 피합니다.",
    ask: "전체 자료가 아니라 관련 chunk를 찾아 답변합니다.",
    learn: "섹션별 설명을 하나씩 보거나 전체 학습 흐름으로 확인하세요."
  }[page] || "학습 목표와 진행 상황을 한눈에 확인하세요.";
}

function Sidebar({ page, setPage }) {
  return (
    <aside className="sidebar">
      <div className="brand">
        <div className="brand-mark">AI</div>
        <div><strong>AI 과외 선생님</strong><span>Personal Study Agent</span></div>
      </div>
      <nav className="nav">
        {menuItems.map(([id, label, icon], index) => (
          <button key={id} className={`nav-item ${page === id ? "active" : ""} ${index === 6 ? "spaced" : ""}`} onClick={() => setPage(id)}>
            <span className="line-icon">{icon}</span><span>{label}</span>
          </button>
        ))}
      </nav>
    </aside>
  );
}

function MobileNav({ page, setPage }) {
  return (
    <nav className="mobile-nav">
      {menuItems.slice(0, 5).map(([id, label, icon]) => (
        <button key={id} className={page === id ? "active" : ""} onClick={() => setPage(id)}>
          <span>{icon}</span><span>{label.replace("학습 ", "")}</span>
        </button>
      ))}
    </nav>
  );
}

function Header({ title, subtitle, user, onLogout, setPage }) {
  const label = user?.email?.slice(0, 1).toUpperCase() || "G";
  const name = user?.email || "게스트";

  return (
    <header className="topbar">
      <div><h1>{title}</h1><p>{subtitle}</p></div>
      <div className="top-actions">
        <button className="icon-button">⌕</button>
        <button className="icon-button">○<span className="dot" /></button>
        <button className="profile-button" type="button" onClick={() => setPage("settings")}><span>{label}</span>{name}</button>
        <button className="text-button" type="button" onClick={onLogout}>로그아웃</button>
      </div>
    </header>
  );
}

function LoginScreen({ authReady, authMessage, setAuthMessage, setPage }) {
  const [mode, setMode] = useState("signin");
  const [form, setForm] = useState({ email: "", password: "", name: "" });
  const [loading, setLoading] = useState(false);

  async function submitAuth(event) {
    event.preventDefault();
    setLoading(true);
    setAuthMessage("");

    try {
      const supabase = await getSupabaseBrowserClient();
      const payload = {
        email: form.email.trim(),
        password: form.password
      };
      const result = mode === "signup"
        ? await supabase.auth.signUp({
          ...payload,
          options: { data: { name: form.name.trim() || form.email.trim() } }
        })
        : await supabase.auth.signInWithPassword(payload);

      if (result.error) {
        setAuthMessage(result.error.message);
        return;
      }

      if (mode === "signup" && !result.data.session) {
        setAuthMessage("가입 확인 메일을 보냈습니다. 메일 인증 후 로그인하세요.");
      } else {
        setPage("home");
      }
    } catch (error) {
      setAuthMessage(error.message || "로그인 처리 중 오류가 발생했습니다.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="auth-page">
      <section className="auth-panel">
        <div className="auth-copy">
          <div className="brand">
            <div className="brand-mark">AI</div>
            <div><strong>AI 과외 선생님</strong><span>Personal Study Agent</span></div>
          </div>
          <h1>내 자료로 공부하는 개인 AI 과외 선생님</h1>
          <p>자료 업로드, 섹션별 학습, 드래그 질문, 메모 기록, 문제 풀이 피드백을 한 공간에서 이어갑니다.</p>
          <div className="auth-points">
            <span>문서 기반 학습</span>
            <span>질문/메모 기록</span>
            <span>개인별 학습 데이터</span>
          </div>
        </div>
        <form className="auth-card" onSubmit={submitAuth}>
          <div>
            <h2>{mode === "signup" ? "회원가입" : "로그인"}</h2>
            <p>{mode === "signup" ? "계정을 만들고 학습 기록을 저장하세요." : "이어서 공부할 계정으로 들어오세요."}</p>
          </div>
          {mode === "signup" && (
            <label>이름<input value={form.name} onChange={(event) => setForm({ ...form, name: event.target.value })} placeholder="지민" /></label>
          )}
          <label>이메일<input type="email" value={form.email} onChange={(event) => setForm({ ...form, email: event.target.value })} placeholder="student@example.com" required /></label>
          <label>비밀번호<input type="password" value={form.password} onChange={(event) => setForm({ ...form, password: event.target.value })} placeholder="6자 이상" minLength={6} required /></label>
          <button className="primary-button" disabled={loading || !authReady}>{loading ? "처리 중..." : mode === "signup" ? "회원가입" : "로그인"}</button>
          <button className="secondary-button" type="button" onClick={() => setMode(mode === "signup" ? "signin" : "signup")}>
            {mode === "signup" ? "이미 계정이 있어요" : "새 계정 만들기"}
          </button>
          <button className="text-button" type="button" onClick={() => setPage("home")}>게스트로 둘러보기</button>
          {authMessage && <p className="status-message error">{authMessage}</p>}
        </form>
      </section>
    </main>
  );
}

function Badge({ children }) {
  const kind = { "학습 가능": "success", "분석 중": "warning", "분석 대기": "muted", "완료": "success", "진행 중": "primary", "복습 필요": "warning" }[children] || "muted";
  return <span className={`badge ${kind}`}>{children}</span>;
}

function Progress({ value }) {
  return <div className="progress"><span style={{ width: `${value}%` }} /></div>;
}

function Dashboard({ documents, setPage, selectDocument }) {
  return (
    <section className="dashboard-grid">
      <article className="card hero-card">
        <div className="card-heading"><div><h2>오늘의 학습 목표</h2><p>2/3 완료</p></div><Badge>진행 중</Badge></div>
        <ul className="goal-list"><li className="done">미적분 개념 이해하기</li><li className="done">예제 문제 5개 풀기</li><li>복습: 조건부 확률</li></ul>
        <button className="primary-button" onClick={() => setPage("learn")}>오늘 학습 시작</button>
      </article>
      <article className="card">
        <div className="card-heading"><h2>학습 현황</h2><span className="soft-label">이번 주</span></div>
        <div className="stat-row"><div><strong>12시간 30분</strong><span>학습 시간</span></div><div><strong>72%</strong><span>이해도 평균</span></div></div>
        <div className="mini-chart">{[32, 42, 54, 72, 66, 88, 46].map((v) => <span key={v} style={{ height: `${v}%` }} />)}</div>
      </article>
      <article className="card">
        <div className="card-heading"><h2>최근 학습</h2><button className="text-button" onClick={() => setPage("documents")}>전체보기</button></div>
        <div className="study-list">
          {documents.slice(0, 3).map((doc) => <button key={doc.id} className="study-item" onClick={() => selectDocument(doc.id)}><span className={`doc-dot ${doc.color || "blue"}`} /><div><strong>{doc.title}</strong><small>마지막 학습: 오늘 08:30</small><Progress value={doc.progress || 0} /></div><b>{doc.progress || 0}%</b></button>)}
        </div>
      </article>
      <article className="card ai-card"><div><h2>AI 선생님 추천</h2><p>업로드 자료를 섹션별로 학습하면 긴 자료도 안정적으로 다룰 수 있어요.</p><button className="secondary-button" onClick={() => setPage("upload")}>자료 업로드</button></div><div className="bot-illustration"><span /></div></article>
    </section>
  );
}

function Documents({ documents, setPage, selectDocument }) {
  return (
    <section className="page-section">
      <div className="section-header"><div><h2>내 문서</h2><p>업로드한 자료의 분석 상태와 섹션 수를 확인하세요.</p></div><button className="primary-button" onClick={() => setPage("upload")}>+ 새 자료 업로드</button></div>
      <div className="table-card">
        <div className="table-row table-head"><span>문서 제목</span><span>과목</span><span>업로드 날짜</span><span>상태</span><span>학습 진행률</span><span></span></div>
        {documents.map((doc) => <button key={doc.id} className="table-row" onClick={() => selectDocument(doc.id)}><span className="doc-name"><i className={doc.color || "blue"} />{doc.title}</span><span>{doc.subject || "기타"}</span><span>{formatDate(doc.createdAt)}</span><span><Badge>{doc.status || "학습 가능"}</Badge></span><span><Progress value={doc.progress || 0} /><small>{doc.sections?.length || 0}섹션</small></span><span>⋯</span></button>)}
      </div>
    </section>
  );
}

function Upload({ onUpload, uploadState }) {
  return (
    <section className="upload-layout">
      <form className="card upload-card" onSubmit={onUpload}>
        <label className="dropzone"><input name="file" type="file" accept=".txt,.md,.pdf,.docx,.pptx" required /><div className="cloud-icon">⇧</div><strong>파일을 드래그하거나 클릭하여 업로드하세요</strong><span>TXT/MD는 즉시 분석, PDF/DOCX/PPTX는 추출기 연결 대상</span></label>
        <div className="form-grid">
          <label>문서 제목<input name="title" placeholder="미적분 - 미분의 개념" required /></label>
          <label>과목<select name="subject"><option>수학</option><option>물리</option><option>화학</option><option>영어</option><option>기타</option></select></label>
          <label>학습 목표<input name="goal" placeholder="중간고사 대비 핵심 개념 정리" /></label>
          <label>시험 날짜<input name="deadline" placeholder="2026.05.20" /></label>
        </div>
        <button className="primary-button" disabled={uploadState.loading}>{uploadState.loading ? "분석 중..." : "자료 분석 시작"}</button>
        {uploadState.message && <p className="status-message">{uploadState.message}</p>}
      </form>
      <aside className="upload-side">
        <div className="card"><h2>분석 진행 상태</h2><div className="process-list">{["파일 업로드", "텍스트 추출", "섹션 분리", "섹션별 설명 생성", "학습 DB 저장", "학습 준비 완료"].map((step, index) => <div key={step} className={index < 4 ? "done" : index === 4 ? "current" : ""}><span>{index + 1}</span>{step}</div>)}</div></div>
        <div className="card blue-tint"><h2>긴 자료 처리 방식</h2><p>문서를 한 번에 AI에 넣지 않고 섹션과 chunk로 나눕니다. 필요할 때 관련 chunk만 검색해 답변합니다.</p></div>
      </aside>
    </section>
  );
}

function Learn({ doc, apiFetch, annotations, refreshAnnotations, questions, refreshQuestions, setDocuments, setPage }) {
  const sections = doc?.sections?.length ? doc.sections : fallbackSections();
  const [activeSectionIndex, setActiveSectionIndex] = useState(0);
  const section = sections[Math.min(activeSectionIndex, sections.length - 1)] || sections[0];
  const [selection, setSelection] = useState(null);
  const [activeTool, setActiveTool] = useState(null);
  const [draft, setDraft] = useState("이 부분을 쉽게 설명해줘");
  const [activeAnnotation, setActiveAnnotation] = useState(null);
  const [followup, setFollowup] = useState("");
  const [working, setWorking] = useState(false);
  const [notice, setNotice] = useState("");
  const sectionAnnotations = annotations.filter((item) => item.documentId === doc?.id && item.sectionId === section?.id);

  useEffect(() => {
    setActiveSectionIndex(0);
    setSelection(null);
    setActiveAnnotation(null);
  }, [doc?.id]);

  function openAnnotation(annotation) {
    setActiveAnnotation(annotation);
    setSelection(null);
    setActiveTool(null);
    setDraft(annotation?.type === "note" ? annotation.note || "" : "이 부분을 쉽게 설명해줘");
    setFollowup("");
  }

  async function openSection(index) {
    setActiveSectionIndex(index);
    setSelection(null);
    setActiveAnnotation(null);
    setNotice("");

    if (!doc?.id || doc.id.startsWith("sample-")) return;
    const progress = Math.max(doc.progress || 0, Math.round(((index + 1) / sections.length) * 100));
    setDocuments((current) => current.map((item) => item.id === doc.id ? { ...item, progress } : item));
    const response = await apiFetch(`/api/documents/${encodeURIComponent(doc.id)}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ progress })
    });
    if (response.ok) {
      const data = await response.json();
      if (data.document) setDocuments((current) => current.map((item) => item.id === doc.id ? data.document : item));
    }
  }

  function captureSelection() {
    const selectedText = window.getSelection?.().toString().trim();
    if (!selectedText || selectedText.length < 2) return;

    const offset = section.content?.indexOf(selectedText) ?? -1;
    setSelection({
      selectedText,
      sectionId: section.id,
      sectionTitle: section.title,
      anchor: {
        type: "text-selection",
        offset,
        length: selectedText.length
      }
    });
    setActiveTool(null);
    setDraft("이 부분을 쉽게 설명해줘");
    setActiveAnnotation(null);
  }

  async function createAnnotation(event) {
    event.preventDefault();
    if (!selection || !activeTool) return;
    setWorking(true);
    const response = await apiFetch("/api/annotations", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        documentId: doc?.id,
        sectionId: selection.sectionId,
        type: activeTool,
        question: activeTool === "question" ? draft : undefined,
        note: activeTool === "note" ? draft : undefined,
        selectedText: selection.selectedText,
        anchor: selection.anchor
      })
    });
    const data = await response.json();
    if (!response.ok) {
      setNotice(data.error || "질문/메모 저장에 실패했습니다.");
      setWorking(false);
      return;
    }
    setActiveAnnotation(data.annotation);
    setSelection(null);
    setActiveTool(null);
    setWorking(false);
    await refreshAnnotations(doc?.id);
    await refreshQuestions();
  }

  async function updateActiveAnnotation(event) {
    event.preventDefault();
    if (!activeAnnotation) return;
    setWorking(true);
    const response = await apiFetch("/api/annotations", {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        id: activeAnnotation.id,
        documentId: doc?.id,
        selectedText: activeAnnotation.selectedText,
        note: activeAnnotation.type === "note" ? draft : undefined,
        followupQuestion: activeAnnotation.type === "question" ? followup : undefined
      })
    });
    const data = await response.json();
    if (!response.ok) {
      setNotice(data.error || "질문/메모 수정에 실패했습니다.");
      setWorking(false);
      return;
    }
    setActiveAnnotation(data.annotation);
    setFollowup("");
    setWorking(false);
    await refreshAnnotations(doc?.id);
  }

  return (
    <section className="workspace">
      <article className="reader card">
        <div className="reader-top"><div><h2>{doc?.title || "미적분 - 미분의 개념"}</h2><p>{sections.length}개 섹션 · {Math.max(doc?.progress || 0, Math.round(((activeSectionIndex + 1) / sections.length) * 100))}% 완료</p></div><button className="icon-button">⋯</button></div>
        <div className="lesson-tabs">{sections.map((item, index) => <button key={item.id || index} type="button" className={index === activeSectionIndex ? "active" : ""} onClick={() => openSection(index)}>{index + 1}. {item.title}</button>)}</div>
        <div className="lesson-body" onMouseUp={captureSelection}>
          <h3>{section.title}</h3>
          <div className="lesson-paragraph">{renderAnnotatedText(section.content || section.explanation?.summary || "", sectionAnnotations, openAnnotation)}</div>
          <div className="formula">{section.explanation?.studyPrompt || "핵심 개념을 읽고 예제에 적용해보세요."}</div>
          <mark>{section.explanation?.keyPoints?.[0] || "즉, 관련 chunk만 가져와 학습 설명을 제공합니다."}</mark>
          {selection && (
            <form className="selection-card" onSubmit={createAnnotation}>
              <div>
                <strong>선택한 부분</strong>
                <p>{selection.selectedText}</p>
              </div>
              <div className="tool-switch">
                <button type="button" className={activeTool === "question" ? "active" : ""} onClick={() => { setActiveTool("question"); setDraft("이 부분을 쉽게 설명해줘"); }}>질문</button>
                <button type="button" className={activeTool === "note" ? "active" : ""} onClick={() => { setActiveTool("note"); setDraft(""); }}>메모</button>
              </div>
              <div className="selection-actions">
                <input value={draft} onChange={(event) => setDraft(event.target.value)} placeholder={activeTool === "note" ? "메모를 입력하세요" : "질문을 입력하세요"} />
                <button className="primary-button" disabled={working || !activeTool}>{working ? "저장 중" : activeTool === "note" ? "메모 저장" : "질문하기"}</button>
              </div>
            </form>
          )}
          {notice && <p className="status-message error">{notice}</p>}
          {activeAnnotation && (
            <form className="annotation-detail" onSubmit={updateActiveAnnotation}>
              <div className="card-heading">
                <h3>{activeAnnotation.type === "note" ? "메모" : "질문 기록"}</h3>
                <button type="button" className="text-button" onClick={() => setActiveAnnotation(null)}>닫기</button>
              </div>
              <p className="selected-quote">{activeAnnotation.selectedText}</p>
              {activeAnnotation.type === "note" ? (
                <>
                  <textarea value={draft || activeAnnotation.note || ""} onChange={(event) => setDraft(event.target.value)} />
                  <button className="primary-button" disabled={working}>{working ? "저장 중" : "메모 수정"}</button>
                </>
              ) : (
                <>
                  <div className="thread-list">{(activeAnnotation.thread || []).map((turn) => <div key={turn.id} className="thread-turn"><b>Q. {turn.question}</b><p>A. {turn.answer}</p></div>)}</div>
                  <div className="selection-actions"><input value={followup} onChange={(event) => setFollowup(event.target.value)} placeholder="추가 질문을 입력하세요" /><button className="primary-button" disabled={working || !followup}>{working ? "질문 중" : "이어 질문"}</button></div>
                </>
              )}
            </form>
          )}
          <div className="floating-menu"><button onClick={() => setPage("ask")}>전체 질문하기</button><button type="button" onClick={() => openSection(Math.max(0, activeSectionIndex - 1))}>이전</button><button type="button" onClick={() => openSection(Math.min(sections.length - 1, activeSectionIndex + 1))}>다음</button></div>
          <h3>섹션별 설명</h3>
          <div className="section-explanations">{sections.map((item, index) => <button type="button" key={item.id} className={`example-box section-jump ${index === activeSectionIndex ? "active" : ""}`} onClick={() => openSection(index)}><strong>{item.title}</strong><p>{item.explanation?.summary}</p></button>)}</div>
        </div>
      </article>
      <aside className="right-panel">
        <div className="panel-card">
          <div className="panel-heading"><h3>질문/메모 기록</h3><button onClick={() => setPage("ask")}>전체보기</button></div>
          <div className="annotation-list">
            {(sectionAnnotations.length ? sectionAnnotations : [{ id: "empty", type: "empty", question: "아직 이 섹션에 남긴 기록이 없습니다.", selectedText: "문장을 드래그해 질문이나 메모를 남겨보세요." }]).map((item) => (
              <button key={item.id} className="annotation-item" type="button" onClick={() => item.type !== "empty" && openAnnotation(item)}>
                <span className="annotation-icon">{item.type === "note" ? "📝" : "💬"}</span>
                <strong>{item.type === "note" ? "메모" : item.thread?.[0]?.question || item.question}</strong>
                <small>{item.selectedText}</small>
              </button>
            ))}
          </div>
        </div>
        <div className="panel-card blue-tint"><h3>AI 요약</h3><p>{doc?.overview?.summary || "미분계수는 순간변화율을 나타내며, 접선의 기울기와 연결됩니다."}</p></div>
      </aside>
    </section>
  );
}

function Ask({ doc, apiFetch, refreshQuestions }) {
  const [question, setQuestion] = useState("이 부분을 쉽게 설명해줘");
  const [answer, setAnswer] = useState(null);
  const [loading, setLoading] = useState(false);

  async function submitQuestion(event) {
    event.preventDefault();
    setLoading(true);
    const response = await apiFetch("/api/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ documentId: doc?.id, question })
    });
    const data = await response.json();
    setAnswer(data);
    setLoading(false);
    refreshQuestions();
  }

  return (
    <section className="workspace">
      <article className="chat-area card">
        <div className="reader-top"><div><h2>AI 질문하기</h2><p>관련 chunk만 검색해 답변합니다.</p></div></div>
        <div className="selected-context"><span>선택한 자료</span><p>{doc?.title}</p></div>
        <div className="chat-thread">
          <div className="bubble user">{question}</div>
          <div className="bubble ai"><p>{answer?.answer || "질문을 제출하면 업로드 자료의 관련 chunk를 찾아 답변합니다."}</p>{answer?.mode && <small>모드: {answer.mode}</small>}{answer?.sources?.map((source) => <small key={source.chunkId || source.sectionId}>참고: {source.title} · 유사도 {source.score}</small>)}</div>
        </div>
        <form className="chat-input" onSubmit={submitQuestion}><input value={question} onChange={(event) => setQuestion(event.target.value)} /><button disabled={loading}>{loading ? "분석" : "보내기"}</button></form>
      </article>
      <aside className="right-panel"><div className="panel-card"><h3>긴 자료 대응</h3><p>API 키가 없을 때는 로컬 해시 embedding으로 chunk를 검색합니다. 키와 pgvector를 연결하면 같은 흐름이 실제 vector 검색으로 바뀝니다.</p></div></aside>
    </section>
  );
}

function Questions({ questions, setPage }) {
  return <section className="page-section"><div className="section-header"><div><h2>질문 기록</h2><p>질문과 답변, 참고 섹션이 저장됩니다.</p></div></div><div className="question-list">{(questions.length ? questions : [{ id: "empty", question: "아직 저장된 질문이 없습니다.", answer: "문서 학습 화면에서 질문을 남겨보세요.", sources: [] }]).map((item) => <button key={item.id} className="question-card" onClick={() => setPage("ask")}><div><strong>{item.question}</strong><span>{formatDate(item.createdAt)}</span></div><p><b>A.</b> {item.answer}</p></button>)}</div></section>;
}

function Roadmap({ roadmap, setPage }) {
  const plan = roadmap?.plan || [];
  return (
    <section className="page-section">
      <div className="roadmap-hero card">
        <div><h2>{roadmap?.documentTitle || "자료 기반 로드맵"}</h2><p>{roadmap?.goal || "섹션별 설명을 학습 단위로 사용합니다."}</p></div>
        <div className="roadmap-stats"><span><b>로컬</b> Agent</span><span><b>{roadmap?.progress || 0}%</b> 진행률</span><span><b>{plan.length}</b> 학습일</span></div>
      </div>
      <div className="roadmap-layout">
        <div className="timeline">
          {plan.map((item) => <article key={item.id} className="timeline-card"><div className="timeline-marker" /><div><div className="card-heading"><h3>{item.day} · {item.title}</h3><Badge>{item.status}</Badge></div><ul>{item.tasks.map((task) => <li key={task}>{task}</li>)}</ul></div></article>)}
        </div>
        <aside className="right-panel inline">
          <div className="panel-card blue-tint"><h3>오늘의 학습</h3><p>{roadmap?.today?.title || "자료를 업로드하면 오늘의 학습이 생성됩니다."}</p><button className="primary-button" onClick={() => setPage("learn")}>시작하기</button></div>
          <div className="panel-card"><h3>추천</h3>{(roadmap?.recommendations || []).map((item) => <p key={item}>{item}</p>)}</div>
        </aside>
      </div>
    </section>
  );
}

function Quiz({ doc, apiFetch, quizSession, setQuizSession, setFeedback, setPage }) {
  const [answer, setAnswer] = useState("");
  const quiz = quizSession.quizzes[quizSession.currentIndex];

  async function generateQuiz() {
    setQuizSession((prev) => ({ ...prev, loading: true, message: "자료 chunk를 기반으로 문제를 생성하는 중입니다." }));
    const response = await apiFetch("/api/quizzes", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ documentId: doc?.id, type: "short_answer", difficulty: "medium", count: 5 })
    });
    const data = await response.json();
    if (!response.ok) {
      setQuizSession((prev) => ({ ...prev, loading: false, message: data.error || "문제 생성에 실패했습니다." }));
      return;
    }
    setAnswer("");
    setQuizSession({ quizzes: data.quizzes || [], currentIndex: 0, loading: false, message: `${data.quizzes?.length || 0}개 문제가 생성되었습니다. (${data.mode})` });
  }

  async function submitAnswer() {
    if (!quiz) return;
    const response = await apiFetch("/api/attempts", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ quizId: quiz.id, userAnswer: answer })
    });
    const data = await response.json();
    if (!response.ok) {
      setQuizSession((prev) => ({ ...prev, message: data.error || "답안 제출에 실패했습니다." }));
      return;
    }
    setFeedback(data);
    setPage("feedback");
  }

  return (
    <section className="workspace">
      <article className="quiz-card card">
        <div className="reader-top">
          <div><h2>문제 풀이</h2><p>{quiz ? `문제 ${quizSession.currentIndex + 1} / ${quizSession.quizzes.length}` : "자료 기반 문제를 먼저 생성하세요."}</p></div>
          <button className="secondary-button" onClick={generateQuiz} disabled={quizSession.loading}>{quizSession.loading ? "생성 중" : "문제 생성"}</button>
        </div>
        <Progress value={quiz ? ((quizSession.currentIndex + 1) / quizSession.quizzes.length) * 100 : 0} />
        <div className="problem">
          <p>{quiz?.question || "현재 선택한 문서의 섹션/chunk를 바탕으로 로컬 문제 생성 Agent가 문제를 만듭니다."}</p>
          {quiz?.options?.length > 0 && <div className="option-list">{quiz.options.map((option) => <button key={option} type="button" onClick={() => setAnswer(option)}>{option}</button>)}</div>}
          <textarea value={answer} onChange={(event) => setAnswer(event.target.value)} placeholder="답안을 입력하세요..." />
          <div className="answer-actions">
            <button className="secondary-button" type="button" onClick={() => quiz && setAnswer(quiz.hint)}>힌트 보기</button>
            <button className="primary-button" type="button" onClick={submitAnswer} disabled={!quiz}>정답 제출</button>
          </div>
          {quizSession.message && <p className="status-message">{quizSession.message}</p>}
        </div>
      </article>
      <aside className="right-panel">
        <div className="panel-card">
          <h3>문제 정보</h3>
          <dl className="info-list">
            <dt>유형</dt><dd>{quiz?.type || "단답형"}</dd>
            <dt>난이도</dt><dd>{quiz?.difficulty || "중"}</dd>
            <dt>섹션</dt><dd>{quiz?.sectionTitle || doc?.sections?.[0]?.title || "-"}</dd>
          </dl>
        </div>
        <div className="panel-card blue-tint"><h3>로컬 Agent</h3><p>AI API 없이 자료의 chunk와 핵심어를 이용해 문제를 생성합니다.</p></div>
      </aside>
    </section>
  );
}

function Feedback({ feedback, setPage }) {
  const result = feedback?.result;
  const quiz = feedback?.quiz;
  const attempt = feedback?.attempt;

  return (
    <section className="workspace">
      <article className="feedback-card card">
        <div className={`result-banner ${result?.isCorrect ? "correct" : "wrong"}`}>
          <strong>{result?.isCorrect ? "맞았어요" : "틀렸어요"}</strong>
          <span>{result?.feedback || "문제를 풀면 피드백이 표시됩니다."}</span>
        </div>
        <div className="answer-compare">
          <div><span>제출한 답</span><p>{attempt?.userAnswer || "-"}</p></div>
          <div><span>정답</span><p>{quiz?.answer || "-"}</p></div>
        </div>
        <div className="explanation"><h3>해설</h3><p>{quiz?.explanation || "아직 풀이 결과가 없습니다."}</p></div>
      </article>
      <aside className="right-panel">
        <div className="panel-card blue-tint">
          <h3>피드백</h3>
          <p>{result?.reviewedSection ? `${result.reviewedSection} 섹션을 다시 확인해보세요.` : "자료 기반 피드백이 여기에 표시됩니다."}</p>
          <button className="wide-button" onClick={() => setPage("quiz")}>유사 문제 풀기</button>
          <button className="wide-button" onClick={() => setPage("learn")}>개념 다시 보기</button>
        </div>
      </aside>
    </section>
  );
}

function Analytics({ analytics }) {
  const metrics = analytics?.metrics || [["문서 수", "0개", "업로드 자료"], ["섹션 수", "0개", "학습 단위"], ["질문 수", "0개", "누적 질문"], ["정답률", "0%", "풀이 기록"]].map(([label, value, delta]) => ({ label, value, delta }));
  return (
    <section className="page-section">
      <div className="analytics-grid">{metrics.map((item) => <article key={item.label} className="card metric-card"><span>{item.label}</span><strong>{item.value}</strong><small>{item.delta}</small></article>)}</div>
      <div className="analysis-layout">
        <article className="card"><h2>학습 준비 상태</h2><p>{analytics?.studyReadiness || "자료 필요"}</p><p>총 chunk 수: {analytics?.totalChunks || 0}</p></article>
        <article className="card"><h2>취약 개념 TOP 3</h2><ol className="weak-list">{(analytics?.weakConcepts?.length ? analytics.weakConcepts : [{ concept: "아직 오답 기록 없음", weaknessScore: 0 }]).map((item) => <li key={item.concept}><span>{item.concept}</span><b>{item.weaknessScore}%</b></li>)}</ol></article>
      </div>
    </section>
  );
}

function Settings() {
  return <section className="page-section"><article className="card settings-card"><h2>설정</h2><label>이름<input defaultValue="지민" /></label><label>답변 난이도<select defaultValue="easy"><option value="easy">쉽게 설명</option><option value="deep">심화 설명</option></select></label><button className="primary-button">저장</button></article></section>;
}

function fallbackSections() {
  return [{ id: "fallback-1", title: "미분의 정의", content: "미분계수는 순간변화율입니다.", explanation: { summary: "함수의 순간변화율을 구하는 개념입니다.", keyPoints: ["접선의 기울기와 연결됩니다."], studyPrompt: "순간변화율과 접선의 기울기를 연결해보세요." } }];
}

function renderAnnotatedText(text, annotations, onOpen) {
  const source = String(text || "");
  const valid = annotations
    .filter((item) => item.selectedText)
    .slice(0, 20);

  if (!valid.length) return source;

  const ranges = [];
  valid.forEach((item) => {
    const anchorStart = Number.isInteger(item.anchor?.offset) ? item.anchor.offset : -1;
    const anchorLength = Number.isInteger(item.anchor?.length) ? item.anchor.length : item.selectedText.length;
    const anchoredText = anchorStart >= 0 ? source.slice(anchorStart, anchorStart + anchorLength) : "";
    const start = anchoredText === item.selectedText ? anchorStart : source.indexOf(item.selectedText);
    if (start >= 0) {
      ranges.push({
        start,
        end: start + anchorLength,
        item
      });
    }
  });

  ranges.sort((a, b) => a.start - b.start);
  const nodes = [];
  let cursor = 0;

  ranges.forEach((range, index) => {
    if (range.start < cursor) return;
    if (range.start > cursor) nodes.push(source.slice(cursor, range.start));
    nodes.push(
      <button key={`${range.item.id}-${index}`} type="button" className={`annotated-text ${range.item.type === "note" ? "note" : "question"}`} title={range.item.type === "note" ? "메모 보기" : "질문 보기"} onClick={() => onOpen?.(range.item)}>
        {source.slice(range.start, range.end)}
        <span className="inline-comment-icon">{range.item.type === "note" ? "📝" : "💬"}</span>
      </button>
    );
    cursor = range.end;
  });

  if (cursor < source.length) nodes.push(source.slice(cursor));
  return nodes;
}

function formatDate(date) {
  if (!date) return "2026.05.04";
  if (/^\d{4}\.\d{2}\.\d{2}$/.test(date)) return date;
  return new Date(date).toLocaleDateString("ko-KR", { year: "numeric", month: "2-digit", day: "2-digit" }).replace(/\s/g, "");
}
