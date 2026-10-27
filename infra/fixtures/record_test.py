import io
import unittest
from contextlib import redirect_stdout

import record
import sanitise


class Scrub(unittest.TestCase):
    def test_drops_phones_and_reviews(self):
        out = record.scrub({"places": [{"id": "x", "nationalPhoneNumber": "0832 222 2222",
                                        "reviews": [{"text": "ok"}], "rating": 4.5}]})
        self.assertEqual(out, {"places": [{"id": "x", "rating": 4.5}]})

    def test_redacts_key_parameters(self):
        out = record.scrub({"link": "https://serpapi.com/search.json?engine=google_flights&api_key=abcdefghijklmnop1234"})
        self.assertNotIn("abcdefghijklmnop1234", out["link"])
        self.assertEqual(sanitise.scan(str(out)), [])


class Plan(unittest.TestCase):
    def test_plan_makes_no_calls_and_stays_in_serpapi_budget(self):
        rec = record.Recorder("unused", plan=True)
        for fn in record.PROVIDERS.values():
            fn(rec)
        self.assertLessEqual(rec.serpapi, record.SERPAPI_MAX)
        self.assertEqual(rec.serpapi, 8)
        self.assertTrue(all("api_key=REDACTED" in u for p, u in rec.calls if p == "serpapi"))

    def test_cli_plan(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            self.assertEqual(record.main(["--out", "unused", "--plan"]), 0)
        self.assertIn("serpapi 8/10", buf.getvalue())


if __name__ == "__main__":
    unittest.main()
