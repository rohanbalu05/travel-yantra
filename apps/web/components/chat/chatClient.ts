import { withAuth } from "@/lib/account";
import { API_BASE_URL } from "@/lib/api";
import type { Itinerary, Lang } from "@/lib/contracts";
import { ApiError } from "@/lib/http";
import { parseSSE } from "@/lib/sse";

/** One Server-Sent Event of POST /chat (TY5's ty_chat.models.ChatEvent). */
export type ChatEvent = {
  type: "heard" | "note" | "text" | "chips" | "plan" | "audio" | "done" | "error";
  text?: string;
  chips?: string[];
  url?: string;
  plan_id?: string;
  share_token?: string;
  itinerary?: Itinerary;
  plan_changed?: boolean;
  lang?: Lang;
};

export type ChatBody = {
  text: string;
  lang: Lang;
  plan_id?: string | null;
  share_token?: string | null;
  location?: { lat: number; lng: number };
};

export const chatAvailable = () => !!API_BASE_URL;

/** POST /chat with this browser's identity (X-Client-Id, plus the Google token when signed in); calls
 * onEvent for each event as it arrives. Throws ApiError for an HTTP error, as the other API calls do. */
export async function streamChat(body: ChatBody, onEvent: (e: ChatEvent) => void, signal?: AbortSignal): Promise<void> {
  await withAuth(async (headers) => {
    const r = await fetch(`${API_BASE_URL.replace(/\/$/, "")}/chat`, {
      method: "POST",
      headers: { ...headers, "Content-Type": "application/json", Accept: "text/event-stream" },
      body: JSON.stringify(body),
      signal,
    });
    if (!r.ok || !r.body) {
      let detail = `HTTP ${r.status}`;
      try {
        const j = await r.json();
        if (typeof j?.detail === "string") detail = j.detail;
      } catch {
        /* not JSON */
      }
      throw new ApiError(detail, r.status);
    }
    for await (const e of parseSSE(r.body)) onEvent(e as unknown as ChatEvent);
  });
}
