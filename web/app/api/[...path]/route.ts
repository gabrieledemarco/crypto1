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

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 30_000);

  try {
    const res = await fetch(upstream, { ...init, signal: controller.signal });
    const body = await res.arrayBuffer();
    return new NextResponse(body, {
      status: res.status,
      headers: {
        "content-type": res.headers.get("content-type") ?? "application/json",
      },
    });
  } catch (err: unknown) {
    const isTimeout = err instanceof Error && err.name === "AbortError";
    return NextResponse.json(
      { detail: isTimeout ? "API request timed out" : "API non raggiungibile" },
      { status: isTimeout ? 504 : 503 }
    );
  } finally {
    clearTimeout(timer);
  }
}

export const GET = proxy;
export const POST = proxy;
export const PUT = proxy;
export const DELETE = proxy;
export const PATCH = proxy;
