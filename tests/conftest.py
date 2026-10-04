from pathlib import Path

import pytest


@pytest.fixture
def tree(tmp_path: Path) -> Path:
    """Small known tree:

    root/
      big/      a.bin 3000, b.txt 100
      many/     f0..f9.txt 10 bytes each
      empty/
      top.dat   500
    """
    root = tmp_path / "root"
    (root / "big").mkdir(parents=True)
    (root / "many").mkdir()
    (root / "empty").mkdir()
    (root / "big" / "a.bin").write_bytes(b"x" * 3000)
    (root / "big" / "b.txt").write_bytes(b"x" * 100)
    for i in range(10):
        (root / "many" / f"f{i}.txt").write_bytes(b"x" * 10)
    (root / "top.dat").write_bytes(b"x" * 500)
    return root


def fixed_cluster(st, path: str) -> int:
    """Deterministic size on disk: 4 KB clusters."""
    return -(-st.st_size // 4096) * 4096
