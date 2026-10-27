"use client";

import Link from "next/link";
import { AppShell } from "@/components/AppShell";
import { NoPlan } from "@/components/NoPlan";
import { Trail } from "@/components/Trail";
import type { Itinerary, Mode } from "@/lib/contracts";
import { MODE_ICON, MODE_NAME, clock, dayLabel, duration, inr } from "@/lib/format";
import { useI18n, type Vars } from "@/lib/i18n";
import { saveChoice, useChoice, usePlanResult } from "@/lib/plan";
import { againstBudget, nights, pickIndex, travellerCount, tripCost } from "@/lib/planView";
import "../plan.css";

const star = <path d="M12 3l2.6 5.6 6 .7-4.5 4.1 1.2 6L12 16.4 6.7 19.4l1.2-6L3.4 9.3l6-.7Z" />;

function Options({ it }: { it: Itinerary }) {
  const { t } = useI18n();
  const mode = (m: Mode) => t(MODE_NAME[m]);
  const opts = it.transport ?? [];
  const best = pickIndex(it);
  const stored = useChoice();
  const sel = stored != null && stored < opts.length ? stored : best;
  const choose = saveChoice;

  const dest = it.request.destinations.join(` ${t("and")} `);
  const people = travellerCount(it);
  const o = opts[sel];
  const cost = o ? tripCost(it, o) : it.budget.total_inr;
  const vs = againstBudget(it, cost);
  const b = it.budget;
  const bestOpt = opts[best];

  return (
    <>
      <div className="po-head">
        <Trail at={3} />
        <div className="col-10">
          <h1 className="page-title">{opts.length === 1 ? t("One way to {dest}", { dest }) : t("{n} ways to {dest}", { n: opts.length, dest })}</h1>
          <p className="page-sub">
            {people > 1
              ? t("Compared for all {people} of you. Costs are for the whole trip: travel, {nights} nights' stay, food and tickets.", { people, nights: nights(it) })
              : t("Compared for you. Costs are for the whole trip: travel, {nights} nights' stay, food and tickets.", { nights: nights(it) })}
          </p>
        </div>
      </div>

      {bestOpt && opts.length > 1 && (
        <div className="pick-note">
          <svg className="ic" viewBox="0 0 24 24" aria-hidden="true">{star}</svg>
          <div>
            <b>{t("Our pick: {mode}", { mode: mode(bestOpt.mode).toLowerCase() })}</b>
            <span>{pickReason(it, best, t)}</span>
          </div>
        </div>
      )}

      <div className="opts" role="radiogroup" aria-label={t("Way to travel")}>
        {opts.map((x, i) => {
          const c = tripCost(it, x);
          const v = againstBudget(it, c);
          return (
            <button key={`${x.mode}-${i}`} type="button" role="radio" aria-checked={i === sel} className={i === sel ? "opt on" : "opt"} onClick={() => choose(i)}>
              <span className="opt-top">
                <span className="opt-ic"><svg className="ic" viewBox="0 0 24 24" aria-hidden="true"><path d={MODE_ICON[x.mode]} /></svg></span>
                <b>{x.legs[0] ? t("{mode}: {from} to {to}", { mode: mode(x.mode), from: x.legs[0].from, to: x.legs.at(-1)!.to }) : mode(x.mode)}</b>
              </span>
              <span className="opt-figs">
                <span><small>{t("Travel time")}</small><span>{duration(x.total_minutes)}</span></span>
                <span><small>{t("Whole trip (est.)")}</small><span>{inr(c)}</span></span>
              </span>
              <span className="badges">
                {v && <span className={v.ok ? "badge badge-ok" : "badge badge-warn"}>{v.ok ? t("{amount} to spare", { amount: inr(v.diff) }) : t("Over by {amount}", { amount: inr(v.diff) })}</span>}
                <span className="badge">{t("Comfort {n} of 5", { n: x.comfort })}</span>
                {i === best && opts.length > 1 && <span className="badge badge-sea">{t("Our pick")}</span>}
              </span>
              <span className="opt-line">{x.legs.length === 1 ? t("Direct, no changes.") : x.legs.length === 2 ? t("{legs} legs, 1 change.", { legs: x.legs.length }) : t("{legs} legs, {changes} changes.", { legs: x.legs.length, changes: x.legs.length - 1 })}</span>
            </button>
          );
        })}
      </div>

      {o && (
        <div className="split">
          <section className="main panel panel-pad" aria-labelledby="d-h">
            <div className="detail-head">
              <h2 className="h2" id="d-h">{t("{mode}, step by step", { mode: mode(o.mode) })}</h2>
              <span className="hint">{t("Going, {date}", { date: dayLabel(o.legs[0]?.depart ?? it.request.start_date) })}</span>
            </div>
            <div className="legs">
              {o.legs.map((l, i) => (
                <div className="leg-row" key={i}>
                  <span className="leg-when">{t("{from} to {to}", { from: clock(l.depart), to: clock(l.arrive) })}</span>
                  <span className="leg-ic"><svg className="ic" viewBox="0 0 24 24" aria-hidden="true"><path d={MODE_ICON[l.mode]} /></svg></span>
                  <div>
                    <b>{t("{from} to {to}", { from: l.from, to: l.to })}</b>
                    <small>{mode(l.mode)} · {duration(l.minutes)} · {people > 1 ? t("{cost} for {n}", { cost: inr(l.cost_inr), n: people }) : inr(l.cost_inr)}</small>
                  </div>
                </div>
              ))}
            </div>
          </section>

          <aside className="side panel panel-pad" aria-labelledby="c-h">
            <h2 className="h3" id="c-h" style={{ marginBottom: 14 }}>{t("Where the money goes")}</h2>
            <dl className="kv cost">
              <dt>{t("Getting there, {mode}", { mode: mode(o.mode).toLowerCase() })}</dt><dd>{inr(o.total_cost_inr)}</dd>
              <dt>{t("Stay")}</dt><dd>{inr(b.stay_inr)}</dd>
              {!!b.food_inr && <><dt>{t("Food")}</dt><dd>{inr(b.food_inr)}</dd></>}
              {!!b.activities_inr && <><dt>{t("Tickets and activities")}</dt><dd>{inr(b.activities_inr)}</dd></>}
              <dt className="tot">{t("Whole trip, estimated")}</dt><dd className="tot">{inr(cost)}</dd>
            </dl>
            {vs && <p className={vs.ok ? "badge badge-ok" : "badge badge-warn"} style={{ marginTop: 14 }}>{vs.ok ? t("{amount} under your budget", { amount: inr(vs.diff) }) : t("{amount} over your budget", { amount: inr(vs.diff) })}</p>}
          </aside>
        </div>
      )}

      <p className="hint" style={{ margin: "16px 0 0" }}>{t("Fares are estimates from sample data until live prices are wired in. You pay the seller directly when you book.")}</p>

      <div className="go">
        <div><b>{o ? t("Go by {mode}", { mode: mode(o.mode).toLowerCase() }) : t("See the plan")}</b><span>{t("Next, the day-by-day plan. You can still switch later.")}</span></div>
        <Link className="btn btn-primary btn-lg" href="/plan/itinerary/">{t("See the day-by-day plan")}</Link>
      </div>
    </>
  );
}

function pickReason(it: Itinerary, best: number, t: (text: string, vars?: Vars) => string): string {
  const opts = it.transport ?? [];
  const o = opts[best];
  const c = tripCost(it, o);
  const v = againstBudget(it, c);
  const parts = [v ? (v.ok ? t("It fits the budget with {amount} to spare", { amount: inr(v.diff) }) : t("It is the closest to your budget")) : t("It costs the least")];
  const faster = opts.filter((x) => x.total_minutes < o.total_minutes).sort((a, b) => a.total_minutes - b.total_minutes)[0];
  if (faster && tripCost(it, faster) > c) parts.push(t("{mode} is {time} quicker but costs {amount} more", { mode: t(MODE_NAME[faster.mode]), time: duration(o.total_minutes - faster.total_minutes), amount: inr(tripCost(it, faster) - c) }));
  return parts.join(". ") + ".";
}

export default function PlanOptions() {
  const res = usePlanResult();
  const it = res === undefined ? undefined : (res?.itinerary ?? null);
  return <AppShell>{it === undefined ? null : it ? <div><Options it={it} /></div> : <NoPlan />}</AppShell>;
}
