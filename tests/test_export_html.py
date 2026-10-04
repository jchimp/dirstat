import json
import re
from pathlib import Path

from conftest import fixed_cluster

from dirstat.export_html import KIND_FOLDED, export_html, render_html, select_nodes
from dirstat.scanner import scan


def _payload(html: str) -> dict:
    m = re.search(r'<script id="data" type="application/json">(.*?)</script>', html, re.S)
    assert m
    return json.loads(m.group(1))


def test_full_report(tree: Path, tmp_path: Path) -> None:
    result = scan(tree, disk_size_fn=fixed_cluster)
    out = export_html(result.root, tmp_path / "r.html", errors=0, elapsed=1.0)
    html = out.read_text(encoding="utf-8")
    assert "__DIRSTAT_" not in html
    data = _payload(html)
    root = data["root"]
    assert root[3] == 13  # files
    assert {c[0] for c in root[6]} == {"big", "many", "empty", "top.dat"}


def test_budget_folds_small_items(tree: Path) -> None:
    root = scan(tree, disk_size_fn=fixed_cluster).root
    # root + 'many' + 'big' + 2 more: the rest must fold, totals must still add up.
    data = _payload(render_html(root, max_nodes=5))
    enc = data["root"]

    def total_files(node: list) -> int:
        if len(node) < 7:
            return node[3]
        return sum(total_files(c) for c in node[6])

    assert total_files(enc) == 13
    assert any(c[5] == KIND_FOLDED for c in enc[6]) or any(
        len(c) > 6 and any(g[5] == KIND_FOLDED for g in c[6]) for c in enc[6]
    )


def test_select_nodes_is_connected(tree: Path) -> None:
    root = scan(tree, disk_size_fn=fixed_cluster).root
    picked = select_nodes(root, 4)
    assert len(picked) == 4
    stack = [root]
    while stack:
        n = stack.pop()
        for c in n.children:
            if id(c) in picked:
                assert id(n) in picked
            stack.append(c)


def test_script_breakout_is_escaped(tmp_path: Path) -> None:
    root = tmp_path / "x"
    root.mkdir()
    (root / "plain.txt").write_bytes(b"1")
    res = scan(root, disk_size_fn=fixed_cluster)
    res.root.children[0].name = "</script><img src=x onerror=alert(1)>"
    html = render_html(res.root)
    assert html.count("</script>") == 2  # only the two real closing tags
    assert _payload(html)["root"][6][0][0].startswith("</script>")
