# Procreate `.brush` / `.brushset` file format (research notes)

Researched 2026-10-01 for stampbyme (generating stamp brushes from black-ink-on-transparent PNGs).

**How this was researched.** Every statement below is backed by one of these:

- **[R] Real files.** Brushes exported by Procreate, downloaded from the Internet Archive and inspected with Python `zipfile` and `plistlib`:
  - 4 single `.brush` stamp brushes, created June 2020 (Procreate 5 era).
  - 3 `.brushset`s, with brushes created in 2020, 2022 and Feb 2024. The Feb 2024 brushes include the Procreate 5.2/5.3 3D-paint and hover keys.
- **[C] Open-source code.** Parsers and generators on GitHub/GitLab.
- **[D] Docs and tutorials.** Procreate Handbook and community tutorials.

Anything that is my own inference is marked **(inference)**. Anything nobody has confirmed is marked **(unverified)**.

> **Bottom-line confidence.**
> - **High** for the container layout, file names, the `Brush.archive` structure, the `brushset.plist` structure and the shape colour convention. These are all observed directly in Procreate-exported files.
> - **Medium** for the "minimal key set". Procreate clearly tolerates missing keys: three different key counts were seen in real files (52, 172 and 194–196). But I could not run an import on an iPad, so a generated file **must be test-imported on a device before shipping**.

---

## 1. Container format

### `.brush`

A plain **ZIP** archive with the extension `.brush`. The entries sit at the zip root, with no wrapping folder. [R][C]

This is what Procreate itself exported (`Star.brush`, created 2020-06-17):

```
Brush.archive                      deflate (method 8)
Shape.png                          deflate
Signature/SignaturePicture.png     deflate   (optional, author signature)
QuickLook/Thumbnail.png            deflate
```

Other entries seen in real Procreate exports:

| Entry (exact case) | Meaning | Required? |
|---|---|---|
| `Brush.archive` | Brush settings. NSKeyedArchiver **binary** plist (`bplist00`). | **Yes** |
| `Shape.png` | Custom shape (tip). Present iff `bundledShapePath` is `$null`. | Only when you use a custom shape |
| `Grain.png` | Custom grain (texture). Usually present iff `bundledGrainPath` is `$null`. | No. `Star.brush` has grain `$null` and **no** `Grain.png` [R] |
| `QuickLook/Thumbnail.png` | Brush-library stroke preview. RGBA, 1060×324 in every real export. | Present in every real file (treat as required) |
| `Signature/SignaturePicture.png` | "About this brush" signature. RGBA, e.g. 800×240. | No (absent in the 2022 Halftone Hospital set) |
| `AuthorPicture/AuthorPicture.png` | Author avatar | No |
| `Reset/…` | A full copy of the brush (`Reset/Brush.archive`, `Reset/Shape.png`, …), used by "Reset brush". | No (absent in the 2022 set) |
| `Sub01/…` | Second brush of a **dual brush** (`Sub01/Brush.archive`, `Sub01/Shape.png`, …). | No |

ZIP details observed in Procreate exports [R]:

- Compression is **deflate** (method 8) for every entry, including PNGs.
- General-purpose flag `0x6`, which is the "maximum compression" bits.
- `create_system` is 0.
- There are **no directory entries**: `QuickLook/` does not appear as its own entry.

A third-party generator (davenquinn/geologic-patterns, built with Python `shutil.make_archive`) wrote these differently, and its brushes were publicly distributed (2017 release) [C][R]:

- a `QuickLook/` directory entry,
- `create_system` 3 (Unix),
- flag 0.

So none of these ZIP details seem to matter **(inference, not device-tested)**. Stored (method 0) entries were not observed in Procreate's own files. Deflate is the safe choice.

### `.brushset`

Also a plain **ZIP**. It has one folder per brush, named by an **uppercase UUID**, plus `brushset.plist` at the root [R][C]. From the 2022 "Tone Scrapers" set:

```
brushset.plist
0275F36B-030E-40C3-9498-63820AF2A7DA/Grain.png
0275F36B-030E-40C3-9498-63820AF2A7DA/Brush.archive
0275F36B-030E-40C3-9498-63820AF2A7DA/Shape.png
0275F36B-030E-40C3-9498-63820AF2A7DA/QuickLook/Thumbnail.png
136A0AB8-1F14-4B2B-BDF1-B5BFF5D0CAB9/Grain.png
136A0AB8-1F14-4B2B-BDF1-B5BFF5D0CAB9/Brush.archive
...
```

Each UUID folder has exactly the same contents as a standalone `.brush`, including optional `Reset/`, `Sub01/`, `Signature/` and `AuthorPicture/` subfolders.

- `brushset.plist` can be the first or the last zip entry; both orders were seen [R].
- One real, distributed set (All-Star) even contains a stray `…/Reset/Signature/.DS_Store`. This suggests Procreate ignores unknown files **(inference)**.
- Still, do **not** add `__MACOSX/` or `.DS_Store` entries.

Readers find members via `brushset.plist` → `brushes` [C: freyalupen converter, `ProcreateBrushSetParser.findBrushPaths`]. Brushkit also falls back to "every top-level dir containing `<dir>/Brush.archive`" [C].

---

## 2. `Brush.archive`

**Format: NSKeyedArchiver archive, written as a binary plist** (`bplist00`). This holds in every Procreate export [R].

- The top-level dict is `{"$version": 100000, "$archiver": "NSKeyedArchiver", "$top": {"root": UID(1)}, "$objects": [...]}`.
- `$objects[0]` is the string `"$null"`.
- `$objects[1]` is the root brush dict. Every reader (freyalupen, brushkit, Brush-Converter) hard-codes index 1 [C], so **keep the root at index 1**.

### Root class

```python
{"$classname": "SilicaBrush", "$classes": ["SilicaBrush", "ValkyrieBrush", "NSObject"]}
```

This is the class record in every Procreate 5-era export (2020, 2022, 2024) [R].

The older (2017, Procreate 4-era) davenquinn template uses `["SilicaBrush", "NSObject"]` [C]. A generator in groot99-droid/Pipelines-Plugin uses the class name `MCBrush`. Its own docstring says it "was never confirmed to import", so **do not use `MCBrush`**.

### Value encoding inside the root dict

