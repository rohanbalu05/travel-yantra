import type { DayPlan, Itinerary, Leg, Mode, Place, StopTime, TransportOption } from "@/lib/contracts";
import { clock, daysBetween } from "@/lib/format";

export type DayRow = { kind: "stop"; n: number; place: Place; at?: StopTime } | { kind: "move"; leg: Leg } | { kind: "stay"; name: string };

/** A journey between cities (TY1's Leg.role), as opposed to a hop between two stops. */
export const isJourney = (leg: Leg) => leg.role === "outbound" || leg.role === "between" || leg.role === "home";

/**
 * Stops in order, each followed by the leg that leaves it; the night's stay last.
 * The journey there (role outbound or between) and its transfer open the day; the journey home closes it.
 * Plans from before Leg.role: a leg that leaves no stop opens the day.
 */
export function dayRows(day: DayPlan, it: Itinerary): DayRow[] {
  const rows: DayRow[] = [];
  const names = new Set((day.stops ?? []).map((s) => s.name));
  const legs = [...(day.legs ?? [])];
  const home = legs.filter((l) => l.role === "home");
  const rest = legs.filter((l) => l.role !== "home");
  // The journey in, then TY1's transfer from the station or centre to the first stop (QA #118).
  while (rest.length && (rest[0].role === "outbound" || rest[0].role === "between" || rest[0].role === "transfer" || (rest[0].role == null && !names.has(rest[0].from)))) {
    rows.push({ kind: "move", leg: rest.shift()! });
  }
  (day.stops ?? []).forEach((place, i) => {
    rows.push({ kind: "stop", n: i + 1, place, at: (day.schedule ?? []).find((x) => x.place_id === place.id) });
    const j = rest.findIndex((l) => l.from === place.name);
    if (j >= 0) rows.push({ kind: "move", leg: rest.splice(j, 1)[0] });
  });
  [...rest, ...home].forEach((leg) => rows.push({ kind: "move", leg }));
  const stay = (it.stays ?? []).find((s) => s.check_in <= day.date && day.date < s.check_out);
  if (stay) rows.push({ kind: "stay", name: stay.name });
  return rows;
}

/**
 * Whole-trip cost if this way of travel is picked. The option in use is the plan's own total
 * (TY1's budget counts every journey, home and between cities too); another is an estimate:
 * the plan's other costs plus that option.
 */
export function tripCost(it: Itinerary, opt: TransportOption): number {
  if (planMode(it) && opt === (it.transport ?? [])[pickIndex(it)]) return it.budget.total_inr;
  return estimate(it, opt);
}

/** The plan's other costs plus this option. pickIndex uses it directly: tripCost calls pickIndex. */
const estimate = (it: Itinerary, opt: TransportOption) => it.budget.total_inr - it.budget.transport_inr + opt.total_cost_inr;

/** "₹2,600 to spare" / "Over by ₹26,700" against the budget, or null with no budget. */
export function againstBudget(it: Itinerary, cost: number): { ok: boolean; diff: number } | null {
  const budget = it.request.constraints?.budget_inr;
  if (!budget) return null;
  return { ok: cost <= budget, diff: Math.abs(budget - cost) };
}

export const travellerCount = (it: Itinerary) => it.request.constraints?.travellers?.length ?? 0;

export const nights = (it: Itinerary) => Math.max(0, daysBetween(it.request.start_date, it.request.end_date));

/**
 * The mode the days were built with: the traveller's choice (TripRequest.transport_mode),
 * else the mode of the first journey out, else null (no journeys in the plan).
 */
export function planMode(it: Itinerary): Mode | null {
  if (it.request.transport_mode) return it.request.transport_mode;
  for (const d of it.days) for (const l of d.legs ?? []) if (l.role === "outbound") return l.mode;
  return null;
}

/** The option the days follow: the first of the plan's mode; else the cheapest that fits the budget. */
export function pickIndex(it: Itinerary): number {
  const opts = it.transport ?? [];
  const m = planMode(it);
  const own = m ? opts.findIndex((o) => o.mode === m) : -1;
  if (own >= 0) return own;
  if (opts.length < 2) return 0;
  const fits = opts.map((o, i) => ({ i, cost: estimate(it, o), ok: againstBudget(it, estimate(it, o))?.ok ?? true }));
  const ok = fits.filter((f) => f.ok);
  return (ok.length ? ok : fits).sort((a, b) => a.cost - b.cost)[0].i;
}

/**
 * The train the plan takes: the first rail journey in the days, else the first
 * rail leg of the option the days follow, else any rail leg.
 */
export function planRailLeg(it: Itinerary): Leg | undefined {
  const inDays = it.days.flatMap((d) => d.legs ?? []).find((l) => l.mode === "rail" && isJourney(l));
  if (inDays) return inDays;
  const opts = it.transport ?? [];
  return opts[pickIndex(it)]?.legs.find((l) => l.mode === "rail") ?? opts.flatMap((o) => o.legs).find((l) => l.mode === "rail");
}

/** The train itself in the option the days follow (the day's journey leg also counts the ride to the station). */
export const trainLeg = (it: Itinerary) => (it.transport ?? [])[pickIndex(it)]?.legs.find((l) => l.mode === "rail");

/**
 * The IRCTC card names another train than the plan: by number when the leg has one (Leg.ref),
 * else by the train's own departure, not the journey leg's (which starts with the cab to the station).
 */
export function trainDiffers(rail: Leg, card: { departs: string; train: { number: string } }, it: Itinerary): boolean {
  if (rail.ref) return card.train.number !== rail.ref;
  return card.departs !== clock((trainLeg(it) ?? rail).depart);
}
