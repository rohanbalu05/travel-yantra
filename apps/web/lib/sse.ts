import type { PlanEvent } from "@/lib/contracts";

/**
 * Reads a `text/event-stream` body and yields each `data:` frame as JSON.
 * Comment lines (`: ping`) and other fields are skipped; multi-line data is
 * joined with newlines, as the SSE spec says. A frame that is not JSON throws
 * a SyntaxError, which the pages show as a failed plan with "Try again".
 */
export async function* parseSSE(body: ReadableStream<Uint8Array>): AsyncGenerator<PlanEvent> {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buf = "";
  let data: string[] = [];
  try {
    for (;;) {
      const { value, done } = await reader.read();
      buf += done ? decoder.decode() : decoder.decode(value, { stream: true });
      const lines = buf.split(/\r\n|\r|\n/);
      buf = done ? "" : (lines.pop() ?? "");
      for (const line of lines) {
        if (line === "") {
          if (data.length) yield JSON.parse(data.join("\n")) as PlanEvent;
          data = [];
        } else if (line.startsWith("data:")) {
          data.push(line.slice(5).replace(/^ /, ""));
        }
      }
      if (done) {
        if (data.length) yield JSON.parse(data.join("\n")) as PlanEvent;
        return;
      }
    }
  } finally {
    reader.releaseLock();
  }
}
