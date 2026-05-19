import { NextRequest, NextResponse } from "next/server";

// Read at runtime on every request — no build-time dependency
function apiBase() {
  return (
    process.env.API_URL ||
    process.env.NEXT_PUBLIC_API_URL ||
    "http://localhost:8000"
  );
}

type Ctx = { params: { path: string[] } };

async function proxy(req: NextRequest, { params }: Ctx) {
  const upstream = `${apiBase()}/${params.path.join("/")}${req.nextUrl.search}`;

  const init: RequestInit = {
    method: req.method,
    headers: { "content-type": req.headers.get("content-type") ?? "application/json" },
  };

  if (req.method !== "GET" && req.method !== "HEAD") {
    init.body = await req.text();
  }

  try {
    const res = await fetch(upstream, init);
    const body = await res.arrayBuffer();
    return new NextResponse(body, {
      status: res.status,
      headers: {
        "content-type": res.headers.get("content-type") ?? "application/json",
      },
    });
  } catch {
    return NextResponse.json(
      { detail: `API non raggiungibile: ${upstream}` },
      { status: 503 }
    );
  }
}

export const GET = proxy;
export const POST = proxy;
export const PUT = proxy;
export const DELETE = proxy;
export const PATCH = proxy;
