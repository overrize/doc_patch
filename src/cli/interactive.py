"""Rich TUI for the repair manual scraper — live progress, keyboard control."""

import sys
import time
import threading
from pathlib import Path
from typing import Optional

from ..engine.scraper import ScraperEngine
from ..storage.filesystem import format_size

try:
    from rich.live import Live
    from rich.panel import Panel
    from rich.progress import BarColumn, Progress, TextColumn
    from rich.console import Console, Group
    from rich.text import Text
    from rich import box
    HAS_RICH = True
except ImportError:
    HAS_RICH = False

_KEY_INPUT = None  # Thread-safe keyboard input
_KEY_LOCK = threading.Lock()
_WIN32 = sys.platform == 'win32'

if _WIN32:
    import msvcrt
else:
    import select


def _kb_listener():
    """Background thread: read keyboard hits into _KEY_INPUT."""
    global _KEY_INPUT
    while True:
        try:
            if _WIN32:
                if msvcrt.kbhit():
                    ch = msvcrt.getch().decode('utf-8', errors='replace').lower()
                    with _KEY_LOCK:
                        _KEY_INPUT = ch
            else:
                import tty
                import termios
                fd = sys.stdin.fileno()
                old = termios.tcgetattr(fd)
                try:
                    tty.setraw(fd)
                    if select.select([sys.stdin], [], [], 0.1)[0]:
                        ch = sys.stdin.read(1).lower()
                        with _KEY_LOCK:
                            _KEY_INPUT = ch
                finally:
                    termios.tcsetattr(fd, termios.TCSADRAIN, old)
        except Exception:
            pass
        time.sleep(0.05)


def _read_key() -> Optional[str]:
    """Read a single keystroke (non-blocking)."""
    global _KEY_INPUT
    with _KEY_LOCK:
        ch = _KEY_INPUT
        _KEY_INPUT = None
    return ch


