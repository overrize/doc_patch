---
name: scrape-repair-manuals
description: Scrape and download phone repair manuals from iFixit, Samsung, Apple, Xiaomi. Use when asked to download repair guides, service manuals, teardown guides, or phone repair documentation. Supports brand filtering (apple, samsung, xiaomi, all) and size limits (e.g., 200MB, 500MB, 1GB).
license: MIT
compatibility: opencode
metadata:
  workflow: scraping
  audience: developers
  version: "0.2.0"
---

# Repair Manual Scraper

Scrapes phone repair guides and manuals from multiple platforms (iFixit, Samsung, Apple, Xiaomi)
and organizes them by brand/product/category.

## Usage

```bash
python -m src.main start <brand> [size]
```

### Arguments

| Arg | Required | Description |
|-----|----------|-------------|
| `brand` | Yes | Target brand: `apple`, `samsung`, `xiaomi`, `all`, or comma-separated: `samsung,xiaomi` |
| `size` | No | Download limit: `200MB`, `500MB`, `1GB`. Default: 1GB |

### Examples

```bash
python -m src.main start apple 200MB
python -m src.main start samsung,xiaomi 500MB
python -m src.main start all
```

## Prerequisites

```bash
pip install -r requirements.txt  # requests, pyyaml
```

## Output

Results go to `manuals/<Brand>/<Product>/`:
- `guides/` — HTML repair guide text
- `images/` — Repair step images
- `manuals/` — PDF service manuals

## Configuration

- Add products: `config/products.yaml`
- Change defaults: `config/settings.yaml`
- Enable LLM matching: set `llm.enabled: true` in settings.yaml
