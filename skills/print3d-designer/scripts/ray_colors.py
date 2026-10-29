"""Ray tests on a multi-colour model (one STL per colour, in one coordinate system).

Usage:
    python scripts/ray_colors.py support parts/ [--marginal 45] [--support 30]
    python scripts/ray_colors.py skin parts/ --light white [--dark red,teal] [--min 1.0]

support: the slicer prints all parts as ONE object, so a part's downward face
  that rests on another colour is an internal interface, not an overhang.
  Every downward face shoots a ray straight down: it either rests on another
  part, hangs over the model (a gap below it) or hangs over the bed. Only the
  hanging ones need a 45-degree rule - this is how tilted brims, cuffs and
  pom-poms on top of a body were verified.

skin: a light colour printed over a dark one shows it through when the light
  layer is thin (two PETG walls let teal or red glow through white). Every
  visible face of the --light part shoots a ray inwards; if a --dark part
  starts closer than --min mm under the surface, the face is flagged. Along a
  colour border the neighbour is always close, so many small flagged patches
  there are normal; a large patch in the middle of a light area is the defect.
  Fix it with a light core (keep the light part >= 2.5 mm thick there) or a
  thicker inlay.

Flagged faces are grouped into patches on a voxel grid, so sampling (big
meshes) does not break them apart. Uses VTK's BSP tree (shipped with pyvista),
so no rtree/embree is needed; vtkOBBTree crashed the interpreter on some
meshes (VTK 9.7, Windows).
"""

import argparse
import sys
from pathlib import Path

import numpy as np
import quiet_vtk  # noqa: F401  (before pyvista)
import pyvista as pv
import trimesh
from scipy import ndimage
from vtkmodules.vtkCommonCore import vtkIdList, vtkPoints
from vtkmodules.vtkFiltersFlowPaths import vtkModifiedBSPTree

LIFT = 0.01  # mm: rays start this far outside the surface they test
EPS = 0.03  # mm: a hit closer than LIFT + EPS counts as touching


class Caster:
    def __init__(self, mesh: trimesh.Trimesh):
        # Own copies, kept alive on self: VTK may share their memory.
        self._verts = np.array(mesh.vertices, dtype=np.float64)
        self._faces = np.column_stack([np.full(len(mesh.faces), 3), mesh.faces]).ravel().astype(np.int64)
        self.poly = pv.PolyData(self._verts, self._faces)
        self.tree = vtkModifiedBSPTree()
        self.tree.SetDataSet(self.poly)
        self.tree.BuildLocator()
        self._pts, self._ids = vtkPoints(), vtkIdList()

    def hits(self, a: np.ndarray, b: np.ndarray) -> np.ndarray:
        """Sorted distances from a of every surface crossing on the segment a-b."""
        # float64 numpy points; Python lists picked a crashing overload once.
        a, b = np.ascontiguousarray(a, dtype=float), np.ascontiguousarray(b, dtype=float)
        if self.tree.IntersectWithLine(a, b, 1e-7, self._pts, self._ids) == 0:
            return np.empty(0)
        pts = np.array([self._pts.GetPoint(i) for i in range(self._pts.GetNumberOfPoints())])
        return np.sort(np.linalg.norm(pts - a, axis=1))


def load_parts(folder: Path) -> dict[str, trimesh.Trimesh]:
    parts = {f.stem: trimesh.load_mesh(f, force="mesh") for f in sorted(folder.glob("*.stl"))}
    if not parts:
        sys.exit(f"no STL files in {folder}")
    return parts


def sample(idx: np.ndarray, limit: int, rng) -> tuple[np.ndarray, float]:
    if len(idx) <= limit:
        return idx, 1.0
    return np.sort(rng.choice(idx, limit, replace=False)), len(idx) / limit


def patches(centres: np.ndarray, areas: np.ndarray, voxel: float) -> list[tuple[float, np.ndarray, np.ndarray]]:
    """(area, min corner, max corner) of face groups touching on a voxel grid, largest first."""
    if not len(centres):
        return []
    keys = np.floor(centres / voxel).astype(int)
    keys -= keys.min(axis=0)
    grid = np.zeros(keys.max(axis=0) + 1, dtype=bool)
    grid[tuple(keys.T)] = True
    labels, count = ndimage.label(grid, structure=np.ones((3, 3, 3)))
    lab = labels[tuple(keys.T)]
    out = [(areas[lab == i].sum(), centres[lab == i].min(axis=0), centres[lab == i].max(axis=0))
           for i in range(1, count + 1)]
    return sorted(out, key=lambda p: -p[0])


def print_patches(found, top: int = 6) -> None:
    for area, lo, hi in found[:top]:
        print(f"      {area:7.2f} mm^2  x {lo[0]:7.2f}..{hi[0]:7.2f}  y {lo[1]:7.2f}..{hi[1]:7.2f}"
              f"  z {lo[2]:6.2f}..{hi[2]:6.2f}")
    if len(found) > top:
        print(f"      ... {len(found) - top} smaller patches")


def voxel_for(parts: dict) -> float:
    lo = np.min([m.bounds[0] for m in parts.values()], axis=0)
    hi = np.max([m.bounds[1] for m in parts.values()], axis=0)
    return max(0.3, float((hi - lo).max()) / 150)


