"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { AppShell } from "@/components/AppShell";
import { Trail } from "@/components/Trail";
import type { Lang, TripDraft } from "@/lib/contracts";
import { LANGS, useI18n } from "@/lib/i18n";
import { track } from "@/lib/metrics";
import { savePlanInput } from "@/lib/plan";
import { FOODS, INTERESTS, PACES, TRANSPORTS, destinationsOf, formFromDraft, formProblems, blankForm, BUDGET_STYLES, leaveSample, splitOf, toTripRequest, tripDays, type TripForm } from "@/lib/tripForm";
import "../plan.css";

const PLAN_LANGS: [Lang, string][] = LANGS.map((l) => [l.code, l.native]);

const SAMPLE_TEXT = "Bengaluru to Goa, 11 to 14 Dec, with my parents and sister. Churches, temples, a little beach. Vegetarian food, about ₹60,000 in all.";

const PEOPLE: [keyof Pick<TripForm, "adults" | "seniors" | "kids">, string, string][] = [
  ["adults", "Adults", "18 to 59"],
  ["seniors", "Seniors", "60 and over"],
  ["kids", "Children", "Under 18"],
];

function PlanStart() {
  const router = useRouter();
  const params = useSearchParams();
  const [mode, setMode] = useState<"words" | "form">(params.get("mode") === "form" ? "form" : "words");
  // The example is a placeholder in the app's language, never prefilled text sent as the traveller's.
  const [text, setText] = useState(params.get("text") ?? "");
  const { lang: uiLang, t } = useI18n();
  // The plan's language follows the app's until the traveller picks another (plan in Hindi, read the app in English).
  const [picked, setLang] = useState<Lang | null>(null);
  const lang = picked ?? uiLang;
  // From needs_input, the form starts from what intake understood; otherwise empty.
  const [form, setForm] = useState<TripForm>(() => {
    try {
      const d = params.get("draft");
      return d ? formFromDraft(JSON.parse(d) as TripDraft) : blankForm();
    } catch {
      return blankForm();
    }
  });
  const [tried, setTried] = useState(false);

  const set = <K extends keyof TripForm>(k: K, v: TripForm[K]) => setForm((f) => ({ ...f, [k]: v }));
  // A new from or to: the sample's choices go (leaveSample); everything else the traveller set stays.
  const setPlace = (k: "from" | "to", v: string) => setForm((f) => ({ ...leaveSample(f), [k]: v }));
  // Any choice made by hand means the rest is no longer just the sample.
  const choose = <K extends keyof TripForm>(k: K, v: TripForm[K]) => setForm((f) => ({ ...f, [k]: v, sample: false }));
  const cities = destinationsOf(form);
  const split = splitOf(form);
  const problems = mode === "form" ? formProblems(form) : text.trim().length < 1 ? ["Tell us about the trip first."] : text.length > 4000 ? ["Keep it under 4,000 characters."] : [];

  const submit = () => {
    setTried(true);
    if (problems.length) return;
    savePlanInput(mode === "form" ? toTripRequest(form, lang) : { text: text.trim(), lang });
    track("start");
    router.push("/plan/thinking/");
  };

  const langPicker = (
    <div className="field">
      <span className="label">{t("Plan and Katha in")}</span>
      <div className="toggle wrap-toggle" role="group" aria-label={t("Language for the plan")}>
        {PLAN_LANGS.map(([k, label]) => (
          <button key={k} type="button" className={k === lang ? "on" : undefined} aria-pressed={k === lang} onClick={() => setLang(k)}>
            {label}
          </button>
        ))}
      </div>
    </div>
  );

  const errors = tried && problems.length > 0 && (
    <ul className="ps-errors" role="alert">
      {problems.map((p) => <li key={p}>{t(p, { days: tripDays(form) })}</li>)}
    </ul>
  );

  return (
    <AppShell>
      <div>
        <div className="ps-head">
          <Trail at={1} />
          <div className="ps-titlebar">
            <div className="col-10">
              <h1 className="page-title">{t("Tell us about the trip")}</h1>
              <p className="page-sub">{t("In your own words, in any of six languages, or fill in a form. Either way the AI checks what it understood before it plans.")}</p>
            </div>
            <div className="toggle" role="group" aria-label={t("How to describe the trip")}>
              <button type="button" className={mode === "words" ? "on" : undefined} aria-pressed={mode === "words"} onClick={() => setMode("words")}>{t("In your words")}</button>
              <button type="button" className={mode === "form" ? "on" : undefined} aria-pressed={mode === "form"} onClick={() => setMode("form")}>{t("Fill a form")}</button>
            </div>
          </div>
        </div>

        {mode === "words" ? (
          <div className="split">
            <section className="main panel panel-pad fsec" aria-labelledby="w-h">
              <h2 className="h3" id="w-h">{t("Where, when and who")}</h2>
              <div className="field">
                <label htmlFor="trip-text">{t("Your trip, in your words")}</label>
                <textarea id="trip-text" className="input ps-text" value={text} maxLength={4000} placeholder={t(SAMPLE_TEXT)} onChange={(e) => setText(e.target.value)} />
                <span className="hint">{t("Say where from and to, the dates, who is going, and anything that matters: food, walking, budget.")}</span>
              </div>
            </section>
            <aside className="side panel" aria-labelledby="go-h">
              <div className="panel-head"><h2 className="h3" id="go-h">{t("Before we plan")}</h2></div>
              <div className="panel-pad fsec">
                {langPicker}
                <p className="hint" style={{ margin: 0 }}>{t("If something is missing, such as the dates, we ask before planning.")}</p>
              </div>
              <div className="ps-cta">
                {errors}
                <button type="button" className="btn btn-primary btn-lg btn-block" onClick={submit}>{t("Plan my trip")}</button>
                <span className="hint">{t("Takes about 15 seconds. Nothing is booked until you say so.")}</span>
              </div>
            </aside>
          </div>
        ) : (
          <div className="form-grid">
            <section className="panel panel-pad fsec" aria-labelledby="f1">
              <h2 className="h3" id="f1">{t("Where and when")}</h2>
              <div className="two">
                <div className="field"><label htmlFor="from">{t("From")}</label><input className="input" id="from" placeholder={t("For example, Bengaluru")} autoComplete="off" value={form.from} onChange={(e) => setPlace("from", e.target.value)} /></div>
                <div className="field"><label htmlFor="to">{t("To")}</label><input className="input" id="to" placeholder={t("For example, Goa or Mysuru, Coorg")} autoComplete="off" value={form.to} onChange={(e) => setPlace("to", e.target.value)} /></div>
              </div>
              <div className="two">
                <div className="field"><label htmlFor="start">{t("First day")}</label><input className="input" id="start" type="date" value={form.start} onChange={(e) => set("start", e.target.value)} /></div>
                <div className="field"><label htmlFor="end">{t("Last day")}</label><input className="input" id="end" type="date" value={form.end} min={form.start} onChange={(e) => set("end", e.target.value)} /></div>
              </div>
              {cities.length > 1 && tripDays(form) > 0 && (
                <div className="field">
                  <span className="label">{t("Days in each city")}</span>
                  {cities.map((c, i) => (
                    <div className="stepper" key={`${c}-${i}`}>
                      <div><b>{c}</b></div>
                      <div className="step-ctl">
                        <button type="button" className="iconbtn round" aria-label={t("One day less in {city}", { city: c })} disabled={split[i] < 1} onClick={() => set("split", split.map((d, j) => (j === i ? d - 1 : d)))}>
                          <svg className="ic" viewBox="0 0 24 24" aria-hidden="true"><path d="M6 12h12" /></svg>
                        </button>
                        <output aria-label={t("Days in {city}", { city: c })}>{split[i]}</output>
                        <button type="button" className="iconbtn round" aria-label={t("One day more in {city}", { city: c })} onClick={() => set("split", split.map((d, j) => (j === i ? d + 1 : d)))}>
                          <svg className="ic" viewBox="0 0 24 24" aria-hidden="true"><path d="M6 12h12" /><path d="M12 6v12" /></svg>
                        </button>
                      </div>
                    </div>
                  ))}
                  <span className="hint">{t("{n} of {total} days", { n: split.reduce((a, b) => a + b, 0), total: tripDays(form) })}</span>
                </div>
              )}
            </section>

            <section className="panel panel-pad fsec" aria-labelledby="f2">
              <h2 className="h3" id="f2">{t("Who is going")}</h2>
              <div>
                {PEOPLE.map(([k, label, hint]) => (
                  <div className="stepper" key={k}>
                    <div><b>{t(label)}</b><small>{t(hint)}</small></div>
                    <div className="step-ctl">
                      <button type="button" className="iconbtn round" aria-label={t("One less: {who}", { who: t(label) })} onClick={() => set(k, Math.max(0, form[k] - 1))}>
                        <svg className="ic" viewBox="0 0 24 24" aria-hidden="true"><path d="M6 12h12" /></svg>
                      </button>
                      <output aria-label={t(label)}>{form[k]}</output>
                      <button type="button" className="iconbtn round" aria-label={t("One more: {who}", { who: t(label) })} onClick={() => set(k, Math.min(9, form[k] + 1))}>
                        <svg className="ic" viewBox="0 0 24 24" aria-hidden="true"><path d="M6 12h12" /><path d="M12 6v12" /></svg>
                      </button>
                    </div>
                  </div>
                ))}
              </div>
              <label className="check"><input type="checkbox" checked={form.stepFree} onChange={(e) => choose("stepFree", e.target.checked)} /><span>{t("Someone needs step-free access or a wheelchair")}</span></label>
            </section>

            <section className="panel panel-pad fsec" aria-labelledby="f3">
              <h2 className="h3" id="f3">{t("What you would like")}</h2>
              <div className="q-chips" role="group" aria-label={t("Interests")}>
                {INTERESTS.map((i) => {
                  const on = form.interests.includes(i);
                  return (
                    <button key={i} type="button" className={on ? "chip on" : "chip"} aria-pressed={on} onClick={() => choose("interests", on ? form.interests.filter((x) => x !== i) : [...form.interests, i])}>{t(i)}</button>
                  );
                })}
              </div>
              <div className="field"><span className="label">{t("How you travel")}</span>
                <div className="toggle wrap-toggle" role="group" aria-label={t("How you travel")}>
                  {TRANSPORTS.map(([v, label]) => <button key={label} type="button" className={(form.transport ?? null) === v ? "on" : undefined} aria-pressed={(form.transport ?? null) === v} onClick={() => choose("transport", v)}>{t(label)}</button>)}
                </div>
                <span className="hint">{t("We compare all three either way; the plan's journeys follow your choice.")}</span>
              </div>
              <div className="field"><span className="label">{t("Pace")}</span>
                <div className="toggle" role="group" aria-label={t("Pace")}>
                  {PACES.map(([v, label]) => <button key={v} type="button" className={form.pace === v ? "on" : undefined} aria-pressed={form.pace === v} onClick={() => choose("pace", v)}>{t(label)}</button>)}
                </div>
              </div>
              <div className="field"><span className="label">{t("Food")}</span>
                <div className="toggle wrap-toggle" role="group" aria-label={t("Food")}>
                  {FOODS.map((v) => <button key={v} type="button" className={form.food === v ? "on" : undefined} aria-pressed={form.food === v} onClick={() => choose("food", v)}>{t(v)}</button>)}
                </div>
              </div>
            </section>

            <section className="panel panel-pad fsec" aria-labelledby="f4">
              <h2 className="h3" id="f4">{t("Budget and language")}</h2>
              <div className="field">
                <label htmlFor="budget">{t("Budget for everyone")}</label>
                <div className="money"><span>₹</span><input className="input" id="budget" inputMode="numeric" value={form.budget} onChange={(e) => choose("budget", e.target.value)} /></div>
                <span className="hint">{t("For everything, including getting there. We show the split before you book.")}</span>
              </div>
              <div className="field"><span className="label">{t("Budget style")}</span>
                <div className="toggle wrap-toggle" role="group" aria-label={t("Budget style")}>
                  {BUDGET_STYLES.map(([v, label]) => <button key={v} type="button" className={(form.budgetStyle ?? "comfort") === v ? "on" : undefined} aria-pressed={(form.budgetStyle ?? "comfort") === v} onClick={() => choose("budgetStyle", v)}>{t(label)}</button>)}
                </div>
                <span className="hint">{t(BUDGET_STYLES.find(([v]) => v === (form.budgetStyle ?? "comfort"))![2])}</span>
              </div>
              {langPicker}
              {errors}
              <button type="button" className="btn btn-primary btn-lg btn-block" onClick={submit}>{t("Plan my trip")}</button>
            </section>
          </div>
        )}
      </div>
    </AppShell>
  );
}

export default function Page() {
  return (
    <Suspense>
      <PlanStart />
    </Suspense>
  );
}
