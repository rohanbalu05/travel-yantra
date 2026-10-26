#!/usr/bin/env python3
"""review-gate: set the `review-gate` commit status on a PR head SHA.

All Codex-specific knowledge (bot login, state comment, P0/P1 badges, the
usage-limit reply) lives here; HQ calibrates it at G1.
"""
import argparse
import json
import re
import subprocess
import sys

CODEX_LOGIN = "chatgpt-codex-connector[bot]"
STATE_RE = re.compile(r"<!--\s*codex-review-state:v1\s*(\{.*?\})\s*-->", re.S)
BLOCKING_RE = re.compile(r"\bP[01]\b")
LIMIT_RE = re.compile(r"usage limit|reached (your|the) .{0,40}limit|rate limit", re.I)


def _codex(items):
    return [i for i in items if (i.get("user") or {}).get("login") == CODEX_LOGIN]


def codex_state(comments, head):
    """The machine-readable code_review block for `head`, or None."""
    found = None
    for c in _codex(comments):
        m = STATE_RE.search(c.get("body") or "")
        if not m:
            continue
        try:
            cr = json.loads(m.group(1))["code_review"]
        except (ValueError, KeyError, TypeError):
            continue
        if cr.get("commit_sha") == head:
            found = cr
    return found


def codex_verdict(head, reviews, inline, comments):
    """'pass', 'fail' or None (no verdict yet for this head SHA). Only evidence
    bound to the head SHA counts; a thumbs-up reaction carries no SHA, so it is
    not used (Codex's state comment says the same thing with the SHA)."""
    st = codex_state(comments, head)
    if st and st.get("status") == "completed":
        return "fail" if st.get("has_unresolved_findings") else "pass"
    mine = [r for r in _codex(reviews) if r.get("commit_id") == head]
    if not mine:
        return None
    latest = max(mine, key=lambda r: r.get("submitted_at") or "")
    for c in _codex(inline):
        if c.get("pull_request_review_id") == latest["id"] and BLOCKING_RE.search(c.get("body") or ""):
            return "fail"
    return "pass"


def usage_limited(head_date, comments):
    for c in _codex(comments):
        body = c.get("body") or ""
        if c.get("created_at", "") >= head_date and not STATE_RE.search(body) and LIMIT_RE.search(body):
            return True
    return False


def evaluate(head, head_date, labels, reviews, inline, comments, backup):
    """Return (state, description, dispatch_backup). `backup` is the
    backup-review status state on head ('success', 'failure', 'pending') or None."""
    if "needs-rohan" in labels and "rohan-ok" not in labels:
        return "failure", "needs-rohan is set; waiting for rohan-ok", False
    verdict = codex_verdict(head, reviews, inline, comments)
    if verdict == "pass":
        return "success", "Codex review clean for this commit", False
    if backup == "success":
        return "success", "backup review passed", False
    if verdict == "fail":
        return "failure", "Codex reported P0/P1 findings", False
    if backup is None and usage_limited(head_date, comments):
        return "pending", "Codex usage limit; backup review requested", True
    if backup == "failure":
        return "failure", "backup review reported P0/P1 findings", False
    return "pending", "waiting for a review of this commit", False


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
    backup = next((s["state"] for s in statuses if s["context"] == "backup-review"), None)
    return dict(
        head=head,
        head_date=gh(f"{r}/commits/{head}")["commit"]["committer"]["date"],
        labels=[l["name"] for l in pr["labels"]],
        reviews=page(f"{r}/pulls/{n}/reviews"),
        inline=page(f"{r}/pulls/{n}/comments"),
        comments=page(f"{r}/issues/{n}/comments"),
        backup=backup,
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
