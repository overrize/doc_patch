"""Interactive terminal UI for the repair manual scraper."""

import sys
import time
from pathlib import Path

from ..engine.scraper import ScraperEngine
from ..storage.filesystem import format_size


class InteractiveCLI:
    """Interactive terminal interface for manual scraper control."""

    def __init__(self):
        self.engine = ScraperEngine(Path("config"))
        self.running = False

    def print_banner(self):
        print(r"""
╔══════════════════════════════════════════════════════╗
║        Repair Manual Scraper v0.1.0                  ║
║        Phone Repair Documentation Crawler            ║
╚══════════════════════════════════════════════════════╝
        """)

    def print_help(self):
        print("""
Commands:
  setup       Initialize scraper and load configuration
  start       Begin scraping all configured platforms
  status      Show current progress (downloaded, queue, etc.)
  platforms   List configured platforms and their status
  products    List target products
  index       Show collected content by product
  stop        Pause the scraper (saves state for resume)
  resume      Resume from last saved state
  limit       Show/set size limit
  quit        Exit the program

Examples:
  > setup
  > start
  > status
        """)

    def cmd_setup(self):
        """Initialize the scraper engine."""
        print("Initializing scraper...")
        try:
            self.engine.setup()
            print(f"[OK] {len(self.engine.products)} products loaded")
            print(f"[OK] {len(self.engine.platforms_config)} platforms configured")
            print(f"[OK] Size limit: {format_size(self.engine.size_tracker.max_bytes)}")
            print(f"[OK] Output: {self.engine.config.output_dir}")
        except Exception as e:
            print(f"[ERROR] Setup failed: {e}")

    def cmd_start(self):
        """Start the crawling process."""
        if self.running:
            print("Scraper is already running!")
            return
        
        print(f"Starting crawl...")
        print(f"Target: {self.engine.size_tracker.max_bytes / 1024 / 1024:.0f} MB limit")
        print(f"Products: {len(self.engine.products)}")
        print(f"Platforms: {len(self.engine.platforms_config)}")
        print("-" * 50)
        
        self.running = True
        try:
            index = self.engine.run()
            self.running = False
            print("-" * 50)
            print("Crawl complete!")
            self._print_index_summary(index)
        except KeyboardInterrupt:
            print("\n[PAUSED] Crawl interrupted. State saved for resume.")
            self.running = False
        except Exception as e:
            print(f"\n[ERROR] {e}")
            self.running = False

    def cmd_status(self):
        """Show current progress."""
        status = self.engine.get_status()
        print(f"""
=== Scraper Status ===
Downloaded:  {status['downloaded']}
Remaining:   {status['remaining']} of 1 GB
Progress:    {status['usage_percent']:.1f}%
Queue:       {status['queue_size']} URLs pending
Elapsed:     {status['elapsed']} seconds
Running:     {'Yes' if self.running else 'No'}
        """.strip())

    def cmd_platforms(self):
        """List configured platforms."""
        print("\n=== Configured Platforms ===")
        for name, cfg in self.engine.platforms_config.items():
            status = "ENABLED" if cfg.get('enabled', True) else "DISABLED"
            print(f"  [{status}] {cfg.get('name', name):20s} - {cfg.get('base_url', 'N/A')}")
        print()

    def cmd_products(self):
        """List target products."""
        print("\n=== Target Products ===")
        brands = {}
        for p in self.engine.products:
            if p.brand not in brands:
                brands[p.brand] = []
            brands[p.brand].append(p.name)
        
        for brand, names in brands.items():
            print(f"\n  {brand}:")
            for name in sorted(names):
                print(f"    - {name}")
        print(f"\n  Total: {len(self.engine.products)} products")

    def cmd_index(self):
        """Show collected content index."""
        try:
            index = self.engine.organizer.build_index()
            self._print_index_summary(index)
        except Exception as e:
            print(f"[ERROR] Cannot build index: {e}")

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
        self.cmd_start()

    def cmd_limit(self, args: list[str] = None):
        """Show or change the size limit."""
        if args:
            try:
                new_limit_mb = float(args[0])
                new_limit_bytes = int(new_limit_mb * 1024 * 1024)
                self.engine.size_tracker.max_bytes = new_limit_bytes
                print(f"Size limit set to {new_limit_mb} MB")
            except ValueError:
                print("Usage: limit <megabytes>")
        else:
            print(f"Current limit: {format_size(self.engine.size_tracker.max_bytes)}")
            print(f"Remaining: {format_size(self.engine.size_tracker.remaining)}")

    def run_interactive(self):
        """Main interactive loop."""
        self.print_banner()
        print("Type 'help' for commands, 'quit' to exit.")
        print("\nQuick start: type 'setup' then 'start'")
        
        while True:
            try:
                cmd = input("\nscraper> ").strip().lower()
                
                if not cmd:
                    continue
                
                if cmd == 'quit' or cmd == 'exit':
                    if self.running:
                        print("Stopping scraper...")
                        self.cmd_stop()
                    print("Goodbye!")
                    break
                elif cmd == 'help':
                    self.print_help()
                elif cmd == 'setup':
                    self.cmd_setup()
                elif cmd == 'start':
                    self.cmd_start()
                elif cmd == 'status':
                    self.cmd_status()
                elif cmd == 'platforms':
                    self.cmd_platforms()
                elif cmd == 'products':
                    self.cmd_products()
                elif cmd == 'index':
                    self.cmd_index()
                elif cmd == 'stop':
                    self.cmd_stop()
                elif cmd == 'resume':
                    self.cmd_resume()
                elif cmd.startswith('limit'):
                    parts = cmd.split()[1:]
                    self.cmd_limit(parts if parts else None)
                else:
                    print(f"Unknown command: '{cmd}'. Type 'help' for available commands.")
                    
            except KeyboardInterrupt:
                print("\nUse 'stop' to pause, 'quit' to exit.")
            except EOFError:
                print("\nGoodbye!")
                break
