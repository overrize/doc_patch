"""iFixit platform adapter for repair guide scraping.

Uses the iFixit API v2.0 to discover guides, scrape full step-by-step content,
and download associated images from the CDN.
"""

import logging
import re
from typing import Optional

from requests.utils import quote as url_quote

from ..types import ScrapedItem, ContentType, Platform, Product, ScraperConfig
from ..engine.limiter import RateLimiter
from .base import BasePlatformScraper

log = logging.getLogger(__name__)

IFIXIT_BASE = "https://www.ifixit.com"
IFIXIT_API_BASE = f"{IFIXIT_BASE}/api/2.0"
IMAGE_CDN_BASE = "https://guide-images.cdn.ifixit.com"

# Regex to extract numeric guide id from API or web URLs
_GUIDE_ID_RE = re.compile(r"/guides?/(\d+)")


class IFixitScraper(BasePlatformScraper):
    """Scraper for iFixit repair guides using the iFixit API v2.0.

    Discovery uses the suggest endpoint to search for guides matching
    product keywords. Full guide content (introduction + step lines) is
    scraped via the guide detail endpoint. Images are downloaded from
    the iFixit CDN using the standard size (~300px).
    """

    def __init__(self, config: ScraperConfig, rate_limiter: RateLimiter):
        super().__init__(config, rate_limiter)

    # ── BasePlatformScraper interface ───────────────────────────────────────

    @property
    def platform(self) -> Platform:
        return Platform.IFIXIT

    def discover_guides(self, product: Product) -> list[str]:
        """Discover guide API URLs for a product using the suggest endpoint.

        Searches for each product keyword via
        ``GET /api/2.0/suggest/{query}?doctypes=guide,device``, keeps
        only ``guide``-type results whose title contains at least one
        product keyword, and returns the corresponding guide API URLs.
        """
        guide_ids: dict[int, str] = {}  # id -> title (dedup)

        for keyword in product.keywords:
            quoted = url_quote(keyword)
            api_url = f"{IFIXIT_API_BASE}/suggest/{quoted}"
            try:
                data = self._get_json(api_url, params={"doctypes": "guide,device"})
            except Exception:
                log.warning("Suggest API failed for keyword %r", keyword)
                continue

            results = data.get("results", [])
            for result in results:
                if result.get("type") != "guide":
                    continue

                docid = result.get("docid")
                title = result.get("title", "")
                if docid is None:
                    continue

                title_lower = title.lower()
                if not _any_keyword_matches(title_lower, product.keywords):
                    continue

                if docid not in guide_ids:
                    guide_ids[docid] = title
                    log.debug("Discovered guide: %s (ID: %s)", title, docid)

        urls = [f"{IFIXIT_API_BASE}/guides/{gid}" for gid in guide_ids]
        log.info(
            "Discovered %d guides for %s %s", len(urls), product.brand, product.name
        )
        return urls

    def scrape_guide(self, url: str, product: Product) -> Optional[ScrapedItem]:
        """Fetch a guide from the API and return a ScrapedItem with full HTML.

        Calls ``GET /api/2.0/guides/{guideid}``, assembles the
        ``introduction_raw`` and ``steps[].lines[].text_raw`` into an
        HTML document, and validates the word count against
        ``config.min_guide_words``.
        """
        try:
            data = self._get_json(url)
        except Exception:
            log.error("Failed to fetch guide: %s", url)
            return None

        guide_id = data.get("guideid")
        title = data.get("title", "Untitled Guide")
        introduction = data.get("introduction_raw", "")
        steps = data.get("steps", [])

        # ── Build HTML content ─────────────────────────────────────────
        html = _build_guide_html(title, introduction, steps)

        # Validate word count
        word_count = len(html.split())
        if word_count < self.config.min_guide_words:
            log.warning(
                "Guide too short (%d words < %d): %s",
                word_count, self.config.min_guide_words, title,
            )
            return None

        content_bytes = html.encode("utf-8")
        guide_web_url = f"{IFIXIT_BASE}/Guide/{guide_id}"

        return ScrapedItem(
            url=url,  # API URL — direct content source
            title=title,
            content_type=ContentType.GUIDE,
            platform=Platform.IFIXIT,
            source_url=guide_web_url,  # human-readable page
            file_extension=".html",
            matched_product=product,
            content_bytes=content_bytes,
        )

    def scrape_images(self, guide_item: ScrapedItem, product: Product) -> list[ScrapedItem]:
        """Download images referenced in a guide's steps.

        Re-fetches the guide JSON from ``guide_item.url`` (the API URL),
        iterates ``steps[].media[].data`` to locate the **standard**
        size (~300px), downloads the image bytes via
        ``_download_file``, and returns one ``ScrapedItem`` per image.
        """
        api_url = guide_item.url
        try:
            data = self._get_json(api_url)
        except Exception:
            log.error("Failed to re-fetch guide for images: %s", api_url)
            return []

        images: list[ScrapedItem] = []
        guide_web_url = guide_item.source_url
        steps = data.get("steps", [])

        for step_idx, step in enumerate(steps, 1):
            media_list = step.get("media", [])
            for media in media_list:
                image_entry = _pick_standard_image(media.get("data"))
                if image_entry is None:
                    continue

                image_url = _resolve_image_url(media, image_entry)
                if not image_url:
                    continue

                image_bytes = self._download_file(image_url)
                if not image_bytes:
                    continue

                # Derive a short title from the first line of the step
                step_title = _step_image_title(guide_item.title, step, step_idx)

                img = ScrapedItem(
                    url=image_url,
                    title=step_title,
                    content_type=ContentType.IMAGE,
                    platform=Platform.IFIXIT,
                    source_url=guide_web_url,
                    file_extension=".jpg",
                    matched_product=product,
                    content_bytes=image_bytes,
                )
                images.append(img)

        return images


