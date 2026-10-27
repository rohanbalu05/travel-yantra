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

/** A study task from TY3 (GET /routes/metrics/tasks): what the participant is asked to plan. */
export type StudyTask = { id: string; title: string; brief: string; arms: ("ty" | "baseline")[] };

const SAMPLE_TASKS: StudyTask[] = [
  { id: "plan_goa_family", title: "Goa with the family", brief: "Plan Bengaluru to Goa for a family of four (two parents in their 60s), 11 to 14 Dec, about ₹60,000 in all. Choose how to travel and where to book.", arms: ["ty", "baseline"] },
  { id: "plan_mysuru_weekend", title: "A weekend in Mysuru", brief: "Plan a weekend in Mysuru for two adults, 19 to 20 Dec. Choose how to travel and where to book.", arms: ["ty", "baseline"] },
];

/** The study tasks; the sample pair when there is no API or the route is not there. */
export async function studyTasks(base = API_BASE_URL): Promise<StudyTask[]> {
  if (!base) return SAMPLE_TASKS;
  try {
    const res = await fetch(`${base}/routes/metrics/tasks`, { headers: { Accept: "application/json" } });
    return res.ok ? ((await res.json()) as StudyTask[]) : SAMPLE_TASKS;
  } catch {
    return SAMPLE_TASKS;
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
