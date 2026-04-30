"""Configuration loader for the scraper."""

import yaml
from pathlib import Path
from typing import Optional

from .types import ScraperConfig, Product


def load_settings(config_dir: Path) -> ScraperConfig:
    """Load general settings from config/settings.yaml."""
    settings_path = config_dir / "settings.yaml"
    with open(settings_path, 'r', encoding='utf-8') as f:
        data = yaml.safe_load(f)

    return ScraperConfig(
        total_size_limit=data['total_size_limit'],
        rate_limits=data.get('rate_limit', {}),
        request_timeout=data.get('request', {}).get('timeout', 30),
        max_retries=data.get('request', {}).get('max_retries', 3),
        retry_delay=data.get('request', {}).get('retry_delay', 5),
        user_agent=data.get('request', {}).get('user_agent', 'RepairManualBot/1.0'),
        state_file=config_dir.parent / data.get('session', {}).get('state_file', 'config/state.json'),
        autosave_interval=data.get('session', {}).get('autosave_interval', 60),
        min_guide_words=data.get('content', {}).get('min_guide_words', 50),
        allowed_extensions=set(data.get('content', {}).get('allowed_extensions', ['.html', '.pdf', '.jpg', '.png'])),
        max_file_size=data.get('content', {}).get('max_file_size', 50 * 1024 * 1024),
        llm_enabled=data.get('llm', {}).get('enabled', False),
        llm_provider=data.get('llm', {}).get('provider', 'deepseek'),
        llm_model=data.get('llm', {}).get('model', 'deepseek-chat'),
        llm_min_confidence=data.get('llm', {}).get('min_confidence_threshold', 0.7),
        log_level=data.get('logging', {}).get('level', 'INFO'),
        log_file=config_dir.parent / data.get('logging', {}).get('file', 'manuals/scraper.log'),
        output_dir=config_dir.parent / "manuals",
    )


def load_products(config_dir: Path) -> list[Product]:
    """Load target products from config/products.yaml."""
    products_path = config_dir / "products.yaml"
    with open(products_path, 'r', encoding='utf-8') as f:
        data = yaml.safe_load(f)

    products = []
    for brand, items in data.items():
        for item in items:
            folder_name = f"{brand}_{item['name']}".replace(' ', '_').replace('/', '_').replace('(', '').replace(')', '')
            products.append(Product(
                brand=brand,
                name=item['name'],
                keywords=item.get('keywords', [item['name'].lower()]),
                folder_name=folder_name,
            ))
    return products


def load_platforms(config_dir: Path) -> dict:
    """Load platform configurations from config/platforms.yaml."""
    platforms_path = config_dir / "platforms.yaml"
    with open(platforms_path, 'r', encoding='utf-8') as f:
        data = yaml.safe_load(f)
    return {k: v for k, v in data.get('platforms', {}).items() if v.get('enabled', True)}
