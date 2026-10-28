"use client";

import { useMemo, useSyncExternalStore } from "react";
import { API_BASE_URL } from "@/lib/api";
import type { Consents, Itinerary, Lang, Me, RatingIn, TripSummary } from "@/lib/contracts";
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
  /** When TY1 last answered "sign-in is not configured": the sign-in button hides for an hour. */
  signInOffAt?: number | null;
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

// TY1 answers any Bearer with 401 "sign-in is not configured" until Firebase is set up on the API.
const SIGN_IN_OFF = "sign-in is not configured";
const OFF_FOR_MS = 60 * 60 * 1000;

const signInOff = (a: Account) => !!a.signInOffAt && Date.now() - a.signInOffAt < OFF_FOR_MS;

/** Show "Sign in": the demo account without Firebase; with it, unless the API turned Google sign-in down lately. */
export function useSignInOffered(): boolean {
  const a = useAccount();
  return !firebaseEnabled || !a || !signInOff(a);
}

async function idToken(force = false): Promise<string | null> {
  if (!firebaseEnabled || signInOff(load())) return null;
  const { instance } = await firebaseAuth();
  await instance.authStateReady(); // after a reload Firebase restores the user asynchronously
  return (await instance.currentUser?.getIdToken(force)) ?? null;
}

/** The token was refused twice: the traveller must sign in again (never a quiet fall-back to the browser id). */
export class SignInExpired extends ApiError {
  constructor() {
    super("Your sign-in has expired. Sign in again.", 401);
  }
}

/**
 * Runs an API call with this browser's headers (X-Client-Id, plus the Google token when signed in).
 * A 401 on a token means it is bad or expired: refresh it and try once more. "sign-in is not
 * configured" turns sign-in off here for an hour and goes on as this browser.
 */
export async function withAuth<T>(call: (headers: Record<string, string>) => Promise<T>): Promise<T> {
  const token = await idToken();
  try {
    return await call(bearer(token));
  } catch (e) {
    if (!(e instanceof ApiError) || e.status !== 401 || !token) throw e;
    if (e.message === SIGN_IN_OFF) {
      await signOut();
      store({ ...load(), signInOffAt: Date.now() });
      return call(bearer(null));
    }
  }
  try {
    return await call(bearer(await idToken(true)));
  } catch (e) {
    throw e instanceof ApiError && e.status === 401 ? new SignInExpired() : e;
  }
}

type FirebaseUser = { uid: string; email: string | null; displayName: string | null };

/** Phones and tablets: popups are blocked or lose their result on Android Chrome, so redirect there. */
export function prefersRedirect(): boolean {
  if (typeof navigator === "undefined") return false;
  return /Android|iPhone|iPad|iPod|Mobile/i.test(navigator.userAgent);
}

/** Stores the signed-in user, moves this browser's data to the account, and keeps trips by default. */
async function finishSignIn(fb: FirebaseUser | null): Promise<User> {
  const user: User = fb
    ? { uid: fb.uid, email: fb.email, name: fb.displayName, demo: false }
    : { uid: "demo-arjun-rao", email: null, name: "Arjun Rao (sample)", demo: true };
  store({ ...load(), user });
  // The first signed-in call carries this browser's X-Client-Id: TY1 moves its trips, ratings and consents to the account.
  if (!user.demo) await syncMe().catch(() => false);
  // "Keep my trips" is on once signed in, unless this person has already made a choice.
  const a = load();
  if (!a.consents_updated_at && !a.consents.plan_history) await saveConsents({ ...a.consents, plan_history: true }).catch(() => {});
  return load().user ?? user;
}

/**
 * Google sign-in. On a laptop a popup; on a phone a redirect (the page reloads, and
 * finishRedirectSignIn picks the result up). Returns null when the page is leaving to Google.
 * No phone sign-in (SMS costs money).
 */
export async function signIn(): Promise<User | null> {
  if (!firebaseEnabled) return finishSignIn(null);
  const { auth, instance } = await firebaseAuth();
  const provider = new auth.GoogleAuthProvider();
  if (prefersRedirect()) {
    await auth.signInWithRedirect(instance, provider);
    return null;
  }
  const cred = await auth.signInWithPopup(instance, provider);
  return finishSignIn(cred.user);
}

/** After a redirect back from Google: the signed-in user, or null when this load was not a sign-in. */
export async function finishRedirectSignIn(): Promise<User | null> {
  if (!firebaseEnabled) return null;
  const { auth, instance } = await firebaseAuth();
  const cred = await auth.getRedirectResult(instance);
  return cred ? finishSignIn(cred.user) : null;
}

/** Email and password (Firebase). `create` makes the account first. */
export async function signInWithEmail(email: string, password: string, create: boolean): Promise<User> {
  if (!firebaseEnabled) throw new AuthProblem("auth/operation-not-allowed");
  const { auth, instance } = await firebaseAuth();
  try {
    const cred = create
      ? await auth.createUserWithEmailAndPassword(instance, email.trim(), password)
      : await auth.signInWithEmailAndPassword(instance, email.trim(), password);
    return await finishSignIn(cred.user);
  } catch (e) {
    throw AuthProblem.from(e);
  }
}

