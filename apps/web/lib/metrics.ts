import { API_BASE_URL } from "@/lib/api";

// User-study timing (TY3's POST /routes/metrics/event). Anonymous: a random id per tab, nothing else.
type MetricEvent = "start" | "plan_shown" | "booking_chosen";

const KEY = "ty.metrics.session";

function sessionId(): string | null {
  try {
    let id = sessionStorage.getItem(KEY);
    if (!id) {
      id = crypto.randomUUID();
      sessionStorage.setItem(KEY, id);
    }
    return id;
  } catch {
    return null;
  }
}

/**
 * Sends one event without waiting. sendBeacon with text/plain survives the
 * traveller leaving for a seller's site and needs no CORS preflight; TY3 parses
 * the body as JSON whatever the type. Does nothing with no API configured.
 */
export function track(event: MetricEvent, task = "plan_trip", base = API_BASE_URL): boolean {
  if (!base || typeof window === "undefined") return false;
  const session_id = sessionId();
  if (!session_id) return false;
  const body = JSON.stringify({ session_id, task, arm: "ty", event });
  const url = `${base}/routes/metrics/event`;
  try {
    if (navigator.sendBeacon?.(url, new Blob([body], { type: "text/plain;charset=UTF-8" }))) return true;
    void fetch(url, { method: "POST", body, keepalive: true, headers: { "Content-Type": "text/plain;charset=UTF-8" } }).catch(() => {});
    return true;
  } catch {
    return false;
  }
}
