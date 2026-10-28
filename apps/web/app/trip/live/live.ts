import type { DayPlan, GuideAnswer, Itinerary, Place } from "@/lib/contracts";

// Where you are against today's plan. Times are local wall-clock ISO strings
// ("2026-12-12T09:50:00", no zone), as the planner writes them, so they compare
// as strings once cut to minutes.

export type Where = { lat: number; lng: number; accuracy?: number };

export type Slot = { place: Place; arrive: string; start: string; leave: string; planned: boolean };

/** "YYYY-MM-DDTHH:MM" in this device's local time. */
export function localNow(d: Date = new Date()): string {
  const p = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}`;
}

const min = (iso: string) => iso.slice(0, 16);

export function addMinutes(iso: string, m: number): string {
  const [date, time] = min(iso).split("T");
  const [y, mo, d] = date.split("-").map(Number);
  const [h, mi] = time.split(":").map(Number);
  return localNow(new Date(y, mo - 1, d, h, mi + m));
}

export function minutesBetween(a: string, b: string): number {
  const t = (iso: string) => {
    const [date, time] = min(iso).split("T");
    const [y, mo, d] = date.split("-").map(Number);
    const [h, mi] = time.split(":").map(Number);
    return new Date(y, mo - 1, d, h, mi).getTime();
  };
  return Math.round((t(b) - t(a)) / 60_000);
}

/** The day whose date is today's, if the trip is on. */
export function todayIndex(it: Itinerary, now: string): number {
  return it.days.findIndex((d) => d.date === now.slice(0, 10));
}

/**
 * Each stop with its times: the planner's schedule when it has one, else
 * worked out from the day's rides and each place's usual visit length,
 * starting at 9:00 (marked planned: false, so the page says "about").
 */
export function slots(day: DayPlan): Slot[] {
  const stops = day.stops ?? [];
  const sched = new Map((day.schedule ?? []).map((s) => [s.place_id, s]));
  const legs = day.legs ?? [];
  let t = `${day.date}T09:00`;
  return stops.map((place) => {
    const s = sched.get(place.id);
    if (s) {
      t = min(s.leave);
      return { place, arrive: min(s.arrive), start: min(s.start), leave: min(s.leave), planned: true };
    }
    const ride = legs.find((l) => l.to === place.name && l.role !== "outbound" && l.role !== "home");
    const arrive = ride ? (min(ride.arrive) > t ? min(ride.arrive) : addMinutes(t, ride.minutes)) : t;
    const leave = addMinutes(arrive, place.typical_visit_minutes);
    t = leave;
    return { place, arrive, start: arrive, leave, planned: false };
  });
}

/** Straight-line distance in metres. */
export function metres(a: { lat: number; lng: number }, b: { lat: number; lng: number }): number {
  const R = 6_371_000;
  const rad = (x: number) => (x * Math.PI) / 180;
  const dLat = rad(b.lat - a.lat);
  const dLng = rad(b.lng - a.lng);
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(rad(a.lat)) * Math.cos(rad(b.lat)) * Math.sin(dLng / 2) ** 2;
  return Math.round(2 * R * Math.asin(Math.sqrt(h)));
}

/** A rough time to get there: walking under 1.2 km, else by road at city speed. Labelled "about". */
export function roughMinutes(m: number): { minutes: number; by: "walk" | "road" } {
  if (m <= 1200) return { minutes: Math.max(1, Math.round(m / 75)), by: "walk" }; // 4.5 km/h
  return { minutes: Math.round((m * 1.35) / 1000 / (25 / 60)) + 5, by: "road" }; // winding roads, 25 km/h, parking
}

export const AT_METRES = 250;

export type Status = {
  /** The stop you are at (by location), or the one the plan has you at now. */
  current: Slot | null;
  /** True when `current` comes from your location, not the clock. */
  here: boolean;
  next: Slot | null;
  /** Straight-line metres to `next`, when your location is known. */
  distance: number | null;
  eta: { minutes: number; by: "walk" | "road" } | null;
  /** Minutes until the plan has you at `next`; negative once that time has passed. */
  until: number | null;
  /** Your estimate of how late you will reach `next` (0 if on time), when it can be told. */
  late: number | null;
  done: boolean;
};

export function status(day: DayPlan, now: string, where: Where | null): Status {
  const all = slots(day);
  const atIdx = where ? all.findIndex((s) => metres(where, s.place) <= AT_METRES + (where.accuracy ?? 0)) : -1;
  const clockIdx = all.findIndex((s) => s.arrive <= now && now < s.leave);
  const here = atIdx >= 0;
  const curIdx = here ? atIdx : clockIdx;
  const nextIdx = curIdx >= 0 ? curIdx + 1 : all.findIndex((s) => s.arrive > now);
  const next = nextIdx >= 0 && nextIdx < all.length ? all[nextIdx] : null;
  const distance = next && where ? metres(where, next.place) : null;
  const eta = distance !== null ? roughMinutes(distance) : null;
  const until = next ? minutesBetween(now, next.arrive) : null;
  let late: number | null = null;
  if (next && until !== null) {
    if (eta) {
      // Still at a stop: you leave it when the plan says, or now if that's passed.
      const leaveAt = here && all[curIdx].leave > now ? minutesBetween(now, all[curIdx].leave) : 0;
      late = Math.max(0, leaveAt + eta.minutes - until);
    } else if (until < 0) {
      late = -until;
    }
  }
  return {
    current: curIdx >= 0 ? all[curIdx] : null,
    here,
    next,
    distance,
    eta,
    until,
    late,
    done: all.length > 0 && !next && (curIdx < 0 || now >= all[all.length - 1].leave),
  };
}

export function distanceText(m: number): string {
  return m < 1000 ? `${Math.round(m / 10) * 10} m` : `${(m / 1000).toFixed(m < 10_000 ? 1 : 0)} km`;
}

export function clockText(iso: string): string {
  const [h, m] = iso.slice(11, 16).split(":").map(Number);
  return `${((h + 11) % 12) + 1}:${String(m).padStart(2, "0")} ${h < 12 ? "am" : "pm"}`;
}

/** Nearby places from the guide's answer, nearest first, with how far each is. */
export function nearbyFrom(a: GuideAnswer, where: Where): { place: Place; metres: number }[] {
  return (a.emergency_places ?? [])
    .map((place) => ({ place, metres: metres(where, place) }))
    .sort((x, y) => x.metres - y.metres);
}

export const mapsLink = (p: { lat: number; lng: number; name?: string }) =>
  `https://www.google.com/maps/dir/?api=1&destination=${p.lat},${p.lng}`;
