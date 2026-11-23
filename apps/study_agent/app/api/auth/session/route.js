import { NextResponse } from "next/server";
import { getRequestUser } from "@/lib/auth";

export async function GET(request) {
  const user = await getRequestUser(request);
  return NextResponse.json({ user });
}
