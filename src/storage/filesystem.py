"""File I/O operations for scraped content."""

import logging
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)


def ensure_dir(path: Path) -> Path:
    """Create directory if it doesn't exist."""
    path.mkdir(parents=True, exist_ok=True)
    return path


def safe_filename(name: str, max_length: int = 100) -> str:
    """Convert a string to a safe filesystem filename."""
    import re
    # Remove unsafe characters
    safe = re.sub(r'[<>:"/\\|?*]', '_', name)
    # Replace spaces with underscores
    safe = safe.replace(' ', '_')
    # Collapse multiple underscores
    safe = re.sub(r'_+', '_', safe)
    # Truncate
    if len(safe) > max_length:
        safe = safe[:max_length]
    # Strip trailing dots and spaces (Windows issue)
    safe = safe.rstrip('. ')
    return safe


def write_file(path: Path, data: bytes) -> int:
    """Write bytes to a file. Returns number of bytes written."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return len(data)


def read_file(path: Path) -> Optional[bytes]:
    """Read file contents. Returns None if file doesn't exist."""
    if path.exists():
        return path.read_bytes()
    return None


def get_file_size(path: Path) -> int:
    """Get file size in bytes, 0 if doesn't exist."""
    return path.stat().st_size if path.exists() else 0


def format_size(bytes_count: int) -> str:
    """Human-readable file size."""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if bytes_count < 1024:
            return f"{bytes_count:.1f} {unit}"
        bytes_count /= 1024
    return f"{bytes_count:.1f} TB"
