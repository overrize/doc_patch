"""Xiaomi repair guide scraper adapter.

Discovers and scrapes repair guides from:
- Xiaomi Support Articles (mi.com/global/support/article/KA-{id}/)
- DIYGeardo (diygeardo.com/category/xiaomi/)
"""

import hashlib
import logging
import re
from html.parser import HTMLParser
from typing import Optional
from urllib.parse import urljoin, urlparse, quote_plus

from ..types import ScrapedItem, ContentType, Platform, Product
from .base import BasePlatformScraper

log = logging.getLogger(__name__)

# Regex patterns
KA_ARTICLE_PATTERN = re.compile(r'/global/support/article/KA-\d+/', re.IGNORECASE)
KA_ID_PATTERN = re.compile(r'KA-(\d+)', re.IGNORECASE)
MODEL_NUMBER_PATTERN = re.compile(r'\b[0-9]{4,}[a-z0-9]{2,6}[cg]?\b', re.IGNORECASE)
GUIDE_URL_PATTERNS = [
    re.compile(p, re.IGNORECASE) for p in [
        r'/global/support/article/',
        r'/category/xiaomi/',
        r'/guides?/',
        r'/repair/',
        r'/teardown/',
        r'/disassembly/',
        r'/replacement/',
        r'/fix/',
        r'/how-to/',
        r'ka-\d+',
    ]
]

# Page regions likely to contain the main guide content
CONTENT_SELECTORS_PATTERNS = [
    re.compile(r'<article[^>]*>(.*?)</article>', re.DOTALL | re.IGNORECASE),
    re.compile(r'<main[^>]*>(.*?)</main>', re.DOTALL | re.IGNORECASE),
    re.compile(r'<div[^>]*class="[^"]*content[^"]*"[^>]*>(.*?)</div>', re.DOTALL | re.IGNORECASE),
    re.compile(r'<div[^>]*class="[^"]*article[^"]*"[^>]*>(.*?)</div>', re.DOTALL | re.IGNORECASE),
    re.compile(r'<div[^>]*class="[^"]*post[^"]*"[^>]*>(.*?)</div>', re.DOTALL | re.IGNORECASE),
    re.compile(r'<div[^>]*class="[^"]*entry[^"]*"[^>]*>(.*?)</div>', re.DOTALL | re.IGNORECASE),
]


class _LinkExtractor(HTMLParser):
    """Extract all <a href> links from HTML."""

    def __init__(self):
        super().__init__()
        self.links: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]):
        if tag.lower() == 'a':
            href = dict(attrs).get('href')
            if href:
                self.links.append(href)


class _ImageExtractor(HTMLParser):
    """Extract all <img src> URLs from HTML."""

    def __init__(self):
        super().__init__()
        self.images: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]):
        if tag.lower() == 'img':
            attr_dict = dict(attrs)
            src = attr_dict.get('src')
            if src:
                self.images.append(src)


def _extract_text(html: str) -> str:
    """Strip HTML tags and return plain text."""
    # Remove script and style elements with their contents
    html = re.sub(r'<(script|style|nav|header|footer|noscript)[^>]*>.*?</\1>',
                  '', html, flags=re.DOTALL | re.IGNORECASE)
    # Remove remaining HTML tags
    text = re.sub(r'<[^>]+>', ' ', html)
    # Normalize whitespace
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def _extract_title(html: str) -> str:
    """Extract page title from HTML."""
    # Try <title> tag first
    m = re.search(r'<title[^>]*>(.*?)</title>', html, re.IGNORECASE | re.DOTALL)
    if m:
        return _extract_text(m.group(1)).strip()

    # Try <h1> tag
    m = re.search(r'<h1[^>]*>(.*?)</h1>', html, re.IGNORECASE | re.DOTALL)
    if m:
        return _extract_text(m.group(1)).strip()

    # Try og:title meta
    m = re.search(r'<meta[^>]+property="og:title"[^>]+content="([^"]*)"', html, re.IGNORECASE)
    if m:
        return m.group(1).strip()

    return "Untitled"


def _extract_main_content(html: str) -> str:
    """Extract the main content region from HTML."""
    for pattern in CONTENT_SELECTORS_PATTERNS:
        m = pattern.search(html)
        if m:
            return m.group(1)
    return html


