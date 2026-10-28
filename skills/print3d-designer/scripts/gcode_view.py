"""Parse a sliced G-code and render what the printer will actually lay down.

Usage:
    python scripts/gcode_view.py plate_1.gcode [--layers 0.3,5,12.5]

Writes toolpaths.png (3D extrusion paths coloured by feature) and layers.png
(top-down views of chosen layers, every line drawn at its true extrusion width
so gaps, thin walls and features the slicer dropped are visible) next to the
G-code, and prints time, filament and where bridges/supports/overhangs occur.
"""

import argparse
import json
import math
import re
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pyvista as pv
from matplotlib.collections import LineCollection
from matplotlib.patches import Patch

sys.path.insert(0, str(Path(__file__).parent))
import config  # noqa: E402

CFG = config.load()
FILAMENT_AREA = math.pi * (CFG["filament"]["diameter"] / 2) ** 2  # mm^2
ARC_STEP = 0.5  # mm per chord when expanding G2/G3
FEATURE_COLORS = {
    "Bridge": "#1f3fff",
    "Internal Bridge": "#6a7dff",
    "Overhang wall": "#00b3b3",
    "Support": "#2ca02c",
    "Support interface": "#7fd67f",
    "Support transition": "#98df8a",
    "Outer wall": "#ff7f0e",
    "Inner wall": "#ffbb78",
    "Top surface": "#d62728",
    "Bottom surface": "#9467bd",
    "Internal solid infill": "#c5b0d5",
    "Sparse infill": "#bcbd22",
    "Gap infill": "#e377c2",
    "Ironing": "#8c564b",
    "Brim": "#7f7f7f",
    "Skirt": "#7f7f7f",
}
OTHER_COLOR = "#aaaaaa"
ALERT_FEATURES = ("Bridge", "Overhang wall", "Support", "Support interface")
# Start-gcode purge lines are tagged Custom; they are not part of the model.
SKIP_FEATURES = ("Custom",)
# OrcaSlicer writes Bambu-style comments for Bambu printers; map them to the plain ones.
BAMBU_MARKERS = (("; FEATURE: ", ";TYPE:"), ("; LINE_WIDTH: ", ";WIDTH:"), ("; CHANGE_LAYER", ";LAYER_CHANGE"),
                 ("; Z_HEIGHT: ", ";Z:"), ("; LAYER_HEIGHT: ", ";HEIGHT:"))
# What a nozzle can actually melt, mm^3/s, when it is below the filament
# profile's own max_volumetric_speed (PETG profiles inherit 0.4-nozzle caps).
# printer.json nozzles[*].flow_limit wins over these PETG rules of thumb.
NOZZLE_FLOW_LIMIT = {0.2: 5.0, 0.25: 7.0, **config.flow_limits(CFG)}
MIN_FLOW_SEGMENT = 2.0  # mm; shorter moves never reach their commanded speed
# Segment columns
X0, Y0, X1, Y1, Z, LAYER, FEATURE, WIDTH, FLOW, TOOL = range(10)


