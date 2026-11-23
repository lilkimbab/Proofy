import "./globals.css";

export const metadata = {
  title: "AI 과외 선생님",
  description: "업로드한 학습 자료 기반 AI 학습 에이전트"
};

export default function RootLayout({ children }) {
  return (
    <html lang="ko">
      <body>{children}</body>
    </html>
  );
}
