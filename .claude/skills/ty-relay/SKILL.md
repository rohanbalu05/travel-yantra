---
name: ty-relay
description: Hand a Travel Yantra lane over to a fresh session when its context is filling up. Use when HQ's reply starts with RELAY.
---

1. Push any pending work with `/ty-push`.
2. Write `.lanes/relay/TYn.md` (not committed; `.lanes/` is git-ignored) with:
   - the package id and goal, copied from HQ's PROMPT;
   - what is done and pushed (short SHAs);
   - what is half-done, and exactly where (files, functions);
   - the next three steps;
   - decisions and assumptions made so far;
   - open messages with other lanes and what they owe you;
   - commands you were using (check, run, curl);
   - the base commit from `.lanes/state/TYn.json`.
3. Print the RELAY block from `.claude/rules/loop.md`, then tell Rohan:
   type `/clear`, then `/ty-lane TYn resume`.