class Toolpath:
    def __init__(self, path: Path):
        self.features: list[str] = []
        self.layer_z: list[float] = []
        self.layer_h: list[float] = []
        self.density = 1.24
        self.nozzle = None
        self.filament_flow_cap = None
        self.time_min = None
        self.filament_mm = 0.0
        self.filament_colours: list[str] = []
        self.grams_per_tool: list[float] = []
        self.tool_changes = 0
        segs = []

        x = y = z = e_abs = feed = 0.0
        tool = 0
        relative_e = relative_xyz = False
        layer, feature, width, skip = -1, -1, 0.0, True
        with open(path, encoding="utf-8", errors="replace") as f:
            for raw in f:
                if raw.startswith(";"):
                    if raw.startswith("; "):  # Bambu-style markers (OrcaSlicer for Bambu printers)
                        for bambu, plain in BAMBU_MARKERS:
                            if raw.startswith(bambu):
                                raw = plain + raw[len(bambu):]
                                break
                    if raw.startswith(";TYPE:"):
                        name = raw[6:].strip()
                        skip = name in SKIP_FEATURES
                        feature = -1 if skip else self._fid(name)
                    elif raw.startswith(";WIDTH:"):
                        width = float(raw[7:])
                    elif raw.startswith(";LAYER_CHANGE"):
                        layer += 1
                    elif raw.startswith(";Z:"):
                        self.layer_z.append(float(raw[3:]))
                    elif raw.startswith(";HEIGHT:"):
                        self.layer_h.append(float(raw[8:]))
                    elif raw.startswith("; filament_density:"):
                        self.density = float(raw.split(":")[1].split(",")[0])
                    elif raw.startswith("; nozzle_diameter = "):
                        self.nozzle = float(raw.split("=")[1].split(",")[0])
                    elif raw.startswith("; filament_max_volumetric_speed = "):
                        self.filament_flow_cap = float(raw.split("=")[1].split(",")[0])
                    elif raw.startswith("; filament_colour = "):
                        self.filament_colours = [c.strip() for c in raw.split("=")[1].split(";")]
                    elif raw.startswith("; filament used [g] = "):
                        self.grams_per_tool = [float(g) for g in raw.split("=")[1].split(",")]
                    elif self.time_min is None and raw.startswith("; estimated printing time"):
                        self.time_min = _minutes(raw.split("=", 1)[-1])  # profiles without M73 (Orca, Anycubic)
                    elif self.time_min is None and "total estimated time:" in raw:
                        self.time_min = _minutes(raw.split("total estimated time:", 1)[1])  # Bambu-style header
                    continue
                words = raw.split(";", 1)[0].split()
                if not words:
                    continue
                cmd = words[0]
                if cmd[0] == "T" and cmd[1:].isdigit():
                    if layer >= 0 and int(cmd[1:]) != tool:
                        self.tool_changes += 1
                    tool = int(cmd[1:])
                elif cmd == "M83":
                    relative_e = True
                elif cmd == "M82":
                    relative_e = False
                elif cmd == "G91":
                    relative_xyz = True
                elif cmd == "G90":
                    relative_xyz = False
                elif cmd == "G92":
                    p = _params(words)
                    e_abs = p.get("E", e_abs)
                elif cmd == "M73" and self.time_min is None:
                    r = next((w for w in words if w.startswith("R")), None)
                    self.time_min = float(r[1:]) if r else None
                elif cmd in ("G0", "G1", "G2", "G3"):
                    p = _params(words)
                    if relative_xyz:
                        nx, ny, nz = x + p.get("X", 0), y + p.get("Y", 0), z + p.get("Z", 0)
                    else:
                        nx, ny, nz = p.get("X", x), p.get("Y", y), p.get("Z", z)
                    if "E" in p:
                        de = p["E"] if relative_e else p["E"] - e_abs
                        e_abs = e_abs + de if relative_e else p["E"]
                    else:
                        de = 0.0
                    feed = p.get("F", feed)
                    self.filament_mm += de
                    if de > 0 and layer >= 0 and not skip and (nx != x or ny != y):
                        pts = _arc(x, y, nx, ny, p, cmd == "G2") if cmd in ("G2", "G3") else [(x, y), (nx, ny)]
                        path_len = sum(math.dist(a, b) for a, b in zip(pts, pts[1:]))
                        flow = de / path_len * FILAMENT_AREA * feed / 60 if path_len >= MIN_FLOW_SEGMENT else 0.0
                        w = width
                        if w <= 0 and path_len >= MIN_FLOW_SEGMENT and self.layer_h:  # no width comments
                            w = de * FILAMENT_AREA / (path_len * self.layer_h[-1])
                        for (ax, ay), (bx, by) in zip(pts, pts[1:]):
                            segs.append((ax, ay, bx, by, nz, layer, feature, w, flow, tool))
                    x, y, z = nx, ny, nz
        self.segs = np.array(segs, dtype=float).reshape(-1, 10)
        self.tools = sorted(set(self.segs[:, TOOL].astype(int)))
        # Several filaments: draw in their real colours instead of by feature.
        self.by_tool = len(self.tools) > 1 and len(self.filament_colours) > max(self.tools)
        self.layers = len(self.layer_z)
        caps = [c for c in (self.filament_flow_cap, NOZZLE_FLOW_LIMIT.get(self.nozzle)) if c]
        self.flow_limit = min(caps) if caps else None

    def _fid(self, name: str) -> int:
        if name not in self.features:
            self.features.append(name)
        return self.features.index(name)

    def color(self, idx: int) -> str:
        return FEATURE_COLORS.get(self.features[idx], OTHER_COLOR)

    def seg_colors(self, s: np.ndarray) -> list[str]:
        if self.by_tool:
            return [self.filament_colours[int(t)] for t in s[:, TOOL]]
        return [self.color(int(i)) for i in s[:, FEATURE]]

    def legend(self) -> list[tuple[str, str]]:
        if self.by_tool:
            return [(f"T{t} {self.filament_colours[t]}", self.filament_colours[t]) for t in self.tools]
        return [(self.features[i], self.color(i)) for i in sorted(set(self.segs[:, FEATURE].astype(int)))]

    def feature_layers(self, name: str) -> np.ndarray:
        if name not in self.features:
            return np.array([], dtype=int)
        mask = self.segs[:, FEATURE] == self.features.index(name)
        return np.unique(self.segs[mask, LAYER]).astype(int)


