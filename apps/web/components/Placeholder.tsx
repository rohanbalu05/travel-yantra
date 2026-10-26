import { SCREENS } from "@/lib/screens";

export function Placeholder({ slug }: { slug: string }) {
  const s = SCREENS.find((x) => x.slug === slug);
  if (!s) throw new Error(`Unknown screen: ${slug}`);
  return (
    <>
      <p className="eyebrow">{s.group}</p>
      <h1>{s.title}</h1>
      <p>{s.blurb}</p>
      <div className="placeholder">Placeholder content. This screen is built in a later card.</div>
    </>
  );
}
