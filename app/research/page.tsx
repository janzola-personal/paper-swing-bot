import { Nav } from "@/components/Nav";
import { createClient } from "@/lib/supabase/server";
import { redirect } from "next/navigation";
import { readFile } from "node:fs/promises";
import path from "node:path";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

export const dynamic = "force-dynamic";

export default async function ResearchPage() {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) redirect("/login");

  let markdown = "# Research report\n\nNo committed report yet. Run `python build_report.py` and copy into `content/REPORT.md`.";
  try {
    markdown = await readFile(path.join(process.cwd(), "content", "REPORT.md"), "utf-8");
  } catch {
    /* keep fallback */
  }

  return (
    <>
      <Nav email={user.email} />
      <main className="max-w-[900px] mx-auto px-4 py-6">
        <div className="flex flex-wrap items-end justify-between gap-3 mb-4">
          <div>
            <h1 className="text-2xl m-0 font-medium">Research</h1>
            <p className="text-sm text-[var(--muted)] mt-1 mb-0">
              Read-only backtest report. Long jobs run via GitHub Actions{" "}
              <code>workflow_dispatch</code>, not inline on Vercel.
            </p>
          </div>
          <a
            className="text-sm text-[var(--accent)]"
            href="https://github.com/janzola-personal/paper-swing-bot/actions/workflows/research.yml"
            target="_blank"
            rel="noreferrer"
          >
            Re-run backtest (Actions) →
          </a>
        </div>
        <article className="prose-research border border-[var(--line)] p-6 text-sm leading-relaxed [&_table]:w-full [&_table]:border-collapse [&_th]:border [&_th]:border-[var(--line)] [&_th]:p-2 [&_th]:text-left [&_td]:border [&_td]:border-[var(--line)] [&_td]:p-2 [&_img]:max-w-full [&_h1]:text-xl [&_h2]:text-lg [&_h2]:mt-6 [&_a]:text-[var(--accent)]">
          <ReactMarkdown
            remarkPlugins={[remarkGfm]}
            components={{
              img: ({ src, alt }) => {
                const raw = typeof src === "string" ? src : undefined;
                if (!raw) return null;
                const url =
                  raw.startsWith("http") || raw.startsWith("/")
                    ? raw
                    : `/research/equity/${raw.replace(/^\.\//, "")}`;
                return (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img src={url} alt={alt ?? ""} className="max-w-full h-auto my-4" />
                );
              },
            }}
          >
            {markdown}
          </ReactMarkdown>
        </article>
        <p className="text-xs text-[var(--muted)] mt-4">
          Equity charts live under <code>/research/equity/</code> (regenerate via{" "}
          <code>python build_report.py</code>). Use the dashboard for interactive paper vs
          backtest.
        </p>
      </main>
    </>
  );
}
