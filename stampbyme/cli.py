"""Command line interface.

    python main.py                                   # every sheet in ./input/ -> one brush set
    python main.py autumn-sheet.png winter.jpg --name "Seasons"
    python main.py autumn-sheet.png --output ./output --padding 20 --size 2048 --min-area 100 --name "Autumn Stamps"
    python main.py --pack ./output --name "Autumn Stamps"   # package existing stamp PNGs into brushes
"""

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

from PIL import Image

from stampbyme.detect import DEFAULT_MIN_AREA, DEFAULT_THRESHOLD, Detection, detect_objects
from stampbyme.export import stale_stamps, stamp_filenames
from stampbyme.loader import SheetError, load_sheet
from stampbyme.preview import render_preview
from stampbyme.procreate import write_brushes
from stampbyme.process import DEFAULT_PADDING, DEFAULT_SIZE, render_stamp, upscale_factor

INPUT_DIR = Path("input")
PREVIEW_NAME = "preview.png"
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}
SOFT_UPSCALE = 4.0  # warn when a stamp is enlarged more than this


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="stampbyme",
        description="Split AI stamp sheets into transparent PNG stamps and one Procreate brush set.",
    )
    p.add_argument("inputs", type=Path, nargs="*", metavar="input",
                   help="sheet images or folders of sheets (default: ./input/); "
                        "bare names are also looked up in ./input/")
    p.add_argument("--output", "-o", type=Path, default=Path("output"), help="output folder (default: ./output)")
    p.add_argument("--padding", type=int, default=DEFAULT_PADDING, help=f"padding around each object in sheet pixels (default: {DEFAULT_PADDING})")
    p.add_argument("--size", type=int, default=DEFAULT_SIZE, help=f"square stamp size in pixels (default: {DEFAULT_SIZE})")
    p.add_argument("--min-area", type=int, default=DEFAULT_MIN_AREA, help=f"ignore objects with fewer ink pixels than this (default: {DEFAULT_MIN_AREA})")
    p.add_argument("--name", help="brush set name (default: from the sheet filename, or 'Stamps' for several sheets)")
    p.add_argument("--author", help="author name stored in each brush")
    p.add_argument("--no-brushes", action="store_true", help="export PNGs only, skip the Procreate brushes")
    p.add_argument("--pack", action="store_true", help="inputs are finished stamp PNGs (or folders of them): skip detection and only build brushes")
    p.add_argument("--threshold", type=int, default=DEFAULT_THRESHOLD, help=f"how much darker than the paper counts as ink, 1-254 (default: {DEFAULT_THRESHOLD})")
    p.add_argument("--keep-text", action="store_true", help="don't remove caption text (by default text lines like '1. Maple leaf' are left out)")
    p.add_argument("--merge", type=int, default=None, help="join ink fragments closer than this many pixels into one object (default: 0.5%% of the sheet's long side)")
    p.add_argument("--dry-run", action="store_true", help="detect and write the previews only; export nothing")
    p.add_argument("--show", action="store_true", help="open the previews and ask before exporting")
    return p


def resolve_input(path: Path) -> Path:
    if not path.exists() and not path.is_absolute() and (INPUT_DIR / path).exists():
        return INPUT_DIR / path
    return path


def natural_key(path: Path) -> list:
    """Sort 'sheet2' before 'sheet10'."""
    return [int(part) if part.isdigit() else part.lower() for part in re.split(r"(\d+)", path.name)]


def expand_inputs(paths: list[Path], suffixes: set[str]) -> list[Path]:
    """Files in the order given; folders expand to their images in natural filename order.

    Previews are skipped, so an output folder can be fed back in with --pack.
    """
    files = []
    for path in map(resolve_input, paths):
        if path.is_dir():
            files += sorted(
                (p for p in path.iterdir()
                 if p.is_file() and p.suffix.lower() in suffixes and not p.name.startswith("preview")),
                key=natural_key,
            )
        else:
            files.append(path)
    return files


def default_set_name(paths: list[Path]) -> str:
    if len(paths) != 1:
        return "Stamps"
    return paths[0].stem.replace("-", " ").replace("_", " ").strip().title() or "Stamps"


def preview_names(sheets: list[Path]) -> list[str]:
    """preview.png for one sheet; preview-<sheet>.png each (kept unique) for several."""
    if len(sheets) == 1:
        return [PREVIEW_NAME]
    names, used = [], set()
    for sheet in sheets:
        name, n = f"preview-{sheet.stem}.png", 2
        while name.lower() in used:
            name, n = f"preview-{sheet.stem}-{n}.png", n + 1
        used.add(name.lower())
        names.append(name)
    return names


