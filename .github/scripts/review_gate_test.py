import json
import unittest

import review_gate as rg

HEAD = "a" * 40
OLD = "b" * 40
T0 = "2026-10-26T10:00:00Z"
T1 = "2026-10-26T11:00:00Z"
BOT = {"login": rg.CODEX_LOGIN}


def state(sha, status="completed", unresolved=False):
    blob = json.dumps({"code_review": {"commit_sha": sha, "has_any_findings": unresolved,
                                       "has_unresolved_findings": unresolved, "status": status}})
    return {"user": BOT, "created_at": T1, "body": f"Summary\n<!-- codex-review-state:v1 {blob} -->"}


def run(**kw):
    base = dict(head=HEAD, head_date=T0, labels=[], reviews=[], inline=[], comments=[], reactions=[], backup=None)
    base.update(kw)
    return rg.evaluate(**base)


class Gate(unittest.TestCase):
    def test_state_comment_clean_passes(self):
        self.assertEqual(run(comments=[state(HEAD)])[0], "success")

    def test_state_comment_unresolved_fails(self):
        self.assertEqual(run(comments=[state(HEAD, unresolved=True)])[0], "failure")

    def test_state_for_old_sha_is_pending(self):
        self.assertEqual(run(comments=[state(OLD)])[0], "pending")

    def test_state_running_is_pending(self):
        self.assertEqual(run(comments=[state(HEAD, status="running")])[0], "pending")

    def test_thumbs_up_passes_only_if_newer_than_head(self):
        up = {"user": BOT, "content": "+1", "created_at": T1}
        stale = {"user": BOT, "content": "+1", "created_at": "2026-10-26T09:00:00Z"}
        self.assertEqual(run(reactions=[up])[0], "success")
        self.assertEqual(run(reactions=[stale])[0], "pending")

    def test_inline_badge_fallback(self):
        review = {"id": 7, "user": BOT, "commit_id": HEAD, "submitted_at": T1}
        p1 = {"user": BOT, "pull_request_review_id": 7, "body": "![P1 Badge](https://img.shields.io/badge/P1-orange) bug"}
        p2 = {"user": BOT, "pull_request_review_id": 7, "body": "![P2 Badge](https://img.shields.io/badge/P2-yellow) nit"}
        self.assertEqual(run(reviews=[review], inline=[p1, p2])[0], "failure")
        self.assertEqual(run(reviews=[review], inline=[p2])[0], "success")

    def test_backup_success_overrides_codex_findings(self):
        self.assertEqual(run(comments=[state(HEAD, unresolved=True)], backup="success")[0], "success")

    def test_usage_limit_dispatches_backup_once(self):
        limit = {"user": BOT, "created_at": T1, "body": "You have reached your Codex usage limits."}
        self.assertEqual(run(comments=[limit]), ("pending", "Codex usage limit; backup review requested", True))
        self.assertFalse(run(comments=[limit], backup="pending")[2])

    def test_backup_failure_fails(self):
        self.assertEqual(run(backup="failure")[0], "failure")

    def test_needs_rohan_blocks_until_rohan_ok(self):
        self.assertEqual(run(labels=["needs-rohan"], comments=[state(HEAD)])[0], "failure")
        self.assertEqual(run(labels=["needs-rohan", "rohan-ok"], comments=[state(HEAD)])[0], "success")

    def test_other_authors_are_ignored(self):
        fake = dict(state(HEAD), user={"login": "someone"})
        self.assertEqual(run(comments=[fake])[0], "pending")


if __name__ == "__main__":
    unittest.main()