- **Numbers and booleans are inline.** Floats are written as plist reals, e.g. `plotSpacing = 2.0`. Integers are plist ints: `version`, `blendMode`, `shapeOrientation`, `shapeFilterMode`, `textureApplication`, `plotSpacingVersion`, `taperVersion`, `grainBlendMode`, `grainOrientation`, `extendedBlend`, `burntEdgesBlendMode`, `dualBlendMode`, `hoverFill`, `hoverOutline`.
- **Strings, data, dates, arrays and curves** are separate objects referenced with `UID(n)`:
  - `name` → `UID` → `"Star"`.
  - `authorName` → `UID` → `"Ghost"`, or `UID(0)` when there is no author.
  - `bundledShapePath` / `bundledGrainPath` → `UID(0)` (`$null`) **means "use the embedded `Shape.png` / `Grain.png`"**. A string means a built-in Procreate source image, e.g. `"Brush-Preset-Medium-Hard.png"` or `"Brush-Artery-Noise.jpg"`. Confirmed by the freyalupen converter ("seems to load embedded Shape.png unless otherwise specified") and by every sample: `$null` always coincides with an embedded file being present.
  - `color` → `UID` → 16 bytes of data (all zero in every sample).
  - `creationDate` → `UID` → `{"NS.time": <seconds since 2001-01-01>, "$class": UID(→NSDate class)}`.
  - `dynamicsPressure*Curve` → `UID` → `{"points": UID(→array), "$class": UID(→ValkyrieMagnitudinalCurve)}`.
    - The array is `{"NS.objects": [UID("{0.000000, 0.000000}"), UID("{1.000000, 1.000000}")], "$class": UID(→NSMutableArray)}`.
    - The points are **strings** in CGPoint string format.
  - `savedPaintSizes` etc. (2024 files) → `UID` → `{"NS.objects": [], "$class": UID(→NSArray)}`.
- Class records look like `{"$classname": X, "$classes": [X, ..., "NSObject"]}`. Procreate stores each class record once and reuses its UID.
- Object order in `$objects` doesn't need to match Procreate's. Only index 0 (`$null`) and index 1 (root) are conventional [C].

### Key sets observed (version drift)

| Source | Created | `version` | # root keys |
|---|---|---|---|
| davenquinn template (third-party, 2017) | – | absent | 52 |
| Ghost stamp brushes (`Star`, `Heart`, `Fox`, `Circle`) | 2020-06 | 2 | 172 |
| All-Star brushset | 2020-12 | 2 | 172 |
| Halftone Hospital "Tone Scrapers" | 2022-06 | 2 | 194 |
| padivv Lineart set | 2024-02 | 2 | 196 (+ `hover*`, `metallic*`, `roughness*`, `height*`, `saved*`, `texturizedGrainFollowsCamera`, `plotFFT*`, `plotMovingAverageStabilization`) |

Key sets grow with app versions, and no key was ever removed. Procreate reads older files that lack the newer keys, which is backward compatibility the app must have for brushes distributed since 2020. So **absent keys fall back to defaults (inference, strongly supported)**.

I found no public source covering anything newer than Procreate 5.3/5X (e.g. a hypothetical Procreate 6 brush engine) as of late 2026. **Unverified** whether any newer app version changed the format.

The complete key list is in Appendix A, with real values from a Procreate stamp brush and a 2024 brush.

### Key meanings (from the aumlette-lab decoder schema v1.7 [C], cross-checked against real values)

| Brush Studio UI | Key | Raw range → UI |
|---|---|---|
| Stroke path › Spacing | `plotSpacing` | 0–2.0 → 0–100%, UI ≈ `72.943·raw^0.4558`, so **2.0 = 100% (max)** |
| Stroke path › Spacing jitter | `plotSpacingJitter` | 0–10 |
| Stroke path › Jitter lateral / linear | `plotJitter` / `plotJitterLongitudinal` | 0–13.78 → 0–200% |
| Stroke path › Fall off | `dynamicsFalloff` | 0–1 |
| StreamLine | `plotSmoothing` | 0–1 |
| Shape › Rotation | `shapeRotation` | −1…1 → −100…100% (stamp rotation offset; 100% = follow stroke) |
| Shape › Scatter | `shapeScatter` | 0–2 |
| Shape › Count / count jitter | `shapeCount` / `shapeCountJitter` | count: raw 1.0 in real single-stamp brushes (decoder says ×16; treat as unclear, keep 1.0) |
| Shape › Randomized / Flip X / Flip Y | `shapeRandomise`, `shapeFlipXJitter`, `shapeFlipYJitter` | bool |
| Shape › Input style | `shapeAzimuth`(+`shapeRoll` in some versions) | False = touch-only |
| Shape › Roundness / Angle | `shapeRoundness` (1 = no distortion), `shapeAngle` (radians) | |
| Shape › Filtering | `shapeFilter` + `shapeFilterMode` | True+0 = Improved, True+1 = Classic, False = none |
| Shape › (invert) | `shapeInverted` | bool, see §4 |
| Grain › Moving/Texturized | `textureApplication` | 0 = Moving, 1 = Texturized |
| Grain › Movement / Scale / Zoom / Rotation | `textureMovement`, `textureScale` (0–16), `textureZoom`, `textureRotation` | |
| Grain › Depth / min / jitter | `grainDepth`, `grainDepthMinimum`, `grainDepthJitter` | |
| Grain › Offset jitter | `textureOffsetJitter` | bool |
| Grain › Blend mode | `grainBlendMode` (+`grainBlendModeExtended`) | 1 = Multiply |
| Grain › (invert) | `textureInverted` | bool |
| Rendering › mode | `renderingRecursiveMixing`, `renderingModulatedTransfer`, `renderingMaxTransfer` | all False = Intense Glaze; (F,F,T) = Light Glaze |
| Rendering › Flow | `dynamicsGlazedFlow` | 0–1 |
| Rendering › Blend | `blendMode` (+`extendedBlend`) | 0 = Normal |
| Dynamics › Jitter size / opacity | `dynamicsJitterSize`, `dynamicsJitterOpacity` | |
| Dynamics › Speed size / opacity | `dynamicsSpeedSize`, `dynamicsSpeedOpacity` | |
| Pencil › Pressure size / opacity / flow | `dynamicsPressureSize`, `dynamicsPressureOpacityTransfer`, `dynamicsPressureOpacity` | |
| Pencil › Tilt | `dynamicsTiltAngle`, `dynamicsTiltSize`, `dynamicsTiltOpacity`, … | |
| Properties › Use stamp preview | `stamp` | bool |
| Properties › Orient to screen | `oriented` | bool |
| Properties › Preview size | `previewSize` | 0–1 |
| Properties › Max / Min size | `maxSize` / `minSize` | 0–16 (×100 = %); real files have 0.62, 0.656, 1.0, **2.41** |
| Properties › Max / Min opacity | `maxOpacity` / `minOpacity` | 0–1 |
| Current slider size / opacity | `paintSize`, `paintOpacity` (also `eraseSize`, `smudgeSize`, …) | 0–1 slider position |
| About › name / author / date | `name`, `authorName`, `creationDate` | |
| Taper (touch) | `taperStartLength`, `taperEndLength`, `taperSize`, `taperOpacity`, `taperShape`, `taperSizeLinked` | |
| Taper (pencil) | `pencilTaper*`, `taperPressure`, `pencilTipAnimation` | |
| Format versioning | `version` (2), `plotSpacingVersion` (1; one 2020 brush had 0), `taperVersion` (1) | |

