import { NextResponse } from "next/server";

/** Public health check — no auth (excluded from middleware matcher). */
export async function GET() {
  return NextResponse.json({ ok: true, service: "paper-swing-bot" });
}
