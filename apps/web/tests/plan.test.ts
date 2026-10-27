import { afterEach, describe, expect, it, vi } from "vitest";
import type { PlanEvent } from "@/lib/contracts";
import { GOA_ITINERARY, goaEvents } from "@/lib/mockPlan";
import { PlanHttpError, streamPlan } from "@/lib/plan";
import { initialPlanState, planReducer } from "@/lib/planState";
import { dayRows, pickIndex, tripCost } from "@/lib/planView";
import { formProblems, goaForm, toTripRequest } from "@/lib/tripForm";

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