### Sensible values for a stamp brush

These come from the real Procreate-exported **`Star.brush` stamp** [R], plus the decoder semantics:

| Key | Value | Why |
|---|---|---|
| `plotSpacing` | `2.0` | Max spacing (100%). The real Star/Heart/Fox stamps all use 2.0. |
| `plotSpacingVersion` | `1` | As in the stamp samples. |
| `plotJitter`, `shapeScatter`, `shapeRotation`, `dynamicsJitterSize`, `dynamicsJitterOpacity`, `dynamicsFalloff`, `plotSmoothing` | `0.0` | No jitter, no rotation. |
| `shapeRandomise`, `shapeAzimuth`, `shapeFlipXJitter`, `shapeFlipYJitter` | `False` | Stamp stays upright. |
| `shapeCount` | `1.0` | One stamp per dab. |
| `shapeOrientation` | `1` | As in all samples. |
| `oriented` | `True` | As in all samples (Orient to screen). |
| `bundledShapePath` | `UID(0)` (`$null`) | Use the embedded `Shape.png`. |
| `bundledGrainPath` | `UID(0)` and **no `Grain.png`** | Exactly what `Star.brush` does: no grain texture. Alternatively ship an all-white `Grain.png` **(inference: white grain = no texture modulation)**. |
| `textureScale`, `textureZoom`, `textureMovement`, `grainDepth` | `1.0` | Star.brush values. |
| `dynamicsPressureSize`, `dynamicsPressureOpacity` | `0.0` | Uniform stamp regardless of pressure (Star.brush). |
| `dynamicsPressureOpacityTransfer`, `dynamicsGlazedFlow`, `paintOpacity`, `maxOpacity` | `1.0` | Fully opaque. |
| `maxSize` | `1.0` (or larger, up to 16) | `1.0` = 100%. Raise it (e.g. `2.0`–`4.0`) so the size slider can make the stamp larger; a real 2020 brush ships `2.41`. **Unverified:** exact pixel size per %. |
| `minSize` | `0.0` | |
| `paintSize` | e.g. `0.5` | Slider start position. Star.brush ships `0.099`. |
| `stamp` | `True` | Shows a stamp preview in the library (Star.brush had False; True is a cosmetic choice). |
| `taper*`, `pencilTaper*` | `0.0` | No taper on a single tap. |
| `blendMode` / `extendedBlend` | `0` | Normal. |
| `version` | `2` | Every Procreate 5-era export. |

---

## 3. `brushset.plist`

An **XML** plist in every real sample, though readers use `plistlib.load`, which accepts both formats [R][C]:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
	<key>brushes</key>
	<array>
		<string>0275F36B-030E-40C3-9498-63820AF2A7DA</string>
		<string>136A0AB8-1F14-4B2B-BDF1-B5BFF5D0CAB9</string>
	</array>
	<key>name</key>
	<string>Tone Scrapers</string>
