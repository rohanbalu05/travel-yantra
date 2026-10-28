"use client";

import type { ReviseRequest, Stay } from "@/lib/contracts";
import { useI18n } from "@/lib/i18n";

/** Stars, guest rating and review count (TY1's Stay fields), each only when known. */
export function StayFacts({ stay }: { stay: Stay }) {
  const { t } = useI18n();
  const stars = stay.stars ? Math.max(1, Math.min(5, Math.round(stay.stars))) : 0;
  if (!stars && stay.rating == null && !stay.sample) return null;
  return (
    <span className="stay-facts">
      {!!stars && <span className="stars" aria-label={t("{n}-star", { n: stars })}>{"★".repeat(stars)}</span>}
      {stay.rating != null && (
        <span>
          {t("{rating} of 5", { rating: stay.rating.toFixed(1) })}
          {stay.reviews ? ` · ${t("{n} reviews", { n: stay.reviews.toLocaleString("en-IN") })}` : ""}
        </span>
      )}
      {stay.sample && <span className="badge">{t("Sample")}</span>}
    </span>
  );
}

type Revise = (req: Omit<ReviseRequest, "lang">, done: string) => Promise<boolean>;

/** "Choose another stay": TY1's change_stay re-prices the plan and its budget. */
export function StayPick({ stay, busy, revise }: { stay: Stay; busy: boolean; revise: Revise }) {
  const { t } = useI18n();
  const pick = (stay_pick: "cheaper" | "better_rated") =>
    void revise({ intent: "change_stay", stay_pick, city: stay.city }, t(stay_pick === "cheaper" ? "Done: a cheaper stay in {city}." : "Done: a better-rated stay in {city}.", { city: stay.city }));
  return (
    <div className="stay-pick">
      <button type="button" className="btn btn-quiet btn-sm" disabled={busy} onClick={() => pick("cheaper")}>{t("Choose a cheaper stay")}</button>
      <button type="button" className="btn btn-quiet btn-sm" disabled={busy} onClick={() => pick("better_rated")}>{t("Choose a better-rated stay")}</button>
    </div>
  );
}
