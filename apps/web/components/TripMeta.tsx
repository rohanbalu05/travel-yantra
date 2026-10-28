"use client";

import type { SavedTrip } from "@/lib/account";
import { MODE_NAME, locale } from "@/lib/format";
import { useI18n } from "@/lib/i18n";
import { tripFacts } from "@/lib/trips";

/** Mode, travellers and when it was made: one line under each trip card. */
export function TripMeta({ trip }: { trip: SavedTrip }) {
  const { lang, t } = useI18n();
  const { mode, travellers } = tripFacts(trip);
  const made = new Date(trip.created_at);
  const parts = [
    mode ? t(MODE_NAME[mode]) : null,
    travellers ? t(travellers === 1 ? "{n} traveller" : "{n} travellers", { n: travellers }) : null,
    Number.isNaN(made.getTime()) ? null : t("Made {when}", { when: made.toLocaleString(locale(lang), { day: "numeric", month: "short", hour: "numeric", minute: "2-digit" }) }),
  ].filter(Boolean);
  return parts.length ? <span className="hint">{parts.join(" · ")}</span> : null;
}
