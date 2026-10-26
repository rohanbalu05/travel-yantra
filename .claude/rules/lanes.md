# Lanes and the paths they own

A lane edits only its own paths. Everything else is read-only to it.

| Lane | Name | Owns |
| --- | --- | --- |
| TY1 | core | `packages/contracts/`, `apps/api/core/`, `apps/api/pyproject.toml`, `apps/api/main.py`, `apps/api/tests/core/` |
| TY2 | guide | `apps/api/guide/`, `apps/api/tests/guide/`, `data/` |
| TY3 | routes | `apps/api/routes/`, `apps/api/tests/routes/` |
| TY4 | web | `apps/web/` |
| TY5 | channels | `services/translate/`, `apps/bots/` (WhatsApp, Telegram), `apps/mcp/` |
| TY6 | ops | `.github/` (except the PR template), `infra/` (except `infra/lanes/`), `fixtures/recorded/` |
| TY7 | docs | `report/`, `deck/`, `paper/`, `bench/` |
| HQ | — | `CLAUDE.md`, `AGENTS.md`, `SECURITY.md`, `.claude/`, `.github/pull_request_template.md`, `infra/lanes/`, root files |

## How the API fits together

- `apps/api/main.py` (TY1) builds the FastAPI app and includes the routers
  `core.router`, `guide.router` and `routes.router`. TY2 and TY3 expose an
  `APIRouter` named `router` in their package `__init__.py`; TY1 mounts it.
- TY2 and TY3 add dependencies by asking TY1 (an ask card) or, if TY1's
  pyproject already lists them, simply using them. If a card needs a new
  dependency immediately, note it under Assumptions and file the ask.
- Every lane imports shared types from `packages/contracts` (Python package
  `ty_contracts`). Web uses the generated types in `packages/contracts/ts/`.

## Cross-lane asks

Need a change in another lane's paths? File a new issue for the owning lane
with labels `lane:tyN`, `status:ready`, `size:S`, `from:tyM`, and say so in
your STOP. Never edit the other lane's files yourself.
