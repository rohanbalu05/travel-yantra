"""Which Cloud Run services deploy.yml ships for one green commit.

Each service is compared with the commit it runs now (its GIT_SHA env on
Cloud Run), not with the last deploy run, so a run skipped or cancelled by a
newer push never drops a service, and an older commit never replaces a newer
one. Usage (in deploy.yml):

    python3 .github/scripts/deploy_plan.py SHA LIVE_JSON [--all]

LIVE_JSON maps service name to its live GIT_SHA ("" if unknown). Prints the
matrix JSON on the last line; reasons go to stderr.
"""

import json
import subprocess
import sys
from pathlib import Path

# name, source dir, Dockerfile. ty-translate is the Gemini image (V3-W);
# services/translate/Dockerfile.indictrans2 is never built.
SERVICES = [
    ("ty-api", "apps/api", "apps/api/Dockerfile"),
    ("ty-web", "apps/web", "infra/web/Dockerfile"),
    ("ty-translate", "services/translate", "services/translate/Dockerfile"),
    ("ty-bots", "apps/bots/whatsapp", "apps/bots/whatsapp/Dockerfile"),
    ("ty-mcp", "apps/mcp", "apps/mcp/Dockerfile"),
]
# A change here redeploys every service.
PLUMBING = (".github/workflows/deploy.yml", "infra/cloudbuild/")
SHARED = ("packages/contracts/",)


def git(*args):
    return subprocess.run(["git", *args], capture_output=True, text=True)


def known(sha):
    return bool(sha) and git("cat-file", "-e", f"{sha}^{{commit}}").returncode == 0


def is_ancestor(a, b):
    return git("merge-base", "--is-ancestor", a, b).returncode == 0


def changed(base, head):
    out = git("diff", "--name-only", base, head)
    if out.returncode != 0:
        return None
    return [line for line in out.stdout.splitlines() if line]


def plan(sha, live, force_all=False, *, exists=lambda p: Path(p).is_file(),
         known=known, is_ancestor=is_ancestor, changed=changed, log=print):
    out = []
    for name, src, dockerfile in SERVICES:
        if not exists(dockerfile):
            log(f"skip {name}: no {dockerfile}")
            continue
        if not (exists(f"{src}/package.json") or exists(f"{src}/pyproject.toml")):
            log(f"skip {name}: no project in {src}")
            continue
        entry = {"name": name, "dir": src, "dockerfile": dockerfile}
        base = (live.get(name) or "").strip()
        if not known(base):
            log(f"deploy {name}: live commit unknown ({base or 'none'})")
            out.append(entry)
            continue
        if base != sha and is_ancestor(sha, base):
            log(f"skip {name}: live {base[:7]} is newer than {sha[:7]}")
            continue
        if force_all:
            log(f"deploy {name}: manual run")
            out.append(entry)
            continue
        if base == sha:
            log(f"skip {name}: already live at {sha[:7]}")
            continue
        files = changed(base, sha)
        if files is None:
            log(f"deploy {name}: could not diff {base[:7]}..{sha[:7]}")
            out.append(entry)
            continue
        prefixes = (f"{src}/", f"{Path(dockerfile).parent.as_posix()}/", *SHARED, *PLUMBING)
        hits = [f for f in files if f.startswith(prefixes)]
        if hits:
            log(f"deploy {name}: {len(hits)} changed since {base[:7]} (e.g. {hits[0]})")
            out.append(entry)
        else:
            log(f"skip {name}: unchanged since {base[:7]}")
    return out


def main(argv):
    sha, live = argv[1], json.loads(argv[2] or "{}")
    matrix = plan(sha, live, "--all" in argv[3:], log=lambda m: print(m, file=sys.stderr))
    print(json.dumps(matrix, separators=(",", ":")))


if __name__ == "__main__":
    main(sys.argv)
