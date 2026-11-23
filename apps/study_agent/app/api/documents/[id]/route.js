import { NextResponse } from "next/server";
import { getRequestUser } from "@/lib/auth";
import { getDocument, updateDocument } from "@/lib/store";

export async function GET(request, context) {
  const user = await getRequestUser(request);
  const params = await context.params;
  const document = await getDocument(params.id, user.id);

  if (!document) {
    return NextResponse.json({ error: "문서를 찾지 못했습니다." }, { status: 404 });
  }

  return NextResponse.json({ document });
}

export async function PATCH(request, context) {
  const user = await getRequestUser(request);
  const params = await context.params;
  const body = await request.json();
  const updates = {};

  if (Number.isFinite(body.progress)) {
    updates.progress = Math.max(0, Math.min(100, Math.round(body.progress)));
  }

  if (typeof body.title === "string") updates.title = body.title.trim();
  if (typeof body.subject === "string") updates.subject = body.subject.trim();
  if (typeof body.goal === "string") updates.goal = body.goal.trim();
  if (typeof body.deadline === "string") updates.deadline = body.deadline.trim();
  if (typeof body.status === "string") updates.status = body.status.trim();

  if (!Object.keys(updates).length) {
    return NextResponse.json({ error: "수정할 값이 없습니다." }, { status: 400 });
  }

  const document = await updateDocument(params.id, updates, user.id);
  if (!document) {
    return NextResponse.json({ error: "문서를 찾지 못했습니다." }, { status: 404 });
  }

  return NextResponse.json({ document });
}
