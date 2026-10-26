import unittest

import sanitise


class Sanitise(unittest.TestCase):
    def test_flags_secrets_and_phones(self):
        self.assertEqual(sanitise.scan('{"x": "AIza' + "a" * 35 + '"}'), ["google api key"])
        self.assertIn("phone number", sanitise.scan("call 9876543210"))
        self.assertIn("key in url or json", sanitise.scan("?api_key=abcdefghijklmnop1234"))

    def test_clean_fixture_passes(self):
        self.assertEqual(sanitise.scan('{"fare": 1450, "pnr": "SAMPLE0001"}'), [])


if __name__ == "__main__":
    unittest.main()
