"use client";

import { useState } from "react";

type Status = {
  equity: number | null;
  cash: number | null;
  day_pnl_pct: number | null;
  market_open: boolean | null;
  engine_label?: string;
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
  shadow_mode: boolean;
};

function fmtMoney(n: number | null) {
  if (n == null || Number.isNaN(n)) return "—";
  return n.toLocaleString("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
  });
}

function fmtPct(n: number | null) {
  if (n == null) return "—";
  return `${(n * 100).toFixed(2)}%`;
}

export function StatusStrip({
  status,
  strategy,
  onRefresh,
}: {
  status: Status | null;
  strategy: string;
  onRefresh: () => void;
}) {
  const [busy, setBusy] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [password, setPassword] = useState("");
  const [dialog, setDialog] = useState<"flatten" | "reset" | "flatten_all" | null>(
    null,
  );

  const engineName = strategy === "lev_trend" ? "lev_trend" : "swing";

  async function pauseToggle() {
    if (!status?.state) return;
    const next = !status.state.paused;
    if (
      !confirm(
        next
          ? `Pause ${status.engine_label || engineName}? That engine will not place orders.`
          : `Resume ${status.engine_label || engineName}?`,
      )
    ) {
      return;
    }
    setBusy("pause");
    setMsg(null);
    const res = await fetch("/api/pause", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ paused: next, engine: engineName }),
    });
    const data = await res.json();
    setBusy(null);
    if (!res.ok) {
      setMsg(data.error || "pause failed");
      return;
    }
    onRefresh();
  }

  async function submitSensitive(kind: "flatten" | "reset" | "flatten_all") {
    setBusy(kind);
    setMsg(null);
    const path = kind === "reset" ? "/api/reset-halt" : "/api/flatten";
    const body =
      kind === "reset"
        ? { confirm: true, password, engine: engineName }
        : {
            confirm: true,
            password,
            engine: kind === "flatten_all" ? "all" : engineName,
          };
    const res = await fetch(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const data = await res.json();
    setBusy(null);
    if (!res.ok) {
      setMsg(data.error || `${kind} failed`);
      return;
    }
    setDialog(null);
    setPassword("");
    setMsg(
      kind === "reset"
        ? "Halt cleared; peak re-anchors next run."
        : kind === "flatten_all"
          ? "Account-wide flatten requested."
          : "Engine flatten requested.",
    );
    onRefresh();
  }

  const stale = status?.last_run_stale;
  const halted = status?.state?.halted;

  return (
    <section className="border border-[var(--line)] p-4">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-x-6 gap-y-2 text-sm">
          <div>
            <div className="text-[var(--muted)] text-xs uppercase tracking-wide">Equity</div>
            <div className="text-xl">{fmtMoney(status?.equity ?? null)}</div>
          </div>
          <div>
            <div className="text-[var(--muted)] text-xs uppercase tracking-wide">Day P&amp;L</div>
            <div className="text-xl">{fmtPct(status?.day_pnl_pct ?? null)}</div>
          </div>
          <div>
            <div className="text-[var(--muted)] text-xs uppercase tracking-wide">Cash</div>
            <div className="text-xl">{fmtMoney(status?.cash ?? null)}</div>
          </div>
          <div>
            <div className="text-[var(--muted)] text-xs uppercase tracking-wide">Market</div>
            <div className="text-xl">
              {status?.market_open == null ? "—" : status.market_open ? "Open" : "Closed"}
            </div>
          </div>
        </div>

        <div className="flex flex-wrap gap-2 items-center">
          <button
            type="button"
            disabled={!!busy}
            onClick={pauseToggle}
            className="border border-[var(--warn)] text-[var(--warn)] bg-transparent px-3 py-1.5 text-sm cursor-pointer"
          >
            {status?.state?.paused ? "Resume trading" : "Pause trading"}
          </button>
          <button
            type="button"
            disabled={!!busy}
            onClick={() => setDialog("flatten")}
            className="border border-[var(--danger)] text-[var(--danger)] bg-transparent px-3 py-1.5 text-sm cursor-pointer"
          >
            Flatten engine
          </button>
          <button
            type="button"
            disabled={!!busy}
            onClick={() => setDialog("flatten_all")}
            className="border border-[var(--danger)] text-[var(--muted)] bg-transparent px-3 py-1.5 text-sm cursor-pointer"
          >
            Flatten all
          </button>
          {halted ? (
            <button
              type="button"
              disabled={!!busy}
              onClick={() => setDialog("reset")}
              className="border border-[var(--accent)] text-[var(--accent)] bg-transparent px-3 py-1.5 text-sm cursor-pointer"
            >
              Reset halt
            </button>
          ) : null}
        </div>
      </div>

      <div className="mt-3 flex flex-wrap gap-3 text-sm">
        <span
          className={stale ? "text-[var(--danger)] font-medium" : "text-[var(--muted)]"}
        >
          Last run:{" "}
          {status?.last_run
            ? `${status.last_run.trading_day} · ${status.last_run.status} · ${status.last_run.mode}`
            : "none"}
          {stale ? " — missing/stale for today’s session" : ""}
        </span>
        {status?.state?.paused ? (
          <span className="text-[var(--warn)]">Paused</span>
        ) : null}
        {status?.shadow_mode ? (
          <span className="text-[var(--accent)]">Shadow mode</span>
        ) : null}
      </div>

      {halted ? (
        <div className="mt-3 border border-[var(--danger)] bg-[rgba(217,107,107,0.12)] p-3 text-sm text-[var(--danger)]">
          HARD HALT: {status?.state?.halted_reason}
        </div>
      ) : null}

      {msg ? <p className="mt-2 text-sm text-[var(--muted)]">{msg}</p> : null}

      {dialog ? (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4">
          <div className="bg-[#15261f] border border-[var(--line)] p-5 max-w-md w-full">
            <h3 className="text-lg m-0 mb-2">
              {dialog === "reset"
                ? "Confirm reset halt"
                : dialog === "flatten_all"
                  ? "Confirm flatten ALL"
                  : "Confirm flatten engine"}
            </h3>
            <p className="text-sm text-[var(--muted)] mt-0">
              {dialog === "reset"
                ? "Clears the hard halt for this engine and re-anchors peak equity on the next run. Re-enter your password."
                : dialog === "flatten_all"
                  ? "Emergency: sells every open position in the shared paper account. Re-enter your password."
                  : `Sells only this engine’s symbols (${status?.engine_label || engineName}). Re-enter your password.`}
            </p>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="Password"
              className="w-full mt-2 mb-3 px-3 py-2 bg-black/30 border border-[var(--line)] text-[var(--fg)]"
            />
            <div className="flex gap-2 justify-end">
              <button
                type="button"
                className="bg-transparent border border-[var(--line)] text-[var(--muted)] px-3 py-1.5 cursor-pointer"
                onClick={() => {
                  setDialog(null);
                  setPassword("");
                }}
              >
                Cancel
              </button>
              <button
                type="button"
                disabled={!!busy || !password}
                className="border border-[var(--danger)] text-[var(--danger)] bg-transparent px-3 py-1.5 cursor-pointer"
                onClick={() => submitSensitive(dialog)}
              >
                {busy ? "Working…" : "Confirm"}
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </section>
  );
}
