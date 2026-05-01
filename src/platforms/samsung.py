"""Samsung repair guide adapter.

Discovers and scrapes Samsung repair guides from:
- samsung.com support search (repair guides, manuals)
- samsungparts.com Self-Repair program (Encompass partner)

Uses headless browser (Playwright) for JS-rendered pages, with static
fallback when headless is not available.
"""

from __future__ import annotations

import logging
from html.parser import HTMLParser
from typing import Optional
from urllib.parse import urljoin, quote_plus

from ..types import ScrapedItem, ContentType, Platform, Product
from .base import BasePlatformScraper
from . import headless

log = logging.getLogger(__name__)

# --- Constants ---

SAMSUNG_SUPPORT_SEARCH = "https://www.samsung.com/us/support/search/?searchText={query}"
SAMSUNG_PARTS_SELF_REPAIR = "https://www.samsungparts.com/pages/self-repair-services"
SAMSUNG_PARTS_DOMAIN = "samsungparts.com"

# Keywords that suggest a repair guide page (path segments)
GUIDE_PATH_INDICATORS = [
    "support", "repair", "guide", "manual", "self-repair",
    "replacement", "teardown", "disassembly", "troubleshoot",
    "how-to", "diy", "ifixit",
]

# URL patterns to exclude (non-guide pages)
EXCLUDED_PATH_FRAGMENTS = [
    "/cart", "/checkout", "/account", "/login", "/search",
    "/wishlist", "javascript:", "mailto:", "tel:", "#",
]

# Image skip indicators (icons, logos, decor)
IMAGE_SKIP_INDICATORS = [
    "icon", "logo", "spacer", "pixel", "avatar", "favicon",
    "sprite", "badge", "banner-ad", "tracking",
]

# Relevant repair image alt text terms
REPAIR_IMAGE_TERMS = [
    "repair", "guide", "step", "disassemble", "replace", "screen",
    "battery", "camera", "board", "internal", "screw", "connector",
    "back", "front", "open", "remove", "tool", "part", "module",
    "assembly", "cable", "flex", "adhesive", "pull-tab",
]

# Minimum image size in bytes (skip tiny placeholders)
MIN_IMAGE_BYTES = 1000

# Samsung PDF naming patterns, e.g. "SM-A556B_RepairGuide_Open_Eng_Rev.1.0_240327_.pdf"
PDF_NAME_WORDS_TO_DROP = {"rev", "eng", "open", "ver", "version"}


# --- HTML Parser ---


class _SamsungHTMLParser(HTMLParser):
    """Single-pass HTML parser extracting links, images, title, and text body."""

    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []
        self.images: list[dict[str, str | None]] = []
        self.title_parts: list[str] = []
        self.text_parts: list[str] = []
        self._in_title = False
        self._in_skip = 0  # nesting counter for <script>/<style>/<noscript>

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr = dict(attrs)
        if tag in ("script", "style", "noscript"):
            self._in_skip += 1
        elif tag == "title":
            self._in_title = True
        elif tag == "a" and attr.get("href"):
            self.links.append(attr["href"])
        elif tag == "img":
            self.images.append(attr)

    def handle_endtag(self, tag: str) -> None:
        if tag in ("script", "style", "noscript"):
            self._in_skip = max(0, self._in_skip - 1)
        elif tag == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        if self._in_skip > 0:
            return
        text = data.strip()
        if not text:
            return
        if self._in_title:
            self.title_parts.append(text)
        else:
            self.text_parts.append(text)

    @property
    def title(self) -> str:
        return " ".join(self.title_parts).strip() or "Samsung Repair Guide"

    @property
    def text(self) -> str:
        return "\n".join(self.text_parts)


# --- Scraper ---


