"use client";

import type { ReactNode } from "react";
import { useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";

import { AppNav } from "@/components/app-nav";
import { Brand, initials } from "@/components/ui";
import { clearStoredSession, readStoredSession, type AuthSession } from "@/lib/auth";

// These routes render their own full-screen layout (landing, onboarding, lesson player).
const STANDALONE_ROUTES = new Set(["/", "/survey", "/diagnostic", "/lesson"]);

export function AppChrome({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [session, setSession] = useState<AuthSession | null>(null);

  useEffect(() => {
    setSession(readStoredSession());
  }, [pathname]);

  if (STANDALONE_ROUTES.has(pathname)) {
    return <>{children}</>;
  }

  return (
    <div className="app">
      <header className="app-header">
        <div className="container app-header-inner">
          <Brand href="/dashboard" />
          <AppNav />
          <div className="header-right">
            {session ? (
              <>
                <span className="user-chip">
                  <span className="avatar" aria-hidden="true">
                    {initials(session.displayName)}
                  </span>
                  <span className="name">{session.displayName}</span>
                </span>
                <button
                  type="button"
                  className="btn btn-ghost btn-sm"
                  onClick={() => {
                    clearStoredSession();
                    router.push("/");
                  }}
                >
                  로그아웃
                </button>
              </>
            ) : null}
          </div>
        </div>
      </header>
      <main className="app-main">
        <div className="container">{children}</div>
      </main>
    </div>
  );
}
