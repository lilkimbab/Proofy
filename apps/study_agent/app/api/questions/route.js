import { NextResponse } from "next/server";
import { listQuestions } from "@/lib/store";
import { getRequestUser } from "@/lib/auth";

export async function GET(request) {
  const user = await getRequestUser(request);
  const questions = await listQuestions(user.id);
  return NextResponse.json({ questions });
}
