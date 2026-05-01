"""Core scraper orchestrator - ties all components together."""

import logging
import os
import time
import traceback
from pathlib import Path
from typing import Optional

# Force UTF-8 for all file I/O on Windows
os.environ.setdefault('PYTHONIOENCODING', 'utf-8')

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
        self.completed_products: list[Product] = []  # Already-downloaded products

    def setup(self, size_override: Optional[int] = None, brands: Optional[list[str]] = None):
        """Initialize all components from configuration.
        
        Args:
            size_override: Override total_size_limit from config (bytes)
            brands: Filter products to only these brands (e.g. ['apple', 'samsung'])
        """
        log.info("Loading configuration...")
        self.config = load_settings(self.config_dir)
        self.products = load_products(self.config_dir)
        
        # Filter by brands if specified
        if brands:
            brands_lower = [b.lower() for b in brands]
            self.products = [p for p in self.products if p.brand.lower() in brands_lower]
            if not self.products:
                available = sorted(set(p.brand for p in load_products(self.config_dir)))
                raise ValueError(f"No products match brands: {brands}. Available: {available}")
            log.info(f"Filtered to {len(self.products)} products from brands: {brands}")
        
        self.platforms_config = load_platforms(self.config_dir)
        
        # Size override
        effective_size = size_override if size_override else self.config.total_size_limit
        
        # Initialize product lookup for LLM classifier
        init_product_lookup(self.products)
        
        # Setup logging with traceback support — UTF-8 for Windows compatibility
        log_format = '%(asctime)s [%(levelname)s] %(name)s:%(lineno)d: %(message)s'
        error_log = self.config.output_dir / "errors.log"
        logging.basicConfig(
            level=getattr(logging, self.config.log_level),
            format=log_format,
            handlers=[
                logging.FileHandler(self.config.log_file, encoding='utf-8'),
                logging.FileHandler(error_log, encoding='utf-8'),
                logging.StreamHandler(),
            ]
        )
        # errors.log only gets WARNING+
        for handler in logging.getLogger().handlers:
            if hasattr(handler, 'baseFilename') and 'errors.log' in handler.baseFilename:
                handler.setLevel(logging.WARNING)
        
        # Initialize components
        self.rate_limiter = RateLimiter(self.config)
        self.size_tracker = SizeTracker(effective_size, self.config.state_file)
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
        
        # Check for already-downloaded products
        self._skip_completed_products()

    def _skip_completed_products(self):
        """Scan manuals/ for products that already have content, and skip them.
        
        A product is considered 'done' if its folder exists and contains any files
        (guides, images, or manuals). Skipped products are logged and removed from
        self.products.
        """
        if not self.config.output_dir.exists():
            return
        
        completed = []
        still_needed = []
        
        for product in self.products:
            product_dir = self.organizer.product_folder(product)
            if product_dir.exists() and self._has_content(product_dir):
                completed.append(product)
            else:
                still_needed.append(product)
        
        if completed:
            self.products = still_needed
            names = [f"{p.brand}/{p.name}" for p in completed]
            log.info(f"Skipping {len(completed)} already-downloaded products: {', '.join(names[:10])}")
            if len(names) > 10:
                log.info(f"  ... and {len(names) - 10} more")
            self.completed_products = completed
        else:
            self.completed_products = []

    @staticmethod
    def _has_content(folder: Path) -> bool:
        """Check if a product folder contains any downloaded files."""
        for sub in ('guides', 'images', 'manuals', 'teardowns', 'schematics', 'specs'):
            subdir = folder / sub
            if subdir.exists():
                if any(f.is_file() for f in subdir.iterdir()):
                    return True
        return False

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
                    log.warning(f"Discovery failed for {product.name} on {platform_name}: {e}", exc_info=True)
        
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
                if not self.size_tracker.can_add(guide_item.size_bytes, guide_item.title):
                    log.warning(f"Size limit reached — skipping: {guide_item.title} ({format_size(guide_item.size_bytes)})")
                    return 0
                
                # Save guide
                saved = self.organizer.save_item(guide_item)
                bytes_saved += saved
                self.size_tracker.add(saved)
                
                # Scrape and save images from the guide
                image_items = adapter.scrape_images(guide_item, guide_item.matched_product)
                for img_item in image_items:
                    if img_item.content_bytes:
                        if not self.size_tracker.can_add(img_item.size_bytes, img_item.title):
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
            log.error(f"Error processing {url}: {e}", exc_info=True)
            mark_visited(self.session_manager.state, url)
        
        return bytes_saved

    def run(self, size_override: Optional[int] = None, brands: Optional[list[str]] = None):
        """Main crawl loop.
        
        Args:
            size_override: Override config's total_size_limit (bytes)
            brands: Only scrape these brands (e.g. ['apple', 'samsung'])
        """
        self.setup(size_override=size_override, brands=brands)
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
        
        # Warn if items were skipped due to size limit
        if self.size_tracker.skipped_files:
            log.warning(
                f"Size limit too small — {len(self.size_tracker.skipped_files)} items skipped "
                f"(need ~{format_size(self.size_tracker.skipped_total_bytes)} more). "
                f"Try a larger limit next time."
            )
            for fname, size in self.size_tracker.skipped_files[:5]:
                log.warning(f"  Skipped: {fname} ({format_size(size)})")
        
        return index

    def get_status(self) -> dict:
        """Get current crawler status for CLI display."""
        return {
            'downloaded': format_size(self.size_tracker.downloaded if self.size_tracker else 0),
            'limit': format_size(self.size_tracker.max_bytes if self.size_tracker else 0),
            'remaining': format_size(self.size_tracker.remaining if self.size_tracker else 0),
            'usage_percent': self.size_tracker.usage_percent if self.size_tracker else 0,
            'queue_size': self.queue.remaining_count() if self.queue else 0,
            'elapsed': int(time.time() - self.start_time) if self.start_time else 0,
            'skipped_count': len(self.size_tracker.skipped_files) if self.size_tracker else 0,
            'skipped_bytes': format_size(self.size_tracker.skipped_total_bytes) if self.size_tracker else '0 B',
            'skipped_files': self.size_tracker.skipped_files[-5:] if self.size_tracker else [],
            'brands': sorted(set(p.brand for p in self.products)) if self.products else [],
            'completed': [f"{p.brand}/{p.name}" for p in (self.completed_products or [])],
        }
