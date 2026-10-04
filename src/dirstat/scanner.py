"""Walk a folder tree and build a Node tree with rolled-up totals."""

from __future__ import annotations

import os
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from dirstat.disksize import DiskSizeFn, make_disk_size_fn
from dirstat.model import Node


class ScanCancelled(Exception):
    """Raised when the cancel event is set during a scan."""


@dataclass(slots=True)
class Progress:
    """Snapshot sent to the progress callback."""

    files: int
    dirs: int
    bytes: int
    errors: int
    current: str


@dataclass(slots=True)
class ScanResult:
    """Finished scan."""

    root: Node
    errors: int
    elapsed: float


def scan(
    root: Path,
    on_progress: Callable[[Progress], None] | None = None,
    cancel: threading.Event | None = None,
    progress_interval: float = 0.1,
    disk_size_fn: DiskSizeFn | None = None,
) -> ScanResult:
    """Scan ``root`` and return the tree.

    Symlinks and junctions are listed as zero-size entries but never followed. That avoids
    loops and counting the same data twice.

    Args:
        root: Folder or drive to scan.
        on_progress: Called at most every ``progress_interval`` seconds.
        cancel: When set, the scan stops and raises ScanCancelled.
        progress_interval: Seconds between progress callbacks.
        disk_size_fn: Override for size on disk; defaults to the platform estimate.

    Returns:
        ScanResult with the root node, the number of unreadable entries, and elapsed seconds.

    Raises:
        NotADirectoryError: ``root`` is not a folder.
        ScanCancelled: ``cancel`` was set.
    """
    root = root.resolve()
    if not root.is_dir():
        raise NotADirectoryError(str(root))
    disk_size = disk_size_fn or make_disk_size_fn(root)

    start = time.monotonic()
    last_report = 0.0
    files = dirs = total_bytes = errors = 0

    root_node = Node(name=str(root), is_dir=True)
    stack: list[tuple[str, Node]] = [(str(root), root_node)]
    # Discovery order puts every parent before its children; reversed, it is a safe rollup order.
    order: list[Node] = []

    while stack:
        if cancel is not None and cancel.is_set():
            raise ScanCancelled
        path, node = stack.pop()
        order.append(node)
        try:
            with os.scandir(path) as entries:
                for entry in entries:
                    try:
                        if entry.is_symlink() or entry.is_junction():
                            node.children.append(Node(name=entry.name, is_dir=False, parent=node))
                            continue
                        if entry.is_dir(follow_symlinks=False):
                            child = Node(name=entry.name, is_dir=True, parent=node)
                            node.children.append(child)
                            stack.append((entry.path, child))
                            dirs += 1
                            continue
                        st = entry.stat(follow_symlinks=False)
                        node.children.append(
                            Node(
                                name=entry.name,
                                is_dir=False,
                                size=st.st_size,
                                disk_size=disk_size(st, entry.path),
                                files=1,
                                parent=node,
                            )
                        )
                        files += 1
                        total_bytes += st.st_size
                    except OSError:
                        errors += 1
        except OSError as exc:
            node.error = exc.strerror or str(exc)
            errors += 1

        if on_progress is not None:
            now = time.monotonic()
            if now - last_report >= progress_interval:
                last_report = now
                on_progress(Progress(files, dirs, total_bytes, errors, path))

    for node in reversed(order):
        for child in node.children:
            node.size += child.size
            node.disk_size += child.disk_size
            node.files += child.files
            if child.is_dir:
                node.dirs += 1 + child.dirs

    if on_progress is not None:
        on_progress(Progress(files, dirs, total_bytes, errors, str(root)))
    return ScanResult(root=root_node, errors=errors, elapsed=time.monotonic() - start)
