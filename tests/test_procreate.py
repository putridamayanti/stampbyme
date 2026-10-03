import io
import plistlib
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pytest
from PIL import Image, ImageDraw

from stampbyme.procreate import (
    REFERENCE_SETTINGS, STAMP_OVERRIDES, THUMBNAIL_SIZE, brush_archive, brush_file, brush_name,
    brushset_file, coverage, make_brush, safe_filename, shape_png,
)

REFERENCE = Path(__file__).parent / "reference" / "Star.brush"
needs_reference = pytest.mark.skipif(not REFERENCE.exists(), reason="tests/reference/Star.brush not present")
UID = plistlib.UID


def stamp(size=256, box=(64, 64, 192, 192), fill=(0, 0, 0, 255)):
    im = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    ImageDraw.Draw(im).ellipse(box, fill=fill)
    return im


def resolve(objects, value):
    return objects[value.data] if isinstance(value, UID) else value


def class_name(objects, obj):
    return objects[obj["$class"].data]["$classname"]


def load_archive(data):
    archive = plistlib.loads(data)
    return archive, archive["$objects"], archive["$objects"][1]


# ---- Brush.archive ----------------------------------------------------------

def test_archive_is_binary_keyed_archive():
    data = brush_archive("Leaf")
    assert data.startswith(b"bplist00")
    archive, objects, root = load_archive(data)
    assert archive["$archiver"] == "NSKeyedArchiver"
    assert archive["$version"] == 100000
    assert archive["$top"] == {"root": UID(1)}
    assert objects[0] == "$null"
    assert objects[root["$class"].data] == {
        "$classname": "SilicaBrush", "$classes": ["SilicaBrush", "ValkyrieBrush", "NSObject"]}


def test_archive_identity_and_images():
    created = datetime(2026, 10, 1, tzinfo=timezone.utc)
    _, objects, root = load_archive(brush_archive("Maple Leaf", author="Me", created=created))
    assert resolve(objects, root["name"]) == "Maple Leaf"
    assert resolve(objects, root["authorName"]) == "Me"
    assert root["bundledShapePath"] == UID(0) and root["bundledGrainPath"] == UID(0)
    assert resolve(objects, root["color"]) == bytes(16)
    date = resolve(objects, root["creationDate"])
    assert class_name(objects, date) == "NSDate"
    assert date["NS.time"] == (created - datetime(2001, 1, 1, tzinfo=timezone.utc)).total_seconds()


def test_no_author_is_null():
    _, _, root = load_archive(brush_archive("Leaf"))
    assert root["authorName"] == UID(0)


def test_stamp_settings():
    _, _, root = load_archive(brush_archive("Leaf"))
    assert root["plotSpacing"] == 2.0 and root["shapeCount"] == 1.0
    for key in ("plotJitter", "shapeScatter", "shapeRotation", "dynamicsJitterSize", "dynamicsPressureSize"):
        assert root[key] == 0.0
    assert root["shapeRandomise"] is False and root["shapeInverted"] is False
    assert root["stamp"] is True and root["version"] == 2


def test_inline_value_types_match_reference_settings():
    _, _, root = load_archive(brush_archive("Leaf"))
    for key, value in REFERENCE_SETTINGS.items():
        assert type(root[key]) is type(value), key


def test_curves_are_linear_magnitudinal_curves():
    _, objects, root = load_archive(brush_archive("Leaf"))
    curve = resolve(objects, root["dynamicsPressureSizeCurve"])
    assert class_name(objects, curve) == "ValkyrieMagnitudinalCurve"
    points = resolve(objects, curve["points"])
    assert class_name(objects, points) == "NSMutableArray"
    assert [resolve(objects, p) for p in points["NS.objects"]] == ["{0.000000, 0.000000}", "{1.000000, 1.000000}"]


def test_every_uid_points_inside_the_object_table():
    _, objects, _ = load_archive(brush_archive("Leaf", author="Me"))

    def walk(value):
        if isinstance(value, UID):
            assert 0 <= value.data < len(objects)
        elif isinstance(value, dict):
            for v in value.values():
                walk(v)
        elif isinstance(value, list):
            for v in value:
                walk(v)

    walk(objects)


@needs_reference
def test_matches_real_procreate_brush():
    """Same keys, types, values (except stamp overrides) and object classes as Procreate's Star.brush."""
    _, real_objects, real = load_archive(zipfile.ZipFile(REFERENCE).read("Brush.archive"))
    _, objects, ours = load_archive(brush_archive("Star", author="Ghost"))
    assert set(ours) == set(real)
    for key, real_value in real.items():
        value = ours[key]
        assert type(value) is type(real_value), key
        if isinstance(real_value, UID):
            real_obj, obj = resolve(real_objects, real_value), resolve(objects, value)
            assert type(obj) is type(real_obj), key
            if isinstance(real_obj, dict) and "$class" in real_obj:
                assert class_name(objects, obj) == class_name(real_objects, real_obj), key
            elif key != "$class":
                assert obj == real_obj, key
        elif key not in STAMP_OVERRIDES:
            assert value == real_value, key


