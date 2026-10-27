import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { KathaPlayer } from "@/components/KathaPlayer";
import { KathaView } from "@/components/KathaView";

// Sample URLs only; nothing is fetched (jsdom does not load media).
const AUDIO = [
  { chapter: 2, url: "https://example.test/katha/ch2.mp3", voice: "en-IN-Sample", characters: 900 },
  { chapter: 1, url: "https://example.test/katha/ch1.mp3", voice: "en-IN-Sample", characters: 1000 },
];

const store = new Map<string, string>();
let play: ReturnType<typeof vi.fn>;

beforeEach(() => {
  store.clear();
  vi.stubGlobal("localStorage", { getItem: (k: string) => store.get(k) ?? null, setItem: (k: string, v: string) => void store.set(k, v), removeItem: (k: string) => void store.delete(k) });
  // jsdom has no media playback: play() resolves and fires "play", pause() fires "pause".
  play = vi.fn(function (this: HTMLMediaElement) {
    Object.defineProperty(this, "paused", { value: false, configurable: true });
    this.dispatchEvent(new Event("play"));
    return Promise.resolve();
  });
  vi.spyOn(HTMLMediaElement.prototype, "play").mockImplementation(play as unknown as () => Promise<void>);
  vi.spyOn(HTMLMediaElement.prototype, "pause").mockImplementation(function (this: HTMLMediaElement) {
    Object.defineProperty(this, "paused", { value: true, configurable: true });
    this.dispatchEvent(new Event("pause"));
  });
});
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

const media = () => document.querySelector("audio")!;

describe("Katha audio player", () => {
  it("never plays by itself, loads nothing until Play, and starts at chapter 1", () => {
    render(<KathaPlayer audio={AUDIO} />);
    expect(play).not.toHaveBeenCalled();
    expect(media().getAttribute("preload")).toBe("none");
    expect(media().getAttribute("src")).toBe(AUDIO[1].url);
    expect(screen.getByText("Part 1 of 2")).toBeTruthy();
  });

  it("plays and pauses on the one button", () => {
    render(<KathaPlayer audio={AUDIO} />);
    fireEvent.click(screen.getByRole("button", { name: "Play the Katha" }));
    expect(play).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByRole("button", { name: "Pause the Katha" }));
    expect(screen.getByRole("button", { name: "Play the Katha" })).toBeTruthy();
  });

  it("sets the speed, and goes on to the next chapter when one ends", async () => {
    render(<KathaPlayer audio={AUDIO} />);
    fireEvent.change(screen.getByRole("combobox"), { target: { value: "1.25" } });
    expect(media().playbackRate).toBe(1.25);
    fireEvent.click(screen.getByRole("button", { name: "Play the Katha" }));
    await act(async () => void media().dispatchEvent(new Event("ended")));
    expect(media().getAttribute("src")).toBe(AUDIO[0].url);
    expect(play).toHaveBeenCalledTimes(2);
  });

  it("shows nothing for a story that was not read aloud", () => {
    const { container } = render(<KathaPlayer audio={[]} />);
    expect(container.innerHTML).toBe("");
  });
});

describe("Katha length (QA #113)", () => {
  it("asks for no story until a length is picked, then remembers it", async () => {
    render(<KathaView req={{ subject_kind: "place", subject: "Mysore Palace" }} />);
    expect(screen.getByText("Pick a length to hear the story.")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "2 Minutes" }));
    expect(store.get("ty.katha.length")).toBe("2");
  });
});
