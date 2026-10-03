"""Find the individual illustrations on a stamp sheet."""

from dataclasses import dataclass, field

import cv2
import numpy as np

from stampbyme.text import find_text

BBox = tuple[int, int, int, int]  # x, y, width, height

DEFAULT_THRESHOLD = 32
DEFAULT_MIN_AREA = 100


@dataclass(frozen=True)
class StampObject:
    """One detected illustration."""

    bbox: BBox  # tight box around the ink, in sheet pixels
    mask: np.ndarray = field(repr=False)  # bool (h, w): which pixels in bbox are this object's ink
    area: int  # number of ink pixels


@dataclass(frozen=True)
class Detection:
    objects: list[StampObject]  # in reading order (rows top to bottom, left to right)
    ignored: list[BBox]  # groups rejected as noise (smaller than min_area)
    paper: np.ndarray  # estimated background colour, float32 RGB
    ink_opacity: float = 1.0  # opacity of the sheet's solid ink; treated as fully opaque
    text: list[BBox] = field(default_factory=list)  # caption lines left out of the stamps


def estimate_paper_color(rgb: np.ndarray) -> np.ndarray:
    """Estimate the sheet's background colour.

    Takes the median colour of the brightest quarter of the pixels, which is
    paper as long as the drawings cover less than three quarters of the sheet.
    Handles cream or grey AI "paper" as well as pure white.
    """
    sample = rgb[::4, ::4].reshape(-1, 3)
    lightness = sample.min(axis=1)
    bright = sample[lightness >= np.percentile(lightness, 75)]
    return np.median(bright, axis=0).astype(np.float32)


def paper_opacity(rgb: np.ndarray, paper: np.ndarray) -> np.ndarray:
    """Smallest opacity (0..1) of dark ink over `paper` that explains each pixel."""
    px = rgb.astype(np.float32)
    paper = paper.astype(np.float32)
    return np.clip(((paper - px) / np.maximum(paper, 1.0)).max(axis=-1), 0.0, 1.0)


