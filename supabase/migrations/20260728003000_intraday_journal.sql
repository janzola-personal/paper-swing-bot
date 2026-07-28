-- Intraday journal (separate from swing journal)
CREATE TABLE IF NOT EXISTS intraday_journal (
    id bigserial PRIMARY KEY,
    trading_day date,
    timestamp_utc timestamptz NOT NULL DEFAULT now(),
    symbol text NOT NULL,
    action text NOT NULL,
    qty integer NOT NULL DEFAULT 0,
    ref_price numeric,
    reason text,
    dry_run boolean NOT NULL DEFAULT true
);

CREATE INDEX IF NOT EXISTS intraday_journal_trading_day_idx ON intraday_journal (trading_day);
