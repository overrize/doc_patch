"""Headless browser wrapper for JS-rendered repair guide sites.

Uses Playwright to render pages that static HTTP scraping can't handle
(e.g., samsung.com, apple.com support pages). Falls back gracefully if
Playwright/Chromium is not installed.
"""

import logging
from typing import Optional

log = logging.getLogger(__name__)

_HEADLESS_AVAILABLE: Optional[bool] = None
_BROWSER = None  # singleton


def is_available() -> bool:
    """Check if Playwright + Chromium are installed and ready."""
    global _HEADLESS_AVAILABLE
    if _HEADLESS_AVAILABLE is not None:
        return _HEADLESS_AVAILABLE
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            p.chromium.launch(headless=True).close()
        _HEADLESS_AVAILABLE = True
    except Exception as e:
        log.warning("Headless browser unavailable: %s", e)
        _HEADLESS_AVAILABLE = False
    return _HEADLESS_AVAILABLE


def get_browser():
    """Get or create the singleton headless browser instance."""
    global _BROWSER
    if _BROWSER is not None:
        return _BROWSER
    if not is_available():
        return None
    from playwright.sync_api import sync_playwright
    pw = sync_playwright().start()
    _BROWSER = pw.chromium.launch(
        headless=True,
        args=['--no-sandbox', '--disable-gpu', '--disable-dev-shm-usage'],
    )
    return _BROWSER


def close_browser():
    """Shut down the headless browser singleton."""
    global _BROWSER
    if _BROWSER:
        try:
            _BROWSER.close()
        except Exception:
            pass
        _BROWSER = None


def render(url: str, wait_selector: str = "body", timeout_ms: int = 15000) -> Optional[str]:
    """Render a JS-heavy page and return its full HTML.

    Args:
        url: The page URL to load.
        wait_selector: CSS selector to wait for before extracting HTML.
        timeout_ms: Max wait time for the selector.

    Returns:
        Rendered HTML string, or None if headless browser is unavailable
        or the page fails to load.
    """
    browser = get_browser()
    if browser is None:
        return None

    try:
        page = browser.new_page()
        page.set_viewport_size({"width": 1280, "height": 800})
        page.set_extra_http_headers({
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0.0.0 Safari/537.36"
            ),
        })
        page.goto(url, wait_until="networkidle", timeout=timeout_ms)
        try:
            page.wait_for_selector(wait_selector, timeout=timeout_ms // 2)
        except Exception:
            pass  # selector may not exist, that's OK

        html = page.content()
        page.close()
        return html
    except Exception as e:
        log.debug("Headless render failed for %s: %s", url, e)
        return None


def extract_links(html: str, base_url: str = "") -> list[str]:
    """Extract all <a href> links from HTML.

    Args:
        html: Rendered HTML content.
        base_url: Optional base URL for resolving relative links.

    Returns:
        List of absolute or relative URLs.
    """
    import re
    from urllib.parse import urljoin
    links = re.findall(r'<a[^>]+href=["\']([^"\']+)["\']', html, re.IGNORECASE)
    if base_url:
        links = [urljoin(base_url, l) for l in links]
    return links


def extract_images(html: str, base_url: str = "") -> list[str]:
    """Extract all <img src> URLs from HTML."""
    import re
    from urllib.parse import urljoin
    imgs = re.findall(r'<img[^>]+src=["\']([^"\']+)["\']', html, re.IGNORECASE)
    if base_url:
        imgs = [urljoin(base_url, i) for i in imgs]
    return imgs
