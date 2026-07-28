import { EducationGuide } from "@/components/education/EducationGuide";
import { Nav } from "@/components/Nav";
import { createClient } from "@/lib/supabase/server";
import { redirect } from "next/navigation";
import { readFile } from "node:fs/promises";
import path from "node:path";

export const dynamic = "force-dynamic";

const FALLBACK = `# Education

Run locally and commit \`content/EDUCATION.md\` for the full guided tour.
`;

export default async function EducationPage() {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) redirect("/login");

  let markdown = FALLBACK;
  try {
    markdown = await readFile(path.join(process.cwd(), "content", "EDUCATION.md"), "utf-8");
  } catch {
    /* fallback */
  }

  return (
    <>
      <Nav email={user.email} />
      <main className="max-w-[1100px] mx-auto px-4 py-6">
        <header className="mb-6">
          <h1 className="text-2xl m-0 mb-2 font-medium">Education</h1>
          <p className="text-sm text-[var(--muted)] mt-0 mb-0 max-w-[70ch]">
            Guided training: what this app does, the concepts behind it, how to paper-test
            swing strategies, how intraday research works, and when (if ever) real money
            enters the picture. Paper only today.
          </p>
        </header>
        <EducationGuide markdown={markdown} />
      </main>
    </>
  );
}
