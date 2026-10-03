import plistlib
import zipfile
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from conftest import blank, filled_rect, grid_sheet
from stampbyme.cli import default_set_name, main
from stampbyme.export import stamp_filenames


@pytest.fixture
def sheet_file(tmp_path):
    sheet, boxes = grid_sheet()
    path = tmp_path / "autumn-sheet.png"
    Image.fromarray(sheet).save(path)
    return path, len(boxes)


def test_exports_numbered_transparent_stamps(tmp_path, sheet_file, capsys):
    path, count = sheet_file
    out = tmp_path / "out"
    assert main([str(path), "--output", str(out), "--size", "128"]) == 0

    stamps = sorted(p.name for p in out.glob("[0-9]*.png"))
    assert stamps == [f"{i:02d}.png" for i in range(1, count + 1)]
    assert (out / "preview.png").exists()
    for name in stamps:
        with Image.open(out / name) as im:
            assert im.mode == "RGBA" and im.size == (128, 128)
            assert im.getpixel((0, 0))[3] == 0
    assert "Autumn Sheet" in capsys.readouterr().out


def test_dry_run_writes_only_preview(tmp_path, sheet_file):
    path, _ = sheet_file
    out = tmp_path / "out"
    assert main([str(path), "-o", str(out), "--dry-run"]) == 0
    assert [p.name for p in out.iterdir()] == ["preview.png"]


def test_no_objects_is_an_error(tmp_path):
    path = tmp_path / "blank.png"
    Image.fromarray(blank()).save(path)
    assert main([str(path), "-o", str(tmp_path / "out")]) == 1


def test_missing_input_is_an_error(tmp_path, capsys):
    assert main([str(tmp_path / "missing.png"), "-o", str(tmp_path / "out")]) == 2
    assert "not found" in capsys.readouterr().err


def test_bare_name_is_found_in_input_folder(tmp_path, monkeypatch):
    (tmp_path / "input").mkdir()
    sheet, _ = grid_sheet()
    Image.fromarray(sheet).save(tmp_path / "input" / "autumn-sheet.png")
    monkeypatch.chdir(tmp_path)
    assert main(["autumn-sheet.png", "--output", "out", "--dry-run"]) == 0


def test_options_are_applied(tmp_path, sheet_file, capsys):
    path, count = sheet_file
    out = tmp_path / "out"
    code = main([str(path), "-o", str(out), "--size", "64", "--padding", "0",
                 "--min-area", "30000", "--name", "Autumn Stamps"])
    assert code == 0
    stamps = list(out.glob("[0-9]*.png"))
    # Only rectangles with >= 30000 ink pixels survive: 200x150, 250x250, 300x100, 150x260, 180x180.
    assert len(stamps) == 5
    with Image.open(stamps[0]) as im:
        assert im.size == (64, 64)
        alpha = np.array(im)[..., 3]
        assert alpha[:, 0].max() > 0 or alpha[0, :].max() > 0  # padding 0: ink reaches the edge
    assert "Autumn Stamps.brushset" in capsys.readouterr().out


def test_warns_about_leftover_stamps(tmp_path, sheet_file, capsys):
    path, count = sheet_file
    out = tmp_path / "out"
    out.mkdir()
    Image.new("RGBA", (4, 4)).save(out / "99.png")
    assert main([str(path), "-o", str(out), "--size", "32"]) == 0
    assert "99.png" in capsys.readouterr().err


def test_show_and_decline_exports_nothing(tmp_path, sheet_file, monkeypatch):
    path, _ = sheet_file
    out = tmp_path / "out"
    monkeypatch.setattr(Image.Image, "show", lambda self, *a, **k: None)
    monkeypatch.setattr("builtins.input", lambda prompt: "n")
    assert main([str(path), "-o", str(out), "--show"]) == 1
    assert not list(out.glob("[0-9]*.png"))


