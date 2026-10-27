import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { deleteMyData, listTrips, rate, rememberTrip, saveConsents, signIn } from "@/lib/account";
import { GOA_ITINERARY } from "@/lib/mockPlan";

// Node's global storage objects hide jsdom's here; plain ones for the tests.
function fakeStorage() {
  const m = new Map<string, string>();
  return { m, s: { getItem: (k: string) => m.get(k) ?? null, setItem: (k: string, v: string) => void m.set(k, v), removeItem: (k: string) => void m.delete(k) } };
}
let local: ReturnType<typeof fakeStorage>;
let session: ReturnType<typeof fakeStorage>;

beforeEach(() => {
  local = fakeStorage();
  session = fakeStorage();
  vi.stubGlobal("localStorage", local.s);
  vi.stubGlobal("sessionStorage", session.s);
});
afterEach(() => vi.unstubAllGlobals());

const account = () => JSON.parse(local.m.get("ty.account") ?? "null");

describe("account without an API (this browser)", () => {
  it("signs in as the demo persona when Firebase is not configured", async () => {
    expect(await signIn()).toMatchObject({ demo: true, name: "Arjun Rao (sample)" });
    expect(account().user.uid).toBe("demo-arjun-rao");
  });

  it("starts with every consent off and records when they change", async () => {
    await signIn();
    expect(account().consents).toEqual({ plan_history: false, location: false, analytics: false });
    await saveConsents({ plan_history: true, location: false, analytics: false });
    expect(account().consents.plan_history).toBe(true);
    expect(account().consents_updated_at).toMatch(/^\d{4}-\d{2}-\d{2}T/);
  });

  it("keeps a trip only with the Keep my trips consent", async () => {
    await rememberTrip(GOA_ITINERARY, "p1", "s1");
    expect((await listTrips()).trips).toEqual([]);
    await saveConsents({ plan_history: true, location: false, analytics: false });
    await rememberTrip(GOA_ITINERARY, "p1", "s1");
    await rememberTrip(GOA_ITINERARY, "p1", "s1"); // the same plan twice is one trip
    const { trips, from } = await listTrips();
    expect(from).toBe("browser");
    expect(trips.map((t) => [t.plan_id, t.title])).toEqual([["p1", "Bengaluru to Goa"]]);
  });

  it("deletes the account, trips, plan in progress and study id, but not the language", async () => {
    await signIn();
    await saveConsents({ plan_history: true, location: true, analytics: true });
    await rememberTrip(GOA_ITINERARY, "p1", "s1");
    local.m.set("ty.lang", "kn");
    session.m.set("ty.plan.result", "{}");
    session.m.set("ty.metrics.session", "abc");
    expect(await deleteMyData()).toEqual({ server: null });
    expect(local.m.has("ty.account")).toBe(false);
    expect(session.m.has("ty.plan.result")).toBe(false);
    expect(session.m.has("ty.metrics.session")).toBe(false);
    expect(local.m.get("ty.lang")).toBe("kn");
  });

  it("keeps a rating in the browser while there is no API", async () => {
    expect(await rate({ plan_id: "p1", score: 4, comment: null, lang: "en" })).toBe("browser");
    expect(JSON.parse(local.m.get("ty.ratings")!)).toEqual([{ plan_id: "p1", score: 4, comment: null, lang: "en" }]);
  });
});
