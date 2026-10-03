"""Synthetic stamp sheets with known object positions."""

import cv2
import numpy as np
import pytest

INK = (0, 0, 0)


def blank(width=1200, height=900, paper=(255, 255, 255)) -> np.ndarray:
    sheet = np.empty((height, width, 3), dtype=np.uint8)
    sheet[:] = paper
    return sheet


def filled_rect(sheet, x, y, w, h, color=INK):
    cv2.rectangle(sheet, (x, y), (x + w - 1, y + h - 1), color, thickness=-1)


def ring(sheet, cx, cy, r, color=INK, thickness=8):
    cv2.circle(sheet, (cx, cy), r, color, thickness=thickness, lineType=cv2.LINE_AA)


def grid_sheet() -> tuple[np.ndarray, list[tuple[int, int, int, int]]]:
    """2 rows x 3 columns of filled rectangles with different sizes, in reading order."""
    sheet = blank()
    boxes = [
        (100, 100, 200, 150),
        (450, 120, 120, 200),
        (800, 90, 250, 250),
        (90, 550, 300, 100),
        (500, 520, 150, 260),
        (850, 600, 180, 180),
    ]
    # Draw in scrambled order so detection order can't just follow drawing order.
    for i in (4, 1, 5, 0, 3, 2):
        filled_rect(sheet, *boxes[i])
    return sheet, boxes


@pytest.fixture
def grid():
    return grid_sheet()
