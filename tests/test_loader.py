import numpy as np
import pytest
from PIL import Image

from stampbyme.loader import SheetError, load_sheet


def test_png_loads_as_rgb(tmp_path):
    path = tmp_path / "sheet.png"
    Image.new("RGB", (40, 30), (10, 20, 30)).save(path)
    rgb = load_sheet(path)
    assert rgb.shape == (30, 40, 3) and rgb.dtype == np.uint8
    assert tuple(rgb[0, 0]) == (10, 20, 30)


def test_jpg_loads(tmp_path):
    path = tmp_path / "sheet.jpg"
    Image.new("RGB", (40, 30), "white").save(path)
    assert load_sheet(path).shape == (30, 40, 3)


def test_transparency_is_flattened_onto_white(tmp_path):
    path = tmp_path / "sheet.png"
    im = Image.new("RGBA", (20, 20), (0, 0, 0, 0))
    im.putpixel((5, 5), (0, 0, 0, 255))
    im.save(path)
    rgb = load_sheet(path)
    assert tuple(rgb[0, 0]) == (255, 255, 255)
    assert tuple(rgb[5, 5]) == (0, 0, 0)


def test_grayscale_loads_as_rgb(tmp_path):
    path = tmp_path / "sheet.png"
    Image.new("L", (20, 10), 128).save(path)
    assert tuple(load_sheet(path)[0, 0]) == (128, 128, 128)


def test_non_ascii_path(tmp_path):
    path = tmp_path / "herbst-blätter-秋.png"
    Image.new("RGB", (8, 8), "white").save(path)
    assert load_sheet(path).shape == (8, 8, 3)


def test_exif_orientation_is_applied(tmp_path):
    path = tmp_path / "rotated.jpg"
    exif = Image.Exif()
    exif[0x0112] = 6  # rotate 90 degrees clockwise on display
    Image.new("RGB", (40, 20), "white").save(path, exif=exif)
    assert load_sheet(path).shape == (40, 20, 3)


def test_missing_file(tmp_path):
    with pytest.raises(SheetError, match="not found"):
        load_sheet(tmp_path / "nope.png")


def test_not_an_image(tmp_path):
    path = tmp_path / "notes.png"
    path.write_text("hello")
    with pytest.raises(SheetError, match="Cannot read"):
        load_sheet(path)
