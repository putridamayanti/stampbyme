"""Load a stamp sheet image as an RGB numpy array."""

from pathlib import Path

import numpy as np
from PIL import Image, ImageOps, UnidentifiedImageError


class SheetError(Exception):
    """The input sheet could not be loaded."""


def load_sheet(path: str | Path) -> np.ndarray:
    """Return the image at `path` as an (H, W, 3) uint8 RGB array.

    Uses Pillow rather than cv2.imread so non-ASCII Windows paths work.
    EXIF orientation is applied and any transparency is flattened onto white,
    so a transparent sheet behaves like ink on white paper.
    """
    path = Path(path)
    try:
        with Image.open(path) as im:
            im = ImageOps.exif_transpose(im)
            if im.mode in ("RGBA", "LA", "PA") or "transparency" in im.info:
                rgba = im.convert("RGBA")
                white = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
                im = Image.alpha_composite(white, rgba)
            return np.array(im.convert("RGB"))
    except FileNotFoundError:
        raise SheetError(f"File not found: {path}") from None
    except (UnidentifiedImageError, OSError) as exc:
        raise SheetError(f"Cannot read image {path}: {exc}") from None
