import type { Itinerary, Mode, PlanEvent, ReviseRequest, TripRequest } from "@/lib/contracts";
import goa from "@/lib/samples/goa_family.json";

/** The Goa family sample (Arjun Rao and family), from packages/contracts/samples. */
export const GOA_REQUEST = goa.request as TripRequest;
export const GOA_ITINERARY = goa.itinerary as Itinerary;
/** The mock plan's share token; /t/{token} opens it without an API. */
export const SAMPLE_SHARE_TOKEN = "sample-goa-family";

/** The events TY1's /plan sends for the Goa sample, in the agreed order. */
export function goaEvents(mode: Mode | null = null): PlanEvent[] {
  // A mode chosen on the form: the sample as TY1 would build it in that mode.
  const it = mode ? revisedItinerary(GOA_ITINERARY, { intent: "transport", mode }) : GOA_ITINERARY;
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
    { stage: "done", step: null, message: "Your plan is ready.", partial: it, plan_id: "sample-goa-family", share_token: SAMPLE_SHARE_TOKEN },
  ];
}

/** The mock's version of a revise: drop the named stop, or the day's last stop for a lighter day. */
export function revisedItinerary(it: Itinerary, req: ReviseRequest): Itinerary {
  if (req.intent === "rain" || req.intent === "booked" || req.intent === "change_stay" || req.intent === "budget_style") return it;
  if (req.intent === "transport" && req.mode) {
    // Like TY1's change_transport: the chosen mode's options first, every journey in that mode.
    const m = req.mode;
    const opts = it.transport ?? [];
    const journey = (r: string | null | undefined) => r === "outbound" || r === "between" || r === "home";
    return {
      ...it,
      request: { ...it.request, transport_mode: m },
      transport: [...opts.filter((o) => o.mode === m), ...opts.filter((o) => o.mode !== m)],
      days: it.days.map((d) => ({ ...d, legs: (d.legs ?? []).map((l) => (journey(l.role) ? { ...l, mode: m } : l)) })),
    };
  }
  const days = it.days.map((d) => {
    const stops = d.stops ?? [];
    const drop = req.intent === "swap_stop" ? stops.find((s) => s.id === req.place_id) : d.date === req.day ? stops.at(-1) : undefined;
    if (!drop) return d;
    return { ...d, stops: stops.filter((s) => s !== drop), legs: (d.legs ?? []).filter((l) => l.from !== drop.name && l.to !== drop.name) };
  });
  return { ...it, days };
}

/** TY1's solver line for a revise, as the mock can tell it. */
function reviseNote(req: ReviseRequest): string {
  if (req.intent === "transport") return `Switched every journey to ${req.mode === "rail" ? "train" : req.mode}`;
  if (req.intent === "rain") return "Planned the day for rain";
  if (req.intent === "move_day") return `Moved a day to ${req.city}`;
  if (req.intent === "booked") return `Re-timed the plan around ${req.booked?.ref || "your booking"}`;
  if (req.intent === "change_stay") return "Changed the stay and re-priced the trip";
  if (req.intent === "budget_style") return `Re-planned for ${req.style}`;
  const day = GOA_ITINERARY.days.find((d) => d.date === req.day);
  const stop = req.intent === "swap_stop" ? day?.stops?.find((s) => s.id === req.place_id) : day?.stops?.at(-1);
  return stop ? `${req.intent === "swap_stop" ? "Swapped" : "Dropped"} ${stop.name}` : "That day is already free";
}

export function mockReviseBody(req: ReviseRequest, delayMs = 300): ReadableStream<Uint8Array> {
  const it = revisedItinerary(GOA_ITINERARY, req);
  return sseBody(
    [
      { stage: "intake", message: "Revising your plan…" },
      { stage: "solving", step: "solver", message: reviseNote(req), partial: it },
      { stage: "checking", step: "checker", iteration: 1, message: "All checks passed.", violations: [], partial: it },
      { stage: "done", message: "Your plan is updated.", partial: it, plan_id: "sample-goa-family-r1", share_token: SAMPLE_SHARE_TOKEN },
    ],
    delayMs,
  );
}

/** A fake `/plan` response body: the Goa events as SSE frames, with pings, one every `delayMs`. */
export function mockPlanBody(delayMs = 450, mode: Mode | null = null): ReadableStream<Uint8Array> {
  return sseBody(goaEvents(mode), delayMs);
}

function sseBody(events: PlanEvent[], delayMs: number): ReadableStream<Uint8Array> {
  const enc = new TextEncoder();
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
