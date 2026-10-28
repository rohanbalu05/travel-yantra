"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { AppShell } from "@/components/AppShell";
import { Trail } from "@/components/Trail";
import type { ViolationCode } from "@/lib/contracts";
import { inr } from "@/lib/format";
import { rememberTrip } from "@/lib/account";
import { useI18n, type Vars } from "@/lib/i18n";
import { track } from "@/lib/metrics";
import { API_BASE_URL } from "@/lib/api";
import { NoPlan } from "@/components/NoPlan";
import { GOA_REQUEST } from "@/lib/mockPlan";
import { PlanHttpError, clearChoice, savePlanInput, savePlanResult, savePlannedFrom, streamPlan, usePlanInput, usePlanResult, usePlannedFrom, type PlanBody } from "@/lib/plan";
import { AGENTS, initialPlanState, planReducer, type Agent, type PlanState } from "@/lib/planState";
import "../plan.css";

// A plan usually takes 15–40 s. Past a minute say so; past four, stop and offer to try again.
const SLOW_MS = 60_000;
const PLAN_TIMEOUT_MS = 240_000;

const AGENT_INFO: Record<Agent, { name: string; sub: string; icon: React.ReactNode }> = {
  transport: {
    name: "Transport",
    sub: "Road, rail and air, door to door",
    icon: <><rect x="6" y="3" width="12" height="13" rx="2" /><path d="M6 10h12" /><path d="M8 16l-2 4M16 16l2 4M7 19h10" /></>,
  },
  places: {
    name: "Places",
    sub: "What to see, grouped by area",
    icon: <><path d="M12 21s-6.5-6.2-6.5-11.2a6.5 6.5 0 0 1 13 0C18.5 14.8 12 21 12 21Z" /><circle cx="12" cy="10" r="2.3" /></>,
  },
  stays: {
    name: "Stays",
    sub: "Where to sleep, close to the plan",
    icon: <><path d="M3 18V7" /><path d="M3 14h18v4" /><path d="M3 11h7a2 2 0 0 1 2 2v1" /><path d="M12 14v-2a2 2 0 0 1 2-2h5a2 2 0 0 1 2 2v2" /></>,
  },
  story: {
    name: "Katha",
    sub: "A story for every stop",
    icon: <><path d="M4 5.5A2.5 2.5 0 0 1 6.5 3H20v15H6.5A2.5 2.5 0 0 0 4 20.5V5.5Z" /><path d="M4 20.5A2.5 2.5 0 0 1 6.5 18H20v3H6.5" /></>,
  },
};

const tick = <path d="M5 12.5l4.5 4.5L19 7.5" />;
const warn = <><circle cx="12" cy="12" r="9" /><path d="M12 7.5v5.5" /><path d="M12 16.5h.01" /></>;

/** From the form, or from what intake understood once a partial plan arrives. */
function title(body: PlanBody | null, s: PlanState, t: (text: string, vars?: Vars) => string): string {
  const dest = s.itinerary?.request.destinations ?? (body && "destinations" in body ? body.destinations : []);
  return dest.length ? t("Planning your {dest} trip", { dest: dest.join(` ${t("and")} `) }) : t("Planning your trip");
}

function AgentCard({ agent, find, planning, n }: { agent: Agent; find: string | null; planning: boolean; n: number }) {
  const { t } = useI18n();
  const a = AGENT_INFO[agent];
  return (
    // The prototype's motion: cards come in one after another; Working turns to Done; the bar fills.
    <article className="agent" style={{ animationDelay: `${n * 90}ms` }} aria-label={t("{name} specialist", { name: t(a.name) })}>
      <div className="agent-top">
        <span className="agent-ic"><svg className="ic" viewBox="0 0 24 24" aria-hidden="true">{a.icon}</svg></span>
        <div><b>{t(a.name)}</b><span className="agent-sub">{t(a.sub)}</span></div>
        {find ? <span key="done" className="st st-ok swap-in">{t("Done")}</span> : <span key="wait" className="st st-wait">{planning ? t("Working") : t("Waiting")}</span>}
      </div>
      <div className="bar"><i className={find ? undefined : planning ? "run" : undefined} style={{ transform: find ? "scaleX(1)" : planning ? undefined : "scaleX(0)" }} /></div>
      <ul className="finds">
        {find ? <li>{find}</li> : <li className="wait">{planning ? t("Looking…") : t("Starts once we have read your trip.")}</li>}
      </ul>
    </article>
  );
}

