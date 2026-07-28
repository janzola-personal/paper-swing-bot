import { NextResponse } from "next/server";
import { requireUser } from "@/lib/auth";
import { loadEquity } from "@/lib/dashboard-data";
import { readFile } from "node:fs/promises";
import path from "node:path";

export const dynamic = "force-dynamic";

/**
 * Expected curve for paper comparison.
 * Prefers content/backtest_window.json (committed snapshot); else aligns a
 * flat initial-cash line to paper dates so the chart never shows paper alone.
 */
export async function GET() {
  const { user, error } = await requireUser();
  if (error || !user) {
    return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  }

  const initialCash = Number(process.env.BACKTEST_INITIAL_CASH || 5000);
  const paper = await loadEquity("rsi2", 200);

  let expected: { trading_day: string; equity: number }[] = [];
  try {
    const file = path.join(process.cwd(), "content", "backtest_window.json");
    const raw = await readFile(file, "utf-8");
    const parsed = JSON.parse(raw) as {
      series?: { trading_day: string; equity: number }[];
    };
    expected = parsed.series || [];
  } catch {
    expected = [];
  }

  // Buy-and-hold placeholder: scale from first paper day if no BH series stored
  let buyHold: { trading_day: string; equity: number }[] = [];
  try {
    const file = path.join(process.cwd(), "content", "backtest_window.json");
    const raw = await readFile(file, "utf-8");
    const parsed = JSON.parse(raw) as {
      buy_hold?: { trading_day: string; equity: number }[];
    };
    buyHold = parsed.buy_hold || [];
  } catch {
    buyHold = [];
  }

  if (!expected.length && paper.length) {
    expected = paper.map((p) => ({
      trading_day: p.trading_day,
      equity: initialCash,
    }));
  }

  return NextResponse.json({
    initial_cash: initialCash,
    paper: paper.map((p) => ({
      trading_day: p.trading_day,
      equity: Number(p.equity),
    })),
    expected,
    buy_hold: buyHold,
  });
}
