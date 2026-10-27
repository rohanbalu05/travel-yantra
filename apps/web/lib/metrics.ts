import { currentConsents } from "@/lib/account";
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
// A study session (the /study/ consent screen) measures this tab only, with its own task and arm.
const STUDY_KEY = "ty.study";
export type Study = { task: string; arm: "ty" | "baseline" };

export function startStudy(s: Study) {
  try {
    sessionStorage.setItem(STUDY_KEY, JSON.stringify(s));
  } catch {
    // Storage blocked: nothing is measured, which is the safe side.
  }
}

export function currentStudy(): Study | null {
  try {
    const raw = sessionStorage.getItem(STUDY_KEY);
    return raw ? (JSON.parse(raw) as Study) : null;
  } catch {
    return null;
  }
}

export function track(event: MetricEvent, task?: string, base = API_BASE_URL): boolean {
  if (!base || typeof window === "undefined") return false;
  const study = currentStudy();
  // DPDP: only with "Help us measure" in Settings, or the study screen's consent for this session.
  if (!study && !currentConsents().analytics) return false;
  const session_id = sessionId();
  if (!session_id) return false;
  const body = JSON.stringify({ session_id, task: task ?? study?.task ?? "plan_trip", arm: study?.arm ?? "ty", event });
  const url = `${base}/routes/metrics/event`;
  try {
    if (navigator.sendBeacon?.(url, new Blob([body], { type: "text/plain;charset=UTF-8" }))) return true;
    void fetch(url, { method: "POST", body, keepalive: true, headers: { "Content-Type": "text/plain;charset=UTF-8" } }).catch(() => {});
    return true;
  } catch {
    return false;
  }
}
