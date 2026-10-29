"""Measure a reference picture row by row: silhouette and colour extents per view.

Usage:
    python scripts/measure_reference.py reference.jpg [--colors red,white,#3f9e95]
        [--height 80] [--step 4] [--views auto | x0:x1,x0:x1] [--json profile.json]
        [--masks masks.png]

A reference sheet usually shows the object several times side by side (front,
side, back). Views are found as column bands separated by background. In each
view every `step`-th row reports the object's left/right edge and the extent
of each colour. With --height (the real or design height of the object, mm)
the rows are converted to mm: z from the object's lowest row upwards, x from
the view's axis (the median centre of the silhouette), so a profile can be
pasted into a model as (half-width, z) points.

The views are column bands of the silhouette, so a ribbon of another colour
across the body does not split a view. The bottom row comes from an anchor
colour (--anchor, default the first of --colors): a floor shadow would
otherwise join the views or move the bottom. Colours are named presets (red, white, green, yellow, teal, orange, black,
pink, blue, skin) or #rrggbb (matched within --tol RGB distance). --masks
writes the detected masks so you can check them before trusting the numbers.

Pitfalls this is built around: the silhouette edge is not the front edge (a
tilted cuff's sides hang lower than its front - look at the side view too);
AI-generated sheets are not consistent between views (measure each view and
decide which to trust); pixel rows step in whole pixels, so thin the points
(every 2nd-3rd row) before building a spline through them, or the surface bands;
a picture sent through a messenger is recompressed, and its noise would add
rows above a white top (the --threshold default and dropped specks handle it).
"""

import argparse
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage


def preset_masks(img: np.ndarray, bg: np.ndarray) -> dict:
    r, g, b = img[..., 0], img[..., 1], img[..., 2]
    light = (r > 200) & (g > 195) & (b > 190)
    grey = img.max(axis=2) - img.min(axis=2) < 22  # anti-aliased coloured edges are light but tinted
    return {
        "red": (r > g + 60) & (r > b + 60),
        "white": light & grey & (np.abs(img - bg).sum(axis=2) > 9),
        "green": (g > r + 15) & (g > b + 5) & (g < 200),
        "yellow": (r > 180) & (g > 120) & (b < 110),
        "teal": (g - r > 25) & (b - r > 15),
        "orange": (r - b > 80) & (r > 150) & (g > 70) & (g < r - 30),
        "black": (r < 60) & (g < 60) & (b < 60),
        "pink": (r > 200) & (g > 120) & (g < 190) & (b > 120) & (r > g + 30),
        "blue": (b > r + 50) & (b > g + 20),
        "skin": (r > 200) & (g > 150) & (g < 215) & (b > 120) & (b < 190) & (r > b + 30),
    }


def colour_mask(name: str, img: np.ndarray, presets: dict, tol: float) -> np.ndarray:
    if name.startswith("#"):
        rgb = np.array([int(name[i:i + 2], 16) for i in (1, 3, 5)])
        return np.sqrt(((img - rgb) ** 2).sum(axis=2)) < tol
    if name not in presets:
        sys.exit(f"unknown colour {name!r}: use one of {', '.join(presets)} or #rrggbb")
    return presets[name]


def background(img: np.ndarray) -> np.ndarray:
    """The background colour: the median of an 8-pixel frame round the picture."""
    border = np.concatenate([img[:8].reshape(-1, 3), img[-8:].reshape(-1, 3),
                             img[:, :8].reshape(-1, 3), img[:, -8:].reshape(-1, 3)])
    return np.median(border, axis=0)


def silhouette(img: np.ndarray, bg: np.ndarray, threshold: float) -> np.ndarray:
    """Pixels further than `threshold` (RGB sum) from the background, holes
    filled; frame lines at the picture's edge are dropped."""
    obj = ndimage.binary_fill_holes(ndimage.binary_closing(np.abs(img - bg).sum(axis=2) > threshold, iterations=3))
    obj[:3], obj[-3:], obj[:, :3], obj[:, -3:] = False, False, False, False
    return obj


