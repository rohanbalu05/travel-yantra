# Design prototype (reference for TY4 web)

Exported from the Travel Yantra design canvas on 27 Oct 2026. These files
are the visual source of truth for `apps/web`: port each screen's layout,
copy and components into Next.js, and reuse `ty.css` tokens and classes.

- One file per screen (`*.dc.html`); `Main.dc.html` is the landing page.
  `canvas.json` lists the screens and their sizes.
- The markup uses a small templating format (`<x-dc>`, `<sc-for>`,
  `<sc-if>`, `{{ value }}` holes, a `Component` class whose `renderVals()`
  holds sample data and state). Translate those into React components and
  state; the sample data becomes props or API data.
- `ty.css` holds the design tokens and shared classes; carry it over as the
  base stylesheet (or as CSS variables plus modules).
- Fonts: Bricolage Grotesque, Figtree, JetBrains Mono, and Anek
  (Kannada, Devanagari, Tamil, Telugu, Bangla) from Google Fonts.

Differences from the prototype that the build must follow:

- Voice is cut (27 Oct): the Voice screen is left out; drop mic buttons and
  voice-note UI elsewhere (WhatsApp screen shows text only).
- Sign in is Google only: no phone number or SMS code (SMS costs money).
- Channels shown on the landing page: web, WhatsApp, Telegram and the MCP
  server.
- Sample data only (Arjun Rao and family; sample PNRs and fares).
