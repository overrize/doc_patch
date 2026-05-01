"""Headless browser wrapper for JS-rendered repair guide sites.

Uses Playwright to connect to system-installed browsers (Edge/Chrome).
No `playwright install chromium` needed — Windows always has Edge,
and Chrome is common on dev machines.

Fallback: static HTTP request when no browser is available.
"""

import logging
from typing import Optional

log = logging.getLogger(__name__)

_HEADLESS_AVAILABLE: Optional[bool] = None
_ACTIVE_CHANNEL: Optional[str] = None  # "msedge", "chrome", or None
_BROWSER = None  # singleton


# Try in order: system Edge (always on Windows), system Chrome, Playwright Chromium
_BROWSER_CHANNELS = [
    ("msedge", "system Microsoft Edge"),
    ("chrome", "system Google Chrome"),
    (None, "Playwright Chromium (install: playwright install chromium)"),
]


def is_available() -> bool:
    """Check if any headless browser is available."""
    global _HEADLESS_AVAILABLE, _ACTIVE_CHANNEL
    if _HEADLESS_AVAILABLE is not None:
        return _HEADLESS_AVAILABLE
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        log.warning("Headless: playwright not installed. Run: pip install playwright")
        _HEADLESS_AVAILABLE = False
        return False

    for channel, desc in _BROWSER_CHANNELS:
        try:
            with sync_playwright() as p:
                if channel:
                    p.chromium.launch(channel=channel, headless=True).close()
                else:
                    p.chromium.launch(headless=True).close()
            _HEADLESS_AVAILABLE = True
            _ACTIVE_CHANNEL = channel
            log.info("Headless browser ready: %s", desc)
            return True
        except Exception:
            log.debug("Headless channel %s unavailable", channel or "default")
            continue

    log.warning("No headless browser found. Install: playwright install chromium")
    _HEADLESS_AVAILABLE = False
    return False


def get_browser():
    """Get or create the singleton headless browser instance."""
    global _BROWSER
    if _BROWSER is not None:
        return _BROWSER
    if not is_available():
        return None
    from playwright.sync_api import sync_playwright
    pw = sync_playwright().start()
    launch_args = {
        "headless": True,
        "args": ['--no-sandbox', '--disable-gpu', '--disable-dev-shm-usage'],
    }
    if _ACTIVE_CHANNEL:
        launch_args["channel"] = _ACTIVE_CHANNEL
    _BROWSER = pw.chromium.launch(**launch_args)
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
    """Render a JS-heavy page and return its full HTML."""
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
        page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
        try:
            page.wait_for_selector(wait_selector, timeout=timeout_ms // 2)
        except Exception:
            pass

        html = page.content()
        page.close()
        return html
    except Exception as e:
        log.debug("Headless render failed for %s: %s", url, e)
        return None


def extract_links(html: str, base_url: str = "") -> list[str]:
    """Extract all <a href> links from HTML."""
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
