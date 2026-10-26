import json
import unittest

import backup_review as br


class Backup(unittest.TestCase):
    def test_parse_drops_unknown_severity(self):
        text = json.dumps({"findings": [{"severity": "P1", "file": "a.py", "message": "x"},
                                        {"severity": "high", "file": "b.py", "message": "y"}]})
        self.assertEqual(len(br.parse_findings(text)), 1)

    def test_bad_json_raises(self):
        with self.assertRaises(ValueError):
            br.parse_findings("not json")

    def test_verdict(self):
        self.assertEqual(br.verdict([{"severity": "P2"}]), "success")
        self.assertEqual(br.verdict([{"severity": "P0"}]), "failure")
        self.assertEqual(br.verdict([], truncated=True), "failure")

    def test_truncate_notes_cut(self):
        out, cut = br.truncate("x" * 30, limit=10)
        self.assertTrue(cut)
        self.assertIn("[diff truncated]", out)
        self.assertEqual(br.truncate("abc"), ("abc", False))

    def test_render_clean_and_with_findings(self):
        self.assertIn("No P0 or P1", br.render([], False))
        out = br.render([{"severity": "P1", "file": "a.py", "line": 3, "message": "bug"}], True)
        self.assertIn("**P1** `a.py:3` bug", out)
        self.assertIn("truncated", out)


if __name__ == "__main__":
    unittest.main()
