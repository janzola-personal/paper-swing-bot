import { Suspense } from "react";
import { Nav } from "@/components/Nav";
import { DashboardClient } from "@/components/dashboard/DashboardClient";
import { createClient } from "@/lib/supabase/server";
import { redirect } from "next/navigation";

export const dynamic = "force-dynamic";

export default async function DashboardPage() {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) redirect("/login");

  return (
    <>
      <Nav email={user.email} />
      <main className="max-w-[1200px] mx-auto px-4 py-6">
        <p className="text-xs uppercase tracking-[0.12em] text-[var(--accent)] m-0 mb-2">
          Observe · pause · flatten — no buy button
        </p>
        <h1 className="text-2xl m-0 mb-4 font-medium">Dashboard</h1>
        <Suspense fallback={<p className="text-[var(--muted)] text-sm">Loading…</p>}>
          <DashboardClient />
        </Suspense>
      </main>
    </>
  );
}
