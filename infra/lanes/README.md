# Laptop lane runners (HQ)

Lanes run as headless sessions on Rohan's laptop, one fresh session per
command. HQ talks to them through GitHub only.

- Each lane has a worktree `C:\TravelYantra\tyN` and a dispatch issue
  titled `[dispatch] TYN ...`. HQ posts a command there
  (`Work your queue: #a, #b`, `Fix PR #n`, `HQ task: <instruction>`, `HQ: pause`, `HQ: resume`;
  add `effort:high` for contract or planner cards). The runner posts
  `RUN ... started` and `RUN ... done` with the session's final line.
- When idle, a lane runner also acts by itself: it fixes its own PRs whose
  second review failed or whose first review has open findings (at most two
  fix runs per PR), and every 20 minutes it works its oldest ready cards.
- The second-review runner reviews every open PR head commit once
  (read-only), posts a PR review marked `second-review:v1` and sets the
  commit status `second-review`. After fixes it runs again in verify mode.
- Lane sessions get no MCP servers (`--strict-mcp-config`), a permission
  allowlist (`lane-settings.json`) and denies for force-push, pushing to
  main, merging, gcloud and firebase.

Setup: `infra\lanes\setup.ps1` (checks logins, creates worktrees, runs a
self-test), then `infra\lanes\start-all.ps1`. Logs: `C:\TravelYantra\logs`.
