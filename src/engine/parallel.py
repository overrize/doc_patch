"""Parallel download engine — ThreadPoolExecutor for maximum throughput.

Downloads images in parallel batches, tracking speed and bytes.
Replaces the serial for-loop in platform adapters.
"""

import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable, Optional

import requests

log = logging.getLogger(__name__)

# Shared session with connection pooling
_session: Optional[requests.Session] = None
_speed_samples: list[tuple[float, int]] = []  # (timestamp, bytes_downloaded)


def get_session() -> requests.Session:
    """Get or create a shared session with connection pooling."""
    global _session
    if _session is None:
        _session = requests.Session()
        adapter = requests.adapters.HTTPAdapter(
            pool_connections=20,
            pool_maxsize=50,
            max_retries=1,
        )
        _session.mount('https://', adapter)
        _session.mount('http://', adapter)
        _session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/125.0.0.0 Safari/537.36',
        })
    return _session


def _download_one(url: str, timeout: int = 15) -> Optional[tuple[str, bytes]]:
    """Download a single URL. Returns (url, bytes) or None."""
    try:
        resp = get_session().get(url, timeout=timeout)
        resp.raise_for_status()
        return (url, resp.content)
    except Exception:
        return None


def batch_download(urls: list[str], max_workers: int = 12, timeout: int = 15,
                   progress_cb: Optional[Callable] = None) -> dict[str, bytes]:
    """Download multiple URLs in parallel.

    Args:
        urls: List of URLs to download.
        max_workers: Maximum concurrent download threads.
        timeout: Per-request timeout in seconds.
        progress_cb: Optional callback(bytes_just_downloaded) for progress.

    Returns:
        Dict mapping URL → bytes (only successful downloads).
    """
    if not urls:
        return {}

    results: dict[str, bytes] = {}
    total = 0

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(_download_one, url, timeout): url for url in urls}
        for future in as_completed(futures):
            result = future.result()
            if result:
                url, data = result
                results[url] = data
                total += len(data)
                if progress_cb:
                    progress_cb(len(data))
                _record_speed(len(data))

    return results


def _record_speed(bytes_downloaded: int):
    """Record a speed sample for tracking."""
    global _speed_samples
    now = time.time()
    _speed_samples.append((now, bytes_downloaded))
    # Keep last 60 samples
    if len(_speed_samples) > 60:
        _speed_samples = _speed_samples[-60:]


def get_speed() -> tuple[float, float]:
    """Get current download speed.
    
    Returns (bytes_per_second, bytes_per_second_5s_average).
    """
    global _speed_samples
    now = time.time()
    
    # Instant speed (last sample)
    instant = 0.0
    if _speed_samples:
        t, b = _speed_samples[-1]
        instant = b / max(0.5, now - t) if now - t > 0 else b
    
    # 5-second average
    recent = [(t, b) for t, b in _speed_samples if now - t <= 5]
    avg = sum(b for _, b in recent) / max(5.0, now - recent[0][0]) if recent else instant
    
    return instant, avg


def format_speed(bytes_per_sec: float) -> str:
    """Human-readable speed string."""
    if bytes_per_sec < 1024:
        return f"{bytes_per_sec:.0f} B/s"
    elif bytes_per_sec < 1024 * 1024:
        return f"{bytes_per_sec / 1024:.1f} KB/s"
    else:
        return f"{bytes_per_sec / 1024 / 1024:.1f} MB/s"
