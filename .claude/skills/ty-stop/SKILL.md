---
name: ty-stop
description: Finish a Travel Yantra lane package - push, run the Sonnet reviewer, fix P0 and P1, gather proof and print the STOP block. Use at the end of every package.
---

1. Push any pending work with `/ty-push`.
2. Find the base: the `base` value in `.lanes/state/TYn.json` (create the
   folder and file if missing; for the first package, use the commit
   origin/main was at when the package started).
3. Use the `ty-reviewer` subagent. Give it: the lane id, the base commit,
   the package goal from HQ's PROMPT, and your lane's check command.
4. If the verdict is FAIL: fix every P0 and P1 (and cheap P2s), push, and run
   the reviewer once more on the new head. At most two review rounds; if a
   P0 or P1 is still open after that, say so in the STOP.
5. Gather proof you have actually seen:
   - your check command's result line;
   - for endpoints, a `curl` against the local server (short output);
   - TY4: Playwright screenshots saved under `.lanes/shots/` (paths only);
   - live smoke calls made, if any;
   - main's CI: `gh run list --branch main --workflow ci --limit 1`.
6. Write `{"base": "<origin/main head after your last push>"}` to
   `.lanes/state/TYn.json`.
7. Print the STOP block from `.claude/rules/loop.md`, filled in honestly,
   in a fenced block. Leave "Context" blank for Rohan. Then wait.
