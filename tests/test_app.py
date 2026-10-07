from pathlib import Path

import dirstat.app as app_module
from dirstat.app import DirStatApp, DirTable
from dirstat.model import Metric


async def _wait(app: DirStatApp, pilot) -> None:  # noqa: ANN001
    await app.workers.wait_for_complete()
    await pilot.pause()


async def test_navigate_and_toggle(tree: Path, tmp_path: Path) -> None:
    app = DirStatApp(tree.resolve(), out_dir=tmp_path)
    async with app.run_test(size=(120, 30)) as pilot:
        await _wait(app, pilot)
        assert app.current is app.result.root
        table = app.query_one(DirTable)
        assert table.row_count == 4

        # Count mode: 'many' (10 files) must be first.
        while app.metric is not Metric.COUNT:
            await pilot.press("m")
        assert app._rows[0].name == "many"

        # Open the selected folder, then go back up.
        table.move_cursor(row=0)
        await pilot.press("enter")
        assert app.current.name == "many"
        assert table.row_count == 11  # '..' + 10 files
        await pilot.press("backspace")
        assert app.current is app.result.root
        assert app._rows[table.cursor_row].name == "many"


async def test_exports(tree: Path, tmp_path: Path, monkeypatch) -> None:  # noqa: ANN001
    opened: list[Path] = []
    monkeypatch.setattr(app_module, "open_file", opened.append)
    out = tmp_path / "out"
    out.mkdir()
    app = DirStatApp(tree.resolve(), out_dir=out)
    async with app.run_test(size=(120, 30)) as pilot:
        await _wait(app, pilot)
        await pilot.press("s")
        await pilot.press("e")
        await _wait(app, pilot)
    assert len(list(out.glob("dirstat-*.svg"))) == 1
    assert len(list(out.glob("dirstat-*.html"))) == 1
    assert opened == list(out.glob("dirstat-*.html"))


async def test_column_widths_fixed_before_idle(tree: Path, tmp_path: Path) -> None:
    # Auto-width columns smear on cursor moves (stale DataTable cell cache); widths must
    # already fit the content when the rows are added, not after the next idle.
    app = DirStatApp(tree.resolve(), out_dir=tmp_path)
    async with app.run_test(size=(120, 30)) as pilot:
        await _wait(app, pilot)
        app.current = next(c for c in app.result.root.children if c.name == "empty")
        app.refresh_table()
        table = app.query_one(DirTable)
        name = table.columns[next(iter(table.columns))]
        assert not name.auto_width
        assert name.width == len("Name")
        app.current = app.result.root
        app.refresh_table()
        assert all(not c.auto_width for c in table.columns.values())
        assert table.columns[next(iter(table.columns))].width == len("top.dat")  # longest
