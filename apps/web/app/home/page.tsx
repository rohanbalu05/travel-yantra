"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { AppShell } from "@/components/AppShell";
import { PlayIcon, Wave } from "@/components/Wave";
import { useI18n } from "@/lib/i18n";
import { track } from "@/lib/metrics";
import { savePlanInput } from "@/lib/plan";
import "./home.css";

// Sample data only (Arjun Rao and family). TY4-02 swaps these for API data.
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

const pin = <path d="M12 21s-6.5-6.2-6.5-11.2a6.5 6.5 0 0 1 13 0C18.5 14.8 12 21 12 21Z" />;
const book = <path d="M4 5.5A2.5 2.5 0 0 1 6.5 3H20v15H6.5A2.5 2.5 0 0 0 4 20.5V5.5ZM4 20.5A2.5 2.5 0 0 1 6.5 18H20v3H6.5" />;

export default function HomePage() {
  const router = useRouter();
  const { lang, t } = useI18n();
  const [playing, setPlaying] = useState(false);
  const [ask, setAsk] = useState("");
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
          <h1>{t("Good evening, {name}.", { name: "Arjun" })}</h1>
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
                  <Link key={i} href={`/plan/start/?text=${encodeURIComponent(i)}`}>{i}</Link>
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
              <div className="mini">
                <div className="mini-top">
                  <button type="button" className="kp-play" onClick={() => setPlaying(!playing)} aria-label={playing ? t("Pause the Katha") : t("Play the Katha")}>
                    <PlayIcon playing={playing} />
                  </button>
                  <div>
                    <b>Mysuru in 5 minutes</b>
                    <span>City Katha for your trip this weekend</span>
                  </div>
                </div>
                <Wave play={playing} count={40} step={0.11} />
              </div>
              <div className="mini-links">
                <Link className="btn btn-cream" href="/katha/city/">{t("Open the City Katha")}</Link>
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
            <h2 className="h2" id="trips-h">{t("Your trips")}</h2>
            <Link href="/trips/" style={{ fontWeight: 700 }}>{t("See all trips")}</Link>
          </div>
          <div className="trips">
            {trips.map((trip) => (
              <Link key={trip.name} className="trip" href={trip.href}>
                <div className="trip-top"><b>{trip.name}</b><span className={trip.badge}>{trip.when}</span></div>
                <small>{trip.dates}</small>
                <div className="trip-route"><span>Bengaluru</span><i /><span>{trip.to}</span></div>
                <div className="trip-foot">
                  {trip.status.map(([cls, text]) => (
                    <span key={text} className={cls}>{text}</span>
                  ))}
                </div>
              </Link>
            ))}
          </div>
        </section>

        <aside className="side panel panel-pad" aria-labelledby="needs-h">
          <h2 className="h3" id="needs-h" style={{ marginBottom: 12 }}>{t("Needs you")}</h2>
          <div className="needs">
            {needs.map((n) => (
              <div className="need" key={n.title}>
                <span className={n.ok ? "ic-wrap ok" : "ic-wrap"}>
                  <svg className="ic" viewBox="0 0 24 24" aria-hidden="true"><path d={n.icon} /></svg>
                </span>
                <div>
                  <b>{n.title}</b>
                  <span>{n.text}</span>
                  {n.link && <Link href="/book/">{n.link}</Link>}
                </div>
              </div>
            ))}
          </div>
        </aside>
      </div>

      <section aria-labelledby="stories-h">
        <div className="sec-title">
          <h2 className="h2" id="stories-h">{t("Stories to start with")}</h2>
          <Link href="/katha/" style={{ fontWeight: 700 }}>{t("Open the Katha library")}</Link>
        </div>
        <div className="stories">
          <Link className="story" href="/katha/place/">
            <svg viewBox="0 0 320 180" aria-hidden="true">
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
            </svg>
            <div className="story-body"><b>Mysore Palace</b><div className="story-meta"><span className="tag tag-history">{t("History")}</span><span className="tag tag-legend">{t("Legend")}</span><span>{t("Place Katha · {min} min", { min: 8 })}</span></div></div>
          </Link>
          <Link className="story" href="/katha/city/">
            <svg viewBox="0 0 320 180" aria-hidden="true">
              <rect width="320" height="180" fill="#245A4B" />
              <path d="M0 180 L0 120 C60 96 110 70 170 64 C230 58 280 88 320 110 L320 180 Z" fill="#1A4337" />
              <g fill="#E7B25C"><rect x="150" y="40" width="22" height="26" /><path d="M146 42 L161 14 L176 42Z" /><rect x="159" y="6" width="4" height="10" /></g>
              <text x="24" y="160" className="kn" fontSize="46" fontWeight="700" fill="#F4EFE6">ಮೈಸೂರು</text>
            </svg>
            <div className="story-body"><b>Mysuru in 5 minutes</b><div className="story-meta"><span className="tag tag-legend">{t("Legend")}</span><span>{t("City Katha · 2, 5 or 10 min")}</span></div></div>
          </Link>
          <Link className="story" href="/trip/live/">
            <svg viewBox="0 0 320 180" aria-hidden="true">
              <rect width="320" height="180" fill="#DE9A58" />
              <rect y="140" width="320" height="40" fill="#3B7A91" />
              <g fill="#9E4529"><rect x="96" y="96" width="128" height="58" /><rect x="108" y="66" width="104" height="32" /><rect x="124" y="42" width="72" height="26" /><path d="M134 44 L134 30 Q160 10 186 30 L186 44Z" /></g>
              <g fill="#6D2E1B"><path d="M150 154 V130 A10 10 0 0 1 170 130 V154Z" /><circle cx="160" cy="80" r="7" /></g>
            </svg>
            <div className="story-body"><b>Saturday in Old Goa</b><div className="story-meta"><span className="tag tag-history">{t("History")}</span><span>{t("Day Katha · {stops} stops · {min} min", { stops: 5, min: 12 })}</span></div></div>
          </Link>
          <Link className="story" href="/katha/">
            <svg viewBox="0 0 320 180" aria-hidden="true">
              <rect width="320" height="180" fill="#C9B48A" />
              <path d="M0 180 L0 128 C40 110 70 132 100 118 C130 104 150 120 180 112 L320 120 L320 180Z" fill="#A88A62" />
              <g fill="#5E4630"><rect x="118" y="96" width="84" height="40" /><path d="M126 96 L160 50 L194 96Z" /><rect x="134" y="80" width="52" height="16" /><circle cx="132" cy="140" r="14" /><circle cx="188" cy="140" r="14" /></g>
              <g fill="#C9B48A"><circle cx="132" cy="140" r="5" /><circle cx="188" cy="140" r="5" /></g>
            </svg>
            <div className="story-body"><b>Hampi&apos;s stone chariot</b><div className="story-meta"><span className="tag tag-history">{t("History")}</span><span>{t("Place Katha · {min} min", { min: 6 })}</span></div></div>
          </Link>
        </div>
      </section>
    </AppShell>
  );
}
