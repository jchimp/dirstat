"""Command line entry point."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from dirstat.export_html import DEFAULT_MAX_NODES


def build_parser() -> argparse.ArgumentParser:
    """Argument parser for ``dirstat``."""
    parser = argparse.ArgumentParser(
        prog="dirstat",
        description="Browse disk usage by size on disk, apparent size, or file count.",
    )
    parser.add_argument("path", nargs="?", default=".", type=Path, help="folder or drive to scan")
    parser.add_argument(
        "--export",
        metavar="FILE.html",
        type=Path,
        help="scan without the TUI and write an HTML report",
    )
    parser.add_argument(
        "--max-nodes",
        type=int,
        default=DEFAULT_MAX_NODES,
        help=f"largest items kept in the HTML report; the rest fold together "
        f"(default {DEFAULT_MAX_NODES:,})",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        help="where the TUI writes SVG/HTML exports (default: current folder)",
    )
    return parser


def _export(path: Path, out: Path, max_nodes: int) -> int:
    from dirstat.export_html import export_html
    from dirstat.model import format_count, format_size
    from dirstat.scanner import Progress, scan

    def progress(p: Progress) -> None:
        print(
            f"\r{format_count(p.files)} files, {format_size(p.bytes)} ...",
            end="",
            file=sys.stderr,
            flush=True,
        )

    result = scan(path, on_progress=progress, progress_interval=0.5)
    print(file=sys.stderr)
    written = export_html(
        result.root, out, errors=result.errors, elapsed=result.elapsed, max_nodes=max_nodes
    )
    root = result.root
    print(
        f"{root.name}: {format_size(root.disk_size)} on disk, {format_size(root.size)} apparent, "
        f"{format_count(root.files)} files, {format_count(root.dirs)} folders, "
        f"{format_count(result.errors)} unreadable, {result.elapsed:.1f}s"
    )
    print(f"Wrote {written}")
    return 0


def main(argv: list[str] | None = None) -> int:
    """Run the TUI, or a headless export when ``--export`` is given."""
    args = build_parser().parse_args(argv)
    path: Path = args.path
    if not path.is_dir():
        print(f"dirstat: not a folder: {path}", file=sys.stderr)
        return 2
    if args.max_nodes < 1:
        print("dirstat: --max-nodes must be at least 1", file=sys.stderr)
        return 2

    if args.export is not None:
        try:
            return _export(path, args.export, args.max_nodes)
        except KeyboardInterrupt:
            print("\nCancelled.", file=sys.stderr)
            return 130

    from dirstat.app import DirStatApp

    out_dir = args.out_dir.resolve() if args.out_dir else None
    if out_dir is not None and not out_dir.is_dir():
        print(f"dirstat: --out-dir is not a folder: {out_dir}", file=sys.stderr)
        return 2
    DirStatApp(path.resolve(), out_dir=out_dir).run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