# ---- Shape.png / thumbnail --------------------------------------------------

def test_coverage_of_transparent_stamp_is_alpha():
    # Transparent pixels stored as black are empty; ink colour doesn't reduce coverage.
    im = Image.new("RGBA", (4, 1))
    im.putdata([(0, 0, 0, 0), (12, 10, 9, 255), (200, 30, 30, 255), (0, 0, 0, 128)])
    assert np.array(coverage(im)).ravel().tolist() == [0, 255, 255, 128]


def test_coverage_of_opaque_image_is_darkness():
    im = Image.new("RGB", (3, 1))
    im.putdata([(255, 255, 255), (0, 0, 0), (128, 128, 128)])
    assert np.array(coverage(im)).ravel().tolist() == [0, 255, 127]


def test_shape_is_white_on_black_grayscale():
    shape = shape_png(stamp())
    assert shape.mode == "L" and shape.size == (256, 256)
    assert shape.getpixel((0, 0)) == 0
    assert shape.getpixel((128, 128)) == 255


def test_shape_keeps_stamp_framing_and_orientation():
    im = Image.new("RGBA", (200, 200), (0, 0, 0, 0))
    ImageDraw.Draw(im).rectangle((20, 10, 60, 50), fill=(0, 0, 0, 255))  # top-left square
    ys, xs = np.nonzero(np.array(shape_png(im)))
    assert (xs.min(), ys.min(), xs.max(), ys.max()) == (20, 10, 60, 50)


def test_non_square_stamp_is_centred_on_square():
    shape = shape_png(Image.new("RGBA", (300, 100), (0, 0, 0, 255)))
    assert shape.size == (300, 300)
    assert shape.getpixel((150, 50)) == 0 and shape.getpixel((150, 150)) == 255


def test_large_stamp_is_capped_at_2048():
    assert shape_png(stamp(size=3000, box=(500, 500, 2500, 2500))).size == (2048, 2048)


def test_thumbnail_is_white_stamps_on_transparent():
    thumb = Image.open(io.BytesIO(make_brush(stamp(), "Dot").thumbnail))
    assert thumb.mode == "RGBA" and thumb.size == THUMBNAIL_SIZE
    a = np.array(thumb)
    assert a[0, 0, 3] == 0
    assert a[..., 3].max() == 255 and (a[a[..., 3] == 255][:, :3] == 255).all()


# ---- zip containers ---------------------------------------------------------

def test_brush_file_layout():
    zf = zipfile.ZipFile(io.BytesIO(brush_file(make_brush(stamp(), "Dot"))))
    assert sorted(zf.namelist()) == ["Brush.archive", "QuickLook/Thumbnail.png", "Shape.png"]
    assert all(i.compress_type == zipfile.ZIP_DEFLATED for i in zf.infolist())
    assert Image.open(io.BytesIO(zf.read("Shape.png"))).mode == "L"


def test_brushset_layout_and_order():
    names = ["First", "Second", "Third"]
    zf = zipfile.ZipFile(io.BytesIO(brushset_file("Autumn Stamps", [make_brush(stamp(), n) for n in names])))
    assert zf.read("brushset.plist").startswith(b"<?xml")
    manifest = plistlib.loads(zf.read("brushset.plist"))
    assert manifest["name"] == "Autumn Stamps" and set(manifest) == {"brushes", "name"}
    ids = manifest["brushes"]
    assert len(set(ids)) == 3 and all(i == i.upper() and len(i) == 36 for i in ids)

    files = ("Brush.archive", "Shape.png", "QuickLook/Thumbnail.png")
    assert set(zf.namelist()) == {"brushset.plist"} | {f"{i}/{f}" for i in ids for f in files}
    assert not any(n.endswith("/") or "__MACOSX" in n or ".DS_Store" in n for n in zf.namelist())

    archives = [plistlib.loads(zf.read(f"{i}/Brush.archive"))["$objects"] for i in ids]
    assert [resolve(objs, objs[1]["name"]) for objs in archives] == names


@needs_reference
def test_brush_file_entry_names_match_real_brush():
    real = {n for n in zipfile.ZipFile(REFERENCE).namelist() if not n.startswith("Signature/")}
    ours = set(zipfile.ZipFile(io.BytesIO(brush_file(make_brush(stamp(), "Dot")))).namelist())
    assert ours == real


# ---- naming -----------------------------------------------------------------

def test_brush_name():
    assert brush_name("07", "Autumn Stamps") == "Autumn Stamps 07"
    assert brush_name("maple-leaf", "Autumn Stamps") == "Maple Leaf"


def test_safe_filename():
    assert safe_filename('Autumn: "Leaves"/Set') == "Autumn_ _Leaves__Set"
    assert safe_filename("...") == "Stamps"
