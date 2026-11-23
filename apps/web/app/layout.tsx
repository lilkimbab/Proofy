import type { Metadata, Viewport } from "next";
import type { ReactNode } from "react";

import { AppChrome } from "@/components/app-chrome";
import { ThemeController } from "@/components/theme-controller";
import "./globals.css";

export const metadata: Metadata = {
  title: "Proofy · 수능 수학",
  description: "진단 평가, AI 칠판 강의, 풀이 채점, 오답노트까지 한 곳에서 하는 수능 수학 공부",
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  themeColor: "#ffffff",
};

export default function RootLayout({ children }: Readonly<{ children: ReactNode }>) {
  return (
    <html lang="ko">
      <head>
        <link rel="preconnect" href="https://cdn.jsdelivr.net" crossOrigin="anonymous" />
        <link
          rel="stylesheet"
          href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/variable/pretendardvariable-dynamic-subset.min.css"
          crossOrigin="anonymous"
        />
      </head>
      <body>
        <ThemeController />
        <AppChrome>{children}</AppChrome>
      </body>
    </html>
  );
}
