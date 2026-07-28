type Pos = {
  symbol: string;
  qty: number;
  avg_entry_price: number;
  current_price: number;
  unrealized_pl: number;
  unrealized_plpc: number;
};

export function Positions({ positions }: { positions: Pos[] }) {
  return (
    <section className="border border-[var(--line)] p-4">
      <h2 className="text-base m-0 mb-3 tracking-wide">Open positions</h2>
      {positions.length === 0 ? (
        <p className="text-sm text-[var(--muted)] m-0">Flat — no open positions.</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm border-collapse">
            <thead>
              <tr className="text-left text-[var(--muted)] border-b border-[var(--line)]">
                <th className="py-2 pr-3 font-normal">Symbol</th>
                <th className="py-2 pr-3 font-normal">Qty</th>
                <th className="py-2 pr-3 font-normal">Entry</th>
                <th className="py-2 pr-3 font-normal">Mark</th>
                <th className="py-2 font-normal">Unrealized</th>
              </tr>
            </thead>
            <tbody>
              {positions.map((p) => (
                <tr key={p.symbol} className="border-b border-[var(--line)]">
                  <td className="py-2 pr-3">{p.symbol}</td>
                  <td className="py-2 pr-3">{p.qty}</td>
                  <td className="py-2 pr-3">{p.avg_entry_price.toFixed(2)}</td>
                  <td className="py-2 pr-3">{p.current_price.toFixed(2)}</td>
                  <td className="py-2">
                    {p.unrealized_pl.toFixed(2)} ({(p.unrealized_plpc * 100).toFixed(2)}%)
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <p className="text-xs text-[var(--muted)] mt-3 mb-0">
        Bars-held / exit distance (rsi2 vs sma5) enrich from journal reasons on the
        next engine pass — UI never recomputes signals.
      </p>
    </section>
  );
}
