"""Textual TUI: ncdu-style drill-down, one folder level at a time."""

from __future__ import annotations

import threading
from datetime import datetime
from pathlib import Path

from rich.text import Text
from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import DataTable, Footer, LoadingIndicator, Static

from dirstat.export_html import DEFAULT_MAX_NODES, export_html
from dirstat.model import Metric, Node, format_count, format_size, sorted_children, value
from dirstat.scanner import Progress, ScanCancelled, ScanResult, scan

# DataTable gets slow past a few thousand rows; giant folders show the top part only.
ROW_LIMIT = 2000
BAR_WIDTH = 20
_PARTIAL = " ▏▎▍▌▋▊▉"

HELP = """\
Enter / →   open folder
Backspace / ←   go up
m   cycle: size on disk → apparent size → file count
s   save SVG screenshot
e   export HTML report
r   rescan
q   quit"""


def bar(fraction: float, width: int = BAR_WIDTH) -> str:
    """Block-character bar with 1/8 cell resolution."""
    eighths = round(max(0.0, min(1.0, fraction)) * width * 8)
    full, part = divmod(eighths, 8)
    text = "█" * full + (_PARTIAL[part] if part else "")
    return text.ljust(width)


class ScanScreen(ModalScreen[None]):
    """Modal progress view while the scan worker runs."""

    BINDINGS = [Binding("escape", "cancel", "Cancel scan")]

    def __init__(self, root: Path) -> None:
        super().__init__()
        self._root = root

    def compose(self) -> ComposeResult:
        with Vertical(id="scan-box"):
            yield Static(f"Scanning [b]{self._root}[/b]", id="scan-title", markup=True)
            yield LoadingIndicator()
            yield Static("", id="scan-stats")
            yield Static("", id="scan-path")
            yield Static("[dim]Esc to cancel[/dim]", markup=True)

    def show(self, p: Progress) -> None:
        """Update the progress text."""
        self.query_one("#scan-stats", Static).update(
            f"{format_count(p.files)} files · {format_count(p.dirs)} folders · "
            f"{format_size(p.bytes)} · {format_count(p.errors)} unreadable"
        )
        self.query_one("#scan-path", Static).update(Text(p.current, overflow="ellipsis"))

    def action_cancel(self) -> None:
        self.app.cancel_scan()  # type: ignore[attr-defined]


class DirTable(DataTable[object]):
    """DataTable with folder navigation keys. Arrow keys would otherwise scroll sideways."""

    BINDINGS = [
        Binding("right", "app.open_selected", "Open", show=False),
        Binding("left", "app.go_up", "Up", show=False),
        Binding("backspace", "app.go_up", "Up"),
    ]


