"""Rich-enhanced CLI for the repair manual scraper — progress, no screen takeover."""

import sys
import time
import threading
from pathlib import Path
from typing import Optional

from ..engine.scraper import ScraperEngine
from ..storage.filesystem import format_size

try:
    from rich.console import Console
    from rich.table import Table
    from rich.text import Text
    HAS_RICH = True
except ImportError:
    HAS_RICH = False

_WIN32 = sys.platform == 'win32'
if _WIN32:
    import msvcrt
else:
    import select

_KEY_PRESSED = None
_KEY_LOCK = threading.Lock()


def _kb_listener():
    global _KEY_PRESSED
    while True:
        try:
            if _WIN32:
                if msvcrt.kbhit():
                    with _KEY_LOCK:
                        _KEY_PRESSED = msvcrt.getch().decode('utf-8', errors='replace').lower()
            else:
                import tty
                import termios
                fd = sys.stdin.fileno()
                old = termios.tcgetattr(fd)
                try:
                    tty.setraw(fd)
                    if select.select([sys.stdin], [], [], 0.1)[0]:
                        with _KEY_LOCK:
                            _KEY_PRESSED = sys.stdin.read(1).lower()
                finally:
                    termios.tcsetattr(fd, termios.TCSADRAIN, old)
        except Exception:
            pass
        time.sleep(0.05)


def _pop_key() -> Optional[str]:
    global _KEY_PRESSED
    with _KEY_LOCK:
        k = _KEY_PRESSED
        _KEY_PRESSED = None
    return k


def _elapsed_str(seconds: float) -> str:
    m, s = divmod(int(seconds), 60)
    return f"{m:02d}:{s:02d}"


