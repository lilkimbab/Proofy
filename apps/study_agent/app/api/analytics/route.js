import { NextResponse } from "next/server";
import { buildLocalAnalytics } from "@/lib/studyPlanner";
import { listAttempts, listDocuments, listQuestions } from "@/lib/store";
import { getRequestUser } from "@/lib/auth";

export async function GET(request) {
  const user = await getRequestUser(request);
  const [documents, questions, attempts] = await Promise.all([
    listDocuments(user.id),
    listQuestions(user.id),
    listAttempts(user.id)
  ]);

  return NextResponse.json({
    mode: "local-analytics",
    analytics: buildLocalAnalytics({ documents, questions, attempts })
  });
}
