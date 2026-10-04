import os
import threading
from pathlib import Path

import pytest
from conftest import fixed_cluster

from dirstat.model import Metric, format_size, sorted_children
from dirstat.scanner import ScanCancelled, scan


def test_totals(tree: Path) -> None:
    result = scan(tree, disk_size_fn=fixed_cluster)
    root = result.root
    assert root.size == 3000 + 100 + 100 + 500
    assert root.files == 13
    assert root.dirs == 3
    # Every non-empty file takes one 4 KB cluster.
    assert root.disk_size == 13 * 4096
    assert result.errors == 0


def test_sorting_by_metric(tree: Path) -> None:
    root = scan(tree, disk_size_fn=fixed_cluster).root
    assert [c.name for c in sorted_children(root, Metric.APPARENT)][:2] == ["big", "top.dat"]
    assert sorted_children(root, Metric.COUNT)[0].name == "many"
    assert sorted_children(root, Metric.DISK)[0].name == "many"


def test_path_property(tree: Path) -> None:
    root = scan(tree).root
    big = next(c for c in root.children if c.name == "big")
    a = next(c for c in big.children if c.name == "a.bin")
    assert Path(a.path) == tree.resolve() / "big" / "a.bin"


def test_symlink_not_followed(tree: Path) -> None:
    link = tree / "loop"
    try:
        os.symlink(tree, link, target_is_directory=True)
    except OSError:
        pytest.skip("symlinks need privileges on this system")
    root = scan(tree, disk_size_fn=fixed_cluster).root
    loop = next(c for c in root.children if c.name == "loop")
    assert not loop.is_dir and loop.size == 0
    assert root.files == 13


def test_unreadable_dir_is_recorded(tree: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    real = os.scandir
    blocked = str((tree / "big").resolve())

    def fake(path):  # noqa: ANN001
        if str(path) == blocked:
            raise PermissionError(13, "Access is denied")
        return real(path)

    monkeypatch.setattr("dirstat.scanner.os.scandir", fake)
    result = scan(tree, disk_size_fn=fixed_cluster)
    big = next(c for c in result.root.children if c.name == "big")
    assert big.error == "Access is denied"
    assert result.errors == 1
    assert result.root.files == 11


def test_cancel(tree: Path) -> None:
    ev = threading.Event()
    ev.set()
    with pytest.raises(ScanCancelled):
        scan(tree, cancel=ev)


def test_not_a_dir(tree: Path) -> None:
    with pytest.raises(NotADirectoryError):
        scan(tree / "top.dat")


def test_real_disk_size_is_sane(tree: Path) -> None:
    root = scan(tree).root
    # Platform estimate: never negative and not absurdly larger than apparent size.
    assert 0 <= root.disk_size <= root.size + 13 * 2 * 1024 * 1024


@pytest.mark.parametrize(
    ("num", "text"),
    [(0, "0 B"), (1023, "1023 B"), (1024, "1.0 KB"), (1536, "1.5 KB"), (5 * 1024**3, "5.0 GB")],
)
def test_format_size(num: int, text: str) -> None:
    assert format_size(num) == text
