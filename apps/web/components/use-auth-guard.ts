"use client";

import { useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";

import { api } from "@/lib/api";
import { clearStoredSession, readStoredSession, type AuthSession } from "@/lib/auth";
import type { BootstrapResponse } from "@/lib/types";

type AuthGuardOptions = {
  requireDiagnostic?: boolean;
  redirectIfDiagnosticDone?: boolean;
};

export function useAuthGuard(options: AuthGuardOptions = {}) {
  const router = useRouter();
  const pathname = usePathname();
  const [ready, setReady] = useState(false);
  const [session, setSession] = useState<AuthSession | null>(null);
  const [bootstrap, setBootstrap] = useState<BootstrapResponse | null>(null);

  useEffect(() => {
    const current = readStoredSession();
    if (!current) {
      router.replace("/");
      return;
    }
    setSession(current);
    api
      .bootstrap()
      .then((response) => {
        setBootstrap(response);
        const requiredRoute = response.onboarding?.requiredRoute ?? "/dashboard";
        const onboardingPage = pathname === "/survey" || pathname === "/diagnostic";
        if (onboardingPage) {
          if (requiredRoute !== pathname) {
            router.replace(requiredRoute);
            return;
          }
          setReady(true);
          return;
        }
        if (requiredRoute !== "/dashboard") {
          router.replace(requiredRoute);
          return;
        }
        setReady(true);
      })
      .catch(() => {
        clearStoredSession();
        router.replace("/");
      });
  }, [options.redirectIfDiagnosticDone, options.requireDiagnostic, pathname, router]);

  return { ready, session, bootstrap };
}
