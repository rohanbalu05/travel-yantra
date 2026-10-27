import { useMemo, useSyncExternalStore } from "react";
import { API_BASE_URL } from "@/lib/api";
import { clientHeaders } from "@/lib/account";
import { detailText } from "@/lib/http";
import type { Itinerary, PlanEvent, PlanStage, PlanText, ReviseRequest, TripRequest } from "@/lib/contracts";
import { mockPlanBody, mockReviseBody } from "@/lib/mockPlan";
import { parseSSE } from "@/lib/sse";

export type PlanBody = TripRequest | PlanText;

/** The stream ends after the first of these. */
export const TERMINAL: ReadonlySet<PlanStage> = new Set(["done", "needs_input", "error"]);

export class PlanHttpError extends Error {}

/**
 * POST /plan and yield its events, stopping after the first terminal one.
 * With no `NEXT_PUBLIC_API_BASE_URL`, replays the Goa sample instead.
 */
export function streamPlan(body: PlanBody, signal?: AbortSignal, base = API_BASE_URL): AsyncGenerator<PlanEvent> {
  return streamEvents("/plan", body, signal, base, () => mockPlanBody());
}

/** POST /plan/{plan_id}/revise: same event stream, ending in done with a new plan_id. */
export function streamRevise(planId: string, body: ReviseRequest, signal?: AbortSignal, base = API_BASE_URL): AsyncGenerator<PlanEvent> {
  return streamEvents(`/plan/${encodeURIComponent(planId)}/revise`, body, signal, base, () => mockReviseBody(body));
}

async function* streamEvents(
  path: string,
  body: unknown,
  signal: AbortSignal | undefined,
  base: string,
  mock: () => ReadableStream<Uint8Array>,
): AsyncGenerator<PlanEvent> {
  let stream: ReadableStream<Uint8Array>;
  if (!base) {
    stream = mock();
  } else {
    const res = await fetch(`${base}${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "text/event-stream", ...clientHeaders() },
      body: JSON.stringify(body),
      signal,
    });
    if (!res.ok || !res.body) {
      const reason = detailText(await res.json().catch(() => null));
      throw new PlanHttpError(reason || `The planner answered ${res.status}.`);
    }
    stream = res.body;
  }
  for await (const ev of parseSSE(stream)) {
    yield ev;
    if (TERMINAL.has(ev.stage)) return;
  }
}

// The plan flow keeps its state in sessionStorage: what was asked, and the result.
const INPUT_KEY = "ty.plan.input";
const RESULT_KEY = "ty.plan.result";
const CHOICE_KEY = "ty.plan.choice";
const CHANGED = "ty-plan-stored";

export type PlanResult = { itinerary: Itinerary; plan_id: string | null; share_token?: string | null };

function write(key: string, value: unknown) {
  try {
    sessionStorage.setItem(key, JSON.stringify(value));
    window.dispatchEvent(new Event(CHANGED));
  } catch {
    // Private mode or storage full: the flow still works within the page.
  }
}

function subscribe(cb: () => void) {
  window.addEventListener(CHANGED, cb);
  window.addEventListener("storage", cb);
  return () => {
    window.removeEventListener(CHANGED, cb);
    window.removeEventListener("storage", cb);
  };
}

const rawItem = (key: string) => {
  try {
    return sessionStorage.getItem(key);
  } catch {
    return null;
  }
};

/** A stored value: undefined while prerendering (no storage yet), null when absent. */
function useStored<T>(key: string): T | null | undefined {
  const raw = useSyncExternalStore(subscribe, () => rawItem(key), () => undefined);
  return useMemo(() => {
    if (raw === undefined) return undefined;
    try {
      return raw ? (JSON.parse(raw) as T) : null;
    } catch {
      return null;
    }
  }, [raw]);
}

export const savePlanInput = (body: PlanBody) => write(INPUT_KEY, body);
export const usePlanInput = () => useStored<PlanBody>(INPUT_KEY);
export const savePlanResult = (r: PlanResult) => write(RESULT_KEY, r);
export const usePlanResult = () => useStored<PlanResult>(RESULT_KEY);
export const saveChoice = (i: number) => write(CHOICE_KEY, i);
export const useChoice = () => useStored<number>(CHOICE_KEY);
