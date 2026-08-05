import { createClient } from "@/lib/supabase/server";

/** Known engine claim keys — keep in sync with config.ENGINE_STRATEGIES. */
export const ENGINE_STRATEGIES = ["rsi2", "lev_trend"] as const;
export type EngineStrategy = (typeof ENGINE_STRATEGIES)[number];

export const ENGINE_META: Record<
  EngineStrategy,
  { name: string; label: string; symbols: string[]; allocation: number | null }
> = {
  rsi2: {
    name: "swing",
    label: "Swing — rsi2",
    symbols: ["SPY", "QQQ"],
    allocation: null,
  },
  lev_trend: {
    name: "lev_trend",
    label: "Leveraged trend — QLD",
    symbols: ["QLD"],
    allocation: 20_000,
  },
};

export function parseStrategy(raw: string | null | undefined): EngineStrategy {
  if (raw && (ENGINE_STRATEGIES as readonly string[]).includes(raw)) {
    return raw as EngineStrategy;
  }
  return "rsi2";
}

export type BotStateRow = {
  peak_equity: number;
  day_start_equity: number;
  day_start_trading_day: string | null;
  halted: boolean;
  halted_reason: string;
  day_halted_trading_day: string | null;
  paused: boolean;
  last_run_date: string | null;
  updated_at: string;
  strategy?: string;
  virtual_cash?: number;
};

export type RunRow = {
  trading_day: string;
  strategy: string;
  status: string;
  mode: string;
  started_at: string;
  completed_at: string | null;
};

export type JournalRow = {
  id: number;
  trading_day: string | null;
  timestamp_utc: string;
  symbol: string;
  action: string;
  qty: number;
  ref_price: number | null;
  reason: string | null;
  equity: number | null;
  cash: number | null;
  dry_run: boolean;
  actor: string | null;
  strategy?: string | null;
};

export type EquityRow = {
  trading_day: string;
  strategy: string;
  equity: number;
  cash: number;
  created_at: string;
};

/** America/New_York calendar date as YYYY-MM-DD (wall clock). */
export function etTodayIso(now = new Date()): string {
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: "America/New_York",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(now);
}

export async function loadBotState(
  strategy: EngineStrategy = "rsi2",
): Promise<BotStateRow | null> {
  const supabase = await createClient();
  const { data, error } = await supabase
    .from("bot_state")
    .select("*")
    .eq("strategy", strategy)
    .maybeSingle();
  if (error) {
    // Pre-migration fallback: singleton id=1
    const legacy = await supabase.from("bot_state").select("*").eq("id", 1).maybeSingle();
    if (legacy.error) throw error;
    return legacy.data as BotStateRow | null;
  }
  return data as BotStateRow | null;
}

export async function loadLatestRun(
  strategy: EngineStrategy = "rsi2",
): Promise<RunRow | null> {
  const supabase = await createClient();
  const { data, error } = await supabase
    .from("runs")
    .select("*")
    .eq("strategy", strategy)
    .order("trading_day", { ascending: false })
    .limit(1)
    .maybeSingle();
  if (error) throw error;
  return data as RunRow | null;
}

export async function loadRunForDay(
  tradingDay: string,
  strategy: EngineStrategy = "rsi2",
): Promise<RunRow | null> {
  const supabase = await createClient();
  const { data, error } = await supabase
    .from("runs")
    .select("*")
    .eq("trading_day", tradingDay)
    .eq("strategy", strategy)
    .maybeSingle();
  if (error) throw error;
  return data as RunRow | null;
}

export async function loadJournal(opts: {
  limit?: number;
  tradingDay?: string;
  strategy?: EngineStrategy;
}): Promise<JournalRow[]> {
  const supabase = await createClient();
  let q = supabase
    .from("journal")
    .select("*")
    .order("id", { ascending: false })
    .limit(opts.limit ?? 50);
  if (opts.tradingDay) {
    q = q.eq("trading_day", opts.tradingDay);
  }
  if (opts.strategy) {
    q = q.eq("strategy", opts.strategy);
  }
  const { data, error } = await q;
  if (error) throw error;
  return (data || []) as JournalRow[];
}

