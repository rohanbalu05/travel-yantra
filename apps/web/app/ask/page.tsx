"use client";

import Link from "next/link";
import { useRef, useState } from "react";
import { AppShell } from "@/components/AppShell";
import { Cited, Sources } from "@/components/Cited";
import { Problem, problemOf } from "@/components/Problem";
import type { GuideAnswer, Place } from "@/lib/contracts";
import { useAccount } from "@/lib/account";
import { askGuide } from "@/lib/guide";
import { useI18n, type Vars } from "@/lib/i18n";
import { osmLink } from "@/lib/map";
import { usePlanResult } from "@/lib/plan";
import "../guide.css";

type Turn = { id: number; q: string; a?: GuideAnswer; problem?: { message: string; retryable: boolean } };

// Starter questions and topics: dictionary keys, asked in the traveller's language. With a plan they
// name its first stop (QA #119); without one, general questions (never a sample trip's place).
const tries = (place: string | null): { q: string; v: Vars; k: string }[] =>
  place
    ? [
        { q: "Why is {place} famous?", v: { place }, k: "History" },
        { q: "What should we wear to {place}?", v: { place }, k: "Etiquette" },
        { q: "Where is the nearest hospital?", v: {}, k: "Emergency" },
      ]
    : [
        { q: "What should we wear to a temple?", v: {}, k: "Etiquette" },
        { q: "Where is the nearest hospital?", v: {}, k: "Emergency" },
      ];

function Emergency({ places }: { places: Place[] }) {
  const { t } = useI18n();
  return (
    <div className="urgent">
      <b>{t("In an emergency, call 112")}</b>
      <ul>
        {places.map((p) => (
          <li key={p.id}>
            <span>{p.name}</span>
            <a className="btn btn-white btn-sm" href={osmLink(p.lat, p.lng)} target="_blank" rel="noopener noreferrer">{t("Map")}</a>
          </li>
        ))}
      </ul>
    </div>
  );
}

