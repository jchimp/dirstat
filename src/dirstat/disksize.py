"""Size-on-disk estimation per platform."""

from __future__ import annotations

import os
import sys
from collections.abc import Callable
from pathlib import Path

DiskSizeFn = Callable[[os.stat_result, str], int]

DEFAULT_CLUSTER = 4096

# Windows file attribute bits (winnt.h).
_ATTR_SPARSE = 0x200
_ATTR_COMPRESSED = 0x800
_ATTR_OFFLINE = 0x1000
_ATTR_RECALL_ON_OPEN = 0x40000
_ATTR_RECALL_ON_DATA_ACCESS = 0x400000
# Cloud placeholders (OneDrive/Dropbox "online only") report a size but use no local clusters.
_ATTR_NOT_LOCAL = _ATTR_OFFLINE | _ATTR_RECALL_ON_OPEN | _ATTR_RECALL_ON_DATA_ACCESS
# For these the cluster estimate is wrong, so ask the OS. They are rare, so the syscall is cheap.
_ATTR_ASK_OS = _ATTR_SPARSE | _ATTR_COMPRESSED


def make_disk_size_fn(root: Path) -> DiskSizeFn:
    """Build a function that returns size on disk for a stat result under ``root``.

    Args:
        root: Scan root. On Windows its volume decides the cluster size.

    Returns:
        A function ``(stat_result, path) -> bytes on disk``.
    """
    if sys.platform == "win32":
        return _windows_fn(_windows_cluster_size(root))
    return _posix_size


def _posix_size(st: os.stat_result, path: str) -> int:
    return st.st_blocks * 512


def _round_up(size: int, cluster: int) -> int:
    return -(-size // cluster) * cluster


def _windows_fn(cluster: int) -> DiskSizeFn:
    def disk_size(st: os.stat_result, path: str) -> int:
        attrs = st.st_file_attributes
        if attrs & _ATTR_NOT_LOCAL:
            return 0
        if attrs & _ATTR_ASK_OS:
            exact = _windows_compressed_size(path)
            if exact is not None:
                return _round_up(exact, cluster)
        return _round_up(st.st_size, cluster)

    return disk_size


def _windows_cluster_size(root: Path) -> int:
    """Bytes per cluster of the volume holding ``root``; DEFAULT_CLUSTER if the OS call fails."""
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    buf = ctypes.create_unicode_buffer(1024)
    if not kernel32.GetVolumePathNameW(str(root.resolve()), buf, len(buf)):
        return DEFAULT_CLUSTER
    sectors = wintypes.DWORD()
    bytes_per_sector = wintypes.DWORD()
    free = wintypes.DWORD()
    total = wintypes.DWORD()
    ok = kernel32.GetDiskFreeSpaceW(
        buf.value,
        ctypes.byref(sectors),
        ctypes.byref(bytes_per_sector),
        ctypes.byref(free),
        ctypes.byref(total),
    )
    if not ok or sectors.value == 0 or bytes_per_sector.value == 0:
        return DEFAULT_CLUSTER
    return sectors.value * bytes_per_sector.value


def _windows_compressed_size(path: str) -> int | None:
    """Actual allocated bytes for a compressed or sparse file, or None on error."""
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.GetCompressedFileSizeW.restype = wintypes.DWORD
    high = wintypes.DWORD()
    low = kernel32.GetCompressedFileSizeW(path, ctypes.byref(high))
    # 0xFFFFFFFF is also a valid low word, so only the error code tells failure apart.
    if low == 0xFFFFFFFF and ctypes.get_last_error() != 0:
        return None
    return (high.value << 32) + low
