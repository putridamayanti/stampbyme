"""Find caption text on a stamp sheet so it isn't cut out as stamps.

There is no OCR here: a caption is recognised by its layout. It is a row of
small ink pieces (letters, or whole words where letters touch) of similar
height, sitting on a shared baseline, much wider than tall, and surrounded by
blank paper. That check keeps small details inside illustrations (fur marks,
eyes, berries) from counting as text. When a sheet has several captions, they
must also share a font size, which rejects rows of small artwork such as a
border of leaves.
"""

from dataclasses import dataclass

import cv2
import numpy as np

BBox = tuple[int, int, int, int]  # x, y, width, height

MAX_TEXT_HEIGHT = 0.04  # of the sheet's long side; captions on AI sheets are ~1.5-2.5%
MIN_PIECES = 3  # e.g. "Owl" -> O, w, l; "5. Owl" -> 5, ., O, w, l
MIN_ASPECT = 2.5  # line width / height
WORD_GAP = 1.5  # max horizontal gap between pieces, in line heights
BASELINE_TOLERANCE = 0.3  # pieces whose bottom is within this many line heights of the baseline
BASELINE_SHARE = 0.6  # ... must be at least this share of the pieces (descenders and dots excepted)
MIN_WIDTH_VARIATION = 0.15  # std/mean of piece widths; rows of identical dots fall below this
CLEARANCE = 0.6 # blank paper required above/below the line, in line heights
OTHER_INK_ALLOWANCE = 0.03  # stray specks tolerated near a caption, as a share of its ink
MIN_LINES_FOR_SIZE_CHECK = 3  # with this many candidate lines, compare their heights
SIZE_TOLERANCE = 1.5  # a caption line is at most this much taller/shorter than the typical one


@dataclass(frozen=True)
class _Piece:
    label: int
    x: int
    y: int
    w: int
    h: int

    @property
    def right(self) -> int:
        return self.x + self.w

    @property
    def bottom(self) -> int:
        return self.y + self.h


def find_text(ink: np.ndarray) -> tuple[np.ndarray, list[BBox]]:
    """Return (mask of caption pixels, caption line boxes) for a boolean ink mask."""
    count, labels, stats, _ = cv2.connectedComponentsWithStats(ink.astype(np.uint8), connectivity=8)
    max_h = MAX_TEXT_HEIGHT * max(ink.shape)
    pieces = [
        _Piece(i, *(int(v) for v in stats[i, :4]))
        for i in range(1, count)
        if stats[i, cv2.CC_STAT_HEIGHT] <= max_h
    ]

    lines = [
        (line, box)
        for line in _group_lines(pieces, max_h)
        if _looks_like_text(line, box := _line_box(line), max_h) and _is_isolated(line, box, labels, stats)
    ]
    lines = _consistent_size(lines)

    text = np.zeros(ink.shape, dtype=bool)
    for line, (x, y, w, h) in lines:
        text[y : y + h, x : x + w] |= np.isin(labels[y : y + h, x : x + w], [p.label for p in line])

    # Words inside a closed outline (a tag, banner or frame) are part of that drawing.
    enclosed = _enclosed_by_artwork(ink & ~text)
    kept = []
    for line, (x, y, w, h) in lines:
        if enclosed[y : y + h, x : x + w].all():
            text[y : y + h, x : x + w] &= ~np.isin(labels[y : y + h, x : x + w], [p.label for p in line])
        else:
            kept.append((x, y, w, h))
    return text, kept


def _enclosed_by_artwork(artwork: np.ndarray) -> np.ndarray:
    """Paper pixels that can't be reached from the sheet border without crossing ink."""
    padded = np.pad(artwork.astype(np.uint8), 1)
    flood_mask = np.zeros((padded.shape[0] + 2, padded.shape[1] + 2), dtype=np.uint8)
    reached = padded.copy()
    cv2.floodFill(reached, flood_mask, (0, 0), 2)
    return (reached == 0)[1:-1, 1:-1]


def _consistent_size(lines: list[tuple[list[_Piece], BBox]]) -> list[tuple[list[_Piece], BBox]]:
    """Keep lines whose height matches the sheet's captions.

    Captions on a sheet share one font size, so with several candidates a line
    much taller or shorter than the typical one is artwork that happens to be
    laid out in a row, e.g. a border of small leaves.
    """
    if len(lines) < MIN_LINES_FOR_SIZE_CHECK:
        return lines
    typical = float(np.median([box[3] for _, box in lines]))
    return [(line, box) for line, box in lines if typical / SIZE_TOLERANCE <= box[3] <= typical * SIZE_TOLERANCE]


def _group_lines(pieces: list[_Piece], max_h: float) -> list[list[_Piece]]:
    """Chain pieces that overlap vertically and are at most WORD_GAP line heights apart."""
    pieces = sorted(pieces, key=lambda p: p.x)
    parent = list(range(len(pieces)))

    def root(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i, a in enumerate(pieces):
        for j in range(i + 1, len(pieces)):
            b = pieces[j]
            height = max(a.h, b.h)
            if b.x - a.right > WORD_GAP * max_h:
                break  # sorted by x: every later piece is further away
            if b.x - a.right > WORD_GAP * height:
                continue
            overlap = min(a.bottom, b.bottom) - max(a.y, b.y)
            if overlap >= 0.5 * min(a.h, b.h):
                parent[root(i)] = root(j)

    lines: dict[int, list[_Piece]] = {}
    for i, piece in enumerate(pieces):
        lines.setdefault(root(i), []).append(piece)
    return list(lines.values())


def _line_box(line: list[_Piece]) -> BBox:
    x0, y0 = min(p.x for p in line), min(p.y for p in line)
    x1, y1 = max(p.right for p in line), max(p.bottom for p in line)
    return x0, y0, x1 - x0, y1 - y0


def _looks_like_text(line: list[_Piece], box: BBox, max_h: float) -> bool:
    _, _, w, h = box
    if len(line) < MIN_PIECES or h > max_h or w < MIN_ASPECT * h:
        return False
    baseline = np.median([p.bottom for p in line])
    on_baseline = sum(abs(p.bottom - baseline) <= BASELINE_TOLERANCE * h for p in line)
    if on_baseline < BASELINE_SHARE * len(line):
        return False
    # Letters differ in shape ("i" vs "m"); a row of identical dots or dashes doesn't.
    widths = np.array([p.w for p in line], dtype=float)
    return widths.std() / widths.mean() >= MIN_WIDTH_VARIATION


def _is_isolated(line: list[_Piece], box: BBox, labels: np.ndarray, stats: np.ndarray) -> bool:
    """Blank paper within CLEARANCE line heights above/below and one line height left/right.

    A few stray specks are tolerated (up to OTHER_INK_ALLOWANCE of the line's
    own ink); anything more means the line sits inside or against artwork.
    """
    x, y, w, h = box
    dy, dx = max(3, round(CLEARANCE * h)), max(3, h)
    rows, cols = labels.shape
    region = labels[max(0, y - dy) : min(rows, y + h + dy), max(0, x - dx) : min(cols, x + w + dx)]
    ids = [p.label for p in line]
    other = np.count_nonzero(~np.isin(region, [0, *ids]))
    own = int(stats[ids, cv2.CC_STAT_AREA].sum())
    return other <= OTHER_INK_ALLOWANCE * own
