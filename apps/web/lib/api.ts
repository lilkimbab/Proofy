import type {
  AuthSession,
  BootstrapResponse,
  DashboardResponse,
  LessonQuestionResponse,
  LessonSessionResponse,
  ReviewResponse,
  ThemeResponse
} from "./types";
import { authHeaders } from "./auth";

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
const WS_BASE =
  process.env.NEXT_PUBLIC_WS_BASE_URL ?? API_BASE.replace(/^http/, "ws");

async function buildError(response: Response, path: string, method: string): Promise<Error> {
  try {
    const payload = (await response.json()) as { detail?: string };
    if (payload?.detail) {
      return new Error(payload.detail);
    }
  } catch {}
  return new Error(`${method} ${path} failed`);
}

type RequestOptions = {
  timeoutMs?: number;
};

async function request<T>(path: string, init?: RequestInit, options?: RequestOptions): Promise<T> {
  const isFormData = typeof FormData !== "undefined" && init?.body instanceof FormData;
  const headers = new Headers(init?.headers ?? undefined);
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), options?.timeoutMs ?? 12000);
  Object.entries(authHeaders()).forEach(([key, value]) => {
    headers.set(key, value);
  });
  if (!isFormData) {
    headers.set("Content-Type", "application/json");
  }
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers,
      cache: "no-store",
      signal: controller.signal,
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      throw new Error("서버 응답이 지연되고 있어요. 잠시 후 다시 시도해 주세요.");
    }
    throw new Error("서버에 연결하지 못했습니다. API 서버가 실행 중인지 확인해 주세요.");
  } finally {
    window.clearTimeout(timeout);
  }
  if (!response.ok) {
    throw await buildError(response, path, init?.method ?? "GET");
  }
  return response.json() as Promise<T>;
}

export const api = {
  signup: (payload: { displayName: string; email: string; password: string }) =>
    request<{ session: AuthSession }>("/api/auth/signup", {
      method: "POST",
      body: JSON.stringify(payload)
    }),
  login: (payload: { email: string; password: string }) =>
    request<{ session: AuthSession }>("/api/auth/login", {
      method: "POST",
      body: JSON.stringify(payload)
    }),
  me: () => request<{ session: AuthSession }>("/api/auth/me"),
  bootstrap: () => request<BootstrapResponse>("/api/bootstrap", undefined, { timeoutMs: 20000 }),
  dashboard: () => request<DashboardResponse>("/api/dashboard"),
  updateProfile: (payload: unknown) =>
    request<{ profile: unknown; onboarding: BootstrapResponse["onboarding"]; dashboard?: DashboardResponse | null }>(
      "/api/profile",
      {
        method: "POST",
        body: JSON.stringify(payload)
      },
      { timeoutMs: 20000 }
    ),
  saveDiagnosticProgress: (answers: Record<string, number>) =>
    request<{
      saved: boolean;
      answerCount: number;
      requiredRoute: string;
    }>("/api/diagnostic/progress", {
      method: "POST",
      body: JSON.stringify({ answers })
    }),
  submitDiagnostic: (answers: Record<string, number>) =>
    request<{
      score: number;
      summary: string;
      topRisks: string[];
      recommendedTrack: string;
      mastery: unknown[];
      dashboard: DashboardResponse;
    }>(
      "/api/diagnostic/submit",
      {
        method: "POST",
        body: JSON.stringify({ answers })
      },
      { timeoutMs: 25000 }
    ),
  lessonSession: () => request<LessonSessionResponse>("/api/lesson/session"),
  activateContent: (payload: {
    bundleId: string;
    lessonId: string;
    problemSetId: string;
    problemId?: string;
  }) =>
    request<{
      dashboard: DashboardResponse;
      lessonSession: LessonSessionResponse;
    }>("/api/content/activate", {
      method: "POST",
      body: JSON.stringify(payload)
    }),
  lessonQuestion: (payload: {
    question: string;
    sceneId?: string;
    selectedObjectId?: string | null;
    runtimeSceneIds?: string[];
  }) =>
    request<LessonQuestionResponse>("/api/lesson/question", {
      method: "POST",
      body: JSON.stringify(payload)
    }, { timeoutMs: 20000 }),
  completeLesson: () =>
    request<{
      dashboard: DashboardResponse;
      lessonSession: LessonSessionResponse;
    }>("/api/lesson/complete", {
      method: "POST",
      body: JSON.stringify({})
    }),
  submitPractice: (payload: Record<string, string>) =>
    request<{
      attempt: unknown;
      dashboard: DashboardResponse;
      lessonSession: LessonSessionResponse;
      review: ReviewResponse;
      mistakeNotes: unknown[];
      syncEvent: Record<string, unknown>;
    }>("/api/practice/submit", {
      method: "POST",
      body: JSON.stringify(payload)
    }),
  nextPractice: () =>
    request<{
      moved: boolean;
      nextProblem?: { nextProblemId: string; nextProblemTitle: string };
      dashboard: DashboardResponse;
      lessonSession: LessonSessionResponse;
      syncEvent: Record<string, unknown>;
    }>("/api/practice/next", {
      method: "POST",
      body: JSON.stringify({})
    }),
  reviewLatest: () => request<ReviewResponse>("/api/review/latest"),
  mistakeNotes: () => request<{ notes: unknown[] }>("/api/mistake-notes"),
  setTheme: (themeId: string) =>
    request<ThemeResponse>("/api/gamification/theme", {
      method: "POST",
      body: JSON.stringify({ themeId })
    })
};

export function wsUrl(path: string, participant: string): string {
  return `${WS_BASE}${path}?participant=${encodeURIComponent(participant)}`;
}
