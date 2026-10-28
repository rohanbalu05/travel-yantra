import unittest

import deploy_plan

NEW, OLD, NEWER = "b" * 40, "a" * 40, "c" * 40
ORDER = {OLD: 0, NEW: 1, NEWER: 2}  # a straight line of commits


def run(live, files=(), force_all=False, missing=()):
    logs = []
    out = deploy_plan.plan(
        NEW, live, force_all,
        exists=lambda p: not any(p.startswith(m) for m in missing),
        known=lambda s: s in ORDER,
        is_ancestor=lambda a, b: ORDER[a] <= ORDER[b],
        changed=lambda base, head: list(files),
        log=logs.append,
    )
    return [e["name"] for e in out], logs


ALL_OLD = {name: OLD for name, _, _ in deploy_plan.SERVICES}


class DeployPlan(unittest.TestCase):
    def test_only_changed_service_ships(self):
        names, _ = run(ALL_OLD, ["apps/web/app/page.tsx"])
        self.assertEqual(names, ["ty-web"])

    def test_web_dockerfile_dir_counts_for_web(self):
        names, _ = run(ALL_OLD, ["infra/web/Dockerfile"])
        self.assertEqual(names, ["ty-web"])

    def test_contracts_and_plumbing_ship_everything(self):
        every = [n for n, _, _ in deploy_plan.SERVICES]
        self.assertEqual(run(ALL_OLD, ["packages/contracts/x.py"])[0], every)
        self.assertEqual(run(ALL_OLD, [".github/workflows/deploy.yml"])[0], every)
        self.assertEqual(run(ALL_OLD, ["infra/cloudbuild/image.yaml"])[0], every)

    def test_unrelated_change_ships_nothing(self):
        self.assertEqual(run(ALL_OLD, ["bench/README.md"])[0], [])

    def test_unknown_live_commit_deploys(self):
        names, logs = run({**ALL_OLD, "ty-api": ""}, [])
        self.assertEqual(names, ["ty-api"])
        self.assertIn("live commit unknown", logs[0])

    def test_already_live_is_skipped_even_on_manual_run(self):
        names, _ = run({**ALL_OLD, "ty-mcp": NEW}, ["apps/mcp/x.py"])
        self.assertNotIn("ty-mcp", names)
        names, _ = run({**ALL_OLD, "ty-mcp": NEW}, force_all=True)
        self.assertIn("ty-mcp", names)

    def test_never_replaces_a_newer_live_commit(self):
        names, logs = run({**ALL_OLD, "ty-web": NEWER}, ["apps/web/x.ts"], force_all=True)
        self.assertNotIn("ty-web", names)
        self.assertTrue(any("is newer" in m for m in logs))

    def test_missing_dockerfile_or_project_is_skipped(self):
        names, _ = run(ALL_OLD, ["apps/mcp/x.py"], missing=("apps/mcp/Dockerfile",))
        self.assertEqual(names, [])
        names, _ = run(ALL_OLD, ["apps/mcp/x.py"], missing=("apps/mcp/pyproject.toml", "apps/mcp/package.json"))
        self.assertEqual(names, [])


if __name__ == "__main__":
    unittest.main()
