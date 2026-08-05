import { NextRequest, NextResponse } from "next/server";
import { requireUser } from "@/lib/auth";
import { loadEquity, parseStrategy } from "@/lib/dashboard-data";
import { readFile } from "node:fs/promises";
import path from "node:path";

export const dynamic = "force-dynamic";

/**
 * Expected curve for paper comparison, scoped to one strategy.
 * Prefers content/backtest_window_<strategy>.json; falls back to
 * content/backtest_window.json for rsi2.
 */
export async function GET(req: NextRequest) {
  const { user, error } = await requireUser();
  if (error || !user) {
    return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  }

  const strategy = parseStrategy(req.nextUrl.searchParams.get("strategy"));
  const initialCash = Number(
    process.env.BACKTEST_INITIAL_CASH ||
      (strategy === "lev_trend" ? 20000 : 5000),
  );
  const paper = await loadEquity(strategy, 200);

  async function readWindow(fileName: string) {
    try {
      const file = path.join(process.cwd(), "content", fileName);
      const raw = await readFile(file, "utf-8");
      return JSON.parse(raw) as {
        series?: { trading_day: string; equity: number }[];
        buy_hold?: { trading_day: string; equity: number }[];
      };
    } catch {
      return null;
    }
  }

  let parsed =
    (await readWindow(`backtest_window_${strategy}.json`)) ||
    (strategy === "rsi2" ? await readWindow("backtest_window.json") : null);

  let expected = parsed?.series || [];
  let buyHold = parsed?.buy_hold || [];

  if (!expected.length && paper.length) {
    expected = paper.map((p) => ({
      trading_day: p.trading_day,
      equity: initialCash,
    }));
  }

  return NextResponse.json({
    strategy,
    initial_cash: initialCash,
    paper: paper.map((p) => ({
      trading_day: p.trading_day,
      equity: Number(p.equity),
    })),
    expected,
    buy_hold: buyHold,
  });
}
