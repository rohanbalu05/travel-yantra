import { afterEach, describe, expect, it, vi } from "vitest";
import type { PlanEvent } from "@/lib/contracts";
import { translate } from "@/lib/i18n";
import { GOA_ITINERARY, goaEvents, revisedItinerary } from "@/lib/mockPlan";
import { PlanHttpError, streamPlan, streamRevise } from "@/lib/plan";
import { initialPlanState, planReducer } from "@/lib/planState";
import { OSM_ATTRIBUTION, OSM_TILES, pinHtml } from "@/lib/map";
import { dayRows, pickIndex, planMode, planRailLeg, tripCost } from "@/lib/planView";
import { formFromDraft, formProblems, goaForm, splitOf, toTripRequest, tripDays } from "@/lib/tripForm";

const sse = (evs: PlanEvent[]) => evs.map((e) => `: ping\n\ndata: ${JSON.stringify(e)}\n\n`).join("");

function fakeFetch(status: number, text: string, type = "text/event-stream") {
  const fn = vi.fn(async () => new Response(text, { status, headers: { "Content-Type": type } }));
  vi.stubGlobal("fetch", fn);
  return fn;
}

async function collect(gen: AsyncGenerator<PlanEvent>) {
  const out: PlanEvent[] = [];
  for await (const ev of gen) out.push(ev);
  return out;
}

afterEach(() => vi.unstubAllGlobals());

describe("streamPlan", () => {
  it("POSTs the body as JSON to {base}/plan and stops at the first terminal event", async () => {
    const fn = fakeFetch(200, sse([{ stage: "intake", message: "a" }, { stage: "needs_input", message: "b", questions: ["When?"] }, { stage: "done", message: "never" }]));
    const evs = await collect(streamPlan({ text: "Goa", lang: "en" }, undefined, "http://api.test"));
    expect(evs.map((e) => e.stage)).toEqual(["intake", "needs_input"]);
    const [url, init] = fn.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe("http://api.test/plan");
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body as string)).toEqual({ text: "Goa", lang: "en" });
  });

  it("turns an HTTP error into a readable PlanHttpError from FastAPI's detail", async () => {
    fakeFetch(422, JSON.stringify({ detail: [{ msg: "text is too long" }] }), "application/json");
    await expect(collect(streamPlan({ text: "x" }, undefined, "http://api.test"))).rejects.toThrow(new PlanHttpError("text is too long"));
  });

  it("replays the Goa sample when no API base URL is set", async () => {
    vi.useFakeTimers();
    const p = collect(streamPlan({ text: "Goa" }, undefined, ""));
    await vi.runAllTimersAsync();
    const evs = await p;
    vi.useRealTimers();
    expect(evs.at(-1)?.stage).toBe("done");
    expect(evs.at(-1)?.plan_id).toBe("sample-goa-family");
  });
});

describe("streamRevise", () => {
  it("POSTs the ReviseRequest to /plan/{id}/revise and ends with the new plan", async () => {
    const it2 = GOA_ITINERARY;
    const fn = fakeFetch(200, sse([{ stage: "intake", message: "Revising" }, { stage: "done", message: "ok", partial: it2, plan_id: "p2", share_token: "s2" }]));
    const evs = await collect(streamRevise("p/1", { intent: "lighter_day", day: "2026-12-12", lang: "en" }, undefined, "http://api.test"));
    const [url, init] = fn.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe("http://api.test/plan/p%2F1/revise");
    expect(JSON.parse(init.body as string)).toEqual({ intent: "lighter_day", day: "2026-12-12", lang: "en" });
    const s = evs.reduce(planReducer, initialPlanState());
    expect([s.status, s.planId, s.shareToken]).toEqual(["done", "p2", "s2"]);
  });

  it("shows TY1's 422 reason when the day is not in the plan", async () => {
    fakeFetch(422, JSON.stringify({ detail: "day 2027-01-01 is not in the plan" }), "application/json");
    await expect(collect(streamRevise("p1", { intent: "rain", day: "2027-01-01" }, undefined, "http://api.test"))).rejects.toThrow("day 2027-01-01 is not in the plan");
  });

  it("mock: a lighter day drops that day's last stop and its legs; other days are untouched", () => {
    const out = revisedItinerary(GOA_ITINERARY, { intent: "lighter_day", day: "2026-12-11" });
    expect(out.days[0].stops?.map((s) => s.id)).toEqual(["goa-basilica"]);
    expect(out.days[0].legs).toEqual([]);
    expect(out.days.slice(1)).toEqual(GOA_ITINERARY.days.slice(1));
  });
});