/** Sends Firebase's password reset email. Says nothing about whether the address has an account. */
export async function resetPassword(email: string): Promise<void> {
  if (!firebaseEnabled) throw new AuthProblem("auth/operation-not-allowed");
  const { auth, instance } = await firebaseAuth();
  try {
    await auth.sendPasswordResetEmail(instance, email.trim());
  } catch (e) {
    const p = AuthProblem.from(e);
    if (p.code !== "auth/user-not-found") throw p;
  }
}

/** A sign-in failure with Firebase's error code, so the page can say what went wrong. */
export class AuthProblem extends Error {
  constructor(readonly code: string) {
    super(code);
  }
  static from(e: unknown): AuthProblem {
    if (e instanceof AuthProblem) return e;
    const code = typeof e === "object" && e && "code" in e ? String((e as { code: unknown }).code) : "unknown";
    return new AuthProblem(code);
  }
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
async function tryApi<T>(call: (headers: Record<string, string>) => Promise<T>): Promise<{ ok: true; value: T } | { ok: false }> {
  if (!API_BASE_URL) return { ok: false };
  try {
    return { ok: true, value: await withAuth(call) };
  } catch (e) {
    if (e instanceof SignInExpired) throw e;
    if (e instanceof ApiError && (e.status === 404 || e.status === 405 || e.status === 401)) return { ok: false };
    throw e;
  }
}

// TY1 keys account data by an anonymous id per browser (X-Client-Id), and by the Google account when signed in.
const CLIENT_KEY = "ty.client";
let clientMemory: string | null = null;

/** This browser's anonymous id: a random UUID, made once. Not linked to a name, email or phone. */
export function clientId(): string {
  try {
    let id = localStorage.getItem(CLIENT_KEY);
    if (!id) {
      id = crypto.randomUUID();
      localStorage.setItem(CLIENT_KEY, id);
    }
    return id;
  } catch {
    return (clientMemory ??= crypto.randomUUID());
  }
}

/** The anonymous id alone; withAuth adds the Google token when signed in. */
export const clientHeaders = (): Record<string, string> => ({ "X-Client-Id": clientId() });

const bearer = (token: string | null): Record<string, string> => ({ ...clientHeaders(), ...(token ? { Authorization: `Bearer ${token}` } : {}) });

export async function saveConsents(next: Consents) {
  const r = await tryApi((headers) => apiJSON<Me>("/me/consents", { method: "PUT", body: next, headers }));
  const a = load();
  // Withdrawing "Keep my trips" clears this browser’s list. TY1 keeps server trips until DELETE /me (asked to erase on withdrawal).
  const trips = next.plan_history ? a.trips : [];
  const saved = r.ok ? { ...NO_CONSENTS, ...r.value.consents } : next;
  store({ ...a, trips, consents: saved, consents_updated_at: (r.ok && r.value.consents_updated_at) || new Date().toISOString() });
}

/** Takes the server's consents (GET /me) as the truth when the API has them; no-op until then. */
export async function syncMe(): Promise<boolean> {
  const r = await tryApi((headers) => apiJSON<Me>("/me", { headers }));
  if (!r.ok) return false;
  const a = load();
  const me = r.value;
  // Signed in with Google, /me names the account ("fb:<uid>", with the token's name and email).
  const user = a.user && !a.user.demo ? { ...a.user, name: me.name ?? a.user.name, email: me.email ?? a.user.email } : a.user;
  store({ ...a, user, consents: { ...NO_CONSENTS, ...me.consents }, consents_updated_at: me.consents_updated_at ?? a.consents_updated_at });
  return true;
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
  const r = await tryApi((headers) => apiJSON<TripSummary[]>("/me/trips", { headers }));
  return r.ok ? { trips: r.value, from: "api" } : { trips: load().trips, from: "browser" };
}

/**
 * Deletes everything Travel Yantra holds about this person: on the API (DELETE /me)
 * when it exists, and always in this browser (account, consents, trips, plan in
 * progress, study session id). The language choice stays; it is not personal data.
 */
export async function deleteMyData(): Promise<{ server: number | null }> {
  const r = await tryApi((headers) => apiJSON<{ deleted: boolean; items: number }>("/me", { method: "DELETE", headers }));
  if (firebaseEnabled) {
    // Remove the Google sign-in record too. Firebase may ask for a recent sign-in; then at least sign out.
    const { auth, instance } = await firebaseAuth();
    const user = instance.currentUser;
    await (user ? auth.deleteUser(user) : Promise.resolve()).catch(() => auth.signOut(instance)).catch(() => {});
  }
  store(null);
  try {
    localStorage.removeItem(RATINGS_KEY);
    localStorage.removeItem(CLIENT_KEY); // a fresh anonymous id from now on, so nothing links back
  } catch {
    // Nothing stored.
  }
  try {
    for (const k of ["ty.plan.input", "ty.plan.result", "ty.plan.choice", "ty.plan.done", "ty.metrics.session", "ty.study"]) sessionStorage.removeItem(k);
    window.dispatchEvent(new Event("ty-plan-stored"));
  } catch {
    // Nothing stored.
  }
  return { server: r.ok ? r.value.items : null };
}

const RATINGS_KEY = "ty.ratings";

/** POST /ratings (anonymous, for the O1 study). Kept in this browser until the endpoint exists. */
export async function rate(r: RatingIn): Promise<"api" | "browser"> {
  const sent = await tryApi((headers) => apiJSON<unknown>("/ratings", { body: r, headers }));
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