class SamsungScraper(BasePlatformScraper):
    """Scrapes Samsung repair guides from samsung.com support and samsungparts.com."""

    @property
    def platform(self) -> Platform:
        return Platform.SAMSUNG

    # ------------------------------------------------------------------
    #  discover_guides
    # ------------------------------------------------------------------

    def discover_guides(self, product: Product) -> list[str]:
        """Search Samsung sources for repair guide URLs matching *product*."""
        if product is None:
            return []
        keywords = product.keywords if product.keywords else [product.name]
        discovered: list[str] = []

        # --- 1. Samsung support search ---
        for keyword in keywords:
            try:
                urls = self._search_samsung_support(keyword)
                discovered.extend(urls)
            except Exception as exc:
                log.warning("Samsung support search failed for %r: %s", keyword, exc)

        # --- 2. Samsung Parts self-repair page ---
        try:
            urls = self._scrape_self_repair_page()
            # Filter to pages mentioning *any* keyword
            for url in urls:
                if self._url_matches_product(url, product):
                    discovered.append(url)
        except Exception as exc:
            log.warning("Samsung Parts self-repair check failed: %s", exc)

        # Deduplicate while keeping discovery order
        unique = list(dict.fromkeys(discovered))
        log.info("Discovered %d Samsung guide URL(s) for %s", len(unique), product.name)
        return unique

    def _search_samsung_support(self, keyword: str) -> list[str]:
        """Try headless browser first, fall back to static request."""
        query = f"{keyword} repair guide"
        search_url = SAMSUNG_SUPPORT_SEARCH.format(query=quote_plus(query))

        html = None
        if headless.is_available():
            html = headless.render(search_url, wait_selector="a[href]")
            if html:
                log.debug("Samsung search rendered via headless browser")
        if html is None:
            resp = self._get(search_url)
            html = self._get_text(resp)

        parser = _SamsungHTMLParser()
        parser.feed(html)

        urls: list[str] = []
        for link in parser.links:
            full = urljoin(search_url, link)
            if self._is_guide_url(full, keyword):
                urls.append(full)
        return urls

    def _scrape_self_repair_page(self) -> list[str]:
        """Pull guide links from Samsung Parts — headless first, static fallback."""
        html = None
        if headless.is_available():
            html = headless.render(SAMSUNG_PARTS_SELF_REPAIR, wait_selector="a[href]")
            if html:
                log.debug("Samsung Parts rendered via headless browser")
        if html is None:
            self.rate_limiter.wait(SAMSUNG_PARTS_DOMAIN)
            resp = self.session.get(
                SAMSUNG_PARTS_SELF_REPAIR,
                timeout=self.config.request_timeout,
            )
            resp.raise_for_status()
            html = self._get_text(resp)

        parser = _SamsungHTMLParser()
        parser.feed(html)

        urls: list[str] = []
        for link in parser.links:
            full = urljoin(SAMSUNG_PARTS_SELF_REPAIR, link)
            if self._is_guide_url(full):
                urls.append(full)
        return urls

    @staticmethod
    def _is_guide_url(url: str, keyword: str | None = None) -> bool:
        """Return *True* if *url* points to a probable repair-guide page."""
        lower = url.lower()

        # Domain gate
        if "samsung.com" not in lower and SAMSUNG_PARTS_DOMAIN not in lower:
            return False

        # Exclude utility pages
        for frag in EXCLUDED_PATH_FRAGMENTS:
            if frag in lower:
                return False

        # Keyword matching (if provided)
        if keyword is not None and keyword.lower() not in lower:
            return False

        # Must contain a guide indicator in the path
        return any(ind in lower for ind in GUIDE_PATH_INDICATORS)

    @staticmethod
    def _url_matches_product(url: str, product: Product) -> bool:
        """Check at least one product keyword appears in the URL."""
        url_lower = url.lower()
        for kw in product.keywords:
            if kw.lower() in url_lower:
                return True
        return product.name.lower() in url_lower

    # ------------------------------------------------------------------
    #  scrape_guide
    # ------------------------------------------------------------------

    def scrape_guide(self, url: str, product: Product) -> Optional[ScrapedItem]:
        """Scrape a single Samsung guide page.  Returns a MANUAL if a PDF is
        linked, otherwise a GUIDE with the page HTML."""
        try:
            resp = self._get(url)
            html = self._get_text(resp)

            parser = _SamsungHTMLParser()
            parser.feed(html)

            # ---- PDF repair guide? ----
            pdf_url = self._find_pdf_link(parser.links, url)
            if pdf_url is not None:
                return self._download_manual(pdf_url, url, product)

            # ---- HTML guide ----
            title = f"Samsung {parser.title}"
            return ScrapedItem(
                url=url,
                title=title,
                content_type=ContentType.GUIDE,
                platform=Platform.SAMSUNG,
                source_url=url,
                file_extension=".html",
                matched_product=product,
                content_bytes=html.encode("utf-8"),
                content_hash="",
            )
        except Exception as exc:
            log.warning("Failed to scrape guide %s: %s", url, exc)
            return None

    @staticmethod
    def _find_pdf_link(links: list[str], base_url: str) -> Optional[str]:
        """Return the first PDF link found in *links*, resolved to absolute."""
        for link in links:
            if link.lower().endswith(".pdf"):
                return urljoin(base_url, link)
        return None

    def _download_manual(self, pdf_url: str, source_url: str, product: Product) -> Optional[ScrapedItem]:
        """Download a PDF repair guide and wrap it in a ScrapedItem."""
        pdf_data = self._download_file(pdf_url)
        if pdf_data is None:
            return None

        title = f"Samsung {_pdf_title_from_url(pdf_url)}"
        return ScrapedItem(
            url=pdf_url,
            title=title,
            content_type=ContentType.MANUAL,
            platform=Platform.SAMSUNG,
            source_url=source_url,
            file_extension=".pdf",
            matched_product=product,
            content_bytes=pdf_data,
            content_hash="",
        )

    # ------------------------------------------------------------------
    #  scrape_images
    # ------------------------------------------------------------------

    def scrape_images(self, guide_item: ScrapedItem, product: Product) -> list[ScrapedItem]:
        """Extract and download repair-relevant images from a scraped guide page."""
        if guide_item.content_bytes is None:
            return []

        try:
            html = guide_item.content_bytes.decode("utf-8", errors="replace")
        except Exception:
            return []

        parser = _SamsungHTMLParser()
        parser.feed(html)

        if not parser.images:
            return []

        base_url = guide_item.url
        results: list[ScrapedItem] = []

        for idx, attrs in enumerate(parser.images):
            src = (attrs.get("src") or "").strip()
            alt = (attrs.get("alt") or "").lower()
            if not src:
                continue

            # Skip decoration / UI images
            src_lower = src.lower()
            if any(skip in src_lower for skip in IMAGE_SKIP_INDICATORS):
                continue

            # Relevance gate: prefer images with repair alt text
            if alt and not any(term in alt for term in REPAIR_IMAGE_TERMS):
                continue

            img_url = urljoin(base_url, src)
            try:
                img_data = self._download_file(img_url)
            except Exception:
                log.debug("Image download failed: %s", img_url)
                continue

            if img_data is None or len(img_data) < MIN_IMAGE_BYTES:
                continue

            ext = _detect_image_extension(img_url, img_data)
            title = alt or f"samsung_repair_image_{idx}"
            results.append(
                ScrapedItem(
                    url=img_url,
                    title=title[:100],
                    content_type=ContentType.IMAGE,
                    platform=Platform.SAMSUNG,
                    source_url=guide_item.url,
                    file_extension=ext,
                    matched_product=product,
                    content_bytes=img_data,
                    content_hash="",
                )
            )

        log.info("Downloaded %d image(s) for %s", len(results), product.name)
        return results