def _params(words: list[str]) -> dict:
    p = {}
    for w in words[1:]:
        if w[0] in "XYZEIJRF" and len(w) > 1:
            try:
                p[w[0]] = float(w[1:])
            except ValueError:
                pass
    return p


def _arc(x0, y0, x1, y1, p, clockwise):
    cx, cy = x0 + p.get("I", 0.0), y0 + p.get("J", 0.0)
    r = math.hypot(x0 - cx, y0 - cy)
    a0, a1 = math.atan2(y0 - cy, x0 - cx), math.atan2(y1 - cy, x1 - cx)
    sweep = a1 - a0
    if clockwise and sweep >= 0:
        sweep -= 2 * math.pi
    elif not clockwise and sweep <= 0:
        sweep += 2 * math.pi
    n = max(2, int(abs(sweep) * r / ARC_STEP) + 1)
    pts = [(cx + r * math.cos(a0 + sweep * i / n), cy + r * math.sin(a0 + sweep * i / n)) for i in range(n)]
    return pts + [(x1, y1)]


def _ranges(tp: Toolpath, name: str, lengths: np.ndarray) -> str:
    """Compress a feature's layers into 'z=a..b (N mm)' runs for the report."""
    layers = tp.feature_layers(name)
    mask = tp.segs[:, FEATURE] == tp.features.index(name)
    per_layer = {int(l): lengths[mask & (tp.segs[:, LAYER] == l)].sum() for l in layers}
    runs, start = [], layers[0]
    for prev, cur in zip(layers, list(layers[1:]) + [None]):
        if cur is None or cur != prev + 1:
            a, b = tp.layer_z[start], tp.layer_z[prev]
            mm = sum(per_layer[l] for l in range(start, prev + 1))
            runs.append(f"{a:.2f}" if start == prev else f"{a:.2f}..{b:.2f}")
            runs[-1] += f" ({mm:.0f} mm)"
            start = cur
    return "z=" + ", ".join(runs[:8]) + (" ..." if len(runs) > 8 else "")


def report(tp: Toolpath) -> None:
    s = tp.segs
    lengths = np.hypot(s[:, X1] - s[:, X0], s[:, Y1] - s[:, Y0])
    grams = tp.filament_mm * FILAMENT_AREA / 1000 * tp.density
    print(f"layers           : {tp.layers} (first {tp.layer_h[0]:.2f} mm, then {np.median(tp.layer_h):.2f} mm)")
    print(f"height           : {max(tp.layer_z):.2f} mm")
    if tp.time_min is not None:
        print(f"print time       : {int(tp.time_min // 60)} h {tp.time_min % 60:.0f} min (slicer estimate)")
    print(f"filament         : {tp.filament_mm / 1000:.2f} m, {grams:.1f} g extruded by the G-code"
          + (f"; slicer total {sum(tp.grams_per_tool):.1f} g incl. colour-change purge"
             if len(tp.grams_per_tool) > 1 else ""))
    if len(tp.tools) > 1:
        tower = s[:, FEATURE] == tp.features.index("Prime tower") if "Prime tower" in tp.features else 0 * lengths
        print(f"filament changes : {tp.tool_changes}")
        for t in tp.tools:
            on_model = (s[:, TOOL] == t) & ~tower.astype(bool)
            used = tp.grams_per_tool[t] if t < len(tp.grams_per_tool) else float("nan")
            print(f"  T{t} {tp.filament_colours[t] if t < len(tp.filament_colours) else '?':8} {used:6.1f} g used,"
                  f" {lengths[on_model].sum() / 1000:6.2f} m of path on the model")
        print(f"  prime tower: {lengths[tower.astype(bool)].sum() / 1000:.1f} m of {lengths.sum() / 1000:.1f} m path;"
              " purge between colours is not drawn (it goes to the chute or into infill)")
        flush = CFG["flush_mm3_per_change"]
        print(f"  purge estimate: {tp.tool_changes} x {flush} mm^3 = {tp.tool_changes * flush / 1000 * tp.density:.1f} g"
              " (flush_mm3_per_change in printer.json)")
    limit = f"{tp.flow_limit:g}" if tp.flow_limit else "?"
    print(f"nozzle           : {tp.nozzle} mm, flow limit {limit} mm^3/s")
    print("by feature (path length, share, median line width, max flow):")
    total = lengths.sum()
    for idx in np.argsort([-lengths[s[:, FEATURE] == i].sum() for i in range(len(tp.features))]):
        mask = s[:, FEATURE] == idx
        ln = lengths[mask].sum()
        if ln > 0:
            print(f"  {tp.features[idx]:22} {ln / 1000:7.2f} m  {100 * ln / total:5.1f}%"
                  f"  {np.median(s[mask, WIDTH]):.2f} mm  {s[mask, FLOW].max():5.1f} mm^3/s")
    alerts = [(name, tp.feature_layers(name)) for name in ALERT_FEATURES]
    alerts = [(n, l) for n, l in alerts if len(l)]
    # 2% slack: the slicer caps moves at exactly the limit and E rounding lands a hair above it.
    over = s[:, FLOW] > tp.flow_limit * 1.02 if tp.flow_limit else np.zeros(len(s), dtype=bool)
    clean = not alerts and not over.any()
    print("ALERTS           :" + (" none (no bridges, supports, overhang walls or flow over limit)" if clean else ""))
    for name, layers in alerts:
        print(f"  {name:22} {len(layers)} layers, {_ranges(tp, name, lengths)}")
    if over.any():
        worst = {tp.features[int(f)] for f in s[over, FEATURE]}
        print(f"  {'Flow over limit':22} up to {s[:, FLOW].max():.1f} mm^3/s > {limit}"
              f" on {100 * lengths[over].sum() / total:.0f}% of the path ({', '.join(sorted(worst))})")


