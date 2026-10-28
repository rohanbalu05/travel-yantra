import type { DayPlan, Itinerary, Leg, Mode, Place, Stay, StopTime, TransportOption } from "@/lib/contracts";
import { MODE_NAME, clock, daysBetween } from "@/lib/format";

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
 * Whole-trip cost if this way of travel is picked, always TY1's number: the option in use is the
 * plan's budget.total_inr; another is its trip_total_inr (the total after a transport revise to it).
 * Null when TY1 sent none: the web never estimates.
 */
export function tripCost(it: Itinerary, opt: TransportOption): number | null {
  if (opt === (it.transport ?? [])[pickIndex(it)]) return it.budget.total_inr;
  return opt.trip_total_inr ?? null;
}

/** The one budget of the plan: TY1's total. */
export const planTotal = (it: Itinerary) => it.budget.total_inr;

/** "₹2,600 to spare" / "Over by ₹26,700" against the budget, or null with no budget. */
export function againstBudget(it: Itinerary, cost: number | null): { ok: boolean; diff: number } | null {
  const budget = it.request.constraints?.budget_inr;
  if (!budget || cost == null) return null;
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
  // No mode in the plan: rank by TY1's whole-trip totals, else the fares alone.
  const fits = opts.map((o, i) => {
    const cost = o.trip_total_inr ?? o.total_cost_inr;
    return { i, cost, ok: againstBudget(it, o.trip_total_inr ?? null)?.ok ?? true };
  });
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

/** The train of the plan's rail option (TY3's card follows it even when the plan goes by road or air). */
export const railOptionLeg = (it: Itinerary): Leg | undefined =>
  (it.transport ?? []).find((o) => o.mode === "rail")?.legs.find((l) => l.mode === "rail");

/** A word for a leg's mode: road legs to and from a station or airport are a cab (TY3's labels). */
export function legModeName(l: Leg): string {
  if (l.mode !== "road") return MODE_NAME[l.mode];
  return l.role === "transfer" || /station|\bjn\b|junction|airport|terminal/i.test(`${l.from} ${l.to}`) ? "Cab" : MODE_NAME[l.mode];
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

/**
 * Stays grouped by stop (TY1: every ranked stay for a city, sharing a check_in; the first is the
 * one the plan and budget use). In the order you reach them.
 */
export function stayGroups(it: Itinerary): { chosen: Stay; others: Stay[] }[] {
  const groups = new Map<string, Stay[]>();
  for (const s of it.stays ?? []) {
    const k = `${s.check_in}|${s.city}`;
    groups.set(k, [...(groups.get(k) ?? []), s]);
  }
  return [...groups.values()]
    .map(([chosen, ...others]) => ({ chosen, others }))
    .sort((a, b) => a.chosen.check_in.localeCompare(b.chosen.check_in));
}

/** The stays the plan uses, one per stop. */
export const chosenStays = (it: Itinerary): Stay[] => stayGroups(it).map((g) => g.chosen);
