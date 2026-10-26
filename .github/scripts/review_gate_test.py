import json
import unittest

import review_gate as rg

HEAD = "a" * 40
OLD = "b" * 40
T0 = "2026-10-26T10:00:00Z"
T1 = "2026-10-26T11:00:00Z"
BOT = {"login": rg.CODEX_LOGIN}
REVIEW = {"id": 7, "user": BOT, "commit_id": OLD, "submitted_at": T1}


def state(sha):
    blob = json.dumps({"code_review": {"commit_sha": sha, "status": "completed"}})
    return {"user": BOT, "created_at": T1, "body": f"Summary\n<!-- codex-review-state:v1 {blob} -->"}


def run(**kw):
    base = dict(head=HEAD, head_date=T0, labels=[], reviews=[], comments=[], backup=None, second=None)
    base.update(kw)
    return rg.evaluate(**base)


class Gate(unittest.TestCase):
    def test_codex_review_on_older_commit_plus_second_passes(self):
        self.assertEqual(run(reviews=[REVIEW], second="success")[0], "success")

    def test_codex_state_comment_counts_as_posted(self):
        self.assertEqual(run(comments=[state(OLD)], second="success")[0], "success")

    def test_second_review_required(self):
        self.assertEqual(run(reviews=[REVIEW]), ("pending", "waiting for second review", False))
        self.assertEqual(run(reviews=[REVIEW], second="pending")[0], "pending")

    def test_second_review_failure_or_error_fails(self):
        for s in ("failure", "error"):
            self.assertEqual(run(reviews=[REVIEW], second=s)[0], "failure")

    def test_codex_missing_is_pending(self):
        self.assertEqual(run(second="success"), ("pending", "waiting for first review", False))

    def test_backup_success_replaces_codex(self):
        self.assertEqual(run(backup="success", second="success")[0], "success")

    def test_backup_failure_fails(self):
        self.assertEqual(run(backup="failure", second="success")[0], "failure")

    def test_usage_limit_dispatches_backup_once(self):
        limit = {"user": BOT, "created_at": T1, "body": "You have reached your Codex usage limits."}
        self.assertEqual(run(comments=[limit]), ("pending", "Codex usage limit; backup review requested", True))
        self.assertFalse(run(comments=[limit], backup="pending")[2])

    def test_needs_rohan_blocks_until_rohan_ok(self):
        ok = dict(reviews=[REVIEW], second="success")
        self.assertEqual(run(labels=["needs-rohan"], **ok)[0], "failure")
        self.assertEqual(run(labels=["needs-rohan", "rohan-ok"], **ok)[0], "success")

    def test_other_authors_are_ignored(self):
        fake = dict(REVIEW, user={"login": "someone"})
        self.assertEqual(run(reviews=[fake], second="success")[0], "pending")


if __name__ == "__main__":
    unittest.main()
