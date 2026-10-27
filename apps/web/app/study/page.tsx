"use client";

import { useRouter } from "next/navigation";
import { Suspense } from "react";
import { StudyFrame, useStudyParams, useTaskBrief } from "@/components/Study";
import { useI18n } from "@/lib/i18n";
import { startStudy } from "@/lib/metrics";
import "../settings/settings.css";

// The study's one-screen consent (V3-AA): measuring this session only, nothing personal.
function StudyConsent() {
  const router = useRouter();
  const { t } = useI18n();
  const { task, arm } = useStudyParams();
  const brief = useTaskBrief(task);

  const agree = () => {
    startStudy({ task, arm });
    // ty: plan in the app (start is sent when the plan is asked for); baseline: the timer page.
    router.push(arm === "ty" ? "/plan/start/" : `/study/baseline/?task=${encodeURIComponent(task)}&arm=baseline`);
  };

  return (
    <StudyFrame arm={arm}>
      <section className="panel panel-pad st-sec study" aria-labelledby="study-h">
        <h1 className="page-title" id="study-h">{t("Before you start")}</h1>
        <p className="page-sub" style={{ margin: 0 }}>
          {arm === "ty"
            ? t("You are taking part in a short study of Travel Yantra. Plan a trip as you normally would.")
            : t("You are taking part in a short study of trip planning. Plan this trip with any websites or apps you usually use, except Travel Yantra.")}
        </p>
        {brief && (
          <div className="study-brief">
            <b>{brief.title}</b>
            <p>{brief.brief}</p>
          </div>
        )}
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
        <p className="hint" style={{ margin: 0 }}>{t("This stops when you close this tab. To stop sooner, close this tab.")}</p>
        <div className="row-wrap">
          <button type="button" className="btn btn-primary btn-lg" onClick={agree}>{t("I agree, start")}</button>
          {arm === "ty" && <button type="button" className="btn btn-quiet" onClick={() => router.push("/home/")}>{t("No, just use the app")}</button>}
        </div>
      </section>
    </StudyFrame>
  );
}

export default function Page() {
  return (
    <Suspense>
      <StudyConsent />
    </Suspense>
  );
}