class RichTUI:
    """Terminal UI with progress line, no screen takeover."""

    def __init__(self):
        self.engine = ScraperEngine(Path("config"))
        self.console = Console() if HAS_RICH else None
        self.running = False
        self._start_time = 0.0
        self._discovery_time = 0.0
        self._items = 0
        self._saved = 0
        self._skipped = 0
        self._brand_counts: dict[str, int] = {}
        self._listener: Optional[threading.Thread] = None

    def _print_header(self, brands_str: str, limit_str: str):
        header = Text.assemble(
            ("\nRepair Manual Scraper v0.3.0\n", "bold cyan"),
            (f"Brands: {brands_str}   Limit: {limit_str}\n", "dim"),
            ("[s] stop  [q] quit\n\n", "dim red"),
        ) if self.console else ""
        if self.console:
            self.console.print(header)
        else:
            print("\nRepair Manual Scraper v0.3.0")
            print(f"Brands: {brands_str}   Limit: {limit_str}")
            print("[s] stop  [q] quit\n")

    def _print_progress(self):
        """One-line progress with speed."""
        elapsed = time.time() - self._start_time
        elapsed_str = _elapsed_str(elapsed)
        size = format_size(self._saved)
        limit = format_size(self.engine.size_tracker.max_bytes) if self.engine.size_tracker else "?"
        pct = self.engine.size_tracker.usage_percent if self.engine.size_tracker else 0

        # Speed
        from ..engine.parallel import get_speed, format_speed
        _, speed = get_speed()
        speed_str = format_speed(speed)

        # Time split: discovery vs download
        disc_str = _elapsed_str(self._discovery_time) if self._discovery_time else "..."

        line = f"[{elapsed_str}]  {self._items} items  {size}/{limit} ({pct:.0f}%)  {speed_str}"

        if self._brand_counts:
            parts = [f"{b}={c}" for b, c in sorted(self._brand_counts.items())]
            line += f"  |  {'  '.join(parts)}"

        if self._skipped:
            line += f"  |  skip:{self._skipped}"

        line += f"  |  disc:{disc_str}"

        if self.console:
            self.console.print(Text(line, style="green"))
        else:
            print(line)

    def _print_final(self, index: dict):
        """Print final summary table."""
        t0 = time.time() - self._start_time
        size = format_size(self._saved)

        if self.console:
            table = Table(title="Results", box=None)
            table.add_column("Brand", style="cyan")
            table.add_column("Product", style="white")
            table.add_column("Guides", justify="right")
            table.add_column("Images", justify="right")

            for brand, products in index.items():
                if brand.startswith('_'):
                    continue
                for pname, cats in products.items():
                    g = cats.get('guides', {}).get('count', 0)
                    im = cats.get('images', {}).get('count', 0)
                    if g or im:
                        table.add_row(brand, pname.replace('_', ' '), str(g), str(im))

            self.console.print()
            self.console.print(table)
            self.console.print(f"\n[bold]{self._items} items, {size}, {_elapsed_str(t0)}[/]")
        else:
            print(f"\nDone. {self._items} items, {size}, {_elapsed_str(t0)}")

        # Skip warnings
        if self.engine.size_tracker and self.engine.size_tracker.skipped_files:
            n = len(self.engine.size_tracker.skipped_files)
            need = format_size(self.engine.size_tracker.skipped_total_bytes)
            msg = f"[WARN] {n} items skipped — need ~{need} more. Try a larger limit."
            self.console.print(Text(msg, style="red")) if self.console else print(msg)

    def run(self, brands: Optional[list[str]] = None, size_mb: Optional[int] = None):
        self.running = True
        self._start_time = time.time()

        # Suppress console during engine setup
        import logging
        import io
        root = logging.getLogger()
        old_level = root.level
        root.setLevel(logging.CRITICAL)  # Silence everything

        size_override = size_mb * 1024 * 1024 if size_mb else None
        old_stdout, old_stderr = sys.stdout, sys.stderr
        sys.stdout = io.StringIO()
        sys.stderr = io.StringIO()
        try:
            self.engine.setup(size_override=size_override, brands=brands)
        finally:
            sys.stdout, sys.stderr = old_stdout, old_stderr
            root.setLevel(old_level)

        # Remove StreamHandlers — keep file handlers only
        for h in list(root.handlers):
            if isinstance(h, logging.StreamHandler) and not isinstance(h, logging.FileHandler):
                root.removeHandler(h)

        limit_str = format_size(size_override) if size_override else format_size(self.engine.config.total_size_limit)
        brand_str = ', '.join(brands) if brands else 'all'
        self._print_header(brand_str, limit_str)

        # Start keyboard listener
        self._listener = threading.Thread(target=_kb_listener, daemon=True)
        self._listener.start()

        try:
            t0 = time.time()
            self.engine.seed_products()
            self._discovery_time = time.time() - t0
            qsize = self.engine.queue.remaining_count()

            if qsize == 0:
                msg = "No guides discovered. All products may already be downloaded or platforms returned no results."
                self.console.print(Text(msg, style="yellow")) if self.console else print(f"\n{msg}")
                return

            # Main loop
            while self.running and self.engine.queue.has_pending():
                key = _pop_key()
                if key == 'q':
                    self.running = False
                    break
                elif key == 's':
                    self.running = False
                    self.engine.session_manager.save()
                    break

                item = self.engine.queue.get_next()
                if item is None:
                    break
                url, platform = item

                b = self.engine.process_url(url, platform)
                self._items += 1
                if b > 0:
                    self._saved += b
                else:
                    self._skipped += 1

                # Track per-brand
                if self.engine.session_manager.state:
                    pass  # brand tracking could be improved

                # Progress every item
                self._print_progress()

            # Final save & summary
            if self.running:
                self.engine.session_manager.save()
            index = self.engine.organizer.build_index()
            self._print_final(index)

        except KeyboardInterrupt:
            self.engine.session_manager.save()
            msg = "[STOP] Interrupted — state saved."
            self.console.print(Text(msg, style="yellow")) if self.console else print(msg)
        except Exception as e:
            msg = f"[ERROR] {e}"
            self.console.print(Text(msg, style="red")) if self.console else print(msg)
        finally:
            self.running = False
            root.setLevel(old_level)


# ── Fallback (no rich) ──────────────────────────────────────────────

class SimpleCLI:
    def __init__(self):
        self.engine = ScraperEngine(Path("config"))

    def run(self, brands=None, size_mb=None):
        size_bytes = size_mb * 1024 * 1024 if size_mb else None
        brand_str = ', '.join(brands) if brands else 'all'
        limit_str = format_size(size_bytes) if size_bytes else "default"
        print(f"Starting: {brand_str}, {limit_str}")
        try:
            self.engine.run(size_override=size_bytes, brands=brands)
        except KeyboardInterrupt:
            print("\n[STOP] State saved")


def run_interactive(brands=None, size_mb=None):
    if HAS_RICH:
        tui = RichTUI()
        tui.run(brands=brands, size_mb=size_mb)
    else:
        cli = SimpleCLI()
        cli.run(brands=brands, size_mb=size_mb)
