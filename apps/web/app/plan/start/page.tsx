"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { AppShell } from "@/components/AppShell";
import { Trail } from "@/components/Trail";
import type { Lang, TripDraft } from "@/lib/contracts";
import { track } from "@/lib/metrics";
import { savePlanInput } from "@/lib/plan";
import { FOODS, INTERESTS, PACES, formFromDraft, formProblems, goaForm, toTripRequest, type TripForm } from "@/lib/tripForm";
import "../plan.css";

const LANGS: [Lang, string][] = [["en", "English"], ["hi", "हिन्दी"], ["kn", "ಕನ್ನಡ"], ["ta", "தமிழ்"], ["te", "తెలుగు"], ["bn", "বাংলা"]];

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
  const [text, setText] = useState(params.get("text") ?? SAMPLE_TEXT);
  const [lang, setLang] = useState<Lang>("en");
  // From needs_input, the form starts from what intake understood; otherwise from the Goa sample.
  const [form, setForm] = useState<TripForm>(() => {
    try {
      const d = params.get("draft");
      return d ? formFromDraft(JSON.parse(d) as TripDraft) : goaForm();
    } catch {
      return goaForm();
    }
  });
  const [tried, setTried] = useState(false);

  const set = <K extends keyof TripForm>(k: K, v: TripForm[K]) => setForm((f) => ({ ...f, [k]: v }));
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
      <span className="label">Plan and Katha in</span>
      <div className="toggle wrap-toggle" role="group" aria-label="Language for the plan">
        {LANGS.map(([k, label]) => (
          <button key={k} type="button" className={k === lang ? "on" : undefined} aria-pressed={k === lang} onClick={() => setLang(k)}>
            {label}
          </button>
        ))}
      </div>
    </div>
  );

  const errors = tried && problems.length > 0 && (
    <ul className="ps-errors" role="alert">
      {problems.map((p) => <li key={p}>{p}</li>)}
    </ul>
  );

  return (
    <AppShell>
      <div>
        <div className="ps-head">
          <Trail at={1} />
          <div className="ps-titlebar">
            <div className="col-10">
              <h1 className="page-title">Tell us about the trip</h1>
              <p className="page-sub">In your own words, in any of six languages, or fill in a form. Either way the AI checks what it understood before it plans.</p>
            </div>
            <div className="toggle" role="group" aria-label="How to describe the trip">
              <button type="button" className={mode === "words" ? "on" : undefined} aria-pressed={mode === "words"} onClick={() => setMode("words")}>In your words</button>
              <button type="button" className={mode === "form" ? "on" : undefined} aria-pressed={mode === "form"} onClick={() => setMode("form")}>Fill a form</button>
            </div>
          </div>
        </div>

        {mode === "words" ? (
          <div className="split">
            <section className="main panel panel-pad fsec" aria-labelledby="w-h">
              <h2 className="h3" id="w-h">Where, when and who</h2>
              <div className="field">
                <label htmlFor="trip-text">Your trip, in your words</label>
                <textarea id="trip-text" className="input ps-text" value={text} maxLength={4000} onChange={(e) => setText(e.target.value)} />
                <span className="hint">Say where from and to, the dates, who is going, and anything that matters: food, walking, budget.</span>
              </div>
            </section>
            <aside className="side panel" aria-labelledby="go-h">
              <div className="panel-head"><h2 className="h3" id="go-h">Before we plan</h2></div>
              <div className="panel-pad fsec">
                {langPicker}
                <p className="hint" style={{ margin: 0 }}>If something is missing, such as the dates, we ask before planning.</p>
              </div>
              <div className="ps-cta">
                {errors}
                <button type="button" className="btn btn-primary btn-lg btn-block" onClick={submit}>Plan my trip</button>
                <span className="hint">Takes about 15 seconds. Nothing is booked until you say so.</span>
              </div>
            </aside>
          </div>
        ) : (
          <div className="form-grid">
            <section className="panel panel-pad fsec" aria-labelledby="f1">
              <h2 className="h3" id="f1">Where and when</h2>
              <div className="two">
                <div className="field"><label htmlFor="from">From</label><input className="input" id="from" value={form.from} onChange={(e) => set("from", e.target.value)} /></div>
                <div className="field"><label htmlFor="to">To</label><input className="input" id="to" value={form.to} onChange={(e) => set("to", e.target.value)} /></div>
              </div>
              <div className="two">
                <div className="field"><label htmlFor="start">First day</label><input className="input" id="start" type="date" value={form.start} onChange={(e) => set("start", e.target.value)} /></div>
                <div className="field"><label htmlFor="end">Last day</label><input className="input" id="end" type="date" value={form.end} min={form.start} onChange={(e) => set("end", e.target.value)} /></div>
              </div>
            </section>

            <section className="panel panel-pad fsec" aria-labelledby="f2">
              <h2 className="h3" id="f2">Who is going</h2>
              <div>
                {PEOPLE.map(([k, label, hint]) => (
                  <div className="stepper" key={k}>
                    <div><b>{label}</b><small>{hint}</small></div>
                    <div className="step-ctl">
                      <button type="button" className="iconbtn round" aria-label={`One less: ${label}`} onClick={() => set(k, Math.max(0, form[k] - 1))}>
                        <svg className="ic" viewBox="0 0 24 24" aria-hidden="true"><path d="M6 12h12" /></svg>
                      </button>
                      <output aria-label={label}>{form[k]}</output>
                      <button type="button" className="iconbtn round" aria-label={`One more: ${label}`} onClick={() => set(k, Math.min(9, form[k] + 1))}>
                        <svg className="ic" viewBox="0 0 24 24" aria-hidden="true"><path d="M6 12h12" /><path d="M12 6v12" /></svg>
                      </button>
                    </div>
                  </div>
                ))}
              </div>
              <label className="check"><input type="checkbox" checked={form.stepFree} onChange={(e) => set("stepFree", e.target.checked)} /><span>Someone needs step-free access or a wheelchair</span></label>
            </section>

            <section className="panel panel-pad fsec" aria-labelledby="f3">
              <h2 className="h3" id="f3">What you would like</h2>
              <div className="q-chips" role="group" aria-label="Interests">
                {INTERESTS.map((i) => {
                  const on = form.interests.includes(i);
                  return (
                    <button key={i} type="button" className={on ? "chip on" : "chip"} aria-pressed={on} onClick={() => set("interests", on ? form.interests.filter((x) => x !== i) : [...form.interests, i])}>{i}</button>
                  );
                })}
              </div>
              <div className="field"><span className="label">Pace</span>
                <div className="toggle" role="group" aria-label="Pace">
                  {PACES.map(([v, label]) => <button key={v} type="button" className={form.pace === v ? "on" : undefined} aria-pressed={form.pace === v} onClick={() => set("pace", v)}>{label}</button>)}
                </div>
              </div>
              <div className="field"><span className="label">Food</span>
                <div className="toggle wrap-toggle" role="group" aria-label="Food">
                  {FOODS.map((v) => <button key={v} type="button" className={form.food === v ? "on" : undefined} aria-pressed={form.food === v} onClick={() => set("food", v)}>{v}</button>)}
                </div>
              </div>
            </section>

            <section className="panel panel-pad fsec" aria-labelledby="f4">
              <h2 className="h3" id="f4">Budget and language</h2>
              <div className="field">
                <label htmlFor="budget">Budget for everyone</label>
                <div className="money"><span>₹</span><input className="input" id="budget" inputMode="numeric" value={form.budget} onChange={(e) => set("budget", e.target.value)} /></div>
                <span className="hint">For everything, including getting there. We show the split before you book.</span>
              </div>
              {langPicker}
              {errors}
              <button type="button" className="btn btn-primary btn-lg btn-block" onClick={submit}>Plan my trip</button>
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
