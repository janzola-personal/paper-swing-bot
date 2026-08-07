-- Shadow position book for allocation-scoped engines (lev_trend).
-- Used when place_orders is false so virtual equity can MTM overnight.

ALTER TABLE public.bot_state
  ADD COLUMN IF NOT EXISTS shadow_positions_json jsonb NOT NULL DEFAULT '{}'::jsonb;
