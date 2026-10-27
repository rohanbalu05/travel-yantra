import type { Itinerary, PlanEvent, TripRequest } from "@/lib/contracts";
import goa from "@/lib/samples/goa_family.json";

/** The Goa family sample (Arjun Rao and family), from packages/contracts/samples. */
export const GOA_REQUEST = goa.request as TripRequest;
export const GOA_ITINERARY = goa.itinerary as Itinerary;

/** The events TY1's /plan sends for the Goa sample, in the agreed order. */
export function goaEvents(): PlanEvent[] {
  const it = GOA_ITINERARY;
  return [
    { stage: "intake", step: null, message: "Reading your trip…" },
    { stage: "intake", step: "intake", message: "Bengaluru to Goa, 11 to 14 Dec, 4 travellers." },
    { stage: "planning", step: "transport", message: "Rail overnight to Madgaon, or a 75-minute flight." },
    { stage: "planning", step: "places", message: "5 places in Old Goa, Panaji and Ponda." },
    { stage: "planning", step: "stays", message: "One base in Panaji for all three nights." },
    { stage: "planning", step: "story", message: "A story for every stop, legends labelled." },
    { stage: "solving", step: "solver", message: "Days laid out by area, nearest first.", partial: it },
    {
      stage: "checking",
      step: "checker",
      iteration: 1,
      message: "1 problem found.",
      violations: [{ code: "long_day", message: "Saturday runs past 7 pm for the seniors.", day: "2026-12-12", place_id: null }],
      partial: it,
    },
    { stage: "repairing", step: "repair", iteration: 1, message: "Moved the sunset stop earlier.", partial: it },
    { stage: "checking", step: "checker", iteration: 2, message: "All checks passed.", violations: [], partial: it },
    { stage: "narrating", step: "narrator", message: "Writing your day-by-day plan.", partial: it },
    { stage: "done", step: null, message: "Your plan is ready.", partial: it, plan_id: "sample-goa-family" },
  ];
}

/** A fake `/plan` response body: the Goa events as SSE frames, with pings, one every `delayMs`. */
export function mockPlanBody(delayMs = 450): ReadableStream<Uint8Array> {
  const enc = new TextEncoder();
  const events = goaEvents();
  return new ReadableStream({
    async start(ctl) {
      for (const ev of events) {
        if (delayMs) await new Promise((r) => setTimeout(r, delayMs));
        ctl.enqueue(enc.encode(": ping\n\n"));
        ctl.enqueue(enc.encode(`data: ${JSON.stringify(ev)}\n\n`));
      }
      ctl.close();
    },
  });
}
