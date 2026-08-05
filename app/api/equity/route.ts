import { NextRequest, NextResponse } from "next/server";
import { requireUser } from "@/lib/auth";
import { loadEquity, parseStrategy } from "@/lib/dashboard-data";

export const dynamic = "force-dynamic";

export async function GET(req: NextRequest) {
  const { user, error } = await requireUser();
  if (error || !user) {
    return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  }
  const strategy = parseStrategy(req.nextUrl.searchParams.get("strategy"));
  const limit = Math.min(Number(req.nextUrl.searchParams.get("limit") || 120), 500);
  const rows = await loadEquity(strategy, limit);
  return NextResponse.json({ rows, strategy });
}
