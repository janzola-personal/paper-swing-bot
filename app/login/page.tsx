"use client";

import { FormEvent, useState } from "react";
import { createClient } from "@/lib/supabase/client";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense } from "react";

function LoginForm() {
  const router = useRouter();
  const params = useSearchParams();
  const next = params.get("next") || "/dashboard";
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    const supabase = createClient();
    const { error: err } = await supabase.auth.signInWithPassword({
      email,
      password,
    });
    setBusy(false);
    if (err) {
      setError(err.message);
      return;
    }
    router.replace(next.startsWith("/") ? next : "/dashboard");
    router.refresh();
  }

  return (
    <main className="min-h-screen flex items-center justify-center px-4">
      <form
        onSubmit={onSubmit}
        className="w-full max-w-md border border-[var(--line)] p-8 bg-black/20"
      >
        <p className="text-xs uppercase tracking-[0.12em] text-[var(--accent)] m-0 mb-3">
          Paper only · single user
        </p>
        <h1 className="text-3xl m-0 mb-2 font-medium">Paper Swing Bot</h1>
        <p className="text-sm text-[var(--muted)] mt-0 mb-6">
          Email + password. No public signup — account is created in Supabase.
        </p>
        <label className="block text-xs text-[var(--muted)] mb-1">Email</label>
        <input
          type="email"
          required
          autoComplete="username"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          className="w-full mb-3 px-3 py-2 bg-black/30 border border-[var(--line)] text-[var(--fg)]"
        />
        <label className="block text-xs text-[var(--muted)] mb-1">Password</label>
        <input
          type="password"
          required
          autoComplete="current-password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          className="w-full mb-4 px-3 py-2 bg-black/30 border border-[var(--line)] text-[var(--fg)]"
        />
        {error ? <p className="text-sm text-[var(--danger)] mb-3">{error}</p> : null}
        <button
          type="submit"
          disabled={busy}
          className="w-full py-2.5 border border-[var(--accent)] text-[var(--accent)] bg-transparent cursor-pointer"
        >
          {busy ? "Signing in…" : "Sign in"}
        </button>
      </form>
    </main>
  );
}

export default function LoginPage() {
  return (
    <Suspense fallback={<main className="p-8 text-[var(--muted)]">Loading…</main>}>
      <LoginForm />
    </Suspense>
  );
}