# ── Helper functions (module-private) ──────────────────────────────────────


def _any_keyword_matches(title_lower: str, keywords: list[str]) -> bool:
    """Return True if *any* product keyword is found in the guide title."""
    for kw in keywords:
        kw_lower = kw.lower()
        if _keyword_matches(title_lower, kw_lower):
            return True
    return False


def _keyword_matches(title_lower: str, keyword_lower: str) -> bool:
    """Simple keyword matching: all words of the keyword must appear in the title."""
    words = keyword_lower.split()
    return all(w in title_lower for w in words)


def _escape_html(text: str) -> str:
    """Escape basic HTML entities in plain text."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _build_guide_html(title: str, introduction: str, steps: list[dict]) -> str:
    """Assemble a self-contained HTML document from guide parts."""
    lines: list[str] = [
        "<!DOCTYPE html>",
        '<html lang="en">',
        "<head>",
        '<meta charset="utf-8">',
        f"<title>{_escape_html(title)}</title>",
        "</head>",
        "<body>",
        f"<h1>{_escape_html(title)}</h1>",
        "<p><em>Source: iFixit</em></p>",
    ]

    if introduction:
        lines.append(f'<div class="introduction">{introduction}</div>')

    for i, step in enumerate(steps, 1):
        step_title = step.get("title")
        lines.append(f"<h2>Step {i}{' &mdash; ' + _escape_html(step_title) if step_title else ''}</h2>")
        step_lines = step.get("lines", [])
        for line in step_lines:
            text = line.get("text_raw", "")
            if not text:
                continue
            level = line.get("level", 0)
            bullet = line.get("bullet", "")
            if bullet == "black":
                lines.append(f"<li>{text}</li>")
            elif level > 0:
                indent = "&nbsp;" * (level * 4)
                lines.append(f"<p>{indent}{text}</p>")
            else:
                lines.append(f"<p>{text}</p>")

    lines.append("</body></html>")
    return "\n".join(lines)


def _pick_standard_image(media_data) -> Optional[dict]:
    """Select the best image variant from media data (~300px, 'standard').

    ``media_data`` can be a dict (keyed by size name/number) or a list
    of size-entry dicts.  Returns the first acceptable entry or None.
    """
    if not media_data:
        return None

    if isinstance(media_data, dict):
        # Prefer the named "standard" key
        if "standard" in media_data:
            return media_data["standard"]
        # Fallback: any key
        return next(iter(media_data.values()), None)

    if isinstance(media_data, list):
        # Look for an entry around 200-400px wide
        for entry in media_data:
            w = entry.get("width", 0)
            if 200 <= w <= 400:
                return entry
        # Fallback: first entry
        return media_data[0] if media_data else None

    return None


def _resolve_image_url(media: dict, image_entry: dict) -> str:
    """Build the CDN image URL from a media object and its size entry."""
    # Use the URL from the size entry if present
    url = image_entry.get("url", "")
    if url:
        return url

    # Otherwise construct from guid + size id
    guid = media.get("guid", "")
    size_id = image_entry.get("id", "")
    if guid and size_id:
        return f"{IMAGE_CDN_BASE}/igi/{guid}.{size_id}"

    return ""


def _step_image_title(guide_title: str, step: dict, step_idx: int) -> str:
    """Derive a short, descriptive title for a step image."""
    lines = step.get("lines", [])
    if lines:
        first_text = lines[0].get("text_raw", "")
        if first_text:
            # Truncate to a reasonable length
            return first_text[:100]
        return f"{guide_title} — Step {step_idx} image"
    return f"{guide_title} — Step {step_idx} image"