export default function AskGuide() {
  const plan = usePlanResult();
  const { lang, t } = useI18n();
  const account = useAccount();
  const city = plan?.itinerary.request.destinations[0] ?? null;
  const firstStop = plan?.itinerary.days.flatMap((d) => d.stops ?? [])[0];
  const TRIES = tries(firstStop ? firstStop.native_names?.[lang] ?? firstStop.name : null);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [pos, setPos] = useState<{ lat: number; lng: number } | null>(null);
  const [posNote, setPosNote] = useState<string | null>(null);
  const seq = useRef(0);

  const run = async (id: number, q: string) => {
    setBusy(true);
    setTurns((t) => t.map((x) => (x.id === id ? { id, q } : x)));
    try {
      const a = await askGuide({ question: q, lang, city, lat: pos?.lat ?? null, lng: pos?.lng ?? null, has_elderly: (plan?.itinerary.request.constraints?.travellers ?? []).some((t) => t.age >= 60) });
      setTurns((t) => t.map((x) => (x.id === id ? { id, q, a } : x)));
    } catch (e) {
      setTurns((t) => t.map((x) => (x.id === id ? { id, q, problem: problemOf(e) } : x)));
    } finally {
      setBusy(false);
    }
  };

  const ask = (q: string) => {
    const text = q.trim().slice(0, 500);
    if (!text || busy) return;
    const id = ++seq.current;
    setTurns((t) => [...t, { id, q: text }]);
    setDraft("");
    void run(id, text);
  };

  // Location is only read when the traveller asks for it, and only sent with questions.
  // posNote holds the English text; it is translated where it is shown.
  const share = () => {
    if (!("geolocation" in navigator)) return setPosNote("This browser cannot share a location.");
    navigator.geolocation.getCurrentPosition(
      (p) => {
        setPos({ lat: p.coords.latitude, lng: p.coords.longitude });
        setPosNote("Location shared for emergency answers in this tab.");
      },
      () => setPosNote("Location not shared. Emergency answers will use your plan's city."),
    );
  };

  // The settings link sits inside the sentence, wherever the language puts it.
  const turnOn = t("Turn on {setting} in Settings first.").split("{setting}");

  return (
    <AppShell>
      <div>
        <div className="ag-head">
          <h1 className="page-title">{city ? t("Ask the guide about {city}", { city }) : t("Ask the guide")}</h1>
          <p className="page-sub">{city ? t("History, food, culture and what to do in an emergency in {city}. Every answer names its sources; if there is no source, the guide says so instead of guessing.", { city }) : t("History, food, culture and what to do in an emergency. Every answer names its sources; if there is no source, the guide says so instead of guessing.")}</p>
        </div>
        <div className="split">
          <section className="main conv" aria-label={t("Conversation")} aria-live="polite">
            {turns.length === 0 && <p className="hint" style={{ margin: 0 }}>{t("Ask anything below, or pick a question to start.")}</p>}
            {turns.map((x) => (
              <div key={x.id} className="turn">
                <div className="msg-user">{x.q}</div>
                {x.a ? (
                  <div className="ans">
                    <p><Cited text={x.a.text} id={`a${x.id}`} count={x.a.citations?.length ?? 0} /></p>
                    {!!x.a.emergency_places?.length && <Emergency places={x.a.emergency_places} />}
                    {x.a.citations?.length ? <Sources id={`a${x.id}`} items={x.a.citations} /> : <small className="hint">{t("No sourced answer, so nothing is cited.")}</small>}
                  </div>
                ) : x.problem ? (
                  <Problem {...x.problem} onRetry={() => void run(x.id, x.q)} />
                ) : (
                  <div className="ans pending">{t("Looking it up…")}</div>
                )}
              </div>
            ))}
            <form className="composer" onSubmit={(e) => { e.preventDefault(); ask(draft); }}>
              <label htmlFor="ask-q" className="sr">{t("Your question")}</label>
              <textarea id="ask-q" value={draft} maxLength={500} placeholder={t("Ask the guide…")} onChange={(e) => setDraft(e.target.value)}
                onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); ask(draft); } }} />
              <button type="submit" className="iconbtn round dark" aria-label={t("Ask")} disabled={busy || !draft.trim()}>
                <svg className="ic" viewBox="0 0 24 24" aria-hidden="true"><path d="M5 12h14" /><path d="M13 6l6 6-6 6" /></svg>
              </button>
            </form>
          </section>
          <aside className="side" style={{ display: "flex", flexDirection: "column", gap: 16 }}>
            <section className="panel panel-pad" aria-labelledby="try-h">
              <h2 className="h3" id="try-h" style={{ marginBottom: 12 }}>{t("Try asking")}</h2>
              <div className="tries">
                {TRIES.map((x) => (
                  <button key={x.q} type="button" className="try" disabled={busy} onClick={() => ask(t(x.q, x.v))}><b>{t(x.q, x.v)}</b><span>{t(x.k)}</span></button>
                ))}
              </div>
            </section>
            <section className="panel panel-pad" aria-labelledby="loc-h">
              <h2 className="h3" id="loc-h" style={{ marginBottom: 8 }}>{t("Emergency numbers")}</h2>
              <p className="hint" style={{ margin: "0 0 12px" }}>{t("For the nearest hospital, police or pharmacy, the guide can use where you are. It is sent only with your questions and not stored.")}</p>
              {account?.consents.location ? (
                <button type="button" className="btn btn-quiet btn-sm" onClick={share} disabled={!!pos}>{pos ? t("Location shared") : t("Share my location")}</button>
              ) : (
                <p className="hint" style={{ margin: 0 }}>{turnOn[0]}<Link href="/settings/">{t("Use my location for emergencies")}</Link>{turnOn[1]}</p>
              )}
              {posNote && <p className="hint" role="status" style={{ margin: "8px 0 0" }}>{t(posNote)}</p>}
            </section>
          </aside>
        </div>
      </div>
    </AppShell>
  );
}
