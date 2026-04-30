"""Core scraping engine module."""

from .dedup import is_duplicate, mark_visited, content_hash, url_hash
from .queue import URLQueue
from .limiter import RateLimiter, SizeTracker
from .session import SessionManager
