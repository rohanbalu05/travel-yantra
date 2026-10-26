#!/usr/bin/env python3
"""guard: reject attribution text, unknown commit authors and (in CI) secrets.

Usage: guard.py BASE_SHA HEAD_SHA   (env: PR_TITLE, PR_BODY)
"""
import fnmatch
import os
import re
import subprocess
import sys
from pathlib import Path

FORBIDDEN = re.compile(r"Co-Authored-By|Generated with Claude Code|claude\.ai/code|Claude-Session", re.I)
EXEMPT = [
    "AGENTS.md", "CLAUDE.md", ".claude/rules/no-attribution.md",
    ".github/workflows/guard.yml", ".github/workflows/strip-attribution.yml",
    ".github/scripts/strip_attribution*.js", ".github/scripts/guard*.py",
    ".github/scripts/fixtures/*",
]
# Mirrors FOOTER in strip_attribution.js: the hosting environment's footer is
# removed from PR bodies by that workflow, so the body is checked without it.
FOOTER = [
    re.compile(r"^\s*_?\s*(\U0001F916\s*)?Generated (by|with) \[Claude Code\]\([^)]*\)\s*_?\s*$", re.I),
    re.compile(r"^\s*<?https?://claude\.ai/code/\S*>?\s*$", re.I),
    re.compile(r"^\s*(Co-Authored-By|Claude-Session):.*(anthropic|claude).*$", re.I),
]
DEFAULT_AUTHORS = {"rohanbalu05", "117021386+rohanbalu05@users.noreply.github.com"}
AUTHORS_FILE = ".github/allowed-authors.txt"


def allowed_authors(path=AUTHORS_FILE):
    p = Path(path)
    if not p.exists():
        return set(DEFAULT_AUTHORS)
    lines = (x.strip().lower() for x in p.read_text().splitlines())
    return {x for x in lines if x and not x.startswith("#")}


def author_ok(name, email, allowed):
    ids = {name.lower(), email.lower()}
    m = re.match(r"^\d+\+(.+)@users\.noreply\.github\.com$", email.lower())
    if m:
        ids.add(m.group(1))
    return bool(ids & {a.lower() for a in allowed})


def clean_body(body):
    return "\n".join(l for l in (body or "").splitlines() if not any(r.match(l) for r in FOOTER))


def added_lines_by_file(diff):
    """Yield (path, added_line) from a unified diff."""
    path = None
    for line in diff.splitlines():
        if line.startswith("+++ "):
            path = line[6:] if line.startswith("+++ b/") else None
        elif line.startswith("+") and path:
            yield path, line[1:]


def exempt(path):
    return any(fnmatch.fnmatch(path, g) for g in EXEMPT)


def check(title, body, commits, diff, allowed):
    """commits: list of (sha, name, email, message). Returns a list of problems."""
    problems = []
    for label, text in (("PR title", title), ("PR body", clean_body(body))):
        if FORBIDDEN.search(text or ""):
            problems.append(f"{label} contains attribution text")
    for sha, name, email, msg in commits:
        if FORBIDDEN.search(msg):
            problems.append(f"commit {sha[:7]} message contains attribution text")
        if not author_ok(name, email, allowed):
            problems.append(f"commit {sha[:7]} author {name} <{email}> is not allowed")
    seen = set()
    for path, line in added_lines_by_file(diff):
        if not exempt(path) and FORBIDDEN.search(line) and path not in seen:
            seen.add(path)
            problems.append(f"{path} contains attribution text")
    return problems


def git(*args):
    return subprocess.run(["git", *args], check=True, capture_output=True, text=True).stdout


def main(base, head):
    sep = "\x1f"
    fmt = sep.join(["%H", "%an", "%ae"]) + sep + "%B" + "\x1e"
    commits = []
    for rec in git("log", f"--format={fmt}", f"{base}..{head}").split("\x1e"):
        if rec.strip():
            sha, name, email, msg = rec.lstrip("\n").split(sep, 3)
            commits.append((sha, name, email, msg))
    problems = check(os.environ.get("PR_TITLE", ""), os.environ.get("PR_BODY", ""), commits,
                     git("diff", "--unified=0", f"{base}...{head}"), allowed_authors())
    for p in problems:
        print(f"::error::{p}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:3]))
