"""Compare the model with the reference picture view by view, in numbers.

Usage:
    python scripts/compare_views.py models/<name>/parts reference.jpg --views front,side,back,three-quarter
        [--ref-views x0:x1,...] [--anchor red] [--elevation 5] [--png views_check.png]
        [--info three-quarter]

The model (a folder of STLs, or one STL) is rendered as a flat silhouette
from each named view and laid over the matching view of the reference sheet,
scaled to the same height and centred. For every view it prints:
  IoU            overlap of the two silhouettes (1.0 = identical)
  aspect         width/height of the model against the picture
  width by band  where the model is too wide or too narrow (bed = 0%)
  colours        per colour part named like a colour (red.stl...), how its
                 area overlaps that colour in the picture (information only:
                 parts the user asked to remove still show in the picture)
It also tries every other order of the views: if another order fits much
better, the --views order does not match the sheet (a three-quarter render
compared with a side photo hides every mistake). views_check.png shows each
picture view above its overlay: grey = both, blue = only in the picture,
red = only in the model.

PASS needs every view except --info ones at IoU >= 0.92 and aspect within 8%
(calibrated on four models: good ones scored 0.93-0.96, a cube copied by eye
0.81-0.90). The limits are fixed: --min-iou and --max-aspect may only be
stricter, and front, side, left and back are always gated (--info is for
views whose camera angle the picture leaves open, such as three-quarter).
A side view that fits better mirrored is reported too: "side" looks from +X,
so a sheet whose side view faces right shows "left". This is the gate for
agents that cannot look at images well: a model that fails it does not match
the reference, whatever it looks like. The verdict goes to views_check.json
next to the parts folder, and make_3mf.py refuses to build a project from
parts that failed it or changed after it.
Views (camera from the model): front, side (+X), back, left, three-quarter,
three-quarter-left, front-left, back-high, top. --elevation lifts the camera
like the slightly-from-above product shots of AI reference sheets.
"""

import argparse
import itertools
import json
import sys
import time
from pathlib import Path

import numpy as np
import quiet_vtk  # noqa: F401  (before pyvista)
import pyvista as pv
import trimesh  # noqa: F401  (pyvista reads the STL; trimesh kept for parity with other scripts)
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).parent))
import measure_reference as mr  # noqa: E402
from render_parts import VIEWS  # noqa: E402

# A side view of the sheet may show the model's other side: the same view
# from the opposite camera is its mirror image.
MIRROR = {"side": "left", "left": "side", "three-quarter": "three-quarter-left", "three-quarter-left": "three-quarter"}
LABELS = [(255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 0), (255, 0, 255), (0, 255, 255), (255, 128, 0),
          (128, 0, 255)]
BANDS = 10
MIN_IOU, MAX_ASPECT = 0.92, 0.08
ALWAYS_GATED = {"front", "side", "left", "back"}
VERDICT = "views_check.json"  # make_3mf.py reads it


def load_meshes(path: Path) -> list[tuple[str, pv.PolyData]]:
    files = sorted(path.glob("*.stl")) if path.is_dir() else [path]
    if not files:
        sys.exit(f"no STL in {path}")
    return [(f.stem, pv.read(str(f))) for f in files]


def direction(view: str, elevation: float) -> tuple[tuple, tuple]:
    if view not in VIEWS:
        sys.exit(f"unknown view {view!r}: use {', '.join(VIEWS)}")
    x, y, z = VIEWS[view]
    if view in ("top", "bottom"):
        return (x, y, z), (0, 1, 0)
    h = float(np.hypot(x, y))
    e = np.radians(elevation)
    return (x / h * np.cos(e), y / h * np.cos(e), np.sin(e)), (0, 0, 1)


def render_labels(meshes, view: str, elevation: float, size: int = 900) -> np.ndarray:
    """Per-pixel part index (-1 = background), flat colours, parallel projection."""
    pl = pv.Plotter(off_screen=True, window_size=(size, size))
    pl.set_background("black")
    for i, (_, mesh) in enumerate(meshes):
        pl.add_mesh(mesh, color=LABELS[i % len(LABELS)], lighting=False)
    d, up = direction(view, elevation)
    pl.view_vector(d, viewup=up)
    pl.enable_parallel_projection()
    pl.reset_camera()
    img = pl.screenshot(return_img=True).astype(int)[..., :3]
    pl.close()
    dist = np.stack([np.abs(img - np.array(c)).sum(axis=2) for c in LABELS[:len(meshes)]])
    labels = dist.argmin(axis=0)
    labels[img.sum(axis=2) < 90] = -1
    return labels


