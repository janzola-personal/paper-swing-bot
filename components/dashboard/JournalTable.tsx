"use client";

import { useMemo, useState } from "react";

type Row = {
  id: number;
  timestamp_utc: string;
  symbol: string;
  action: string;
  qty: number;
  ref_price: number | null;
  reason: string | null;
  actor: string | null;
};

type Filter = "all" | "trades" | "halts" | "errors";

function etTime(iso: string) {
  try {
    return new Intl.DateTimeFormat("en-US", {
      timeZone: "America/New_York",
      month: "short",
      day: "numeric",
      hour: "numeric",
      minute: "2-digit",
    }).format(new Date(iso));
  } catch {
    return iso;
  }
}

export function JournalTable({ rows }: { rows: Row[] }) {
  const [filter, setFilter] = useState<Filter>("all");
  const [expanded, setExpanded] = useState<number | null>(null);

  const filtered = useMemo(() => {
    return rows.filter((r) => {
      const a = r.action.toUpperCase();
      if (filter === "trades") return ["BUY", "SELL"].includes(a);
      if (filter === "halts")
        return a.includes("HALT") || a === "RESET_HALT" || (r.reason || "").toLowerCase().includes("halt");
      if (filter === "errors") return a.includes("ERROR") || (r.reason || "").toLowerCase().includes("error");
      return true;
    });
  }, [rows, filter]);

  return (
    <section id="journal" className="border border-[var(--line)] p-4">
      <div className="flex flex-wrap items-center justify-between gap-2 mb-3">
        <h2 className="text-base m-0 tracking-wide">Journal</h2>
        <div className="flex gap-1 text-xs">
          {(["all", "trades", "halts", "errors"] as Filter[]).map((f) => (
            <button
              key={f}
              type="button"
              onClick={() => setFilter(f)}
              className={`px-2 py-1 border cursor-pointer ${
                filter === f
                  ? "border-[var(--accent)] text-[var(--accent)] bg-transparent"
                  : "border-[var(--line)] text-[var(--muted)] bg-transparent"
              }`}
            >
              {f}
            </button>
          ))}
        </div>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm border-collapse">
          <thead>
            <tr className="text-left text-[var(--muted)] border-b border-[var(--line)]">
              <th className="py-2 pr-3 font-normal">Time (ET)</th>
              <th className="py-2 pr-3 font-normal">Symbol</th>
              <th className="py-2 pr-3 font-normal">Action</th>
              <th className="py-2 pr-3 font-normal">Qty</th>
              <th className="py-2 pr-3 font-normal">Price</th>
              <th className="py-2 font-normal">Reason</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((r) => {
              const reason = r.reason || "";
              const short = reason.length > 80 && expanded !== r.id ? `${reason.slice(0, 80)}…` : reason;
              return (
                <tr key={r.id} className="border-b border-[var(--line)] align-top">
                  <td className="py-2 pr-3 whitespace-nowrap">{etTime(r.timestamp_utc)}</td>
                  <td className="py-2 pr-3">{r.symbol}</td>
                  <td className="py-2 pr-3">{r.action}</td>
                  <td className="py-2 pr-3">{r.qty}</td>
                  <td className="py-2 pr-3">
                    {r.ref_price != null ? Number(r.ref_price).toFixed(2) : "—"}
                  </td>
                  <td className="py-2 text-[var(--muted)]">
                    <button
                      type="button"
                      className="bg-transparent border-0 text-inherit p-0 text-left cursor-pointer"
                      onClick={() => setExpanded(expanded === r.id ? null : r.id)}
                    >
                      {short}
                      {r.actor ? ` · actor=${r.actor}` : ""}
                    </button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}
