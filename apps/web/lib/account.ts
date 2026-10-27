"use client";

import { useMemo, useSyncExternalStore } from "react";
import { API_BASE_URL } from "@/lib/api";
import type { Consents, Itinerary, Lang, RatingIn, TripSummary } from "@/lib/contracts";
import { ApiError, apiJSON } from "@/lib/http";

// Google sign-in through Firebase Auth when these are set (Rohan creates the Firebase project).
// Without them the app runs with a demo account: the sample persona, kept in this browser.
const FIREBASE = {
  apiKey: process.env.NEXT_PUBLIC_FIREBASE_API_KEY ?? "",
  authDomain: process.env.NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN ?? "",
  projectId: process.env.NEXT_PUBLIC_FIREBASE_PROJECT_ID ?? "",
  appId: process.env.NEXT_PUBLIC_FIREBASE_APP_ID ?? "",
};
export const firebaseEnabled = !!(FIREBASE.apiKey && FIREBASE.authDomain && FIREBASE.projectId);

export type User = { uid: string; email: string | null; name: string | null; demo: boolean };

/** A saved trip; the local stand-in also keeps the plan, so My Trips can reopen it. */
export type SavedTrip = TripSummary & { itinerary?: Itinerary };

type Account = {
  user: User | null;
  consents: Consents;
  consents_updated_at: string | null;
  trips: SavedTrip[];
};

export const NO_CONSENTS: Consents = { plan_history: false, location: false, analytics: false };
const EMPTY: Account = { user: null, consents: NO_CONSENTS, consents_updated_at: null, trips: [] };

// ---- the local copy (this browser), also the stand-in until TY1's /me endpoints exist ----

const KEY = "ty.account";
const CHANGED = "ty-account";
let memory: string | null = null; // used when storage is blocked

function readRaw(): string | null {
  try {
    return localStorage.getItem(KEY);
  } catch {
    return memory; // only when storage is blocked; otherwise storage is the truth
  }
}

function load(): Account {
  try {
    const raw = readRaw();
    return raw ? { ...EMPTY, ...(JSON.parse(raw) as Partial<Account>) } : EMPTY;
  } catch {
    return EMPTY;
  }
}

function store(a: Account | null) {
  memory = a ? JSON.stringify(a) : null;
  try {
    if (a) localStorage.setItem(KEY, memory!);
    else localStorage.removeItem(KEY);
  } catch {
    // Storage blocked: `memory` keeps it for this page.
  }
  window.dispatchEvent(new Event(CHANGED));
}

function subscribe(cb: () => void) {
  window.addEventListener(CHANGED, cb);
  window.addEventListener("storage", cb);
  return () => {
    window.removeEventListener(CHANGED, cb);
    window.removeEventListener("storage", cb);
  };
}

/** The account in this browser: undefined while prerendering, then the stored state. */
export function useAccount(): Account | undefined {
  const raw = useSyncExternalStore(subscribe, readRaw, () => undefined);
  return useMemo(() => (raw === undefined ? undefined : load()), [raw]);
}

/** Current consents without a hook (for code that runs outside React). */
export const currentConsents = (): Consents => (typeof window === "undefined" ? NO_CONSENTS : load().consents);

// ---- Firebase (loaded only when configured) ----

async function firebaseAuth() {
  const [{ initializeApp, getApps }, auth] = await Promise.all([import("firebase/app"), import("firebase/auth")]);
  const app = getApps()[0] ?? initializeApp(FIREBASE);
  return { auth, instance: auth.getAuth(app) };
}

async function idToken(): Promise<string | null> {
  if (!firebaseEnabled) return null;
  const { instance } = await firebaseAuth();
  return (await instance.currentUser?.getIdToken()) ?? null;
}

/** Google only: no phone sign-in (SMS costs money). */
export async function signIn(): Promise<User> {
  let user: User;
  if (firebaseEnabled) {
    const { auth, instance } = await firebaseAuth();
    const cred = await auth.signInWithPopup(instance, new auth.GoogleAuthProvider());
    user = { uid: cred.user.uid, email: cred.user.email, name: cred.user.displayName, demo: false };
  } else {
    user = { uid: "demo-arjun-rao", email: null, name: "Arjun Rao (sample)", demo: true };
  }
  store({ ...load(), user });
  return user;
}

