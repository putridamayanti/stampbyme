"""Build Procreate .brush and .brushset files from stamp PNGs.

The format is documented in docs/procreate-brush-format.md. Every value here is
copied from a real Procreate-exported stamp brush (Star.brush, 2020); only the
name, date and a few stamp-friendly properties differ. Nothing is guessed.
"""

import io
import plistlib
import uuid
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from PIL import Image

UID = plistlib.UID

SHAPE_MAX_SIZE = 2048  # Procreate's own stamp shapes are 2048x2048
THUMBNAIL_SIZE = (1060, 324)  # every Procreate-exported QuickLook/Thumbnail.png
APPLE_EPOCH = datetime(2001, 1, 1, tzinfo=timezone.utc)

# All 156 inline settings of Procreate's exported Star.brush stamp, with their
# exact plist types (int vs real vs bool). Floats like 0.10000000149011612 are
# Procreate's float32 values. Overrides for stamps are in STAMP_OVERRIDES.
REFERENCE_SETTINGS: dict[str, int | float | bool] = {
    "attackTilt": False, "attackTiltAngle": 0.10000000149011612, "bleedTiltAngle": 0.10000000149011612,
    "blendGammaCorrect": False, "blendMode": 0, "brightnessTiltAngle": 0.10000000149011612,
    "burntEdgesAmount": 0.0, "burntEdgesBlendMode": 1, "darknessJitterTilt": False,
    "darknessJitterTiltAngle": 0.10000000149011612, "dualBlendMode": 0, "dynamicsBlur": 0.0,
    "dynamicsBlurJitter": 0.0, "dynamicsFalloff": 0.0, "dynamicsGlazedFlow": 1.0,
    "dynamicsJitterDarkness": 0.0, "dynamicsJitterHue": 0.0, "dynamicsJitterLightness": 0.0,
    "dynamicsJitterOpacity": 0.0, "dynamicsJitterSaturation": 0.0, "dynamicsJitterSize": 0.0,
    "dynamicsJitterStrokeDarkness": 0.0, "dynamicsJitterStrokeHue": 0.0,
    "dynamicsJitterStrokeLightness": 0.0, "dynamicsJitterStrokeSaturation": 0.0, "dynamicsLoad": 0.5,
    "dynamicsMix": 0.0, "dynamicsMixSoftening": 0.0, "dynamicsPressureBleed": 0.0,
    "dynamicsPressureBleedSpeed": 0.30000001192092896, "dynamicsPressureBrightness": 0.0,
    "dynamicsPressureHue": 0.0, "dynamicsPressureMix": 0.0, "dynamicsPressureOpacity": 0.0,
    "dynamicsPressureOpacitySpeed": 0.30000001192092896, "dynamicsPressureOpacityTransfer": 1.0,
    "dynamicsPressureResponse": 0.30000001192092896, "dynamicsPressureSaturation": 0.0,
    "dynamicsPressureSecondaryColor": 0.0, "dynamicsPressureShapeRoundness": 1.0,
    "dynamicsPressureShapeRoundnessMinimum": 1.0, "dynamicsPressureSize": 0.0,
    "dynamicsPressureSizeSpeed": 0.30000001192092896, "dynamicsPressureSmoothing": 0.0,
    "dynamicsSmudgeAccumulation": 0.75, "dynamicsSpeedOpacity": 0.0, "dynamicsSpeedSize": 0.0,
    "dynamicsTiltAngle": 0.10000000149011612, "dynamicsTiltBleed": 0.0, "dynamicsTiltBrightness": 0.0,
    "dynamicsTiltCompression": 1.0, "dynamicsTiltGradation": 0.0, "dynamicsTiltHue": 0.0,
    "dynamicsTiltOpacity": 0.0, "dynamicsTiltSaturation": 0.0, "dynamicsTiltSecondaryColor": 0.0,
    "dynamicsTiltShapeRoundness": 1.0, "dynamicsTiltShapeRoundnessMinimum": 1.0,
    "dynamicsTiltSize": 0.0, "dynamicsWetAccumulation": 0.75, "dynamicsWetnessJitter": 0.0,
    "eraseOpacity": 1.0, "eraseSize": 0.5, "extendedBlend": 0,
    "gradationTiltAngle": 0.10000000149011612, "grainBlendMode": 1, "grainDepth": 1.0,
    "grainDepthJitter": 0.0, "grainDepthMinimum": 0.0, "grainOrientation": 1, "hueJitterTilt": False,
    "hueJitterTiltAngle": 0.10000000149011612, "hueTiltAngle": 0.10000000149011612,
    "importedFromABR": False, "jitterSecondary": 0.0, "jitterStrokeSecondary": 0.0,
    "lightnessJitterTilt": False, "lightnessJitterTiltAngle": 0.10000000149011612, "maxOpacity": 1.0,
    "maxPressureSizeClamped": False, "maxSize": 1.0, "minOpacity": 0.0, "minSize": 0.0,
    "opacityTiltAngle": 0.10000000149011612, "oriented": True, "paintOpacity": 1.0,
    "paintPressure": 1.0, "paintSize": 0.09909626096487045, "pencilTaperEndLength": 0.0,
    "pencilTaperOpacity": 0.0, "pencilTaperShape": 0.0, "pencilTaperSize": 0.0,
    "pencilTaperSizeLinked": False, "pencilTaperStartLength": 0.0, "pencilTipAnimation": True,
    "plotJitter": 0.0, "plotJitterTilt": False, "plotJitterTiltAngle": 0.10000000149011612,
    "plotSmoothing": 0.0, "plotSpacing": 2.0, "plotSpacingVersion": 1,
    "previewSize": 0.30000001192092896, "renderingMaxTransfer": False,
    "renderingModulatedTransfer": False, "renderingRecursiveMixing": False,
    "saturationJitterTilt": False, "saturationJitterTiltAngle": 0.10000000149011612,
    "saturationTiltAngle": 0.10000000149011612, "secondaryColorJitterTilt": False,
    "secondaryColorJitterTiltAngle": 0.10000000149011612,
    "secondaryColorTiltAngle": 0.10000000149011612, "shapeAngle": 0.0, "shapeAzimuth": False,
    "shapeCount": 1.0, "shapeCountJitter": 0.0, "shapeCountTilt": False,
    "shapeCountTiltAngle": 0.10000000149011612, "shapeFilter": True, "shapeFilterMode": 0,
    "shapeFlipXJitter": False, "shapeFlipYJitter": False, "shapeInverted": False,
    "shapeOrientation": 1, "shapeRandomise": False, "shapeRotation": 0.0, "shapeRoundness": 1.0,
    "shapeRoundnessTiltAngle": 0.10000000149011612, "shapeScatter": 0.0,
    "sizeTiltAngle": 0.10000000149011612, "smudgeOpacity": 0.800000011920929, "smudgeSize": 0.5,
    "stamp": False, "taperEndLength": 0.0, "taperOpacity": 0.0, "taperPressure": 1.0,
    "taperShape": 0.0, "taperSize": 0.0, "taperSizeLinked": False, "taperStartLength": 0.0,
    "taperVersion": 1, "textureApplication": 0, "textureBrightness": 0.0, "textureContrast": 0.0,
    "textureDepthTilt": False, "textureDepthTiltAngle": 0.10000000149011612, "textureFilter": True,
    "textureFilterMode": 0, "textureInverted": False, "textureMovement": 1.0,
    "textureOffsetJitter": True, "textureOrientation": 1, "textureRotation": 0.0, "textureScale": 1.0,
    "textureZoom": 1.0, "version": 2, "wetEdgesAmount": 0.0,
}

