"""Session state persistence for resume support."""

import json
import time
import threading
from pathlib import Path
from typing import Optional

from ..types import CrawlState


class SessionManager:
    """Manages serialization and restoration of crawl state."""

    def __init__(self, state_file: Path, autosave_interval: int = 60):
        self.state_file = state_file
        self.autosave_interval = autosave_interval
        self._state: Optional[CrawlState] = None
        self._last_save = 0.0
        self._lock = threading.Lock()

    def create_new(self) -> CrawlState:
        """Create a fresh crawl state."""
        self._state = CrawlState()
        return self._state

    def load_or_create(self) -> CrawlState:
        """Load existing state or create new one."""
        if self.state_file.exists():
            return self.load()
        return self.create_new()

    def load(self) -> CrawlState:
        """Load crawl state from disk."""
        with open(self.state_file, 'r', encoding='utf-8') as f:
            raw = json.load(f)
        state = CrawlState(
            total_bytes_downloaded=raw.get('total_bytes_downloaded', 0),
            total_items_scraped=raw.get('total_items_scraped', 0),
            urls_visited=set(raw.get('urls_visited', [])),
            content_hashes=set(raw.get('content_hashes', [])),
            queue_remaining=raw.get('queue_remaining', []),
        )
        self._state = state
        return state

    def save(self):
        """Save current state to disk (thread-safe)."""
        if self._state is None:
            return
        with self._lock:
            self._state.last_updated = time.time()
            data = {
                'total_bytes_downloaded': self._state.total_bytes_downloaded,
                'total_items_scraped': self._state.total_items_scraped,
                'urls_visited': list(self._state.urls_visited),
                'content_hashes': list(self._state.content_hashes),
                'queue_remaining': self._state.queue_remaining,
                'started_at': self._state.started_at.isoformat(),
                'last_updated': self._state.last_updated.isoformat(),
            }
            self.state_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.state_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, default=str)
            self._last_save = time.time()

    def should_autosave(self) -> bool:
        """Check if enough time has passed since last save."""
        return time.time() - self._last_save >= self.autosave_interval

    @property
    def state(self) -> Optional[CrawlState]:
        return self._state
