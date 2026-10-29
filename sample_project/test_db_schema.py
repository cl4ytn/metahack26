"""Unit tests for Bookmarks Service database schema using Python's built-in unittest."""

import unittest
from db_schema import get_schema_ddl


class TestDatabaseSchema(unittest.TestCase):
    def test_acceptance_criteria(self):
        ddl = get_schema_ddl()
        self.assertIn(
            "CREATE TABLE bookmarks",
            ddl,
            "Acceptance criteria failed: missing bookmarks table definition"
        )
        self.assertIn(
            "idx_bookmarks_url_hash",
            ddl,
            "Acceptance criteria failed: missing index on url_hash (idx_bookmarks_url_hash)"
        )


if __name__ == "__main__":
    unittest.main()
