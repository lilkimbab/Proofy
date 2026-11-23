import { NextResponse } from "next/server";
import { generateLocalQuiz } from "@/lib/quizEngine";
import { getDocument, saveQuizzes } from "@/lib/store";
import { getRequestUser } from "@/lib/auth";

export async function POST(request) {
  const user = await getRequestUser(request);
  const body = await request.json();
  const documentId = String(body.documentId || "");
  const type = String(body.type || "short_answer");
  const difficulty = String(body.difficulty || "medium");
  const count = Number(body.count || 5);

  const document = await getDocument(documentId, user.id);
  if (!document) {
    return NextResponse.json({ error: "문서를 찾지 못했습니다." }, { status: 404 });
  }

  const quizzes = generateLocalQuiz(document, { type, difficulty, count });
  const saved = await saveQuizzes(quizzes.map((quiz) => ({ ...quiz, userId: user.id })), user.id);

  return NextResponse.json({
    mode: "local-quiz",
    quizzes: saved
  });
}
