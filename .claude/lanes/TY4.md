# TY4 web — brief (v3)

Session TY4-web · purple · belt ty-front (MCP: context7, Playwright,
Next.js DevTools) · worktree `C:\TravelYantra\ty4` · branch `lane/ty4`.

Owns: `apps/web/`.

Objectives served: O1 and O3 on the web (the live web app is the main demo
surface), O2 on screen (six languages), O6 consents and delete flow.

Check command (run before every push):
`cd apps/web && pnpm install --frozen-lockfile && pnpm lint && pnpm typecheck && pnpm test`
and `pnpm build` before every STOP.

## Packages

- **P0 Merge your open work (after TY1's "MAIN GREEN").**
  If #93 is still open (`gh pr view 93 --json state`), `git merge --no-ff origin/ty/ty4-01-web-shell`; if it already merged, pull (#93, the Next.js 16 shell
  from the prototype). TY6 merges #96 (web CI pnpm version) at the same
  time; message TY6-infra so the web CI job runs. Check, fix, push.
- **P1 Plan flow on the API.** Cards #9 (Home, PlanStart, PlanThinking) and
  #30 (PlanOptions, Itinerary). Wire to TY1's streaming `/plan` (mock it
  until it lands; the API base URL comes from an env var). Done when the Goa
  family trip goes from Home to an Itinerary in the browser, shown by
  Playwright screenshots in `.lanes/shots/` (paths in the STOP).
- **P2 Guide, Katha and booking.** Cards #32 (Katha and AskGuide pages) and
  #31 (Book page, with TY3's sellers and links).
- **P3 Languages, account, tests.** Cards #42 (language switcher, six
  languages), #43 (sign in with Google only, Settings with DPDP consents and
  delete, My Trips), #44 (Playwright end-to-end test and rating widget).

## Design

- The prototype in `design/prototype/` is the base: keep its look, type and
  spacing; the landing page uses a generic story, with Bengaluru → Goa kept
  inside the app.
- No voice anywhere. Channels shown: web, WhatsApp, MCP.
- Check every screen at phone and laptop widths with Playwright before a STOP.

## Interfaces

- TY1 (plan stream, trips, share links), TY2 (ask, Katha), TY3 (compare,
  sellers), TY5 (languages). Agree shapes by message; use the generated
  contract types in `packages/contracts/ts/`.
- TY6 deploys the web app to Cloud Run; keep `pnpm build` working with
  Next.js standalone output.
