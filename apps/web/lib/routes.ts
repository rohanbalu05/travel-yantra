import { API_BASE_URL } from "@/lib/api";
import { withAuth } from "@/lib/account";
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
  /** The classes this train has (TY3); the card's class is one of them. */
  classes?: string[];
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
  return withAuth((headers) => apiJSON<CompareResponse>("/routes/compare", { body: req, signal, base, headers }));
}

/**
 * GET /routes/irctc-card (TY3). `train` and `after` (HH:MM) name the plan's train; with no class,
 * TY3 uses the train's own default and lists the others in `classes`.
 */
export async function irctcCard(p: { from: string; to: string; date: string; party: Party; travel_class?: string | null; train?: string | null; after?: string | null; travellers?: number }, signal?: AbortSignal, base = API_BASE_URL): Promise<IrctcCard> {
  if (!base) {
    await wait(200);
    return sampleIrctcCard({ ...p, travel_class: p.travel_class ?? undefined });
  }
  return withAuth((headers) => apiJSON<IrctcCard>(`/routes/irctc-card?${query(p)}`, { signal, base, headers }));
}

export async function pnrStatus(pnr: string, signal?: AbortSignal, base = API_BASE_URL): Promise<PnrStatus> {
  if (!base) {
    await wait(200);
    return samplePnr(pnr);
  }
  return withAuth((headers) => apiJSON<PnrStatus>(`/routes/pnr-mock?${query({ pnr })}`, { signal, base, headers }));
}

/** The sample party whose names TY3 fills into the IRCTC card (no names travel in the URL). */
export const partyFor = (it: Itinerary): Party => (it.request.destinations.some((d) => /mysu/i.test(d)) ? "mysuru_weekend" : "goa_family");
