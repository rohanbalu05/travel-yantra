#!/usr/bin/env python3
"""backup-review: ask Gemini (AI Studio free key) to review a PR diff.

Env: GH_TOKEN, GEMINI_API_KEY, optional BACKUP_REVIEW_MODEL. Usage: backup_review.py REPO PR
"""
import json
import os
import subprocess
import sys
import urllib.request
from pathlib import Path

MODEL = os.environ.get("BACKUP_REVIEW_MODEL", "gemini-3.5-flash")
MAX_DIFF = 150_000
SEVERITIES = ("P0", "P1", "P2")
SCHEMA = {"type": "OBJECT", "properties": {"findings": {"type": "ARRAY", "items": {
    "type": "OBJECT", "required": ["severity", "file", "message"], "properties": {
        "severity": {"type": "STRING", "enum": list(SEVERITIES)},
        "file": {"type": "STRING"}, "line": {"type": "INTEGER"}, "message": {"type": "STRING"}}}}},
    "required": ["findings"]}


def truncate(diff, limit=MAX_DIFF):
    if len(diff) <= limit:
        return diff, False
    return diff[:limit] + "\n[diff truncated]\n", True


def build_prompt(rules, diff):
    return (f"{rules}\n\nReview this pull request diff against the rules above. Report only real "
            f"problems, each with a severity of P0, P1 or P2. Return JSON only.\n\n{diff}")


def parse_findings(text):
    try:
        raw = json.loads(text)["findings"]
    except (ValueError, KeyError, TypeError):
        raise ValueError("model did not return the findings JSON")
    return [f for f in raw if f.get("severity") in SEVERITIES]


def verdict(findings):
    return "failure" if any(f["severity"] in ("P0", "P1") for f in findings) else "success"


def render(findings, truncated):
    lines = ["Backup review (Gemini)."]
    if not findings:
        lines.append("No P0 or P1 findings.")
    for f in sorted(findings, key=lambda f: f["severity"]):
        where = f"{f['file']}:{f['line']}" if f.get("line") else f["file"]
        lines.append(f"- **{f['severity']}** `{where}` {f['message']}")
    if truncated:
        lines.append("\nThe diff was truncated; later files were not reviewed.")
    return "\n".join(lines)


def gemini(prompt):
    req = urllib.request.Request(
        f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent",
        data=json.dumps({"contents": [{"parts": [{"text": prompt}]}], "generationConfig": {
            "responseMimeType": "application/json", "responseSchema": SCHEMA}}).encode(),
        headers={"Content-Type": "application/json", "x-goog-api-key": os.environ["GEMINI_API_KEY"]})
    with urllib.request.urlopen(req, timeout=120) as r:  # single attempt, bounded
        return json.load(r)["candidates"][0]["content"]["parts"][0]["text"]


def gh(*args, stdin=None):
    return subprocess.run(["gh", "api", *args], check=True, capture_output=True, text=True, input=stdin).stdout


def main(repo, pr):
    r = f"repos/{repo}"
    head = json.loads(gh(f"{r}/pulls/{pr}"))["head"]["sha"]

    def status(state, desc):
        gh("-X", "POST", f"{r}/statuses/{head}", "-f", f"state={state}", "-f", "context=backup-review",
           "-f", f"description={desc[:140]}")

    status("pending", "backup review running")
    try:
        diff, cut = truncate(gh("-H", "Accept: application/vnd.github.v3.diff", f"{r}/pulls/{pr}"))
        rules = Path("AGENTS.md").read_text()
        findings = parse_findings(gemini(build_prompt(rules, diff)))
    except Exception as e:  # report the failure on the commit, never leave it pending
        status("error", f"backup review failed: {type(e).__name__}")
        raise
    gh("-X", "POST", f"{r}/pulls/{pr}/reviews", "--input", "-", stdin=json.dumps(
        {"commit_id": head, "event": "COMMENT", "body": render(findings, cut)}))
    state = verdict(findings)
    status(state, "no P0/P1 findings" if state == "success" else "P0/P1 findings in backup review")
    return 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:3]))
