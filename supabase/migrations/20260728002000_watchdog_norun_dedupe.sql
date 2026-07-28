-- Dedupe NO RUN emails: one per trading day (NOTIFICATIONS.md §3).
ALTER TABLE public.bot_state
  ADD COLUMN IF NOT EXISTS watchdog_norun_sent_day date;