def drop_specks(mask: np.ndarray) -> np.ndarray:
    """The object without the noise round it: a picture sent through a
    messenger is recompressed, and one speck above a white top adds rows to
    the object's height. Blobs under 1% of the largest one go."""
    labels, n = ndimage.label(mask)
    if n < 2:
        return mask
    sizes = ndimage.sum(mask, labels, range(1, n + 1))
    return np.isin(labels, np.flatnonzero(sizes >= 0.01 * sizes.max()) + 1)


def clamp_spans(spans: list[tuple[int, int]], size: int, flag: str) -> list[tuple[int, int]]:
    """Hand-given pixel ranges are inclusive: an end equal to the picture's
    width or height (its edge) means the last pixel."""
    spans = [(max(0, min(a, size - 1)), max(0, min(b, size - 1))) for a, b in spans]
    if any(b <= a for a, b in spans):
        sys.exit(f"{flag}: each range needs its end after its start, inside the picture (0..{size - 1})")
    return spans


def split_views(obj: np.ndarray, anchor, gap: int, expected: int | None = None) -> list[tuple[int, int]]:
    """Column spans of the views on the sheet, found on the silhouette: a
    ribbon of another colour across the body must not split one view in two.

    A floor shadow often runs under the whole sheet and joins the views, so
    rows below the anchor colour's lowest row are ignored, and the column
    threshold is raised step by step until the sheet splits into the expected
    number of views (with no number, the first split counts); each view is
    then widened back to its real edges."""
    mask = obj.copy()
    if anchor is not None and anchor.any():
        mask[np.where(anchor.any(axis=1))[0].max() + 1:] = False
    counts = mask.sum(axis=0)
    if not counts.any():
        sys.exit("no object found: check the background or pass --threshold")
    spans = []
    for frac in (0.15, 0.25, 0.35, 0.5, 0.65):
        cols = np.where(counts > frac * counts.max())[0]
        runs, start = [], cols[0]
        for a, b in zip(cols, cols[1:]):
            if b - a > gap:
                runs.append([start, a])
                start = b
        runs.append([start, cols[-1]])
        spans = [r for r in runs if r[1] - r[0] >= max(10, obj.shape[1] // 40)]
        if expected is None or len(spans) == expected:
            break
    low = 0.08 * counts.max()
    for i, s in enumerate(spans):
        left_limit = spans[i - 1][1] + 1 if i else 0
        right_limit = spans[i + 1][0] - 1 if i + 1 < len(spans) else len(counts) - 1
        while s[0] - 1 >= left_limit and counts[s[0] - 1] > low:
            s[0] -= 1
        while s[1] + 1 <= right_limit and counts[s[1] + 1] > low:
            s[1] += 1
    return [(int(a), int(b)) for a, b in spans]


def extent(row: np.ndarray):
    xs = np.where(row)[0]
    return (int(xs.min()), int(xs.max()), int(len(xs))) if len(xs) > 1 else None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("image", type=Path)
    parser.add_argument("--colors", default="", help="comma-separated presets or #rrggbb")
    parser.add_argument("--height", type=float, help="object height in mm, to convert pixels")
    parser.add_argument("--step", type=int, default=4, help="report every N-th row")
    parser.add_argument("--views", default="auto", help="auto, or x0:x1,x0:x1 pixel column ranges")
    parser.add_argument("--anchor", help="colour that sets each view's bottom row (default: the first of"
                        " --colors); keeps floor shadows out")
    parser.add_argument("--rows", help="y0:y1 pixel rows of the object, overrides top/bottom detection")
    parser.add_argument("--gap", type=int, default=12, help="background columns that split views")
    parser.add_argument("--threshold", type=float, default=20, help="RGB sum difference from background"
                        " (20: steady on recompressed pictures)")
    parser.add_argument("--tol", type=float, default=60, help="RGB distance for #rrggbb colours")
    parser.add_argument("--json", type=Path)
    parser.add_argument("--masks", type=Path, help="write the detected masks as a PNG")
    args = parser.parse_args()

    img = np.asarray(Image.open(args.image).convert("RGB")).astype(int)
    h, w, _ = img.shape
    bg = background(img)
    obj = silhouette(img, bg, args.threshold)
    presets = preset_masks(img, bg)
    names = [c.strip() for c in args.colors.split(",") if c.strip()]
    masks = {n: colour_mask(n, img, presets, args.tol) & obj for n in names}
    print(f"image {w} x {h} px, background RGB {bg.astype(int).tolist()}")

    anchor_name = args.anchor or (names[0] if names else None)
    anchor = masks[anchor_name] if anchor_name in masks else (
        colour_mask(anchor_name, img, presets, args.tol) & obj if anchor_name else obj)
    if args.views == "auto":
        views = split_views(obj, anchor, args.gap)
    else:
        views = clamp_spans([tuple(int(v) for v in rng.split(":")) for rng in args.views.split(",")], w, "--views")
    result = {"image": str(args.image), "size": [w, h], "views": []}
    for vi, (x0, x1) in enumerate(views):
        o = drop_specks(obj[:, x0:x1 + 1])
        rows = np.where(o.any(axis=1))[0]
        if not len(rows):
            sys.exit(f"view {vi} (columns {x0}..{x1}) holds no object")
        top = int(rows.min())
        # Bottom from the anchor colour: below it is usually the floor shadow.
        anchor_rows = np.where(anchor[:, x0:x1 + 1].any(axis=1))[0]
        bottom = int(anchor_rows.max()) if len(anchor_rows) else int(rows.max())
        if args.rows:
            [(top, bottom)] = clamp_spans([tuple(int(v) for v in args.rows.split(":"))], h, "--rows")
        centres = [(e[0] + e[1]) / 2 for y in rows if (e := extent(o[y]))]
        axis = float(np.median(centres)) + x0
        mm = args.height / (bottom - top) if args.height else None
        view = {"index": vi, "x0": int(x0), "x1": int(x1), "top": top, "bottom": bottom, "axis_px": axis,
                "mm_per_px": mm, "rows": []}
        print(f"\n== view {vi}: columns {x0}..{x1}, rows {top}..{bottom} ({bottom - top} px), axis x={axis:.0f}"
              + (f", {mm:.4f} mm/px" if mm else ""))
        for y in range(top, bottom + 1, args.step):
            row = {"y": int(y)}
            if mm:
                row["z"] = round((bottom - y) * mm, 2)
            e = extent(o[y])
            if e:
                row["object"] = [e[0] + x0, e[1] + x0]
            for n, m in masks.items():
                ce = extent(m[y, x0:x1 + 1] & o[y])
                if ce:
                    row[n] = [ce[0] + x0, ce[1] + x0, ce[2]]
            view["rows"].append(row)

            def fmt(span):
                a, b = span[0], span[1]
                n = f" n{span[2]}" if len(span) > 2 else ""  # pixel count: a span with few pixels is edges
                if mm:
                    return f"{(a - axis) * mm:7.2f}..{(b - axis) * mm:6.2f} w{(b - a) * mm:6.2f}{n}"
                return f"{a:5}..{b:5} w{b - a:4}{n}"
            line = f"  y{y:5}" + (f" z{row['z']:7.2f}" if mm else "")
            line += f"  obj {fmt(row['object'])}" if "object" in row else " " * 30
            for n in masks:
                if n in row:
                    line += f"  {n} {fmt(row[n])}"
            print(line)
        result["views"].append(view)

    if args.json:
        args.json.write_text(json.dumps(result, indent=1), encoding="utf-8")
        print(f"\njson  : {args.json}")
    if args.masks:
        out = np.full((h, w, 3), 255, dtype=np.uint8)
        out[obj] = (210, 210, 210)
        palette = [(220, 30, 30), (30, 120, 220), (30, 170, 60), (230, 170, 0), (150, 50, 200), (0, 0, 0)]
        for i, m in enumerate(masks.values()):
            out[m] = palette[i % len(palette)]
        for x0, x1 in views:
            out[:, [x0, x1]] = (255, 0, 255)
        Image.fromarray(out).save(args.masks)
        print(f"masks : {args.masks} (grey object, colours in --colors order, magenta view bounds)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
