#!/usr/bin/env python3
"""Fail if any recorded fixture holds a key, token or phone number."""
import re
import sys
from pathlib import Path

PATTERNS = {
    "google api key": re.compile(r"AIza[0-9A-Za-z_-]{30,}"),
    "bearer token": re.compile(r"Bearer\s+[A-Za-z0-9._-]{20,}", re.I),
    "key in url or json": re.compile(r"(api[_-]?key|token|secret)[\"']?\s*[:=]\s*[\"']?[A-Za-z0-9_-]{16,}", re.I),
    "phone number": re.compile(r"(?<!\d)(\+?91[\s-]?)?[6-9]\d{9}(?!\d)"),
    # Landlines with an STD code, spaced or not: 0832 222 2222, +91 832 2222222.
    "landline number": re.compile(r"(?<![\d.])(?:0|\+91[\s-]?)[1-9]\d{1,3}[\s-]?\d{3,4}[\s-]?\d{3,4}(?![\d.])"),
}


def scan(text):
    return [name for name, rx in PATTERNS.items() if rx.search(text)]


def main(root):
    bad = 0
    for p in sorted(Path(root).rglob("*")):
        if p.is_file():
            for name in scan(p.read_text(errors="ignore")):
                print(f"::error file={p}::possible {name}")
                bad += 1
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "fixtures/recorded"))
