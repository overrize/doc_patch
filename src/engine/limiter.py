"""Rate limiter and download size tracker."""

import time
import threading
from pathlib import Path

from ..config import ScraperConfig
from ..types import Platform


class RateLimiter:
    """Enforces per-domain rate limits using token bucket algorithm."""

    def __init__(self, config: ScraperConfig):
        self.default_rate = config.rate_limits.get('default', 1.0)
        self.domain_rates = config.rate_limits
        self._last_request: dict[str, float] = {}
        self._lock = threading.Lock()

    def wait(self, domain: str):
        """Block until it's safe to make a request to the given domain."""
        rate = self.domain_rates.get(domain, self.default_rate)
        delay = 1.0 / rate if rate > 0 else 0

        with self._lock:
            now = time.time()
            last = self._last_request.get(domain, 0)
            wait_time = delay - (now - last)
            if wait_time > 0:
                time.sleep(wait_time)
            self._last_request[domain] = time.time()

    def domain_from_platform(self, platform: Platform) -> str:
        """Get the domain string for a platform."""
        mapping = {
            Platform.IFIXIT: "ifixit.com",
            Platform.SAMSUNG: "samsung.com",
            Platform.APPLE: "apple.com",
            Platform.XIAOMI: "xiaomi.com",
            Platform.FCCID: "fccid.io",
            Platform.REPAIR_WIKI: "repair.wiki",
            Platform.TECHWALLS: "techwalls.com",
            Platform.NOTEBOOKCHECK: "notebookcheck.net",
        }
        return mapping.get(platform, "default")


class SizeTracker:
    """Tracks total downloaded bytes, enforces size limit, logs skips."""

    def __init__(self, max_bytes: int, state_file: Path):
        self.max_bytes = max_bytes
        self.state_file = state_file
        self._downloaded = 0
        self._lock = threading.Lock()
        self.skipped_files: list[tuple[str, int]] = []  # (filename, bytes_needed)
        self.skipped_total_bytes: int = 0

    @property
    def downloaded(self) -> int:
        return self._downloaded

    @property
    def remaining(self) -> int:
        return max(0, self.max_bytes - self._downloaded)

    @property
    def is_full(self) -> bool:
        return self._downloaded >= self.max_bytes

    @property
    def usage_percent(self) -> float:
        return (self._downloaded / self.max_bytes) * 100 if self.max_bytes else 0

    def can_add(self, size: int, filename: str = "") -> bool:
        """Check if adding this many bytes would exceed the limit.
        
        If it would exceed, records the skip for reporting.
        """
        ok = self._downloaded + size <= self.max_bytes
        if not ok and filename:
            self.skipped_files.append((filename, size))
            self.skipped_total_bytes += size
        return ok

    def add(self, size: int):
        """Record downloaded bytes."""
        with self._lock:
            self._downloaded += size

    def reset(self):
        with self._lock:
            self._downloaded = 0
