function extractDetail(errBody: unknown, fallback: string): string {
  if (!errBody || typeof errBody !== "object") return fallback;
  const body = errBody as Record<string, unknown>;
  const raw = body.detail ?? body.message;
  if (!raw) return fallback;
  if (typeof raw === "string") return raw;
  if (Array.isArray(raw))
    return raw.map((d) => (typeof d === "object" && d !== null ? (d as Record<string, unknown>).msg ?? JSON.stringify(d) : String(d))).join("; ");
  return String(raw);
}

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`/api${path}`);
  if (!res.ok) {
    let detail = `GET ${path} → ${res.status}`;
    try { detail = extractDetail(await res.json(), detail); } catch {}
    const err = new Error(detail);
    (err as any).status = res.status;
    throw err;
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
    try { detail = extractDetail(await res.json(), detail); } catch {}
    const err = new Error(detail);
    (err as any).status = res.status;
    throw err;
  }
  return res.json() as Promise<T>;
}

async function del<T>(path: string): Promise<T> {
  const res = await fetch(`/api${path}`, { method: "DELETE" });
  if (!res.ok) {
    let detail = `DELETE ${path} → ${res.status}`;
    try { detail = extractDetail(await res.json(), detail); } catch {}
    const err = new Error(detail);
    (err as any).status = res.status;
    throw err;
  }
  return res.json() as Promise<T>;
}

export const api = { get, post, delete: del };
