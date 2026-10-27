---
name: ty-checkpoint
description: Print the mid-package CHECKPOINT block for a Travel Yantra lane, then keep working. Use about halfway through each package.
---

Print the CHECKPOINT block from `.claude/rules/loop.md` in a fenced block,
filled in honestly:

- Done: what works now (seen working, not assumed).
- Now: the step you are on.
- Pushed: short SHAs of your commits on origin/main since the package
  started (`git log --oneline <package start>..origin/main --author=Rohan`
  and check they are yours), or "none yet".
- Tests: the last check command and its pass and fail counts.
- Off plan?: no, or yes with the reason (a blocker, a change of approach, an
  interface another lane hasn't built).

Then continue the package. Do not wait for a reply.