describe("planReducer", () => {
  it("folds the Goa events into a finished plan", () => {
    const s = goaEvents().reduce(planReducer, initialPlanState());
    expect(s.status).toBe("done");
    expect(Object.values(s.agents).every(Boolean)).toBe(true);
    expect(s.checks.map((c) => c.violations.length)).toEqual([1, 0]);
    expect(s.repairs).toHaveLength(1);
    expect(s.intake).toBe("Bengaluru to Goa, 11 to 14 Dec, 4 travellers.");
    expect(s.itinerary).toEqual(GOA_ITINERARY);
    expect(s.planId).toBe("sample-goa-family");
  });

  it("keeps the parsed intake message over the quick first one, whatever the order", () => {
    const s = [{ stage: "intake", step: "intake", message: "parsed" }, { stage: "intake", step: null, message: "Reading…" }].reduce(
      (a, e) => planReducer(a, e as PlanEvent),
      initialPlanState(),
    );
    expect(s.intake).toBe("parsed");
  });

  it("records questions on needs_input (at most 3) and retryable errors", () => {
    const q = planReducer(initialPlanState(), { stage: "needs_input", message: "Need more", questions: ["a", "b", "c", "d"] });
    expect(q.status).toBe("needs_input");
    expect(q.questions).toEqual(["a", "b", "c"]);
    const e = planReducer(initialPlanState(), { stage: "error", message: "Model timed out", retryable: true });
    expect(e.error).toEqual({ message: "Model timed out", retryable: true });
  });
});

describe("plan view helpers", () => {
  it("prices the trip per way of travel and picks the cheapest that fits the budget", () => {
    const [rail, air] = GOA_ITINERARY.transport!;
    expect(tripCost(GOA_ITINERARY, rail)).toBe(46800 - 19200 + 4800);
    expect(tripCost(GOA_ITINERARY, air)).toBe(46800 - 19200 + 16400);
    expect(pickIndex(GOA_ITINERARY)).toBe(0);
  });

  it("puts each leg after the stop it leaves, and the night's stay last", () => {
    const rows = dayRows(GOA_ITINERARY.days[0], GOA_ITINERARY);
    expect(rows.map((r) => r.kind)).toEqual(["stop", "move", "stop", "stay"]);
    expect(dayRows(GOA_ITINERARY.days[3], GOA_ITINERARY)).toEqual([]); // check-out day: no stay that night
  });
});

describe("multi-city days", () => {
  it("opens the day with the city-to-city leg that leaves no stop", () => {
    const day = {
      date: "2026-12-13",
      stops: [GOA_ITINERARY.days[0].stops![0]],
      legs: [{ from: "Goa", to: "Mysuru", mode: "road" as const, depart: "2026-12-13T08:00:00", arrive: "2026-12-13T14:00:00", minutes: 360, cost_inr: 6000 }],
      notes: ["Travel: Goa to Mysuru by road."],
    };
    expect(dayRows(day, GOA_ITINERARY).map((r) => r.kind)).toEqual(["move", "stop", "stay"]);
  });
});

describe("journeys by Leg.role", () => {
  it("puts the journey there first and the journey home last, whatever the order in legs", () => {
    const stop = GOA_ITINERARY.days[0].stops![0];
    const leg = (from: string, to: string, role: "outbound" | "home" | null) => ({ from, to, mode: "rail" as const, depart: "2026-12-11T08:00:00", arrive: "2026-12-11T10:00:00", minutes: 120, cost_inr: 500, role });
    const day = { date: "2026-12-14", stops: [stop], legs: [leg("Goa", "Bengaluru", "home"), leg("Bengaluru", "Goa", "outbound")] };
    const rows = dayRows(day, GOA_ITINERARY).filter((r) => r.kind !== "stay");
    expect(rows.map((r) => (r.kind === "move" ? r.leg.role : r.kind))).toEqual(["outbound", "stop", "home"]);
  });
});

