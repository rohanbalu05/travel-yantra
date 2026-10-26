#!/usr/bin/env python3
"""review-gate: set the `review-gate` commit status on a PR head SHA.

Passes when Codex has posted its one round (or backup-review succeeded),
second-review is success on the head SHA, and needs-rohan is absent or
rohan-ok is present. Codex-specific knowledge (bot login, state comment,
usage-limit reply) lives here.
"""
import argparse
import json
import re
import subprocess
import sys

CODEX_LOGIN = "chatgpt-codex-connector[bot]"
STATE_RE = re.compile(r"<!--\s*codex-review-state:v1\s*(\{.*?\})\s*-->", re.S)
LIMIT_RE = re.compile(r"usage limit|reached (your|the) .{0,40}limit|rate limit", re.I)


def _codex(items):
    return [i for i in items if (i.get("user") or {}).get("login") == CODEX_LOGIN]


def codex_posted(reviews, comments):
    """True once Codex has posted its round-1 review on this PR (any commit)."""
    return bool(_codex(reviews)) or any(STATE_RE.search(c.get("body") or "") for c in _codex(comments))


def usage_limited(head_date, comments):
    for c in _codex(comments):
        body = c.get("body") or ""
        if c.get("created_at", "") >= head_date and not STATE_RE.search(body) and LIMIT_RE.search(body):
            return True
    return False


def evaluate(head, head_date, labels, reviews, comments, backup, second):
    """Return (state, description, dispatch_backup). `backup` and `second` are
    the backup-review / second-review status states on head, or None."""
    if "needs-rohan" in labels and "rohan-ok" not in labels:
        return "failure", "needs-rohan is set; waiting for rohan-ok", False
    if second in ("failure", "error"):
        return "failure", "second review failed for this commit", False
    if backup == "error":
        return "failure", "backup review errored; rerun backup-review.yml", False
    if backup == "failure":
        return "failure", "backup review reported P0/P1 findings", False
    first = codex_posted(reviews, comments) or backup == "success"
    if first and second == "success":
        return "success", "first and second review done for this commit", False
    if not first and backup is None and usage_limited(head_date, comments):
        return "pending", "Codex usage limit; backup review requested", True
    return "pending", "waiting for " + ("second review" if first else "first review"), False


def gh(*args, lines=False):
    out = subprocess.run(["gh", "api", *args], check=True, capture_output=True, text=True).stdout
    return [json.loads(x) for x in out.splitlines() if x.strip()] if lines else json.loads(out or "null")


def fetch(repo, n):
    r = f"repos/{repo}"
    pr = gh(f"{r}/pulls/{n}")
    head = pr["head"]["sha"]
    page = lambda p: gh("--paginate", p, "--jq", ".[]", lines=True)  # noqa: E731
    # Combined status = latest status per context (the plain list is paged, newest first).
    statuses = gh(f"{r}/commits/{head}/status")["statuses"]
    state = lambda c: next((s["state"] for s in statuses if s["context"] == c), None)  # noqa: E731
    return dict(
        head=head,
        head_date=gh(f"{r}/commits/{head}")["commit"]["committer"]["date"],
        labels=[l["name"] for l in pr["labels"]],
        reviews=page(f"{r}/pulls/{n}/reviews"),
        comments=page(f"{r}/issues/{n}/comments"),
        backup=state("backup-review"),
        second=state("second-review"),
    )


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    ap.add_argument("--pr", type=int, help="one PR; default is every open PR")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    nums = [a.pr] if a.pr else [p["number"] for p in gh("--paginate", f"repos/{a.repo}/pulls?state=open", "--jq", ".[]", lines=True)]
    for n in nums:
        d = fetch(a.repo, n)
        state, desc, dispatch = evaluate(**d)
        print(f"#{n} {d['head'][:7]} review-gate={state}: {desc}")
        if a.dry_run:
            continue
        gh("-X", "POST", f"repos/{a.repo}/statuses/{d['head']}", "-f", f"state={state}",
           "-f", "context=review-gate", "-f", f"description={desc[:140]}")
        if dispatch:
            subprocess.run(["gh", "workflow", "run", "backup-review.yml", "--repo", a.repo, "-f", f"pr={n}"], check=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
