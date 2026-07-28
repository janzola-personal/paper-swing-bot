type Row = {
  symbol: string;
  action: string;
  qty: number;
  ref_price: number | null;
  reason: string | null;
};

export function TodayDecisions({ rows }: { rows: Row[] }) {
  return (
    <section className="border border-[var(--line)] p-4">
      <h2 className="text-base m-0 mb-3 tracking-wide">Today&apos;s decision</h2>
      {rows.length === 0 ? (
        <p className="text-sm text-[var(--muted)] m-0">
          No journal rows for today&apos;s trading day yet. Verdicts always show
          their inputs (rsi / sma thresholds) once the after-close run lands.
        </p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm border-collapse">
            <thead>
              <tr className="text-left text-[var(--muted)] border-b border-[var(--line)]">
                <th className="py-2 pr-3 font-normal">Symbol</th>
                <th className="py-2 pr-3 font-normal">Action</th>
                <th className="py-2 pr-3 font-normal">Qty</th>
                <th className="py-2 pr-3 font-normal">Ref</th>
                <th className="py-2 font-normal">Inputs / note</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r, i) => (
                <tr key={`${r.symbol}-${i}`} className="border-b border-[var(--line)] align-top">
                  <td className="py-2 pr-3">{r.symbol}</td>
                  <td className="py-2 pr-3 uppercase">{r.action}</td>
                  <td className="py-2 pr-3">{r.qty}</td>
                  <td className="py-2 pr-3">
                    {r.ref_price != null ? Number(r.ref_price).toFixed(2) : "—"}
                  </td>
                  <td className="py-2 text-[var(--muted)]">{r.reason || "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
