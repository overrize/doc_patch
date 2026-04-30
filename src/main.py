"""Main entry point for the Repair Manual Scraper."""

import sys
from pathlib import Path

# Ensure src is on path
sys.path.insert(0, str(Path(__file__).parent))

from src.cli.interactive import InteractiveCLI
from src.engine.scraper import ScraperEngine


def main():
    """Entry point - launches interactive CLI or runs headless."""
    if len(sys.argv) > 1:
        cmd = sys.argv[1]
        engine = ScraperEngine(Path("config"))
        
        if cmd == "headless":
            print("Starting headless crawl...")
            engine.setup()
            index = engine.run()
            print("Headless crawl completed!")
            return
        elif cmd == "status":
            engine.setup()
            print(engine.get_status())
            return
        elif cmd == "index":
            engine.setup()
            index = engine.organizer.build_index()
            for brand, products in index.items():
                print(f"\n[{brand}]")
                for name, cats in products.items():
                    print(f"  {name}: {cats}")
            return
        else:
            print(f"Usage: python -m src.main [headless|status|index]")
            return
    
    # Interactive mode (default)
    cli = InteractiveCLI()
    cli.run_interactive()


if __name__ == "__main__":
    main()
