---
description: Scrape repair manuals by brand (apple, samsung, xiaomi, or all)
agent: build
---

You are running the Repair Manual Scraper — a Python CLI that downloads phone repair guides
from iFixit, Samsung, Apple, Xiaomi platforms into organized product folders.

**IMPORTANT**: Do NOT chat. Execute immediately with the bash tool.

## Steps

1. First, verify the Python environment is ready:
```bash
python --version && pip show requests pyyaml >/dev/null 2>&1 && echo "Ready" || echo "Need setup"
```
If "Need setup" — run `pip install -r requirements.txt` first.

2. Parse arguments — user said: $ARGUMENTS
   - $1 = brand (required: apple, samsung, xiaomi, all, or comma-separated like samsung,xiaomi)
   - $2 = size limit (optional, e.g. 200MB, 500MB, 1GB. Default: 500MB)
   If brand is missing, ask user ONE question: "Which brand? (apple / samsung / xiaomi / all)"

3. Run the scraper:
```bash
python -m src.main start $1 $2
```

4. When the scraper finishes, print a brief summary:
   - What brand(s) were scraped
   - How many guides/images/manuals were downloaded
   - Total size downloaded
   - Any warnings (size limit hits, failed downloads)
   - Where the files are: `manuals/<Brand>/<Product>/`

## Quick reference
| Brand | What it covers |
|-------|---------------|
| apple | iPhone 12–17, MacBook M3/M4, iPad Pro, Apple Watch |
| samsung | Galaxy S22–S25, Z Fold/Flip, A series |
| xiaomi | Xiaomi 12–15, Redmi Note, POCO |
| all | Everything above |

Config files (to add more products): `config/products.yaml`
Size limit global: `config/settings.yaml`
