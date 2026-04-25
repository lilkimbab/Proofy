import type { Metadata } from "next";
import type { ReactNode } from "react";

import { AppChrome } from "@/components/app-chrome";
import { ThemeController } from "@/components/theme-controller";
import "./globals.css";

export const metadata: Metadata = {
  title: "Proofy",
  description: "고3을 위한 AI 수능 수학 코치"
};

export default function RootLayout({
  children
}: Readonly<{ children: ReactNode }>) {
  return (
    <html lang="ko">
      <body>
        <ThemeController />
        <AppChrome>{children}</AppChrome>
      </body>
    </html>
  );
}
