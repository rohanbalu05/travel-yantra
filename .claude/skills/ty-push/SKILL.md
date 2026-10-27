---
name: ty-push
description: Commit, rebase on origin/main, run the lane's checks and push HEAD to main. Use after every working step in a Travel Yantra lane.
argument-hint: "[commit message]"
---

Follow `.claude/rules/loop.md` → "Pushing to main".

1. `git status`. Stage only your lane's paths. Commit with `[TYn] <message>`
   (use $ARGUMENTS as the message if given). No trailers.
2. `git fetch origin main` then `git rebase origin/main`. Resolve conflicts in
   your own paths; for another lane's paths, abort the rebase
   (`git rebase --abort`), message that lane, and tell Rohan.
3. Run your lane's check command from your brief. If it fails, fix and go to 1.
4. `git push origin HEAD:main`. If rejected because main moved, go to 2
   (at most three times, then report).
5. Print one line: `PUSHED TYn <short sha> · <n> commit(s) · checks <result>`.

Never `--force`, never `--no-verify`, never push with failing checks.
