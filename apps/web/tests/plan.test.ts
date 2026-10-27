import { afterEach, describe, expect, it, vi } from "vitest";
import type { PlanEvent } from "@/lib/contracts";
import { GOA_ITINERARY, goaEvents, revisedItinerary } from "@/lib/mockPlan";
import { PlanHttpError, streamPlan, streamRevise } from "@/lib/plan";
import { initialPlanState, planReducer } from "@/lib/planState";
import { dayRows, pickIndex, tripCost } from "@/lib/planView";
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
    expect(formProblems({ ...two, split: [2, 2] })).toEqual(["The days in each city should add up to 5."]);
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
