"""Platform adapter modules for different repair guide sources.

Each module implements a BasePlatformScraper subclass for one repair-guide source.
"""
from .base import BasePlatformScraper
from .apple import AppleScraper
from .samsung import SamsungScraper
from .ifixit import IFixitScraper
from .xiaomi import XiaomiScraper

__all__ = [
    "BasePlatformScraper",
    "AppleScraper",
    "IFixitScraper",
    "SamsungScraper",
    "XiaomiScraper",
]
