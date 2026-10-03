import io

import cv2
import numpy as np
import pytest
from PIL import Image

from conftest import blank, filled_rect, grid_sheet, ring
from stampbyme.detect import detect_objects, estimate_paper_color, sort_reading_order, StampObject


def test_finds_every_object_with_exact_bbox(grid):
    sheet, boxes = grid
    result = detect_objects(sheet)
    assert [o.bbox for o in result.objects] == boxes


def test_reading_order_is_rows_then_columns(grid):
    sheet, boxes = grid
    result = detect_objects(sheet)
    xs_row1 = [o.bbox[0] for o in result.objects[:3]]
    xs_row2 = [o.bbox[0] for o in result.objects[3:]]
    assert xs_row1 == sorted(xs_row1) and xs_row2 == sorted(xs_row2)
    assert max(o.bbox[1] for o in result.objects[:3]) < min(o.bbox[1] for o in result.objects[3:])


def test_reading_order_tolerates_uneven_rows():
    def obj(x, y, w, h):
        return StampObject((x, y, w, h), np.ones((h, w), bool), w * h)

    tall_left = obj(0, 0, 100, 300)
    short_right_low = obj(200, 150, 100, 100)  # centre inside tall_left's span -> same row
    next_row = obj(0, 400, 100, 100)
    ordered = sort_reading_order([next_row, short_right_low, tall_left])
    assert ordered == [tall_left, short_right_low, next_row]


def test_mask_and_area_match_ink(grid):
    sheet, boxes = grid
    obj = detect_objects(sheet).objects[0]
    x, y, w, h = boxes[0]
    assert obj.mask.shape == (h, w)
    assert obj.mask.all()
    assert obj.area == w * h


def test_small_noise_is_ignored():
    sheet = blank()
    filled_rect(sheet, 100, 100, 200, 200)
    specks = [(600, 300), (900, 700), (400, 800)]
    for x, y in specks:
        filled_rect(sheet, x, y, 3, 3)
    result = detect_objects(sheet, min_area=100)
    assert [o.bbox for o in result.objects] == [(100, 100, 200, 200)]
    assert sorted(result.ignored) == sorted((x, y, 3, 3) for x, y in specks)


def test_min_area_boundary():
    sheet = blank()
    filled_rect(sheet, 100, 100, 10, 10)  # exactly 100 ink pixels
    assert len(detect_objects(sheet, min_area=100).objects) == 1
    assert len(detect_objects(sheet, min_area=101).objects) == 0


def test_nearby_fragments_merge_into_one_object():
    sheet = blank()
    ring(sheet, 300, 300, 100)
    filled_rect(sheet, 300, 410, 8, 8)  # small detached "stem", ~4px below the ring
    merged = detect_objects(sheet, merge=6)
    split = detect_objects(sheet, merge=0, min_area=10)
    assert len(merged.objects) == 1
    assert len(split.objects) == 2


def test_default_merge_keeps_well_separated_objects_apart(grid):
    sheet, boxes = grid
    assert len(detect_objects(sheet).objects) == len(boxes)


def test_interleaved_objects_get_separate_masks():
    # A small square sits inside an L-shape's bounding box without touching it.
    sheet = blank()
    filled_rect(sheet, 100, 100, 40, 400)  # L vertical bar
    filled_rect(sheet, 100, 460, 400, 40)  # L horizontal bar
    filled_rect(sheet, 300, 200, 100, 100)  # square inside the L's bbox
    result = detect_objects(sheet)
    assert len(result.objects) == 2
    big, small = sorted(result.objects, key=lambda o: o.area, reverse=True)
    assert big.bbox == (100, 100, 400, 400)
    # The square's pixels are inside the L's bbox but not in the L's mask.
    assert not big.mask[100:200, 200:300].any()
    assert small.bbox == (300, 200, 100, 100)


def test_cream_paper_is_estimated_and_not_detected():
    cream = (246, 238, 220)
    sheet = blank(paper=cream)
    filled_rect(sheet, 200, 200, 300, 300)
    paper = estimate_paper_color(sheet)
    assert np.allclose(paper, cream, atol=1)
    result = detect_objects(sheet)
    assert [o.bbox for o in result.objects] == [(200, 200, 300, 300)]


def test_coloured_ink_is_detected():
    sheet = blank()
    filled_rect(sheet, 100, 100, 200, 200, color=(250, 220, 0))  # yellow: only blue channel is dark
    assert len(detect_objects(sheet).objects) == 1


def test_light_grey_below_threshold_is_paper():
    sheet = blank()
    filled_rect(sheet, 100, 100, 200, 200, color=(235, 235, 235))
    assert detect_objects(sheet, threshold=32).objects == []
    assert len(detect_objects(sheet, threshold=10).objects) == 1


def test_blank_sheet_has_no_objects():
    result = detect_objects(blank())
    assert result.objects == [] and result.ignored == []


def test_survives_jpeg_artifacts(grid):
    sheet, boxes = grid
    buf = io.BytesIO()
    Image.fromarray(sheet).save(buf, format="JPEG", quality=70)
    jpeg = np.array(Image.open(io.BytesIO(buf.getvalue())).convert("RGB"))
    result = detect_objects(jpeg)
    assert len(result.objects) == len(boxes)
    for obj, (x, y, w, h) in zip(result.objects, boxes):
        ox, oy, ow, oh = obj.bbox
        assert abs(ox - x) <= 2 and abs(oy - y) <= 2
        assert abs(ow - w) <= 4 and abs(oh - h) <= 4


def test_anti_aliased_line_art():
    sheet = blank()
    ring(sheet, 250, 250, 120, thickness=3)
    cv2.line(sheet, (600, 100), (1000, 500), (0, 0, 0), 2, cv2.LINE_AA)
    result = detect_objects(sheet)
    assert len(result.objects) == 2
    # The ring's hollow centre is not ink.
    ring_obj = result.objects[0]
    h, w = ring_obj.mask.shape
    assert not ring_obj.mask[h // 2, w // 2]


def test_large_merge_does_not_absorb_distant_specks():
    sheet = blank()
    filled_rect(sheet, 300, 300, 300, 40)
    filled_rect(sheet, 450, 370, 3, 3)  # speck 30px below the bar
    result = detect_objects(sheet, merge=50)
    assert [o.bbox for o in result.objects] == [(300, 300, 300, 40)]
    assert result.ignored == [(450, 370, 3, 3)]


def test_speck_touching_an_object_is_kept():
    sheet = blank()
    filled_rect(sheet, 300, 300, 300, 40)
    filled_rect(sheet, 450, 343, 3, 3)  # 3px gap: part of the drawing (e.g. a dot accent)
    result = detect_objects(sheet, merge=50)
    assert [o.bbox for o in result.objects] == [(300, 300, 300, 46)]
    assert result.ignored == []


def test_ring_of_dots_groups_with_larger_merge():
    sheet = blank()
    for i in range(12):
        angle = np.deg2rad(i * 30)
        cv2.circle(sheet, (int(600 + 150 * np.cos(angle)), int(450 + 150 * np.sin(angle))), 12, (0, 0, 0), -1)
    assert len(detect_objects(sheet).objects) == 12
    assert len(detect_objects(sheet, merge=60).objects) == 1
