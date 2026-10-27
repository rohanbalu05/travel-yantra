"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { AppShell } from "@/components/AppShell";
import { KathaView } from "@/components/KathaView";
import { useI18n } from "@/lib/i18n";
import { usePlanResult } from "@/lib/plan";
import "@/app/guide.css";

/** A place or city Katha page; the subject comes from ?subject=. */
export function KathaSubject({ kind, fallback }: { kind: "place" | "city"; fallback: string }) {
  const { lang, t } = useI18n();
  const subject = useSearchParams().get("subject")?.trim() || fallback;
  // The place's own name in the reading language when the plan has it (QA #115); English kept below it.
  const plan = usePlanResult();
  const place = plan?.itinerary.days.flatMap((d) => d.stops ?? []).find((p) => p.name.toLowerCase() === subject.toLowerCase());
  const native = lang !== "en" ? place?.native_names?.[lang] : undefined;
  return (
    <AppShell>
      <div>
        <nav className="crumbs" aria-label={t("Breadcrumb")} style={{ marginBottom: 12, fontSize: 14 }}>
          <Link href="/katha/">{t("Katha")}</Link> · <span>{kind === "city" ? t("City") : t("Place")}</span>
        </nav>
        <div className="k-head">
          <h1 className="page-title" lang={native ? lang : "en"}>{native ?? subject}</h1>
          {native && <p className="hint" lang="en" style={{ margin: 0 }}>{subject}</p>}
          <p className="page-sub">{kind === "city" ? t("The city's story, from its founding to today.") : t("The story of this place, history first, legends labelled.")}</p>
        </div>
        <KathaView key={`${kind}:${subject}`} req={{ subject_kind: kind, subject }} />
        <p style={{ marginTop: 24 }}>
          <Link className="btn btn-quiet btn-sm" href="/ask/">{t("Ask the guide about {place}", { place: native ?? subject })}</Link>
        </p>
      </div>
    </AppShell>
  );
}