export async function signOut() {
  if (firebaseEnabled) {
    const { auth, instance } = await firebaseAuth();
    await auth.signOut(instance);
  }
  store({ ...load(), user: null });
}

// ---- API calls (TY1's /me, /me/consents, /me/trips, /ratings), falling back to the local copy ----

/** True when the API answered; false when the route does not exist yet, so the local copy is used. */
async function tryApi<T>(call: (token: string | null) => Promise<T>): Promise<{ ok: true; value: T } | { ok: false }> {
  if (!API_BASE_URL) return { ok: false };
  try {
    return { ok: true, value: await call(await idToken()) };
  } catch (e) {
    if (e instanceof ApiError && (e.status === 404 || e.status === 405 || e.status === 401)) return { ok: false };
    throw e;
  }
}

const bearer = (token: string | null) => (token ? { Authorization: `Bearer ${token}` } : undefined);

export async function saveConsents(next: Consents) {
  await tryApi((token) => apiJSON<unknown>("/me/consents", { method: "PUT", body: next, headers: bearer(token) }));
  const a = load();
  // Withdrawing "Keep my trips" also removes the trips kept under it (DPDP: stop using it, and erase it).
  const trips = next.plan_history ? a.trips : [];
  store({ ...a, trips, consents: next, consents_updated_at: new Date().toISOString() });
}

/** Saves a finished plan to My Trips, only with the plan_history consent. */
export async function rememberTrip(it: Itinerary, plan_id: string | null, share_token: string | null) {
  const a = load();
  if (!a.consents.plan_history || !plan_id) return;
  const trip: SavedTrip = {
    plan_id,
    share_token: share_token ?? "",
    title: `${it.request.origin} to ${it.request.destinations.join(", ")}`,
    origin: it.request.origin,
    destinations: it.request.destinations,
    start_date: it.request.start_date,
    end_date: it.request.end_date,
    created_at: new Date().toISOString(),
    itinerary: it,
  };
  store({ ...a, trips: [trip, ...a.trips.filter((t) => t.plan_id !== plan_id)].slice(0, 50) });
}

/** The API's list when it has one (the server saves plans for signed-in users), else this browser's. */
export async function listTrips(): Promise<{ trips: SavedTrip[]; from: "api" | "browser" }> {
  const r = await tryApi((token) => apiJSON<TripSummary[]>("/me/trips", { headers: bearer(token) }));
  return r.ok ? { trips: r.value, from: "api" } : { trips: load().trips, from: "browser" };
}

/**
 * Deletes everything Travel Yantra holds about this person: on the API (DELETE /me)
 * when it exists, and always in this browser (account, consents, trips, plan in
 * progress, study session id). The language choice stays; it is not personal data.
 */
export async function deleteMyData(): Promise<{ server: number | null }> {
  const r = await tryApi((token) => apiJSON<{ deleted: boolean; items: number }>("/me", { method: "DELETE", headers: bearer(token) }));
  if (firebaseEnabled) {
    // Remove the Google sign-in record too. Firebase may ask for a recent sign-in; then at least sign out.
    const { auth, instance } = await firebaseAuth();
    const user = instance.currentUser;
    await (user ? auth.deleteUser(user) : Promise.resolve()).catch(() => auth.signOut(instance)).catch(() => {});
  }
  store(null);
  try {
    localStorage.removeItem(RATINGS_KEY);
  } catch {
    // Nothing stored.
  }
  try {
    for (const k of ["ty.plan.input", "ty.plan.result", "ty.plan.choice", "ty.metrics.session", "ty.study"]) sessionStorage.removeItem(k);
    window.dispatchEvent(new Event("ty-plan-stored"));
  } catch {
    // Nothing stored.
  }
  return { server: r.ok ? r.value.items : null };
}

const RATINGS_KEY = "ty.ratings";

/** POST /ratings (anonymous, for the O1 study). Kept in this browser until the endpoint exists. */
export async function rate(r: RatingIn): Promise<"api" | "browser"> {
  const sent = await tryApi(() => apiJSON<unknown>("/ratings", { body: r }));
  if (sent.ok) return "api";
  try {
    const list = JSON.parse(localStorage.getItem(RATINGS_KEY) ?? "[]") as RatingIn[];
    localStorage.setItem(RATINGS_KEY, JSON.stringify([...list, r].slice(-50)));
  } catch {
    // Storage blocked: the rating is lost; nothing personal was in it.
  }
  return "browser";
}

export type { Consents, Lang };
