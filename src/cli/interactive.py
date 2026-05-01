"""Interactive terminal UI for the repair manual scraper."""

import time
from pathlib import Path

from ..engine.scraper import ScraperEngine
from ..storage.filesystem import format_size


_AVAILABLE_BRANDS = {"apple", "samsung", "xiaomi", "all"}


class InteractiveCLI:
    """Interactive terminal interface for manual scraper control."""

    def __init__(self):
        self.engine = ScraperEngine(Path("config"))
        self.engine.setup()
        self.running = False

    def print_banner(self):
        print(r"""
  Repair Manual Scraper v0.2.0

  Usage: start [brand] [size]   e.g. start, start apple, start 200MB
         brands                  list available brands
         status                  show progress + completed products
         stop / resume           pause / continue
         help / quit
        """)

    def print_help(self):
        print("""
Commands:
  start [brand] [size]   Begin scraping. No args = all brands, default size.
                         brand: apple|samsung|xiaomi|all (or comma-sep)
                         size: 200MB, 500MB, 1GB (default: config settings.yaml)
  brands                 List available brands
  status                 Show progress, completed products, skip warnings
  stop                   Pause and save state
  resume                 Continue from last saved state
  quit                   Exit

Examples:
  > start                 # all brands, default size
  > start 200MB           # all brands, 200MB limit
  > start apple           # one brand, default size
  > start samsung 500MB   # one brand, 500MB limit
  > status
        """)

    def _parse_size(self, s: str) -> int:
        """Parse size string like '200MB', '1GB' to bytes."""
        s = s.strip().upper()
        multipliers = {'B': 1, 'KB': 1024, 'MB': 1024**2, 'GB': 1024**3}
        for unit, mult in sorted(multipliers.items(), key=lambda x: -x[1]):
            if s.endswith(unit):
                try:
                    return int(float(s[:-len(unit)]) * mult)
                except ValueError:
                    pass
        try:
            return int(s)  # raw bytes
        except ValueError:
            raise ValueError(f"Invalid size: '{s}'. Use 200MB, 1GB, etc.")

    def _is_size_arg(self, s: str) -> bool:
        """Check if a string looks like a size argument (ends with B/KB/MB/GB/TB)."""
        s_upper = s.strip().upper()
        return any(s_upper.endswith(u) for u in ('B', 'KB', 'MB', 'GB', 'TB'))

    def cmd_start(self, args: list[str]):
        """Start the crawling process.
        
        No args: all brands, config default size.
        start <size>           → all brands, specified size (e.g. start 200MB)
        start <brand>          → one brand, default size
        start <brand> <size>   → one brand, specified size
        start <brand,brand> [size] → multiple brands
        """
        if self.running:
            print("Scraper is already running! Use 'stop' first.")
            return
        
        brands = None  # None = all
        size_override = None
        
        if args:
            first = args[0].lower().strip()
            
            if self._is_size_arg(first):
                # start 200MB → all brands, given size
                try:
                    size_override = self._parse_size(first)
                except ValueError as e:
                    print(f"[ERROR] {e}")
                    return
            else:
                # start apple [200MB]
                if first == 'all':
                    brands = None
                else:
                    brands = [b.strip() for b in first.split(',')]
                    invalid = [b for b in brands if b not in _AVAILABLE_BRANDS]
                    if invalid:
                        print(f"Unknown brand(s): {', '.join(invalid)}")
                        print(f"Available: {', '.join(sorted(_AVAILABLE_BRANDS))} + all")
                        return
                
                if len(args) >= 2:
                    try:
                        size_override = self._parse_size(args[1])
                    except ValueError as e:
                        print(f"[ERROR] {e}")
                        return
        
        size_str = format_size(size_override) if size_override else format_size(self.engine.config.total_size_limit)
        brand_str = ', '.join(brands) if brands else 'all'
        
        print(f"Starting: brands={brand_str}, limit={size_str}")
        print("-" * 50)
        
        self.running = True
        try:
            index = self.engine.run(size_override=size_override, brands=brands)
            self.running = False
            print("-" * 50)
            print("Crawl complete!")
            self._print_index_summary(index)
            self._print_skip_warnings()
        except KeyboardInterrupt:
            print("\n[PAUSED] State saved. Use 'resume' to continue.")
            self.running = False
        except ValueError as e:
            print(f"\n[ERROR] {e}")
            self.running = False
        except Exception as e:
            print(f"\n[ERROR] {e}")
            print("Check manuals/errors.log for details.")
            self.running = False

    def cmd_status(self):
        """Show current progress with skip warnings."""
        status = self.engine.get_status()
        brands_str = ', '.join(status['brands']) if status.get('brands') else 'all'
        completed = status.get('completed', [])
        print(f"""
=== Scraper Status ===
Brands:      {brands_str}
Downloaded:  {status['downloaded']} / {status['limit']} ({status['usage_percent']:.1f}%)
Queue:       {status['queue_size']} URLs pending
Elapsed:     {status['elapsed']} seconds
        """.strip())
        
        if completed:
            print(f"\n  Already done ({len(completed)} products):")
            for name in completed[:10]:
                print(f"    - {name}")
            if len(completed) > 10:
                print(f"    ... and {len(completed) - 10} more")
        
        if status.get('skipped_count', 0) > 0:
            print(f"\n[WARN] {status['skipped_count']} items skipped — need ~{status['skipped_bytes']} more")
            print("  Try: start <brand> <larger_size>")
            for fname, size in status.get('skipped_files', [])[:3]:
                print(f"  - {fname} ({format_size(size)})")

    def cmd_brands(self):
        """List available brands."""
        print("\n=== Available Brands ===")
        print("  apple    — iPhone 12–17, MacBook, iPad, Apple Watch")
        print("  samsung  — Galaxy S22–S25, Z Fold/Flip, A series")
        print("  xiaomi   — Xiaomi 12–15, Redmi Note, POCO")
        print("  all      — Everything above")
        print("\nAdd more in config/products.yaml")

    def cmd_stop(self):
        """Pause the scraper."""
        if not self.running:
            print("Scraper is not running.")
            return
        self.running = False
        self.engine.session_manager.state.queue_remaining = self.engine.queue.save_state()
        self.engine.session_manager.save()
        print("[PAUSED] State saved. Use 'resume' to continue.")

    def cmd_resume(self):
        """Resume from saved state."""
        if self.running:
            print("Already running!")
            return
        print("Resuming from saved state...")
        self.engine.running = False  # Reset to allow restart
        self.cmd_start([])  # Re-run with same params

    def _print_index_summary(self, index: dict):
        """Print a summary of collected content."""
        if not index:
            print("No content collected yet.")
            return
        
        print("\n=== Collected Content ===")
        total_guides = 0
        total_images = 0
        total_manuals = 0
        
        for brand, products in index.items():
            if brand.startswith('_'):
                continue
            print(f"\n  [{brand}]")
            for prod_name, categories in products.items():
                readable_name = prod_name.replace('_', ' ')
                guides = categories.get('guides', {}).get('count', 0)
                images = categories.get('images', {}).get('count', 0)
                manuals = categories.get('manuals', {}).get('count', 0)
                
                if guides or images or manuals:
                    print(f"    {readable_name}: {guides} guides, {images} images, {manuals} manuals")
                    total_guides += guides
                    total_images += images
                    total_manuals += manuals
        
        print(f"\n  Total: {total_guides} guides, {total_images} images, {total_manuals} manuals")

    def _print_skip_warnings(self):
        """Print warnings about skipped items."""
        if self.engine.size_tracker and self.engine.size_tracker.skipped_files:
            count = len(self.engine.size_tracker.skipped_files)
            need = format_size(self.engine.size_tracker.skipped_total_bytes)
            print(f"\n[WARN] Size limit too small — {count} items skipped (need ~{need} more)")
            print(f"  Try a larger limit next time: start <brand> <size>")
            for fname, size in self.engine.size_tracker.skipped_files[:5]:
                print(f"  - {fname} ({format_size(size)})")

    def run_interactive(self):
        """Main interactive loop."""
        self.print_banner()
        
        while True:
            try:
                cmd = input("\nscraper> ").strip()
                
                if not cmd:
                    continue
                
                parts = cmd.split()
                verb = parts[0].lower()
                args = parts[1:] if len(parts) > 1 else []
                
                if verb in ('quit', 'exit'):
                    if self.running:
                        self.cmd_stop()
                    print("Goodbye!")
                    break
                elif verb == 'help':
                    self.print_help()
                elif verb == 'start':
                    self.cmd_start(args)
                elif verb == 'status':
                    self.cmd_status()
                elif verb == 'brands':
                    self.cmd_brands()
                elif verb == 'stop':
                    self.cmd_stop()
                elif verb == 'resume':
                    self.cmd_resume()
                else:
                    print(f"Unknown: '{verb}'. Type 'help'.")
                    
            except KeyboardInterrupt:
                print("\nUse 'stop' to pause, 'quit' to exit.")
            except EOFError:
                print("\nGoodbye!")
                break
