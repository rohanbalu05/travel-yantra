# Card protocol

A card is a GitHub issue titled `[TY3-04] title` with labels `lane:ty3`,
`status:ready|claimed|blocked|done` and `size:S|M`. The body is the full
prompt: goal, files to read first, done when, out of scope, needs, and
cost or approval flags.

Repo: `rohanbalu05/travel-yantra`. `R=repos/rohanbalu05/travel-yantra`.

## 0. First, your open PRs

Before any new card, check your lane's open PRs for review findings
(Codex or the backup reviewer):

```
gh api "$R/pulls?state=open" --jq '.[] | select(.head.ref|startswith("ty/ty3-")) | .number'
gh api "$R/pulls/N/reviews"            # review bodies
gh api "$R/pulls/N/comments"           # inline findings
```

Fix every P0 and P1 finding (and cheap P2s), push to the same branch, then
add the label `fixes-pushed`:
`gh api -X POST "$R/issues/N/labels" -f 'labels[]=fixes-pushed'`.
Never reply to or resolve review comments. Never request a review yourself.

## 1. Claim

Only take a card whose "Needs" are merged. Swap labels:
`gh api -X DELETE "$R/issues/N/labels/status:ready"` then add `status:claimed`.

## 2. Build

- Branch `ty/ty3-04-short-slug` from the latest `main`
  (`git fetch origin main && git switch -c ty/ty3-04-slug origin/main`).
- Read only the files the card names, plus this folder.
- Write code and tests. Run the targeted tests.
- Commit messages: `[TY3-04] what changed`. No trailers of any kind.

## 3. Open the PR (normal, not draft)

```
gh api -X POST "$R/pulls" -f title='[TY3-04] title' -f head='ty/ty3-04-slug' \
  -f base=main -f body="$(cat /tmp/pr_body.md)"
```

Body sections: `## What`, `## Why`, `## How tested`, `## Assumptions`,
then `Closes #N`. Nothing else — no footer, no links to sessions, no tool
names. Do not enable auto-merge. Do not merge.

## 4. STOP comment on the card

```
gh api -X POST "$R/issues/N/comments" -f body="$(cat /tmp/stop.md)"
```

```
STOP TY3.04 — DONE | BLOCKED
PR: #123
Tests: <commands run and result>
Changed for other lanes: <contracts, endpoints, env var names, or "nothing">
Asks: <new cards filed, e.g. #140 for TY1, or "none">
Blocker: <only if BLOCKED: what and who can unblock>
```

Then set the label: `status:done` (PR open, STOP posted) or `status:blocked`.
The issue closes when HQ merges the PR.

## 5. Asks

Each ask is a new issue for the owning lane: title `[TY1-xx?] short ask`
(HQ renumbers), labels `lane:ty1`, `status:ready`, `size:S`, `from:ty3`,
and a body with the goal and done-when. Mention it in the STOP.

## 6. End of session

One final line: cards done, PR numbers, blockers.
