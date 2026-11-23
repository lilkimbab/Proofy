import { NextResponse } from "next/server";
import { gradeLocalAttempt } from "@/lib/quizEngine";
import { getQuiz, saveAttempt } from "@/lib/store";
import { getRequestUser } from "@/lib/auth";

export async function POST(request) {
  const user = await getRequestUser(request);
  const body = await request.json();
  const quizId = String(body.quizId || "");
  const userAnswer = String(body.userAnswer || "");

  if (!quizId) {
    return NextResponse.json({ error: "quizId가 필요합니다." }, { status: 400 });
  }

  const quiz = await getQuiz(quizId, user.id);
  if (!quiz) {
    return NextResponse.json({ error: "문제를 찾지 못했습니다." }, { status: 404 });
  }

  const result = gradeLocalAttempt(quiz, userAnswer);
  const attempt = await saveAttempt({
    quizId,
    userId: user.id,
    documentId: quiz.documentId,
    userAnswer,
    ...result
  });

  return NextResponse.json({
    quiz,
    attempt,
    result
  });
}
