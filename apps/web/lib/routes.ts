import { API_BASE_URL } from "@/lib/api";
import type { CompareRequest, CompareResponse, Itinerary } from "@/lib/contracts";
import { apiJSON, query } from "@/lib/http";
import { sampleCompare, sampleIrctcCard, samplePnr } from "@/lib/samples/routes";

// TY3's /routes/irctc-card and /routes/pnr-mock shapes (apps/api/routes/irctc.py); not in contracts.
export type StationRef = { code: string; name: string };
export type IrctcCard = {
  train: { number: string; name: string };
  from: StationRef;
  to: StationRef;
  date: string;
  date_irctc: string;
  departs: string;
  arrives: string;
  arrives_day_offset: number;
  travel_class: string;
  quota: string;
  passengers: { name: string; age: number; gender: string; berth: string }[];
  fare_estimate_inr: number;
  copy_text: string;
  booking_url: string;
  sample: boolean;
  notes: string[];
};
export type PnrStatus = {
  pnr: string;
  train: string;
  class: string;
  date: string;
  from: StationRef;
  to: StationRef;
  passengers: { name: string; status: string }[];
  timeline: { at: string; status: string; note: string }[];
  current_status: string;
  chart_prepared: boolean;
  sample: boolean;
};

export type Party = "goa_family" | "mysuru_weekend";
export const SAMPLE_PNRS = ["4521683907", "4521690144", "1234567890"];

const wait = (ms: number) => new Promise((r) => setTimeout(r, ms));

/** POST /routes/compare (TY3). With no API configured, ranks the plan's own transport options. */
export async function compareRoutes(req: CompareRequest, it: Itinerary, signal?: AbortSignal, base = API_BASE_URL): Promise<CompareResponse> {
  if (!base) {
    await wait(250);
    return sampleCompare(req, it);
  }
  return apiJSON<CompareResponse>("/routes/compare", { body: req, signal, base });
}

export async function irctcCard(p: { from: string; to: string; date: string; party: Party; travel_class?: string }, signal?: AbortSignal, base = API_BASE_URL): Promise<IrctcCard> {
  if (!base) {
    await wait(200);
    return sampleIrctcCard(p);
  }
  return apiJSON<IrctcCard>(`/routes/irctc-card?${query({ ...p, travel_class: p.travel_class ?? "3A" })}`, { signal, base });
}

export async function pnrStatus(pnr: string, signal?: AbortSignal, base = API_BASE_URL): Promise<PnrStatus> {
  if (!base) {
    await wait(200);
    return samplePnr(pnr);
  }
  return apiJSON<PnrStatus>(`/routes/pnr-mock?${query({ pnr })}`, { signal, base });
}

/** The sample party whose names TY3 fills into the IRCTC card (no names travel in the URL). */
export const partyFor = (it: Itinerary): Party => (it.request.destinations.some((d) => /mysu/i.test(d)) ? "mysuru_weekend" : "goa_family");
