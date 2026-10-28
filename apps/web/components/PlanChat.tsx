"use client";

import { useRouter } from "next/navigation";
import ChatPanel, { type PlanChanged } from "@/components/chat/ChatPanel";
import { useI18n } from "@/lib/i18n";
import { clearChoice, savePlanResult } from "@/lib/plan";

/**
 * TY5's chat, boxed for a page. A chat edit replaces the stored plan, so every page reading
 * usePlanResult (the Itinerary here) redraws in place. `openOnNew`: a new plan from the chat
 * (Plan start, no plan yet) opens the Itinerary.
 */
export function PlanChat({ planId, shareToken, openOnNew = false }: { planId: string | null; shareToken?: string | null; openOnNew?: boolean }) {
  const { lang, t } = useI18n();
  const router = useRouter();
  const changed = (e: PlanChanged) => {
    savePlanResult({ itinerary: e.itinerary, plan_id: e.plan_id, share_token: e.share_token ?? shareToken ?? null });
    clearChoice();
    if (openOnNew && e.plan_id !== planId) router.push("/plan/itinerary/");
  };
  return (
    <section className="panel plan-chat" aria-labelledby="chat-h">
      <div className="panel-head">
        <h2 className="h3" id="chat-h">{planId ? t("Change it in chat") : t("Or plan it in chat")}</h2>
        <span className="hint">{planId ? t("Say what to change, for example: a lighter Saturday, or add a beach.") : t("Tell the planner about the trip, one message at a time.")}</span>
      </div>
      <ChatPanel planId={planId} shareToken={shareToken ?? null} lang={lang} onPlanChanged={changed} />
    </section>
  );
}
