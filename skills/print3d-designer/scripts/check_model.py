"""Check a mesh for printability and render a preview PNG.

Usage:
    python scripts/check_model.py model.stl [--png preview.png] [--density 1.27]

Reports: watertightness, body count, bounding box, volume, solid-mass upper
bound, whether the part fits the build volume (printer.json), and how much
downward-facing area needs support. The PNG shows isometric, top, front and
bottom (first-layer) views with dimension ticks, plus two overhang maps:
red = needs support or a bridge, orange = marginal for PETG, grey = on the bed.
"""

import argparse
import sys
from pathlib import Path

import numpy as np
import pyvista as pv
import trimesh

sys.path.insert(0, str(Path(__file__).parent))
import config  # noqa: E402

CFG = config.load()
BED = np.array(config.bed(CFG))  # printable volume, mm
PETG_DENSITY = CFG["filament"]["density"]  # g/cm^3
# Slope of a downward face, measured from horizontal. Below SUPPORT_DEG the
# slicer generates support (profile support_threshold_angle); below
# MARGINAL_DEG PETG overhangs droop visibly.
SUPPORT_DEG = 30.0
MARGINAL_DEG = 45.0
OVERHANG_COLORS = ["#d9d9d9", "#e8892b", "#f0a020", "#d62728"]  # bed, ok, marginal, support

# (title, camera direction from the part, camera up vector)
VIEWS = [
    ("isometric", (1, -1, 1), (0, 0, 1)),
    ("top", (0, 0, 1), (0, 1, 0)),
    ("front", (0, -1, 0), (0, 0, 1)),
    ("bottom (first layer)", (1, -1, -1), (0, 0, 1)),
]


def overhang_classes(normals: np.ndarray, centers_z: np.ndarray, z_min: float) -> np.ndarray:
    """Per-face class: 0 on the bed, 1 ok, 2 marginal overhang, 3 needs support."""
    slope = np.degrees(np.arccos(np.clip(-normals[:, 2], -1.0, 1.0)))
    classes = np.ones(len(normals), dtype=int)
    downward = normals[:, 2] < -1e-6
    classes[downward & (slope < MARGINAL_DEG)] = 2
    classes[downward & (slope < SUPPORT_DEG)] = 3
    classes[downward & (centers_z - z_min < 0.05)] = 0
    return classes


def report(mesh: trimesh.Trimesh, density: float) -> bool:
    bodies = mesh.split(only_watertight=False, repair=False)
    classes = overhang_classes(mesh.face_normals, mesh.triangles_center[:, 2], mesh.bounds[0][2])
    area = mesh.area_faces
    extents = mesh.bounding_box.extents
    fits = bool(np.all(np.sort(extents) <= np.sort(BED)))
    ok = mesh.is_watertight and mesh.is_winding_consistent and fits

    print(f"triangles        : {len(mesh.faces)}")
    print(f"bodies           : {len(bodies)}")
    print(f"watertight       : {mesh.is_watertight}")
    print(f"winding ok       : {mesh.is_winding_consistent}")
    print(f"size X x Y x Z   : {extents[0]:.2f} x {extents[1]:.2f} x {extents[2]:.2f} mm")
    print(f"min corner       : {np.round(mesh.bounds[0], 3).tolist()}")
    if mesh.is_volume:
        cm3 = mesh.volume / 1000.0
        print(f"volume           : {cm3:.2f} cm^3")
        print(f"mass if 100% fill: {cm3 * density:.1f} g (upper bound)")
    print(f"fits {'x'.join(f'{b:g}' for b in BED)} bed: {fits}")
    print(f"bed contact area : {area[classes == 0].sum():.0f} mm^2")
    print(f"overhang <{MARGINAL_DEG:.0f} deg : {area[classes == 2].sum():.0f} mm^2 (marginal for PETG)")
    print(f"overhang <{SUPPORT_DEG:.0f} deg : {area[classes == 3].sum():.0f} mm^2 (support or bridge)")
    print(f"RESULT           : {'OK' if ok else 'PROBLEMS'}")
    return ok


def render(path: Path, out: Path) -> None:
    mesh = pv.read(str(path)).compute_normals(cell_normals=True, point_normals=False)
    mesh.cell_data["overhang"] = overhang_classes(
        mesh.cell_data["Normals"], mesh.cell_centers().points[:, 2], mesh.bounds[4]
    )
    views = VIEWS + [
        ("overhangs from below", (1, -1, -1), (0, 0, 1)),
        ("overhangs from below, other side", (-1, 1, -1), (0, 0, 1)),
    ]
    plotter = pv.Plotter(shape=(2, 3), off_screen=True, window_size=(2100, 1200))
    for i, (title, direction, up) in enumerate(views):
        plotter.subplot(i // 3, i % 3)
        if title.startswith("overhangs"):
            plotter.add_mesh(
                mesh, scalars="overhang", cmap=OVERHANG_COLORS, clim=[0, 3],
                n_colors=4, show_scalar_bar=False, ambient=0.5, diffuse=0.6,
            )
        else:
            plotter.add_mesh(mesh, color="#e8892b", specular=0.3)
        plotter.show_bounds(font_size=8, location="outer", ticks="outside")
        plotter.add_text(title, font_size=10)
        plotter.view_vector(direction, viewup=up)
        plotter.enable_parallel_projection()
        plotter.reset_camera()
    plotter.screenshot(str(out))
    plotter.close()
    print(f"preview          : {out}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("mesh", type=Path)
    parser.add_argument("--png", type=Path, help="write a preview image here")
    parser.add_argument("--density", type=float, default=PETG_DENSITY, help="g/cm^3")
    args = parser.parse_args()

    ok = report(trimesh.load_mesh(args.mesh, force="mesh"), args.density)
    if args.png:
        render(args.mesh, args.png)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
