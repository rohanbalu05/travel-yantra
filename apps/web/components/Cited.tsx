import type { Citation } from "@/lib/contracts";
import { citedParts } from "@/lib/guide";

/** Text with [n] markers turned into links to source n in the matching <Sources id={id}>. */
export function Cited({ text, id, count }: { text: string; id: string; count: number }) {
  return (
    <>
      {citedParts(text).map((p, i) =>
        "text" in p ? (
          <span key={i}>{p.text}</span>
        ) : p.n >= 1 && p.n <= count ? (
          <a key={i} className="cite" href={`#${id}-${p.n}`} aria-label={`Source ${p.n}`}>[{p.n}]</a>
        ) : null, // a marker with no matching source is dropped rather than shown broken
      )}
    </>
  );
}

/** Numbered sources; each is the target of the [n] markers in <Cited>. */
export function Sources({ id, items }: { id: string; items: Citation[] }) {
  if (!items.length) return null;
  return (
    <div className="srcs">
      <small>Sources</small>
      <ol>
        {items.map((c, i) => (
          <li key={i} id={`${id}-${i + 1}`}>
            {c.url ? <a href={c.url} target="_blank" rel="noopener noreferrer">{c.title}</a> : c.title}
          </li>
        ))}
      </ol>
    </div>
  );
}

/** A source string from KathaStory.sources: a URL becomes a link titled by its host and last path part. */
export function citationFrom(source: string): Citation {
  try {
    const u = new URL(source);
    const last = decodeURIComponent(u.pathname.split("/").filter(Boolean).at(-1) ?? "").replaceAll("_", " ");
    return { title: last ? `${last} (${u.hostname.replace(/^www\./, "")})` : u.hostname, url: source };
  } catch {
    return { title: source, url: null };
  }
}
