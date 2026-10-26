import { AppShell } from "@/components/AppShell";
import { SCREENS } from "@/lib/screens";

/** Stand-in for screens that come with their own cards (TY4-02 to TY4-08). */
export function Placeholder({ slug }: { slug: string }) {
  const s = SCREENS.find((x) => x.slug === slug);
  if (!s) throw new Error(`Unknown screen: ${slug}`);
  return (
    <AppShell>
      <div className="stack">
        <h1 className="page-title">{s.title}</h1>
        <p className="page-sub">{s.blurb}</p>
        <div className="note note-info">This screen is built in a later card.</div>
      </div>
    </AppShell>
  );
}