</dict>
</plist>
```

- `name` (string) is the set title shown in the Brush Library.
- `brushes` (array of strings) gives the folder names, **in display order**. These are uppercase UUIDs in all samples.
- No other keys appear in any sample. Python: `plistlib.dumps({"brushes": ids, "name": title}, fmt=plistlib.FMT_XML)`.
- The file name is all lowercase, `brushset.plist`. Brushkit issue #152 describes an odd set with `Brushset.plist` and `<UUID>.brush/` folders from an unknown tool. Procreate support for that layout is unknown, so don't copy it.

---

## 4. Shape and grain image requirements

### Convention: **white = paint, black = transparent**, grayscale

- **Real exports [R]:**
  - `Shape.png` is **8-bit grayscale (`L`), no alpha**, with an embedded Apple "GRAY" ICC profile.
  - The background is black (corner pixel 0) and the shape is white (e.g. Star, Heart and Fox centre ≈ 253).
  - Procreate's built-in source images (extracted in tohsakrat/Brush-Converter `Images/`) follow the same pattern: `L` mode, black background.
- **Brushkit [C]:** "Decode a Procreate `Shape.png` … White is stamp coverage, so the luminance is taken as-is."
- **Tutorials [D]:**
  - Designs "need to be white on a black background".
  - "Procreate uses white for the solid stamp and black for transparency."
  - "If you don't invert your image … your brush will be squared with your shape being empty." In-app, a two-finger tap in the Shape Editor inverts the image.
- **davenquinn generator [C]:** "Brush Grain image needs to be inverted so inked parts are white". It flattens alpha onto white, then inverts.
- **`shapeInverted` [R]:** the All-Star "Glitter Brush" stores a mostly-white `Shape.png` (mean 233) with `shapeInverted = True`. So Procreate keeps the image as imported and applies inversion via the flag. Either approach works, but **white-on-black with `shapeInverted = False` is the common case**: Star, Heart, Fox and Tone Scraper all do this.

### Conversion needed for our black-ink-on-transparent PNGs

1. Compute coverage per pixel: `coverage = alpha × (255 − luminance) / 255`.
   - Opaque black ink → 255 (white).
   - Transparent → 0 (black).
   - Anti-aliased edges and grey ink keep partial values.
   - Do **not** just take the RGB channels: transparent pixels are often stored as RGB (0,0,0), which would read as ink.
2. Optionally crop to the bounding box.
3. Scale **up or down** to fit a square, with a small margin (~5%).
4. Paste centred on a black square.
5. Save as a single-channel `L` PNG (no alpha). The ICC profile is optional (inference: third-party brushes without one were distributed).

Recommended size: **2048×2048**.
- All Procreate 5 stamp exports and the built-in sources are 2048×2048.
- One real 2022 brush uses 1002×1002, and the davenquinn grain is 921×921, so non-2048 and non-power-of-two sizes are accepted.
- Keep the image square. I found no documented hard maximum. 2048 is the observed ceiling **(unverified as a limit)**.

### Grain

- Also grayscale. Real grains are `L` 2048×2048. The davenquinn generator used RGB 921×921.
- Multiply grain blend (`grainBlendMode = 1`): white = full paint and dark = less paint. This matches Procreate's own phrasing for material sources: "white areas … allow …, dark or black areas … block" [D, Handbook].
- For a clean stamp, either omit `Grain.png` entirely as `Star.brush` does, or ship a solid-white square **(inference)**.

### Thumbnail

`QuickLook/Thumbnail.png` in real exports is an **RGBA 1060×324** stroke preview on a transparent background. Third-party generators used other sizes (921×921 RGBA, or the shape itself). The thumbnail is a library preview, and Procreate likely regenerates it **(unverified)**. A reasonable choice is a 1060×324 RGBA image with the stamp drawn in white or black, centred.

---

## 5. Minimal import-safe recipe and pitfalls

### Recommended minimal file set (per brush)

```
Brush.archive            (binary NSKeyedArchiver plist, root SilicaBrush at $objects[1])
Shape.png                (L-mode, white-on-black, 2048x2048)
QuickLook/Thumbnail.png  (RGBA preview)
[Grain.png]              (optional; omit with bundledGrainPath = $null, as Star.brush does)
```

This combination (no `Grain.png`, no `Reset/`), plus an optional `Signature/SignaturePicture.png`, is exactly how the four Ghost stamp brushes ship [R]. The 2022 Halftone Hospital set ships only `Brush.archive`, `Shape.png`, `Grain.png` and `QuickLook/Thumbnail.png` per brush [R].

### Keys

- **Safest:** emit the full key set with stamp values, i.e. Appendix A, column "Star".
- **Smaller:** the example below emits about 85 keys. The 52-key davenquinn file was publicly distributed, which suggests Procreate fills in defaults, but that file was built for Procreate 4 **(unverified for Procreate 5.x)**.
- Always include:
  - `name` (UID → string), `version` (2), `$class`
  - `bundledShapePath`, `bundledGrainPath`
  - `plotSpacing`, `paintSize`, `maxSize`, `minSize`, `paintOpacity`, `maxOpacity`, `minOpacity`
  - the `shape*` and `texture*` keys you care about

### Pitfalls (with evidence level)

- **Binary, not XML, for `Brush.archive`.** Procreate always writes `bplist00` [R]. davenquinn explicitly converts XML → `binary1` with `plutil` [C]. Brushkit #152 shows an XML/flat `Brush.archive` set of unknown provenance and unknown importability [C]. Use `plistlib.dumps(..., fmt=plistlib.FMT_BINARY)`.
- **Use real `plistlib.UID` objects** for references. Never write plain ints or `{"CF$UID": n}` dicts in binary output. plistlib writes UIDs natively in Python ≥ 3.8 [C: Pipelines-Plugin note "written with plistlib so its object table and UIDs are right"].
- **Root at `$objects[1]`**, and `$top = {"root": UID(1)}` [R][C].
- **Strings must be UID-referenced objects**, not inline. In particular `$null` is `UID(0)`, never the literal string inline [R].
- **Class name must be `SilicaBrush`** [R]. Don't invent class names (`MCBrush` is unconfirmed).
- **Zip layout:**
  - Entries go at the archive root for `.brush`. Do **not** zip a containing folder.
  - Use forward-slash paths.
  - No `__MACOSX/` and no AppleDouble `._*` files. Procreate's own exports never contain them **(inference that they would hurt; not verified)**.
  - Use deflate.
- **File extension matters to iOS.** A `.brushset` renamed to `.zip` will not open in Procreate until renamed back [D: GeorgBrush troubleshooting].
- **Case-sensitive names:** `Brush.archive`, `Shape.png`, `Grain.png`, `QuickLook/Thumbnail.png`, `brushset.plist` [R].
- **UUID folder names** must match the `brushes` entries exactly. Generate uppercase `uuid4` values, unique per brush. Re-importing the same UUID probably dedupes or overwrites **(unverified)**.
- **No `bundledBrushName` key exists** in any real file. The relevant keys are `bundledShapePath` and `bundledGrainPath`.
- **`plotSpacing` is not a percentage.** 2.0 raw is the 100% UI maximum. Values above 2.0 are outside the UI range **(behaviour unverified)**.

---

## 6. Concrete minimal `Brush.archive` (plistlib)

Abstract shape of the archive (indices are illustrative):

```python
{
  "$version": 100000,
  "$archiver": "NSKeyedArchiver",
  "$top": {"root": UID(1)},
  "$objects": [
    "$null",                                   # 0
    {                                          # 1  root SilicaBrush
      "$class": UID(17),
      "name": UID(2),
      "authorName": UID(0),                    # none
      "color": UID(3),
      "creationDate": UID(15),
      "bundledShapePath": UID(0),              # -> embedded Shape.png
      "bundledGrainPath": UID(0),              # -> embedded Grain.png (or none)
      "dynamicsPressureSizeCurve": UID(8),
      "version": 2, "plotSpacing": 2.0, "plotSpacingVersion": 1,
      "maxSize": 1.0, "minSize": 0.0, "paintSize": 0.5, "stamp": True,
      # ... more inline reals / bools / ints ...
    },
    "My Stamp",                                # 2
    b"\x00" * 16,                              # 3  color
    "{0.000000, 0.000000}",                    # 4
    "{1.000000, 1.000000}",                    # 5
    {"$classname": "NSMutableArray", "$classes": ["NSMutableArray", "NSArray", "NSObject"]},  # 6
    {"NS.objects": [UID(4), UID(5)], "$class": UID(6)},                                      # 7
    {"points": UID(7), "$class": UID(9)},                                                    # 8 curve
    {"$classname": "ValkyrieMagnitudinalCurve", "$classes": ["ValkyrieMagnitudinalCurve", "NSObject"]},  # 9
    # ...
    {"NS.time": 812345678.0, "$class": UID(16)},                                             # 15
    {"$classname": "NSDate", "$classes": ["NSDate", "NSObject"]},                            # 16
    {"$classname": "SilicaBrush", "$classes": ["SilicaBrush", "ValkyrieBrush", "NSObject"]}, # 17
  ],
}
```

The runnable reference generator below was smoke-tested in this research only for plist and zip round-trip. Its structure, class records and value types match the Procreate exports. **It has NOT been import-tested on an iPad.**

```python
"""Reference sketch: build a stamp .brush / .brushset with plistlib + zipfile.
Structure mirrors real Procreate-exported files (see docs/procreate-brush-format.md).
NOT import-tested on an iPad."""
import io, plistlib, uuid, zipfile, datetime
from PIL import Image

UID = plistlib.UID

