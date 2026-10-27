import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

// Firebase faked: one signed-in user whose token changes when refreshed. No network.
const tokens = { getIdToken: vi.fn(async (force?: boolean) => (force ? "fresh" : "stale")) };
vi.mock("firebase/app", () => ({ getApps: () => [{}], initializeApp: () => ({}) }));
vi.mock("firebase/auth", () => ({
  getAuth: () => ({ currentUser: tokens, authStateReady: async () => {} }),
  signOut: vi.fn(async () => {}),
}));

const store = new Map<string, string>();

beforeEach(() => {
  store.clear();
  tokens.getIdToken.mockClear();
  vi.stubGlobal("localStorage", { getItem: (k: string) => store.get(k) ?? null, setItem: (k: string, v: string) => void store.set(k, v), removeItem: (k: string) => void store.delete(k) });
  // Dummy values: firebaseEnabled is read when lib/account loads.
  vi.stubEnv("NEXT_PUBLIC_FIREBASE_API_KEY", "test-key");
  vi.stubEnv("NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN", "test.example");
  vi.stubEnv("NEXT_PUBLIC_FIREBASE_PROJECT_ID", "test-project");
  vi.resetModules();
});
afterEach(() => {
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
});

// Fresh modules each test (firebaseEnabled is read at load), so ApiError must come from the same load.
const load = async () => ({ ...(await import("@/lib/account")), ApiError: (await import("@/lib/http")).ApiError });

const seen: Record<string, string>[] = [];
afterEach(() => void (seen.length = 0));

describe("signed-in calls (TY1: Bearer plus X-Client-Id)", () => {
  it("sends the token with the browser id", async () => {
    const { withAuth } = await load();
    await withAuth(async (h) => void seen.push(h));
    expect(seen[0].Authorization).toBe("Bearer stale");
    expect(seen[0]["X-Client-Id"]).toBeTruthy();
  });

  it("refreshes a refused token and tries once more", async () => {
    const { ApiError, withAuth } = await load();
    const out = await withAuth(async (h) => {
      seen.push(h);
      if (seen.length === 1) throw new ApiError("token expired", 401);
      return "ok";
    });
    expect(out).toBe("ok");
    expect(seen.map((h) => h.Authorization)).toEqual(["Bearer stale", "Bearer fresh"]);
  });

  it("says so when the token is refused twice, never falling back quietly", async () => {
    const { ApiError, SignInExpired, withAuth } = await load();
    await expect(withAuth(async () => { throw new ApiError("bad token", 401); })).rejects.toBeInstanceOf(SignInExpired);
  });

  it("turns sign-in off and goes on as this browser when the API has no sign-in", async () => {
    const { ApiError, withAuth } = await load();
    const out = await withAuth(async (h) => {
      seen.push(h);
      if (h.Authorization) throw new ApiError("sign-in is not configured", 401);
      return "ok";
    });
    expect(out).toBe("ok");
    expect(seen[1].Authorization).toBeUndefined();
    expect(JSON.parse(store.get("ty.account")!).signInOffAt).toBeGreaterThan(0);
    await withAuth(async (h) => void seen.push(h));
    expect(seen[2].Authorization).toBeUndefined(); // off for the next hour
  });
});
