import { Nav } from "@/components/Nav";
import { createClient } from "@/lib/supabase/server";
import { redirect } from "next/navigation";
import { readFile } from "node:fs/promises";
import path from "node:path";

export const dynamic = "force-dynamic";

const STAGES = ["BENCH", "BACKTEST-PASS", "PAPER", "LIVE-ELIGIBLE"] as const;

export default async function GatePage() {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) redirect("/login");

  let gatesText = "";
  try {
    gatesText = await readFile(path.join(process.cwd(), "content", "gates.md"), "utf-8");
  } catch {
    gatesText = "";
  }

  // gate_results table arrives in Part E — shell empty state for now.
  let hasResults = false;
  try {
    const { data, error } = await supabase.from("gate_results").select("id").limit(1);
    hasResults = !error && Array.isArray(data) && data.length > 0;
  } catch {
    hasResults = false;
  }

  return (
    <>
      <Nav email={user.email} />
      <main className="max-w-[900px] mx-auto px-4 py-6">
        <h1 className="text-2xl m-0 mb-2 font-medium">Gate</h1>
        <p className="text-sm text-[var(--muted)] mt-0 mb-6">
          Phase 2 scoreboard — thresholds vs measured results. Strategies promote
          {STAGES.map((s) => ` ${s}`).join(" →")}.
        </p>

        {!hasResults ? (
          <div className="border border-[var(--line)] p-6 mb-6">
            <p className="m-0 text-[var(--warn)]">
              No gate runs yet — complete Part E Prompt 11.
            </p>
          </div>
        ) : null}

        <div className="overflow-x-auto border border-[var(--line)]">
          <table className="w-full text-sm border-collapse">
            <thead>
              <tr className="text-left text-[var(--muted)] border-b border-[var(--line)]">
                <th className="p-3 font-normal">Strategy</th>
                <th className="p-3 font-normal">Stage</th>
                <th className="p-3 font-normal">Criterion</th>
                <th className="p-3 font-normal">Threshold</th>
                <th className="p-3 font-normal">Measured</th>
                <th className="p-3 font-normal">Pass/Fail</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td className="p-3 text-[var(--muted)]" colSpan={6}>
                  Empty until <code>gate_results</code> is populated.
                </td>
              </tr>
            </tbody>
          </table>
        </div>

        {gatesText ? (
          <pre className="mt-6 text-xs text-[var(--muted)] whitespace-pre-wrap border border-[var(--line)] p-4 overflow-x-auto">
            {gatesText}
          </pre>
        ) : null}
      </main>
    </>
  );
}
