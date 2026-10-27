# Lanes and the paths they own (v3)

A lane edits only its own paths. Everything else is read-only to it.

| Lane | Session name | Colour | Belt | Worktree | Owns |
| --- | --- | --- | --- | --- | --- |
| TY1 | TY1-core | blue | ty-back | `C:\TravelYantra\ty1` | `packages/contracts/`, `apps/api/core/`, `apps/api/main.py`, `apps/api/pyproject.toml`, `apps/api/uv.lock`, `apps/api/Dockerfile`, `apps/api/tests/core/`, `apps/api/tests/conftest.py` |
| TY2 | TY2-guide | green | ty-back | `C:\TravelYantra\ty2` | `apps/api/guide/`, `apps/api/tests/guide/`, `data/` |
| TY3 | TY3-routes | orange | ty-back | `C:\TravelYantra\ty3` | `apps/api/routes/`, `apps/api/tests/routes/` |
| TY4 | TY4-web | purple | ty-front | `C:\TravelYantra\ty4` | `apps/web/` |
| TY5 | TY5-channels | cyan | ty-back | `C:\TravelYantra\ty5` | `services/translate/`, `apps/bots/` (WhatsApp; Telegram only if WhatsApp fails), `apps/mcp/` |
| TY6 | TY6-infra | red | ty-infra | `C:\TravelYantra\ty6` | `.github/`, `infra/` (except `infra/lanes/`), `fixtures/recorded/` |
| TY7 | TY7-docs | grey | — | later | `report/`, `deck/`, `paper/`, `bench/` |
| HQ | — | — | — | — | `CLAUDE.md`, `AGENTS.md`, `SECURITY.md`, `.claude/`, `.githooks/`, `infra/lanes/`, `design/`, root files |

The main checkout is `C:\TravelYantra\main`. Each lane works on a local
branch `lane/tyN` in its own worktree and pushes `HEAD:main`.

## One owner per dependency file

- `apps/api/pyproject.toml` and `apps/api/uv.lock`: TY1. TY2 and TY3 message
  TY1 with the package and version they need; TY1 adds it within the hour.
- `apps/web/package.json` and `apps/web/pnpm-lock.yaml`: TY4.
- `apps/mcp/`, `apps/bots/`, `services/translate/` dependency files: TY5.
- Workflows and Dockerfiles under `infra/`: TY6. `apps/api/Dockerfile`: TY1.

## How the API fits together

- `apps/api/main.py` (TY1) builds the FastAPI app and includes the routers
  `core.router`, `guide.router` and `routes.router`. TY2 and TY3 expose an
  `APIRouter` named `router` in their package `__init__.py`; TY1 mounts it.
- Service images (api, mcp, translate, web) build with their own Dockerfile
  path; api and mcp build from the repo root so they can copy
  `packages/contracts`.
- Every lane imports shared types from `packages/contracts` (Python package
  `ty_contracts`). Web uses the generated types in `packages/contracts/ts/`.

## Talking to other lanes

- Interfaces (an endpoint shape, a field, a dependency) are agreed directly
  between lanes with cross-session messages. Name the lane, say exactly what
  you need, and say what you will do meanwhile (mock it, skip it).
- Decisions (scope, cost, architecture, anything Rohan must do) go to HQ in
  your STOP.
