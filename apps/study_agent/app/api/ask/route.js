import { NextResponse } from "next/server";
import { answerWithRag } from "@/lib/rag";
import { getDocument, saveQuestion } from "@/lib/store";
import { getRequestUser } from "@/lib/auth";

export async function POST(request) {
  const user = await getRequestUser(request);
  const body = await request.json();
  const question = String(body.question || "").trim();
  const documentId = String(body.documentId || "");
  const selectedText = String(body.selectedText || "").trim();
  const sectionId = String(body.sectionId || "");
  const anchor = body.anchor || null;

  if (!question) {
    return NextResponse.json({ error: "질문을 입력해주세요." }, { status: 400 });
  }

  const document = await getDocument(documentId, user.id);
  if (!document) {
    return NextResponse.json({
      answer: "저장된 문서를 찾지 못했습니다. 먼저 자료를 업로드해주세요.",
      sources: []
    });
  }

  const response = await answerWithRag({ document, question });

  await saveQuestion({
    documentId,
    userId: user.id,
    sectionId,
    selectedText,
    anchor,
    documentTitle: document.title,
    question,
    answer: response.answer,
    sources: response.sources,
    mode: response.mode
  });

  return NextResponse.json(response);
}
