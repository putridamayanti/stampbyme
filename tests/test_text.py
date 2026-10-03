import cv2
import numpy as np
import pytest

from conftest import blank, filled_rect, ring
from stampbyme.detect import absorb_enclosed, detect_objects

FONT = cv2.FONT_HERSHEY_SIMPLEX


def caption(sheet, text, x, y, scale=0.7, thickness=2):
    """Draw caption text with its baseline at y."""
    cv2.putText(sheet, text, (x, y), FONT, scale, (0, 0, 0), thickness, cv2.LINE_AA)


def captioned_sheet():
    """Three drawings, each with a caption underneath, like an AI stamp sheet."""
    sheet = blank()
    ring(sheet, 200, 250, 120, thickness=10)
    filled_rect(sheet, 480, 140, 220, 220)
    ring(sheet, 950, 250, 110, thickness=25)
    caption(sheet, "1. Maple leaf", 120, 430)
    caption(sheet, "2. Oak leaf", 520, 430)
    caption(sheet, "3. Birch leaf", 870, 430)
    return sheet


def test_captions_are_not_stamps():
    result = detect_objects(captioned_sheet())
    assert len(result.objects) == 3
    assert len(result.text) == 3
    for x, y, w, h in result.text:
        assert 400 < y < 440 and h < 40


def test_stamps_do_not_include_caption_pixels():
    result = detect_objects(captioned_sheet())
    for obj in result.objects:
        assert obj.bbox[1] + obj.bbox[3] < 400  # nothing extends down into the caption row


def test_keep_text_keeps_captions():
    result = detect_objects(captioned_sheet(), keep_text=True)
    assert result.text == []
    assert len(result.objects) > 3


def test_caption_close_under_drawing_is_found():
    sheet = blank()
    filled_rect(sheet, 300, 100, 300, 300)
    caption(sheet, "Pumpkin patch", 330, 440)  # ~20px of paper between drawing and text
    result = detect_objects(sheet)
    assert len(result.text) == 1
    assert [o.bbox for o in result.objects] == [(300, 100, 300, 300)]


def test_large_lettering_is_artwork_not_a_caption():
    sheet = blank()
    caption(sheet, "Hello Autumn", 150, 500, scale=4, thickness=12)
    result = detect_objects(sheet, merge=40)
    assert result.text == []
    assert len(result.objects) == 1


def test_text_inside_a_drawing_is_kept():
    sheet = blank()
    cv2.rectangle(sheet, (300, 200), (700, 400), (0, 0, 0), 8)  # a label/tag outline
    caption(sheet, "Fresh apples", 380, 310)
    result = detect_objects(sheet)
    assert result.text == []
    assert len(result.objects) == 1  # the words stay inside the tag's stamp


def test_row_of_identical_dots_is_not_text():
    sheet = blank()
    for i in range(8):
        cv2.circle(sheet, (300 + i * 30, 450), 8, (0, 0, 0), -1)
    result = detect_objects(sheet, merge=20)
    assert result.text == []
    assert len(result.objects) == 1


def test_row_of_artwork_taller_than_the_captions_is_kept():
    sheet = captioned_sheet()
    # A border of small leaves: text-like layout, but twice the caption height.
    for i, w in enumerate((30, 44, 26, 40, 34, 48)):
        cv2.ellipse(sheet, (200 + i * 60, 700), (w // 2, 22), 0, 0, 360, (0, 0, 0), -1)
    result = detect_objects(sheet)
    assert len(result.text) == 3
    assert any(o.bbox[1] > 650 for o in result.objects)


def test_detail_enclosed_by_outline_joins_the_drawing():
    sheet = blank()
    ring(sheet, 400, 400, 200, thickness=10)  # head outline
    cv2.circle(sheet, (330, 350), 15, (0, 0, 0), -1)  # eye, well inside, not touching
    result = detect_objects(sheet)
    assert len(result.objects) == 1
    assert result.objects[0].mask.sum() == result.objects[0].area


def test_absorb_enclosed_keeps_neighbours_in_bbox_separate():
    # Same layout as the L-shape test: the square is inside the L's box, not inside its outline.
    sheet = blank()
    filled_rect(sheet, 100, 100, 40, 400)
    filled_rect(sheet, 100, 460, 400, 40)
    filled_rect(sheet, 300, 200, 100, 100)
    objects = detect_objects(sheet).objects
    assert len(absorb_enclosed(objects)) == 2
