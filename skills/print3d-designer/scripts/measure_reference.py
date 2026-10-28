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

The views and the bottom row come from an anchor colour (--anchor, default
the first of --colors): a floor shadow or a frame line would otherwise join
the views or move the bottom. Colours are named presets (red, white, green, yellow, teal, orange, black,
pink, blue, skin) or #rrggbb (matched within --tol RGB distance). --masks
writes the detected masks so you can check them before trusting the numbers.

Pitfalls this is built around: the silhouette edge is not the front edge (a
tilted cuff's sides hang lower than its front - look at the side view too);
AI-generated sheets are not consistent between views (measure each view and
decide which to trust); pixel rows step in whole pixels, so thin the points
(every 2nd-3rd row) before building a spline through them, or the surface bands.
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


def find_views(mask: np.ndarray, gap: int, min_width: int) -> list[tuple[int, int]]:
    """Column bands of the mask. Columns count only when the mask is tall there,
    so a floor shadow or a frame line joining the views does not merge them."""
    counts = mask.sum(axis=0)
    cols = np.where(counts > max(3, 0.15 * counts.max()))[0]
    if not len(cols):
        sys.exit("no object found: check the background or pass --threshold")
    views, start = [], cols[0]
    for a, b in zip(cols, cols[1:]):
        if b - a > gap:
            views.append((start, a))
            start = b
    views.append((start, cols[-1]))
    return [(a, b) for a, b in views if b - a >= min_width]


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
    parser.add_argument("--anchor", help="colour that splits the views and sets the bottom row"
                        " (default: the first of --colors); keeps floor shadows out")
    parser.add_argument("--rows", help="y0:y1 pixel rows of the object, overrides top/bottom detection")
    parser.add_argument("--gap", type=int, default=12, help="background columns that split views")
    parser.add_argument("--threshold", type=float, default=12, help="RGB sum difference from background")
    parser.add_argument("--tol", type=float, default=60, help="RGB distance for #rrggbb colours")
    parser.add_argument("--json", type=Path)
    parser.add_argument("--masks", type=Path, help="write the detected masks as a PNG")
    args = parser.parse_args()

    img = np.asarray(Image.open(args.image).convert("RGB")).astype(int)
    h, w, _ = img.shape
    border = np.concatenate([img[:8].reshape(-1, 3), img[-8:].reshape(-1, 3),
                             img[:, :8].reshape(-1, 3), img[:, -8:].reshape(-1, 3)])
    bg = np.median(border, axis=0)
    diff = np.abs(img - bg).sum(axis=2)
    obj = ndimage.binary_fill_holes(ndimage.binary_closing(diff > args.threshold, iterations=3))
    obj[:3], obj[-3:], obj[:, :3], obj[:, -3:] = False, False, False, False  # frame lines
    presets = preset_masks(img, bg)
    names = [c.strip() for c in args.colors.split(",") if c.strip()]
    masks = {n: colour_mask(n, img, presets, args.tol) & obj for n in names}
    print(f"image {w} x {h} px, background RGB {bg.astype(int).tolist()}")

    anchor_name = args.anchor or (names[0] if names else None)
    anchor = masks[anchor_name] if anchor_name in masks else (
        colour_mask(anchor_name, img, presets, args.tol) & obj if anchor_name else obj)
    if args.views == "auto":
        views = find_views(anchor, args.gap, max(10, w // 40))
    else:
        views = [tuple(int(v) for v in rng.split(":")) for rng in args.views.split(",")]
    result = {"image": str(args.image), "size": [w, h], "views": []}
    for vi, (x0, x1) in enumerate(views):
        x0, x1 = int(x0), int(x1)
        o = obj[:, x0:x1 + 1]
        rows = np.where(o.any(axis=1))[0]
        top = int(rows.min())
        # Bottom from the anchor colour: below it is usually the floor shadow.
        anchor_rows = np.where(anchor[:, x0:x1 + 1].any(axis=1))[0]
        bottom = int(anchor_rows.max()) if len(anchor_rows) else int(rows.max())
        if args.rows:
            top, bottom = (int(v) for v in args.rows.split(":"))
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
                ce = extent(m[y, x0:x1 + 1])
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
