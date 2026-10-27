"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { AppShell } from "@/components/AppShell";
import { KathaView } from "@/components/KathaView";
import { useI18n } from "@/lib/i18n";
import "@/app/guide.css";

/** A place or city Katha page; the subject comes from ?subject=. */
export function KathaSubject({ kind, fallback }: { kind: "place" | "city"; fallback: string }) {
  const { t } = useI18n();
  const subject = useSearchParams().get("subject")?.trim() || fallback;
  return (
    <AppShell>
      <div>
        <nav className="crumbs" aria-label={t("Breadcrumb")} style={{ marginBottom: 12, fontSize: 14 }}>
          <Link href="/katha/">{t("Katha")}</Link> · <span>{kind === "city" ? t("City") : t("Place")}</span>
        </nav>
        <div className="k-head">
          <h1 className="page-title">{subject}</h1>
          <p className="page-sub">{kind === "city" ? t("The city's story, from its founding to today.") : t("The story of this place, history first, legends labelled.")}</p>
        </div>
        <KathaView key={`${kind}:${subject}`} req={{ subject_kind: kind, subject }} />
        <p style={{ marginTop: 24 }}>
          <Link className="btn btn-quiet btn-sm" href="/ask/">{t("Ask the guide about {place}", { place: subject })}</Link>
        </p>
      </div>
    </AppShell>
  );
}
