import { API_BASE_URL } from "@/lib/api";

/** An API answer that was not 2xx, with a reason a traveller can read. */
export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
  }
  /** 503 (offline, not configured) and 5xx may pass; 4xx means the request itself is wrong. */
  get retryable() {
    return this.status >= 500 || this.status === 0;
  }
}

/** Short, readable reason from a FastAPI error body (`detail` is a string or a list). */
export function detailText(body: unknown): string {
  const d = (body as { detail?: unknown } | null)?.detail;
  if (typeof d === "string") return d;
  if (Array.isArray(d)) return d.map((x) => (x as { msg?: string }).msg ?? "").filter(Boolean).join("; ");
  return "";
}

/**
 * GET (no body) or POST (with body) JSON to the API. Network failures become
 * ApiError status 0, so callers have one error type to show.
 */
export async function apiJSON<T>(
  path: string,
  opts: { body?: unknown; signal?: AbortSignal; base?: string; method?: "GET" | "POST" | "PUT" | "DELETE"; headers?: Record<string, string> } = {},
): Promise<T> {
  const base = opts.base ?? API_BASE_URL;
  let res: Response;
  try {
    res = await fetch(`${base}${path}`, {
      method: opts.method ?? (opts.body === undefined ? "GET" : "POST"),
      headers: { Accept: "application/json", ...(opts.body === undefined ? {} : { "Content-Type": "application/json" }), ...opts.headers },
      body: opts.body === undefined ? undefined : JSON.stringify(opts.body),
      signal: opts.signal,
    });
  } catch (e) {
    if (opts.signal?.aborted) throw e;
    throw new ApiError("We could not reach Travel Yantra. Check your connection.", 0);
  }
  if (!res.ok) {
    const reason = detailText(await res.json().catch(() => null));
    throw new ApiError(reason || `The server answered ${res.status}.`, res.status);
  }
  return (await res.json()) as T;
}

/** "a=1&b=x" from an object, skipping empty values. */
export function query(params: Record<string, string | number | null | undefined>): string {
  const q = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v !== null && v !== undefined && v !== "") q.set(k, String(v));
  return q.toString();
}
