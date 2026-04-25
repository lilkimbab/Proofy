"use client";

import type { ReactNode } from "react";
import { useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";

import { AppNav } from "@/components/app-nav";
import { clearStoredSession, readStoredSession, type AuthSession } from "@/lib/auth";

export function AppChrome({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [session, setSession] = useState<AuthSession | null>(null);

  useEffect(() => {
    setSession(readStoredSession());
  }, [pathname]);

  const standalone =
    pathname === "/" ||
    pathname === "/survey" ||
    pathname === "/diagnostic" ||
    pathname === "/lesson";

  if (standalone) {
    return (
      <div className={`shell ${pathname === "/lesson" ? "shell-lesson" : "shell-landing"}`}>
        <main className={`app-shell ${pathname === "/lesson" ? "lesson-shell" : ""}`}>{children}</main>
      </div>
    );
  }

  return (
    <div className="shell">
      <header className="topbar topbar-compact">
        <div className="topbar-copy">
          <h1>Proofy</h1>
        </div>
        <div className="topbar-actions">
          {session ? (
            <div className="session-chip">
              <strong>{session.displayName}</strong>
            </div>
          ) : null}
          <AppNav />
          {session ? (
            <button
              type="button"
              className="button ghost"
              onClick={() => {
                clearStoredSession();
                router.push("/");
              }}
            >
              로그아웃
            </button>
          ) : null}
        </div>
      </header>
      <main className="app-shell">{children}</main>
    </div>
  );
}
