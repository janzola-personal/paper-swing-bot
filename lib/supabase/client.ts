import { createBrowserClient } from "@supabase/ssr";
import { requirePublicSupabaseEnv } from "./env";

export function createClient() {
  const { url, anon } = requirePublicSupabaseEnv();
  return createBrowserClient(url, anon);
}
