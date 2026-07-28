/**
 * Server-side proxy from Next.js → Python Vercel functions.
 * AuthN already done by Supabase session; this adds CRON_SECRET for the engine.
 */

function engineBaseUrl(): string {
  if (process.env.ENGINE_BASE_URL) return process.env.ENGINE_BASE_URL.replace(/\/$/, "");
  if (process.env.VERCEL_URL) return `https://${process.env.VERCEL_URL}`;
  return "http://127.0.0.1:3000";
}

function engineSecret(): string {
  return (
    process.env.CRON_SECRET ||
    process.env.HOSTED_RUN_SECRET ||
    process.env.ENGINE_ACTION_SECRET ||
    ""
  );
}

export async function callEngine(
  path: string,
  body: Record<string, unknown>,
): Promise<{ ok: boolean; status: number; data: Record<string, unknown> }> {
  const secret = engineSecret();
  if (!secret) {
    return {
      ok: false,
      status: 503,
      data: { error: "CRON_SECRET / HOSTED_RUN_SECRET not configured" },
    };
  }
  const url = `${engineBaseUrl()}${path.startsWith("/") ? path : `/${path}`}`;
  const res = await fetch(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${secret}`,
    },
    body: JSON.stringify(body),
    cache: "no-store",
  });
  let data: Record<string, unknown> = {};
  try {
    data = (await res.json()) as Record<string, unknown>;
  } catch {
    data = { error: "invalid engine response" };
  }
  return { ok: res.ok, status: res.status, data };
}

/** Local/dev fallback: invoke Python actions via child process when ENGINE_INLINE=1. */
export async function callEngineOrInline(
  action: "pause" | "flatten" | "reset_halt",
  body: Record<string, unknown>,
): Promise<{ ok: boolean; status: number; data: Record<string, unknown> }> {
  const preferInline =
    process.env.ENGINE_INLINE === "1" ||
    (!process.env.VERCEL && process.env.ENGINE_INLINE !== "0");
  if (preferInline) {
    const { spawnSync } = await import("node:child_process");
    const script = `
import json, os, sys
sys.path.insert(0, os.getcwd())
from actions import set_paused, flatten_now, reset_hard_halt
body = json.loads(sys.argv[1])
actor = body.get("actor") or ""
if sys.argv[2] == "pause":
    print(json.dumps(set_paused(bool(body.get("paused")), actor)))
elif sys.argv[2] == "flatten":
    print(json.dumps(flatten_now(actor)))
else:
    print(json.dumps(reset_hard_halt(actor)))
`;
    const py = process.env.PYTHON || ".venv/bin/python";
    const r = spawnSync(py, ["-c", script, JSON.stringify(body), action], {
      encoding: "utf-8",
      env: process.env,
    });
    if (r.status !== 0) {
      return {
        ok: false,
        status: 500,
        data: { error: r.stderr || r.stdout || "inline engine failed" },
      };
    }
    try {
      return { ok: true, status: 200, data: JSON.parse(r.stdout.trim()) };
    } catch {
      return { ok: false, status: 500, data: { error: "bad inline json" } };
    }
  }

  const pathMap = {
    pause: "/api/engine_pause",
    flatten: "/api/engine_flatten",
    reset_halt: "/api/engine_reset_halt",
  } as const;
  return callEngine(pathMap[action], body);
}
