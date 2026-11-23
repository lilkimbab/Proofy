import { NextResponse } from "next/server";

function getMainApiBaseUrl() {
  return String(
    process.env.MAIN_API_BASE_URL ||
    process.env.MAIN_SERVER_URL ||
    "http://127.0.0.1:8000"
  ).replace(/\/+$/, "");
}

export async function GET() {
  try {
    const response = await fetch(`${getMainApiBaseUrl()}/api/agents/status`);
    const text = await response.text();
    const payload = text ? JSON.parse(text) : {};
    return NextResponse.json(payload, { status: response.status });
  } catch (error) {
    return NextResponse.json({ error: error.message || "agent status 조회 실패" }, { status: 500 });
  }
}
