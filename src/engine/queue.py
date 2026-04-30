"""URL queue management for multi-platform crawling."""

from collections import deque
from typing import Optional

from ..types import CrawlState, Platform


class URLQueue:
    """Priority queue for URLs across multiple platforms.
    
    Implements breadth-first crawling with round-robin across platforms.
    """

    def __init__(self):
        self._queues: dict[Platform, deque[tuple[int, str]]] = {}
        self._platform_order: list[Platform] = []

    def add(self, url: str, platform: Platform, priority: int = 0):
        """Add a URL to the queue for a specific platform.
        
        Lower priority number = higher priority (0 = highest).
        """
        if platform not in self._queues:
            self._queues[platform] = deque()
            self._platform_order.append(platform)
        self._queues[platform].append((priority, url))

    def extend(self, urls: list[tuple[str, Platform]], priority: int = 0):
        """Add multiple URLs with the same priority."""
        for url, platform in urls:
            self.add(url, platform, priority)

    def get_next(self) -> Optional[tuple[str, Platform]]:
        """Get the next URL to crawl, round-robin across platforms."""
        if not self._platform_order:
            return None
        # Rotate: take from first platform, move to end
        for _ in range(len(self._platform_order)):
            platform = self._platform_order.pop(0)
            if platform in self._queues and self._queues[platform]:
                _, url = self._queues[platform].popleft()
                self._platform_order.append(platform)
                return (url, platform)
            # Empty queue for this platform, don't re-add
        return None

    def has_pending(self) -> bool:
        """Check if any URLs remain in any queue."""
        return any(len(q) > 0 for q in self._queues.values())

    def remaining_count(self) -> int:
        """Total number of URLs waiting."""
        return sum(len(q) for q in self._queues.values())

    def save_state(self) -> list[tuple[str, Platform]]:
        """Serialize remaining queue for session resumption."""
        items = []
        for platform, queue in self._queues.items():
            for _, url in queue:
                items.append((url, platform))
        return items

    def restore_state(self, items: list[tuple[str, Platform]]):
        """Restore queue from saved state."""
        for url, platform in items:
            self.add(url, platform)
