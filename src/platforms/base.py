"""Abstract base class for platform-specific scrapers."""

import logging
import requests
from abc import ABC, abstractmethod
from typing import Optional

from ..types import ScrapedItem, Platform, Product, ScraperConfig
from ..engine.limiter import RateLimiter

log = logging.getLogger(__name__)


class BasePlatformScraper(ABC):
    """Base class for all platform-specific scrapers.
    
    Each platform adapter implements the scraping logic for one repair guide source.
    """

    def __init__(self, config: ScraperConfig, rate_limiter: RateLimiter):
        self.config = config
        self.rate_limiter = rate_limiter
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': config.user_agent,
            'Accept': 'text/html,application/json,*/*',
        })
        self.session.timeout = config.request_timeout

    @property
    @abstractmethod
    def platform(self) -> Platform:
        """Return the Platform enum value for this scraper."""
        ...

    @abstractmethod
    def discover_guides(self, product: Product) -> list[str]:
        """Discover guide URLs for a specific product.
        
        Returns list of guide page URLs.
        """
        ...

    @abstractmethod
    def scrape_guide(self, url: str, product: Product) -> Optional[ScrapedItem]:
        """Scrape a single guide page into a ScrapedItem.
        
        Returns None if the page couldn't be scraped.
        """
        ...

    @abstractmethod
    def scrape_images(self, guide_item: ScrapedItem, product: Product) -> list[ScrapedItem]:
        """Extract and download images from a scraped guide.
        
        Returns list of image ScrapedItem objects.
        """
        ...

    def _get(self, url: str, **kwargs) -> requests.Response:
        """Rate-limited GET request with retries."""
        self.rate_limiter.wait(self.rate_limiter.domain_from_platform(self.platform))
        for attempt in range(self.config.max_retries):
            try:
                resp = self.session.get(url, timeout=self.config.request_timeout, **kwargs)
                resp.raise_for_status()
                return resp
            except requests.RequestException as e:
                log.warning(f"Request failed (attempt {attempt+1}/{self.config.max_retries}): {url} - {e}")
                if attempt < self.config.max_retries - 1:
                    import time
                    time.sleep(self.config.retry_delay)
                else:
                    raise

    def _get_json(self, url: str, **kwargs) -> dict:
        """Rate-limited GET request expecting JSON response."""
        resp = self._get(url, **kwargs)
        return resp.json()

    def _download_file(self, url: str) -> Optional[bytes]:
        """Download a binary file (image, PDF). Returns bytes or None."""
        try:
            self.rate_limiter.wait(self.rate_limiter.domain_from_platform(self.platform))
            resp = self.session.get(url, timeout=self.config.request_timeout)
            resp.raise_for_status()
            if len(resp.content) > self.config.max_file_size:
                log.warning(f"File too large ({len(resp.content)} bytes): {url}")
                return None
            return resp.content
        except Exception as e:
            log.warning(f"Download failed: {url} - {e}")
            return None

    @staticmethod
    def _get_text(resp) -> str:
        """Decode response content as UTF-8, with replacement for bad bytes.
        
        Use this instead of resp.text to avoid Windows GBK encoding issues.
        """
        return resp.content.decode('utf-8', errors='replace')
