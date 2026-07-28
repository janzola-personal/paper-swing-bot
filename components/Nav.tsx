import Link from "next/link";

const links = [
  { href: "/dashboard", label: "Dashboard" },
  { href: "/research", label: "Research" },
  { href: "/gate", label: "Gate" },
];

export function Nav({ email }: { email?: string | null }) {
  return (
    <header className="border-b border-[var(--line)] px-4 py-3 flex items-center justify-between gap-4">
      <div className="flex items-baseline gap-6">
        <Link href="/dashboard" className="text-lg tracking-wide no-underline text-[var(--fg)]">
          Paper Swing Bot
        </Link>
        <nav className="flex gap-4 text-sm text-[var(--muted)]">
          {links.map((l) => (
            <Link key={l.href} href={l.href} className="hover:text-[var(--accent)] no-underline text-inherit">
              {l.label}
            </Link>
          ))}
        </nav>
      </div>
      <div className="text-xs text-[var(--muted)] flex items-center gap-3">
        {email ? <span>{email}</span> : null}
        <form action="/auth/signout" method="post">
          <button
            type="submit"
            className="border border-[var(--line)] bg-transparent text-[var(--muted)] px-2 py-1 cursor-pointer text-xs"
          >
            Sign out
          </button>
        </form>
      </div>
    </header>
  );
}