def estimate_ink_opacity(rgb: np.ndarray, paper: np.ndarray, ink: np.ndarray) -> float:
    """How opaque the sheet's solid ink is.

    AI sheets rarely use pure black, so ink like (25, 25, 30) on cream paper
    is only ~90% opaque. Stamps should treat that ink as solid. The solid ink
    is the darkest cluster of ink pixels (within 0.08 of the 98th percentile);
    its lower quartile is used so noise inside solid areas still reaches full
    opacity. Never below 0.5, so a sheet of light-grey drawings isn't pushed
    all the way to solid.
    """
    pixels = rgb[ink]
    if len(pixels) == 0:
        return 1.0
    opacity = paper_opacity(pixels[:: max(1, len(pixels) // 200_000)], paper)
    solid = opacity[opacity >= np.percentile(opacity, 98) - 0.08]
    return float(np.clip(np.percentile(solid, 25), 0.5, 1.0))


def ink_mask(rgb: np.ndarray, paper: np.ndarray, threshold: int = DEFAULT_THRESHOLD) -> np.ndarray:
    """Pixels darker than the paper by more than `threshold` in any channel."""
    paper_i = np.round(paper).astype(np.int16)
    darkness = np.zeros(rgb.shape[:2], dtype=np.int16)
    for c in range(3):
        np.maximum(darkness, paper_i[c] - rgb[..., c].astype(np.int16), out=darkness)
    return darkness > threshold


def default_merge_distance(shape: tuple[int, ...]) -> int:
    """Gap (px) below which ink fragments count as one object: 0.5% of the sheet's long side."""
    return max(2, round(max(shape[:2]) * 0.005))


def detect_objects(
    rgb: np.ndarray,
    *,
    threshold: int = DEFAULT_THRESHOLD,
    min_area: int = DEFAULT_MIN_AREA,
    merge: int | None = None,
    keep_text: bool = False,
) -> Detection:
    """Detect separate illustrations on the sheet.

    Ink fragments of at least `min_area` pixels that are closer than `merge`
    px are grouped into one object, so a leaf with detached veins or a ring of
    dots stays together. Smaller fragments (specks) only join an object they
    almost touch (within the default merge distance); otherwise they are
    noise. This way a large `merge` doesn't sweep stray specks into objects.

    Caption text (e.g. "1. Maple leaf" under a drawing) is removed first
    unless `keep_text` is set; see stampbyme/text.py.
    """
    paper = estimate_paper_color(rgb)
    ink = ink_mask(rgb, paper, threshold)
    text: list[BBox] = []
    if not keep_text:
        text_pixels, text = find_text(ink)
        ink &= ~text_pixels
    if merge is None:
        merge = default_merge_distance(rgb.shape)
    near = min(merge, default_merge_distance(rgb.shape))

    _, fragments, fragment_stats, _ = cv2.connectedComponentsWithStats(ink.astype(np.uint8), connectivity=8)
    is_speck = fragment_stats[:, cv2.CC_STAT_AREA] < min_area
    is_speck[0] = False  # background label
    speck = is_speck[fragments]
    core = (ink & ~speck).astype(np.uint8)

    ignored: list[BBox] = []
    if speck.any():
        attached = speck & (_dilate(core, near) > 0)
        ink = core.astype(bool) | attached
        for label in np.flatnonzero(is_speck):
            x, y, w, h = (int(v) for v in fragment_stats[label, :4])
            if not attached[y : y + h, x : x + w][fragments[y : y + h, x : x + w] == label].any():
                ignored.append((x, y, w, h))

    grouped = _dilate(core, merge)
    count, labels, stats, _ = cv2.connectedComponentsWithStats(grouped, connectivity=8)
    objects: list[StampObject] = []
    for label in range(1, count):
        gx, gy, gw, gh = (int(v) for v in stats[label, :4])
        region = ink[gy : gy + gh, gx : gx + gw] & (labels[gy : gy + gh, gx : gx + gw] == label)
        area = int(np.count_nonzero(region))
        if area == 0:
            continue
        bx, by, bw, bh = cv2.boundingRect(region.astype(np.uint8))
        bbox = (gx + bx, gy + by, bw, bh)
        if area < min_area:
            ignored.append(bbox)
        else:
            objects.append(StampObject(bbox, region[by : by + bh, bx : bx + bw].copy(), area))

    objects = absorb_enclosed(objects)
    return Detection(sort_reading_order(objects), ignored, paper, estimate_ink_opacity(rgb, paper, ink), text)


def absorb_enclosed(objects: list[StampObject]) -> list[StampObject]:
    """Merge objects lying entirely inside another object's outline into it.

    A rabbit's eye or a pattern inside a pumpkin isn't connected to the outline
    but belongs to the drawing. Objects that only overlap another's bounding
    box (not its filled outline) stay separate.
    """
    remaining = sorted(objects, key=lambda o: o.area, reverse=True)
    result: list[StampObject] = []
    while remaining:
        outer = remaining.pop(0)
        x, y, w, h = outer.bbox
        contours, _ = cv2.findContours(outer.mask.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        filled = np.zeros((h, w), dtype=np.uint8)
        cv2.drawContours(filled, contours, -1, 1, thickness=cv2.FILLED)
        mask, area, keep = outer.mask.copy(), outer.area, []
        for inner in remaining:
            ix, iy, iw, ih = inner.bbox
            ox, oy = ix - x, iy - y
            inside = 0 <= ox and 0 <= oy and ox + iw <= w and oy + ih <= h
            if inside and filled[oy : oy + ih, ox : ox + iw][inner.mask].all():
                mask[oy : oy + ih, ox : ox + iw] |= inner.mask
                area += inner.area
            else:
                keep.append(inner)
        remaining = keep
        result.append(StampObject(outer.bbox, mask, area))
    return result


def _dilate(mask: np.ndarray, radius: int) -> np.ndarray:
    if radius <= 0:
        return mask
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * radius + 1, 2 * radius + 1))
    return cv2.dilate(mask, kernel)


def sort_reading_order(objects: list[StampObject]) -> list[StampObject]:
    """Order objects in rows, top to bottom, then left to right within a row.

    An object joins the current row when its vertical centre falls inside the
    vertical span of the row's first object.
    """
    by_centre = sorted(objects, key=lambda o: o.bbox[1] + o.bbox[3] / 2)
    rows: list[list[StampObject]] = []
    for obj in by_centre:
        centre_y = obj.bbox[1] + obj.bbox[3] / 2
        if rows:
            first = rows[-1][0]
            if centre_y <= first.bbox[1] + first.bbox[3]:
                rows[-1].append(obj)
                continue
        rows.append([obj])
    return [obj for row in rows for obj in sorted(row, key=lambda o: o.bbox[0])]
