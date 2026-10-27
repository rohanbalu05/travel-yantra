# The v3 loop: packages, pushes and reports

## The loop

1. HQ writes a `PROMPT TYn · Pk` block. Rohan pastes it into your terminal.
2. You work that package (60–90 minutes): small commits, `/ty-push` often.
3. About halfway, run `/ty-checkpoint`: print the CHECKPOINT block and keep
   working. Do not wait for a reply.
4. At the end, run `/ty-stop`: the reviewer checks the package, you fix every
   P0 and P1, push, then print the STOP block and wait.
5. Rohan pastes your STOP to HQ, adding your context % from the status line.
   HQ checks your claims against the public repo and replies with the next
   PROMPT, or with RELAY.
6. If you are blocked mid-package (a cost-gate item, a login only Rohan can
   do, an interface another lane hasn't built), keep going on what you can
   and report it at the STOP. Stop early only if nothing useful is left.

## Pushing to main (`/ty-push` does this)

1. Commit your work: `[TYn] what changed` (one line, present tense, no
   trailers).
2. `git fetch origin main`, then `git rebase origin/main` (your own unpushed
   commits only; your branch is never shared).
3. Run your lane's checks (the commands in your brief). Fix failures before
   pushing.
4. `git push origin HEAD:main`. If it is rejected because main moved, go back
   to step 2 (at most three times, then report).
5. Never force-push, never `--no-verify`, never push a red test run.

A rebase conflict in your own paths: resolve it. A conflict in another
lane's paths: don't touch their file; message that lane and HQ.

## Main red

- `gh run list --branch main --workflow ci --limit 3` shows main's CI.
- If main turned red after your push, fix it (or revert your own commit with
  `git revert`) before anything else, and say so in your next report.
- If another lane broke it, message that lane; don't fix their files.

## Report formats (print exactly these, in a fenced block)

```
CHECKPOINT TYn · Pk · ~45 min
Done: <what works now, plain words>
Now: <what I'm on>
Pushed: <short SHAs on origin/main, or none yet>
Tests: <command → passed/failed counts>
Off plan? <no | yes: why>
```

```
STOP TYn · Pk · DONE | PARTIAL | BLOCKED
Built: <2–4 lines, what works now>
Proof: <commands run and their result lines; curl output; screenshot paths>
Pushed: <short SHAs on origin/main> · main CI: <green | red | running>
Review (Sonnet): <PASS | FAIL> · P0 <n> · P1 <n> fixed · P2 left <n>
Faked or stubbed: <fixtures, mocks, TODOs — honestly>
Changed for others: <endpoints, contract fields, env var names | nothing>
Asks: <lane: ask | none>
Needs Rohan: <item | none>
Next: <proposed next package, one line>
Context: <leave blank; Rohan adds the % from the status line>
```

```
RELAY TYn
Written: .lanes/relay/TYn.md (not committed)
Resume with: /clear, then /ty-lane TYn resume
```

## Context relay

When HQ's reply starts with RELAY, run `/ty-relay`: it writes everything the
next session needs to `.lanes/relay/TYn.md`. Rohan then types `/clear` and
`/ty-lane TYn resume`. You continue the same package with a fresh context.

## Live smoke calls

Allowed for TY1, TY2, TY3 and TY5 (and TY6 for deploy checks): a handful per
package, through the trial project's Vertex AI or the agreed free APIs,
cached where the code caches, never inside tests. List each in Proof.