STAMP_OVERRIDES: dict[str, int | float | bool] = {
    "stamp": True,  # Properties > Use stamp preview: the library shows the stamp, not a stroke
    "paintSize": 0.5,  # start with the size slider in the middle (Star ships ~10%)
}

# Pressure curves Procreate stores as objects; all linear 0..1 in real files.
CURVE_KEYS = (
    "dynamicsPressureBleedCurve", "dynamicsPressureBrightnessCurve", "dynamicsPressureHueCurve",
    "dynamicsPressureOpacityCurve", "dynamicsPressureSaturationCurve",
    "dynamicsPressureSecondaryColorCurve", "dynamicsPressureShapeRoundnessCurve",
    "dynamicsPressureSizeCurve", "dynamicsPressureTransferModulationCurve",
)

BRUSH_CLASS = {"$classname": "SilicaBrush", "$classes": ["SilicaBrush", "ValkyrieBrush", "NSObject"]}
ARRAY_CLASS = {"$classname": "NSMutableArray", "$classes": ["NSMutableArray", "NSArray", "NSObject"]}
CURVE_CLASS = {"$classname": "ValkyrieMagnitudinalCurve", "$classes": ["ValkyrieMagnitudinalCurve", "NSObject"]}
DATE_CLASS = {"$classname": "NSDate", "$classes": ["NSDate", "NSObject"]}


