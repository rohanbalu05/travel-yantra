import type { CompareRequest, CompareResponse, Itinerary } from "@/lib/contracts";
import type { IrctcCard, Party, PnrStatus } from "@/lib/routes";

// Mock-mode stand-ins for TY3's routes endpoints. Sample persona and sample trains only.

const PEOPLE: Record<Party, [string, number, string, string][]> = {
  goa_family: [["Arjun Rao", 34, "Male", "Side lower"], ["Venkatesh", 64, "Male", "Lower"], ["Shobha", 58, "Female", "Lower"], ["Meera", 22, "Female", "Middle"]],
  mysuru_weekend: [["Arjun Rao", 34, "Male", "Window"], ["Meera", 22, "Female", "Aisle"]],
};

/** The plan's own transport options, ranked cheapest first, in compare's shape. */
export function sampleCompare(req: CompareRequest, it: Itinerary): CompareResponse {
  const opts = [...(it.transport ?? [])].sort((a, b) => a.total_cost_inr - b.total_cost_inr);
  return {
    origin: { name: req.origin, lat: 12.9716, lng: 77.5946 },
    destination: { name: req.destination, lat: 15.4909, lng: 73.8278 },
    date: req.date ?? it.request.start_date,
    rank_by: req.rank_by ?? "balanced",
    options: opts.map((o, i) => ({ id: `${o.mode}-sample${i}`, rank: i + 1, changes: o.legs.length - 1, score: 1 - i * 0.1, sources: ["sample"], option: o })),
    unavailable: [],
    notes: ["Sample options from the plan; live comparison needs the API."],
  };
}

export function sampleIrctcCard(p: { from: string; to: string; date: string; party: Party; travel_class?: string }): IrctcCard {
  const [y, m, d] = p.date.split("-");
  const cls = p.travel_class ?? "3A";
  const people = PEOPLE[p.party];
  const passengers = people.map(([name, age, gender, berth]) => ({ name, age, gender, berth }));
  return {
    train: { number: "90001", name: "Sample Goa Express" },
    classes: ["SL", "3A", "2A"],
    from: { code: "SBC", name: "KSR Bengaluru City Jn" },
    to: { code: "MAO", name: "Madgaon Jn" },
    date: p.date,
    date_irctc: `${d}-${m}-${y}`,
    departs: "21:00",
    arrives: "11:00",
    arrives_day_offset: 1,
    travel_class: cls,
    quota: "General",
    passengers,
    fare_estimate_inr: 1150 * people.length,
    copy_text: [
      "From: SBC (KSR Bengaluru City Jn)",
      "To: MAO (Madgaon Jn)",
      `Date: ${d}-${m}-${y}`,
      `Class: ${cls}`,
      "Quota: General",
      "Train: 90001 Sample Goa Express, departs 21:00",
      "Passengers:",
      ...passengers.map((x, i) => `${i + 1}. ${x.name}, ${x.age}, ${x.gender}, ${x.berth}`),
    ].join("\n"),
    booking_url: "https://www.irctc.co.in/nget/train-search",
    sample: true,
    notes: ["Sample train for the prototype."],
  };
}

export function samplePnr(pnr: string): PnrStatus {
  const waiting = pnr === "4521690144";
  const at = (day: string, t: string) => `2026-12-${day}T${t}:00+05:30`;
  return {
    pnr,
    train: waiting ? "90010 Sample Goa Express (return)" : "90001 Sample Goa Express",
    class: "3A",
    date: waiting ? "2026-12-14" : "2026-12-11",
    from: waiting ? { code: "MAO", name: "Madgaon Jn" } : { code: "SBC", name: "KSR Bengaluru City Jn" },
    to: waiting ? { code: "SBC", name: "KSR Bengaluru City Jn" } : { code: "MAO", name: "Madgaon Jn" },
    passengers: [{ name: "Arjun Rao", status: waiting ? "WL 7" : "CNF B2 34" }],
    timeline: waiting
      ? [
          { at: at("10", "09:00"), status: "WL 7", note: "Moved up overnight." },
          { at: at("05", "09:00"), status: "WL 12", note: "Cancellations ahead of you." },
          { at: at("01", "09:00"), status: "WL 19", note: "Booked on the waitlist." },
        ]
      : [{ at: at("01", "09:00"), status: "CNF B2 34", note: "Confirmed at booking." }],
    current_status: waiting ? "WL 7" : "CNF",
    chart_prepared: false,
    sample: true,
  };
}