def _word_count(text: str) -> int:
    """Count words in text."""
    return len(text.split())


def _keyword_matches(text: str, keywords: list[str]) -> bool:
    """Check if any keyword matches the text."""
    text_lower = text.lower()
    for kw in keywords:
        kw_lower = kw.lower()
        if kw_lower in text_lower:
            return True
        # Also try matching model numbers from keywords
        if re.search(r'\d{4,}', kw_lower):
            if kw_lower in text_lower:
                return True
    return False


class XiaomiScraper(BasePlatformScraper):
    """Scraper for Xiaomi repair guides from support articles and third-party sites."""

    MI_SUPPORT_SEARCH = "https://www.mi.com/global/support/search/"
    MI_ARTICLE_BASE = "https://www.mi.com/global/support/article/"
    DIYGEARDO_BASE = "https://www.diygeardo.com"

    @property
    def platform(self) -> Platform:
        return Platform.XIAOMI

    def discover_guides(self, product: Product) -> list[str]:
        """Discover guide URLs for a Xiaomi product.

        Searches:
        1. mi.com/global/support/ for repair guides by product keywords
        2. diygeardo.com/category/xiaomi/ for Xiaomi repair guides
        """
        urls: set[str] = set()

        # Search Xiaomi Support
        mi_urls = self._search_mi_support(product)
        urls.update(mi_urls)
        if mi_urls:
            log.info(f"[xiaomi] Found {len(mi_urls)} guide(s) on mi.com for {product.name}")

        # Search DIYGeardo
        dg_urls = self._search_diygeardo(product)
        urls.update(dg_urls)
        if dg_urls:
            log.info(f"[xiaomi] Found {len(dg_urls)} guide(s) on diygeardo.com for {product.name}")

        return list(urls)

    def scrape_guide(self, url: str, product: Product) -> Optional[ScrapedItem]:
        """Scrape a single guide page into a ScrapedItem."""
        try:
            if "mi.com" in url:
                return self._scrape_mi_article(url, product)
            elif "diygeardo.com" in url:
                return self._scrape_diygeardo_article(url, product)
            else:
                return self._scrape_generic_guide(url, product)
        except Exception as e:
            log.warning(f"[xiaomi] Failed to scrape guide {url}: {e}")
            return None

    def scrape_images(self, guide_item: ScrapedItem, product: Product) -> list[ScrapedItem]:
        """Extract images from a scraped guide page."""
        images: list[ScrapedItem] = []

        if not guide_item.content_bytes:
            return images

        html = guide_item.content_bytes.decode('utf-8', errors='replace')
        extractor = _ImageExtractor()
        extractor.feed(html)
        extractor.close()

        seen_urls: set[str] = set()

        for img_src in extractor.images:
            # Resolve relative URLs
            img_url = urljoin(guide_item.url, img_src)
            if img_url in seen_urls:
                continue
            seen_urls.add(img_url)

            # Skip tiny/inline images
            if any(x in img_url.lower() for x in ('icon', 'logo', 'avatar', 'favicon')):
                continue

            # Determine file extension
            parsed = urlparse(img_url)
            path_lower = parsed.path.lower()
            if not any(path_lower.endswith(ext) for ext in
                       ('.jpg', '.jpeg', '.png', '.gif', '.webp', '.svg')):
                # Try to determine from URL pattern, default to .jpg
                for ext in ('.jpg', '.jpeg', '.png', '.gif', '.webp'):
                    if ext in path_lower:
                        file_ext = ext
                        break
                else:
                    continue  # Skip non-image URLs

            try:
                img_bytes = self._download_file(img_url)
                if not img_bytes:
                    continue

                img_title = f"Image from: {guide_item.title}"
                file_ext = '.jpg'
                for ext in ('.png', '.jpg', '.jpeg', '.gif', '.webp', '.svg'):
                    if path_lower.endswith(ext):
                        file_ext = ext
                        break

                img_hash = hashlib.sha256(img_bytes).hexdigest()

                img_item = ScrapedItem(
                    url=img_url,
                    title=img_title,
                    content_type=ContentType.IMAGE,
                    platform=Platform.XIAOMI,
                    source_url=guide_item.url,
                    file_extension=file_ext,
                    matched_product=product,
                    content_bytes=img_bytes,
                    content_hash=img_hash,
                )
                images.append(img_item)

            except Exception as e:
                log.warning(f"[xiaomi] Failed to download image {img_url}: {e}")

        return images

    # ─── Private: mi.com Support Search ─────────────────────────────

    def _search_mi_support(self, product: Product) -> set[str]:
        """Search Xiaomi support pages for repair guides."""
        urls: set[str] = set()

        # Build search terms - use product name and model numbers
        search_terms = [product.name]
        for kw in product.keywords:
            if MODEL_NUMBER_PATTERN.match(kw):
                search_terms.append(kw)

        for term in search_terms[:3]:  # Limit to avoid too many requests
            search_url = f"{self.MI_SUPPORT_SEARCH}?keywords={quote_plus(term)}+repair"
            try:
                resp = self._get(search_url)
                html = resp.text
                links = self._extract_links(html)

                for link in links:
                    abs_url = urljoin(search_url, link)
                    if KA_ARTICLE_PATTERN.search(abs_url):
                        # Check if the link text or surrounding content matches
                        if self._is_relevant_guide(abs_url, product):
                            urls.add(abs_url)

            except Exception as e:
                log.warning(f"[xiaomi] Support search failed for '{term}': {e}")

        return urls

    def _is_relevant_guide(self, url: str, product: Product) -> bool:
        """Quick check if a discovered URL is likely relevant."""
        url_lower = url.lower()
        for kw in product.keywords:
            if kw.lower() in url_lower:
                return True
        # Check if product name parts match
        name_parts = product.name.lower().replace('xiaomi', '').strip().split()
        for part in name_parts:
            if len(part) > 2 and part in url_lower:
                return True
        return True  # Default to including it; content check during scrape

    # ─── Private: DIYGeardo Search ──────────────────────────────────

    def _search_diygeardo(self, product: Product) -> set[str]:
        """Search DIYGeardo for Xiaomi repair guides."""
        urls: set[str] = set()

        # Try the Xiaomi category page
        category_url = f"{self.DIYGEARDO_BASE}/category/xiaomi/"
        try:
            self.rate_limiter.wait("diygeardo.com")
            resp = self.session.get(category_url, timeout=self.config.request_timeout)
            resp.raise_for_status()
            html = resp.text

            links = self._extract_links(html)
            for link in links:
                abs_url = urljoin(category_url, link)
                # Try to match against product keywords
                url_lower = abs_url.lower()
                for kw in product.keywords:
                    if kw.lower() in url_lower:
                        urls.add(abs_url)
                        break
                else:
                    # If the link points to a guide-like page within diygeardo
                    if 'diygeardo.com' in abs_url and any(
                        p.search(abs_url) for p in GUIDE_URL_PATTERNS
                    ):
                        if '/' not in abs_url.rstrip('/').rsplit('/', 1)[-1]:
                            continue  # Skip category/index pages
                        urls.add(abs_url)

        except Exception as e:
            log.warning(f"[xiaomi] DIYGeardo category page failed: {e}")

        return urls

    # ─── Private: Article Scraping ──────────────────────────────────

    def _scrape_mi_article(self, url: str, product: Product) -> Optional[ScrapedItem]:
        """Scrape a Xiaomi Support KA article."""
        resp = self._get(url)
        html = resp.text

        title = _extract_title(html)
        content_html = _extract_main_content(html)
        content_text = _extract_text(content_html)
        word_count = _word_count(content_text)

        if word_count < self.config.min_guide_words:
            log.info(f"[xiaomi] Skipping short article ({word_count} words): {url}")
            return None

        # Build enriched HTML content with attribution
        ka_id = ""
        m = KA_ID_PATTERN.search(url)
        if m:
            ka_id = m.group(0)

        enriched_html = self._build_enriched_html(
            title=title,
            url=url,
            content=content_html,
            source="Xiaomi Support",
            article_id=ka_id,
            product=product,
        )

        content_bytes = enriched_html.encode('utf-8')
        content_hash_val = hashlib.sha256(content_bytes).hexdigest()

        return ScrapedItem(
            url=url,
            title=title,
            content_type=ContentType.GUIDE,
            platform=Platform.XIAOMI,
            source_url=url,
            file_extension=".html",
            matched_product=product,
            content_bytes=content_bytes,
            content_hash=content_hash_val,
        )

    def _scrape_diygeardo_article(self, url: str, product: Product) -> Optional[ScrapedItem]:
        """Scrape a DIYGeardo repair guide article."""
        self.rate_limiter.wait("diygeardo.com")
        resp = self.session.get(url, timeout=self.config.request_timeout)
        resp.raise_for_status()
        html = resp.text

        title = _extract_title(html)
        content_html = _extract_main_content(html)
        content_text = _extract_text(content_html)
        word_count = _word_count(content_text)

        if word_count < self.config.min_guide_words:
            log.info(f"[xiaomi] Skipping short DIYGeardo article ({word_count} words): {url}")
            return None

        enriched_html = self._build_enriched_html(
            title=title,
            url=url,
            content=content_html,
            source="DIYGeardo",
            article_id="",
            product=product,
        )

        content_bytes = enriched_html.encode('utf-8')
        content_hash_val = hashlib.sha256(content_bytes).hexdigest()

        return ScrapedItem(
            url=url,
            title=title,
            content_type=ContentType.GUIDE,
            platform=Platform.XIAOMI,
            source_url=url,
            file_extension=".html",
            matched_product=product,
            content_bytes=content_bytes,
            content_hash=content_hash_val,
        )

    def _scrape_generic_guide(self, url: str, product: Product) -> Optional[ScrapedItem]:
        """Generic guide scraper for any URL (fallback)."""
        try:
            resp = self._get(url)
            html = resp.text
        except Exception:
            return None

        title = _extract_title(html)
        content_html = _extract_main_content(html)
        content_text = _extract_text(content_html)
        word_count = _word_count(content_text)

        if word_count < self.config.min_guide_words:
            log.info(f"[xiaomi] Skipping short guide ({word_count} words): {url}")
            return None

        enriched_html = self._build_enriched_html(
            title=title,
            url=url,
            content=content_html,
            source="Third-party",
            article_id="",
            product=product,
        )

        content_bytes = enriched_html.encode('utf-8')
        content_hash_val = hashlib.sha256(content_bytes).hexdigest()

        return ScrapedItem(
            url=url,
            title=title,
            content_type=ContentType.GUIDE,
            platform=Platform.XIAOMI,
            source_url=url,
            file_extension=".html",
            matched_product=product,
            content_bytes=content_bytes,
            content_hash=content_hash_val,
        )

    # ─── Private: Helpers ───────────────────────────────────────────

    def _extract_links(self, html: str) -> list[str]:
        """Extract all href values from <a> tags in HTML."""
        parser = _LinkExtractor()
        parser.feed(html)
        parser.close()
        return parser.links

    def _build_enriched_html(
        self,
        title: str,
        url: str,
        content: str,
        source: str,
        article_id: str,
        product: Product,
    ) -> str:
        """Build a self-contained HTML wrapper with metadata."""
        header = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{self._escape_html(title)}</title>
<meta name="source" content="{self._escape_html(source)}">
<meta name="platform" content="xiaomi">
<meta name="product" content="{self._escape_html(product.name)}">
<meta name="original-url" content="{self._escape_html(url)}">
<meta name="scraped-by" content="RepairManualBot/1.0">
</head>
<body>
<header>
<p>Source: {self._escape_html(source)}</p>
<p>Original URL: <a href="{self._escape_html(url)}">{self._escape_html(url)}</a></p>
<p>Product: {self._escape_html(product.name)}"""
        if article_id:
            header += f' | Article: {self._escape_html(article_id)}'
        header += """</p>
<hr>
</header>
<main>
"""
        footer = """
</main>
<footer>
<hr>
<p><small>Scraped for educational purposes by RepairManualBot</small></p>
</footer>
</body>
</html>
"""
        return header + content + footer

    @staticmethod
    def _escape_html(text: str) -> str:
        """Escape HTML special characters."""
        return (text.replace('&', '&amp;')
                    .replace('<', '&lt;')
                    .replace('>', '&gt;')
                    .replace('"', '&quot;')
                    .replace("'", '&#39;'))
