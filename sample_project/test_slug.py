"""Unit tests for slug generator using Python's built-in unittest."""

import unittest
from slug_gen import generate_slug


class TestSlugGenerator(unittest.TestCase):
    def test_slug_deterministic(self):
        slug1 = generate_slug("https://example.com/page")
        slug2 = generate_slug("https://example.com/page")
        self.assertEqual(slug1, slug2)
        self.assertEqual(len(slug1), 8)

    def test_empty_url_rejected(self):
        with self.assertRaises(ValueError):
            generate_slug("")


if __name__ == "__main__":
    unittest.main()
