import { describe, expect, it } from "vitest";
import { parseSSE } from "@/lib/sse";

/** A body that delivers `text` in the given chunk sizes, to test frames split across reads. */
function body(chunks: string[]): ReadableStream<Uint8Array> {
  const enc = new TextEncoder();
  return new ReadableStream({
    start(ctl) {
      chunks.forEach((c) => ctl.enqueue(enc.encode(c)));
      ctl.close();
    },
  });
}

async function all(stream: ReadableStream<Uint8Array>) {
  const out = [];
  for await (const ev of parseSSE(stream)) out.push(ev);
  return out;
}

describe("parseSSE", () => {
  it("yields each data frame and skips ping comments", async () => {
    const evs = await all(body([': ping\n\ndata: {"stage":"intake","message":"a"}\n\n', ': ping\n\ndata: {"stage":"done","message":"b"}\n\n']));
    expect(evs.map((e) => e.stage)).toEqual(["intake", "done"]);
  });

  it("joins frames split across reads, including inside a UTF-8 character", async () => {
    const frame = 'data: {"stage":"planning","message":"₹4,800 by rail"}\n\n';
    const bytes = new TextEncoder().encode(frame);
    const cut = new TextEncoder().encode(frame.slice(0, frame.indexOf("₹"))).length + 1; // inside the 3-byte ₹
    const stream = new ReadableStream<Uint8Array>({
      start(ctl) {
        ctl.enqueue(bytes.slice(0, cut));
        ctl.enqueue(bytes.slice(cut));
        ctl.close();
      },
    });
    const evs = await all(stream);
    expect(evs).toHaveLength(1);
    expect(evs[0].message).toBe("₹4,800 by rail");
  });

  it("handles CRLF line endings and multi-line data", async () => {
    const evs = await all(body(['data: {"stage":"done",\r\ndata: "message":"ok"}\r\n\r\n']));
    expect(evs).toEqual([{ stage: "done", message: "ok" }]);
  });

  it("yields a last frame that has no closing blank line", async () => {
    const evs = await all(body(['data: {"stage":"error","message":"x"}']));
    expect(evs.map((e) => e.stage)).toEqual(["error"]);
  });
});
