"""Core scraper orchestrator - ties all components together."""

import logging
import time
from pathlib import Path
from typing import Optional

from ..config import load_settings, load_products, load_platforms
from ..types import Platform, Product, ScraperConfig
from ..engine.dedup import is_duplicate, mark_visited
from ..engine.queue import URLQueue
from ..engine.limiter import RateLimiter, SizeTracker
from ..engine.session import SessionManager
from ..storage.organizer import ContentOrganizer
from ..storage.filesystem import format_size
from ..llm.classifier import classify_item, init_product_lookup

log = logging.getLogger(__name__)


class ScraperEngine:
    """Main scraper orchestrator that coordinates all components."""

    def __init__(self, config_dir: Path = Path("config")):
        self.config_dir = config_dir
        self.config: Optional[ScraperConfig] = None
        self.products: list[Product] = []
        self.platforms_config: dict = {}
        
        # Components (initialized in setup())
        self.rate_limiter: Optional[RateLimiter] = None
        self.size_tracker: Optional[SizeTracker] = None
        self.session_manager: Optional[SessionManager] = None
        self.queue: Optional[URLQueue] = None
        self.organizer: Optional[ContentOrganizer] = None
        
        # Platform adapters (lazy loaded)
        self._adapters: dict = {}
        
        # Progress tracking
        self.start_time: float = 0
        self.paused: bool = False

    def setup(self):
        """Initialize all components from configuration."""
        log.info("Loading configuration...")
        self.config = load_settings(self.config_dir)
        self.products = load_products(self.config_dir)
        self.platforms_config = load_platforms(self.config_dir)
        
        # Initialize product lookup for LLM classifier
        init_product_lookup(self.products)
        
        # Setup logging
        logging.basicConfig(
            level=getattr(logging, self.config.log_level),
            format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
            handlers=[
                logging.FileHandler(self.config.log_file),
                logging.StreamHandler(),
            ]
        )
        
        # Initialize components
        self.rate_limiter = RateLimiter(self.config)
        self.size_tracker = SizeTracker(self.config.total_size_limit, self.config.state_file)
        self.session_manager = SessionManager(self.config.state_file, self.config.autosave_interval)
        self.queue = URLQueue()
        self.organizer = ContentOrganizer(self.config.output_dir)
        
        # Load or create crawl state
        state = self.session_manager.load_or_create()
        
        # Restore size tracker from state
        self.size_tracker._downloaded = state.total_bytes_downloaded
        
        # Restore queue from state
        if state.queue_remaining:
            self.queue.restore_state(state.queue_remaining)
        
        self.start_time = time.time()
        
        log.info(f"Setup complete. {len(self.products)} products, "
                 f"{len(self.platforms_config)} platforms configured.")
        log.info(f"Output directory: {self.config.output_dir}")
        log.info(f"Size limit: {format_size(self.size_tracker.max_bytes)} "
                 f"({format_size(self.size_tracker.remaining)} remaining)")

    def _get_adapter(self, platform: Platform):
        """Lazy-load platform adapters."""
        if platform not in self._adapters:
            if platform == Platform.IFIXIT:
                from ..platforms.ifixit import IFixitScraper
                self._adapters[platform] = IFixitScraper(self.config, self.rate_limiter)
            elif platform == Platform.SAMSUNG:
                from ..platforms.samsung import SamsungScraper
                self._adapters[platform] = SamsungScraper(self.config, self.rate_limiter)
            elif platform == Platform.APPLE:
                from ..platforms.apple import AppleScraper
                self._adapters[platform] = AppleScraper(self.config, self.rate_limiter)
            elif platform == Platform.XIAOMI:
                from ..platforms.xiaomi import XiaomiScraper
                self._adapters[platform] = XiaomiScraper(self.config, self.rate_limiter)
            else:
                log.warning(f"No adapter available for platform: {platform}")
                return None
        return self._adapters[platform]

    def _platform_name_to_enum(self, name: str) -> Optional[Platform]:
        """Convert platform config name to Platform enum."""
        mapping = {
            'ifixit': Platform.IFIXIT,
            'samsung_parts': Platform.SAMSUNG,
            'apple_self_repair': Platform.APPLE,
            'xiaomi_service': Platform.XIAOMI,
            'repair_wiki': Platform.REPAIR_WIKI,
            'techwalls': Platform.TECHWALLS,
            'notebookcheck': Platform.NOTEBOOKCHECK,
            'fccid': Platform.FCCID,
        }
        return mapping.get(name)

    def seed_products(self):
        """Seed the URL queue with product discovery queries for each platform."""
        log.info("Seeding product discovery URLs...")
        
        for product in self.products:
            for platform_name, platform_config in self.platforms_config.items():
                platform_enum = self._platform_name_to_enum(platform_name)
                if platform_enum is None:
                    continue
                
                adapter = self._get_adapter(platform_enum)
                if adapter is None:
                    continue
                
                try:
                    guide_urls = adapter.discover_guides(product)
                    for url in guide_urls:
                        if not is_duplicate(self.session_manager.state, url):
                            self.queue.add(url, platform_enum, priority=5)
                    log.debug(f"Discovered {len(guide_urls)} URLs for {product.name} on {platform_name}")
                except Exception as e:
                    log.warning(f"Discovery failed for {product.name} on {platform_name}: {e}")
        
        log.info(f"Queue seeded with {self.queue.remaining_count()} URLs")

    def process_url(self, url: str, platform: Platform) -> int:
        """Process a single URL: scrape, classify, save. Returns bytes saved."""
        if self.size_tracker.is_full:
            return 0
        
        adapter = self._get_adapter(platform)
        if adapter is None:
            return 0
        
        bytes_saved = 0
        
        # Find matching product
        matched_product = None
        for product in self.products:
            # Try each product's keywords against the URL
            for kw in product.keywords:
                if kw.lower() in url.lower():
                    matched_product = product
                    break
            if matched_product:
                break
        
        if matched_product is None:
            # Will be classified from content later
            matched_product = None
        
        try:
            # Scrape the guide
            guide_item = adapter.scrape_guide(url, matched_product)
            
            if guide_item and guide_item.content_bytes:
                # Classify if no product matched yet
                if guide_item.matched_product is None:
                    guide_item.matched_product = classify_item(
                        title=guide_item.title,
                        content=guide_item.content_bytes.decode('utf-8', errors='replace'),
                        platform=platform,
                        all_products=self.products,
                        use_llm=self.config.llm_enabled,
                        min_confidence=self.config.llm_min_confidence,
                    )
                
                # Skip if still unmatched
                if guide_item.matched_product is None:
                    log.debug(f"Unmatched: {guide_item.title}")
                    return 0
                
                # Check size budget
                if not self.size_tracker.can_add(guide_item.size_bytes):
                    log.info("Size limit reached, stopping.")
                    return 0
                
                # Save guide
                saved = self.organizer.save_item(guide_item)
                bytes_saved += saved
                self.size_tracker.add(saved)
                
                # Scrape and save images from the guide
                image_items = adapter.scrape_images(guide_item, guide_item.matched_product)
                for img_item in image_items:
                    if img_item.content_bytes:
                        if not self.size_tracker.can_add(img_item.size_bytes):
                            break
                        saved = self.organizer.save_item(img_item)
                        bytes_saved += saved
                        self.size_tracker.add(saved)
                
                log.info(f"Saved: {guide_item.title} ({format_size(bytes_saved)})")
            
            # Mark URL as visited
            mark_visited(self.session_manager.state, url, guide_item.content_bytes if guide_item else None)
            self.session_manager.state.total_bytes_downloaded = self.size_tracker.downloaded
            self.session_manager.state.total_items_scraped += 1
            
        except Exception as e:
            log.error(f"Error processing {url}: {e}")
            mark_visited(self.session_manager.state, url)
        
        return bytes_saved

    def run(self):
        """Main crawl loop."""
        self.setup()
        self.seed_products()
        
        log.info(f"Starting crawl. Queue: {self.queue.remaining_count()} URLs")
        
        items_this_session = 0
        
        while self.queue.has_pending() and not self.size_tracker.is_full:
            next_item = self.queue.get_next()
            if next_item is None:
                break
            
            url, platform = next_item
            bytes_saved = self.process_url(url, platform)
            items_this_session += 1
            
            # Progress report every 10 items
            if items_this_session % 10 == 0:
                elapsed = time.time() - self.start_time
                log.info(f"Progress: {items_this_session} items, "
                         f"{format_size(self.size_tracker.downloaded)} downloaded "
                         f"({self.size_tracker.usage_percent:.1f}%), "
                         f"{self.queue.remaining_count()} remaining, "
                         f"{int(elapsed)}s elapsed")
            
            # Autosave state
            if self.session_manager.should_autosave():
                self.session_manager.state.queue_remaining = self.queue.save_state()
                self.session_manager.save()
        
        # Final save
        self.session_manager.state.queue_remaining = self.queue.save_state()
        self.session_manager.save()
        
        # Build index
        index = self.organizer.build_index()
        
        elapsed = time.time() - self.start_time
        log.info(f"Crawl complete. {format_size(self.size_tracker.downloaded)} total, "
                 f"{items_this_session} items this session, "
                 f"took {int(elapsed)}s")
        
        return index

    def get_status(self) -> dict:
        """Get current crawler status for CLI display."""
        return {
            'downloaded': format_size(self.size_tracker.downloaded),
            'remaining': format_size(self.size_tracker.remaining),
            'usage_percent': self.size_tracker.usage_percent,
            'queue_size': self.queue.remaining_count(),
            'elapsed': int(time.time() - self.start_time) if self.start_time else 0,
        }
