import unittest

from selecto_radio.metadata import parse_title


class MetadataTests(unittest.TestCase):
    def test_parse_title_normalizes_whitespace(self) -> None:
        self.assertEqual(parse_title(b'{"titulo": "DJ  Name\\nLive"}'), "DJ Name Live")

    def test_parse_title_rejects_invalid_json(self) -> None:
        with self.assertRaises(ValueError):
            parse_title(b"not json")
