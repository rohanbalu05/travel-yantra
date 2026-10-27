"use client";

import { useState } from "react";
import { rate } from "@/lib/account";
import { useI18n } from "@/lib/i18n";

const WORDS = ["Not useful", "Weak", "Okay", "Good", "Great"];

/** 1 to 5, with an optional note; anonymous (no name or contact), for the O1 study. */
export function Rating({ planId }: { planId: string | null }) {
  const { lang, t } = useI18n();
  const [score, setScore] = useState(0);
  const [comment, setComment] = useState("");
  const [state, setState] = useState<"idle" | "sending" | "sent" | "failed">("idle");

  const send = async () => {
    if (!score) return;
    setState("sending");
    try {
      await rate({ plan_id: planId, score, comment: comment.trim() || null, lang });
      setState("sent");
    } catch {
      setState("failed");
    }
  };

  if (state === "sent") return <section className="panel panel-pad rating" role="status"><b>{t("Thank you")}</b><span className="hint">{t("Your rating helps us make plans better.")}</span></section>;

  return (
    <section className="panel panel-pad rating" aria-labelledby="rate-h">
      <h2 className="h3" id="rate-h">{t("Rate this plan")}</h2>
      <div className="stars" role="radiogroup" aria-label={t("Rating, 1 to 5")}>
        {WORDS.map((w, i) => (
          <button key={w} type="button" role="radio" aria-checked={score === i + 1} aria-label={`${i + 1}: ${t(w)}`} className={i < score ? "star on" : "star"} onClick={() => setScore(i + 1)}>
            <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3l2.6 5.6 6 .7-4.5 4.1 1.2 6L12 16.4 6.7 19.4l1.2-6L3.4 9.3l6-.7Z" /></svg>
          </button>
        ))}
        {score > 0 && <span className="hint">{t(WORDS[score - 1])}</span>}
      </div>
      {score > 0 && (
        <>
          <label className="sr" htmlFor="rate-c">{t("Anything to add")}</label>
          <textarea id="rate-c" className="input" maxLength={500} placeholder={t("Anything to add? (optional, no personal details)")} value={comment} onChange={(e) => setComment(e.target.value)} />
          <button type="button" className="btn btn-primary btn-sm" disabled={state === "sending"} onClick={() => void send()}>{t("Send")}</button>
          {state === "failed" && <p className="hint" role="alert" style={{ margin: 0 }}>{t("Something went wrong. Try again.")}</p>}
        </>
      )}
    </section>
  );
}
