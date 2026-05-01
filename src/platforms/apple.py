"""Apple Self Service Repair adapter for support.apple.com/self-service-repair.

Apple publishes web-based HTML repair manuals (not PDFs) organized by device.
Each device has a TOC (Table of Contents) page at support.apple.com/en-us/{doc_id}
with sections: Safety, Troubleshooting, Procedures, Views/Parts/Tools.
"""

import logging
import re
import hashlib
import html as html_mod
from typing import Optional
from urllib.parse import urljoin, urlparse

from ..types import ScrapedItem, ContentType, Platform, Product
from .base import BasePlatformScraper

log = logging.getLogger(__name__)

APPLE_SUPPORT_BASE = "https://support.apple.com"
APPLE_SEARCH_BASE = "https://support.apple.com/kb/index"
IMAGE_CDN_DOMAINS = [
    "cdsassets.apple.com",
    "help.apple.com",
    "manuals.info.apple.com",
]

# Known Apple Self Service Repair manual TOC page IDs.
# Maps normalized product name to the support.apple.com/en-us/{id} document ID.
KNOWN_TOC_IDS = {
    "iphone 15": "104900",
    "iphone 15 plus": "104858",
    "iphone 15 pro": "104872",
    "iphone 15 pro max": "104917",
    "iphone 14": "102638",
    "iphone 14 plus": "102636",
    "iphone 14 pro": "102633",
    "iphone 14 pro max": "102637",
    "iphone 13": "101745",
    "iphone 13 mini": "101742",
    "iphone 13 pro": "101743",
    "iphone 13 pro max": "101744",
    "iphone 12": "100491",
    "iphone 12 mini": "100495",
    "iphone 12 pro": "100492",
    "iphone 12 pro max": "100493",
    "iphone se (3rd generation)": "102440",
    "iphone se (3rd gen)": "102440",
    "iphone 16": "120692",
    "iphone 16 plus": "120702",
    "iphone 16 pro": "120710",
    "iphone 16 pro max": "120819",
    "iphone 16e": "121720",
    "macbook air m3": "119580",
    "macbook pro m3": "119583",
}

# Normalized names are also mapped from model numbers for quick lookup
MODEL_TO_NAME = {
    "a2849": "iphone 15 pro max",
    "a2848": "iphone 15 pro",
    "a2846": "iphone 15",
    "a2651": "iphone 14 pro max",
    "a2650": "iphone 14 pro",
    "a2649": "iphone 14",
    "a2484": "iphone 13 pro max",
    "a2482": "iphone 13",
    "a2172": "iphone 12",
    "a2595": "iphone se (3rd generation)",
    "a2782": "iphone se (3rd generation)",
    "a3113": "macbook air m3",
    "a3114": "macbook air m3",
    "a3112": "macbook pro m3",
    "a2991": "macbook pro m3",
}


