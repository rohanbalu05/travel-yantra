"use client";

import Link from "next/link";
import { AppShell } from "@/components/AppShell";
import { GOA_ITINERARY } from "@/lib/mockPlan";
import { usePlanResult } from "@/lib/plan";
import "../guide.css";

const LIBRARY = [
  { kind: "city", subject: "Mysuru", note: "City Katha" },
  { kind: "city", subject: "Goa", note: "City Katha" },
  { kind: "place", subject: "Basilica of Bom Jesus", note: "Place Katha" },
] as const;

const href = (kind: "place" | "city", subject: string) => `/katha/${kind}/?subject=${encodeURIComponent(subject)}`;

export default function KathaHome() {
  const plan = usePlanResult();
  const it = plan?.itinerary ?? GOA_ITINERARY;
  const mine = !!plan;
  const stops = it.days.flatMap((d) => d.stops ?? []);

  return (
    <AppShell>
      <div className="k-head">
        <h1 className="page-title">Katha</h1>
        <p className="page-sub">The history and legends of a city, a place or a planned day, in 2, 5 or 10 minutes. Every legend is labelled as one, and every history line names its source.</p>
      </div>

      <section aria-labelledby="trip-h">
        <div className="sec-title">
          <h2 className="h2" id="trip-h">{mine ? "For your trip" : "For the Goa sample trip"}</h2>
          <Link href="/katha/day/" style={{ fontWeight: 700 }}>Stories for each day</Link>
        </div>
        <div className="kh-grid">
          {it.request.destinations.map((c) => (
            <Link key={c} className="kh-card" href={href("city", c)}><b>{c}</b><span>City Katha</span></Link>
          ))}
          {stops.map((p) => (
            <Link key={p.id} className="kh-card" href={href("place", p.name)}><b>{p.name}</b><span>Place Katha · {p.category}</span></Link>
          ))}
        </div>
      </section>

      <section aria-labelledby="lib-h">
        <div className="sec-title"><h2 className="h2" id="lib-h">Library</h2></div>
        <div className="kh-grid">
          {LIBRARY.map((x) => (
            <Link key={x.subject} className="kh-card" href={href(x.kind, x.subject)}><b>{x.subject}</b><span>{x.note}</span></Link>
          ))}
        </div>
      </section>
    </AppShell>
  );
}
