"""Content deduplication via URL and content hash."""

import hashlib
from typing import Optional

from .types import CrawlState


def content_hash(data: bytes) -> str:
    """Compute SHA-256 hash of content for deduplication."""
    return hashlib.sha256(data).hexdigest()


def url_hash(url: str) -> str:
    """Normalize and hash a URL for dedup."""
    # Strip trailing slashes and fragments for normalization
    normalized = url.split('#')[0].rstrip('/').lower()
    return hashlib.sha256(normalized.encode()).hexdigest()


def is_duplicate(state: CrawlState, url: str, data: Optional[bytes] = None) -> bool:
    """Check if a URL or content has already been visited."""
    url_key = url_hash(url)
    if url_key in state.urls_visited:
        return True
    if data:
        ch = content_hash(data)
        if ch in state.content_hashes:
            return True
    return False


def mark_visited(state: CrawlState, url: str, data: Optional[bytes] = None):
    """Record a URL as visited and optionally record content hash."""
    state.urls_visited.add(url_hash(url))
    if data:
        state.content_hashes.add(content_hash(data))
