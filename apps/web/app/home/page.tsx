"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { AppShell } from "@/components/AppShell";
import { PlayIcon } from "@/components/Wave";
import { listTrips, useAccount, type SavedTrip } from "@/lib/account";
import { dayLabel } from "@/lib/format";
import { LIBRARY_FALLBACK, kathaLibrary, type LibraryItem } from "@/lib/guide";
import { useI18n } from "@/lib/i18n";
import { track } from "@/lib/metrics";
import { savePlanInput, savePlanResult, usePlanResult } from "@/lib/plan";
import { latestTrips, loadTrip } from "@/lib/trips";
import { TripMeta } from "@/components/TripMeta";
import "./home.css";

// Sample data only (Arjun Rao and family), shown and labelled as samples until the person has trips.
const trips = [
  { href: "/plan/itinerary/", name: "Goa with family", badge: "badge badge-sea", when: "In 6 weeks", dates: "Fri 11 to Mon 14 Dec · 4 travellers", to: "Goa", status: [["st st-ok", "3 of 5 booked"], ["st st-wait", "Return train waitlisted"]] },
  { href: "/katha/day/", name: "Mysuru weekend", badge: "badge badge-ok", when: "This weekend", dates: "Sat 31 Oct to Sun 1 Nov · 3 travellers", to: "Mysuru", status: [["st st-ok", "Plan and Day Katha ready"]] },
  { href: "/trips/", name: "Temple trail", badge: "badge", when: "Draft", dates: "Udupi, Kollur and Sringeri · 3 days", to: "Udupi", status: [["st st-off", "Dates not set"]] },
];

const needs = [
  { ok: false, icon: "M6 3h12v13H6zM6 10h12M8 16l-2 4M16 16l2 4M7 19h10", title: "Return train is waitlisted", text: "Moved from WL 12 to WL 7 this morning. We will tell you the moment it confirms.", link: "See booking" },
  { ok: false, icon: "M5 16V12l2-5h10l2 5v4M3 16h18v2H3z", title: "Saturday's cab is not booked", text: "A day cab for Old Goa and Ponda, about ₹2,600.", link: "Book it" },
  { ok: true, icon: "M12 4v11M7.5 10.5L12 15l4.5-4.5M5 19h14", title: "Mysuru Katha saved for offline", text: "Both days, in English and Kannada, 38 MB." },
];

const ideas = ["Goa with family", "A weekend in Mysuru", "Temple trail: Udupi, Kollur, Sringeri", "Hampi in 3 days"];

/** Illustrations for story cards (decorative), used in turn. */
const ART = [
  <svg key="art0" viewBox="0 0 320 180" aria-hidden="true">
    <rect width="320" height="180" fill="#E3A33B" />
    <circle cx="250" cy="52" r="22" fill="#F3CB7A" />
    <g fill="#7A3A1E">
    <rect x="36" y="112" width="248" height="68" />
    <rect x="132" y="76" width="56" height="36" />
    <path d="M128 78 Q160 22 192 78Z" />
    <rect x="157" y="20" width="6" height="18" />
    <rect x="58" y="92" width="36" height="20" /><path d="M56 94 Q76 62 96 94Z" />
    <rect x="226" y="92" width="36" height="20" /><path d="M224 94 Q244 62 264 94Z" />
    </g>
    </svg>,
  <svg key="art1" viewBox="0 0 320 180" aria-hidden="true">
    <rect width="320" height="180" fill="#245A4B" />
    <path d="M0 180 L0 120 C60 96 110 70 170 64 C230 58 280 88 320 110 L320 180 Z" fill="#1A4337" />
    <g fill="#E7B25C"><rect x="150" y="40" width="22" height="26" /><path d="M146 42 L161 14 L176 42Z" /><rect x="159" y="6" width="4" height="10" /></g>
    <text x="24" y="160" className="kn" fontSize="46" fontWeight="700" fill="#F4EFE6">ಮೈಸೂರು</text>
    </svg>,
  <svg key="art2" viewBox="0 0 320 180" aria-hidden="true">
    <rect width="320" height="180" fill="#DE9A58" />
    <rect y="140" width="320" height="40" fill="#3B7A91" />
    <g fill="#9E4529"><rect x="96" y="96" width="128" height="58" /><rect x="108" y="66" width="104" height="32" /><rect x="124" y="42" width="72" height="26" /><path d="M134 44 L134 30 Q160 10 186 30 L186 44Z" /></g>
    <g fill="#6D2E1B"><path d="M150 154 V130 A10 10 0 0 1 170 130 V154Z" /><circle cx="160" cy="80" r="7" /></g>
    </svg>,
  <svg key="art3" viewBox="0 0 320 180" aria-hidden="true">
    <rect width="320" height="180" fill="#C9B48A" />
    <path d="M0 180 L0 128 C40 110 70 132 100 118 C130 104 150 120 180 112 L320 120 L320 180Z" fill="#A88A62" />
    <g fill="#5E4630"><rect x="118" y="96" width="84" height="40" /><path d="M126 96 L160 50 L194 96Z" /><rect x="134" y="80" width="52" height="16" /><circle cx="132" cy="140" r="14" /><circle cx="188" cy="140" r="14" /></g>
    <g fill="#C9B48A"><circle cx="132" cy="140" r="5" /><circle cx="188" cy="140" r="5" /></g>
    </svg>,
];

