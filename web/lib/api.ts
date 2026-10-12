// Client for the Django API at /api/fsa (same origin, via the Next.js rewrite).
// Every response is { data, meta }. A refusal is { error, blockedBy[], message } — rendered verbatim.

export type Tone = "ok" | "warn" | "bad" | "na" | "info";

export type AuditEntry = { at: string; what: string; who: string; entityType?: string; entityRef?: string };
export type Envelope<T> = { data: T; meta: { audit?: AuditEntry; source?: string; today?: string; [k: string]: unknown } };

export class ApiError extends Error {
  status: number;
  error: string;
  blockedBy: string[];
  constructor(status: number, body: { error?: string; blockedBy?: string[]; message?: string; detail?: unknown }) {
    const detail = typeof body.detail === "string" ? body.detail : undefined;
    super(body.message ?? detail ?? `Request failed (${status})`);
    this.status = status;
    this.error = body.error ?? "error";
    this.blockedBy = body.blockedBy ?? (Array.isArray(body.detail) ? body.detail.map((d: { msg?: string }) => d.msg ?? String(d)) : []);
  }
}

function csrfToken(): string {
  if (typeof document === "undefined") return "";
  const match = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
  return match ? decodeURIComponent(match[1]) : "";
}

let csrfReady: Promise<void> | null = null;
async function ensureCsrf() {
  if (csrfToken()) return;
  csrfReady ??= fetch("/api/fsa/auth/csrf", { credentials: "same-origin", cache: "no-store" }).then(() => undefined);
  await csrfReady;
}

export async function api<T>(path: string, init: { method?: string; body?: unknown; screen?: string } = {}): Promise<Envelope<T>> {
  const method = init.method ?? "GET";
  if (method !== "GET") await ensureCsrf();
  const res = await fetch(`/api/fsa${path}`, {
    method,
    credentials: "same-origin",
    cache: "no-store", // register data is never cached (rules 6 and 7)
    headers: {
      Accept: "application/json",
      ...(init.body !== undefined ? { "Content-Type": "application/json" } : {}),
      ...(method !== "GET" ? { "X-CSRFToken": csrfToken() } : {}),
      ...(init.screen ? { "X-FSA-Screen": init.screen } : {}),
    },
    body: init.body !== undefined ? JSON.stringify(init.body) : undefined,
  });
  const text = await res.text();
  const json = text ? JSON.parse(text) : {};
  if (!res.ok) throw new ApiError(res.status, json);
  return json as Envelope<T>;
}
