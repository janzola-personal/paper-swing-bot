import { NextRequest, NextResponse } from "next/server";
import { requireUser } from "@/lib/auth";
import { loadJournal } from "@/lib/dashboard-data";

export const dynamic = "force-dynamic";

export async function GET(req: NextRequest) {
  const { user, error } = await requireUser();
  if (error || !user) {
    return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  }
  const sp = req.nextUrl.searchParams;
  const limit = Math.min(Number(sp.get("limit") || 50), 200);
  const tradingDay = sp.get("trading_day") || undefined;
  const rows = await loadJournal({ limit, tradingDay });
  return NextResponse.json({ rows });
}