def brush_archive(name: str, *, author: str | None = None, created: datetime | None = None) -> bytes:
    """Brush.archive: an NSKeyedArchiver binary plist with a SilicaBrush root at $objects[1]."""
    objects: list = ["$null"]
    root: dict = {}
    objects.append(root)

    def add(obj) -> UID:
        objects.append(obj)
        return UID(len(objects) - 1)

    array_class = add(ARRAY_CLASS)
    curve_class = add(CURVE_CLASS)
    for key in CURVE_KEYS:
        points = add({"NS.objects": [add("{0.000000, 0.000000}"), add("{1.000000, 1.000000}")], "$class": array_class})
        root[key] = add({"points": points, "$class": curve_class})

    created = created or datetime.now(timezone.utc)
    root.update(REFERENCE_SETTINGS)
    root.update(STAMP_OVERRIDES)
    root.update({
        "name": add(name),
        "authorName": add(author) if author else UID(0),
        "color": add(bytes(16)),
        "creationDate": add({"NS.time": (created - APPLE_EPOCH).total_seconds(), "$class": add(DATE_CLASS)}),
        "bundledShapePath": UID(0),  # $null: use the embedded Shape.png
        "bundledGrainPath": UID(0),  # $null with no Grain.png: no grain texture, as in Star.brush
        "$class": add(BRUSH_CLASS),
    })

    archive = {"$version": 100000, "$archiver": "NSKeyedArchiver", "$top": {"root": UID(1)}, "$objects": objects}
    return plistlib.dumps(archive, fmt=plistlib.FMT_BINARY, sort_keys=False)


def coverage(stamp: Image.Image) -> Image.Image:
    """Paint coverage of a stamp as an L image: 255 = full paint, 0 = none.

    For a stamp with transparency (what Phase 1 writes) coverage is the alpha
    channel: Procreate paints in the chosen colour, so the ink's own colour
    doesn't matter and transparent pixels are empty whatever RGB they store.
    A fully opaque image (e.g. ink drawn on white) uses darkness instead.
    """
    rgba = np.asarray(stamp.convert("RGBA"), dtype=np.float32)
    if (rgba[..., 3] < 255).any():
        cover = rgba[..., 3]
    else:
        cover = 255.0 - (rgba[..., 0] * 0.299 + rgba[..., 1] * 0.587 + rgba[..., 2] * 0.114)
    return Image.fromarray(np.round(cover).astype(np.uint8), "L")


