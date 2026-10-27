"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { AppShell } from "@/components/AppShell";
import { Problem, problemOf } from "@/components/Problem";
import { listTrips, useAccount, type SavedTrip } from "@/lib/account";
import { dayLabel } from "@/lib/format";
import { useI18n } from "@/lib/i18n";
import { savePlanResult } from "@/lib/plan";
import "../settings/settings.css";

export default function MyTrips() {
  const account = useAccount();
  const router = useRouter();
  const { lang, t } = useI18n();
  const [res, setRes] = useState<{ trips?: SavedTrip[]; from?: "api" | "browser"; problem?: { message: string; retryable: boolean } } | null>(null);
  const [run, setRun] = useState(0);
  const keep = !!account?.consents.plan_history;
  const count = account?.trips.length ?? 0;

  useEffect(() => {
    let live = true;
    listTrips()
      .then((r) => live && setRes(r))
      .catch((e) => live && setRes({ problem: problemOf(e) }));
    return () => {
      live = false;
    };
  }, [run, count]);

  // A plan kept in this browser reopens in full; one from the server opens as its share page.
  const open = (trip: SavedTrip) => {
    if (trip.itinerary) {
      savePlanResult({ itinerary: trip.itinerary, plan_id: trip.plan_id, share_token: trip.share_token || null });
      router.push("/plan/itinerary/");
    } else if (trip.share_token) {
      router.push(`/t/${encodeURIComponent(trip.share_token)}/`);
    }
  };

  return (
    <AppShell>
      <div className="st-head">
        <h1 className="page-title">{t("My trips")}</h1>
        <p className="page-sub">
          {!keep
            ? t("Saving trips is off. Turn on Keep my trips in Settings and the next plan you make will be saved here.")
            : res?.from === "browser"
              ? t("Plans you made in this browser, newest first.")
              : t("Plans you made, newest first.")}
        </p>
      </div>
      {!keep && <p><Link className="btn btn-quiet btn-sm" href="/settings/">{t("Open Settings")}</Link></p>}
      {!res ? (
        <p className="hint" role="status">{t("Loading")}…</p>
      ) : res.problem ? (
        <Problem {...res.problem} onRetry={() => { setRes(null); setRun((r) => r + 1); }} />
      ) : res.trips!.length === 0 ? (
        <div className="panel panel-pad" style={{ display: "flex", flexDirection: "column", gap: 12, alignItems: "flex-start" }}>
          <b>{t("No saved trips yet.")}</b>
          <Link className="btn btn-primary" href="/plan/start/">{t("Plan a trip")}</Link>
        </div>
      ) : (
        <div className="trips-list">
          {res.trips!.map((trip) => (
            <article className="trip-card" key={trip.plan_id}>
              <b>{trip.destinations.join(", ")}</b>
              <span className="hint">{t("From {origin} · {start} to {end}", { origin: trip.origin, start: dayLabel(trip.start_date, lang), end: dayLabel(trip.end_date, lang) })}</span>
              <div className="row-wrap">
                <button type="button" className="btn btn-primary btn-sm" onClick={() => open(trip)} disabled={!trip.itinerary && !trip.share_token}>{t("View details")}</button>
                {trip.share_token && <Link className="btn btn-quiet btn-sm" href={`/t/${encodeURIComponent(trip.share_token)}/`}>{t("Share")}</Link>}
              </div>
            </article>
          ))}
        </div>
      )}
    </AppShell>
  );
}