describe("form from intake's draft", () => {
  it("keeps what intake understood and leaves the rest empty to ask", () => {
    const f = formFromDraft({ origin: "Bengaluru", destinations: ["Goa", "Gokarna"], travellers: [{ name: "You", age: 30 }, { name: "Father", age: 60 }] });
    expect([f.from, f.to, f.start, f.end]).toEqual(["Bengaluru", "Goa, Gokarna", "", ""]);
    expect([f.adults, f.seniors, f.kids]).toEqual([1, 1, 0]);
    expect(formProblems(f)).toEqual(["Pick the first and last day."]);
    const r = toTripRequest({ ...f, start: "2026-12-11", end: "2026-12-14" });
    expect(r.constraints?.travellers?.map((t) => t.name)).toEqual(["You", "Father"]);
  });
});

describe("days per destination", () => {
  const two = { ...goaForm(), from: "Bengaluru", to: "Mysuru, Coorg", start: "2026-10-30", end: "2026-11-03" };

  it("splits evenly like TY1 until the traveller changes it, and sends only a chosen split", () => {
    expect(tripDays(two)).toBe(5);
    expect(splitOf(two)).toEqual([3, 2]);
    expect(toTripRequest(two).days_per_destination).toBeNull();
    const chosen = { ...two, split: [2, 3] };
    expect(formProblems(chosen)).toEqual([]);
    expect(toTripRequest(chosen).days_per_destination).toEqual([2, 3]);
  });

  it("says when the days do not add up", () => {
    const problems = formProblems({ ...two, split: [2, 2] });
    expect(problems).toEqual(["The days in each city should add up to {days}."]);
    expect(translate(problems[0], "en", { days: tripDays(two) })).toBe("The days in each city should add up to 5.");
  });

  it("ignores an old split once the cities change", () => {
    expect(splitOf({ ...two, to: "Mysuru, Coorg, Hampi", split: [2, 3] })).toEqual([2, 2, 1]);
  });
});

describe("trip form", () => {
  it("prefills from the Goa sample and sends the sample's travellers unchanged", () => {
    const f = goaForm();
    expect([f.adults, f.seniors, f.kids]).toEqual([3, 1, 0]);
    const r = toTripRequest(f);
    expect(r.origin).toBe("Bengaluru");
    expect(r.destinations).toEqual(["Goa"]);
    expect(r.constraints?.budget_inr).toBe(60000);
    expect(r.constraints?.travellers?.map((t) => t.name)).toContain("Arjun Rao");
    expect(r.constraints?.dietary).toEqual(["vegetarian"]);
    expect(formProblems(f)).toEqual([]);
  });

  it("explains what is wrong in plain words", () => {
    const f = { ...goaForm(), to: " ", end: "2026-12-01", budget: "lots", adults: 0, seniors: 0 };
    expect(formProblems(f)).toEqual([
      "Say where you are going.",
      "The last day is before the first.",
      "Add at least one traveller.",
      "Write the budget as a number of rupees.",
    ]);
  });
});

describe("the chosen way to travel", () => {
  it("sends the form's mode as transport_mode, null when the planner picks", () => {
    expect(toTripRequest(goaForm()).transport_mode).toBeNull();
    expect(toTripRequest({ ...goaForm(), transport: "road" }).transport_mode).toBe("road");
  });

  it("follows the plan's mode: transport_mode, else the first journey out", () => {
    const air = GOA_ITINERARY.transport!.findIndex((o) => o.mode === "air");
    const chosen = { ...GOA_ITINERARY, request: { ...GOA_ITINERARY.request, transport_mode: "air" as const } };
    expect(planMode(chosen)).toBe("air");
    expect(pickIndex(chosen)).toBe(air);
    const out = { ...GOA_ITINERARY, days: [{ date: "2026-12-11", legs: [{ from: "Bengaluru", to: "Madgaon", mode: "air" as const, depart: "2026-12-11T06:00:00+05:30", arrive: "2026-12-11T07:15:00+05:30", minutes: 75, cost_inr: 20000, role: "outbound" as const }] }] };
    expect(planMode(out)).toBe("air");
    expect(pickIndex(out)).toBe(air);
    expect(planMode(GOA_ITINERARY)).toBeNull(); // the sample has no journey roles: cheapest that fits
  });

  it("the mock's transport revise puts the mode first and switches every journey", () => {
    const base = { ...GOA_ITINERARY, days: [{ date: "2026-12-11", legs: [{ from: "Bengaluru", to: "Madgaon", mode: "rail" as const, depart: "2026-12-11T06:00:00+05:30", arrive: "2026-12-11T14:00:00+05:30", minutes: 480, cost_inr: 3000, role: "outbound" as const }, { from: "A", to: "B", mode: "road" as const, depart: "2026-12-11T15:00:00+05:30", arrive: "2026-12-11T15:20:00+05:30", minutes: 20, cost_inr: 300 }] }] };
    const r = revisedItinerary(base, { intent: "transport", mode: "air" });
    expect(r.request.transport_mode).toBe("air");
    expect(r.transport![0].mode).toBe("air");
    expect(r.days[0].legs!.map((l) => l.mode)).toEqual(["air", "road"]);
    expect(pickIndex(r)).toBe(0);
  });
});

