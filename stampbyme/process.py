"""Turn a detected object into a square, centred, transparent stamp image."""

import cv2
import numpy as np
from PIL import Image

from stampbyme.detect import StampObject, paper_opacity

DEFAULT_SIZE = 2048
DEFAULT_PADDING = 20
DEFAULT_NOISE_FLOOR = 0.06  # alpha below this (after unmixing) is paper grain / JPEG noise
FRINGE = 2  # px around the thresholded ink kept for anti-aliased edges


def remove_background(
    rgb: np.ndarray,
    paper: np.ndarray,
    noise_floor: float = DEFAULT_NOISE_FLOOR,
    ink_opacity: float = 1.0,
) -> np.ndarray:
    """Convert paper-coloured background to transparency ("colour to alpha").

    Each pixel is treated as ink composited over the paper colour. Alpha is
    the smallest opacity that explains the pixel, and the colour is un-mixed
    from the paper so anti-aliased edges and grey shading become partially
    transparent ink instead of a light halo. For black ink on white this
    gives pure black with alpha = darkness.

    Alpha is then stretched so `noise_floor` -> 0 (paper grain, JPEG noise)
    and `ink_opacity` -> 1 (the sheet's solid ink, which is rarely pure black).
    """
    px = rgb.astype(np.float32)
    paper = paper.astype(np.float32)
    alpha = paper_opacity(rgb, paper)

    safe = np.where(alpha > 0, alpha, 1.0)[..., None]
    color = np.clip(paper + (px - paper) / safe, 0, 255)

    alpha = np.clip((alpha - noise_floor) / max(ink_opacity - noise_floor, 1e-3), 0.0, 1.0)
    out = np.empty(rgb.shape[:2] + (4,), dtype=np.uint8)
    out[..., :3] = np.round(color)
    out[..., 3] = np.round(alpha * 255)
    out[out[..., 3] == 0, :3] = 0
    return out


def render_stamp(
    rgb: np.ndarray,
    paper: np.ndarray,
    obj: StampObject,
    *,
    size: int = DEFAULT_SIZE,
    padding: int = DEFAULT_PADDING,
    noise_floor: float = DEFAULT_NOISE_FLOOR,
    ink_opacity: float = 1.0,
) -> Image.Image:
    """Cut `obj` out of the sheet and fit it, centred, on a transparent size x size canvas.

    `padding` is in sheet pixels around the object's tight bounding box; the
    padded box is scaled (up or down) so its longer side fills the canvas,
    preserving aspect ratio. Only this object's ink is kept, so neighbours
    that intrude into its bounding box are not copied.
    """
    sheet_h, sheet_w = rgb.shape[:2]
    x, y, w, h = obj.bbox
    # Work on the bbox plus a FRINGE margin on every side. Where that margin runs
    # off the sheet it stays transparent, so resampling is symmetric and the
    # object stays centred even when it touches the sheet edge.
    x0, y0 = max(0, x - FRINGE), max(0, y - FRINGE)
    x1, y1 = min(sheet_w, x + w + FRINGE), min(sheet_h, y + h + FRINGE)
    rgba = np.zeros((h + 2 * FRINGE, w + 2 * FRINGE, 4), dtype=np.uint8)
    ox, oy = x0 - (x - FRINGE), y0 - (y - FRINGE)
    rgba[oy : oy + y1 - y0, ox : ox + x1 - x0] = remove_background(rgb[y0:y1, x0:x1], paper, noise_floor, ink_opacity)

    keep = np.zeros(rgba.shape[:2], dtype=np.uint8)
    keep[FRINGE : FRINGE + h, FRINGE : FRINGE + w] = obj.mask
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * FRINGE + 1, 2 * FRINGE + 1))
    keep = cv2.dilate(keep, kernel)
    rgba[keep == 0] = 0
    cutout = Image.fromarray(rgba, "RGBA")

    scale = size / (max(w, h) + 2 * padding)
    scaled_w = max(1, round(cutout.width * scale))
    scaled_h = max(1, round(cutout.height * scale))
    # Pillow resizes RGBA with premultiplied alpha, so edges don't pick up dark fringes.
    cutout = cutout.resize((scaled_w, scaled_h), Image.Resampling.LANCZOS)

    centre_x, centre_y = scaled_w / 2, scaled_h / 2
    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    canvas.paste(cutout, (round(size / 2 - centre_x), round(size / 2 - centre_y)))
    return canvas


def upscale_factor(obj: StampObject, size: int, padding: int) -> float:
    """How much the object is enlarged to fill the canvas (>1 means upscaled, may look soft)."""
    return size / (max(obj.bbox[2], obj.bbox[3]) + 2 * padding)
