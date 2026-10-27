import { layoutPins, osmLink, type Pin } from "@/lib/map";

/**
 * The day's stops as numbered pins, placed by their coordinates, with the
 * route between them. No map tiles (no key, no cost): each pin opens
 * OpenStreetMap at that spot.
 */
export function StopsMap({ pins, caption }: { pins: Pin[]; caption: string }) {
  const placed = layoutPins(pins);
  if (!placed.length) return null;
  const route = placed.filter((p) => p.kind === "stop").map((p) => `${p.x},${p.y}`).join(" ");
  return (
    <figure className="smap">
      <div className="smap-box" role="img" aria-label={caption}>
        <svg viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">
          <defs>
            <pattern id="smap-grid" width="10" height="10" patternUnits="userSpaceOnUse"><path d="M10 0H0V10" fill="none" stroke="#D8CFBF" strokeWidth=".3" /></pattern>
          </defs>
          <rect width="100" height="100" fill="url(#smap-grid)" />
          {route.includes(" ") && <polyline points={route} fill="none" stroke="#13212B" strokeWidth=".6" strokeDasharray="1.6 1.6" vectorEffect="non-scaling-stroke" />}
        </svg>
        {placed.map((p) => (
          <a key={p.id} className={`smap-pin ${p.kind}`} style={{ left: `${p.x}%`, top: `${p.y}%` }} href={osmLink(p.lat, p.lng)} target="_blank" rel="noopener noreferrer" title={`${p.name} on OpenStreetMap`} aria-label={`${p.name} on OpenStreetMap`}>
            {p.label}
          </a>
        ))}
      </div>
      <figcaption className="map-cap"><span>{caption}</span><span>Pins open OpenStreetMap</span></figcaption>
    </figure>
  );
}
