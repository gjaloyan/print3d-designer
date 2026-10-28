"""Export a build123d shape to STL without tessellation debris.

OCC sometimes leaves single degenerate triangles at sphere poles. They show up
as extra loose "bodies" and open edges; slicers ignore them, but they make the
mesh checks noisy, so drop any connected piece with fewer than four faces.
"""

from pathlib import Path

import trimesh
from build123d import export_stl


def export_clean_stl(shape, path: Path, tolerance: float = 0.02, angular_tolerance: float = 0.15,
                     max_debris: int = 8) -> int:
    export_stl(shape, str(path), tolerance=tolerance, angular_tolerance=angular_tolerance)
    mesh = trimesh.load_mesh(path, force="mesh")
    # repair=False: never patch holes here, a real defect must stay visible.
    pieces = mesh.split(only_watertight=False, repair=False)
    kept = [p for p in pieces if len(p.faces) >= 4]
    dropped = len(pieces) - len(kept)
    if dropped > max_debris:
        # Thousands of loose triangles are a broken surface (a spline pole on
        # the revolve axis did this once), not pole debris: keep the evidence.
        print(f"WARNING {Path(path).name}: {dropped} loose triangle groups - degenerate surface,"
              " fix the model; file not cleaned")
        return 0
    if dropped:
        trimesh.util.concatenate(kept).export(path)
    return dropped