def crop(mask: np.ndarray) -> tuple[slice, slice]:
    rows, cols = np.where(mask.any(axis=1))[0], np.where(mask.any(axis=0))[0]
    return slice(rows.min(), rows.max() + 1), slice(cols.min(), cols.max() + 1)


def centre(mask: np.ndarray, rows: slice) -> float:
    """Median of the row mid-points: the object's axis, robust to a shadow on one side."""
    mids = [(xs[0] + xs[-1]) / 2 for r in range(rows.start, rows.stop) if len(xs := np.where(mask[r])[0])]
    return float(np.median(mids)) if mids else mask.shape[1] / 2


def fit(ref: np.ndarray, model: np.ndarray, keep: slice) -> tuple[np.ndarray, np.ndarray]:
    """Scale `model` (int labels) to the reference height; put both on one
    canvas with their axes (row mid-points over the `keep` rows) aligned."""
    h = ref.shape[0]
    w = max(1, round(model.shape[1] * h / model.shape[0]))
    scaled = np.asarray(Image.fromarray((model + 1).astype(np.uint8)).resize((w, h), Image.NEAREST)).astype(int) - 1
    cr, cm = centre(ref >= 0, keep), centre(scaled >= 0, keep)
    half = int(max(cr, ref.shape[1] - cr, cm, w - cm)) + 4
    a = np.full((h, 2 * half), -1)
    b = np.full((h, 2 * half), -1)
    xa, xb = int(round(half - cr)), int(round(half - cm))
    a[:, xa:xa + ref.shape[1]] = ref
    b[:, xb:xb + w] = scaled
    return a, b


def iou(a: np.ndarray, b: np.ndarray) -> float:
    union = (a | b).sum()
    return float((a & b).sum() / union) if union else 0.0


