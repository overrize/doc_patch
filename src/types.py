"""Shared type definitions and constants for the scraper."""

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional
from datetime import datetime


class ContentType(Enum):
    GUIDE = "guide"       # Text/html repair guide
    MANUAL = "manual"     # PDF service manual
    IMAGE = "image"       # Repair process image
    SCHEMATIC = "schematic"  # Circuit/schematic diagram
    TEARDOWN = "teardown"  # Teardown photos
    SPECS = "specs"        # Device specifications


class Platform(Enum):
    IFIXIT = "ifixit"
    SAMSUNG = "samsung"
    APPLE = "apple"
    XIAOMI = "xiaomi"
    FCCID = "fccid"
    REPAIR_WIKI = "repair_wiki"
    TECHWALLS = "techwalls"
    NOTEBOOKCHECK = "notebookcheck"


@dataclass
class Product:
    """A target product to collect repair info for."""
    brand: str          # e.g. "Apple", "Samsung", "Xiaomi"
    name: str           # e.g. "iPhone 15 Pro"
    keywords: list[str] # Search/matching keywords
    folder_name: str    # Filesystem-safe folder name

    def __hash__(self):
        return hash((self.brand, self.name))


@dataclass
class ScrapedItem:
    """Represents a single scraped item (guide, image, manual, etc.)."""
    url: str
    title: str
    content_type: ContentType
    platform: Platform
    source_url: str         # The page this item was found on
    file_extension: str     # e.g. ".html", ".pdf", ".jpg"
    matched_product: Optional["Product"] = None
    content_bytes: Optional[bytes] = None
    file_path: Optional[Path] = None
    scraped_at: datetime = field(default_factory=datetime.now)
    content_hash: str = ""  # SHA-256 hash for dedup

    @property
    def size_bytes(self) -> int:
        return len(self.content_bytes) if self.content_bytes else 0

    @property
    def is_image(self) -> bool:
        return self.file_extension.lower() in {'.jpg', '.jpeg', '.png', '.gif', '.webp'}


@dataclass
class CrawlState:
    """Serializable state for resume support."""
    total_bytes_downloaded: int = 0
    total_items_scraped: int = 0
    urls_visited: set[str] = field(default_factory=set)
    content_hashes: set[str] = field(default_factory=set)
    queue_remaining: list[tuple[str, Platform]] = field(default_factory=list)
    started_at: datetime = field(default_factory=datetime.now)
    last_updated: datetime = field(default_factory=datetime.now)


@dataclass
class ScraperConfig:
    """Runtime configuration loaded from YAML."""
    total_size_limit: int
    rate_limits: dict[str, float]
    request_timeout: int
    max_retries: int
    retry_delay: int
    user_agent: str
    state_file: Path
    autosave_interval: int
    min_guide_words: int
    allowed_extensions: set[str]
    max_file_size: int
    llm_enabled: bool
    llm_provider: str
    llm_model: str
    llm_min_confidence: float
    log_level: str
    log_file: Path
    output_dir: Path
