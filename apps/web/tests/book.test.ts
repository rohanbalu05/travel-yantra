import { afterEach, describe, expect, it, vi } from "vitest";
import { layoutPins } from "@/lib/map";
import { startStudy, track } from "@/lib/metrics";
import { GOA_ITINERARY } from "@/lib/mockPlan";
import { compareRoutes, irctcCard, partyFor, pnrStatus } from "@/lib/routes";

function fakeFetch(body: unknown) {
  const fn = vi.fn(async () => new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } }));
  vi.stubGlobal("fetch", fn);
  return fn;
}

// Node's global localStorage hides jsdom's here; the account (with its consents) lives in this one.
const store = new Map<string, string>();
const withStorage = () =>
  vi.stubGlobal("localStorage", { getItem: (k: string) => store.get(k) ?? null, setItem: (k: string, v: string) => void store.set(k, v), removeItem: (k: string) => void store.delete(k) });
const consent = (analytics: boolean) => store.set("ty.account", JSON.stringify({ consents: { plan_history: false, location: false, analytics } }));

afterEach(() => {
  vi.unstubAllGlobals();
  store.clear();
});

describe("routes client", () => {
  it("POSTs compare with the party size", async () => {
    const fn = fakeFetch({ options: [] });
    await compareRoutes({ origin: "Bengaluru", destination: "Goa", date: "2026-12-11", travellers: 4 }, GOA_ITINERARY, undefined, "http://api.test");
    const [url, init] = fn.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe("http://api.test/routes/compare");
    expect(JSON.parse(init.body as string)).toMatchObject({ travellers: 4 });
  });

  it("GETs the IRCTC card with the rail leg's stations and a sample party, no names, and no default class", async () => {
    const fn = fakeFetch({});
    await irctcCard({ from: "KSR Bengaluru City Jn", to: "Madgaon Jn", date: "2026-12-11", party: "goa_family" }, undefined, "http://api.test");
    const url = new URL((fn.mock.calls[0] as unknown as [string])[0]);
    expect(url.pathname).toBe("/routes/irctc-card");
    expect(Object.fromEntries(url.searchParams)).toEqual({ from: "KSR Bengaluru City Jn", to: "Madgaon Jn", date: "2026-12-11", party: "goa_family" });
  });

  it("GETs the PNR mock", async () => {
    const fn = fakeFetch({});
    await pnrStatus("4521690144", undefined, "http://api.test");
    expect((fn.mock.calls[0] as unknown as [string])[0]).toBe("http://api.test/routes/pnr-mock?pnr=4521690144");
  });

  it("picks the sample party from the destination", () => {
    expect(partyFor(GOA_ITINERARY)).toBe("goa_family");
    expect(partyFor({ ...GOA_ITINERARY, request: { ...GOA_ITINERARY.request, destinations: ["Mysuru"] } })).toBe("mysuru_weekend");
  });
});

describe("metrics beacon", () => {
  it("sends nothing without the analytics consent (DPDP opt-in)", () => {
    withStorage();
    consent(false);
    const beacon = vi.fn<(url: string, data: Blob) => boolean>(() => true);
    vi.stubGlobal("navigator", { ...navigator, sendBeacon: beacon });
    expect(track("start", "plan_trip", "http://api.test")).toBe(false);
    expect(beacon).not.toHaveBeenCalled();
  });

  it("sends text/plain JSON by sendBeacon with an anonymous session id", async () => {
    withStorage();
    consent(true);
    const beacon = vi.fn<(url: string, data: Blob) => boolean>(() => true);
    vi.stubGlobal("navigator", { ...navigator, sendBeacon: beacon });
    expect(track("booking_chosen", "plan_trip", "http://api.test")).toBe(true);
    const [url, blob] = beacon.mock.calls[0];
    expect(url).toBe("http://api.test/routes/metrics/event");
    expect(blob.type).toBe("text/plain;charset=utf-8");
    const body = JSON.parse(await blob.text());
    expect(Object.keys(body).sort()).toEqual(["arm", "event", "session_id", "task"]);
    expect(body.session_id).toMatch(/^[A-Za-z0-9_-]{8,64}$/);
  });

  it("measures a study session after its one-screen consent, with the study's task and arm", async () => {
    withStorage();
    consent(false);
    const ss = new Map<string, string>();
    vi.stubGlobal("sessionStorage", { getItem: (k: string) => ss.get(k) ?? null, setItem: (k: string, v: string) => void ss.set(k, v), removeItem: (k: string) => void ss.delete(k) });
    const beacon = vi.fn<(url: string, data: Blob) => boolean>(() => true);
    vi.stubGlobal("navigator", { ...navigator, sendBeacon: beacon });
    expect(track("start", undefined, "http://api.test")).toBe(false);
    startStudy({ task: "plan_mysuru", arm: "baseline" });
    expect(track("start", undefined, "http://api.test")).toBe(true);
    const body = JSON.parse(await beacon.mock.calls[0][1].text());
    expect([body.task, body.arm, body.event]).toEqual(["plan_mysuru", "baseline", "start"]);
  });

  it("does nothing without an API", () => {
    expect(track("start", "plan_trip", "")).toBe(false);
  });
});

describe("map pins", () => {
  it("puts north up and west left, inside the box", () => {
    const [basilica, fontainhas] = layoutPins([
      { id: "a", label: "1", name: "Basilica", lat: 15.5009, lng: 73.9116, kind: "stop" },
      { id: "b", label: "2", name: "Fontainhas", lat: 15.4963, lng: 73.8312, kind: "stop" },
    ]);
    expect(fontainhas.x).toBeLessThan(basilica.x); // Fontainhas is west of Old Goa
    expect(basilica.y).toBeLessThan(fontainhas.y); // and slightly south
    for (const p of [basilica, fontainhas]) {
      expect(p.x).toBeGreaterThanOrEqual(0);
      expect(p.x).toBeLessThanOrEqual(100);
    }
  });

  it("centres a single pin", () => {
    const [p] = layoutPins([{ id: "a", label: "1", name: "A", lat: 12, lng: 77, kind: "stop" }]);
    expect([p.x, p.y]).toEqual([50, 50]);
  });
});
