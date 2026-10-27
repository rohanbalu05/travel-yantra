---
name: ty-lane
description: Start or resume a Travel Yantra lane. Typed by Rohan or the launcher as /ty-lane TYn start, or /ty-lane TYn resume after a relay.
argument-hint: TYn start|resume
disable-model-invocation: true
---

Lane id: $0. Mode: $1 (start if empty).

1. Read `CLAUDE.md`, every file in `.claude/rules/`, and your brief
   `.claude/lanes/$0.md`. If the mode is resume, also read
   `.lanes/relay/$0.md` and continue from it.
2. Check the environment. Never print a secret; report only ok or a problem.
   - `git config user.email` is `117021386+rohanbalu05@users.noreply.github.com`
     and `git config user.name` is `Rohan Balu`. If not, set them (CLAUDE.md).
   - `git config core.hooksPath` is `.githooks`.
   - `git fetch origin main`. Your branch is `lane/<lane id in lower case>`
     (for example `lane/ty3`). If you are on a detached HEAD or another branch
     and the worktree is clean, run `git switch -C lane/tyN origin/main`.
     If it is not clean, report it and wait.
   - `gh auth status` succeeds (it uses `GH_TOKEN` from the launcher).
   - `CLOUDSDK_CONFIG` and `GOOGLE_CLOUD_PROJECT` are set (names only).
   - TY6 only: `gcloud config list --format="value(core.project)"` prints
     `project-cea09bbb-b5f7-4fc4-95b`.
   - The MCP servers your belt should have are connected (see your brief).
3. Print this block and wait for HQ's PROMPT (Rohan pastes it):

```
LANE UP $0 · <session name> · <colour> · <model>
Worktree: <path> · Branch: lane/tyN at <short sha> · origin/main <short sha>
Belt: <belt> · MCP: <connected servers>
Checks: identity <ok> · hooks <ok> · gh <ok> · cloud env <ok> · gcloud <ok | n/a>
Main CI: <green | red | running> (gh run list --branch main --workflow ci --limit 1)
Resume point: <from the relay note | none>
Ready for: <the first package in your brief>
```
