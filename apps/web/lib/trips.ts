import { withAuth, type SavedTrip } from "@/lib/account";
import type { Itinerary, Mode, SavedPlan } from "@/lib/contracts";
import { ApiError, apiJSON } from "@/lib/http";
import type { PlanResult } from "@/lib/plan";

/** One trip, many versions (each revision is a new plan_id): the same request, so one key. */
const tripKey = (t: SavedTrip) => [t.origin, ...t.destinations, t.start_date, t.end_date].join("|").toLowerCase();

const changed = (t: SavedTrip) => t.updated_at || t.created_at;

/**
 * The latest version of each trip, most recently changed first. TY1 already sends one row per
 * trip; plans kept in this browser (and older server rows) can hold one row per revision.
 */
export function latestTrips(trips: SavedTrip[]): SavedTrip[] {
  const byKey = new Map<string, SavedTrip>();
  for (const t of trips) {
    const k = tripKey(t);
    const seen = byKey.get(k);
    if (!seen || changed(t) > changed(seen)) byKey.set(k, t);
  }
  return [...byKey.values()].sort((a, b) => changed(b).localeCompare(changed(a)));
}

/** The plan's main way of travel: the outbound leg's mode. */
export function planMode(it: Itinerary): Mode | null {
  const legs = it.days.flatMap((d) => d.legs ?? []);
  const out = legs.find((l) => l.role === "outbound") ?? legs.find((l) => l.role !== "transfer");
  return it.request.transport_mode ?? out?.mode ?? it.transport?.[0]?.mode ?? null;
}

/** Mode and number of travellers: from TY1's summary when it has them, else from the kept plan. */
export function tripFacts(t: SavedTrip): { mode: Mode | null; travellers: number | null } {
  const it = t.itinerary;
  return {
    mode: t.mode ?? (it ? planMode(it) : null),
    travellers: t.travellers ?? (it?.request.constraints?.travellers?.length || null),
  };
}

/**
 * The owner's editable plan: TY1's GET /plan/{id} (owner only) when it exists, else the
 * shared copy by its token. Revising needs only the plan_id, so either reopens the Itinerary.
 */
export async function loadTrip(t: SavedTrip): Promise<PlanResult> {
  if (t.itinerary) return { itinerary: t.itinerary, plan_id: t.plan_id, share_token: t.share_token || null };
  try {
    const r = await withAuth((headers) => apiJSON<SavedPlan>(`/plan/${encodeURIComponent(t.plan_id)}`, { headers }));
    return { itinerary: r.itinerary, plan_id: r.plan_id, share_token: r.share_token || t.share_token || null };
  } catch (e) {
    // 404/405: TY1's owner GET is not there yet; 403 should not happen for the owner's own list.
    if (!(e instanceof ApiError) || ![404, 405].includes(e.status) || !t.share_token) throw e;
  }
  const itinerary = await apiJSON<Itinerary>(`/trips/${encodeURIComponent(t.share_token)}`);
  return { itinerary, plan_id: t.plan_id, share_token: t.share_token };
}
