# dirstat

Terminal disk usage browser, in the spirit of WinDirStat and ncdu. It scans a drive or folder and
lists folders and files sorted largest first. Toggle the measure between **size on disk**,
**apparent size**, and **file count**. Export an SVG screenshot or a self-contained HTML report
with a treemap.

## Install

Needs [uv](https://docs.astral.sh/uv/) and Python 3.12+ (uv can fetch Python for you).
Works on Windows, Linux, and macOS.

```sh
uv tool install git+https://github.com/jchimp/dirstat   # from GitHub
uv tool upgrade dirstat                                 # get the latest version
```

From a local clone:

```sh
git clone https://github.com/jchimp/dirstat
cd dirstat
uv tool install .            # or -e . for an editable install
```

Run once without installing:

```sh
uvx --from git+https://github.com/jchimp/dirstat dirstat C:\
```

## Use

```sh
dirstat                      # scan the current folder
dirstat C:\                  # scan a drive
dirstat ~/projects --out-dir ~/reports      # where s / e exports go
dirstat D:\data --export data.html          # no TUI: scan and write the HTML report
dirstat D:\data --export data.html --max-nodes 200000
```

| Key | Action |
|---|---|
| Enter / → | open folder |
| Backspace / ← | go up |
| m | cycle size on disk → apparent size → file count |
| s | save SVG screenshot of the current view |
| e | export HTML report (whole scan, not just the current folder) |
| r | rescan, stays in the same folder |
| ? | help |
| q | quit |

Esc cancels a running scan.

## HTML report

One `.html` file, no CDN or network access, so it opens the same way offline and years later.
It has a metric toggle, a breadcrumb, a zoomable treemap (files colored by extension), and a
collapsible tree table.

To keep the file small, the report keeps the `--max-nodes` largest items (default 50,000, by size
on disk). The rest of each folder folds into one `<N smaller items>` entry. Totals stay exact.
A 312k-file tree gives a ~3 MB report.

## What "size on disk" means

- **Linux/macOS:** allocated blocks (`st_blocks * 512`).
- **Windows:** apparent size rounded up to the volume cluster size. Compressed and sparse files
  ask the OS for the real allocation (`GetCompressedFileSizeW`). Cloud placeholders
  (OneDrive/Dropbox "online only") count as 0. Very small files stored inside the NTFS MFT still
  count as one cluster, so the total can be slightly high.

Units are 1024-based with Explorer-style names (1 KB = 1024 bytes).

## Behavior and limits

- Symlinks and junctions are listed with size 0 and never followed (no loops, no double counting).
- Folders that cannot be read show in red with `!`; their totals are partial. Run elevated for
  full system-drive totals.
- Memory: one small object per file. Expect roughly 200–300 MB for 1M files.
- Folders with more than 2,000 entries show the top 2,000 in the TUI.

## Develop

```sh
uv sync
uv run pytest
uv run ruff check . && uv run ruff format --check .
uv run dirstat .
```

## License

MIT. See [LICENSE](LICENSE).
