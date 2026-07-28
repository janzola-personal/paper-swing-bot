import { NextResponse } from "next/server";
import {
  fetchAccount,
  fetchClock,
  fetchPositions,
} from "@/lib/alpaca-server";
import {
  dayPnlPct,
  etTodayIso,
  lastRunIsStale,
  loadBotState,
  loadGateProgress,
  loadJournal,
  loadLatestRun,
  loadRunForDay,
} from "@/lib/dashboard-data";
import { requireUser } from "@/lib/auth";

export const dynamic = "force-dynamic";

export async function GET() {
  const { user, error } = await requireUser();
  if (error || !user) {
    return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  }

  const todayEt = etTodayIso();
  const state = await loadBotState();
  const todayRun = await loadRunForDay(todayEt);
  const latestRun = todayRun || (await loadLatestRun());
  const todayJournal = await loadJournal({ tradingDay: todayEt, limit: 40 });
  const gate = await loadGateProgress();

  let account = null;
  let positions: Awaited<ReturnType<typeof fetchPositions>> = [];
  let clock = null;
  let brokerError: string | null = null;
  try {
    account = await fetchAccount();
    positions = await fetchPositions();
    clock = await fetchClock();
  } catch (e) {
    brokerError = e instanceof Error ? e.message : "broker error";
  }

  const equity = account?.equity ?? null;
  const cash = account?.cash ?? null;
  const pnl = dayPnlPct(equity ?? 0, state?.day_start_equity);

  const shadowMode =
    (process.env.BOT_SHADOW_MODE || "true").toLowerCase() !== "false";
  const submit = (process.env.BOT_SUBMIT || "false").toLowerCase() === "true";

  return NextResponse.json({
    trading_day_et: todayEt,
    equity,
    cash,
    day_pnl_pct: pnl,
    market_open: clock?.is_open ?? null,
    clock,
    state: state
      ? {
          paused: state.paused,
          halted: state.halted,
          halted_reason: state.halted_reason,
          day_halted_trading_day: state.day_halted_trading_day,
          peak_equity: state.peak_equity,
          day_start_equity: state.day_start_equity,
          day_start_trading_day: state.day_start_trading_day,
        }
      : null,
    last_run: latestRun,
    last_run_stale: lastRunIsStale(todayEt, todayRun),
    positions,
    today_decisions: todayJournal.filter((j) => j.symbol !== "SYSTEM"),
    broker_error: brokerError,
    shadow_mode: shadowMode,
    submit,
    gate,
    actor: user.email,
  });
}
