import { type NextRequest } from "next/server";
import { updateSession } from "@/lib/supabase/middleware";

export async function middleware(request: NextRequest) {
  return updateSession(request);
}

export const config = {
  matcher: [
    "/",
    "/login",
    "/dashboard/:path*",
    "/research/:path*",
    "/gate/:path*",
    // Next.js dashboard APIs only — cron / engine_* Python routes stay open
    // (they use Bearer CRON_SECRET themselves).
    "/api/status",
    "/api/journal",
    "/api/equity",
    "/api/backtest-window",
    "/api/pause",
    "/api/flatten",
    "/api/reset-halt",
  ],
};
