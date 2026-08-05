import { NextRequest, NextResponse } from "next/server";
import { requireUser, verifyPassword } from "@/lib/auth";
import { callEngineOrInline } from "@/lib/engine-proxy";

export const dynamic = "force-dynamic";

export async function POST(req: NextRequest) {
  const { user, error } = await requireUser();
  if (error || !user?.email) {
    return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  }
  let body: { password?: string; confirm?: boolean; engine?: string } = {};
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: "invalid json" }, { status: 400 });
  }
  if (!body.confirm) {
    return NextResponse.json({ error: "confirm required" }, { status: 400 });
  }
  if (!body.password) {
    return NextResponse.json({ error: "password re-entry required" }, { status: 400 });
  }
  const ok = await verifyPassword(user.email, body.password);
  if (!ok) {
    return NextResponse.json({ error: "password incorrect" }, { status: 403 });
  }
  const result = await callEngineOrInline("reset_halt", {
    actor: user.email,
    engine: body.engine || "swing",
  });
  return NextResponse.json(result.data, { status: result.status });
}
