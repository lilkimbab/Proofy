import { NextResponse } from "next/server";
import { answerWithRag } from "@/lib/rag";
import { getRequestUser } from "@/lib/auth";
import { createAnnotation, listAnnotations, updateAnnotation } from "@/lib/annotationStore";
import { getDocument, saveQuestion } from "@/lib/store";

export async function GET(request) {
  try {
    const user = await getRequestUser(request);
    const { searchParams } = new URL(request.url);
    const documentId = searchParams.get("documentId");
    const sectionId = searchParams.get("sectionId");

    if (!documentId) {
      return NextResponse.json({ error: "documentId가 필요합니다." }, { status: 400 });
    }

    const annotations = await listAnnotations({ userId: user.id, documentId, sectionId });
    return NextResponse.json({ annotations });
  } catch (error) {
    return NextResponse.json({ error: error.message || "질문/메모 기록을 불러오지 못했습니다." }, { status: 500 });
  }
}

export async function POST(request) {
  try {
    const user = await getRequestUser(request);
    const body = await request.json();
    const type = String(body.type || "question");
    const documentId = String(body.documentId || "");
    const sectionId = String(body.sectionId || "");
    const selectedText = String(body.selectedText || "").trim();

    if (!documentId || !sectionId || !selectedText) {
      return NextResponse.json({ error: "documentId, sectionId, selectedText가 필요합니다." }, { status: 400 });
    }

    let thread = [];
    let note = String(body.note || "");

    if (type === "question") {
      const question = String(body.question || "이 부분을 쉽게 설명해줘").trim();
      const document = await getDocument(documentId, user.id);
      if (!document) return NextResponse.json({ error: "문서를 찾지 못했습니다." }, { status: 404 });

      const response = await answerWithRag({ document, question: `${question}\n\n선택한 부분: ${selectedText}` });
      thread = [{
        id: `turn_${Date.now()}`,
        question,
        answer: response.answer,
        mode: response.mode,
        sources: response.sources,
        createdAt: new Date().toISOString()
      }];

      await saveQuestion({
        documentId,
        userId: user.id,
        sectionId,
        selectedText,
        anchor: body.anchor || null,
        documentTitle: document.title,
        question,
        answer: response.answer,
        sources: response.sources,
        mode: response.mode
      });
    }

    const annotation = await createAnnotation({
      userId: user.id,
      documentId,
      sectionId,
      type,
      selectedText,
      anchor: body.anchor || null,
      note,
      thread
    });

    return NextResponse.json({ annotation });
  } catch (error) {
    return NextResponse.json({ error: error.message || "질문/메모 기록을 저장하지 못했습니다." }, { status: 500 });
  }
}

export async function PATCH(request) {
  try {
    const user = await getRequestUser(request);
    const body = await request.json();
    const id = String(body.id || "");

    if (!id) return NextResponse.json({ error: "id가 필요합니다." }, { status: 400 });

    let threadItem = null;
    if (body.followupQuestion) {
      const document = await getDocument(String(body.documentId || ""), user.id);
      if (!document) return NextResponse.json({ error: "문서를 찾지 못했습니다." }, { status: 404 });
      const response = await answerWithRag({
        document,
        question: `${body.followupQuestion}\n\n선택한 부분: ${body.selectedText || ""}`
      });
      threadItem = {
        id: `turn_${Date.now()}`,
        question: body.followupQuestion,
        answer: response.answer,
        mode: response.mode,
        sources: response.sources,
        createdAt: new Date().toISOString()
      };
    }

    const annotation = await updateAnnotation({
      id,
      userId: user.id,
      note: body.note,
      threadItem
    });

    return NextResponse.json({ annotation });
  } catch (error) {
    return NextResponse.json({ error: error.message || "질문/메모 기록을 수정하지 못했습니다." }, { status: 500 });
  }
}
