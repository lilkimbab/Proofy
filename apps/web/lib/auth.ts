"use client";

export type AuthSession = {
  userId: string;
  email: string;
  displayName: string;
};

const STORAGE_KEY = "proofy-auth-session";

export function readStoredSession(): AuthSession | null {
  if (typeof window === "undefined") return null;
  const raw = window.localStorage.getItem(STORAGE_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as AuthSession;
  } catch {
    return null;
  }
}

export function writeStoredSession(session: AuthSession) {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(session));
}

export function clearStoredSession() {
  if (typeof window === "undefined") return;
  window.localStorage.removeItem(STORAGE_KEY);
}

export function authHeaders() {
  const session = readStoredSession();
  if (!session) return {};
  return { "X-User-Id": session.userId };
}
