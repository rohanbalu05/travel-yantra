"use client";

import { Suspense, useState } from "react";
import { StudyFrame, useStudyParams, useTaskBrief } from "@/components/Study";
import { useI18n } from "@/lib/i18n";
import { currentStudy, track } from "@/lib/metrics";
import "../../settings/settings.css";

type Step = "ready" | "planning" | "planned" | "done";

// Baseline arm: the participant plans in other tabs with other sites; these buttons send the same
// three events as the app (no `at`: the server's clock times both arms).
function BaselineTimer() {
  const { t } = useI18n();
  const { task } = useStudyParams();
  const brief = useTaskBrief(task);
  const [step, setStep] = useState<Step>("ready");
  const consented = currentStudy() !== null;

  // Only after the consent screen started a study session; track() itself sends nothing otherwise.
  const press = (event: "start" | "plan_shown" | "booking_chosen", next: Step) => {
    track(event, task);
    setStep(next);
  };

  return (
    <StudyFrame arm="baseline">
      <section className="panel panel-pad st-sec study" aria-labelledby="base-h">
        <h1 className="page-title" id="base-h">{brief?.title ?? t("Your task")}</h1>
        {brief && <p className="page-sub" style={{ margin: 0 }}>{brief.brief}</p>}
        {!consented && <p className="hint" style={{ margin: 0 }}>{t("Open the study link first so we can ask for your consent.")}</p>}
        <ol className="base-steps">
          <li className={step === "ready" ? "on" : "done"}>
            <span>{t("When you are ready, press Start, then plan in another tab with any sites you like.")}</span>
            <button type="button" className="btn btn-primary" disabled={step !== "ready" || !consented} onClick={() => press("start", "planning")}>{t("Start")}</button>
          </li>
          <li className={step === "planning" ? "on" : step === "ready" ? "" : "done"}>
            <span>{t("Press this when you have a plan: how you will travel and where you will stay.")}</span>
            <button type="button" className="btn btn-primary" disabled={step !== "planning"} onClick={() => press("plan_shown", "planned")}>{t("I have my plan")}</button>
          </li>
          <li className={step === "planned" ? "on" : step === "done" ? "done" : ""}>
            <span>{t("Press this when you have chosen where you would book.")}</span>
            <button type="button" className="btn btn-primary" disabled={step !== "planned"} onClick={() => press("booking_chosen", "done")}>{t("I chose where to book")}</button>
          </li>
        </ol>
        {step === "done" && <p className="st-done" role="status">{t("Thank you. You can close this tab.")}</p>}
      </section>
    </StudyFrame>
  );
}

export default function Page() {
  return (
    <Suspense>
      <BaselineTimer />
    </Suspense>
  );
}
