-- Lock down bot tables: RLS on; anon has no access; authenticated may SELECT only.
-- Engine writes use DATABASE_URL (Postgres role bypasses RLS) or service_role.
-- Never grant INSERT/UPDATE/DELETE to anon or authenticated — mutations go
-- through the Python engine only (ARCHITECTURE.md).

ALTER TABLE public.bot_state ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.journal ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.equity_snapshots ENABLE ROW LEVEL SECURITY;

-- Drop any prior open policies if re-applied
DROP POLICY IF EXISTS bot_state_select_authenticated ON public.bot_state;
DROP POLICY IF EXISTS runs_select_authenticated ON public.runs;
DROP POLICY IF EXISTS journal_select_authenticated ON public.journal;
DROP POLICY IF EXISTS equity_snapshots_select_authenticated ON public.equity_snapshots;

-- Revoke broad defaults, then grant read-only to logged-in dashboard user
REVOKE ALL ON TABLE public.bot_state FROM anon, authenticated;
REVOKE ALL ON TABLE public.runs FROM anon, authenticated;
REVOKE ALL ON TABLE public.journal FROM anon, authenticated;
REVOKE ALL ON TABLE public.equity_snapshots FROM anon, authenticated;

GRANT SELECT ON TABLE public.bot_state TO authenticated;
GRANT SELECT ON TABLE public.runs TO authenticated;
GRANT SELECT ON TABLE public.journal TO authenticated;
GRANT SELECT ON TABLE public.equity_snapshots TO authenticated;

-- Single-owner paper bot: any authenticated user may read (signups disabled in Part C)
CREATE POLICY bot_state_select_authenticated
  ON public.bot_state
  FOR SELECT
  TO authenticated
  USING (true);

CREATE POLICY runs_select_authenticated
  ON public.runs
  FOR SELECT
  TO authenticated
  USING (true);

CREATE POLICY journal_select_authenticated
  ON public.journal
  FOR SELECT
  TO authenticated
  USING (true);

CREATE POLICY equity_snapshots_select_authenticated
  ON public.equity_snapshots
  FOR SELECT
  TO authenticated
  USING (true);
