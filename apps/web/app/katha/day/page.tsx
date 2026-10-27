"use client";

import Link from "next/link";
import { useState } from "react";
import { AppShell } from "@/components/AppShell";
import { KathaView } from "@/components/KathaView";
import { dayLabel } from "@/lib/format";
import { useI18n } from "@/lib/i18n";
import { GOA_ITINERARY } from "@/lib/mockPlan";
import { usePlanResult } from "@/lib/plan";
import "../../guide.css";

export default function KathaDay() {
  const plan = usePlanResult();
  const { lang, t } = useI18n();
  const it = plan?.itinerary ?? GOA_ITINERARY;
  const days = it.days.filter((d) => (d.stops ?? []).length);
  const [sel, setSel] = useState(0);
  const day = days[Math.min(sel, days.length - 1)];
  const city = it.request.destinations[0] ?? "";
  const n = day ? it.days.indexOf(day) + 1 : 0;

  return (
    <AppShell>
      <div>
        <nav className="crumbs" aria-label={t("Breadcrumb")} style={{ marginBottom: 12, fontSize: 14 }}>
          <Link href="/katha/">{t("Katha")}</Link> · <span>{t("Day")}</span>
        </nav>
        <div className="k-head">
          <h1 className="page-title">{day ? t("{day} in {city}", { day: dayLabel(day.date, lang), city }) : t("No days to tell yet")}</h1>
          <p className="page-sub">{plan ? t("One story that walks with you from stop to stop, in the order of your plan.") : t("One story that walks with you from stop to stop, in the order of the sample plan.")}</p>
        </div>
        {day && (
          <div className="split">
            <div className="main">
              <KathaView key={day.date} req={{ subject_kind: "day", subject: `Day ${n}, ${city}`, places: (day.stops ?? []).map((s) => s.name) }} />
            </div>
            <aside className="side panel panel-pad" aria-labelledby="days-h">
              <h2 className="h3" id="days-h" style={{ marginBottom: 12 }}>{t("Days")}</h2>
              <div className="k-stops" role="tablist" aria-label={t("Days")}>
                {days.map((d, i) => (
                  <button key={d.date} type="button" role="tab" aria-selected={d === day} className={d === day ? "on" : undefined} onClick={() => setSel(i)}>
                    <span className="n">{it.days.indexOf(d) + 1}</span>
                    <span>{dayLabel(d.date, lang)}: {(d.stops ?? []).map((s) => s.name).join(", ")}</span>
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
