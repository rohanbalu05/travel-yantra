import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.hoisted(() => {
  process.env.NEXT_PUBLIC_API_BASE_URL = "http://api.test";
});

import sample from "@/lib/samples/goa_family.json";
import { ChatPanel } from "./ChatPanel";
import { EMPTY, pieces, reduce } from "./chatState";
import { SPEECH_LANG } from "./speech";
import { CHAT_STRINGS } from "./strings";

const itinerary = (sample as { itinerary: unknown }).itinerary;

function sseResponse(events: object[]) {
  const body = events.map((e) => `: ping\n\ndata: ${JSON.stringify(e)}\n\n`).join("");
  return new Response(body, { status: 200, headers: { "Content-Type": "text/event-stream" } });
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("chat state", () => {
  it("replaces the working note with the reply and ends busy on done", () => {
    let s = reduce(EMPTY, { kind: "sent", text: "Plan Goa" });
    s = reduce(s, { kind: "event", event: { type: "note", text: "Working on your plan" } });
    expect(s.busy).toBe(true);
    s = reduce(s, { kind: "event", event: { type: "text", text: "Goa from Bengaluru" } });
    s = reduce(s, { kind: "event", event: { type: "chips", chips: ["share", "lighter day 2"] } });
    s = reduce(s, { kind: "event", event: { type: "done" } });
    expect(s.lines.map((l) => l.role)).toEqual(["user", "bot"]);
    expect(s.chips).toEqual(["share", "lighter day 2"]);
    expect(s.busy).toBe(false);
  });

  it("splits links out of a reply", () => {
    expect(pieces("[1] Fort https://maps.google.com/?q=15.5,73.9 ok")).toEqual([
      { text: "[1] Fort " },
      { text: "https://maps.google.com/?q=15.5,73.9", href: "https://maps.google.com/?q=15.5,73.9" },
      { text: " ok" },
    ]);
  });

  it("has every label in all six languages and a speech locale for each", () => {
    for (const entry of Object.values(CHAT_STRINGS)) expect(Object.keys(entry).sort()).toEqual(["bn", "en", "hi", "kn", "ta", "te"]);
    expect(Object.values(SPEECH_LANG)).toEqual(["en-IN", "hi-IN", "kn-IN", "ta-IN", "te-IN", "bn-IN"]);
  });
});

describe("ChatPanel", () => {
  it("streams a reply, fires onPlanChanged and shows chips", async () => {
    const fetch = vi.fn(async () =>
      sseResponse([
        { type: "note", text: "Working on your plan now" },
        { type: "plan", plan_id: "p1", share_token: "tok1", itinerary, plan_changed: true },
        { type: "text", text: "Goa from Bengaluru, 11 Dec to 14 Dec" },
        { type: "chips", chips: ["share", "lighter day 2"] },
        { type: "done", plan_id: "p1", plan_changed: true, lang: "hi" },
      ]),
    );
    vi.stubGlobal("fetch", fetch);
    const onPlanChanged = vi.fn();
    render(<ChatPanel planId="p0" lang="hi" onPlanChanged={onPlanChanged} />);
    const box = screen.getByRole("textbox");
    fireEvent.change(box, { target: { value: "lighter day 2" } });
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: CHAT_STRINGS.send.hi }));
    });
    await waitFor(() => expect(screen.getByText("Goa from Bengaluru, 11 Dec to 14 Dec")).toBeTruthy());
    const [url, init] = fetch.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe("http://api.test/chat");
    expect(JSON.parse(init.body as string)).toEqual({ text: "lighter day 2", lang: "hi", plan_id: "p0", share_token: null });
    expect((init.headers as Record<string, string>)["X-Client-Id"]).toBeTruthy();
    expect(onPlanChanged).toHaveBeenCalledWith({ plan_id: "p1", share_token: "tok1", itinerary });
    expect(screen.getByText(CHAT_STRINGS.updated.hi)).toBeTruthy();
    expect(screen.queryByText("Working on your plan now")).toBeNull();
    expect(screen.getByRole("button", { name: "lighter day 2" })).toBeTruthy();
  });

  it("says what failed when the API refuses", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ detail: "rate limited" }), { status: 429 })));
    render(<ChatPanel planId={null} lang="en" />);
    fireEvent.change(screen.getByRole("textbox"), { target: { value: "hi" } });
    await act(async () => {
      fireEvent.submit(screen.getByRole("textbox").closest("form")!);
    });
    await waitFor(() => expect(screen.getByText(/Something went wrong.*rate limited/)).toBeTruthy());
  });

  it("explains the fallback when the browser has no speech recognition", () => {
    render(<ChatPanel planId={null} lang="ta" />);
    fireEvent.click(screen.getByRole("button", { name: CHAT_STRINGS.speak.ta }));
    expect(screen.getByRole("status").textContent).toBe(CHAT_STRINGS.noVoice.ta);
  });

  it("hides the mic when voice is off", () => {
    render(<ChatPanel planId={null} lang="en" voice={false} />);
    expect(screen.queryByRole("button", { name: CHAT_STRINGS.speak.en })).toBeNull();
  });

  it("listens in the page's language and sends what it heard", async () => {
    const started: string[] = [];
    class FakeRecognition {
      lang = "";
      interimResults = false;
      maxAlternatives = 1;
      continuous = false;
      onresult: ((e: unknown) => void) | null = null;
      onerror: ((e: unknown) => void) | null = null;
      onend: (() => void) | null = null;
      start() {
        started.push(this.lang);
        setTimeout(() => {
          this.onresult?.({ results: [{ 0: { transcript: "गोवा की यात्रा" }, isFinal: true }] });
          this.onend?.();
        }, 0);
      }
      stop() {}
      abort() {}
    }
    vi.stubGlobal("webkitSpeechRecognition", FakeRecognition);
    const fetch = vi.fn(async () => sseResponse([{ type: "text", text: "ठीक है" }, { type: "done" }]));
    vi.stubGlobal("fetch", fetch);
    render(<ChatPanel planId={null} lang="hi" />);
    await act(async () => {}); // the mic check runs after mount
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: CHAT_STRINGS.speak.hi }));
    });
    await waitFor(() => expect(screen.getByText("ठीक है")).toBeTruthy());
    expect(started).toEqual(["hi-IN"]);
    const init = (fetch.mock.calls[0] as unknown as [string, RequestInit])[1];
    expect(JSON.parse(init.body as string).text).toBe("गोवा की यात्रा");
  });
});
