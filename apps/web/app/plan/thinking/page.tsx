"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { AppShell } from "@/components/AppShell";
import { Trail } from "@/components/Trail";
import type { ViolationCode } from "@/lib/contracts";
import { inr } from "@/lib/format";
import { GOA_REQUEST } from "@/lib/mockPlan";
import { PlanHttpError, savePlanInput, savePlanResult, streamPlan, usePlanInput, type PlanBody } from "@/lib/plan";
import { AGENTS, initialPlanState, planReducer, type Agent, type PlanState } from "@/lib/planState";
import "../plan.css";

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

function title(body: PlanBody | null): string {
  if (body && "destinations" in body && body.destinations.length) return `Planning your ${body.destinations.join(" and ")} trip`;
  return "Planning your trip";
}

function AgentCard({ agent, find, planning }: { agent: Agent; find: string | null; planning: boolean }) {
  const a = AGENT_INFO[agent];
  return (
    <article className="agent" aria-label={`${a.name} specialist`}>
      <div className="agent-top">
        <span className="agent-ic"><svg className="ic" viewBox="0 0 24 24" aria-hidden="true">{a.icon}</svg></span>
        <div><b>{a.name}</b><span className="agent-sub">{a.sub}</span></div>
        {find ? <span className="st st-ok">Done</span> : <span className="st st-wait">{planning ? "Working" : "Waiting"}</span>}
      </div>
      <div className="bar"><i className={find ? undefined : planning ? "run" : undefined} style={{ transform: find ? "scaleX(1)" : planning ? undefined : "scaleX(0)" }} /></div>
      <ul className="finds">
        {find ? <li>{find}</li> : <li className="wait">{planning ? "Looking…" : "Starts once we have read your trip."}</li>}
      </ul>
    </article>
  );
}