def render_3d(tp: Toolpath, out: Path) -> None:
    s = tp.segs
    if "Prime tower" in tp.features:  # it sits far away and dwarfs a small model
        s = s[s[:, FEATURE] != tp.features.index("Prime tower")]
    n = len(s)
    points = np.empty((2 * n, 3))
    points[0::2] = s[:, [X0, Y0, Z]]
    points[1::2] = s[:, [X1, Y1, Z]]
    lines = np.column_stack([np.full(n, 2), np.arange(0, 2 * n, 2), np.arange(1, 2 * n, 2)]).ravel()
    poly = pv.PolyData(points, lines=lines)
    if tp.by_tool:
        poly.cell_data["id"] = s[:, TOOL]
        colors = tp.filament_colours
    else:
        poly.cell_data["id"] = s[:, FEATURE]
        colors = [tp.color(i) for i in range(len(tp.features))]

    plotter = pv.Plotter(shape=(1, 2), off_screen=True, window_size=(2000, 1000))
    plotter.set_background("#b8bec6" if tp.by_tool else "white")
    for col, direction in enumerate([(1, -1, 0.8), (-1, 1, 0.8)]):
        plotter.subplot(0, col)
        plotter.add_mesh(
            poly, scalars="id", cmap=colors, clim=[-0.5, len(colors) - 0.5],
            n_colors=len(colors), show_scalar_bar=False, line_width=2,
        )
        plotter.view_vector(direction, viewup=(0, 0, 1))
        plotter.enable_parallel_projection()
        plotter.reset_camera()
        if col == 0:
            plotter.add_legend([list(item) for item in tp.legend()], bcolor="#7f8790" if tp.by_tool else "white",
                               size=(0.2, 0.25), loc="upper right")
        plotter.add_text("toolpaths, front-right" if col == 0 else "toolpaths, back-left", font_size=10)
    plotter.screenshot(str(out))
    plotter.close()
    print(f"toolpaths        : {out}")


def pick_layers(tp: Toolpath, heights: list[float] | None, count: int = 8) -> list[int]:
    zs = np.array(tp.layer_z)
    if heights:
        return sorted({int(np.argmin(np.abs(zs - h))) for h in heights})
    last = tp.layers - 1
    chosen = {0, min(1, last), last}
    # The first layer of every contiguous run of a problem feature: that is
    # where the slicer starts printing over air.
    for name in ALERT_FEATURES:
        layers = tp.feature_layers(name)
        for start in layers[np.r_[True, np.diff(layers) > 1]] if len(layers) else []:
            if len(chosen) < count - 2:
                chosen.add(int(start))
    for idx in np.linspace(2, last - 1, max(count - len(chosen), 0) + 2)[1:-1]:
        if len(chosen) < count:
            chosen.add(int(round(idx)))
    return sorted(i for i in chosen if 0 <= i <= last)


