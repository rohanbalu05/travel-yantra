import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Cited, Sources, citationFrom } from "@/components/Cited";
import { askGuide, citedParts, getKatha } from "@/lib/guide";
import { sampleKatha } from "@/lib/samples/guide";

function fakeFetch(status: number, body: unknown) {
  const fn = vi.fn(async () => new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } }));
  vi.stubGlobal("fetch", fn);
  return fn;
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("cited text", () => {
  it("splits [n] markers out of the text", () => {
    expect(citedParts("Built in 1605 [1]. Holds relics [1][2].")).toEqual([
      { text: "Built in 1605 " }, { n: 1 }, { text: ". Holds relics " }, { n: 1 }, { n: 2 }, { text: "." },
    ]);
  });

  it("links each marker to its numbered source and drops markers with no source", () => {
    render(
      <>
        <p><Cited text="A [1] B [3]" id="t" count={1} /></p>
        <Sources id="t" items={[{ title: "Basilica (Wikipedia)", url: "https://en.wikipedia.org/wiki/Basilica_of_Bom_Jesus" }]} />
      </>,
    );
    expect(screen.getByRole("link", { name: "Source 1" }).getAttribute("href")).toBe("#t-1");
    expect(screen.queryByRole("link", { name: "Source 3" })).toBeNull();
    expect(document.getElementById("t-1")?.textContent).toBe("Basilica (Wikipedia)");
  });

  it("links only http(s) sources", () => {
    render(<Sources id="u" items={[{ title: "Bad", url: "javascript:alert(1)" }, { title: "Good", url: "https://example.org/a" }]} />);
    expect(screen.queryByRole("link", { name: "Bad" })).toBeNull();
    expect(screen.getByRole("link", { name: "Good" }).getAttribute("href")).toBe("https://example.org/a");
  });

  it("turns a Katha source URL into a readable title", () => {
    expect(citationFrom("https://en.wikipedia.org/wiki/Basilica_of_Bom_Jesus")).toEqual({ title: "Basilica of Bom Jesus (en.wikipedia.org)", url: "https://en.wikipedia.org/wiki/Basilica_of_Bom_Jesus" });
    expect(citationFrom("Gazetteer of Goa (State archive)")).toEqual({ title: "Gazetteer of Goa (State archive)", url: null });
  });
});

describe("askGuide", () => {
  it("POSTs the question to /guide/ask", async () => {
    const fn = fakeFetch(200, { text: "ok", citations: [], emergency_places: [], lang: "en" });
    await askGuide({ question: "Why?", lang: "en" }, undefined, "http://api.test");
    const [url, init] = fn.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe("http://api.test/guide/ask");
    expect(JSON.parse(init.body as string)).toEqual({ question: "Why?", lang: "en" });
  });

  it("surfaces TY2's 503 reason as a retryable error", async () => {
    fakeFetch(503, { detail: "The guide is offline right now." });
    await expect(askGuide({ question: "x" }, undefined, "http://api.test")).rejects.toMatchObject({ message: "The guide is offline right now.", retryable: true });
  });
});

describe("getKatha", () => {
  it("falls back to the sample story while the route is missing on the API", async () => {
    fakeFetch(404, { detail: "Not Found" });
    const s = await getKatha({ subject_kind: "city", subject: "Mysuru", length_min: 2, lang: "en" }, undefined, "http://api.test");
    expect(s.sample).toBe(true);
    expect(s.segments?.map((x) => x.label)).toEqual(["history", "legend"]);
  });

  it("shows TY2's own 404 instead of a sample", async () => {
    fakeFetch(404, { detail: "No story for that place yet." });
    await expect(getKatha({ subject_kind: "place", subject: "Nowhere", length_min: 5, lang: "en" }, undefined, "http://api.test")).rejects.toMatchObject({ message: "No story for that place yet.", retryable: false });
  });

  it("sends a day's stops in order as places", async () => {
    const fn = fakeFetch(200, { subject_kind: "day", subject: "Day 1, Goa", length_min: 5, text: "", segments: [], sources: [] });
    await getKatha({ subject_kind: "day", subject: "Day 1, Goa", length_min: 5, lang: "en", places: ["Basilica of Bom Jesus", "Se Cathedral"] }, undefined, "http://api.test");
    const body = JSON.parse((fn.mock.calls[0] as unknown as [string, RequestInit])[1].body as string);
    expect(body.places).toEqual(["Basilica of Bom Jesus", "Se Cathedral"]);
    // Through withAuth like every API call: the browser's id (and the Google token when signed in).
    const headers = (fn.mock.calls[0] as unknown as [string, RequestInit])[1].headers as Record<string, string>;
    expect(headers["X-Client-Id"]).toBeTruthy();
  });
});

describe("sample stories", () => {
  it("grow with the length switch and label legends", () => {
    const short = sampleKatha("place", "Basilica of Bom Jesus", 2);
    const long = sampleKatha("place", "Basilica of Bom Jesus", 10);
    expect(short.segments).toHaveLength(2);
    expect(long.segments!.length).toBeGreaterThan(short.segments!.length);
    expect(long.segments!.filter((s) => s.label === "legend").every((s) => s.text.startsWith("As the story goes"))).toBe(true);
  });

  it("renumbers sources when a day joins several places, so every marker has its source", () => {
    const d = sampleKatha("day", "Day 1", 10, "en", ["Goa", "Basilica of Bom Jesus"]);
    const markers = d.segments!.flatMap((s) => [...s.text.matchAll(/\[(\d+)\]/g)].map((m) => Number(m[1])));
    expect(markers.length).toBeGreaterThan(0);
    expect(markers.every((n) => n >= 1 && n <= d.sources!.length)).toBe(true);
    expect(new Set(d.sources).size).toBe(d.sources!.length);
    expect(d.segments![0].text).toContain("Portuguese"); // Goa's story first, in the order given
  });

  it("does not invent a story for an unknown subject", () => {
    expect(sampleKatha("place", "Somewhere Else", 5).segments).toEqual([]);
  });
});
