# Laptop lanes (v3, HQ)

Six interactive Claude Code sessions on Rohan's laptop, all on Opus, one
worktree each, pushing tested commits straight to main. Rohan pastes HQ's
prompts in and the lanes' reports out. The plan is in Notion ("TY-SRP v3
plan"); the lane rules are `CLAUDE.md` and `.claude/`.

## Folders

- `C:\TravelYantra\main`: the main checkout (pull it to update the kit).
- `C:\TravelYantra\ty1` … `ty6`: one worktree per lane, on `lane/ty1` …
  `lane/ty6`.
- `%USERPROFILE%\.gcloud-travel`: the gcloud config for the trial project
  only (secondary Google account).

## Files

- `setup.ps1`: checks tools, logins and tokens (never prints them), updates
  main, sets git identity and hooks, puts each worktree on its lane branch,
  and does one tiny Haiku run to prove the flags parse. Safe to re-run.
- `start-all.ps1`: opens six windows, one per lane.
- `ty.ps1 TYn [start|resume]`: starts one lane: scoped GitHub token
  (`TY_GH_TOKEN` → `GH_TOKEN`), the gcloud-travel config, Opus, the lane's
  belt (MCP servers and permissions), user-level Claude settings ignored, and
  `/ty-lane TYn` as the first message.
- `belts/`: `back`, `front`, `infra`: MCP servers and permissions per belt.
  Only `infra` may run gcloud and firebase, with a deny list for destructive,
  billing and account commands.
- `statusline.js`: lane, model, context used, 5-hour and weekly usage; says
  "RELAY due" at 60% context.

## Lane skills (in `.claude/skills/`)

`/ty-lane`, `/ty-push`, `/ty-checkpoint`, `/ty-stop` (runs the Sonnet
`ty-reviewer` subagent), `/ty-relay`.
