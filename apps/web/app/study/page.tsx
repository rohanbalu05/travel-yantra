"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { Suspense } from "react";
import { AppShell } from "@/components/AppShell";
import { useI18n } from "@/lib/i18n";
import { startStudy, type Study } from "@/lib/metrics";
import "../settings/settings.css";

// The study's one-screen consent (V3-AA): measuring this session only, nothing personal.
// Organisers open /study/?task=plan_mysuru&arm=ty for each participant.
function StudyConsent() {
  const router = useRouter();
  const params = useSearchParams();
  const { t } = useI18n();
  const task = (params.get("task") ?? "plan_trip").replace(/[^a-z0-9_-]/gi, "").slice(0, 40) || "plan_trip";
  const arm: Study["arm"] = params.get("arm") === "baseline" ? "baseline" : "ty";

  const agree = () => {
    startStudy({ task, arm });
    router.push("/home/");
  };

  return (
    <AppShell>
      <section className="panel panel-pad st-sec study" aria-labelledby="study-h">
        <h1 className="page-title" id="study-h">{t("Before you start")}</h1>
        <p className="page-sub" style={{ margin: 0 }}>{t("You are taking part in a short study of Travel Yantra. Plan a trip as you normally would.")}</p>
        <div className="study-cols">
          <div>
            <b>{t("What we measure")}</b>
            <ul>
              <li>{t("When you start planning, when you see a plan, and when you choose a booking.")}</li>
              <li>{t("A random id for this session only, so the times can be put together.")}</li>
            </ul>
          </div>
          <div>
            <b>{t("What we do not collect")}</b>
            <ul>
              <li>{t("Your name, email, phone number or location.")}</li>
              <li>{t("What you type or the trip you plan.")}</li>
            </ul>
          </div>
        </div>
        <p className="hint" style={{ margin: 0 }}>{t("This stops when you close this tab. You can stop at any time.")}</p>
        <div className="row-wrap">
          <button type="button" className="btn btn-primary btn-lg" onClick={agree}>{t("I agree, start")}</button>
          <button type="button" className="btn btn-quiet" onClick={() => router.push("/home/")}>{t("No, just use the app")}</button>
        </div>
      </section>
    </AppShell>
  );
}

export default function Page() {
  return (
    <Suspense>
      <StudyConsent />
    </Suspense>
  );
}
