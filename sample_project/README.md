# Sample Project (Turnkey Demo Target)

This directory provides a lightweight, zero-dependency demo project using Python's built-in `unittest` module.

## Files
* `db_schema.py`: Schema DDL generator for Bookmarks Service. Starts in a **failing state** (missing the `idx_bookmarks_url_hash` index).
* `test_db_schema.py`: Verifies database schema against acceptance criteria.
* `slug_gen.py`: Deterministic slug generator.
* `test_slug.py`: Verifies slug generation.

---

## 🎬 10-Second Demo Walkthrough

### 1. Initial Test Run (Fails & Blocks Downstream DAG)
In GraphPilot, select `task-db-schema`:
* **Project Directory**: `sample_project`
* **Command**: `python -m unittest test_db_schema.py`
* Click **Run configured checks**.
* **Result**:
  * Test fails with `AssertionError: idx_bookmarks_url_hash not found`.
  * Exit code is `1`.
  * `task-db-schema` marks `FAILED`.
  * Downstream tasks (`task-link-service`, `task-api`, `task-web-ui`) immediately lock into `BLOCKED`.

### 2. Repair the Code
In `sample_project/db_schema.py`, switch to the repaired return statement:
```python
def get_schema_ddl() -> str:
    return """
    CREATE TABLE bookmarks (
        id TEXT PRIMARY KEY,
        url TEXT NOT NULL,
        slug TEXT UNIQUE NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    CREATE INDEX idx_bookmarks_url_hash ON bookmarks(url);
    """
```

### 3. Rerun Verification (Passes & Unlocks Downstream DAG)
Rerun `python -m unittest test_db_schema.py`:
* **Result**:
  * Test passes with exit code `0`.
  * `task-db-schema` transitions to `VERIFIED`.
  * Once `task-slug` is also verified, downstream `task-link-service` automatically unlocks into `READY`!