class RichTUI:
    """Live-updating terminal UI using Rich."""

    def __init__(self):
        self.engine = ScraperEngine(Path("config"))
        self.running = False
        self.console = Console()
        self._log_lines: list[str] = []
        self._current_action = ""
        self._current_brand = ""
        self._brand_stats: dict[str, dict] = {}  # brand -> {guides, images, size}
        self._total_items = 0
        self._total_bytes = 0
        self._start_time = 0.0
        self._listener_thread: Optional[threading.Thread] = None

    # ------------------------------------------------------------------
    #  Layout builder
    # ------------------------------------------------------------------

    def _build_layout(self) -> Panel:
        """Build the TUI panel."""
        elapsed = int(time.time() - self._start_time) if self._start_time else 0
        m, s = divmod(elapsed, 60)

        # ── Size progress bar ──
        bar = Progress(
            BarColumn(bar_width=40, style="green", complete_style="bright_green"),
            TextColumn("[progress.percentage]{task.percentage:>4.0f}%"),
        )
        if self.engine.size_tracker:
            used = self.engine.size_tracker.downloaded
            limit = self.engine.size_tracker.max_bytes
            _task = bar.add_task("size", total=limit or 1, completed=used)
        else:
            _task = bar.add_task("size", total=100, completed=0)
            used, limit = 0, 0

        # ── Header ──
        header = Text.assemble(
            ("Repair Manual Scraper v0.3.0\n", "bold cyan"),
            (f"  {format_size(used)} / {format_size(limit) if limit else '?'}  ",
             "dim"),
        )

        # ── Brand breakdown ──
        brand_lines = []
        if self._brand_stats:
            brand_lines.append(Text("", style="dim"))
            for brand, stats in sorted(self._brand_stats.items()):
                count = stats.get('items', 0)
                bsize = format_size(stats.get('size', 0))
                brand_lines.append(
                    Text(f"  {brand:8s}  {count:3d} items  {bsize:>8s}", style="green")
                )
        else:
            brand_lines.append(Text("  Waiting for discovery...", style="dim"))

        # ── Current action ──
        action = Text(f"  {self._current_action or 'Starting...'}", style="yellow")

        # ── Log tail ──
        log_text = Text()
        for line in self._log_lines[-6:]:
            log_text.append(f"  {line}\n", style="dim")

        # ── Footer ──
        footer = Text.assemble(
            ("\n", ""),
            (f"  [{m:02d}:{s:02d}]", "dim"),
            ("   [s] stop", "bold red"),
            ("   [q] quit", "bold red"),
        )

        body = Group(header, bar, *brand_lines, Text(""), action, Text(""), log_text, footer)
        return Panel(body, box=box.ROUNDED, border_style="bright_black",
                     title="[bold]REPAIR MANUAL SCRAPER[/]", title_align="left")

    # ------------------------------------------------------------------
    #  Run loop
    # ------------------------------------------------------------------

    def _on_progress(self, url: str, platform: str, title: str, matched_product, bytes_saved: int):
        """Callback from engine after each URL processed."""
        self._total_items += 1
        self._total_bytes += bytes_saved
        self._current_action = title or url

        if matched_product:
            brand = matched_product.brand
            if brand not in self._brand_stats:
                self._brand_stats[brand] = {'items': 0, 'size': 0}
            self._brand_stats[brand]['items'] += 1
            self._brand_stats[brand]['size'] += bytes_saved

        if bytes_saved:
            self._log_lines.append(f"[OK] {title} ({format_size(bytes_saved)})")
        elif title:
            self._log_lines.append(f"[SKIP] {title}")
        if len(self._log_lines) > 50:
            self._log_lines = self._log_lines[-30:]

    def run(self, brands: Optional[list[str]] = None, size_mb: Optional[int] = None):
        """Run scraping with TUI display."""
        self.running = True
        self._start_time = time.time()

        # Re-setup with size/brand overrides
        size_override = size_mb * 1024 * 1024 if size_mb else None
        self.engine.setup(size_override=size_override, brands=brands)

        # Suppress console log output during TUI — keep file handlers only
        import logging
        root = logging.getLogger()
        old_handlers = list(root.handlers)
        for h in old_handlers:
            if isinstance(h, logging.StreamHandler) and not isinstance(h, logging.FileHandler):
                root.removeHandler(h)

        try:
            with Live(self._build_layout(), console=self.console, refresh_per_second=4,
                      screen=True, transient=False) as live:

                # Setup and seed (done already in __init__)
                self._current_action = "Discovering guides..."
                self.engine.seed_products()
                queue_count = self.engine.queue.remaining_count()
                self._log_lines.append(f"Queue: {queue_count} URLs")
                self._current_action = f"Starting crawl ({queue_count} URLs)..."

                items = 0
                while self.running and self.engine.queue.has_pending():
                    # Keyboard check
                    key = _read_key()
                    if key == 'q':
                        self.running = False
                        self._log_lines.append("[QUIT] User exit")
                        break
                    elif key == 's':
                        self.running = False
                        self._log_lines.append("[STOP] Paused — run 'resume' to continue")
                        break

                    item = self.engine.queue.get_next()
                    if item is None:
                        break

                    url, platform = item
                    bytes_saved = self.engine.process_url(url, platform)
                    items += 1

                    # Progress callback for TUI
                    self._on_progress(
                        url=url,
                        platform=platform.value,
                        title="",  # engine doesn't expose this easily yet
                        matched_product=None,
                        bytes_saved=bytes_saved,
                    )

                    # Refresh TUI
                    live.update(self._build_layout())

                    if items % 5 == 0:
                        self._current_action = f"Crawling... {items} processed"

                # Final state
                if not self.running:
                    self.engine.session_manager.save()
                self._current_action = "Done."

                # Build final index
                index = self.engine.organizer.build_index()
                self._log_lines.append("")

                total_guides = 0
                total_images = 0
                for brand, products in index.items():
                    if brand.startswith('_'):
                        continue
                    for prod, cats in products.items():
                        g = cats.get('guides', {}).get('count', 0)
                        i = cats.get('images', {}).get('count', 0)
                        total_guides += g
                        total_images += i
                self._log_lines.append(f"Total: {total_guides} guides, {total_images} images, "
                                       f"{format_size(self._total_bytes)}")

                # Show skip warnings
                if self.engine.size_tracker and self.engine.size_tracker.skipped_files:
                    n = len(self.engine.size_tracker.skipped_files)
                    need = format_size(self.engine.size_tracker.skipped_total_bytes)
                    self._log_lines.append(f"[WARN] {n} items skipped — need ~{need} more")

                live.update(self._build_layout())
                time.sleep(2)  # Let user see final state

        except KeyboardInterrupt:
            self._log_lines.append("[STOP] Interrupted — state saved")
            self.engine.session_manager.save()
        except Exception as e:
            self._log_lines.append(f"[ERROR] {e}")
        finally:
            self.running = False
            # Restore original log handlers
            for h in old_handlers:
                if h not in root.handlers:
                    root.addHandler(h)


# ── Fallback simple CLI (no rich) ────────────────────────────────────

class SimpleCLI:
    """Fallback CLI when rich is not installed."""

    def __init__(self):
        self.engine = ScraperEngine(Path("config"))
        self.engine.setup()
        self.running = False

    def run(self, brands=None, size_mb=None):
        size_bytes = size_mb * 1024 * 1024 if size_mb else None
        brand_str = ', '.join(brands) if brands else 'all'
        size_str = format_size(size_bytes) if size_bytes else "default"
        print(f"Starting: brands={brand_str}, limit={size_str}")
        print("-" * 40)
        try:
            self.engine.run(size_override=size_bytes, brands=brands)
        except KeyboardInterrupt:
            print("\n[STOP] State saved")
        print("-" * 40)
        print("Done.")


# ── Entry point ──────────────────────────────────────────────────────

def run_interactive(brands: Optional[list[str]] = None, size_mb: Optional[int] = None):
    """Launch the best available UI."""
    if HAS_RICH and not sys.flags.interactive:
        tui = RichTUI()
        tui.run(brands=brands, size_mb=size_mb)
    else:
        cli = SimpleCLI()
        cli.run(brands=brands, size_mb=size_mb)
