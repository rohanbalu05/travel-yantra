import unittest

import sanitise


class Sanitise(unittest.TestCase):
    def test_flags_secrets_and_phones(self):
        self.assertEqual(sanitise.scan('{"x": "AIza' + "a" * 35 + '"}'), ["google api key"])
        self.assertIn("phone number", sanitise.scan("call 9876543210"))
        self.assertIn("key in url or json", sanitise.scan("?api_key=abcdefghijklmnop1234"))

    def test_flags_landlines(self):
        for text in ["call 0832 222 2222", "tel +91 832 2222222", "0821-2421051"]:
            self.assertIn("landline number", sanitise.scan(text), text)

    def test_ignores_coordinates_and_ids(self):
        self.assertEqual(sanitise.scan('{"lat": 15.5009, "lng": 73.9116, "id": "Q391123", "year": 1912}'), [])

    def test_clean_fixture_passes(self):
        self.assertEqual(sanitise.scan('{"fare": 1450, "pnr": "SAMPLE0001"}'), [])


if __name__ == "__main__":
    unittest.main()