def validate(args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    if args.size < 16:
        parser.error("--size must be at least 16")
    if args.padding < 0:
        parser.error("--padding cannot be negative")
    if args.min_area < 1:
        parser.error("--min-area must be at least 1")
    if not 1 <= args.threshold <= 254:
        parser.error("--threshold must be between 1 and 254")
    if args.merge is not None and args.merge < 0:
        parser.error("--merge cannot be negative")


def confirm(prompt: str) -> bool:
    try:
        return input(prompt).strip().lower() in ("", "y", "yes")
    except EOFError:
        return False


@dataclass
class SheetResult:
    path: Path
    detection: Detection
    preview: Path


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    validate(args, parser)

    inputs = args.inputs or [INPUT_DIR]
    files = expand_inputs(inputs, {".png"} if args.pack else IMAGE_SUFFIXES)
    if not files:
        print(f"error: no images found in {', '.join(map(str, inputs))}", file=sys.stderr)
        return 1
    name = args.name or default_set_name(files)

    if args.pack:
        missing = [f for f in files if not f.is_file()]
        if missing:
            print(f"error: File not found: {missing[0]}", file=sys.stderr)
            return 2
        report_brushes(*write_brushes(files, args.output, name, author=args.author))
        return 0

    args.output.mkdir(parents=True, exist_ok=True)
    sheets = detect_sheets(files, args)
    if sheets is None:
        return 2
    total = sum(len(s.detection.objects) for s in sheets)
    if total == 0:
        print("error: no objects found (try a lower --threshold or --min-area)", file=sys.stderr)
        return 1
    if args.dry_run:
        return 0
    if args.show:
        for sheet in sheets:
            Image.open(sheet.preview).show()
        if not confirm(f"Export {total} stamps to {args.output}? [Y/n] "):
            print("cancelled")
            return 1

    paths = export_stamps(sheets, args)
    for path in stale_stamps(args.output, paths):
        print(f"warning: {path} is left over from an earlier run", file=sys.stderr)
    sources = f" from {len(sheets)} sheets" if len(sheets) > 1 else ""
    print(f"Exported {len(paths)} stamps{sources} to {args.output}")
    if not args.no_brushes:
        report_brushes(*write_brushes(paths, args.output, name, author=args.author))
    return 0


def detect_sheets(files: list[Path], args: argparse.Namespace) -> list[SheetResult] | None:
    """Detect objects on every sheet and write its preview. None if a sheet can't be read."""
    sheets: list[SheetResult] = []
    next_number = 1
    for path, preview_name in zip(files, preview_names(files)):
        try:
            rgb = load_sheet(path)
        except SheetError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return None
        detection = detect_objects(rgb, threshold=args.threshold, min_area=args.min_area, merge=args.merge,
                                   keep_text=args.keep_text)
        count = len(detection.objects)
        preview = args.output / preview_name
        render_preview(rgb, detection, first_number=next_number).save(preview)
        span = f"stamps {next_number}-{next_number + count - 1}" if count else "no objects found"
        print(f"{path}: {rgb.shape[1]}x{rgb.shape[0]}, {span}, {len(detection.text)} text lines left out, {len(detection.ignored)} ignored as noise -> {preview}")
        sheets.append(SheetResult(path, detection, preview))
        next_number += count
    return sheets


def export_stamps(sheets: list[SheetResult], args: argparse.Namespace) -> list[Path]:
    """Render and save every stamp, numbered continuously across sheets, one at a time."""
    names = iter(stamp_filenames(sum(len(s.detection.objects) for s in sheets)))
    paths = []
    for sheet in sheets:
        if not sheet.detection.objects:
            continue
        if len(sheets) > 1:
            print(f"{sheet.path.name}:")
        rgb = load_sheet(sheet.path)
        detection = sheet.detection
        for obj in detection.objects:
            image = render_stamp(rgb, detection.paper, obj, size=args.size, padding=args.padding,
                                 ink_opacity=detection.ink_opacity)
            path = args.output / next(names)
            image.save(path, format="PNG")
            paths.append(path)
            factor = upscale_factor(obj, args.size, args.padding)
            note = f"  (upscaled {factor:.1f}x, may look soft)" if factor > SOFT_UPSCALE else ""
            print(f"  {path.name}  {obj.bbox[2]}x{obj.bbox[3]} px{note}")
    return paths


def report_brushes(set_path: Path, brush_paths: list[Path]) -> None:
    print(f"Brushes: {len(brush_paths)} in {brush_paths[0].parent}")
    print(f"Brush set: {set_path}")
