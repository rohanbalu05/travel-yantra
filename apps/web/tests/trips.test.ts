import { describe, expect, it } from "vitest";
import type { SavedTrip } from "@/lib/account";
import type { Itinerary, TransportOption } from "@/lib/contracts";
import { GOA_ITINERARY } from "@/lib/mockPlan";
import { chosenStays, legModeName, railOptionLeg, stayGroups, tripCost } from "@/lib/planView";
import { latestTrips, tripFacts } from "@/lib/trips";

const trip = (over: Partial<SavedTrip>): SavedTrip => ({
  plan_id: "p",
  share_token: "s",
  title: "Bengaluru to Goa",
  origin: "Bengaluru",
  destinations: ["Goa"],
  start_date: "2026-12-11",
  end_date: "2026-12-14",
  created_at: "2026-10-01T10:00:00Z",
  ...over,
});

describe("My trips", () => {
  it("shows one card per trip: the latest version, newest first", () => {
    const list = latestTrips([
      trip({ plan_id: "a1", created_at: "2026-10-01T10:00:00Z" }),
      trip({ plan_id: "a2", created_at: "2026-10-02T10:00:00Z" }),
      trip({ plan_id: "b", destinations: ["Mysuru"], created_at: "2026-10-01T12:00:00Z", updated_at: "2026-10-03T09:00:00Z" }),
    ]);
    expect(list.map((t) => t.plan_id)).toEqual(["b", "a2"]);
  });

  it("takes mode and travellers from TY1, else from the kept plan", () => {
    expect(tripFacts(trip({ mode: "air", travellers: 2 }))).toEqual({ mode: "air", travellers: 2 });
    const kept = tripFacts(trip({ itinerary: GOA_ITINERARY }));
    expect(kept.travellers).toBe(GOA_ITINERARY.request.constraints!.travellers!.length);
    expect(kept.mode).not.toBeNull();
  });
});

describe("one budget", () => {
  const it2: Itinerary = { ...GOA_ITINERARY, request: { ...GOA_ITINERARY.request, transport_mode: "rail" } };
  const opts = it2.transport ?? [];
  it("is TY1's total for the option in use, its trip_total_inr for another, never an estimate", () => {
    const inUse = opts.find((o) => o.mode === "rail")!;
    const other = opts.find((o) => o.mode !== "rail")!;
    expect(tripCost(it2, inUse)).toBe(it2.budget.total_inr);
    expect(tripCost(it2, { ...other, trip_total_inr: null })).toBeNull();
    const priced: TransportOption = { ...other, trip_total_inr: 61000 };
    expect(tripCost({ ...it2, transport: opts.map((o) => (o === other ? priced : o)) }, priced)).toBe(61000);
  });
});

describe("stays and legs", () => {
  it("groups TY1's candidate stays by stop; the first is the one in the plan", () => {
    const [a] = GOA_ITINERARY.stays!;
    const alt = { ...a, id: "alt", name: "Other Inn", price_per_night_inr: 1 };
    const it2 = { ...GOA_ITINERARY, stays: [a, alt] };
    expect(stayGroups(it2)).toEqual([{ chosen: a, others: [alt] }]);
    expect(chosenStays(it2)).toEqual([a]);
  });

  it("calls a road leg to a station a cab", () => {
    expect(legModeName({ from: "Home", to: "KSR Bengaluru City Jn", mode: "road", depart: "", arrive: "", minutes: 30, cost_inr: 300 })).toBe("Cab");
    expect(legModeName({ from: "Bengaluru", to: "Goa", mode: "road", depart: "", arrive: "", minutes: 600, cost_inr: 9000, role: "outbound" })).toBe("Road");
  });

  it("finds the rail option's train even when the plan goes by air", () => {
    const it2: Itinerary = { ...GOA_ITINERARY, request: { ...GOA_ITINERARY.request, transport_mode: "air" } };
    expect(railOptionLeg(it2)?.mode).toBe("rail");
  });
});