class AppleScraper(BasePlatformScraper):
    """Scraper for Apple Self Service Repair manuals.

    Discovers device-specific HTML repair manuals from support.apple.com,
    extracts procedure text, and downloads repair images/diagrams.
    """

    @property
    def platform(self) -> Platform:
        return Platform.APPLE

    def discover_guides(self, product: Product) -> list[str]:
        """Discover Apple repair manual TOC pages for a product."""
        if product is None:
            return []
        name_lower = product.name.lower().strip()

        # 1. Check known TOC ID mapping by product name
        for known_name, toc_id in KNOWN_TOC_IDS.items():
            if known_name in name_lower or name_lower in known_name:
                url = f"{APPLE_SUPPORT_BASE}/en-us/{toc_id}"
                urls.append(url)
                log.info("Found known manual for '%s': %s", product.name, toc_id)
                break

        # 2. Check model number keywords against model-to-name mapping
        if not urls:
            for kw in product.keywords:
                kw_lower = kw.lower().strip()
                # Model numbers like a2849
                model_name = MODEL_TO_NAME.get(kw_lower)
                if model_name:
                    for known_name, toc_id in KNOWN_TOC_IDS.items():
                        if known_name == model_name:
                            url = f"{APPLE_SUPPORT_BASE}/en-us/{toc_id}"
                            urls.append(url)
                            log.info(
                                "Found manual via model '%s' for '%s': %s",
                                kw, product.name, toc_id,
                            )
                            break
                    if urls:
                        break

        # 3. Search Apple Support for repair manuals
        if not urls:
            urls = self._search_manuals(product)

        return list(dict.fromkeys(urls))  # deduplicate, preserve order

    def scrape_guide(self, url: str, product: Product) -> Optional[ScrapedItem]:
        """Scrape an Apple repair manual HTML page."""
        if product is None:
            product_name = "Unknown"
        else:
            product_name = product.name
        
        try:
            resp = self._get(url)
            html_content = self._get_text(resp)
        except Exception as e:
            log.warning("Failed to fetch Apple guide %s: %s", url, e)
            return None

        title = self._extract_title(html_content) or f"Apple Repair Manual - {product_name}"

        # Extract Manual ID (e.g. QNCHKL)
        manual_id = self._extract_manual_id(html_content)

        # Build a clean, self-contained HTML document
        output_parts = ['<!DOCTYPE html>', '<html lang="en">', '<head>',
                        '<meta charset="utf-8">',
                        f'<title>{title}</title>',
                        '</head>', '<body>']

        output_parts.append(f'<h1>{title}</h1>')

        if manual_id:
            output_parts.append(f'<p><strong>Manual ID:</strong> {manual_id}</p>')

        output_parts.append(f'<p><strong>Product:</strong> {product_name}</p>')
        output_parts.append(
            f'<p><strong>Original URL:</strong> <a href="{url}">{url}</a></p>'
        )
        output_parts.append('<hr>')

        # Extract the main content (sections: Safety, Troubleshooting,
        # Procedures, Views/Parts/Tools)
        content_body = self._extract_main_content(html_content)
        if content_body:
            output_parts.append(content_body)
        else:
            # Fallback: save cleaned HTML of the page body
            output_parts.append(self._clean_html(html_content))

        # Attribution footer
        output_parts.append('<hr>')
        output_parts.append('<p><em>Source: Apple Self Service Repair</em></p>')
        output_parts.append('</body>')
        output_parts.append('</html>')

        full_html = "\n".join(output_parts)
        content_bytes = full_html.encode('utf-8')
        content_hash = hashlib.sha256(content_bytes).hexdigest()

        return ScrapedItem(
            url=url,
            title=title,
            content_type=ContentType.GUIDE,
            platform=Platform.APPLE,
            source_url=url,
            file_extension=".html",
            matched_product=product,
            content_bytes=content_bytes,
            content_hash=content_hash,
        )

    def scrape_images(self, guide_item: ScrapedItem, product: Product) -> list[ScrapedItem]:
        """Extract and download images from an Apple repair manual page.

        Apple manuals include internal view diagrams, tool images,
        and step-by-step procedure photographs.  Images are saved as
        ContentType.TEARDOWN (for internal views) or ContentType.IMAGE.
        """
        if not guide_item.content_bytes:
            return []

        html_content = guide_item.content_bytes.decode('utf-8', errors='replace')
        images = []

        # Collect all image source URLs from the HTML
        img_sources = set()

        # img tag with quoted src attribute
        for m in re.finditer(
            r'<img\s[^>]*?src\s*=\s*["\']([^"\']+)["\']',
            html_content,
            re.IGNORECASE,
        ):
            img_sources.add(m.group(1))

        # img tag with unquoted src (fallback)
        for m in re.finditer(
            r'<img\s[^>]*?src\s*=\s*([^\s"\'][^\s>]*)',
            html_content,
            re.IGNORECASE,
        ):
            img_sources.add(m.group(1))

        for img_url in img_sources:
            if not img_url or img_url.startswith('data:'):
                continue

            # Normalize URL
            img_url = img_url.strip()
            if img_url.startswith('//'):
                img_url = 'https:' + img_url
            elif not img_url.startswith('http'):
                img_url = urljoin(guide_item.source_url, img_url)

            # Determine file extension (default to .jpg)
            ext = ".jpg"
            ext_match = re.search(r'\.([a-z]{3,4})(?:\?|$)', img_url.lower())
            if ext_match:
                ext = f".{ext_match.group(1)}"
                if ext not in ('.jpg', '.jpeg', '.png', '.gif', '.webp', '.svg'):
                    ext = ".jpg"

            # Build a human-readable title from the URL path
            path_parts = urlparse(img_url).path.split('/')
            filename = path_parts[-1] if path_parts else "image"
            name_part = re.sub(r'\.[a-z]+$', '', filename)
            title = name_part.replace('_', ' ').replace('-', ' ').strip()

            # Determine content type
            content_type = ContentType.IMAGE
            url_lower = img_url.lower()
            if any(
                t in url_lower
                for t in ('teardown', 'internal', 'locator', 'exploded', 'view')
            ):
                content_type = ContentType.TEARDOWN

            # Download the image binary
            content_bytes = self._download_file(img_url)

            if content_bytes is None:
                log.debug("Skipping image (download failed): %s", img_url)
                continue

            content_hash = hashlib.sha256(content_bytes).hexdigest()

            images.append(ScrapedItem(
                url=img_url,
                title=title,
                content_type=content_type,
                platform=Platform.APPLE,
                source_url=guide_item.source_url,
                file_extension=ext,
                matched_product=product,
                content_bytes=content_bytes,
                content_hash=content_hash,
            ))

        return images

    # ------------------------------------------------------------------
    #  Private helpers
    # ------------------------------------------------------------------

    def _search_manuals(self, product: Product) -> list[str]:
        """Search support.apple.com for repair manuals matching the product.

        Builds queries from the product name and model-number keywords,
        then parses search-results HTML for documentation page links.
        """
        found_urls = []

        # Primary query: product name
        queries = [f"repair manual {product.name}"]

        # Add model-number queries (e.g. "a2849")
        for kw in product.keywords:
            kw_lower = kw.lower().strip()
            if re.match(r'^a\d{4}$', kw_lower):
                queries.append(f"repair manual {kw}")

        for query in queries[:3]:  # limit to avoid excessive HTTP calls
            try:
                params = {
                    'page': 'search',
                    'q': query,
                    'doctype': 'DOCUMENTATIONS',
                    'locale': 'en_US',
                    'currentPage': 1,
                }
                resp = self._get(APPLE_SEARCH_BASE, params=params)
                html_text = resp.text

                # Find linked documentation pages:
                #   href="/en-us/104900"
                #   href="https://support.apple.com/en-us/104900"
                link_pattern = r'href="(?:https://support\.apple\.com)?(/en-us/\d+)"'
                matches = re.findall(link_pattern, html_text)
                for rel_path in matches:
                    full_url = f"{APPLE_SUPPORT_BASE}{rel_path}"
                    if full_url not in found_urls:
                        found_urls.append(full_url)

            except Exception as e:
                log.warning("Apple search failed for '%s': %s", query, e)

        # Keep only plausible repair-manual IDs (5-6 digit document IDs)
        return [u for u in found_urls if re.search(r'/en-us/\d{5,6}$', u)]

    @staticmethod
    def _extract_title(html_content: str) -> Optional[str]:
        """Extract the visible page title from the first <h1> tag."""
        match = re.search(
            r'<h1[^>]*>(.*?)</h1>', html_content, re.DOTALL | re.IGNORECASE,
        )
        if match:
            # Strip inner tags, decode entities
            title = re.sub(r'<[^>]+>', '', match.group(1))
            title = html_mod.unescape(title).strip()
            return title or None
        return None

    @staticmethod
    def _extract_manual_id(html_content: str) -> Optional[str]:
        """Extract the Manual ID (e.g. 'QNCHKL') from the page content."""
        # Bold variant: Manual ID: <strong>QNCHKL</strong>
        match = re.search(
            r'Manual\s*ID:\s*<strong>\s*([A-Z0-9]{4,10})\s*</strong>',
            html_content,
            re.IGNORECASE,
        )
        if match:
            return match.group(1)

        # Plain text variant: Manual ID: QNCHKL
        match = re.search(
            r'Manual\s*ID:\s*(?:</?[^>]+>\s*)*([A-Z0-9]{4,10})',
            html_content,
            re.IGNORECASE,
        )
        return match.group(1) if match else None

    @staticmethod
    def _extract_main_content(html_content: str) -> Optional[str]:
        """Extract the main content area from an Apple support page.

        Apple repair manual pages place content inside a div with id
        'sections', 'content', or 'howto-section'.
        """
        # Try each known container ID
        for div_id in ('sections', 'content', 'howto-section'):
            # Match from <div id="..."> up to the following <footer>
            # or footer-related element
            pattern = (
                r'<div\s[^>]*?\bid\s*=\s*["\']' + re.escape(div_id) +
                r'["\'][^>]*>(.*?)</div>\s*'
                r'(?=<footer|<div\s+id=["\']footernav|<div\s+class=["\'][^"\']*footer)'
            )
            match = re.search(pattern, html_content, re.DOTALL | re.IGNORECASE)
            if match:
                return match.group(1).strip()
        return None

    @staticmethod
    def _clean_html(html_content: str) -> str:
        """Minimally clean HTML: remove scripts, styles, and comments."""
        cleaned = re.sub(
            r'<script[^>]*>.*?</script>', '',
            html_content, flags=re.DOTALL | re.IGNORECASE,
        )
        cleaned = re.sub(
            r'<style[^>]*>.*?</style>', '',
            cleaned, flags=re.DOTALL | re.IGNORECASE,
        )
        cleaned = re.sub(r'<!--.*?-->', '', cleaned, flags=re.DOTALL)
        return cleaned
