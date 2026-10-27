import type { Itinerary, PlanEvent, TripDraft, Violation } from "@/lib/contracts";

export const AGENTS = ["transport", "places", "stays", "story"] as const;
export type Agent = (typeof AGENTS)[number];

export type CheckRound = { iteration: number; violations: Violation[]; message: string };

export type PlanState = {
  status: "running" | "done" | "needs_input" | "error";
  intake: string | null;
  agents: Record<Agent, string | null>; // the agent's finding once it reports, else null
  solved: boolean;
  checks: CheckRound[];
  repairs: string[];
  narrating: boolean;
  questions: string[];
  draft: TripDraft | null; // what intake did understand, on needs_input
  error: { message: string; retryable: boolean } | null;
  itinerary: Itinerary | null;
  planId: string | null;
  shareToken: string | null;
};

export const initialPlanState = (): PlanState => ({
  status: "running",
  intake: null,
  agents: { transport: null, places: null, stays: null, story: null },
  solved: false,
  checks: [],
  repairs: [],
  narrating: false,
  questions: [],
  draft: null,
  error: null,
  itinerary: null,
  planId: null,
  shareToken: null,
});

/** Folds one /plan event into the screen state. Unknown steps are ignored. */
export function planReducer(s: PlanState, ev: PlanEvent): PlanState {
  const next: PlanState = { ...s, itinerary: ev.partial ?? s.itinerary };
  switch (ev.stage) {
    case "intake":
      // A quick "Reading your trip…" may come first (step null); the parsed one has step "intake".
      if (ev.step === "intake" || next.intake === null) next.intake = ev.message;
      break;
    case "planning":
      if (ev.step && (AGENTS as readonly string[]).includes(ev.step)) next.agents = { ...s.agents, [ev.step]: ev.message };
      break;
    case "solving":
      next.solved = true;
      break;
    case "checking":
      next.solved = true;
      next.checks = [...s.checks, { iteration: ev.iteration ?? s.checks.length + 1, violations: ev.violations ?? [], message: ev.message }];
      break;
    case "repairing":
      next.repairs = [...s.repairs, ev.message];
      break;
    case "narrating":
      next.narrating = true;
      break;
    case "done":
      next.status = "done";
      next.planId = ev.plan_id ?? null;
      next.shareToken = ev.share_token ?? null;
      break;
    case "needs_input":
      next.status = "needs_input";
      next.questions = (ev.questions ?? []).slice(0, 3);
      next.draft = ev.draft ?? null;
      next.intake = ev.message;
      break;
    case "error":
      next.status = "error";
      next.error = { message: ev.message, retryable: ev.retryable ?? false };
      break;
  }
  return next;
}