def make_brush_archive(name: str, author: str | None = None) -> bytes:
    objects = ["$null"]          # index 0 is always the $null sentinel

    def add(obj):
        objects.append(obj)
        return UID(len(objects) - 1)

    root = {}
    objects.append(root)         # index 1 = root SilicaBrush (what $top.root points to)

    # --- class records -------------------------------------------------------
    cls_curve = None
    cls_array = None

    def curve():
        """Linear 0..1 ValkyrieMagnitudinalCurve, identical to what Procreate writes."""
        nonlocal cls_curve, cls_array
        p0 = add("{0.000000, 0.000000}")
        p1 = add("{1.000000, 1.000000}")
        if cls_array is None:
            cls_array = add({"$classname": "NSMutableArray",
                             "$classes": ["NSMutableArray", "NSArray", "NSObject"]})
        arr = add({"NS.objects": [p0, p1], "$class": cls_array})
        if cls_curve is None:
            cls_curve = add({"$classname": "ValkyrieMagnitudinalCurve",
                             "$classes": ["ValkyrieMagnitudinalCurve", "NSObject"]})
        return add({"points": arr, "$class": cls_curve})

    root.update({
        # identity
        "name": add(name),
        "authorName": add(author) if author else UID(0),
        "version": 2,
        "color": add(b"\x00" * 16),
        # images: $null => use embedded Shape.png / Grain.png
        "bundledShapePath": UID(0),
        "bundledGrainPath": UID(0),
        # stroke path: max spacing => one stamp per tap / widely spaced stamps
        "plotSpacing": 2.0,
        "plotSpacingVersion": 1,
        "plotJitter": 0.0,
        "plotSmoothing": 0.0,
        "dynamicsFalloff": 0.0,
        # shape: no rotation / scatter / randomisation
        "shapeRotation": 0.0,
        "shapeScatter": 0.0,
        "shapeCount": 1.0,
        "shapeCountJitter": 0.0,
        "shapeRandomise": False,
        "shapeAzimuth": False,
        "shapeFlipXJitter": False,
        "shapeFlipYJitter": False,
        "shapeOrientation": 1,
        "shapeInverted": False,
        "shapeRoundness": 1.0,
        "shapeAngle": 0.0,
        "shapeFilter": True,
        "shapeFilterMode": 0,
        "oriented": True,
        # grain: neutral
        "textureScale": 1.0,
        "textureZoom": 1.0,
        "textureMovement": 1.0,
        "textureRotation": 0.0,
        "textureInverted": False,
        "textureApplication": 0,
        "textureFilter": True,
        "textureFilterMode": 0,
        "textureOrientation": 1,
        "textureOffsetJitter": False,
        "grainDepth": 1.0,
        "grainDepthMinimum": 0.0,
        "grainDepthJitter": 0.0,
        "grainBlendMode": 1,
        "grainOrientation": 1,
        # dynamics: none
        "dynamicsJitterSize": 0.0,
        "dynamicsJitterOpacity": 0.0,
        "dynamicsPressureSize": 0.0,
        "dynamicsPressureOpacity": 0.0,
        "dynamicsPressureOpacityTransfer": 1.0,
        "dynamicsSpeedSize": 0.0,
        "dynamicsSpeedOpacity": 0.0,
        "dynamicsGlazedFlow": 1.0,
        "dynamicsMix": 0.0,
        "dynamicsLoad": 0.5,
        "dynamicsTiltSize": 0.0,
        "dynamicsTiltOpacity": 0.0,
        "dynamicsTiltAngle": 0.1,
        "dynamicsPressureSizeCurve": curve(),
        "dynamicsPressureOpacityCurve": curve(),
        # taper: none
        "taperStartLength": 0.0, "taperEndLength": 0.0, "taperSize": 0.0, "taperOpacity": 0.0,
        "pencilTaperStartLength": 0.0, "pencilTaperEndLength": 0.0,
        "pencilTaperSize": 0.0, "pencilTaperOpacity": 0.0,
        "taperVersion": 1,
        # rendering
        "blendMode": 0,
        "extendedBlend": 0,
        "renderingMaxTransfer": False,
        "renderingModulatedTransfer": False,
        "renderingRecursiveMixing": False,
        # properties
        "paintSize": 0.5,
        "paintOpacity": 1.0,
        "maxSize": 1.0,
        "minSize": 0.0,
        "maxOpacity": 1.0,
        "minOpacity": 0.0,
        "eraseSize": 0.5, "eraseOpacity": 1.0,
        "smudgeSize": 0.5, "smudgeOpacity": 0.8,
        "stamp": True,          # "Use stamp preview" in the brush library
        "previewSize": 0.3,
        "importedFromABR": False,
    })
    date_cls = add({"$classname": "NSDate", "$classes": ["NSDate", "NSObject"]})
    secs = (datetime.datetime.now(datetime.timezone.utc)
            - datetime.datetime(2001, 1, 1, tzinfo=datetime.timezone.utc)).total_seconds()
    root["creationDate"] = add({"NS.time": secs, "$class": date_cls})
    root["$class"] = add({"$classname": "SilicaBrush",
                          "$classes": ["SilicaBrush", "ValkyrieBrush", "NSObject"]})

    archive = {"$version": 100000, "$archiver": "NSKeyedArchiver",
               "$top": {"root": UID(1)}, "$objects": objects}
    return plistlib.dumps(archive, fmt=plistlib.FMT_BINARY, sort_keys=False)


