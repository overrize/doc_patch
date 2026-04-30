"""Product folder organizer for scraped content."""

import logging
from pathlib import Path

from ..types import ScrapedItem, ContentType, Product
from .filesystem import ensure_dir, safe_filename, write_file

log = logging.getLogger(__name__)


class ContentOrganizer:
    """Organizes scraped content into brand > product > category folders."""

    # Subdirectories within each product folder
    CATEGORY_DIRS = {
        ContentType.GUIDE: "guides",
        ContentType.MANUAL: "manuals",
        ContentType.IMAGE: "images",
        ContentType.SCHEMATIC: "schematics",
        ContentType.TEARDOWN: "teardowns",
        ContentType.SPECS: "specs",
    }

    def __init__(self, output_root: Path):
        self.output_root = output_root
        ensure_dir(output_root)

    def product_folder(self, product: Product) -> Path:
        """Get the folder path for a specific product."""
        return self.output_root / product.brand / product.folder_name

    def item_folder(self, product: Product, content_type: ContentType) -> Path:
        """Get the category subfolder for a product."""
        base = self.product_folder(product)
        sub = self.CATEGORY_DIRS.get(content_type, "other")
        return ensure_dir(base / sub)

    def organize(self, item: ScrapedItem) -> Path:
        """Save a scraped item to the correct product folder.
        
        Returns the path where the item was saved.
        """
        if item.matched_product is None:
            # Store unmatched items in _uncategorized/
            folder = ensure_dir(self.output_root / "_uncategorized" / item.platform.value)
            filename = safe_filename(f"{item.title}_{item.content_type.value}")
        else:
            folder = self.item_folder(item.matched_product, item.content_type)
            prefix = item.platform.value
            filename = safe_filename(f"{prefix}_{item.title}")

        # Ensure extension
        if not filename.endswith(item.file_extension):
            filename = filename[:150] + item.file_extension
        else:
            filename = filename[:150]

        filepath = folder / filename
        return filepath

    def save_item(self, item: ScrapedItem) -> int:
        """Save item content to the organized path. Returns bytes written."""
        if item.content_bytes is None:
            log.warning(f"No content to save for: {item.title}")
            return 0

        target_path = self.organize(item)
        write_file(target_path, item.content_bytes)
        item.file_path = target_path
        return item.size_bytes

    def build_index(self) -> dict:
        """Generate an index of all collected content."""
        index = {}
        for product_dir in self.output_root.iterdir():
            if not product_dir.is_dir() or product_dir.name.startswith('_'):
                continue
            brand = product_dir.name
            index[brand] = {}
            for prod_path in product_dir.iterdir():
                if prod_path.is_dir() and not prod_path.name.startswith('_'):
                    prod_name = prod_path.name
                    index[brand][prod_name] = {}
                    for cat_path in prod_path.iterdir():
                        if cat_path.is_dir():
                            files = [f.name for f in cat_path.iterdir() if f.is_file()]
                            index[brand][prod_name][cat_path.name] = {
                                'count': len(files),
                                'files': files[:20],  # First 20 for preview
                            }
        return index
