"""Sample Project: Database schema definition for Bookmarks Service.

This file starts in an intentional FAILING state for the demo.
The acceptance criteria requires an index on 'idx_bookmarks_url_hash'.

To repair this file during the demo:
Uncomment the repaired return statement below and comment out the failing one.
"""

def get_schema_ddl() -> str:
    # --- FAILING DEMO STATE: Missing url_hash index ---
    return """
CREATE TABLE bookmarks (
    id TEXT PRIMARY KEY,
    url TEXT NOT NULL,
    slug TEXT UNIQUE NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

    # --- REPAIRED STATE (Uncomment to pass acceptance criteria) ---
    # return """
    # CREATE TABLE bookmarks (
    #     id TEXT PRIMARY KEY,
    #     url TEXT NOT NULL,
    #     slug TEXT UNIQUE NOT NULL,
    #     created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    # );
    # CREATE INDEX idx_bookmarks_url_hash ON bookmarks(url);
    # """