def shape_from_black_on_transparent(png: Image.Image, size: int = 2048, pad: float = 0.05) -> bytes:
    """Black-ink-on-transparent RGBA -> Procreate Shape.png (L mode, white = paint, black = empty)."""
    im = png.convert("RGBA")
    lum = im.convert("L")
    alpha = im.getchannel("A")
    # coverage = alpha * darkness ; pure black opaque ink -> 255, transparent -> 0
    from PIL import ImageChops, ImageOps
    cover = ImageChops.multiply(alpha, ImageOps.invert(lum))
    bbox = cover.getbbox()
    if bbox:
        cover = cover.crop(bbox)
    inner = int(size * (1 - 2 * pad))
    scale = inner / max(cover.width, cover.height)   # up- or down-scale to fill the square
    cover = cover.resize((max(1, round(cover.width * scale)), max(1, round(cover.height * scale))),
                         Image.LANCZOS)
    canvas = Image.new("L", (size, size), 0)
    canvas.paste(cover, ((size - cover.width) // 2, (size - cover.height) // 2))
    out = io.BytesIO()
    canvas.save(out, "PNG")
    return out.getvalue()


def write_brush_entries(zf: zipfile.ZipFile, prefix: str, archive: bytes, shape: bytes, thumb: bytes):
    zf.writestr(prefix + "Brush.archive", archive)
    zf.writestr(prefix + "Shape.png", shape)
    zf.writestr(prefix + "QuickLook/Thumbnail.png", thumb)


def make_brushset(title: str, brushes: list[tuple[str, bytes, bytes]]) -> bytes:
    buf = io.BytesIO()
    ids = []
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, shape, thumb in brushes:
            bid = str(uuid.uuid4()).upper()
            ids.append(bid)
            write_brush_entries(zf, bid + "/", make_brush_archive(name), shape, thumb)
        zf.writestr("brushset.plist", plistlib.dumps({"brushes": ids, "name": title},
                                                     fmt=plistlib.FMT_XML))
    return buf.getvalue()


if __name__ == "__main__":
    # smoke test: synthetic black star on transparent
    from PIL import ImageDraw
    src = Image.new("RGBA", (600, 400), (0, 0, 0, 0))
    ImageDraw.Draw(src).ellipse((100, 50, 500, 350), fill=(0, 0, 0, 255))
    shape = shape_from_black_on_transparent(src)
    thumb = io.BytesIO(); src.save(thumb, "PNG")
    data = make_brushset("Test Set", [("Stamp A", shape, thumb.getvalue()),
                                      ("Stamp B", shape, thumb.getvalue())])
    open("test.brushset", "wb").write(data)
    single = io.BytesIO()
    with zipfile.ZipFile(single, "w", zipfile.ZIP_DEFLATED) as zf:
        write_brush_entries(zf, "", make_brush_archive("Stamp A"), shape, thumb.getvalue())
    open("test.brush", "wb").write(single.getvalue())
    print("ok")
```

---

## 7. Sources

| # | Source | What I took from it |
|---|---|---|
| R1 | Internet Archive item `GhostFoxProBrush`: https://archive.org/details/GhostFoxProBrush (downloaded `Star.brush`, `Heart.brush`, `Circle.brush`, `Fox.brush`) | Procreate-exported **stamp** brushes (created 2020-06). Zip layout, deflate/flags, 172-key `Brush.archive`, root class `SilicaBrush`/`ValkyrieBrush`, curve/date encoding, stamp values (`plotSpacing` 2.0, no jitter), no `Grain.png` with grain `$null`, Shape.png L 2048² white-on-black, thumbnail 1060×324 RGBA |
| R2 | Internet Archive item `all-star`: https://archive.org/details/all-star (`All-Star.brushset`; central directory, `brushset.plist` and 2 brushes fetched via HTTP range requests) | `.brushset` layout (UUID folders, `Reset/`, `Sub01/`, `Signature/`, `AuthorPicture/`, stray `.DS_Store`), XML `brushset.plist` with `brushes` + `name`, `shapeInverted = True` with a white-background shape, `maxSize` 2.41, built-in names like `Brush-Artery-Noise.jpg` |
| R3 | Internet Archive item `padivv_Lineart_Set`: https://archive.org/details/padivv_Lineart_Set | 2024-created brushes, 196 keys (3D/hover/saved* keys), `version` still 2, `brushset.plist` placed last, built-in shape/grain names |
| R4 | Internet Archive item `halftone-hospital-basic-tone-kit` (`…Tone_Scrapers.brushset`, partial range fetch): https://archive.org/details/halftone-hospital-basic-tone-kit | Minimal real set (Brush.archive, Shape.png, Grain.png, QuickLook/Thumbnail.png only), 194 keys, 1002×1002 shape, `textureInverted` |
| C1 | davenquinn/geologic-patterns `procreate-brushes/create-brushes` + `template/Brush.archive`: https://github.com/davenquinn/geologic-patterns/tree/master/procreate-brushes and release zip https://github.com/davenquinn/geologic-patterns/releases/tag/v1.0.0 | Third-party generator: XML template → `plutil -convert binary1`, 52-key archive, invert-so-ink-is-white comment, `bundledShapePath = "Brush-Preset-Medium.png"` + embedded Grain, `shutil.make_archive` zip accepted for distribution |
| C2 | Freya Lupen, Procreate to Krita Brush Converter: https://invent.kde.org/freyalupen/procreate-to-krita-brush-converter (`procreate/procreate_brush_parser.py`, `procreate_to_kpp.py`) | `brushset.plist['brushes']` lookup, `$objects[1]` root, `Sub01` dual brush, `$null` → embedded Shape.png, list of keys incl. `stamp`, `maxSize`, `shapeInverted`, `version`, `savedPaintSizes` |
| C3 | aumlette-lab/procreate-brush-decoder schema `src/data/procreate-brush-decoder-v1.7.json`: https://github.com/aumlette-lab/procreate-brush-decoder | UI ↔ key mapping and raw ranges/formulas (spacing 0–2, max size 0–16, stamp preview, filter modes, rendering modes, blend codes) |
| C4 | pmwoz/brushkit `crates/preview/src/procreate.rs`: https://github.com/pmwoz/brushkit | "White is stamp coverage" for Shape.png, `brushset.plist` = `name` + `brushes`, `Reset/` not a member, census note (5803 real archives ≤ 10 KB) |
| C5 | pmwoz/brushkit issue #152: https://github.com/pmwoz/brushkit/issues/152 | Odd XML/flat `Brush.archive` variant of unknown origin. A warning, not a model |
| C6 | tohsakrat/Brush-Converter `brushset-parser.py` + `Images/`: https://github.com/tohsakrat/Brush-Converter | Skips `Reset` entries, `bundled*Path` → built-in images; built-in shape images are L-mode black-background 2048² / 1024² |
| C7 | groot99-droid/Pipelines-Plugin `studio/pipeline/brush_pack.py`: https://github.com/groot99-droid/Pipelines-Plugin | **Counter-example.** Uses class `MCBrush` and invented `brush*` keys, and states it was never confirmed to import. Only the plistlib/UID technique is reusable |
| C8 | dymokomi/luce-procreate README: https://github.com/dymokomi/luce-procreate | Confirms the zip + NSKeyedArchiver + Shape/Grain/QuickLook layout and the `bundledShapePath`/`bundledGrainPath` meaning |
| D1 | Procreate Handbook, Brush Studio Settings: https://help.procreate.com/procreate/handbook/brushes/brush-studio-settings (and 5.0 version) | Meaning of Spacing, Max/Min size, Stamp preview, Orient to screen; white-passes/black-blocks wording for material sources |
| D2 | Krita Artists thread "Procreate brush import plugin prototype": https://krita-artists.org/t/procreate-brush-import-plugin-prototype/104894 | Brushes are zip archives with preview, tip, texture, author picture, signature and a bplist `Brush.archive` |
| D3 | Stamp-brush tutorials (search results summarising designbundles.net, stringlabscreative.com, leilaandpo.studio, adventureswithart.com) | "White = solid stamp, black = transparency", two-finger-tap invert, 3000 px canvas suggestion |
| D4 | GeorgBrush.club ZIP troubleshooting: https://www.georgbrush.club/blog/2020/5/9/zip-file-troubleshooting-installing-procreate-brushes | `.brushset` downloaded as `.zip` must be renamed back to import |

### Uncertain or unverified

1. **No on-device import test was possible.** The generated structure mirrors real files, but someone must import a generated `.brush` and `.brushset` in current Procreate before release.
2. Whether a reduced key set (~85 keys) imports cleanly in Procreate 5.3+/5X. It is very likely, given 52/172/194/196-key files all exist in the wild, but unverified.
3. Whether anything after Procreate 5.3 (late-2026 app versions) changed the brush format. No public evidence found either way.
4. Maximum `Shape.png` resolution. 2048² is observed in Procreate's own files, not a documented limit.
5. Whether an absent `Grain.png` with `bundledGrainPath = $null` renders as "no grain" (Star.brush does exactly this, so it is very likely) or whether a white Grain.png is preferable.
6. The exact meaning of `shapeCount` raw scale (decoder ×16 vs. real value 1.0), and of `plotSpacingVersion` 0 vs 1.
7. Whether Procreate tolerates zip directory entries, Unix `create_system`, or stored PNGs. The davenquinn file had the first two and was distributed; stored entries were never observed.

---

## Appendix A — every root key seen, with real values

- **"Star"** is Procreate-exported `Star.brush` (stamp, 2020, 172 keys).
- **"padivv 2024"** is a 2024 lineart brush (196 keys).
- `-` means the key is absent in that file.
- Curves are all linear `{0,0}→{1,1}`.

| Key | Star (stamp, 2020) | padivv 2024 |
|---|---|---|
| `attackTilt` | False | False |
| `attackTiltAngle` | 0.1 | 0.1 |
| `authorName` | 'Ghost' | 'Padi' |
| `bleedTiltAngle` | 0.1 | 0.1 |
| `blendGammaCorrect` | False | True |
| `blendMode` | 0 | 0 |
| `brightnessTiltAngle` | 0.1 | 0.1 |
| `bundledGrainPath` | '$null' | 'Brush-Pocket-Munched-Paper.png' |
| `bundledHeightPath` | - | '$null' |
| `bundledMetallicPath` | - | '$null' |
| `bundledRoughnessPath` | - | '$null' |
| `bundledShapePath` | '$null' | 'Brush-Preset-Medium-Hard.png' |
| `burntEdgesAmount` | 0 | 1 |
| `burntEdgesBlendMode` | 1 | 11 |
| `color` | <data 16B> | <data 16B> |
| `creationDate` | <NSDate> | <NSDate> |
| `darknessJitterTilt` | False | False |
| `darknessJitterTiltAngle` | 0.1 | 0.1 |
| `dualBlendMode` | 0 | 0 |
| `dynamicsBlur` | 0 | 0 |
| `dynamicsBlurJitter` | 0 | 0 |
| `dynamicsFalloff` | 0 | 0 |
| `dynamicsGlazedFlow` | 1 | 1 |
| `dynamicsJitterDarkness` | 0 | 0 |
| `dynamicsJitterHue` | 0 | 0 |
| `dynamicsJitterLightness` | 0 | 0 |
| `dynamicsJitterOpacity` | 0 | 0 |
| `dynamicsJitterSaturation` | 0 | 0 |
| `dynamicsJitterSize` | 0 | 0 |
| `dynamicsJitterStrokeDarkness` | 0 | 0 |
| `dynamicsJitterStrokeHue` | 0 | 0 |
| `dynamicsJitterStrokeLightness` | 0 | 0 |
| `dynamicsJitterStrokeSaturation` | 0 | 0 |
| `dynamicsLoad` | 0.5 | 0.5 |
| `dynamicsMix` | 0 | 0 |
| `dynamicsMixSoftening` | 0 | 0 |
| `dynamicsPressureBleed` | 0 | 0 |
| `dynamicsPressureBleedCurve` | <ValkyrieMagnitudinalCurve> | <ValkyrieMagnitudinalCurve> |
| `dynamicsPressureBleedSpeed` | 0.3 | 0.3 |
| `dynamicsPressureBrightness` | 0 | 0 |
| `dynamicsPressureBrightnessCurve` | <ValkyrieMagnitudinalCurve> | <ValkyrieMagnitudinalCurve> |
| `dynamicsPressureHue` | 0 | 0 |
| `dynamicsPressureHueCurve` | <ValkyrieMagnitudinalCurve> | <ValkyrieMagnitudinalCurve> |
| `dynamicsPressureMix` | 0 | 0 |
| `dynamicsPressureOpacity` | 0 | 0.193852 |
| `dynamicsPressureOpacityCurve` | <ValkyrieMagnitudinalCurve> | <ValkyrieMagnitudinalCurve> |
| `dynamicsPressureOpacitySpeed` | 0.3 | 0.3 |
| `dynamicsPressureOpacityTransfer` | 1 | 1 |
| `dynamicsPressureResponse` | 0.3 | 0.3 |
| `dynamicsPressureSaturation` | 0 | 0 |
| `dynamicsPressureSaturationCurve` | <ValkyrieMagnitudinalCurve> | <ValkyrieMagnitudinalCurve> |
| `dynamicsPressureSecondaryColor` | 0 | 0 |
| `dynamicsPressureSecondaryColorCurve` | <ValkyrieMagnitudinalCurve> | <ValkyrieMagnitudinalCurve> |
| `dynamicsPressureShapeRoundness` | 1 | 1 |
| `dynamicsPressureShapeRoundnessCurve` | <ValkyrieMagnitudinalCurve> | <ValkyrieMagnitudinalCurve> |
| `dynamicsPressureShapeRoundnessMinimum` | 1 | 1 |
| `dynamicsPressureSize` | 0 | 0.488545 |
| `dynamicsPressureSizeCurve` | <ValkyrieMagnitudinalCurve> | <ValkyrieMagnitudinalCurve> |
| `dynamicsPressureSizeSpeed` | 0.3 | 0.3 |
| `dynamicsPressureSmoothing` | 0 | 0 |
| `dynamicsPressureTransferModulationCurve` | <ValkyrieMagnitudinalCurve> | <ValkyrieMagnitudinalCurve> |
| `dynamicsSmudgeAccumulation` | 0.75 | 0.75 |
| `dynamicsSpeedOpacity` | 0 | 0 |
| `dynamicsSpeedSize` | 0 | 0 |
| `dynamicsTiltAngle` | 0.1 | 0.1 |
| `dynamicsTiltBleed` | 0 | 0 |
| `dynamicsTiltBrightness` | 0 | 0 |
| `dynamicsTiltCompression` | 1 | 1 |
| `dynamicsTiltGradation` | 0 | 0 |
| `dynamicsTiltHue` | 0 | 0 |
| `dynamicsTiltOpacity` | 0 | 0 |
| `dynamicsTiltSaturation` | 0 | 0 |
| `dynamicsTiltSecondaryColor` | 0 | 0 |
| `dynamicsTiltShapeRoundness` | 1 | 1 |
| `dynamicsTiltShapeRoundnessMinimum` | 1 | 1 |
| `dynamicsTiltSize` | 0 | 0 |
| `dynamicsWetAccumulation` | 0.75 | 0.75 |
| `dynamicsWetnessJitter` | 0 | 0 |
| `eraseOpacity` | 1 | 1 |
| `eraseSize` | 0.5 | 0.245785 |
| `extendedBlend` | 0 | 0 |
| `gradationTiltAngle` | 0.1 | 0.1 |
| `grainBlendMode` | 1 | 1 |
| `grainDepth` | 1 | 1 |
| `grainDepthJitter` | 0 | 0 |
| `grainDepthMinimum` | 0 | 0 |
| `grainOrientation` | 1 | 1 |
| `heightAmount` | - | 0.5 |
| `heightScale` | - | 0.16 |
| `hoverFill` | - | 1 |
| `hoverOutline` | - | 1 |
| `hoverPressure` | - | 0.1 |
| `hueJitterTilt` | False | False |
| `hueJitterTiltAngle` | 0.1 | 0.1 |
| `hueTiltAngle` | 0.1 | 0.1 |
| `importedFromABR` | False | False |
| `jitterSecondary` | 0 | 0 |
| `jitterStrokeSecondary` | 0 | 0 |
| `lightnessJitterTilt` | False | False |
| `lightnessJitterTiltAngle` | 0.1 | 0.1 |
| `maxOpacity` | 1 | 1 |
| `maxPressureSizeClamped` | False | False |
| `maxSize` | 1 | 1 |
| `metallicAmount` | - | 0 |
| `metallicGrainInverted` | - | False |
| `metallicScale` | - | 0.16 |
| `minOpacity` | 0 | 0 |
| `minSize` | 0 | 0 |
| `name` | 'Star' | 'Textured Lineart ตัดเส้นแบบมีเทกซ์เจอร์ ' |
| `opacityTiltAngle` | 0.1 | 0.1 |
| `oriented` | True | True |
| `paintOpacity` | 1 | 0.700966 |
| `paintPressure` | 1 | 1 |
| `paintSize` | 0.0990963 | 0.316064 |
| `pencilTaperEndLength` | 0 | 1 |
| `pencilTaperOpacity` | 0 | 1 |
| `pencilTaperShape` | 0 | 0 |
| `pencilTaperSize` | 0 | 1 |
| `pencilTaperSizeLinked` | False | True |
| `pencilTaperStartLength` | 0 | 1 |
| `pencilTipAnimation` | True | True |
| `plotFFTSmoothingAmount` | - | 0 |
| `plotFFTSmoothingBias` | - | 0 |
| `plotJitter` | 0 | 0 |
| `plotJitterTilt` | False | False |
| `plotJitterTiltAngle` | 0.1 | 0.1 |
| `plotMovingAverageStabilization` | - | 0 |
| `plotSmoothing` | 0 | 0.584206 |
| `plotSpacing` | 2 | 0 |
| `plotSpacingVersion` | 1 | 1 |
| `previewSize` | 0.3 | 0.3 |
| `renderingMaxTransfer` | False | False |
| `renderingModulatedTransfer` | False | False |
| `renderingRecursiveMixing` | False | True |
| `roughnessAmount` | - | 0.5 |
| `roughnessGrainInverted` | - | False |
| `roughnessScale` | - | 0.16 |
| `saturationJitterTilt` | False | False |
| `saturationJitterTiltAngle` | 0.1 | 0.1 |
| `saturationTiltAngle` | 0.1 | 0.1 |
| `savedEraseOpacities` | - | <NSArray> |
| `savedEraseSizes` | - | <NSArray> |
| `savedPaintOpacities` | - | <NSArray> |
| `savedPaintSizes` | - | <NSArray> |
| `savedSmudgeOpacities` | - | <NSArray> |
| `savedSmudgeSizes` | - | <NSArray> |
| `secondaryColorJitterTilt` | False | False |
| `secondaryColorJitterTiltAngle` | 0.1 | 0.1 |
| `secondaryColorTiltAngle` | 0.1 | 0.1 |
| `shapeAngle` | 0 | 0 |
| `shapeAzimuth` | False | False |
| `shapeCount` | 1 | 0 |
| `shapeCountJitter` | 0 | 0 |
| `shapeCountTilt` | False | False |
| `shapeCountTiltAngle` | 0.1 | 0.1 |
| `shapeFilter` | True | True |
| `shapeFilterMode` | 0 | 0 |
| `shapeFlipXJitter` | False | False |
| `shapeFlipYJitter` | False | False |
| `shapeInverted` | False | False |
| `shapeOrientation` | 1 | 1 |
| `shapeRandomise` | False | False |
| `shapeRotation` | 0 | 0 |
| `shapeRoundness` | 1 | 1 |
| `shapeRoundnessTiltAngle` | 0.1 | 0.1 |
| `shapeScatter` | 0 | 0 |
| `sizeTiltAngle` | 0.1 | 0.1 |
| `smudgeOpacity` | 0.8 | 0.8 |
| `smudgeSize` | 0.5 | 0.5 |
| `stamp` | False | False |
| `taperEndLength` | 0 | 1 |
| `taperOpacity` | 0 | 0 |
| `taperPressure` | 1 | 1 |
| `taperShape` | 0 | 0 |
| `taperSize` | 0 | 0 |
| `taperSizeLinked` | False | True |
| `taperStartLength` | 0 | 1 |
| `taperVersion` | 1 | 1 |
| `textureApplication` | 0 | 0 |
| `textureBrightness` | 0 | 0 |
| `textureContrast` | 0 | 0 |
| `textureDepthTilt` | False | False |
| `textureDepthTiltAngle` | 0.1 | 0.1 |
| `textureFilter` | True | True |
| `textureFilterMode` | 0 | 0 |
| `textureInverted` | False | False |
| `textureMovement` | 1 | 1 |
| `textureOffsetJitter` | True | True |
| `textureOrientation` | 1 | 1 |
| `textureRotation` | 0 | 0 |
| `textureScale` | 1 | 1 |
| `textureZoom` | 1 | 1 |
| `texturizedGrainFollowsCamera` | - | True |
| `version` | 2 | 2 |
| `wetEdgesAmount` | 0 | 0 |


---

## Appendix B — what stampbyme implements (`stampbyme/procreate.py`)

Added after implementation. Verified against `tests/reference/Star.brush` and the Freya Lupen parser; **not yet import-tested on an iPad**.

- **Settings:** all 172 root keys of `Star.brush` with identical types and values (`test_matches_real_procreate_brush`), except:
  - `stamp = True`, so the library shows the stamp;
  - `paintSize = 0.5`, so the size slider starts in the middle.
  - `maxSize` stays at Star's `1.0`. Raising it is unverified, so it is left alone until a device test.
- **Object graph:** the 9 pressure curves, `color`, `creationDate`, `name` and `authorName` (`$null` when not given) are built the same way as in Star.
  - Floats are written as 8-byte reals. Procreate writes 4-byte reals; Apple's plist reader accepts both.
- **Files:** `Brush.archive`, `Shape.png` and `QuickLook/Thumbnail.png`.
  - No `Grain.png`, as in Star.
  - No `Signature/`, which is optional.
- **Shape:** 8-bit `L`, white = paint, on black, square, at most 2048 px. Stamps are not re-cropped, so Phase 1's padding and centring carry over.
- **Shape coverage departs from §4 step 1:**
  - For images with transparency, coverage is **alpha only**, not alpha × darkness. Procreate paints in the chosen colour, so the ink's own colour must not weaken the shape. Alpha × darkness turned near-black, noisy AI ink into ~90% paint.
  - Fully opaque images (no transparency) use darkness.
- **Thumbnail:** RGBA 1060×324, with three white copies of the stamp on transparent.
- **`.brushset`:** uppercase `uuid4` folder per brush, plus XML `brushset.plist` = `{brushes, name}` in PNG filename order. The zip is deflated, with no directory entries and no `__MACOSX`.