const pin = <path d="M12 21s-6.5-6.2-6.5-11.2a6.5 6.5 0 0 1 13 0C18.5 14.8 12 21 12 21Z" />;
const book = <path d="M4 5.5A2.5 2.5 0 0 1 6.5 3H20v15H6.5A2.5 2.5 0 0 0 4 20.5V5.5ZM4 20.5A2.5 2.5 0 0 1 6.5 18H20v3H6.5" />;

export default function HomePage() {
  const router = useRouter();
  const { lang, t } = useI18n();
  const user = useAccount()?.user;
  // Signed in: their own first name. Never the sample persona's name for a real visitor.
  const firstName = user?.name ? user.name.split(" ")[0] : null;
  const greeting = useGreeting(firstName);
  const plan = usePlanResult();
  const [library, setLibrary] = useState<LibraryItem[]>(LIBRARY_FALLBACK);
  useEffect(() => {
    const ctl = new AbortController();
    kathaLibrary(lang, ctl.signal).then((r) => setLibrary(r.items), () => {});
    return () => ctl.abort();
  }, [lang]);
  // Stories with audio first, four of them; the featured city is the trip's own when there is a plan.
  const stories = [...library].sort((a, b) => Number(b.has_audio) - Number(a.has_audio)).slice(0, 4);
  const featured = plan?.itinerary.request.destinations[0] ?? library.find((x) => x.subject_kind === "city")?.subject ?? "Mysuru";
  // Saved trips from the API (signed in) or this browser; null until known.
  const [mine, setMine] = useState<SavedTrip[] | null>(null);
  useEffect(() => {
    let live = true;
    listTrips()
      .then((r) => live && setMine(latestTrips(r.trips)))
      .catch(() => live && setMine([]));
    return () => {
      live = false;
    };
  }, []);
  const [ask, setAsk] = useState("");
  const [opening, setOpening] = useState<string | null>(null);
  // The owner's own trip reopens the editable Itinerary; on failure, My trips explains.
  const openTrip = async (trip: SavedTrip) => {
    setOpening(trip.plan_id);
    try {
      savePlanResult(await loadTrip(trip));
      router.push("/plan/itinerary/");
    } catch {
      router.push("/trips/");
    }
  };
  // Sample reminders only for a first-time visitor, labelled; never beside a real person's trips.
  const showSampleNeeds = mine !== null && !mine.length && !(user && !user.demo);
  // Typed text goes straight to planning; an empty box opens the full start page.
  const planIt = () => {
    const text = ask.trim();
    if (!text) return router.push("/plan/start/");
    savePlanInput({ text, lang });
    track("start");
    router.push("/plan/thinking/");
  };
  return (
    <AppShell>
      <div>
        <div className="hm-greet">
          <h1 suppressHydrationWarning>{greeting}</h1>
          <p className="page-sub">{t("Plan something new, or hear the story of where you are going.")}</p>
        </div>

        <div className="doors">
          <section className="door door-plan" aria-labelledby="plan-h">
            <svg className="door-art" viewBox="0 0 440 440" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
              <path d="M70 40 C60 90 80 120 70 160 C64 190 90 220 100 260 C112 306 130 340 150 400" />
              <path d="M380 330 C330 290 300 240 250 210 C200 180 150 130 96 104" strokeDasharray="3 10" strokeWidth="4" strokeLinecap="round" />
              <circle cx="380" cy="330" r="9" />
              <circle cx="96" cy="104" r="9" />
              <path d="M300 60h80v80h-80z" />
              <circle cx="340" cy="100" r="28" />
            </svg>
            <span className="door-k">
              <svg className="ic" viewBox="0 0 24 24" aria-hidden="true">{pin}<circle cx="12" cy="10" r="2.3" /></svg>
              {t("Planning")}
            </span>
            <h2 id="plan-h">{t("Plan a trip")}</h2>
            <p>{t("Say where, when and who you are going with. Get road, rail and air compared, a plan checked stop by stop, and every booking lined up.")}</p>
            <div className="door-box">
              <div className="hm-composer">
                <label htmlFor="hm-ask">{t("Where do you want to go?")}</label>
                <textarea id="hm-ask" value={ask} maxLength={4000} onChange={(e) => setAsk(e.target.value)} placeholder={t("Bengaluru to Goa, 11 to 14 Dec, with my parents and sister. Churches, temples, a little beach.")} />
                <div className="hm-composer-row">
                  <button type="button" className="btn btn-primary" onClick={planIt}>{t("Plan my trip")}</button>
                </div>
              </div>
              <div className="hm-chips" aria-label={t("Ideas")}>
                {ideas.map((i) => (
                  <Link key={i} href={`/plan/start/?text=${encodeURIComponent(t(i))}`}>{t(i)}</Link>
                ))}
              </div>
            </div>
          </section>

          <section className="door door-katha" aria-labelledby="katha-h">
            <span className="door-art" aria-hidden="true">ಕಥೆ</span>
            <span className="door-k">
              <svg className="ic" viewBox="0 0 24 24" aria-hidden="true">{book}</svg>
              {t("Katha")}
            </span>
            <h2 id="katha-h">{t("Hear the story")}</h2>
            <p>{t("The history and the legends of a city, a place or your planned day, told in your language, with each legend labelled as one.")}</p>
            <div className="door-box">
              {/* A real story to open: the trip's first city, else one from TY2's library. No fake player here. */}
              <Link className="mini mini-link" href={`/katha/city/?subject=${encodeURIComponent(featured)}`}>
                <div className="mini-top">
                  <span className="kp-play" aria-hidden="true"><PlayIcon playing={false} /></span>
                  <div>
                    <b>{featured}</b>
                    <span>{t("City Katha · 2 or 5 min")}</span>
                  </div>
                </div>
              </Link>
              <div className="mini-links">
                <Link className="btn btn-cream" href={`/katha/city/?subject=${encodeURIComponent(featured)}`}>{t("Open the City Katha")}</Link>
                <Link className="btn btn-on-dark" href="/katha/">{t("Browse the library")}</Link>
                <Link className="btn btn-on-dark" href="/ask/">{t("Ask the guide")}</Link>
              </div>
            </div>
          </section>
        </div>
      </div>

      <div className="split">
        <section className="main" aria-labelledby="trips-h">
          <div className="sec-title">
            <h2 className="h2" id="trips-h">{mine?.length ? t("Your trips") : t("Sample trips")}</h2>
            <Link href="/trips/" style={{ fontWeight: 700 }}>{t("See all trips")}</Link>
          </div>
          {/* Home and My trips agree (QA #116): the person's own trips when there are any, else samples marked as such. */}
          {mine?.length ? (
            <div className="trips">
              {mine.slice(0, 3).map((trip) => (
                <button key={trip.plan_id} type="button" className="trip" disabled={opening !== null} aria-busy={opening === trip.plan_id} onClick={() => void openTrip(trip)}>
                  <div className="trip-top"><b>{trip.title}</b><span className="trip-open">{opening === trip.plan_id ? `${t("Loading")}…` : t("View details")}</span></div>
                  <small>{t("{from} to {to}", { from: dayLabel(trip.start_date, lang), to: dayLabel(trip.end_date, lang) })}</small>
                  <TripMeta trip={trip} />
                  <div className="trip-route"><span>{trip.origin}</span><i /><span>{trip.destinations.at(-1)}</span></div>
                </button>
              ))}
            </div>
          ) : (
          <>
          <p className="hint" style={{ margin: "0 0 12px" }}>{t("Examples from the sample family (Arjun Rao and family), to show how trips look. Yours appear here once you plan one with Keep my trips on.")}</p>
          <div className="trips">
            {trips.map((trip) => (
              <Link key={trip.name} className="trip" href={trip.href}>
                <div className="trip-top"><b>{t(trip.name)}</b><span className="badge">{t("Sample")}</span></div>
                <small>{t(trip.dates)}</small>
                <div className="trip-route"><span>Bengaluru</span><i /><span>{trip.to}</span></div>
                <div className="trip-foot">
                  {trip.status.map(([cls, text]) => (
                    <span key={text} className={cls}>{t(text)}</span>
                  ))}
                </div>
              </Link>
            ))}
          </div>
          </>
          )}
        </section>

        {showSampleNeeds && (
        <aside className="side panel panel-pad" aria-labelledby="needs-h">
          <h2 className="h3" id="needs-h" style={{ marginBottom: 12 }}>{t("Needs you")} <span className="badge">{t("Sample")}</span></h2>
          <div className="needs">
            {needs.map((n) => (
              <div className="need" key={n.title}>
                <span className={n.ok ? "ic-wrap ok" : "ic-wrap"}>
                  <svg className="ic" viewBox="0 0 24 24" aria-hidden="true"><path d={n.icon} /></svg>
                </span>
                <div>
                  <b>{t(n.title)}</b>
                  <span>{t(n.text)}</span>
                  {n.link && <Link href="/book/">{t(n.link)}</Link>}
                </div>
              </div>
            ))}
          </div>
        </aside>
        )}
      </div>

      <section aria-labelledby="stories-h">
        <div className="sec-title">
          <h2 className="h2" id="stories-h">{t("Stories to start with")}</h2>
          <Link href="/katha/" style={{ fontWeight: 700 }}>{t("Open the Katha library")}</Link>
        </div>
        {/* TY2's library: real subjects, real lengths (10 minutes hidden), an Audio tag where it is recorded. */}
        <div className="stories">
          {stories.map((x, i) => (
            <Link key={x.subject_kind + x.subject} className="story" href={`/katha/${x.subject_kind}/?subject=${encodeURIComponent(x.subject)}`}>
              {ART[i % ART.length]}
              <div className="story-body">
                <b>{x.subject}</b>
                <div className="story-meta">
                  {x.has_audio && <span className="tag tag-history">{t("Audio")}</span>}
                  <span>{t(x.subject_kind === "city" ? "City Katha" : "Place Katha")}{x.lengths.some((n) => n === 2 || n === 5) ? ` · ${t("{list} min", { list: x.lengths.filter((n) => n === 2 || n === 5).join(", ") })}` : ""}</span>
                </div>
              </div>
            </Link>
          ))}
        </div>
      </section>
    </AppShell>
  );
}

/** Good morning / afternoon / evening by this device's clock (re-read every minute). */
function useGreeting(name: string | null): string {
  const { t } = useI18n();
  const [hour, setHour] = useState<number | null>(null);
  useEffect(() => {
    const tick = () => setHour(new Date().getHours());
    tick();
    const id = setInterval(tick, 60_000);
    return () => clearInterval(id);
  }, []);
  if (hour === null) return name ? t("Hello, {name}.", { name }) : t("Hello.");
  const part = hour < 5 ? "evening" : hour < 12 ? "morning" : hour < 17 ? "afternoon" : "evening";
  const key = { morning: "Good morning", afternoon: "Good afternoon", evening: "Good evening" }[part];
  return name ? t(`${key}, {name}.`, { name }) : t(`${key}.`);
}
