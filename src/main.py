"""Main entry point for the Repair Manual Scraper."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from src.cli.interactive import InteractiveCLI
from src.engine.scraper import ScraperEngine
from src.storage.filesystem import format_size


def _parse_size(s: str) -> int:
    """Parse size string like '200MB', '1GB' to bytes."""
    s = s.strip().upper()
    multipliers = {'B': 1, 'KB': 1024, 'MB': 1024 ** 2, 'GB': 1024 ** 3}
    for unit, mult in sorted(multipliers.items(), key=lambda x: -x[1]):
        if s.endswith(unit):
            return int(float(s[:-len(unit)]) * mult)
    return int(s)  # raw bytes


def main():
    if len(sys.argv) > 1:
        cmd = sys.argv[1].lower()

        if cmd == "start":
            # python -m src.main start <brand> [size]
            brands = None
            size_override = None

            if len(sys.argv) >= 3:
                brand_arg = sys.argv[2].lower()
                if brand_arg != 'all':
                    brands = [b.strip() for b in brand_arg.split(',')]

            if len(sys.argv) >= 4:
                size_override = _parse_size(sys.argv[3])

            engine = ScraperEngine(Path("config"))
            brand_str = ', '.join(brands) if brands else 'all'
            size_str = format_size(size_override) if size_override else format_size(engine.config.total_size_limit)

            print(f"Repair Manual Scraper")
            print(f"  Brands: {brand_str}")
            print(f"  Limit:  {size_str}")
            print("-" * 50)

            try:
                index = engine.run(size_override=size_override, brands=brands)
                print("-" * 50)
                print("Done!")
                if engine.size_tracker and engine.size_tracker.skipped_files:
                    count = len(engine.size_tracker.skipped_files)
                    need = format_size(engine.size_tracker.skipped_total_bytes)
                    print(f"\n[WARN] {count} items skipped — need ~{need} more. Try a larger limit.")
            except ValueError as e:
                print(f"[ERROR] {e}")
                sys.exit(1)
            except KeyboardInterrupt:
                print("\n[PAUSED] State saved. Re-run to resume.")
            return

        elif cmd == "status":
            engine = ScraperEngine(Path("config"))
            engine.setup()
            s = engine.get_status()
            print(f"Downloaded: {s['downloaded']} / {s['limit']} ({s['usage_percent']:.1f}%)")
            print(f"Queue:      {s['queue_size']} pending")
            if s.get('skipped_count', 0):
                print(f"Skipped:    {s['skipped_count']} items (~{s['skipped_bytes']} more needed)")
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
            print("  python -m src.main start samsung,xiaomi 500MB")
            print("  python -m src.main start all")
            return

    # Interactive mode (default)
    cli = InteractiveCLI()
    cli.run_interactive()


if __name__ == "__main__":
    main()
