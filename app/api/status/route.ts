import { NextRequest, NextResponse } from "next/server";
import {
  fetchAccount,
  fetchClock,
  fetchPositions,
} from "@/lib/alpaca-server";
import {
  ENGINE_META,
  ENGINE_STRATEGIES,
  dayPnlPct,
  etTodayIso,
  lastRunIsStale,
  loadBotState,
  loadGateProgress,
  loadJournal,
  loadLatestEquity,
  loadLatestRun,
  loadRunForDay,
  parseStrategy,
} from "@/lib/dashboard-data";
import { requireUser } from "@/lib/auth";

export const dynamic = "force-dynamic";

export async function GET(req: NextRequest) {
  const { user, error } = await requireUser();
  if (error || !user) {
    return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  }

  const strategy = parseStrategy(req.nextUrl.searchParams.get("strategy"));
  const meta = ENGINE_META[strategy];
  const todayEt = etTodayIso();
  const state = await loadBotState(strategy);
  const todayRun = await loadRunForDay(todayEt, strategy);
  const latestRun = todayRun || (await loadLatestRun(strategy));
  const todayJournal = await loadJournal({
    tradingDay: todayEt,
    limit: 40,
    strategy,
  });
  const gate = await loadGateProgress(strategy);
  const latestEq = await loadLatestEquity(strategy);

  // Peer equity strip (separate figures — never summed).
  const peerEquity: Record<string, number | null> = {};
  for (const s of ENGINE_STRATEGIES) {
    const row = await loadLatestEquity(s);
    peerEquity[s] = row ? Number(row.equity) : null;
  }

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

  // Filter positions to this engine's universe.
  const scopedPositions = positions.filter((p) =>
    meta.symbols.includes(p.symbol),
  );

  // Prefer per-strategy equity snapshot; fall back to account only for swing.
  let equity: number | null = latestEq ? Number(latestEq.equity) : null;
  let cash: number | null = latestEq ? Number(latestEq.cash) : null;
  if (equity == null && strategy === "rsi2" && account) {
    equity = account.equity;
    cash = account.cash;
  }
  if (equity == null && meta.allocation != null) {
    equity = state?.virtual_cash ?? meta.allocation;
    cash = state?.virtual_cash ?? meta.allocation;
  }

  const pnl = dayPnlPct(equity ?? 0, state?.day_start_equity);

  const shadowEnv =
    strategy === "lev_trend" ? "BOT_SHADOW_MODE_LEV_TREND" : "BOT_SHADOW_MODE";
  const submitEnv =
    strategy === "lev_trend" ? "BOT_SUBMIT_LEV_TREND" : "BOT_SUBMIT";
  const shadowMode =
    (process.env[shadowEnv] || "true").toLowerCase() !== "false";
  const submit = (process.env[submitEnv] || "false").toLowerCase() === "true";

  return NextResponse.json({
    trading_day_et: todayEt,
    strategy,
    engine: meta.name,
    engine_label: meta.label,
    symbols: meta.symbols,
    peer_equity: peerEquity,
    equity,
    cash,
    day_pnl_pct: pnl,
    market_open: clock?.is_open ?? null,
    clock,
    account_equity: account?.equity ?? null,
    state: state
      ? {
          paused: state.paused,
          halted: state.halted,
          halted_reason: state.halted_reason,
          day_halted_trading_day: state.day_halted_trading_day,
          peak_equity: state.peak_equity,
          day_start_equity: state.day_start_equity,
          day_start_trading_day: state.day_start_trading_day,
          virtual_cash: state.virtual_cash ?? null,
        }
      : null,
    last_run: latestRun,
    last_run_stale: lastRunIsStale(todayEt, todayRun),
    positions: scopedPositions,
    today_decisions: todayJournal.filter((j) => j.symbol !== "SYSTEM"),
    broker_error: brokerError,
    shadow_mode: shadowMode,
    submit,
    gate,
    actor: user.email,
  });
}
