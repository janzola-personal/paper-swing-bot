-- Paper swing bot state (Postgres source of truth).
-- No secrets in tables. Apply via Supabase CLI or dashboard SQL.

-- Singleton bot state (one row, id = 1)
CREATE TABLE IF NOT EXISTS bot_state (
    id integer PRIMARY KEY DEFAULT 1 CHECK (id = 1),
    peak_equity double precision NOT NULL DEFAULT 0,
    day_start_equity double precision NOT NULL DEFAULT 0,
    day_start_trading_day date,
    halted boolean NOT NULL DEFAULT false,
    halted_reason text NOT NULL DEFAULT '',
    day_halted_trading_day date,
    paused boolean NOT NULL DEFAULT false,
    last_run_date date,
    updated_at timestamptz NOT NULL DEFAULT now()
);

INSERT INTO bot_state (id) VALUES (1) ON CONFLICT (id) DO NOTHING;

-- Dual-scheduler idempotency: one successful claim per (trading_day, strategy)
CREATE TABLE IF NOT EXISTS runs (
    id bigserial PRIMARY KEY,
    trading_day date NOT NULL,
    strategy text NOT NULL,
    started_at timestamptz NOT NULL DEFAULT now(),
    completed_at timestamptz,
    status text NOT NULL,
    mode text NOT NULL,
    UNIQUE (trading_day, strategy)
);

CREATE INDEX IF NOT EXISTS runs_trading_day_idx ON runs (trading_day);

-- Decision log (same fields as journal.csv + actor / trading_day)
CREATE TABLE IF NOT EXISTS journal (
    id bigserial PRIMARY KEY,
    trading_day date,
    timestamp_utc timestamptz NOT NULL DEFAULT now(),
    symbol text NOT NULL,
    action text NOT NULL,
    qty integer NOT NULL DEFAULT 0,
    ref_price numeric,
    reason text,
    equity numeric,
    cash numeric,
    dry_run boolean NOT NULL DEFAULT true,
    actor text,
    run_id bigint REFERENCES runs (id)
);

CREATE INDEX IF NOT EXISTS journal_trading_day_idx ON journal (trading_day);

-- Paper equity curve for dashboard vs backtest
CREATE TABLE IF NOT EXISTS equity_snapshots (
    id bigserial PRIMARY KEY,
    trading_day date NOT NULL,
    strategy text NOT NULL,
    equity numeric NOT NULL,
    cash numeric NOT NULL,
    positions_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (trading_day, strategy)
);
