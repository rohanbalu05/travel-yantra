# AGENTS.md

Instructions for automated agents working on this repository, including
code reviewers. Lane build rules are in `CLAUDE.md` and `.claude/rules/`.

## Code Review Rules

These are the review guidelines for this repository.

### Severity

- **P0** — must not merge: leaked secret or credential; real personal data
  or phone numbers; data loss or destructive migration; security hole
  (injection, auth bypass, SSRF, unsafe deserialisation); broken build on
  `main`; attribution text (see below).
- **P1** — fix before merge: incorrect behaviour against the card's
  "done when"; missing or failing tests for new logic; a live network call
  in a test; a paid API call without caching or outside the agreed free
  caps; a breaking change to `packages/contracts` without HQ approval; a
  lane editing paths it does not own (see `.claude/rules/lanes.md`);
  unbounded loops, retries or fan-outs against external APIs; missing
  timeouts on outbound calls.
- **P2** — nice to have: naming, structure, small performance or
  readability improvements. P2 findings never block a merge.

Label every finding with its severity (P0, P1 or P2). If there are no P0
or P1 findings, say so plainly.

### Always flag (P0)

- Any of these strings in commits, PR text or files: `Co-Authored-By`,
  `Generated with Claude Code`, `claude.ai/code`, `Claude-Session`.
  Exception: the files that define this rule and the check that enforces
  it (`AGENTS.md`, `CLAUDE.md`, `.claude/rules/no-attribution.md`,
  `.github/workflows/guard.yml`, `.github/workflows/strip-attribution.yml`
  and their test fixtures) may list them.
- PR and issue bodies: a footer appended by the hosting environment is
  removed automatically by `strip-attribution` on `main`; flag it only if
  it is still present after that workflow has run.
- Secrets or tokens in code, fixtures, logs or test data.

### Check

- Secrets come from env vars only, referenced by name.
- External calls have timeouts, caching where specified, and fakes in tests.
- Translation output passes through the QA checks before it is shown.
- Emergency guidance (hospitals, police) comes from Places data, not model
  memory.
- Sample data only: the sample persona, sample PNRs and fares.

### Do not flag

- Formatting that `ruff` or `prettier` would fix.
- Missing features that the PR's card lists as out of scope.