# ------------------------------------------------------------------
#  Helpers
# ------------------------------------------------------------------


def _pdf_title_from_url(pdf_url: str) -> str:
    """Build a readable title from a Samsung PDF filename.

    >>> _pdf_title_from_url("https://.../SM-A556B_RepairGuide_Open_Eng_Rev.1.0_240327_.pdf")
    'RepairGuide Eng 1.0 240327'
    """
    basename = pdf_url.rsplit("/", 1)[-1]
    # Strip extension
    if basename.lower().endswith(".pdf"):
        basename = basename[:-4]

    parts = basename.split("_")
    meaningful: list[str] = []
    for part in parts:
        low = part.lower().replace(".", "")
        if low in PDF_NAME_WORDS_TO_DROP:
            continue
        meaningful.append(part)

    return " ".join(meaningful).strip() or "Repair Guide"


def _detect_image_extension(url: str, data: bytes) -> str:
    """Return a reasonable file extension for an image.

    Checks URL string first, then falls back to magic bytes.
    """
    # URL-based
    lower = url.lower()
    for ext in (".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".bmp"):
        if ext in lower.split("?")[0].split("#")[0]:
            return ext

    # Magic-byte detection
    if data[:4] == b"\x89PNG":
        return ".png"
    if data[:3] == b"\xff\xd8\xff":
        return ".jpg"
    if data[:4] == b"GIF8":
        return ".gif"
    if data[:4] == b"RIFF" and len(data) >= 12 and data[8:12] == b"WEBP":
        return ".webp"
    if data[:2] == b"BM":
        return ".bmp"

    return ".jpg"  # sensible default
