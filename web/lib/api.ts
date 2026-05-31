export class ApiError extends Error {
  constructor(message: string, public readonly status: number) {
    super(message);
    this.name = "ApiError";
  }
}

function extractDetail(errBody: unknown, fallback: string): string {
  if (!errBody || typeof errBody !== "object") return fallback;
  const body = errBody as Record<string, unknown>;
  const raw = body.detail ?? body.message;
  if (!raw) return fallback;
  if (typeof raw === "string") return raw;
  if (Array.isArray(raw)) {
    const items = raw.slice(0, 3).map((d: Record<string, unknown>) => String(d?.msg ?? JSON.stringify(d)));
    const extra = raw.length > 3 ? ` … (${raw.length - 3} more)` : "";
    return items.join("; ") + extra;
  }
  return String(raw);
}

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`/api${path}`);
  if (!res.ok) {
    let detail = `GET ${path} → ${res.status}`;
    try { detail = extractDetail(await res.json(), detail); } catch { /* ignore */ }
    throw new ApiError(detail, res.status);
  }
  return res.json() as Promise<T>;
}

async function post<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`/api${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    let detail = `POST ${path} → ${res.status}`;
    try { detail = extractDetail(await res.json(), detail); } catch { /* ignore */ }
    throw new ApiError(detail, res.status);
  }
  return res.json() as Promise<T>;
}

async function del<T>(path: string): Promise<T> {
  const res = await fetch(`/api${path}`, { method: "DELETE" });
  if (!res.ok) {
    let detail = `DELETE ${path} → ${res.status}`;
    try { detail = extractDetail(await res.json(), detail); } catch { /* ignore */ }
    throw new ApiError(detail, res.status);
  }
  return res.json() as Promise<T>;
}

export const api = { get, post, delete: del };
