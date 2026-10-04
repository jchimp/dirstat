from pathlib import Path

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


async def test_exports(tree: Path, tmp_path: Path) -> None:
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