def render_layers(tp: Toolpath, chosen: list[int], out: Path) -> None:
    cols = min(4, len(chosen))
    rows = math.ceil(len(chosen) / cols)
    fig, axes = plt.subplots(rows, cols, figsize=(5 * cols, 5 * rows + 0.6), dpi=110, squeeze=False)
    per_axis = []
    # Zoom on the model: the prime tower sits far away and would shrink it.
    model = tp.segs[:, FEATURE] != tp.features.index("Prime tower") if "Prime tower" in tp.features else True
    for ax, idx in zip(axes.flat, chosen):
        s = tp.segs[(tp.segs[:, LAYER] == idx) & model]
        xs, ys = np.r_[s[:, X0], s[:, X1]], np.r_[s[:, Y0], s[:, Y1]]
        pad = 1.0 + s[:, WIDTH].max()
        ax.set_xlim(xs.min() - pad, xs.max() + pad)
        ax.set_ylim(ys.min() - pad, ys.max() + pad)
        ax.set_aspect("equal")
        if tp.by_tool:
            ax.set_facecolor("#b8bec6")
        present = sorted({tp.features[int(i)] for i in s[:, FEATURE]} & set(ALERT_FEATURES))
        title = f"layer {idx + 1}/{tp.layers}  z={tp.layer_z[idx]:.2f}"
        ax.set_title(title + (f"\n{', '.join(present)}" if present else ""), fontsize=10,
                     color="#c00000" if present else "black")
        ax.tick_params(labelsize=7)
        per_axis.append((ax, s))
    for ax in axes.flat[len(chosen):]:
        ax.axis("off")
    legend = tp.legend()
    fig.legend(handles=[Patch(facecolor=c, edgecolor="#555555", label=n) for n, c in legend],
               loc="lower center", ncol=min(len(legend), 8), fontsize=8)
    fig.tight_layout(rect=(0, 0.05, 1, 1))
    fig.canvas.draw()
    # Line widths are in points; convert each extrusion width from mm so the
    # drawing shows real bead widths and the gaps between them.
    for ax, s in per_axis:
        x0, x1 = ax.get_xlim()
        pt_per_mm = ax.get_window_extent().width / (x1 - x0) * 72 / fig.dpi
        segments = s[:, [X0, Y0, X1, Y1]].reshape(-1, 2, 2)
        colors = tp.seg_colors(s)
        ax.add_collection(LineCollection(segments, colors=colors, linewidths=s[:, WIDTH] * pt_per_mm,
                                         capstyle="round", joinstyle="round"))
    fig.savefig(out)
    plt.close(fig)
    print(f"layers           : {out}")


def _minutes(text: str) -> float | None:
    """'1d 2h 3m 4s' (any subset) in minutes."""
    parts = re.findall(r"(\d+(?:\.\d+)?)\s*([dhms])\b", text)
    scale = {"d": 1440.0, "h": 60.0, "m": 1.0, "s": 1 / 60}
    return round(sum(float(v) * scale[u] for v, u in parts), 1) if parts else None


def summary(tp: Toolpath) -> dict:
    """The numbers a price or a plan needs, in plain units."""
    extruded = tp.filament_mm * FILAMENT_AREA / 1000 * tp.density
    return {
        "minutes": tp.time_min,  # the slicer's estimate, without the time of colour changes
        "grams": round(sum(tp.grams_per_tool), 2) if tp.grams_per_tool else round(extruded, 2),
        "grams_per_tool": tp.grams_per_tool,
        "tool_changes": tp.tool_changes,
        "tools": len(tp.tools),
        "layers": tp.layers,
        "height": round(max(tp.layer_z), 2) if tp.layer_z else None,
        "nozzle": tp.nozzle,
    }


def analyze(gcode: Path, toolpaths_png: Path, layers_png: Path, heights=None) -> Toolpath:
    """Report, images, and summary.json next to the G-code."""
    tp = Toolpath(gcode)
    report(tp)
    (Path(gcode).parent / "summary.json").write_text(json.dumps(summary(tp), indent=1), encoding="utf-8")
    render_3d(tp, toolpaths_png)
    render_layers(tp, pick_layers(tp, heights), layers_png)
    return tp


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("gcode", type=Path)
    parser.add_argument("--layers", help="comma-separated Z heights to draw")
    args = parser.parse_args()
    heights = [float(z) for z in args.layers.split(",")] if args.layers else None
    out = args.gcode.parent
    analyze(args.gcode, out / "toolpaths.png", out / "layers.png", heights)
    return 0


if __name__ == "__main__":
    sys.exit(main())
