// TY6's file (agreed with TY4): the pure helpers behind /trip/live/.
import { describe, expect, it } from "vitest";
import { addMinutes, distanceText, clockText, metres, minutesBetween, roughMinutes, slots, status, todayIndex } from "@/app/trip/live/live";
import type { DayPlan, Place } from "@/lib/contracts";
import { GOA_ITINERARY } from "@/lib/mockPlan";

const place = (id: string, lat: number, lng: number, visit = 60): Place => ({
  id, name: id, lat, lng, category: "sight", typical_visit_minutes: visit, source: "sample",
});
// Old Goa: Bom Jesus and Se Cathedral are ~300 m apart; Mangueshi is ~12 km away.
const BOM = place("bom", 15.5009, 73.9116, 45);
const SE = place("se", 15.5036, 73.9123, 40);
const MANG = place("mang", 15.4436, 73.9916, 60);
const DAY: DayPlan = {
  date: "2026-12-12",
  stops: [BOM, SE, MANG],
  schedule: [
    { place_id: "bom", arrive: "2026-12-12T09:00:00", start: "2026-12-12T09:00:00", leave: "2026-12-12T09:45:00" },
    { place_id: "se", arrive: "2026-12-12T09:50:00", start: "2026-12-12T09:50:00", leave: "2026-12-12T10:30:00" },
    { place_id: "mang", arrive: "2026-12-12T11:00:00", start: "2026-12-12T11:00:00", leave: "2026-12-12T12:00:00" },
  ],
};

describe("time helpers", () => {
  it("adds minutes across the hour and midnight", () => {
    expect(addMinutes("2026-12-12T09:50", 15)).toBe("2026-12-12T10:05");
    expect(addMinutes("2026-12-12T23:50:00", 20)).toBe("2026-12-13T00:10");
    expect(minutesBetween("2026-12-12T09:00", "2026-12-12T10:30:00")).toBe(90);
  });
  it("formats clock and distance", () => {
    expect(clockText("2026-12-12T09:05")).toBe("9:05 am");
    expect(clockText("2026-12-12T12:30")).toBe("12:30 pm");
    expect(clockText("2026-12-12T00:15")).toBe("12:15 am");
    expect(distanceText(304)).toBe("300 m");
    expect(distanceText(12_400)).toBe("12 km");
    expect(distanceText(2_340)).toBe("2.3 km");
  });
  it("measures distance and a rough time", () => {
    expect(metres(BOM, SE)).toBeGreaterThan(250);
    expect(metres(BOM, SE)).toBeLessThan(400);
    expect(roughMinutes(300)).toEqual({ minutes: 4, by: "walk" });
    expect(roughMinutes(12_000).by).toBe("road");
  });
});

describe("today's plan", () => {
  it("finds today's day, or none", () => {
    const first = GOA_ITINERARY.days[0].date;
    expect(todayIndex(GOA_ITINERARY, `${first}T10:00`)).toBe(0);
    expect(todayIndex(GOA_ITINERARY, "2020-01-01T10:00")).toBe(-1);
  });

  it("uses the schedule when there is one", () => {
    const s = slots(DAY);
    expect(s.map((x) => [x.arrive, x.leave, x.planned])).toEqual([
      ["2026-12-12T09:00", "2026-12-12T09:45", true],
      ["2026-12-12T09:50", "2026-12-12T10:30", true],
      ["2026-12-12T11:00", "2026-12-12T12:00", true],
    ]);
  });

  it("works times out from visit lengths when there is no schedule", () => {
    const s = slots({ date: "2026-12-12", stops: [BOM, SE] });
    expect(s[0]).toMatchObject({ arrive: "2026-12-12T09:00", leave: "2026-12-12T09:45", planned: false });
    expect(s[1]).toMatchObject({ arrive: "2026-12-12T09:45", leave: "2026-12-12T10:25", planned: false });
  });

  it("goes by the clock without a location", () => {
    const st = status(DAY, "2026-12-12T09:20", null);
    expect(st.current?.place.id).toBe("bom");
    expect(st.here).toBe(false);
    expect(st.next?.place.id).toBe("se");
    expect(st.until).toBe(30);
    expect(st.distance).toBeNull();
    expect(st.late).toBeNull(); // can't tell before the time passes
  });

  it("says you're late by the clock once the next stop's time has passed", () => {
    const st = status(DAY, "2026-12-12T10:00", null);
    expect(st.current?.place.id).toBe("se");
    expect(status(DAY, "2026-12-12T10:40", null)).toMatchObject({ current: null, late: null });
    expect(status(DAY, "2026-12-12T11:10", { lat: SE.lat, lng: SE.lng }).late).toBeGreaterThan(10);
  });

  it("goes by your location when you are at a stop", () => {
    // At Bom Jesus after its time: you're still here, and Mangueshi is far.
    const st = status(DAY, "2026-12-12T10:20", { lat: BOM.lat, lng: BOM.lng, accuracy: 20 });
    expect(st.here).toBe(true);
    expect(st.current?.place.id).toBe("bom");
    expect(st.next?.place.id).toBe("se");
    expect(st.eta?.by).toBe("walk");
    expect(st.late).toBeGreaterThan(30);
  });

  it("is done after the last stop", () => {
    expect(status(DAY, "2026-12-12T13:00", null)).toMatchObject({ next: null, done: true });
  });
});
