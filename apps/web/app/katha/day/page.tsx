"use client";

import Link from "next/link";
import { useState } from "react";
import { AppShell } from "@/components/AppShell";
import { KathaView } from "@/components/KathaView";
import { dayLabel } from "@/lib/format";
import { GOA_ITINERARY } from "@/lib/mockPlan";
import { usePlanResult } from "@/lib/plan";
import "../../guide.css";

export default function KathaDay() {
  const plan = usePlanResult();
  const it = plan?.itinerary ?? GOA_ITINERARY;
  const days = it.days.filter((d) => (d.stops ?? []).length);
  const [sel, setSel] = useState(0);
  const day = days[Math.min(sel, days.length - 1)];
  const city = it.request.destinations[0] ?? "";
  const n = day ? it.days.indexOf(day) + 1 : 0;

  return (
    <AppShell>
      <div>
        <nav className="crumbs" aria-label="Breadcrumb" style={{ marginBottom: 12, fontSize: 14 }}>
          <Link href="/katha/">Katha</Link> · <span>Day</span>
        </nav>
        <div className="k-head">
          <h1 className="page-title">{day ? `${dayLabel(day.date)} in ${city}` : "No days to tell yet"}</h1>
          <p className="page-sub">One story that walks with you from stop to stop, in the order of {plan ? "your" : "the sample"} plan.</p>
        </div>
        {day && (
          <div className="split">
            <div className="main">
              <KathaView key={day.date} req={{ subject_kind: "day", subject: `Day ${n}, ${city}`, places: (day.stops ?? []).map((s) => s.name), lang: "en" }} />
            </div>
            <aside className="side panel panel-pad" aria-labelledby="days-h">
              <h2 className="h3" id="days-h" style={{ marginBottom: 12 }}>Days</h2>
              <div className="k-stops" role="tablist" aria-label="Days">
                {days.map((d, i) => (
                  <button key={d.date} type="button" role="tab" aria-selected={d === day} className={d === day ? "on" : undefined} onClick={() => setSel(i)}>
                    <span className="n">{it.days.indexOf(d) + 1}</span>
                    <span>{dayLabel(d.date)}: {(d.stops ?? []).map((s) => s.name).join(", ")}</span>
                  </button>
                ))}
              </div>
            </aside>
          </div>
        )}
      </div>
    </AppShell>
  );
}