@pytest.mark.parametrize("bad", [["--size", "8"], ["--padding", "-1"], ["--min-area", "0"], ["--threshold", "255"]])
def test_invalid_options_rejected(tmp_path, sheet_file, bad):
    path, _ = sheet_file
    with pytest.raises(SystemExit):
        main([str(path), "-o", str(tmp_path / "out"), *bad])


def test_filename_numbering_widens_past_99():
    assert stamp_filenames(3) == ["01.png", "02.png", "03.png"]
    assert stamp_filenames(120)[0] == "001.png" and stamp_filenames(120)[-1] == "120.png"


def test_default_set_name():
    assert default_set_name([Path("autumn-sheet.png")]) == "Autumn Sheet"
    assert default_set_name([Path("my_leaf_set.jpg")]) == "My Leaf Set"
    assert default_set_name([Path("a.png"), Path("b.png")]) == "Stamps"


def test_builds_brushes_and_brushset(tmp_path, sheet_file):
    path, count = sheet_file
    out = tmp_path / "out"
    assert main([str(path), "-o", str(out), "--size", "128", "--name", "Autumn Stamps"]) == 0
    brushes = sorted(p.name for p in (out / "brushes").glob("*.brush"))
    assert brushes == [f"{i:02d}.brush" for i in range(1, count + 1)]
    with zipfile.ZipFile(out / "Autumn Stamps.brushset") as zf:
        manifest = plistlib.loads(zf.read("brushset.plist"))
        assert manifest["name"] == "Autumn Stamps" and len(manifest["brushes"]) == count
        objects = plistlib.loads(zf.read(manifest["brushes"][0] + "/Brush.archive"))["$objects"]
        assert objects[objects[1]["name"].data] == "Autumn Stamps 01"


def test_no_brushes_flag(tmp_path, sheet_file):
    path, _ = sheet_file
    out = tmp_path / "out"
    assert main([str(path), "-o", str(out), "--size", "64", "--no-brushes"]) == 0
    assert not (out / "brushes").exists() and not list(out.glob("*.brushset"))


def test_packages_a_folder_of_pngs(tmp_path):
    folder = tmp_path / "stamps"
    folder.mkdir()
    for stem in ("oak-leaf", "acorn"):
        im = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        im.paste((0, 0, 0, 255), (16, 16, 48, 48))
        im.save(folder / f"{stem}.png")
    Image.new("RGB", (8, 8)).save(folder / "preview.png")
    out = tmp_path / "out"
    assert main(["--pack", str(folder), "-o", str(out), "--name", "Leaves"]) == 0
    assert sorted(p.name for p in (out / "brushes").iterdir()) == ["acorn.brush", "oak-leaf.brush"]
    assert (out / "Leaves.brushset").exists()


def test_empty_folder_is_an_error(tmp_path):
    (tmp_path / "empty").mkdir()
    assert main([str(tmp_path / "empty"), "-o", str(tmp_path / "out")]) == 1
    assert main(["--pack", str(tmp_path / "empty"), "-o", str(tmp_path / "out")]) == 1


# ---- several sheets -> one brush set ----------------------------------------

def save_sheet(path, rects):
    sheet = blank()
    for rect in rects:
        filled_rect(sheet, *rect)
    Image.fromarray(sheet).save(path)


@pytest.fixture
def input_folder(tmp_path):
    """input/ with three sheets: 2 + 3 + 1 objects, named so natural order differs from plain sorting."""
    folder = tmp_path / "input"
    folder.mkdir()
    save_sheet(folder / "sheet10.png", [(100, 100, 200, 200)])
    save_sheet(folder / "sheet1.jpg", [(100, 100, 200, 200), (600, 100, 200, 200)])
    save_sheet(folder / "sheet2.png", [(100, 100, 200, 200), (500, 100, 200, 200), (900, 100, 200, 200)])
    (folder / "notes.txt").write_text("not an image")
    return folder


