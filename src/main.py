"""Main entry point for the Repair Manual Scraper."""

import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))


def _fix_windows_encoding():
    if sys.platform == 'win32':
        if hasattr(sys.stdout, 'reconfigure'):
            sys.stdout.reconfigure(encoding='utf-8', errors='replace')
            sys.stderr.reconfigure(encoding='utf-8', errors='replace')
        os.environ.setdefault('PYTHONIOENCODING', 'utf-8')


_fix_windows_encoding()  # noqa: E402

from src.cli.interactive import run_interactive
from src.engine.scraper import ScraperEngine
from src.storage.filesystem import format_size


def _parse_size(s: str) -> int:
    s = s.strip().upper()
    multipliers = {'B': 1, 'KB': 1024, 'MB': 1024 ** 2, 'GB': 1024 ** 3}
    for unit, mult in sorted(multipliers.items(), key=lambda x: -x[1]):
        if s.endswith(unit):
            return int(float(s[:-len(unit)]) * mult)
    return int(s)


def main():
    if len(sys.argv) > 1:
        cmd = sys.argv[1].lower()

        if cmd == "start":
            brands = None
            size_override = None

            if len(sys.argv) >= 3 and sys.argv[2].lower() != 'all':
                brand_arg = sys.argv[2].lower()
                brands = [b.strip() for b in brand_arg.split(',')]

            if len(sys.argv) >= 4:
                size_override = _parse_size(sys.argv[3])

            run_interactive(brands=brands, size_mb=int(size_override / 1024 / 1024) if size_override else None)
            return

        elif cmd == "status":
            engine = ScraperEngine(Path("config"))
            engine.setup()
            s = engine.get_status()
            print(f"Downloaded: {s['downloaded']} / {s['limit']} ({s['usage_percent']:.1f}%)")
            print(f"Queue:      {s['queue_size']} pending")
            if s.get('completed'):
                print(f"Completed:  {len(s['completed'])} products")
            if s.get('skipped_count', 0):
                print(f"Skipped:    {s['skipped_count']} items (~{s['skipped_bytes']} needed)")
            return

        elif cmd == "brands":
            print("Available brands:")
            print("  apple    — iPhone 12–17, MacBook, iPad, Apple Watch")
            print("  samsung  — Galaxy S22–S25, Z Fold/Flip, A series")
            print("  xiaomi   — Xiaomi 12–15, Redmi Note, POCO")
            print("  all      — Everything above")
            print("\nAdd more: config/products.yaml")
            return

        else:
            print("Usage:")
            print("  python -m src.main start <brand> [size]")
            print("  python -m src.main status")
            print("  python -m src.main brands")
            print("\nExamples:")
            print("  python -m src.main start apple 200MB")
            print("  python -m src.main start samsung,xiaomi")
            print("  python -m src.main start")
            return

    # Interactive mode (default, no args)
    run_interactive()
    # close headless browser on exit
    try:
        from src.platforms.headless import close_browser
        close_browser()
    except Exception:
        pass


if __name__ == "__main__":
    main()