describe("map pins", () => {
  it("escapes the label in the Leaflet pin and credits OpenStreetMap", () => {
    expect(pinHtml({ label: "<b>1</b>", kind: "stop" })).toBe('<span class="smap-pin smap-stop" aria-hidden="true">&#60;b&#62;1&#60;/b&#62;</span>');
    expect(OSM_ATTRIBUTION).toContain("OpenStreetMap</a> contributors");
    expect(OSM_TILES).toBe("https://tile.openstreetmap.org/{z}/{x}/{y}.png");
  });
});

describe("the plan's train (QA #101)", () => {
  it("takes the rail journey from the days before any option's leg", () => {
    const leg = { from: "Bangalore City JN", to: "Mysuru JN", mode: "rail" as const, depart: "2026-10-31T07:00:00+05:30", arrive: "2026-10-31T09:44:00+05:30", minutes: 164, cost_inr: 400, role: "outbound" as const };
    const it = { ...GOA_ITINERARY, days: [{ date: "2026-10-31", legs: [leg] }] };
    expect(planRailLeg(it)).toBe(leg);
    expect(planRailLeg(GOA_ITINERARY)?.depart).toBe("2026-12-11T21:00:00"); // no journeys in the days: the option's leg
  });
});

describe("what a revise changed (QA #108)", () => {
  it("keeps the solver's line from the stream", async () => {
    let s = initialPlanState();
    for await (const ev of streamRevise("sample-goa-family", { intent: "lighter_day", day: GOA_ITINERARY.days[1].date })) s = planReducer(s, ev);
    expect(s.status).toBe("done");
    expect(s.solvedNote).toBe(`Dropped ${GOA_ITINERARY.days[1].stops!.at(-1)!.name}`);
  });
});

describe("TY1's journey day (QA #118, #104)", () => {
  const out = { from: "Bengaluru", to: "Mysuru", mode: "rail" as const, depart: "2026-10-31T07:00:00", arrive: "2026-10-31T09:44:00", minutes: 164, cost_inr: 1200, role: "outbound" as const, ref: "12613" };
  const transfer = { from: "Mysuru", to: "Mysore Palace", mode: "road" as const, depart: "2026-10-31T10:00:00", arrive: "2026-10-31T10:15:00", minutes: 15, cost_inr: 150, role: "transfer" as const };
  const stop = { ...GOA_ITINERARY.days[0].stops![0], id: "palace", name: "Mysore Palace" };
  const day = { date: "2026-10-31", stops: [stop], legs: [out, transfer], schedule: [{ place_id: "palace", arrive: "2026-10-31T10:15:00", start: "2026-10-31T10:20:00", leave: "2026-10-31T11:50:00" }] };
  const plan = { ...GOA_ITINERARY, days: [day], stays: [] };

  it("opens the day with the journey, then the transfer, then the stop at its scheduled time", () => {
    const rows = dayRows(day, plan);
    expect(rows.map((r) => (r.kind === "move" ? r.leg.role : r.kind))).toEqual(["outbound", "transfer", "stop"]);
    expect(rows[2].kind === "stop" && rows[2].at?.start).toBe("2026-10-31T10:20:00");
  });

  it("costs the option in use at the plan's own total", () => {
    expect(planRailLeg(plan)?.ref).toBe("12613");
    const used = plan.transport!.find((o) => o.mode === "rail")!;
    expect(tripCost(plan, used)).toBe(plan.budget.total_inr);
  });
});