function Checker({ s }: { s: PlanState }) {
  const { t } = useI18n();
  const last = s.checks.at(-1);
  const passed = s.status === "done" || (last !== undefined && last.violations.length === 0);
  const badge = s.checks.length === 0 ? (s.solved ? t("Checking") : t("Waiting")) : passed ? t("All checks passed") : t("{n} to fix", { n: last!.violations.length });
  const budget = s.itinerary?.budget;
  return (
    <section className="panel" aria-labelledby="chk-h">
      <div className="panel-head">
        <h2 className="h3" id="chk-h">{t("The checker")}</h2>
        <span className={passed ? "badge badge-ok" : "badge badge-warn"}>{badge}</span>
      </div>
      <div className="panel-pad" style={{ display: "flex", flexDirection: "column", gap: 14, paddingTop: 6 }}>
        {s.checks.length === 0 ? (
          <p className="hint" style={{ margin: 0 }}>{t("Opening hours, travel time, long days, rest and budget are checked once the days are laid out.")}</p>
        ) : (
          <ul className="checks">
            {s.checks.map((c) => (
              <li key={c.iteration}>
                <svg className={c.violations.length ? "ic fx" : "ic"} viewBox="0 0 24 24" aria-hidden="true">{c.violations.length ? warn : tick}</svg>
                <span>{t("Round {n}: {message}", { n: c.iteration, message: c.message })}</span>
                <small className={c.violations.length ? "fx" : undefined}>{c.violations.length ? t("{n} found", { n: c.violations.length }) : t("Passed")}</small>
              </li>
            ))}
            {budget && (
              <li>
                <svg className="ic" viewBox="0 0 24 24" aria-hidden="true">{tick}</svg>
                <span>{t("Budget")}</span>
                <small className={budget.within_budget === false ? "fx" : undefined}>{budgetOf(s, inr(budget.total_inr), t)}</small>
              </li>
            )}
          </ul>
        )}
        {s.checks.map((c, ci) =>
          c.violations.map((v, vi) => {
            // A problem from an earlier round was repaired; one from the last round is still open.
            const repair = ci < s.checks.length - 1 ? s.repairs[ci] : undefined;
            return (
              <div className="fix" key={`${c.iteration}-${v.code}-${vi}`}>
                <b>{repair ? t("Fixed: {problem}", { problem: t(VIOLATION_NAME[v.code]) }) : t("Found: {problem}", { problem: t(VIOLATION_NAME[v.code]) })}</b>
                {v.message}{repair ? ` ${repair}` : ""}
              </div>
            );
          }),
        )}
      </div>
    </section>
  );
}

const VIOLATION_NAME: Record<ViolationCode, string> = {
  over_budget: "over budget",
  closed: "closed that day",
  long_day: "a long day",
  too_much_travel: "too much travel",
  no_rest: "no time to rest",
};

function budgetOf(s: PlanState, total: string, t: (text: string, vars?: Vars) => string): string {
  const b = s.itinerary?.request.constraints?.budget_inr;
  return b ? t("{total} of {budget}", { total, budget: inr(b) }) : total;
}