def support(parts: dict, marginal: float, support_deg: float, limit: int, rng) -> int:
    casters = {name: Caster(m) for name, m in parts.items()}
    z_min = min(m.bounds[0][2] for m in parts.values())
    voxel = voxel_for(parts)
    problems = 0
    for name, mesh in parts.items():
        n, c, area = mesh.face_normals, mesh.triangles_center, mesh.area_faces
        slope = np.degrees(np.arccos(np.clip(-n[:, 2], -1, 1)))
        cand = np.where((n[:, 2] < -1e-6) & (slope < marginal) & (c[:, 2] - z_min > 0.05))[0]
        cand, weight = sample(cand, limit, rng)
        rests, hang_bed, hang_model = [], [], []
        for i in cand:
            a = c[i] + np.array([0, 0, LIFT])
            b = np.array([c[i][0], c[i][1], z_min - 1.0])
            other = [d for o, cs in casters.items() if o != name for d in cs.hits(a, b)[:1]]
            if other and min(other) <= LIFT + EPS:
                rests.append(i)
                continue
            own = casters[name].hits(a, b)
            below = [*other, *own[own > LIFT + EPS]]
            (hang_model if below else hang_bed).append(i)
        hanging = np.array(hang_bed + hang_model, dtype=int)
        steep = hanging[slope[hanging] < support_deg] if len(hanging) else hanging
        print(f"== {name}: {len(cand)} downward faces under {marginal:g} deg tested"
              + (f" (sampled, areas x{weight:.1f})" if weight > 1 else ""))
        print(f"   rests on another part : {area[rests].sum() * weight:8.2f} mm^2 (interface, fine)")
        print(f"   hangs over the model  : {area[hang_model].sum() * weight:8.2f} mm^2")
        print(f"   hangs over the bed    : {area[hang_bed].sum() * weight:8.2f} mm^2")
        print(f"   of those < {support_deg:g} deg    : {area[steep].sum() * weight:8.2f} mm^2"
              " (needs support or a bridge)")
        if len(hanging):
            print("   hanging patches:")
            print_patches(patches(c[hanging], area[hanging] * weight, voxel))
        # A tiny ceiling (groove end, inlay lip) bridges; a patch the size of
        # a few lines' length squared does not.
        worst = patches(c[steep], area[steep] * weight, voxel)[:1] if len(steep) else []
        problems += int(bool(worst) and worst[0][0] > 1.0)
    print("RESULT: " + ("OK" if not problems else f"{problems} part(s) have a patch over 1 mm^2 below {support_deg:g} deg"))
    return 1 if problems else 0


def skin(parts: dict, light: str, dark: list[str], min_mm: float, depth: float, limit: int, rng) -> int:
    if light not in parts:
        sys.exit(f"no {light}.stl among {', '.join(parts)}")
    dark = dark or [p for p in parts if p != light]
    mesh = parts[light]
    others = {name: Caster(parts[name]) for name in parts if name != light}
    n, c, area = mesh.face_normals, mesh.triangles_center, mesh.area_faces
    idx, weight = sample(np.arange(len(mesh.faces)), limit, rng)
    visible, thin, depths = [], [], []
    for i in idx:
        out_a, out_b = c[i] - n[i] * LIFT, c[i] + n[i] * (LIFT + EPS)
        if any(len(cs.hits(out_a, out_b)) for cs in others.values()):
            continue  # this face touches another colour: not visible
        visible.append(i)
        a, b = c[i] + n[i] * LIFT, c[i] - n[i] * depth
        found = [cs.hits(a, b)[:1] for name, cs in others.items() if name in dark]
        d = min((float(h[0]) - LIFT for h in found if len(h)), default=None)
        if d is not None and d < min_mm:
            thin.append(i)
            depths.append(d)
    vis_area, thin_area = area[visible].sum() * weight, area[thin].sum() * weight
    print(f"== {light} over {', '.join(dark)}: {len(visible)} visible faces tested"
          + (f" (sampled, areas x{weight:.1f})" if weight > 1 else ""))
    print(f"   visible {light} surface : {vis_area:8.1f} mm^2")
    print(f"   dark closer than {min_mm:g} mm: {thin_area:8.1f} mm^2 ({100 * thin_area / max(vis_area, 1e-9):.1f}%)")
    found = []
    if thin:
        d, t = np.array(depths), np.array(thin)
        for lo, hi in ((0, 0.3), (0.3, 0.6), (0.6, 1.0), (1.0, min_mm)):
            if hi > lo:
                print(f"     {lo:.1f}-{hi:.1f} mm: {area[t[(d >= lo) & (d < hi)]].sum() * weight:7.1f} mm^2")
        found = patches(c[t], area[t] * weight, voxel_for(parts))
        print("   thin patches (borders between colours always show some small ones):")
        print_patches(found)
    biggest = found[0][0] if found else 0.0
    bad = biggest > max(1.0, 0.01 * vis_area)
    print("RESULT: " + ("OK" if not bad else f"a {biggest:.1f} mm^2 patch of {light} is thinner than {min_mm:g} mm"
                        " over a dark part"))
    return 1 if bad else 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("support", "skin"))
    parser.add_argument("parts", type=Path, help="folder of <colour>.stl files")
    parser.add_argument("--marginal", type=float, default=45.0)
    parser.add_argument("--support", type=float, default=30.0)
    parser.add_argument("--light", default="white")
    parser.add_argument("--dark", default="", help="comma-separated part names (default: all others)")
    parser.add_argument("--min", type=float, default=1.0, help="mm of light material wanted over dark")
    parser.add_argument("--depth", type=float, default=5.0, help="mm to look inwards")
    parser.add_argument("--max-rays", type=int, default=60000)
    args = parser.parse_args()

    parts = load_parts(args.parts)
    rng = np.random.default_rng(0)
    if args.mode == "support":
        return support(parts, args.marginal, args.support, args.max_rays, rng)
    dark = [d for d in args.dark.split(",") if d]
    return skin(parts, args.light, dark, args.min, args.depth, args.max_rays, rng)


if __name__ == "__main__":
    sys.exit(main())
