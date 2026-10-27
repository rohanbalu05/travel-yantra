"use client";

import Link from "next/link";
import { useRef, useState } from "react";
import { AppShell } from "@/components/AppShell";
import { Cited, Sources } from "@/components/Cited";
import { Problem, problemOf } from "@/components/Problem";
import type { GuideAnswer, Place } from "@/lib/contracts";
import { useAccount } from "@/lib/account";
import { askGuide } from "@/lib/guide";
import { useI18n } from "@/lib/i18n";
import { osmLink } from "@/lib/map";
import { usePlanResult } from "@/lib/plan";
import "../guide.css";

type Turn = { id: number; q: string; a?: GuideAnswer; problem?: { message: string; retryable: boolean } };

const TRIES = [
  { q: "Why is the Basilica of Bom Jesus famous?", k: "History" },
  { q: "What should we wear to the Basilica?", k: "Etiquette" },
  { q: "Where is the nearest hospital?", k: "Emergency" },
];

function Emergency({ places }: { places: Place[] }) {
  return (
    <div className="urgent">
      <b>In an emergency, call 112</b>
      <ul>
        {places.map((p) => (
          <li key={p.id}>
            <span>{p.name}</span>
            <a className="btn btn-white btn-sm" href={osmLink(p.lat, p.lng)} target="_blank" rel="noopener noreferrer">Map</a>
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

  return (
    <AppShell>
      <div>
        <div className="ag-head">
          <h1 className="page-title">{t("Ask the guide")}</h1>
          <p className="page-sub">History, food, culture and what to do in an emergency{city ? ` in ${city}` : ""}. Every answer names its sources; if there is no source, the guide says so instead of guessing.</p>
        </div>
        <div className="split">
          <section className="main conv" aria-label="Conversation" aria-live="polite">
            {turns.length === 0 && <p className="hint" style={{ margin: 0 }}>Ask anything below, or pick a question to start.</p>}
            {turns.map((t) => (
              <div key={t.id} className="turn">
                <div className="msg-user">{t.q}</div>
                {t.a ? (
                  <div className="ans">
                    <p><Cited text={t.a.text} id={`a${t.id}`} count={t.a.citations?.length ?? 0} /></p>
                    {!!t.a.emergency_places?.length && <Emergency places={t.a.emergency_places} />}
                    {t.a.citations?.length ? <Sources id={`a${t.id}`} items={t.a.citations} /> : <small className="hint">No sourced answer, so nothing is cited.</small>}
                  </div>
                ) : t.problem ? (
                  <Problem {...t.problem} onRetry={() => void run(t.id, t.q)} />
                ) : (
                  <div className="ans pending">Looking it up…</div>
                )}
              </div>
            ))}
            <form className="composer" onSubmit={(e) => { e.preventDefault(); ask(draft); }}>
              <label htmlFor="ask-q" className="sr">Your question</label>
              <textarea id="ask-q" value={draft} maxLength={500} placeholder="Ask the guide…" onChange={(e) => setDraft(e.target.value)}
                onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); ask(draft); } }} />
              <button type="submit" className="iconbtn round dark" aria-label="Ask" disabled={busy || !draft.trim()}>
                <svg className="ic" viewBox="0 0 24 24" aria-hidden="true"><path d="M5 12h14" /><path d="M13 6l6 6-6 6" /></svg>
              </button>
            </form>
          </section>
          <aside className="side" style={{ display: "flex", flexDirection: "column", gap: 16 }}>
            <section className="panel panel-pad" aria-labelledby="try-h">
              <h2 className="h3" id="try-h" style={{ marginBottom: 12 }}>Try asking</h2>
              <div className="tries">
                {TRIES.map((x) => (
                  <button key={x.q} type="button" className="try" disabled={busy} onClick={() => ask(x.q)}><b>{x.q}</b><span>{x.k}</span></button>
                ))}
              </div>
            </section>
            <section className="panel panel-pad" aria-labelledby="loc-h">
              <h2 className="h3" id="loc-h" style={{ marginBottom: 8 }}>{t("Emergency numbers")}</h2>
              <p className="hint" style={{ margin: "0 0 12px" }}>For the nearest hospital, police or pharmacy, the guide can use where you are. It is sent only with your questions and not stored.</p>
              {account?.consents.location ? (
                <button type="button" className="btn btn-quiet btn-sm" onClick={share} disabled={!!pos}>{pos ? "Location shared" : "Share my location"}</button>
              ) : (
                <p className="hint" style={{ margin: 0 }}>Turn on <Link href="/settings/">Use my location for emergencies</Link> in Settings first.</p>
              )}
              {posNote && <p className="hint" role="status" style={{ margin: "8px 0 0" }}>{posNote}</p>}
            </section>
          </aside>
        </div>
      </div>
    </AppShell>
  );
}
