"use client";

import { useCallback, useEffect, useState } from "react";
import { StatusStrip } from "./StatusStrip";
import { TodayDecisions } from "./TodayDecisions";
import { EquityChart } from "./EquityChart";
import { GateProgress } from "./GateProgress";
import { Positions } from "./Positions";
import { JournalTable } from "./JournalTable";

type StatusPayload = {
  equity: number | null;
  cash: number | null;
  day_pnl_pct: number | null;
  market_open: boolean | null;
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

export function DashboardClient() {
  const [status, setStatus] = useState<StatusPayload | null>(null);
  const [journal, setJournal] = useState<JournalRow[]>([]);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setError(null);
    const [sRes, jRes] = await Promise.all([
      fetch("/api/status", { cache: "no-store" }),
      fetch("/api/journal?limit=50", { cache: "no-store" }),
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
  }, []);

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
      {error ? <p className="text-[var(--danger)] text-sm m-0">{error}</p> : null}
      {status?.broker_error ? (
        <p className="text-[var(--warn)] text-sm m-0">
          Broker read unavailable: {status.broker_error} (DB state still shown)
        </p>
      ) : null}
      {status && status.submit && !status.shadow_mode ? (
        <p className="text-sm text-[var(--accent)] m-0 border border-[var(--line)] p-3">
          Paper submit ON — after-close runs place Alpaca <strong>paper</strong> market
          DAY orders that queue for the next open. Not live money.
        </p>
      ) : null}
      <StatusStrip status={status} onRefresh={refresh} />
      <TodayDecisions rows={status?.today_decisions || []} />
      <div className="grid lg:grid-cols-2 gap-4">
        <EquityChart />
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
