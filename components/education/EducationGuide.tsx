"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

export type EducationSection = {
  id: string;
  title: string;
};

/** Map markdown ## headings to stable anchor ids (must match EDUCATION.md). */
export const EDUCATION_SECTIONS: EducationSection[] = [
  { id: "start-here-what-this-app-is", title: "Start here" },
  { id: "what-happens-each-trading-day", title: "Daily flow" },
  { id: "key-concepts", title: "Key concepts" },
  { id: "strategies-you-have-today", title: "Strategies" },
  { id: "paper-testing-timeline-swing-rsi2", title: "Paper timeline" },
  { id: "weekly-routine-while-paper-trading", title: "Weekly routine" },
  { id: "how-to-create-a-new-strategy", title: "New strategies" },
  { id: "day-trading-strategies-intraday-lab", title: "Day trading" },
  { id: "the-promotion-gate", title: "Promotion gate" },
  { id: "paper-to-real-money-when-how-and-why-not-yet", title: "Paper → live" },
  { id: "dashboard-controls-what-each-button-means", title: "Dashboard" },
  { id: "glossary", title: "Glossary" },
  { id: "your-first-week-checklist", title: "First week" },
];

function slugify(text: string): string {
  return text
    .toLowerCase()
    .replace(/[^\w\s-]/g, "")
    .replace(/\s+/g, "-")
    .replace(/-+/g, "-")
    .trim();
}

type Props = {
  markdown: string;
};

export function EducationGuide({ markdown }: Props) {
  const sections = useMemo(() => EDUCATION_SECTIONS, []);
  const [activeId, setActiveId] = useState(sections[0]?.id ?? "");

  useEffect(() => {
    const obs = new IntersectionObserver(
      (entries) => {
        for (const e of entries) {
          if (e.isIntersecting) {
            setActiveId(e.target.id);
            break;
          }
        }
      },
      { rootMargin: "-20% 0px -70% 0px", threshold: 0 },
    );
    for (const s of sections) {
      const el = document.getElementById(s.id);
      if (el) obs.observe(el);
    }
    return () => obs.disconnect();
  }, [sections]);

  const scrollTo = useCallback((id: string) => {
    document.getElementById(id)?.scrollIntoView({ behavior: "smooth", block: "start" });
    setActiveId(id);
  }, []);

  return (
    <div className="flex flex-col lg:flex-row gap-8 items-start">
      <aside className="lg:w-52 shrink-0 w-full lg:sticky lg:top-4 border border-[var(--line)] p-4 bg-[rgba(0,0,0,0.15)]">
        <p className="text-xs uppercase tracking-wide text-[var(--muted)] m-0 mb-3">Guided path</p>
        <ol className="list-none m-0 p-0 text-sm space-y-1">
          {sections.map((s, i) => (
            <li key={s.id}>
              <button
                type="button"
                onClick={() => scrollTo(s.id)}
                className={`w-full text-left border-0 bg-transparent cursor-pointer py-1 px-0 text-sm ${
                  activeId === s.id ? "text-[var(--accent)]" : "text-[var(--muted)] hover:text-[var(--fg)]"
                }`}
              >
                <span className="text-[var(--line)] mr-2">{i + 1}.</span>
                {s.title}
              </button>
            </li>
          ))}
        </ol>
        <div className="mt-4 pt-4 border-t border-[var(--line)] text-xs text-[var(--muted)] space-y-2">
          <p className="m-0">Related pages:</p>
          <Link href="/dashboard" className="block text-[var(--accent)] no-underline">
            Dashboard →
          </Link>
          <Link href="/research" className="block text-[var(--accent)] no-underline">
            Research →
          </Link>
          <Link href="/gate" className="block text-[var(--accent)] no-underline">
            Gate →
          </Link>
        </div>
      </aside>

      <article className="flex-1 min-w-0 prose-research border border-[var(--line)] p-6 text-sm leading-relaxed [&_table]:w-full [&_table]:border-collapse [&_th]:border [&_th]:border-[var(--line)] [&_th]:p-2 [&_th]:text-left [&_td]:border [&_td]:border-[var(--line)] [&_td]:p-2 [&_pre]:text-xs [&_pre]:overflow-x-auto [&_blockquote]:border-l-2 [&_blockquote]:border-[var(--accent)] [&_blockquote]:pl-4 [&_blockquote]:text-[var(--muted)] [&_h1]:text-xl [&_h2]:text-lg [&_h2]:mt-8 [&_h2]:scroll-mt-4 [&_h3]:text-base [&_a]:text-[var(--accent)]">
        <ReactMarkdown
          remarkPlugins={[remarkGfm]}
          components={{
            h2: ({ children }) => {
              const text = String(children);
              const id = slugify(text);
              return (
                <h2 id={id} className="font-medium">
                  {children}
                </h2>
              );
            },
            a: ({ href, children }) => {
              if (href?.startsWith("/")) {
                return (
                  <Link href={href} className="text-[var(--accent)]">
                    {children}
                  </Link>
                );
              }
              return (
                <a href={href} target="_blank" rel="noreferrer" className="text-[var(--accent)]">
                  {children}
                </a>
              );
            },
          }}
        >
          {markdown}
        </ReactMarkdown>
      </article>
    </div>
  );
}
