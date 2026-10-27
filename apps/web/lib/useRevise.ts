import { useEffect, useRef, useState } from "react";
import type { Lang, ReviseRequest } from "@/lib/contracts";
import { useI18n } from "@/lib/i18n";
import { PlanHttpError, clearChoice, savePlanResult, streamRevise } from "@/lib/plan";
import { initialPlanState, planReducer } from "@/lib/planState";

// A revise is one day's solve and check; past this the connection has stalled.
const REVISE_TIMEOUT_MS = 90_000;

export type Said = { text: string; bad: boolean };

/**
 * POST /plan/{plan_id}/revise and keep the new plan. Revise streams like /plan
 * and ends in done with a new plan_id. `busy` is the pending message while it
 * runs; `said` is the outcome, already translated.
 */
export function useRevise(planId: string | null, lang: Lang | undefined) {
  const { t } = useI18n();
  const [busy, setBusy] = useState<string | null>(null);
  const [said, setSaid] = useState<Said | null>(null);
  const live = useRef<AbortController | null>(null);
  useEffect(() => () => live.current?.abort(), []);

  /** `done` is shown when it works and the stream named no change. Resolves true when the new plan is saved. */
  const revise = async (req: Omit<ReviseRequest, "lang">, done: string): Promise<boolean> => {
    if (!planId || busy) return false;
    setBusy(done);
    setSaid(null);
    const ctl = new AbortController();
    live.current = ctl;
    const timer = setTimeout(() => ctl.abort(), REVISE_TIMEOUT_MS);
    try {
      let s = initialPlanState();
      for await (const ev of streamRevise(planId, { ...req, lang: lang ?? "en" }, ctl.signal)) s = planReducer(s, ev);
      if (s.status === "done" && s.itinerary) {
        savePlanResult({ itinerary: s.itinerary, plan_id: s.planId, share_token: s.shareToken });
        // A new transport order: the highlighted option follows the plan again.
        if (req.intent === "transport") clearChoice();
        // TY1's solver line says what really changed ("Dropped X", "already free"); a bare "Done" could hide a no-op (QA #108).
        setSaid({ text: s.solvedNote ? t("Done: {what}", { what: s.solvedNote }) : done, bad: false });
        return true;
      }
      setSaid({ text: t(s.error?.message ?? "The planner stopped before finishing. Try again."), bad: true });
    } catch (e) {
      const text = e instanceof PlanHttpError ? e.message : ctl.signal.aborted ? t("The planner took too long. Try again.") : t("We could not reach the planner. Check your connection.");
      setSaid({ text, bad: true });
    } finally {
      clearTimeout(timer);
      setBusy(null);
    }
    return false;
  };

  return { busy, said, revise };
}