def brushset_names(path):
    with zipfile.ZipFile(path) as zf:
        manifest = plistlib.loads(zf.read("brushset.plist"))
        names = []
        for folder in manifest["brushes"]:
            objects = plistlib.loads(zf.read(folder + "/Brush.archive"))["$objects"]
            names.append(objects[objects[1]["name"].data])
        return manifest["name"], names


def test_folder_of_sheets_makes_one_brushset(tmp_path, input_folder, capsys):
    out = tmp_path / "out"
    assert main([str(input_folder), "-o", str(out), "--size", "64", "--name", "Seasons"]) == 0
    assert sorted(p.name for p in out.glob("[0-9]*.png")) == [f"{i:02d}.png" for i in range(1, 7)]
    assert sorted(p.name for p in out.glob("preview*.png")) == [
        "preview-sheet1.png", "preview-sheet10.png", "preview-sheet2.png"]
    title, names = brushset_names(out / "Seasons.brushset")
    assert title == "Seasons"
    assert names == [f"Seasons {i:02d}" for i in range(1, 7)]
    log = capsys.readouterr().out
    # Natural order: sheet1 (stamps 1-2), sheet2 (3-5), sheet10 (6).
    assert log.index("sheet1.jpg") < log.index("sheet2.png") < log.index("sheet10.png")
    assert "stamps 3-5" in log and "from 3 sheets" in log


def test_stamps_follow_sheet_order(tmp_path, input_folder):
    out = tmp_path / "out"
    assert main([str(input_folder / "sheet2.png"), str(input_folder / "sheet10.png"),
                 "-o", str(out), "--size", "64", "--no-brushes"]) == 0
    assert len(list(out.glob("[0-9]*.png"))) == 4


def test_no_arguments_uses_input_folder(tmp_path, input_folder, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert main(["--size", "64"]) == 0
    assert len(list((tmp_path / "output").glob("[0-9]*.png"))) == 6
    assert (tmp_path / "output" / "Stamps.brushset").exists()


def test_sheet_without_objects_is_skipped(tmp_path, input_folder, capsys):
    Image.fromarray(blank()).save(input_folder / "sheet3.png")
    out = tmp_path / "out"
    assert main([str(input_folder), "-o", str(out), "--size", "64", "--no-brushes"]) == 0
    assert len(list(out.glob("[0-9]*.png"))) == 6
    assert "sheet3.png" in capsys.readouterr().out


def test_unreadable_sheet_stops_before_exporting(tmp_path, input_folder):
    (input_folder / "broken.png").write_text("not a png")
    out = tmp_path / "out"
    assert main([str(input_folder), "-o", str(out)]) == 2
    assert not list(out.glob("[0-9]*.png"))


def test_dry_run_with_several_sheets(tmp_path, input_folder):
    out = tmp_path / "out"
    assert main([str(input_folder), "-o", str(out), "--dry-run"]) == 0
    assert sorted(p.name for p in out.iterdir()) == [
        "preview-sheet1.png", "preview-sheet10.png", "preview-sheet2.png"]


def test_preview_names_stay_unique():
    from stampbyme.cli import preview_names
    assert preview_names([Path("a.png")]) == ["preview.png"]
    assert preview_names([Path("x/leaf.png"), Path("y/leaf.jpg")]) == ["preview-leaf.png", "preview-leaf-2.png"]


def test_pack_skips_previews_and_keeps_same_stems_apart(tmp_path):
    for folder in ("a", "b"):
        (tmp_path / folder).mkdir()
        Image.new("RGBA", (32, 32), (0, 0, 0, 255)).save(tmp_path / folder / "01.png")
        Image.new("RGB", (8, 8)).save(tmp_path / folder / "preview-x.png")
    out = tmp_path / "out"
    assert main(["--pack", str(tmp_path / "a"), str(tmp_path / "b"), "-o", str(out)]) == 0
    assert sorted(p.name for p in (out / "brushes").iterdir()) == ["01-2.brush", "01.brush"]
    assert len(brushset_names(out / "Stamps.brushset")[1]) == 2