def band_errors(ref: np.ndarray, model: np.ndarray) -> list[float]:
    """Relative width error per height band, bed first."""
    h = ref.shape[0]
    out = []
    for i in range(BANDS):
        rows = slice(h - (i + 1) * h // BANDS, h - i * h // BANDS)
        wr, wm = ref[rows].sum(axis=1).mean(), model[rows].sum(axis=1).mean()
        out.append((wm - wr) / wr if wr else 0.0)
    return out


def reference_views(args, img: np.ndarray):
    bg = mr.background(img)
    obj = mr.silhouette(img, bg, args.threshold)
    presets = mr.preset_masks(img, bg)
    anchor = mr.colour_mask(args.anchor, img, presets, args.tol) & obj if args.anchor else None
    if args.ref_views:
        spans = mr.clamp_spans([tuple(int(v) for v in s.split(":")) for s in args.ref_views.split(",")],
                               img.shape[1], "--ref-views")
    else:
        spans = mr.split_views(obj, anchor, args.gap, args.expected)
    views = []
    for x0, x1 in spans:
        sub = obj[:, x0:x1 + 1].copy()
        if anchor is not None and anchor[:, x0:x1 + 1].any():
            bottom = np.where(anchor[:, x0:x1 + 1].any(axis=1))[0].max()
            sub[bottom + 1:] = False  # floor shadow below the object
        sub = mr.drop_specks(sub)
        rs, cs = crop(sub)
        views.append({"span": (int(x0), int(x1)), "mask": sub[rs, cs],
                      "rgb": img[rs, x0 + cs.start:x0 + cs.stop], "presets": {k: v[rs, x0 + cs.start:x0 + cs.stop]
                                                                              for k, v in presets.items()}})
    return views


def compare(ref_view: dict, labels: np.ndarray, names: list[str], skip_bottom: float) -> dict:
    """Overlap, aspect and width errors. The bottom `skip_bottom` of the
    height is left out: floor shadows in product shots make the picture
    wider there (and bases get chamfers anyway)."""
    rs, cs = crop(labels >= 0)
    model = labels[rs, cs]
    ref = np.where(ref_view["mask"], 0, -1)
    h = ref.shape[0]
    keep = slice(0, max(1, int(round(h * (1 - skip_bottom)))))
    a, b = fit(ref, model, keep)
    sa, sb = a >= 0, b >= 0
    ka, kb = sa[keep], sb[keep]
    # Typical width (75th percentile of row widths), not the maximum: a few
    # rows of shadow beside the base must not set it.
    wa, wb = np.percentile(ka.sum(axis=1), 75), np.percentile(kb.sum(axis=1), 75)
    res = {"iou": iou(ka, kb), "a": sa, "b": sb, "keep": keep.stop,
           "aspect": (wb - wa) / wa if wa else 0.0, "bands": band_errors(sa, sb), "colours": {}}
    # Colour parts named like a colour preset: overlap with that colour in the picture.
    for i, name in enumerate(names):
        if name in ref_view["presets"]:
            ref_c = np.where(ref_view["presets"][name] & ref_view["mask"], 0, -1)
            ca, cb = fit(ref_c if (ref_c >= 0).any() else ref, model, keep)
            if (ref_c >= 0).any():
                res["colours"][name] = iou(ca[keep] >= 0, cb[keep] == i)
    return res


def panel(ref_view: dict, res: dict, title: str, height: int = 320) -> Image.Image:
    a, b = res["a"], res["b"]
    over = np.full(a.shape + (3,), 255, dtype=np.uint8)
    over[a & b] = (200, 200, 200)
    over[a & ~b] = (60, 120, 255)
    over[~a & b] = (255, 80, 60)
    over[res["keep"]:] = (over[res["keep"]:] * 0.35 + 165).astype(np.uint8)  # not scored (floor shadow zone)
    k = height / a.shape[0]
    ov = Image.fromarray(over).resize((max(1, round(a.shape[1] * k)), height), Image.NEAREST)
    ref = Image.fromarray(ref_view["rgb"].astype(np.uint8))
    ref = ref.resize((max(1, round(ref.width * height / ref.height)), height))
    w = max(ov.width, ref.width) + 20
    out = Image.new("RGB", (w, 2 * height + 40), "white")
    out.paste(ref, ((w - ref.width) // 2, 20))
    out.paste(ov, ((w - ov.width) // 2, height + 40))
    d = ImageDraw.Draw(out)
    d.text((6, 4), title, fill=(0, 0, 0))
    d.text((6, height + 24), f"IoU {res['iou']:.3f}  aspect {res['aspect']:+.1%}", fill=(0, 0, 0))
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("model", type=Path, help="folder of colour STLs, or one STL")
    parser.add_argument("reference", type=Path)
    parser.add_argument("--views", required=True, help="view names in the SAME order as the sheet, left to right")
    parser.add_argument("--ref-views", help="x0:x1,... pixel columns of each view (default: found automatically)")
    parser.add_argument("--anchor", help="body colour preset or #rrggbb: sets each view's bottom row (drops shadows)")
    parser.add_argument("--elevation", type=float, default=5.0, help="camera height above the horizon, degrees")
    parser.add_argument("--min-iou", type=float, default=MIN_IOU, help="stricter only")
    parser.add_argument("--skip-bottom", type=float, default=0.10, help="share of the height left out (floor shadow)")
    parser.add_argument("--max-aspect", type=float, default=MAX_ASPECT, help="stricter only")
    parser.add_argument("--info", default="", help="views reported but not gated: three-quarter and other views"
                        " whose camera angle the picture leaves open")
    parser.add_argument("--png", type=Path, help="write the overlays here (default: next to the model)")
    parser.add_argument("--threshold", type=float, default=20, help="RGB sum difference from the background")
    parser.add_argument("--gap", type=int, default=12)
    parser.add_argument("--tol", type=float, default=60)
    args = parser.parse_args()

    if args.min_iou < MIN_IOU or args.max_aspect > MAX_ASPECT:
        sys.exit(f"the gate's limits are fixed (IoU >= {MIN_IOU}, aspect within {MAX_ASPECT:.0%}): stricter is"
                 " allowed, looser is not. Fix the model; if the user has seen views_check.png and accepts the"
                 ' difference, make_3mf.py takes --accept-views "<their words>"')
    info = {v.strip() for v in args.info.split(",") if v.strip()}
    if info & ALWAYS_GATED:
        sys.exit(f"--info {','.join(sorted(info & ALWAYS_GATED))}: front, side, left and back are always gated;"
                 " --info is for views whose camera angle the picture leaves open (three-quarter...)")
    names_v = [v.strip() for v in args.views.split(",") if v.strip()]
    args.expected = len(names_v)
    img = np.asarray(Image.open(args.reference).convert("RGB")).astype(int)
    refs = reference_views(args, img)
    if len(refs) != len(names_v):
        spans = ", ".join(f"{a}:{b}" for a, b in (r["span"] for r in refs))
        sys.exit(f"the picture has {len(refs)} views ({spans}) but --views names {len(names_v)}: "
                 "name each view of the sheet in order, or pass --ref-views")
    meshes = load_meshes(args.model)
    names = [n for n, _ in meshes]
    renders = {v: render_labels(meshes, v, args.elevation) for v in set(names_v)}

    results = [compare(r, renders[v], names, args.skip_bottom) for r, v in zip(refs, names_v)]
    failed = []
    print(f"reference: {args.reference.name}, {len(refs)} views; model: {', '.join(names)}; elevation {args.elevation:g} deg")
    for r, v, res in zip(refs, names_v, results):
        gate = v not in info
        ok = res["iou"] >= args.min_iou and abs(res["aspect"]) <= args.max_aspect
        if gate and not ok:
            failed.append(v)
        tag = "INFO" if not gate else ("PASS" if ok else "FAIL")
        print(f"\n[{tag}] {v:18} columns {r['span'][0]}..{r['span'][1]}  IoU {res['iou']:.3f}"
              f"  aspect {res['aspect']:+.1%} (model {'wider' if res['aspect'] > 0 else 'narrower'} for its height)")
        skipped = int(round(args.skip_bottom * BANDS))
        bad = [(i, e) for i, e in enumerate(res["bands"]) if abs(e) > args.max_aspect and i >= skipped]
        for i, e in bad:
            print(f"       {i * 100 // BANDS:3d}-{(i + 1) * 100 // BANDS:3d}% of the height: "
                  f"model {'wider' if e > 0 else 'narrower'} by {abs(e):.0%}")
        for name, c in res["colours"].items():
            print(f"       colour {name:8} overlap {c:.2f}")

    # Is a side view the mirror image (the picture shows the other side)?
    for r, v, res in zip(refs, names_v, results):
        if v in MIRROR:
            flipped = compare(r, renders[v][:, ::-1], names, args.skip_bottom)["iou"]
            if flipped - res["iou"] > 0.02:
                print(f"\nWARNING view '{v}' looks mirrored (IoU {flipped:.3f} flipped against {res['iou']:.3f}):"
                      f" the picture shows the model's other side - name it '{MIRROR[v]}'.")
                failed.append("mirror")

    # Would another order of the same view names fit much better?
    if len(set(names_v)) > 1 and len(refs) <= 6:
        matrix = [[compare(r, renders[v], names, args.skip_bottom)["iou"] for v in names_v] for r in refs]
        given = np.mean([matrix[i][i] for i in range(len(refs))])
        best = max(itertools.permutations(range(len(refs))), key=lambda p: np.mean([matrix[i][p[i]] for i in range(len(refs))]))
        best_iou = np.mean([matrix[i][best[i]] for i in range(len(refs))])
        if best_iou - given > 0.03:
            order = ",".join(names_v[j] for j in best)
            print(f"\nWARNING the views look out of order: --views {order} fits better"
                  f" (mean IoU {best_iou:.3f} against {given:.3f}). Name the sheet's views left to right.")
            failed.append("order")

    folder = args.model.resolve().parent  # the model's folder: parts/ (or the STL) lies in it
    out = args.png or folder / "views_check.png"
    panels = [panel(r, res, v) for r, v, res in zip(refs, names_v, results)]
    sheet = Image.new("RGB", (sum(p.width for p in panels), max(p.height for p in panels)), "white")
    x = 0
    for p in panels:
        sheet.paste(p, (x, 0))
        x += p.width
    sheet.save(out)
    verdict = {"result": "FAIL" if failed else "PASS", "failed": failed, "time": time.time(),
               "model": str(args.model.resolve()), "reference": str(args.reference.resolve()),
               "views": [{"name": v, "gated": v not in info, "iou": round(res["iou"], 3),
                          "aspect": round(res["aspect"], 3)} for v, res in zip(names_v, results)]}
    (folder / VERDICT).write_text(json.dumps(verdict, indent=1), encoding="utf-8")
    print(f"\noverlays : {out} (grey both, blue only in the picture, red only in the model)")
    print(f"verdict  : {folder / VERDICT} (make_3mf.py builds no project from failed parts)")
    print("RESULT   : " + ("PASS" if not failed else "FAIL (" + ", ".join(failed) + ")"))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
