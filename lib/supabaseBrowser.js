"use client";

import { createClient } from "@supabase/supabase-js";

let cachedClient = null;
let cachedConfig = null;

export async function getSupabaseBrowserClient() {
  if (cachedClient) return cachedClient;

  const response = await fetch("/api/auth/config");
  const config = await response.json();

  if (!config.configured) {
    throw new Error(config.error || "Supabase Auth 설정이 필요합니다.");
  }

  cachedConfig = config;
  cachedClient = createClient(config.url, config.anonKey, {
    auth: {
      persistSession: true,
      autoRefreshToken: true,
      detectSessionInUrl: true
    }
  });

  return cachedClient;
}

export function getCachedSupabaseConfig() {
  return cachedConfig;
}
