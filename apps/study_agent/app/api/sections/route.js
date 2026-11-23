import { NextResponse } from "next/server";
import { getDocument } from "@/lib/store";
import { getRequestUser } from "@/lib/auth";

export async function GET(request) {
  const user = await getRequestUser(request);
  const { searchParams } = new URL(request.url);
  const id = searchParams.get("documentId");
  const document = await getDocument(id, user.id);

  if (!document) {
    return NextResponse.json({ error: "문서를 찾지 못했습니다." }, { status: 404 });
  }

  return NextResponse.json({
    documentId: document.id,
    title: document.title,
    overview: document.overview,
    sections: document.sections || []
  });
}
