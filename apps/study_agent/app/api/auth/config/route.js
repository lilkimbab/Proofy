import { NextResponse } from "next/server";

export async function GET() {
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL || process.env.SUPABASE_URL || "";
  const anonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY || process.env.SUPABASE_ANON_KEY || "";

  if (!url || !anonKey) {
    return NextResponse.json({
      configured: false,
      error: "Supabase URL 또는 anon key가 설정되지 않았습니다."
    });
  }

  return NextResponse.json({
    configured: true,
    url,
    anonKey
  });
}