export default function PlanThinking() {
  const { t } = useI18n();
  const stored = usePlanInput();
  const result = usePlanResult();
  const plannedFrom = usePlannedFrom();
  // Nothing typed yet: the offline demo plans the Goa sample; the live app asks for a trip instead.
  const body: PlanBody | null = stored === undefined ? null : (stored ?? (API_BASE_URL ? null : GOA_REQUEST));
  const bodyKey = body ? JSON.stringify(body) : "";
  const [live, setState] = useState<PlanState>(initialPlanState);
  const [run, setRun] = useState(0);
  const [answers, setAnswers] = useState("");
  const [slow, setSlow] = useState(false);
  // This input was already planned (refresh, Back, the stepper): show that result, never plan again.
  const already = !!bodyKey && plannedFrom === bodyKey && !!result && run === 0;

  const state = useMemo(
    () => (already && result ? planReducer(initialPlanState(), { stage: "done", message: "", partial: result.itinerary, plan_id: result.plan_id, share_token: result.share_token ?? null }) : live),
    [already, result, live],
  );

  useEffect(() => {
    if (!bodyKey || plannedFrom === undefined || result === undefined || already) return;
    const input = JSON.parse(bodyKey) as PlanBody;
    const ctl = new AbortController();
    const slowTimer = setTimeout(() => setSlow(true), SLOW_MS);
    const stopTimer = setTimeout(() => ctl.abort("timeout"), PLAN_TIMEOUT_MS);
    (async () => {
      try {
        for await (const ev of streamPlan(input, ctl.signal)) {
          if (ctl.signal.aborted) return;
          setState((s) => planReducer(s, ev));
        }
      } catch (e) {
        if (ctl.signal.aborted && ctl.signal.reason !== "timeout") return;
        const message = ctl.signal.reason === "timeout" ? "The planner took too long. Try again." : e instanceof PlanHttpError ? e.message : "We could not reach the planner. Check your connection.";
        setState((s) => ({ ...s, status: "error", error: { message, retryable: ctl.signal.reason === "timeout" || !(e instanceof PlanHttpError) } }));
      } finally {
        clearTimeout(slowTimer);
        clearTimeout(stopTimer);
      }
    })();
    return () => {
      clearTimeout(slowTimer);
      clearTimeout(stopTimer);
      ctl.abort("left");
    };
    // `already`, `plannedFrom` and `result` only gate the first run; a new input or Try again plans again.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [bodyKey, run, plannedFrom === undefined, result === undefined]);

  useEffect(() => {
    if (state.status !== "done" || !state.itinerary) return;
    if (already) return; // shown from storage, not a new plan
    savePlanResult({ itinerary: state.itinerary, plan_id: state.planId, share_token: state.shareToken });
    savePlannedFrom(bodyKey);
    clearChoice(); // a choice made on an earlier plan's options does not carry over
    void rememberTrip(state.itinerary, state.planId, state.shareToken); // only with the Keep my trips consent
    track("plan_shown");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [state.status, state.itinerary, state.planId, state.shareToken]);

  const retry = () => {
    setSlow(false);
    setState(initialPlanState());
    setRun((r) => r + 1);
  };

  const resend = () => {
    if (!body || !answers.trim()) return;
    const original = "text" in body ? body.text : "";
    setState(initialPlanState());
    setAnswers("");
    savePlanInput({ text: `${original}\n${answers.trim()}`.trim().slice(0, 4000), lang: body.lang ?? "en" });
  };

  const planning = state.intake !== null;
  const it = state.itinerary;
  const ways = it?.transport?.length ?? 0;

  if (stored === null && !body) return <AppShell><NoPlan /></AppShell>;

  return (
    <AppShell>
      <div>
        <div className="pt-head">
          <Trail at={2} />
          <div className="pt-titlebar">
            <div className="col-10">
              <h1 className="page-title">{title(body, state, t)}</h1>
              <p className="page-sub">{t("Four AI specialists work at once. Then a checker tests every stop on every day, and fixes what fails, before you see a thing.")}</p>
            </div>
            {state.intake && <p className="badge" role="status" style={{ margin: 0 }}>{state.intake}</p>}
          </div>
        </div>

        {state.status === "needs_input" && (
          <div className="ask-box" style={{ marginBottom: 20 }}>
            <b>{t("A few things before we plan")}</b>
            <ol>{state.questions.map((q) => <li key={q}>{q}</li>)}</ol>
            <label htmlFor="answers" className="sr">{t("Your answers")}</label>
            <textarea id="answers" className="input" value={answers} onChange={(e) => setAnswers(e.target.value)} placeholder={t("Answer in your own words…")} />
            <div className="row-wrap">
              <button type="button" className="btn btn-primary" onClick={resend} disabled={!answers.trim()}>{t("Send and plan")}</button>
              <Link className="btn btn-quiet" href={state.draft ? `/plan/start/?mode=form&draft=${encodeURIComponent(JSON.stringify(state.draft))}` : "/plan/start/?mode=form"}>
                {state.draft ? t("Finish it in the form") : t("Fill a form instead")}
              </Link>
            </div>
          </div>
        )}

        <div className="split">
          <div className="main" style={{ display: "flex", flexDirection: "column", gap: 20 }}>
            <div className="agents">
              {AGENTS.map((a, i) => <AgentCard key={a} n={i} agent={a} find={state.agents[a]} planning={planning && state.status === "running"} />)}
            </div>
          </div>
          <aside className="side" style={{ display: "flex", flexDirection: "column", gap: 16 }}>
            <Checker s={state} />
            <div className="why">
              <div><b>{t("The AI")}</b>{t("Understands what you asked, compares the options and writes the plan.")}</div>
              <div><b>{t("The checker")}</b>{t("Plain rules that never guess: hours, distances, meals, budget.")}</div>
            </div>
          </aside>
        </div>

        {state.status === "error" ? (
          <div className="ready bad" role="alert">
            <div><b>{t("We could not finish the plan")}</b><span>{state.error ? t(state.error.message) : null}</span></div>
            <div className="row-wrap">
              {state.error?.retryable && <button type="button" className="btn btn-primary btn-lg" onClick={retry}>{t("Try again")}</button>}
              <Link className="btn btn-on-dark" href="/plan/start/">{t("Change the trip")}</Link>
            </div>
          </div>
        ) : state.status !== "needs_input" && (
          <div className="ready" key={state.status} aria-live="polite">
            {state.status === "done" ? (
              <>
                <div><b>{t("Your plan is ready")}</b><span>{ways > 1 ? t("{ways} ways to get there, compared for all of you.", { ways }) : t("Checked stop by stop.")}</span></div>
                <Link className="btn btn-primary btn-lg" href={ways > 1 ? "/plan/options/" : "/plan/itinerary/"}>{ways > 1 ? t("See the {ways} ways to go", { ways }) : t("See the plan")}</Link>
              </>
            ) : (
              <div><b>{t("Still planning")}</b><span>{state.narrating ? t("Writing your day-by-day plan.") : slow ? t("This is taking longer than usual. Keep this page open; it can take up to four minutes.") : t("About 15 seconds. Keep this page open.")}</span></div>
            )}
          </div>
        )}
      </div>
    </AppShell>
  );
}
