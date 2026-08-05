-- Per-strategy bot_state + journal.strategy for dual engines.
-- Existing singleton row becomes strategy='rsi2'. Engine writes via DATABASE_URL.

-- Drop singleton check so we can hold one row per strategy.
ALTER TABLE public.bot_state DROP CONSTRAINT IF EXISTS bot_state_id_check;

ALTER TABLE public.bot_state
  ADD COLUMN IF NOT EXISTS strategy text;

UPDATE public.bot_state
SET strategy = 'rsi2'
WHERE strategy IS NULL;

ALTER TABLE public.bot_state
  ALTER COLUMN strategy SET NOT NULL;

-- Virtual cash for allocation-scoped engines (0 = use account cash / full book).
ALTER TABLE public.bot_state
  ADD COLUMN IF NOT EXISTS virtual_cash double precision NOT NULL DEFAULT 0;

CREATE UNIQUE INDEX IF NOT EXISTS bot_state_strategy_uidx
  ON public.bot_state (strategy);

-- Allow inserting additional strategy rows (id no longer forced to 1).
-- Keep id as serial-ish: use existing sequence or max+1 inserts from app.
CREATE SEQUENCE IF NOT EXISTS bot_state_id_seq;
SELECT setval(
  'bot_state_id_seq',
  GREATEST((SELECT COALESCE(MAX(id), 1) FROM public.bot_state), 1)
);
ALTER TABLE public.bot_state
  ALTER COLUMN id SET DEFAULT nextval('bot_state_id_seq');

-- Journal: tag rows by strategy (engine rows); actor/global rows may stay null.
ALTER TABLE public.journal
  ADD COLUMN IF NOT EXISTS strategy text;

UPDATE public.journal
SET strategy = 'rsi2'
WHERE strategy IS NULL AND actor IS NULL;

CREATE INDEX IF NOT EXISTS journal_strategy_idx ON public.journal (strategy);
