---
name: scrape-repair-manuals
description: Scrape and download phone repair manuals from iFixit, Samsung, Apple, Xiaomi. Use when asked to download repair guides, service manuals, teardown guides, or phone repair documentation. Supports brand filtering and size limits.
license: MIT
compatibility: claude-code
metadata:
  version: "0.2.0"
---

# Repair Manual Scraper

## Quick Start

```bash
pip install -r requirements.txt
python -m src.main start apple 200MB
```

## Commands

```bash
python -m src.main start <brand> [size]   # Begin scraping
python -m src.main status                 # Check progress
python -m src.main brands                 # List available brands
```

| Brand | Products Covered |
|-------|-----------------|
| `apple` | iPhone 12–17, MacBook M3/M4, iPad Pro, Apple Watch |
| `samsung` | Galaxy S22–S25, Z Fold/Flip, A series |
| `xiaomi` | Xiaomi 12–15, Redmi Note, POCO |
| `all` | All of the above |

## Output Structure

```
manuals/
  <Brand>/
    <Product>/
      guides/   — HTML repair guides
      images/   — Step images
      manuals/  — PDF manuals
```

## Configuration

- `config/products.yaml` — Add/modify target products
- `config/settings.yaml` — Size limits, rate limits, LLM settings
- `config/platforms.yaml` — Enable/disable platforms
