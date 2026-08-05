"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { StatusStrip } from "./StatusStrip";
import { TodayDecisions } from "./TodayDecisions";
import { EquityChart } from "./EquityChart";
import { GateProgress } from "./GateProgress";
import { Positions } from "./Positions";
import { JournalTable } from "./JournalTable";

const STRATEGIES = [
  { id: "rsi2", label: "Swing — rsi2" },
  { id: "lev_trend", label: "Leveraged trend — QLD" },
] as const;

type StatusPayload = {
  strategy: string;
  engine: string;
  engine_label: string;
  symbols: string[];
  peer_equity: Record<string, number | null>;
  equity: number | null;
  cash: number | null;
  day_pnl_pct: number | null;
  market_open: boolean | null;
  account_equity: number | null;
  last_run: {
    trading_day: string;
    status: string;
    completed_at: string | null;
    mode: string;
  } | null;
  last_run_stale: boolean;
  state: {
    paused: boolean;
    halted: boolean;
    halted_reason: string;
  } | null;
  positions: {
    symbol: string;
    qty: number;
    avg_entry_price: number;
    current_price: number;
    unrealized_pl: number;
    unrealized_plpc: number;
  }[];
  today_decisions: {
    symbol: string;
    action: string;
    qty: number;
    ref_price: number | null;
    reason: string | null;
  }[];
  shadow_mode: boolean;
  submit: boolean;
  gate?: {
    days: number;
    trades: number;
    overrides: number;
    halts: number;
    paper_start: string | null;
    days_target: number;
    trades_target: number;
  } | null;
  broker_error?: string | null;
};

type JournalRow = {
  id: number;
  timestamp_utc: string;
  symbol: string;
  action: string;
  qty: number;
  ref_price: number | null;
  reason: string | null;
  actor: string | null;
};

function fmtMoney(n: number | null) {
  if (n == null || Number.isNaN(n)) return "—";
  return n.toLocaleString("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
  });
}

export function DashboardClient() {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const strategy = useMemo(() => {
    const raw = searchParams.get("strategy") || "rsi2";
    return STRATEGIES.some((s) => s.id === raw) ? raw : "rsi2";
  }, [searchParams]);

  const [status, setStatus] = useState<StatusPayload | null>(null);
  const [journal, setJournal] = useState<JournalRow[]>([]);
  const [error, setError] = useState<string | null>(null);

  const setStrategy = useCallback(
    (next: string) => {
      const sp = new URLSearchParams(searchParams.toString());
      sp.set("strategy", next);
      router.replace(`${pathname}?${sp.toString()}`);
    },
    [pathname, router, searchParams],
  );

  const refresh = useCallback(async () => {
    setError(null);
    const q = `strategy=${encodeURIComponent(strategy)}`;
    const [sRes, jRes] = await Promise.all([
      fetch(`/api/status?${q}`, { cache: "no-store" }),
      fetch(`/api/journal?limit=50&${q}`, { cache: "no-store" }),
    ]);
    if (!sRes.ok) {
      setError("Failed to load status");
      return;
    }
    setStatus(await sRes.json());
    if (jRes.ok) {
      const j = await jRes.json();
      setJournal(j.rows || []);
    }
  }, [strategy]);

  useEffect(() => {
    refresh();
    const onFocus = () => refresh();
    window.addEventListener("focus", onFocus);
    const id = window.setInterval(() => {
      if (document.visibilityState === "visible") refresh();
    }, 60_000);
    return () => {
      window.removeEventListener("focus", onFocus);
      window.clearInterval(id);
    };
  }, [refresh]);

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-end justify-between gap-4 border-b border-[var(--line)] pb-3">
        <div
          role="tablist"
          aria-label="Strategy"
          className="flex gap-0 border border-[var(--line)]"
        >
          {STRATEGIES.map((s) => {
            const active = s.id === strategy;
            return (
              <button
                key={s.id}
                type="button"
                role="tab"
                aria-selected={active}
                onClick={() => setStrategy(s.id)}
                className={
                  active
                    ? "bg-[rgba(143,184,154,0.12)] text-[var(--fg)] px-4 py-2 text-sm border-0 cursor-pointer"
                    : "bg-transparent text-[var(--muted)] px-4 py-2 text-sm border-0 cursor-pointer"
                }
              >
                {s.label}
              </button>
            );
          })}
        </div>
        <div className="flex gap-6 text-sm">
          {STRATEGIES.map((s) => (
            <div key={s.id}>
              <div className="text-[var(--muted)] text-xs uppercase tracking-wide">
                {s.label}
              </div>
              <div className={s.id === strategy ? "text-[var(--fg)]" : "text-[var(--muted)]"}>
                {fmtMoney(status?.peer_equity?.[s.id] ?? null)}
              </div>
            </div>
          ))}
        </div>
      </div>

      {error ? <p className="text-[var(--danger)] text-sm m-0">{error}</p> : null}
      {status?.broker_error ? (
        <p className="text-[var(--warn)] text-sm m-0">
          Broker read unavailable: {status.broker_error} (DB state still shown)
        </p>
      ) : null}
      {status && status.submit && !status.shadow_mode ? (
        <p className="text-sm text-[var(--accent)] m-0 border border-[var(--line)] p-3">
          Paper submit ON for <strong>{status.engine_label}</strong> — after-close runs
          place Alpaca <strong>paper</strong> market DAY orders that queue for the next
          open. Not live money.
        </p>
      ) : null}
      {strategy === "lev_trend" && status && (!status.submit || status.shadow_mode) ? (
        <p className="text-sm text-[var(--muted)] m-0 border border-[var(--line)] p-3">
          Leveraged trend is shadow-only until Stage A passes (see Research /
          LEV_TREND_STAGE_A). No paper orders yet.
        </p>
      ) : null}

      <StatusStrip status={status} strategy={strategy} onRefresh={refresh} />
      <TodayDecisions rows={status?.today_decisions || []} />
      <div className="grid lg:grid-cols-2 gap-4">
        <EquityChart strategy={strategy} />
        <GateProgress
          submitEnabled={Boolean(status?.submit && !status?.shadow_mode)}
          gate={status?.gate ?? null}
        />
      </div>
      <Positions positions={status?.positions || []} />
      <JournalTable rows={journal} />
    </div>
  );
}
