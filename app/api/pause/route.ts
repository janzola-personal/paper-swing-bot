import { NextRequest, NextResponse } from "next/server";
import { requireUser } from "@/lib/auth";
import { callEngineOrInline } from "@/lib/engine-proxy";

export const dynamic = "force-dynamic";

export async function POST(req: NextRequest) {
  const { user, error } = await requireUser();
  if (error || !user?.email) {
    return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  }
  let body: { paused?: boolean; engine?: string } = {};
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: "invalid json" }, { status: 400 });
  }
  if (typeof body.paused !== "boolean") {
    return NextResponse.json({ error: "paused boolean required" }, { status: 400 });
  }
  const result = await callEngineOrInline("pause", {
    paused: body.paused,
    actor: user.email,
    engine: body.engine || "swing",
  });
  return NextResponse.json(result.data, { status: result.status });
}
