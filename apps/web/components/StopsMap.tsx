"use client";

import "leaflet/dist/leaflet.css";
import { useEffect, useRef, useState } from "react";
import { useI18n } from "@/lib/i18n";
import { OSM_ATTRIBUTION, OSM_TILES, layoutPins, osmLink, pinHtml, type Pin } from "@/lib/map";

/**
 * The day's stops as numbered pins on OpenStreetMap tiles (Leaflet; no key,
 * no cost), with the route between them. Until Leaflet loads, or if it cannot,
 * the pins sit on a plain grid by their coordinates and each opens OSM.
 */
export function StopsMap({ pins, caption }: { pins: Pin[]; caption: string }) {
  const { t } = useI18n();
  const box = useRef<HTMLDivElement>(null);
  const [live, setLive] = useState(false);
  const placed = layoutPins(pins);
  // Everything the map draws, translated; the map is rebuilt when it changes (another day or language).
  const draw = JSON.stringify(pins.map((p) => ({ ...p, link: t("{name} on OpenStreetMap", { name: p.name }), href: osmLink(p.lat, p.lng) })));

  useEffect(() => {
    let gone = false;
    let map: import("leaflet").Map | undefined;
    import("leaflet")
      .then(({ default: L }) => {
        if (gone || !box.current) return;
        const ps = JSON.parse(draw) as (Pin & { link: string; href: string })[];
        if (!ps.length) return;
        map = L.map(box.current, { scrollWheelZoom: false });
        L.tileLayer(OSM_TILES, { maxZoom: 19, attribution: OSM_ATTRIBUTION }).addTo(map);
        const stops = ps.filter((p) => p.kind === "stop").map((p) => L.latLng(p.lat, p.lng));
        if (stops.length > 1) L.polyline(stops, { color: "#13212B", weight: 2, dashArray: "5 5" }).addTo(map);
        for (const p of ps) {
          const icon = L.divIcon({ className: "smap-icon", html: pinHtml(p), iconSize: [30, 30], iconAnchor: [15, 15], popupAnchor: [0, -16] });
          const popup = document.createElement("div");
          const name = popup.appendChild(document.createElement("b"));
          name.textContent = p.name;
          popup.appendChild(document.createElement("br"));
          const a = popup.appendChild(document.createElement("a"));
          Object.assign(a, { href: p.href, target: "_blank", rel: "noopener noreferrer", textContent: p.link });
          L.marker([p.lat, p.lng], { icon, title: p.name, alt: p.name, keyboard: true }).bindPopup(popup).addTo(map);
        }
        const all = L.latLngBounds(ps.map((p) => L.latLng(p.lat, p.lng)));
        if (ps.length === 1) map.setView(all.getCenter(), 15);
        else map.fitBounds(all, { padding: [30, 30], maxZoom: 16 });
        setLive(true);
      })
      .catch(() => setLive(false)); // no Leaflet: the grid stays
    return () => {
      gone = true;
      map?.remove();
    };
  }, [draw]);

  if (!placed.length) return null;
  const route = placed.filter((p) => p.kind === "stop").map((p) => `${p.x},${p.y}`).join(" ");
  return (
    <figure className="smap">
      <div className="smap-box" role={live ? "region" : "img"} aria-label={caption}>
        {!live && (
          <>
            <svg viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">
              <defs>
                <pattern id="smap-grid" width="10" height="10" patternUnits="userSpaceOnUse"><path d="M10 0H0V10" fill="none" stroke="#D8CFBF" strokeWidth=".3" /></pattern>
              </defs>
              <rect width="100" height="100" fill="url(#smap-grid)" />
              {route.includes(" ") && <polyline points={route} fill="none" stroke="#13212B" strokeWidth=".6" strokeDasharray="1.6 1.6" vectorEffect="non-scaling-stroke" />}
            </svg>
            {placed.map((p) => (
              <a key={p.id} className={`smap-pin smap-${p.kind}`} style={{ left: `${p.x}%`, top: `${p.y}%` }} href={osmLink(p.lat, p.lng)} target="_blank" rel="noopener noreferrer" title={t("{name} on OpenStreetMap", { name: p.name })} aria-label={t("{name} on OpenStreetMap", { name: p.name })}>
                {p.label}
              </a>
            ))}
          </>
        )}
        <div ref={box} className="smap-live" />
      </div>
      <figcaption className="map-cap"><span>{caption}</span><span>{t(live ? "Tap a pin for its name" : "Pins open OpenStreetMap")}</span></figcaption>
    </figure>
  );
}
