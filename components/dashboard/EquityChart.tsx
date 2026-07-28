"use client";

import { useEffect, useState } from "react";
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

type Point = { trading_day: string; equity: number };

export function EquityChart() {
  const [logScale, setLogScale] = useState(false);
  const [rows, setRows] = useState<
    { trading_day: string; paper?: number; expected?: number; buy_hold?: number }[]
  >([]);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      const res = await fetch("/api/backtest-window", { cache: "no-store" });
      if (!res.ok) {
        if (!cancelled) setErr("Could not load equity window");
        return;
      }
      const data = await res.json();
      const byDay = new Map<
        string,
        { trading_day: string; paper?: number; expected?: number; buy_hold?: number }
      >();
      for (const p of (data.paper || []) as Point[]) {
        byDay.set(p.trading_day, {
          ...(byDay.get(p.trading_day) || { trading_day: p.trading_day }),
          paper: p.equity,
        });
      }
      for (const p of (data.expected || []) as Point[]) {
        byDay.set(p.trading_day, {
          ...(byDay.get(p.trading_day) || { trading_day: p.trading_day }),
          expected: p.equity,
        });
      }
      for (const p of (data.buy_hold || []) as Point[]) {
        byDay.set(p.trading_day, {
          ...(byDay.get(p.trading_day) || { trading_day: p.trading_day }),
          buy_hold: p.equity,
        });
      }
      if (!cancelled) {
        setRows([...byDay.values()].sort((a, b) => a.trading_day.localeCompare(b.trading_day)));
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <section className="border border-[var(--line)] p-4 h-full">
      <div className="flex items-center justify-between gap-2 mb-2">
        <h2 className="text-base m-0 tracking-wide">Paper vs backtest</h2>
        <label className="text-xs text-[var(--muted)] flex items-center gap-1">
          <input
            type="checkbox"
            checked={logScale}
            onChange={(e) => setLogScale(e.target.checked)}
          />
          log scale
        </label>
      </div>
      {err ? <p className="text-sm text-[var(--danger)]">{err}</p> : null}
      {!rows.length && !err ? (
        <p className="text-sm text-[var(--muted)]">
          No equity snapshots yet. After shadow/paper runs, paper equity appears here
          beside the backtest expectation (same capital window).
        </p>
      ) : (
        <div className="h-64">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={rows}>
              <CartesianGrid stroke="rgba(232,240,234,0.08)" />
              <XAxis dataKey="trading_day" tick={{ fill: "#9fb5a6", fontSize: 10 }} minTickGap={24} />
              <YAxis
                scale={logScale ? "log" : "auto"}
                domain={["auto", "auto"]}
                tick={{ fill: "#9fb5a6", fontSize: 10 }}
                width={56}
              />
              <Tooltip
                contentStyle={{
                  background: "#15261f",
                  border: "1px solid rgba(232,240,234,0.12)",
                }}
              />
              <Legend />
              <Line type="monotone" dataKey="paper" name="Paper" stroke="#8fb89a" dot={false} strokeWidth={2} />
              <Line
                type="monotone"
                dataKey="expected"
                name="Backtest expect"
                stroke="#6f9fbf"
                dot={false}
                strokeWidth={1.5}
              />
              <Line
                type="monotone"
                dataKey="buy_hold"
                name="Buy & hold"
                stroke="#9fb5a6"
                strokeDasharray="4 4"
                dot={false}
                strokeWidth={1}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}
    </section>
  );
}
