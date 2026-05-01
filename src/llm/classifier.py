"""LLM-assisted product name classification for scraped content.

Uses a configured LLM (via OpenCode's provider system) to match scraped
guide titles/content to the correct product when keyword matching is ambiguous.
"""

import json
import logging
from typing import Optional

from ..types import Product, Platform

log = logging.getLogger(__name__)


# Product lookup table built from products config
_PRODUCT_LOOKUP: dict[str, list[Product]] = {}
_products_loaded = False


def init_product_lookup(products: list[Product]):
    """Initialize the product lookup table for classification."""
    global _products_loaded, _PRODUCT_LOOKUP
    _PRODUCT_LOOKUP = {}
    for p in products:
        if p.brand not in _PRODUCT_LOOKUP:
            _PRODUCT_LOOKUP[p.brand] = []
        _PRODUCT_LOOKUP[p.brand].append(p)
    _products_loaded = True


def match_by_keywords(title: str, content: str, products: list[Product]) -> Optional[Product]:
    """Simple keyword matching - first pass before LLM.
    
    Returns the best matching Product, or None if no match found.
    """
    text = (title + " " + content[:500]).lower()
    
    best_match: Optional[Product] = None
    best_score = 0
    
    for product in products:
        score = 0
        for keyword in product.keywords:
            kw = keyword.lower()
            if kw in text:
                # Model numbers (short codes) get higher weight
                if len(kw) <= 8 and any(c.isdigit() for c in kw):
                    score += 3
                else:
                    score += 1
        
        if score > best_score:
            best_score = score
            best_match = product
    
    return best_match if best_score >= 1 else None


def llm_classify(
    title: str,
    content: str,
    platform: Platform,
    products: list[Product],
    min_confidence: float = 0.7,
) -> Optional[Product]:
    """Use LLM to classify scraped content to the correct product.
    
    This is called when keyword matching is ambiguous (multiple matches
    or no clear match). Returns the best Product or None.
    
    Note: This function is a placeholder for LLM integration.
    In production, this would call an LLM API (DeepSeek, Claude, etc.)
    via the OpenCode provider system.
    """
    if not products:
        return None
    
    # Build a prompt for the LLM
    product_list = "\n".join(
        f"- {p.brand}: {p.name} (keywords: {', '.join(p.keywords[:3])})"
        for p in products
    )
    
    prompt = f"""Given the following repair guide, identify which product it belongs to.

TITLE: {title}
PLATFORM: {platform.value}
CONTENT PREVIEW: {content[:1000]}

Available products:
{product_list}

IMPORTANT:
- Match model numbers (e.g., "a2849", "sm-s928") with highest priority
- If the content mentions a specific product name, match to that
- If ambiguous, pick the closest match or respond "none"
- Confidence is a number between 0.0 and 1.0

Respond in JSON format:
{{"product": "Brand: Product Name", "confidence": 0.95, "reasoning": "..."}}"""

    # Placeholder: In production, this would call the LLM
    # For now, fall back to keyword matching with logging
    log.debug(f"LLM classify called for: {title}")
    result = match_by_keywords(title, content, products)
    if result:
        log.info(f"Keyword match: {result.brand} {result.name} for '{title}'")
    else:
        log.info(f"No product match for: '{title}' (platform: {platform.value})")
    
    return result


def classify_item(
    title: str,
    content: str,
    platform: Platform,
    all_products: list[Product],
    use_llm: bool = True,
    min_confidence: float = 0.7,
) -> Optional[Product]:
    """Full classification pipeline: keyword matching → LLM fallback.
    
    Returns the matched Product or None.
    """
    if not _products_loaded:
        init_product_lookup(all_products)
    
    # Stage 1: Keyword matching
    result = match_by_keywords(title, content, all_products)
    if result:
        return result
    
    # Stage 2: LLM classification (if enabled)
    if use_llm:
        result = llm_classify(title, content, platform, all_products, min_confidence)
    
    return result
