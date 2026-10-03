"""Stamp filenames in the output folder."""

import re
from pathlib import Path

STAMP_NAME = re.compile(r"^\d+\.png$")


def stamp_filenames(count: int) -> list[str]:
    """01.png, 02.png, ... (wider numbers once there are 100+ stamps)."""
    width = max(2, len(str(count)))
    return [f"{i:0{width}d}.png" for i in range(1, count + 1)]


def stale_stamps(out_dir: Path, written: list[Path]) -> list[Path]:
    """Numbered PNGs in `out_dir` left over from an earlier run with more stamps."""
    keep = {p.name for p in written}
    return sorted(p for p in out_dir.glob("*.png") if STAMP_NAME.match(p.name) and p.name not in keep)
