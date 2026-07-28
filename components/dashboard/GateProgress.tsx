export type GateStats = {
  days: number;
  trades: number;
  overrides: number;
  halts: number;
  paper_start: string | null;
  days_target: number;
  trades_target: number;
};

export function GateProgress({
  submitEnabled,
  gate,
}: {
  submitEnabled: boolean;
  gate: GateStats | null;
}) {
  if (!submitEnabled) {
    return (
      <section className="border border-[var(--line)] p-4 opacity-70">
        <h2 className="text-base m-0 mb-2 tracking-wide">Gate progress (Stage B)</h2>
        <p className="text-sm text-[var(--muted)] m-0">
          Collapsed while shadow / submit-off. Enable paper submit
          (<code>BOT_SUBMIT=true</code>, shadow off) to track Days / 60, Trades / 40,
          manual overrides (must stay 0), and halts.
        </p>
      </section>
    );
  }

  const days = gate?.days ?? 0;
  const trades = gate?.trades ?? 0;
  const overrides = gate?.overrides ?? 0;
  const halts = gate?.halts ?? 0;
  const daysTarget = gate?.days_target ?? 60;
  const tradesTarget = gate?.trades_target ?? 40;

  return (
    <section className="border border-[var(--line)] p-4">
      <h2 className="text-base m-0 mb-1 tracking-wide">Gate progress (Stage B)</h2>
      <p className="text-xs text-[var(--muted)] mt-0 mb-3">
        Paper submit window
        {gate?.paper_start ? ` from ${gate.paper_start}` : " (starts on first submit run)"}
        . Alpaca market DAY orders queue after close → next open.
      </p>
      <Bar label={`Days ${days} / ${daysTarget}`} value={days / daysTarget} />
      <Bar
        label={`Trades ${trades} / ${tradesTarget}`}
        value={Math.min(trades / tradesTarget, 1)}
      />
      <Bar
        label={`Manual overrides ${overrides} / 0`}
        value={overrides > 0 ? 1 : 0}
        good={overrides === 0}
        bad={overrides > 0}
      />
      <p className="text-sm text-[var(--muted)] mt-3 mb-0">
        Halts: {halts}{" "}
        <a href="#journal" className="text-[var(--accent)]">
          → journal
        </a>
      </p>
    </section>
  );
}

function Bar({
  label,
  value,
  good,
  bad,
}: {
  label: string;
  value: number;
  good?: boolean;
  bad?: boolean;
}) {
  const color = bad ? "var(--danger)" : good ? "var(--ok)" : "var(--accent)";
  return (
    <div className="mb-2">
      <div className="text-xs text-[var(--muted)] mb-1">{label}</div>
      <div className="h-2 bg-black/30">
        <div
          className="h-2"
          style={{
            width: `${Math.max(0, Math.min(1, value)) * 100}%`,
            background: color,
          }}
        />
      </div>
    </div>
  );
}