class DirStatApp(App[None]):
    """Disk usage browser."""

    TITLE = "dirstat"
    CSS_PATH = "app.tcss"
    BINDINGS = [
        Binding("m", "cycle_metric", "Metric"),
        Binding("s", "screenshot", "SVG"),
        Binding("e", "export", "HTML"),
        Binding("r", "rescan", "Rescan"),
        Binding("question_mark", "help", "Help"),
        Binding("q", "quit", "Quit"),
    ]

    def __init__(self, root: Path, out_dir: Path | None = None) -> None:
        super().__init__()
        self.root_path = root
        self.out_dir = out_dir or Path.cwd()
        self.metric = Metric.DISK
        self.result: ScanResult | None = None
        self.current: Node | None = None
        self._rows: list[Node] = []
        self._cancel = threading.Event()
        self._restore: list[str] = []

    def compose(self) -> ComposeResult:
        yield Static("", id="crumbs")
        yield Static("", id="totals")
        yield DirTable(id="table", cursor_type="row", zebra_stripes=True)
        yield Footer()

    def on_mount(self) -> None:
        self.start_scan()

    def on_unmount(self) -> None:
        self._cancel.set()

    # ---- scanning ---------------------------------------------------------

    def start_scan(self) -> None:
        """Show the progress modal and scan in a background thread."""
        self._cancel = threading.Event()
        self.push_screen(ScanScreen(self.root_path))
        self._scan_worker(self._cancel)

    def cancel_scan(self) -> None:
        """Ask the running scan to stop."""
        self._cancel.set()

    @work(thread=True, exclusive=True, group="scan")
    def _scan_worker(self, cancel: threading.Event) -> None:
        def progress(p: Progress) -> None:
            try:
                self.call_from_thread(self._on_progress, p)
            except RuntimeError:
                cancel.set()  # App already closed.

        try:
            result = scan(self.root_path, on_progress=progress, cancel=cancel)
        except ScanCancelled:
            self.call_from_thread(self._scan_cancelled)
            return
        except OSError as exc:
            self.call_from_thread(self.exit, message=f"Cannot scan {self.root_path}: {exc}")
            return
        self.call_from_thread(self._scan_done, result)

    def _on_progress(self, p: Progress) -> None:
        if isinstance(self.screen, ScanScreen):
            self.screen.show(p)

    def _scan_cancelled(self) -> None:
        if isinstance(self.screen, ScanScreen):
            self.pop_screen()
        if self.result is None:
            self.exit(message="Scan cancelled.")
        else:
            self.notify("Rescan cancelled; showing previous results.")

    def _scan_done(self, result: ScanResult) -> None:
        if isinstance(self.screen, ScanScreen):
            self.pop_screen()
        self.result = result
        self.current = self._find(result.root, self._restore)
        self.refresh_table()
        self.query_one(DirTable).focus()

    @staticmethod
    def _find(root: Node, names: list[str]) -> Node:
        """Walk ``names`` down from ``root``; stop at the deepest folder that still exists."""
        node = root
        for name in names:
            nxt = next((c for c in node.children if c.is_dir and c.name == name), None)
            if nxt is None:
                break
            node = nxt
        return node

    # ---- rendering --------------------------------------------------------

    def refresh_table(self, select: Node | None = None) -> None:
        """Rebuild the table for ``self.current``; put the cursor on ``select`` if listed."""
        node = self.current
        if node is None:
            return
        table = self.query_one(DirTable)
        table.clear(columns=True)
        size_metric = Metric.APPARENT if self.metric is Metric.APPARENT else Metric.DISK
        table.add_column("Name", key="name")
        table.add_column(Text("%", justify="right"), key="pct", width=6)
        table.add_column("", key="bar", width=BAR_WIDTH)
        table.add_column(Text(size_metric.value, justify="right"), key="size")
        table.add_column(Text("Files", justify="right"), key="files")
        table.add_column(Text("Folders", justify="right"), key="dirs")

        offset = 0
        if node.parent is not None:
            table.add_row(Text("..", style="bold"), "", "", "", "", "", key="..")
            offset = 1

        kids = sorted_children(node, self.metric)
        self._rows = kids[:ROW_LIMIT]
        total = value(node, self.metric) or 1
        for i, child in enumerate(self._rows):
            frac = value(child, self.metric) / total
            if child.is_dir:
                style = "bold red" if child.error else "bold"
                name = Text(child.name + "/" + (" !" if child.error else ""), style=style)
                dirs = Text(format_count(child.dirs), justify="right")
            else:
                name = Text(child.name)
                dirs = Text("")
            table.add_row(
                name,
                Text(f"{frac * 100:.1f}", justify="right"),
                Text(bar(frac), style="cyan"),
                Text(format_size(value(child, size_metric)), justify="right"),
                Text(format_count(child.files), justify="right"),
                dirs,
                key=str(i),
            )
        if len(kids) > ROW_LIMIT:
            more = len(kids) - ROW_LIMIT
            table.add_row(
                Text(f"<{format_count(more)} more items>", style="dim italic"),
                "",
                "",
                "",
                "",
                "",
                key="more",
            )

        if select is not None and select in self._rows:
            table.move_cursor(row=self._rows.index(select) + offset)
        elif self._rows:
            table.move_cursor(row=offset)
        self._update_header()

    def _update_header(self) -> None:
        node = self.current
        if node is None or self.result is None:
            return
        self.query_one("#crumbs", Static).update(Text(node.path, style="bold"))
        totals = (
            f"[b]{self.metric.value}[/b]  │  "
            f"Disk {format_size(node.disk_size)} · Apparent {format_size(node.size)} · "
            f"{format_count(node.files)} files · {format_count(node.dirs)} folders  │  "
            f"scan {self.result.elapsed:.1f}s · {format_count(self.result.errors)} unreadable"
        )
        if node.error:
            totals += f"  │  [red]this folder: {node.error}[/red]"
        self.query_one("#totals", Static).update(totals)

    # ---- navigation -------------------------------------------------------

    def _selected(self) -> str | None:
        table = self.query_one(DirTable)
        if table.row_count == 0:
            return None
        return table.ordered_rows[table.cursor_row].key.value

    def _activate(self, key: str | None) -> None:
        if key is None or key == "more":
            return
        if key == "..":
            self.action_go_up()
            return
        node = self._rows[int(key)]
        if node.is_dir:
            self.current = node
            self.refresh_table()

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        self._activate(event.row_key.value)

    def action_open_selected(self) -> None:
        self._activate(self._selected())

    def action_go_up(self) -> None:
        if self.current is None or self.current.parent is None:
            return
        came_from = self.current
        self.current = self.current.parent
        self.refresh_table(select=came_from)

    def action_cycle_metric(self) -> None:
        key = self._selected()
        keep = self._rows[int(key)] if key and key.isdigit() else None
        self.metric = self.metric.next()
        self.refresh_table(select=keep)

    # ---- exports & misc ---------------------------------------------------

    def _stamp(self) -> str:
        return datetime.now().strftime("%Y%m%d-%H%M%S")

    def action_screenshot(self) -> None:
        path = self.save_screenshot(filename=f"dirstat-{self._stamp()}.svg", path=str(self.out_dir))
        self.notify(f"Saved {path}")

    def action_export(self) -> None:
        if self.result is None:
            return
        out = self.out_dir / f"dirstat-{self._stamp()}.html"
        self.notify("Writing HTML report…")
        self._export_worker(self.result, out)

    @work(thread=True, group="export")
    def _export_worker(self, result: ScanResult, out: Path) -> None:
        try:
            path = export_html(
                result.root,
                out,
                errors=result.errors,
                elapsed=result.elapsed,
                max_nodes=DEFAULT_MAX_NODES,
            )
        except OSError as exc:
            self.call_from_thread(self.notify, f"Export failed: {exc}", severity="error")
            return
        self.call_from_thread(self.notify, f"Saved {path}")

    def action_rescan(self) -> None:
        names: list[str] = []
        node = self.current
        while node is not None and node.parent is not None:
            names.append(node.name)
            node = node.parent
        self._restore = names[::-1]
        self.start_scan()

    def action_help(self) -> None:
        self.notify(HELP, title="Keys", timeout=12)
