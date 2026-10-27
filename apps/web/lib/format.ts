import type { Mode } from "@/lib/contracts";

const inrFmt = new Intl.NumberFormat("en-IN", { maximumFractionDigits: 0 });

/** ₹57,400 */
export const inr = (n: number) => `₹${inrFmt.format(Math.round(n))}`;

/** 840 → "14 h", 75 → "1 h 15 m", 20 → "20 m" */
export function duration(minutes: number): string {
  const h = Math.floor(minutes / 60);
  const m = Math.round(minutes % 60);
  if (!h) return `${m} m`;
  return m ? `${h} h ${m} m` : `${h} h`;
}

// Dates from the API are local "YYYY-MM-DD" or "YYYY-MM-DDTHH:MM:SS" with no zone; read them as written.
function parts(iso: string) {
  const [y, mo, d] = iso.slice(0, 10).split("-").map(Number);
  return new Date(Date.UTC(y, mo - 1, d));
}

/** "2026-12-11" → "Fri 11 Dec" */
export const dayLabel = (iso: string) =>
  parts(iso).toLocaleDateString("en-IN", { weekday: "short", day: "numeric", month: "short", timeZone: "UTC" });

/** "2026-12-11" → "Fri" */
export const weekday = (iso: string) => parts(iso).toLocaleDateString("en-IN", { weekday: "short", timeZone: "UTC" });

/** "2026-12-11T21:00:00" → "21:00" */
export const clock = (iso: string) => iso.slice(11, 16);

/** Whole days between two "YYYY-MM-DD" dates. */
export const daysBetween = (a: string, b: string) => Math.round((parts(b).getTime() - parts(a).getTime()) / 86_400_000);

export const MODE_NAME: Record<Mode, string> = { rail: "Rail", air: "Air", road: "Road" };

export const MODE_ICON: Record<Mode, string> = {
  rail: "M6 3h12v13H6zM6 10h12M8 16l-2 4M16 16l2 4M7 19h10",
  air: "M10.5 21l1.5-6-7-2V11l7 1V6.5a1.5 1.5 0 0 1 3 0V12l7-1v2l-7 2 1.5 6Z",
  road: "M5 16V12l2-5h10l2 5v4M3 16h18v2H3z",
};
