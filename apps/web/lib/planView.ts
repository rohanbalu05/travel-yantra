import type { DayPlan, Itinerary, Leg, Place, TransportOption } from "@/lib/contracts";
import { daysBetween } from "@/lib/format";

export type DayRow = { kind: "stop"; n: number; place: Place } | { kind: "move"; leg: Leg } | { kind: "stay"; name: string };

/**
 * Stops in order, each followed by the leg that leaves it; the night's stay last.
 * A leg that leaves no stop (multi-city: TY1 puts the city-to-city leg first) opens the day.
 */
export function dayRows(day: DayPlan, it: Itinerary): DayRow[] {
  const rows: DayRow[] = [];
  const names = new Set((day.stops ?? []).map((s) => s.name));
  const legs = [...(day.legs ?? [])];
  while (legs.length && !names.has(legs[0].from)) rows.push({ kind: "move", leg: legs.shift()! });
  (day.stops ?? []).forEach((place, i) => {
    rows.push({ kind: "stop", n: i + 1, place });
    const j = legs.findIndex((l) => l.from === place.name);
    if (j >= 0) rows.push({ kind: "move", leg: legs.splice(j, 1)[0] });
  });
  legs.forEach((leg) => rows.push({ kind: "move", leg }));
  const stay = (it.stays ?? []).find((s) => s.check_in <= day.date && day.date < s.check_out);
  if (stay) rows.push({ kind: "stay", name: stay.name });
  return rows;
}

/** Whole-trip cost if this way of travel is picked: the plan's other costs plus this option. */
export function tripCost(it: Itinerary, opt: TransportOption): number {
  const b = it.budget;
  return b.total_inr - b.transport_inr + opt.total_cost_inr;
}

/** "₹2,600 to spare" / "Over by ₹26,700" against the budget, or null with no budget. */
export function againstBudget(it: Itinerary, cost: number): { ok: boolean; diff: number } | null {
  const budget = it.request.constraints?.budget_inr;
  if (!budget) return null;
  return { ok: cost <= budget, diff: Math.abs(budget - cost) };
}

export const travellerCount = (it: Itinerary) => it.request.constraints?.travellers?.length ?? 0;

export const nights = (it: Itinerary) => Math.max(0, daysBetween(it.request.start_date, it.request.end_date));

/** The plan's own choice comes first in `transport`; fall back to the cheapest that fits. */
export function pickIndex(it: Itinerary): number {
  const opts = it.transport ?? [];
  if (opts.length < 2) return 0;
  const fits = opts.map((o, i) => ({ i, cost: tripCost(it, o), ok: againstBudget(it, tripCost(it, o))?.ok ?? true }));
  const ok = fits.filter((f) => f.ok);
  return (ok.length ? ok : fits).sort((a, b) => a.cost - b.cost)[0].i;
}
