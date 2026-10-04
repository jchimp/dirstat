"""Tree model for scan results."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


class Metric(Enum):
    """What the views sort and measure by."""

    DISK = "Size on disk"
    APPARENT = "Apparent size"
    COUNT = "File count"

    def next(self) -> Metric:
        """Return the metric after this one, wrapping around."""
        members = list(Metric)
        return members[(members.index(self) + 1) % len(members)]


# slots=True matters: a full drive scan holds one Node per file.
@dataclass(slots=True, eq=False)
class Node:
    """A file or folder. Folder totals include everything below it.

    A file node has ``files == 1`` so the COUNT metric works the same for files and folders.
    """

    name: str
    is_dir: bool
    size: int = 0
    disk_size: int = 0
    files: int = 0
    dirs: int = 0
    children: list[Node] = field(default_factory=list)
    error: str | None = None
    parent: Node | None = None

    @property
    def path(self) -> str:
        """Full path, built from the parent chain. The root's name is its full path."""
        parts: list[str] = []
        node: Node | None = self
        while node is not None:
            parts.append(node.name)
            node = node.parent
        parts.reverse()
        return str(Path(*parts))


def value(node: Node, metric: Metric) -> int:
    """Return the number a node is measured by under ``metric``."""
    if metric is Metric.DISK:
        return node.disk_size
    if metric is Metric.APPARENT:
        return node.size
    return node.files


def sorted_children(node: Node, metric: Metric) -> list[Node]:
    """Children sorted largest first; ties fall back to name."""
    return sorted(node.children, key=lambda c: (-value(c, metric), c.name.lower()))


def format_size(num: int) -> str:
    """Human readable size with 1024 steps and Explorer-style unit names (KB = 1024 bytes)."""
    if num < 1024:
        return f"{num} B"
    size = float(num)
    for unit in ("KB", "MB", "GB", "TB", "PB"):
        size /= 1024
        if size < 1024 or unit == "PB":
            return f"{size:.1f} {unit}"
    raise AssertionError("unreachable")


def format_count(num: int) -> str:
    """Integer with thousands separators."""
    return f"{num:,}"
