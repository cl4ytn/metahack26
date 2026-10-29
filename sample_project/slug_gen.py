"""Sample Project: Deterministic slug generation for Bookmarks Service."""

import hashlib


def generate_slug(url: str) -> str:
    """Generate deterministic 8-character hex slug from URL."""
    if not url:
        raise ValueError("URL cannot be empty")
    return hashlib.sha256(url.encode("utf-8")).hexdigest()[:8]
