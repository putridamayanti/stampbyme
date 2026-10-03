# stampbyme

Turn one or more AI-generated stamp sheets into individual transparent PNG stamps and one Procreate `.brushset`.

```
sheet image → detect objects → crop → remove paper → centre + resize → 01.png, 02.png, …
                                                                     → one .brush per PNG
                                                                     → Autumn Stamps.brushset
```

## Setup

```bash
py -3.13 -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
```

## Usage

```bash
python main.py --name "Autumn Stamps"                   # every sheet in ./input/ -> one brush set
python main.py autumn-sheet.png winter.jpg --name "Seasons"   # just these sheets
python main.py autumn-sheet.png                         # a single sheet
```

Inputs can be image files (PNG, JPG, WebP, BMP, TIFF) or folders of them; with no input, `./input/` is used. Folders are read in natural filename order (`sheet2` before `sheet10`), and a bare filename is also looked up in `./input/`. All settings apply to every sheet; paper colour and ink level are measured per sheet.

Stamps from all sheets are numbered continuously (sheet 1 gives 01–07, sheet 2 continues at 08, …) and go into one brush set. Output:

```
output/
├── preview.png              detected stamps as numbered boxes (blue = captions left out, grey = specks)
│                            (one preview-<sheet>.png per sheet when there are several)
├── 01.png, 02.png, …        transparent stamps
├── brushes/01.brush, …      one Procreate brush per stamp
└── Autumn Stamps.brushset   all brushes in one set (named by --name)
```

Brushes are named after their PNG: `07.png` becomes "Autumn Stamps 07", `maple-leaf.png` becomes "Maple Leaf".

**Re-packaging edited stamps:** `--pack` skips detection and turns finished stamp PNGs (files or folders, previews ignored) into brushes, e.g. after deleting or renaming stamps:

```bash
python main.py --pack ./output --name "Autumn Stamps"
```

**Importing:** AirDrop the `.brushset` (or save it to Files and tap it) on the iPad; Procreate opens it and adds the set to the top of the Brush Library. If it arrives as `.zip`, rename it back to `.brushset`.

| Option | Default | Meaning |
|---|---|---|
| `--output`, `-o` | `./output` | Output folder |
| `--padding` | `20` | Margin around each object, in sheet pixels, before scaling |
| `--size` | `2048` | Square stamp size in pixels |
| `--min-area` | `100` | Fragments with fewer ink pixels are noise unless they almost touch an object |
| `--name` | sheet filename; `Stamps` for several sheets | Brush set name and brush name prefix |
| `--author` | | Author shown in each brush's About page |
| `--no-brushes` | | Export PNGs only |
| `--pack` | | Inputs are finished stamp PNGs: build brushes only |
| `--threshold` | `32` | How much darker than the paper (0–255) counts as ink |
| `--merge` | 0.5% of long side | Join fragments closer than this many px into one stamp |
| `--keep-text` | | Don't remove caption text |
| `--dry-run` | | Write the previews only |
| `--show` | | Open the previews and ask before exporting |

### Tuning

- **One drawing split into several stamps** (lettering, dotted wreaths, motion lines around a leaf): raise `--merge`, e.g. `--merge 40`. Sheets with tightly packed drawings need a smaller value than airy ones, so process those separately if needed.
- **A caption wasn't removed, or artwork was** (blue box in the preview): check the preview; use `--keep-text` to turn caption removal off.
- **Two drawings merged into one stamp**: lower `--merge`.
- **Faint or light-grey lines missed**: lower `--threshold`.
- **Paper texture detected as objects**: raise `--threshold` or `--min-area`.

## How it works

- **Paper colour** is estimated from the brightest quarter of the pixels, so cream or grey AI "paper" works as well as white.
- **Captions** ("1. Maple leaf" under a drawing) are removed before detection. Without OCR, a caption is recognised by layout: a row of small, varied pieces on a shared baseline, much wider than tall, with blank paper around it, and the same font size as the sheet's other captions. Lettering that is large, enclosed in a drawn frame, or part of the artwork is kept.
- **Detection** thresholds ink against the paper, groups nearby fragments by dilation, and labels connected groups. Pieces lying inside a drawing's outline (an eye, a pattern) join that drawing. Each stamp keeps only its own ink, so a neighbour poking into its bounding box isn't copied.
- **Background removal** is colour-to-alpha against the paper colour: anti-aliased edges and grey shading become partially transparent ink, not a light halo.
- **Ink level**: AI sheets rarely use pure black, so the sheet's solid ink level is measured and treated as fully opaque; grey shading stays proportionally lighter.
- **Resizing** fits the padded box's longer side to `--size` (preserving aspect ratio), centres it, and uses premultiplied Lanczos resampling. Stamps enlarged more than 4× are flagged as possibly soft.
- **Brushes** follow [docs/procreate-brush-format.md](docs/procreate-brush-format.md). `Brush.archive` carries all 172 settings of a real Procreate-exported stamp brush (`Star.brush`), with the same types and values, except "Use stamp preview" (on) and the starting size (50%). The shape is the stamp's alpha as white-on-black greyscale. A test compares generated archives against the real brush key by key.

## Project layout

```
main.py               CLI entry point
stampbyme/
  loader.py           load PNG/JPG → RGB array (EXIF, transparency, unicode paths)
  detect.py           paper estimate, ink mask, object grouping, reading order
  text.py             caption detection (layout-based, no OCR)
  process.py          colour-to-alpha, crop, centre, resize
  preview.py          numbered bounding-box preview
  export.py           01.png… naming and saving
  procreate.py        Brush.archive, Shape.png, .brush and .brushset writers
  cli.py              argument parsing and the pipeline
docs/
  procreate-brush-format.md   research notes for Phase 2
tests/                pytest suite (synthetic sheets with known geometry)
  reference/Star.brush  real Procreate export used to check generated brushes
```

## Tests

```bash
.venv\Scripts\python -m pytest
```
