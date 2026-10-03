"""Draw detected objects on the sheet so detection can be checked before exporting."""

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from stampbyme.detect import Detection

PREVIEW_MAX_SIDE = 2400
BOX_COLOR = (230, 40, 90)
IGNORED_COLOR = (150, 150, 150)
TEXT_COLOR = (40, 120, 230)


def render_preview(
    rgb: np.ndarray, detection: Detection, first_number: int = 1, max_side: int = PREVIEW_MAX_SIDE
) -> Image.Image:
    """Sheet with numbered boxes for each stamp, blue boxes for captions left out, and thin grey boxes for noise.

    Numbers match the exported filenames (1 -> 01.png); with several sheets,
    `first_number` continues the numbering from the previous sheet.
    """
    sheet = Image.fromarray(rgb, "RGB")
    scale = min(1.0, max_side / max(sheet.size))
    if scale < 1.0:
        sheet = sheet.resize((round(sheet.width * scale), round(sheet.height * scale)), Image.Resampling.LANCZOS)

    draw = ImageDraw.Draw(sheet)
    line = max(2, round(max(sheet.size) / 600))
    font = ImageFont.load_default(size=max(14, round(max(sheet.size) / 60)))

    def scaled(box):
        x, y, w, h = box
        return [x * scale, y * scale, (x + w) * scale, (y + h) * scale]

    for box in detection.ignored:
        draw.rectangle(scaled(box), outline=IGNORED_COLOR, width=1)
    for box in detection.text:
        draw.rectangle(scaled(box), outline=TEXT_COLOR, width=max(1, line // 2))

    for number, obj in enumerate(detection.objects, start=first_number):
        left, top, right, bottom = scaled(obj.bbox)
        draw.rectangle([left, top, right, bottom], outline=BOX_COLOR, width=line)
        label = str(number)
        tl, tt, tr, tb = draw.textbbox((0, 0), label, font=font)
        pad = line * 2
        label_h = (tb - tt) + 2 * pad
        # Sit the label just above the box so it doesn't hide small objects.
        label_top = top - label_h if top >= label_h else top
        label_box = [left, label_top, left + (tr - tl) + 2 * pad, label_top + label_h]
        draw.rectangle(label_box, fill=BOX_COLOR)
        draw.text((left + pad - tl, label_top + pad - tt), label, fill="white", font=font)

    return sheet