def shape_png(stamp: Image.Image) -> Image.Image:
    """Procreate Shape.png: white = paint on black, square, at most 2048 px.

    The stamp keeps its own framing (padding and centring from Phase 1);
    non-square images are centred on a square canvas.
    """
    cover = coverage(stamp)
    side = max(cover.size)
    if side > SHAPE_MAX_SIZE:
        scale = SHAPE_MAX_SIZE / side
        cover = cover.resize((max(1, round(cover.width * scale)), max(1, round(cover.height * scale))), Image.Resampling.LANCZOS)
        side = SHAPE_MAX_SIZE
    shape = Image.new("L", (side, side), 0)
    shape.paste(cover, ((side - cover.width) // 2, (side - cover.height) // 2))
    return shape


def thumbnail_png(shape: Image.Image) -> Image.Image:
    """QuickLook/Thumbnail.png: three white stamps along a stroke on transparent, like Procreate's."""
    width, height = THUMBNAIL_SIZE
    thumb = Image.new("RGBA", THUMBNAIL_SIZE, (0, 0, 0, 0))
    bbox = shape.getbbox()
    if bbox is None:
        return thumb
    ink = shape.crop(bbox)
    scale = (height * 0.8) / max(ink.size)
    ink = ink.resize((max(1, round(ink.width * scale)), max(1, round(ink.height * scale))), Image.Resampling.LANCZOS)
    white = Image.new("RGBA", ink.size, (255, 255, 255, 255))
    white.putalpha(ink)
    for centre_x in (width * 0.2, width * 0.5, width * 0.8):
        thumb.alpha_composite(white, (round(centre_x - ink.width / 2), round((height - ink.height) / 2)))
    return thumb


def _png_bytes(image: Image.Image) -> bytes:
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    return buf.getvalue()


@dataclass(frozen=True)
class Brush:
    name: str
    archive: bytes
    shape: bytes
    thumbnail: bytes

    def entries(self) -> dict[str, bytes]:
        """Files of the brush, relative to the brush root (case-sensitive names)."""
        return {"Brush.archive": self.archive, "Shape.png": self.shape, "QuickLook/Thumbnail.png": self.thumbnail}


def make_brush(stamp: Image.Image, name: str, *, author: str | None = None) -> Brush:
    shape = shape_png(stamp)
    return Brush(name, brush_archive(name, author=author), _png_bytes(shape), _png_bytes(thumbnail_png(shape)))


def _zip(entries: dict[str, bytes]) -> bytes:
    """Deflated zip with forward-slash paths and no directory entries, like Procreate's exports."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for path, data in entries.items():
            zf.writestr(path, data)
    return buf.getvalue()


def brush_file(brush: Brush) -> bytes:
    """A standalone .brush: the brush files at the zip root."""
    return _zip(brush.entries())


def brushset_file(title: str, brushes: list[Brush]) -> bytes:
    """A .brushset: one uppercase-UUID folder per brush plus brushset.plist listing them in order."""
    ids = [str(uuid.uuid4()).upper() for _ in brushes]
    entries = {f"{folder}/{path}": data for folder, brush in zip(ids, brushes) for path, data in brush.entries().items()}
    entries["brushset.plist"] = plistlib.dumps({"brushes": ids, "name": title}, fmt=plistlib.FMT_XML)
    return _zip(entries)


def brush_name(stem: str, set_name: str) -> str:
    """Brush name from a PNG filename: '07' -> 'Autumn Stamps 07', 'maple-leaf' -> 'Maple Leaf'."""
    if stem.isdigit():
        return f"{set_name} {stem}"
    return stem.replace("-", " ").replace("_", " ").strip().title() or set_name


def safe_filename(name: str) -> str:
    """Strip characters Windows and iOS can't put in a filename."""
    cleaned = "".join("_" if c in '<>:"/\\|?*' or ord(c) < 32 else c for c in name).strip(" .")
    return cleaned or "Stamps"


def write_brushes(stamps: list[Path], out_dir: Path, set_name: str, *, author: str | None = None) -> tuple[Path, list[Path]]:
    """Write one .brush per stamp into out_dir/brushes/ and all of them into out_dir/<set_name>.brushset."""
    brush_dir = out_dir / "brushes"
    brush_dir.mkdir(parents=True, exist_ok=True)
    brushes, brush_paths, used = [], [], set()
    for path in stamps:
        with Image.open(path) as image:
            brush = make_brush(image, brush_name(path.stem, set_name), author=author)
        filename, n = f"{path.stem}.brush", 2
        while filename.lower() in used:  # same stem from different folders
            filename, n = f"{path.stem}-{n}.brush", n + 1
        used.add(filename.lower())
        brush_path = brush_dir / filename
        brush_path.write_bytes(brush_file(brush))
        brushes.append(brush)
        brush_paths.append(brush_path)
    set_path = out_dir / f"{safe_filename(set_name)}.brushset"
    set_path.write_bytes(brushset_file(set_name, brushes))
    return set_path, brush_paths
