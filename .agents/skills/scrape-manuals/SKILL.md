---
name: scrape-repair-manuals
description: Scrape and download phone repair manuals from iFixit, Samsung, Apple, Xiaomi. Use when asked to download repair guides, service manuals, teardown guides, or phone repair documentation. Supports brand filtering and size limits.
license: MIT
compatibility: openclaw
metadata:
  version: "0.2.0"
---

# Repair Manual Scraper

## Usage

```bash
pip install -r requirements.txt
python -m src.main start <brand> [size]
```

| Brand | Coverage |
|-------|----------|
| `apple` | iPhone, MacBook, iPad, Apple Watch |
| `samsung` | Galaxy S/Z/A series |
| `xiaomi` | Xiaomi, Redmi, POCO |
| `all` | All brands |

Size examples: `200MB`, `500MB`, `1GB`.

## Output

Files saved to `manuals/<Brand>/<Product>/guides|images|manuals/`.

## Config Files

- Products: `config/products.yaml`
- Settings: `config/settings.yaml`
- Platforms: `config/platforms.yaml`
