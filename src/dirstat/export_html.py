"""Self-contained HTML report: tree table + treemap, no network needed to view."""

from __future__ import annotations

import heapq
import html
import json
from datetime import datetime
from importlib.resources import files
from pathlib import Path

from dirstat.model import Node

DEFAULT_MAX_NODES = 50_000

# Compact node encoding shared with report_template.html:
# [name, disk, apparent, files, dirs, kind, children?]
KIND_FILE = 0
KIND_DIR = 1
KIND_DIR_ERROR = 2
KIND_FOLDED = 3


def select_nodes(root: Node, max_nodes: int) -> set[int]:
    """Pick the ``max_nodes`` largest nodes (by size on disk) reachable from the root.

    A node is only picked after its parent, so the result is always a connected tree.
    Without a budget a full-drive report would be hundreds of MB.

    Returns:
        ``id()`` of every picked node.
    """
    picked: set[int] = set()
    # The counter breaks ties so heapq never compares Node objects.
    heap: list[tuple[int, int, Node]] = [(-root.disk_size, 0, root)]
    counter = 1
    while heap and len(picked) < max_nodes:
        _, _, node = heapq.heappop(heap)
        picked.add(id(node))
        for child in node.children:
            heapq.heappush(heap, (-child.disk_size, counter, child))
            counter += 1
    return picked


def encode(node: Node, picked: set[int]) -> list[object]:
    """Encode a picked node and its picked descendants. Unpicked children fold into one entry."""
    if not node.is_dir:
        return [node.name, node.disk_size, node.size, node.files, 0, KIND_FILE]
    kind = KIND_DIR_ERROR if node.error else KIND_DIR
    children: list[list[object]] = []
    folded = [0, 0, 0, 0, 0]  # count, disk, apparent, files, dirs
    for child in node.children:
        if id(child) in picked:
            children.append(encode(child, picked))
        else:
            folded[0] += 1
            folded[1] += child.disk_size
            folded[2] += child.size
            folded[3] += child.files
            folded[4] += (1 + child.dirs) if child.is_dir else 0
    if folded[0]:
        label = f"<{folded[0]:,} smaller items>"
        children.append([label, folded[1], folded[2], folded[3], folded[4], KIND_FOLDED])
    return [node.name, node.disk_size, node.size, node.files, node.dirs, kind, children]


def render_html(
    root: Node,
    *,
    errors: int = 0,
    elapsed: float = 0.0,
    max_nodes: int = DEFAULT_MAX_NODES,
) -> str:
    """Build the full report as an HTML string.

    Args:
        root: Scanned tree root.
        errors: Unreadable entries during the scan.
        elapsed: Scan time in seconds.
        max_nodes: Node budget; smaller items fold into ``<N smaller items>``.

    Returns:
        Complete HTML document.
    """
    data = {
        "root": encode(root, select_nodes(root, max_nodes)),
        "generated": datetime.now().isoformat(timespec="seconds"),
        "errors": errors,
        "elapsed": round(elapsed, 2),
        "maxNodes": max_nodes,
    }
    # "</" inside a <script> block would end it early; "<\/" is the same string to JSON.
    payload = json.dumps(data, separators=(",", ":"), ensure_ascii=False).replace("</", "<\\/")
    template = files("dirstat").joinpath("report_template.html").read_text(encoding="utf-8")
    return template.replace("__DIRSTAT_TITLE__", html.escape(root.name)).replace(
        "__DIRSTAT_DATA__", payload
    )


def export_html(
    root: Node,
    out: Path,
    *,
    errors: int = 0,
    elapsed: float = 0.0,
    max_nodes: int = DEFAULT_MAX_NODES,
) -> Path:
    """Write the report to ``out`` and return the resolved path."""
    out = out.resolve()
    out.write_text(
        render_html(root, errors=errors, elapsed=elapsed, max_nodes=max_nodes), encoding="utf-8"
    )
    return out
