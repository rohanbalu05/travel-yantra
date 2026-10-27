/** OpenStreetMap page centred on a point (no key, no cost). */
export const osmLink = (lat: number, lng: number, zoom = 17) =>
  `https://www.openstreetmap.org/?mlat=${lat.toFixed(5)}&mlon=${lng.toFixed(5)}#map=${zoom}/${lat.toFixed(5)}/${lng.toFixed(5)}`;

export type Pin = { id: string; label: string; name: string; lat: number; lng: number; kind: "stop" | "stay" };

/**
 * Places pins inside a box, as percentages, keeping the map's shape true to
 * the ground (a degree of longitude is shorter than one of latitude away from
 * the equator). One pin, or pins in the same spot, sit in the middle.
 */
export function layoutPins(pins: Pin[], pad = 0.12): (Pin & { x: number; y: number })[] {
  if (!pins.length) return [];
  const lats = pins.map((p) => p.lat);
  const lngs = pins.map((p) => p.lng);
  const midLat = (Math.min(...lats) + Math.max(...lats)) / 2;
  const k = Math.cos((midLat * Math.PI) / 180);
  const xs = lngs.map((l) => l * k);
  const [x0, x1, y0, y1] = [Math.min(...xs), Math.max(...xs), Math.min(...lats), Math.max(...lats)];
  const span = Math.max(x1 - x0, y1 - y0) || 1;
  const cx = (x0 + x1) / 2;
  const cy = (y0 + y1) / 2;
  const scale = (1 - 2 * pad) / span;
  return pins.map((p, i) => ({
    ...p,
    x: 50 + (xs[i] - cx) * scale * 100,
    y: 50 - (p.lat - cy) * scale * 100, // north is up
  }));
}
