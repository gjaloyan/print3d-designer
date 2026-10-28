"""List where a mesh overhangs: downward faces grouped into clusters with their boxes.

Usage:
    python scripts/overhang_spots.py model.stl [--support 30] [--marginal 45] [--top 8]

The overhang map in check_model.py shows THAT something overhangs; this says
WHERE (x/y/z box and area of each patch), so you can find the feature in the
model code. Faces within 0.05 mm of the lowest point lie on the bed and are
skipped. Slopes are measured from horizontal: below --support the slicer
generates support, below --marginal PETG droops.
"""

import argparse
import sys
from pathlib import Path

import numpy as np
import trimesh


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("mesh", type=Path)
    parser.add_argument("--support", type=float, default=30.0)
    parser.add_argument("--marginal", type=float, default=45.0)
    parser.add_argument("--top", type=int, default=8, help="largest patches to list per class")
    args = parser.parse_args()

    mesh = trimesh.load_mesh(args.mesh, force="mesh")
    n, c, a = mesh.face_normals, mesh.triangles_center, mesh.area_faces
    slope = np.degrees(np.arccos(np.clip(-n[:, 2], -1, 1)))
    down = (n[:, 2] < -1e-6) & (c[:, 2] - mesh.bounds[0][2] > 0.05)
    classes = ((f"support <{args.support:g}", down & (slope < args.support)),
               (f"marginal {args.support:g}-{args.marginal:g}", down & (slope >= args.support) & (slope < args.marginal)))
    for label, mask in classes:
        idx = np.where(mask)[0]
        print(f"{label}: {a[idx].sum():.1f} mm^2 in {len(idx)} faces")
        if not len(idx):
            continue
        sub = mesh.submesh([idx], append=True, repair=False)
        # repair=False: trimesh's repair needs networkx and patches holes silently.
        for part in sorted(sub.split(only_watertight=False, repair=False), key=lambda p: -p.area)[:args.top]:
            lo, hi = part.bounds
            print(f"   {part.area:7.2f} mm^2  x {lo[0]:7.2f}..{hi[0]:7.2f}  y {lo[1]:7.2f}..{hi[1]:7.2f}"
                  f"  z {lo[2]:6.2f}..{hi[2]:6.2f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
