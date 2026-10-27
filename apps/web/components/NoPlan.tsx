"use client";

import Link from "next/link";
import { useI18n } from "@/lib/i18n";

/** Shown when a plan screen opens with no finished plan in this tab. */
export function NoPlan() {
  const { t } = useI18n();
  return (
    <section className="panel panel-pad" style={{ display: "flex", flexDirection: "column", gap: 12, alignItems: "flex-start" }}>
      <h1 className="h2" style={{ margin: 0 }}>{t("No plan yet")}</h1>
      <p className="page-sub" style={{ margin: 0 }}>{t("Plans live in this browser tab until you save them. Start one and it will show up here.")}</p>
      <Link className="btn btn-primary" href="/plan/start/">{t("Plan a trip")}</Link>
    </section>
  );
}