export async function loadEquity(
  strategy: EngineStrategy = "rsi2",
  limit = 120,
): Promise<EquityRow[]> {
  const supabase = await createClient();
  const { data, error } = await supabase
    .from("equity_snapshots")
    .select("trading_day, strategy, equity, cash, created_at")
    .eq("strategy", strategy)
    .order("trading_day", { ascending: true })
    .limit(limit);
  if (error) throw error;
  return (data || []) as EquityRow[];
}

export async function loadLatestEquity(
  strategy: EngineStrategy,
): Promise<EquityRow | null> {
  const supabase = await createClient();
  const { data, error } = await supabase
    .from("equity_snapshots")
    .select("trading_day, strategy, equity, cash, created_at")
    .eq("strategy", strategy)
    .order("trading_day", { ascending: false })
    .limit(1)
    .maybeSingle();
  if (error) throw error;
  return data as EquityRow | null;
}

export async function loadGateProgress(
  strategy: EngineStrategy = "rsi2",
): Promise<{
  days: number;
  trades: number;
  overrides: number;
  halts: number;
  paper_start: string | null;
  days_target: number;
  trades_target: number;
}> {
  const supabase = await createClient();
  const { data: runs, error: runsErr } = await supabase
    .from("runs")
    .select("trading_day, status, mode")
    .eq("strategy", strategy);
  if (runsErr) throw runsErr;

  const handled = new Set([
    "ok",
    "halt",
    "paused",
    "skipped_stale_data",
    "skipped_duplicate",
  ]);
  const submitDays = [
    ...new Set(
      (runs || [])
        .filter((r) => r.mode === "submit" && handled.has(r.status))
        .map((r) => r.trading_day as string),
    ),
  ].sort();
  const paperStart = submitDays[0] || null;

  let journalQuery = supabase
    .from("journal")
    .select("trading_day, action, qty, dry_run, actor, strategy")
    .eq("strategy", strategy)
    .order("id", { ascending: false })
    .limit(5000);
  if (paperStart) {
    journalQuery = journalQuery.gte("trading_day", paperStart);
  }
  const { data: journal, error: jErr } = await journalQuery;
  if (jErr) throw jErr;

  const rows = journal || [];
  const trades = rows.filter(
    (j) =>
      ["buy", "sell"].includes(String(j.action).toLowerCase()) &&
      Number(j.qty) > 0 &&
      j.dry_run === false,
  ).length;
  const overrides = rows.filter(
    (j) =>
      j.actor &&
      ["FLATTEN", "PAUSE", "RESUME", "RESET_HALT"].includes(
        String(j.action).toUpperCase(),
      ),
  ).length;
  const halts = rows.filter(
    (j) => String(j.action).toLowerCase() === "halt",
  ).length;

  return {
    days: submitDays.length,
    trades,
    overrides,
    halts,
    paper_start: paperStart,
    days_target: 60,
    trades_target: 40,
  };
}

export function dayPnlPct(
  equity: number,
  dayStart: number | null | undefined,
): number | null {
  if (!dayStart || dayStart <= 0) return null;
  return equity / dayStart - 1;
}

/** After ~5:30pm ET on a weekday, missing ok run is "stale". */
export function lastRunIsStale(
  todayEt: string,
  run: RunRow | null,
  now = new Date(),
): boolean {
  if (!run || run.trading_day !== todayEt || run.status !== "ok") {
    const parts = new Intl.DateTimeFormat("en-US", {
      timeZone: "America/New_York",
      weekday: "short",
      hour: "numeric",
      hour12: false,
      minute: "numeric",
    }).formatToParts(now);
    const weekday = parts.find((p) => p.type === "weekday")?.value;
    const hour = Number(parts.find((p) => p.type === "hour")?.value);
    const minute = Number(parts.find((p) => p.type === "minute")?.value);
    if (!weekday || ["Sat", "Sun"].includes(weekday)) return false;
    const mins = hour * 60 + minute;
    if (mins < 17 * 60 + 30) return false;
    return true;
  }
  return false;
}