function Checker({ s }: { s: PlanState }) {
  const last = s.checks.at(-1);
  const passed = s.status === "done" || (last !== undefined && last.violations.length === 0);
  const badge = s.checks.length === 0 ? (s.solved ? "Checking" : "Waiting") : passed ? "All checks passed" : `${last!.violations.length} to fix`;
  const budget = s.itinerary?.budget;
  return (
    <section className="panel" aria-labelledby="chk-h">
      <div className="panel-head">
        <h2 className="h3" id="chk-h">The checker</h2>
        <span className={passed ? "badge badge-ok" : "badge badge-warn"}>{badge}</span>
      </div>
      <div className="panel-pad" style={{ display: "flex", flexDirection: "column", gap: 14, paddingTop: 6 }}>
        {s.checks.length === 0 ? (
          <p className="hint" style={{ margin: 0 }}>Opening hours, travel time, long days, rest and budget are checked once the days are laid out.</p>
        ) : (
          <ul className="checks">
            {s.checks.map((c) => (
              <li key={c.iteration}>
                <svg className={c.violations.length ? "ic fx" : "ic"} viewBox="0 0 24 24" aria-hidden="true">{c.violations.length ? warn : tick}</svg>
                <span>Round {c.iteration}: {c.message}</span>
                <small className={c.violations.length ? "fx" : undefined}>{c.violations.length ? `${c.violations.length} found` : "Passed"}</small>
              </li>
            ))}
            {budget && (
              <li>
                <svg className="ic" viewBox="0 0 24 24" aria-hidden="true">{tick}</svg>
                <span>Budget</span>
                <small className={budget.within_budget === false ? "fx" : undefined}>{inr(budget.total_inr)}{budgetOf(s)}</small>
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
                <b>{repair ? "Fixed" : "Found"}: {VIOLATION_NAME[v.code]}</b>
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

function budgetOf(s: PlanState): string {
  const b = s.itinerary?.request.constraints?.budget_inr;
  return b ? ` of ${inr(b)}` : "";
}

export default function PlanThinking() {
  const stored = usePlanInput();
  // Opening this page directly (nothing typed yet) plans the Goa sample.
  const body: PlanBody | null = stored === undefined ? null : (stored ?? GOA_REQUEST);
  const bodyKey = body ? JSON.stringify(body) : "";
  const [state, setState] = useState<PlanState>(initialPlanState);
  const [run, setRun] = useState(0);
  const [answers, setAnswers] = useState("");

  useEffect(() => {
    if (!bodyKey) return;
    const input = JSON.parse(bodyKey) as PlanBody;
    const ctl = new AbortController();
    (async () => {
      try {
        for await (const ev of streamPlan(input, ctl.signal)) {
          if (ctl.signal.aborted) return;
          setState((s) => planReducer(s, ev));
        }
      } catch (e) {
        if (ctl.signal.aborted) return;
        const message = e instanceof PlanHttpError ? e.message : "We could not reach the planner. Check your connection.";
        setState((s) => ({ ...s, status: "error", error: { message, retryable: !(e instanceof PlanHttpError) } }));
      }
    })();
    return () => ctl.abort();
  }, [bodyKey, run]);

  useEffect(() => {
    if (state.status === "done" && state.itinerary) savePlanResult({ itinerary: state.itinerary, plan_id: state.planId });
  }, [state.status, state.itinerary, state.planId]);

  const retry = () => {
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

  return (
    <AppShell>
      <div>
        <div className="pt-head">
          <Trail at={2} />
          <div className="pt-titlebar">
            <div className="col-10">
              <h1 className="page-title">{title(body)}</h1>
              <p className="page-sub">Four AI specialists work at once. Then a checker tests every stop on every day, and fixes what fails, before you see a thing.</p>
            </div>
            {state.intake && <p className="badge" role="status" style={{ margin: 0 }}>{state.intake}</p>}
          </div>
        </div>

        {state.status === "needs_input" && (
          <div className="ask-box" style={{ marginBottom: 20 }}>
            <b>A few things before we plan</b>
            <ol>{state.questions.map((q) => <li key={q}>{q}</li>)}</ol>
            <label htmlFor="answers" className="sr">Your answers</label>
            <textarea id="answers" className="input" value={answers} onChange={(e) => setAnswers(e.target.value)} placeholder="Answer in your own words…" />
            <div className="row-wrap">
              <button type="button" className="btn btn-primary" onClick={resend} disabled={!answers.trim()}>Send and plan</button>
              <Link className="btn btn-quiet" href="/plan/start/?mode=form">Fill a form instead</Link>
            </div>
          </div>
        )}

        <div className="split">
          <div className="main" style={{ display: "flex", flexDirection: "column", gap: 20 }}>
            <div className="agents">
              {AGENTS.map((a) => <AgentCard key={a} agent={a} find={state.agents[a]} planning={planning && state.status === "running"} />)}
            </div>
          </div>
          <aside className="side" style={{ display: "flex", flexDirection: "column", gap: 16 }}>
            <Checker s={state} />
            <div className="why">
              <div><b>The AI</b>Understands what you asked, compares the options and writes the plan.</div>
              <div><b>The checker</b>Plain rules that never guess: hours, distances, meals, budget.</div>
            </div>
          </aside>
        </div>

        {state.status === "error" ? (
          <div className="ready bad" role="alert">
            <div><b>We could not finish the plan</b><span>{state.error?.message}</span></div>
            <div className="row-wrap">
              {state.error?.retryable && <button type="button" className="btn btn-primary btn-lg" onClick={retry}>Try again</button>}
              <Link className="btn btn-on-dark" href="/plan/start/">Change the trip</Link>
            </div>
          </div>
        ) : state.status !== "needs_input" && (
          <div className="ready" aria-live="polite">
            {state.status === "done" ? (
              <>
                <div><b>Your plan is ready</b><span>{ways > 1 ? `${ways} ways to get there, compared for all of you.` : "Checked stop by stop."}</span></div>
                <Link className="btn btn-primary btn-lg" href={ways > 1 ? "/plan/options/" : "/plan/itinerary/"}>{ways > 1 ? `See the ${ways} ways to go` : "See the plan"}</Link>
              </>
            ) : (
              <div><b>Still planning</b><span>{state.narrating ? "Writing your day-by-day plan." : "About 15 seconds. Keep this page open."}</span></div>
            )}
          </div>
        )}
      </div>
    </AppShell>
  );
}
