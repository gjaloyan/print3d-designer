"""Tested build123d shapes for printable figurines (print3d-designer skill).

Copy this file next to a model script (models/<name>/shapes.py) or put the
skill's scripts/ folder on sys.path, then `from shapes import *`. Every
function here comes from a model that was built, sliced and checked; the
docstrings say what each one is for and which trap it avoids. Units are
design units (often the reference picture's pixels), front faces -Y, Z is up,
the bed is z = 0. Scale once at the end with scaled().

Feature in the picture -> function:
  ball, egg, cone, tiers (round from above) ... profile_solid, revolved, ball, spheroid, ellipsoid
  soft box, pudding, cushion, block ........... rounded_box
  bow loops, petals, ears, leaves, wings ...... lobe
  tilted hat cuff / brim / rim ................ tilted, rim_skirt
  arms, legs, a ball hanging off the body ..... capsule, support_cone
  eyes, mouth, lines, grooves ................. strokes, tapered_stroke, engrave, inlay, skin
  knit, ribs .................................. raised_ribs, band_grooves, v_grooves
  placing and cutting ......................... front_of, behind, above, below, prism_y, scaled
  output ...................................... export_parts, export_clean_stl

Run `python shapes.py` to build every shape once and check it is a valid solid.
"""

import math
import sys
from pathlib import Path

import numpy as np
import trimesh
from build123d import *  # noqa: F401,F403 - the model scripts use the same names
from scipy.interpolate import PchipInterpolator

BIG = 4000.0  # helper solids are this big: keep designs well inside +-BIG/2


# ---------- bodies ----------

def revolved(curve, arc: float = 360) -> Part:
    """Revolve a closed (r, z) profile drawn in XY around the Z axis."""
    return revolve(Plane.XZ * make_face(curve), Axis.Z, revolution_arc=arc)


def profile_solid(points, depth: float = 1.0, grow: float = 0.0, samples: int = 40) -> Part:
    """Body of revolution through measured (half-width, z) rows, bottom to top.

    PCHIP never overshoots between rows. Thin pixel rows to every 2nd-3rd one
    first, or the surface bands. `depth` squeezes it front-to-back (side
    view width / front view width); `grow` offsets it outwards (negative:
    inwards, for skins). Start the profile with a 50-degree rise for a flat,
    printable base. The top is closed flat, so end the profile inside
    another part or at a small radius - never ON the axis: a spline that
    ends on the axis tessellates into thousands of loose triangles.
    """
    r = PchipInterpolator([z for _, z in points], [r for r, _ in points])
    zs = np.linspace(points[0][1], points[-1][1], samples)
    pts = [(float(r(z)) + grow, float(z)) for z in zs]
    top = pts[-1][1]
    curve = Line((0, 0), pts[0]) + Spline(*pts) + Line(pts[-1], (0, top)) + Line((0, top), (0, 0))
    solid = revolved(curve)
    return scale(solid, by=(1, depth, 1)) if depth != 1.0 else solid


def ball(center, r: float) -> Part:
    """A true sphere. Use this for every ball: a revolved ellipse with equal
    radii shattered into loose triangles once booleans had trimmed it."""
    return Pos(*center) * Sphere(r)


def spheroid(center, r_eq: float, r_axis: float, axis: str = "z") -> Part:
    """Ellipsoid of revolution from an exact ellipse (scaling a Sphere
    non-uniformly tessellates lumpy). For equal radii use ball()."""
    curve = EllipticalCenterArc((0, 0), r_eq, r_axis, -90, arc_size=180) + Line((0, r_axis), (0, -r_axis))
    solid = revolved(curve)
    if axis == "y":
        solid = Rot(90, 0, 0) * solid
    elif axis == "x":
        solid = Rot(0, 90, 0) * solid
    return Pos(*center) * solid


def ellipsoid(center, a: float, b: float, c: float) -> Part:
    """Half-axes a (x), b (y), c (z): a spheroid squeezed along Y."""
    return Pos(*center) * scale(spheroid((0, 0, 0), a, c), by=(1, b / a, 1))


def rounded_box(levels, corner_r: float, lid_round: float = 0.0, base_chamfer: float = 0.0,
                chamfer_deg: float = 50.0, inset: float = 0.0, sections: int = 13) -> Part:
    """A soft box: loft through rounded rectangles that follow the walls.

    levels: (z, half_width, half_depth) rows, bottom to top - half-width from
    the FRONT view, half-depth from the SIDE view (they differ: the gift box
    was 0.8 as deep as wide and narrower at the lid than at the bottom).
    corner_r rounds the vertical edges, lid_round the lid's edges (fillet),
    base_chamfer cuts the bottom edge back by that much at chamfer_deg (a
    rounded bottom edge would hang). `inset` shrinks every section - use it
    for the inner wall of an engraving skin (with no chamfer or lid round).
    """
    zs_m = [lv[0] for lv in levels]
    w = PchipInterpolator(zs_m, [lv[1] for lv in levels])
    d = PchipInterpolator(zs_m, [lv[2] for lv in levels])
    zs = np.linspace(zs_m[0], zs_m[-1], sections)
    body = loft([Plane.XY.offset(float(z)) * RectangleRounded(2 * (float(w(z)) - inset), 2 * (float(d(z)) - inset),
                                                             corner_r - inset) for z in zs])
    if base_chamfer:
        t = math.tan(math.radians(chamfer_deg))
        w0, d0, r0 = float(w(zs[0])) - base_chamfer, float(d(zs[0])) - base_chamfer, corner_r - base_chamfer
        rise = zs[-1] - zs[0] + 20.0  # taller than the box: an intersection keeps only what is inside
        frustum = loft([Plane.XY.offset(zs[0]) * RectangleRounded(2 * w0, 2 * d0, max(r0, 0.5)),
                        Plane.XY.offset(zs[0] + rise) * RectangleRounded(2 * (w0 + rise / t), 2 * (d0 + rise / t),
                                                                         max(r0, 0.5) + rise / t)], ruled=True)
        body = body & frustum
    if lid_round:
        body = fillet(body.edges().group_by(Axis.Z)[-1], lid_round)
    return body


def lobe(sections, z0: float = 0.0, cap: float = 10.0, both: bool = False) -> Part:
    """A puffy lobe along +X - a bow loop, petal, ear, leaf.

    sections: (x, half_depth_y, height_z) across the lobe, from the root to
    its widest end; the loft goes through ellipses centred at height z0 and
    an ellipsoid of the last section closes the end round (`cap` = its
    length). Put z0 ON the surface the lobe lies on: the lower half is then
    inside the part below and nothing hangs. Rotate the result about Z to
    point it elsewhere; both=True adds the mirror image on -X.
    Traps it avoids: two joined ellipsoids read as a row of bumps; ending the
    loft with ever smaller sections made it overshoot and broke a face.
    """
    shape = Pos(0, 0, z0) * loft([Plane.YZ.offset(x) * Ellipse(b, c) for x, b, c in sections])
    if cap:
        x, b, c = sections[-1]
        shape += ellipsoid((x, 0, z0), cap, b, c)
    return shape + mirror(shape, Plane.YZ) if both else shape


# ---------- placement and cutting ----------

def scaled(shape: Part, factor: float) -> Part:
    """Uniform scale about the origin. scale() ignores a shape's own Location
    (from Pos(...) * shape) - a star once landed 50 mm too high - so bake it
    in with a boolean first."""
    return scale(shape & Box(BIG, BIG, BIG), factor)


def front_of(y: float = 0.0) -> Part:
    """Half-space y < y (the front)."""
    return Pos(0, y - BIG / 4, 0) * Box(BIG, BIG / 2, BIG)


def behind(y: float = 0.0) -> Part:
    return Pos(0, y + BIG / 4, 0) * Box(BIG, BIG / 2, BIG)


def above(z: float) -> Part:
    return Pos(0, 0, z + BIG / 4) * Box(BIG, BIG, BIG / 2)


def below(z: float) -> Part:
    return Pos(0, 0, z - BIG / 4) * Box(BIG, BIG, BIG / 2)


def prism_y(sketch, length: float = 1000.0) -> Part:
    """Push a front-view (XZ) drawing through the model along Y."""
    return extrude(Plane.XZ * sketch, amount=length / 2, both=True)


def skin(outer: Part, inner: Part, region: Part) -> Part:
    """The layer between a surface and its inward offset, inside a region."""
    return (outer - inner) & region


def tilted(pos, tilt_deg: float) -> Location:
    """Frame for a part built upright and then tilted back: the top leans to
    +Y (backwards). Build the hat/cuff with its rim at z = 0, then frame * hat."""
    return Pos(*pos) * Rot(-tilt_deg, 0, 0)


def rim_skirt(frame: Location, radius: float, inset: float, deg: float = 50.0) -> Part:
    """Printable underside of a (tilted) rim: a ruled band from the rim
    circle down and inwards at `deg`, ending inside the part below. Make the
    rim's bottom edge sharp - a rounded edge sticks out below the skirt."""
    rim = frame * Circle(radius)
    k = (radius - inset) / radius
    inner = Pos(0, 0, -inset * math.tan(math.radians(deg))) * scale(rim, by=(k, k, 1))
    return loft([rim, inner], ruled=True)


def capsule(a: Vector, b: Vector, radius: float) -> Part:
    """Rounded rod from a to b (arms, legs)."""
    axis = b - a
    rod = Plane(origin=a, z_dir=axis) * Cylinder(radius, axis.length, align=(Align.CENTER, Align.CENTER, Align.MIN))
    return rod + Pos(a) * Sphere(radius) + Pos(b) * Sphere(radius)


def support_cone(center: Vector, radius: float, apex: Vector) -> Part:
    """Cone from `apex` (inside the body) tangent to the sphere (center,
    radius): holds up the round lower end of an arm or a hanging ball. Aim
    it 55-60 degrees down into the body."""
    axis = center - apex
    length = axis.length
    height = (length**2 - radius**2) / length
    top_r = radius * math.sqrt(length**2 - radius**2) / length
    return Plane(origin=apex, z_dir=axis) * Cone(0, top_r, height, align=(Align.CENTER, Align.CENTER, Align.MIN))


# ---------- strokes, inlays, engravings ----------

def strokes(edges, width: float) -> Sketch:
    """Round-ended strokes along arcs/lines (eyes, smiles): sum of SlotArcs.
    Keep width >= 2 line widths in FINAL mm (0.5 mm on a 0.2 nozzle)."""
    shapes = [SlotArc(e.edge() if hasattr(e, "edge") else e, width) for e in edges]
    return sum(shapes[1:], shapes[0])


def tapered_stroke(edge, width: float, n: int = 24) -> Sketch:
    """A stroke that narrows to points at both ends: as a groove on a steep
    wall it has no flat ceiling at its upper end (arm lines, folds)."""
    left, right = [], []
    for i in range(n + 1):
        t = i / n
        p, tan = edge.position_at(t), edge.tangent_at(t)
        nrm = Vector(-tan.Y, tan.X)
        half = width / 2 * math.sin(math.pi * t) ** 0.6
        left.append((p.X + nrm.X * half, p.Y + nrm.Y * half))
        right.append((p.X - nrm.X * half, p.Y - nrm.Y * half))
    return Sketch() + make_face(Polyline(*(left + right[::-1][1:-1]), close=True))


def inlay(sketch, skin_solid: Part) -> Part:
    """Flush colour piece: the skin under a front-view drawing. Subtract it
    from the body colour and give it its own colour (one STL per colour)."""
    return skin_solid & prism_y(sketch)


def engrave(sketch, wall_y: float, skin_solid: Part, angle: float = 45.0) -> Part:
    """Groove to subtract: the drawing cut into the wall by a prism that runs
    in and DOWN at `angle`. From the front it looks like a straight cut, but
    every groove's top wall slopes at `angle` instead of being a flat
    ceiling (gift box: overhang < 30 deg went from 3.7 mm^2 to 0).
    wall_y: the wall's y at the drawing (negative at the front)."""
    a = math.radians(angle)
    plane = Plane.XZ.offset(-wall_y)
    cutter = extrude(plane * sketch, amount=BIG / 8, dir=(0, math.cos(a), -math.sin(a)), both=True)
    return skin_solid & cutter


# ---------- knit and ribs ----------

def radial_slabs(count: int, width: float, size: float, z_mid: float, height: float) -> Part:
    """`count` thin slabs through the Z axis, evenly turned (2 ribs each)."""
    slabs = [Rot(0, 0, i * 180 / count) * Pos(0, 0, z_mid) * Box(size, width, height) for i in range(count)]
    return slabs[0].fuse(*slabs[1:])


def raised_ribs(outer: Part, inner: Part, ribs: int, width: float, size: float, z_mid: float, height: float) -> Part:
    """Ribs lying ON a dome: the shell between two domes cut by radial slabs.
    Raised ribs, not cut grooves - grooves end in ceilings on a flat crown.
    `shape & [a, b]` intersects with every item in turn, so the slabs are
    fused first."""
    return (outer - inner) & radial_slabs(ribs // 2, width, size, z_mid, height)


def band_grooves(radius: float, count: int, width: float, depth: float, z0: float, z1: float) -> Part:
    """Vertical grooves round a band (a cuff), to subtract. They run out
    through both edges, so none ends in a ceiling; stop them at the band's
    top or they notch whatever sits above."""
    boxes = [Rot(0, 0, (i + 0.5) * 360 / count) * Pos(radius, 0, (z0 + z1) / 2) * Box(2 * depth, width, z1 - z0)
             for i in range(count)]
    return boxes[0].fuse(*boxes[1:])


def v_grooves(radius: float, zs, depth: float) -> Part:
    """Horizontal V-grooves with 45-degree flanks round a ring, to subtract."""
    cuts = [revolved(Polyline((radius + 1, z - depth - 1), (radius - depth, z), (radius + 1, z + depth + 1), close=True))
            for z in zs]
    return sum(cuts[1:], cuts[0])


# ---------- output ----------

def export_clean_stl(shape, path: Path, tolerance: float = 0.003, angular_tolerance: float = 0.05,
                     max_debris: int = 8) -> int:
    """STL without OCC's few degenerate triangles at sphere poles. More loose
    bits than max_debris is a broken surface, not debris: the file is left as
    exported and a warning printed. Tolerances are in FINAL mm."""
    path = Path(path)
    export_stl(shape, str(path), tolerance=tolerance, angular_tolerance=angular_tolerance)
    mesh = trimesh.load_mesh(path, force="mesh")
    pieces = mesh.split(only_watertight=False, repair=False)  # never repair: it hides real holes
    kept = [p for p in pieces if len(p.faces) >= 4]
    dropped = len(pieces) - len(kept)
    if dropped > max_debris:
        print(f"WARNING {path.name}: {dropped} loose triangle groups - degenerate surface"
              " (spline pole on the axis? revolved equal-radii ellipse?); fix the model, file not cleaned")
        return 0
    if dropped:
        trimesh.util.concatenate(kept).export(path)
    return dropped


def export_parts(parts: dict, folder: Path, stem: str, step: bool = True, **fine) -> None:
    """Write parts["mono"] as <stem>.stl (+ .step) and every other entry as
    parts/<colour>.stl. Name colour parts after colours (red, white, teal...):
    render_parts.py and compare_views.py colour them by name."""
    folder = Path(folder)
    parts = dict(parts)
    mono = parts.pop("mono", None)
    debris = 0
    if mono is not None:
        debris += export_clean_stl(mono, folder / f"{stem}.stl", **fine)
        if step:
            export_step(mono, str(folder / f"{stem}.step"))
    if parts:
        (folder / "parts").mkdir(exist_ok=True)
        for colour, part in parts.items():
            debris += export_clean_stl(part, folder / "parts" / f"{colour}.stl", **fine)
    print("parts:", ", ".join(f"{c} {p.volume:.1f} mm3" for c, p in parts.items()) or "-")
    if debris:
        print(f"dropped {debris} degenerate tessellation fragments")


# ---------- self-check ----------

def _check() -> int:
    """Build every shape once; each must be one valid solid."""
    cases = {
        "profile_solid": lambda: profile_solid([(10, 0), (14, 6), (15, 14), (11, 22), (6, 26)], depth=0.9),
        "ball": lambda: ball((0, 0, 10), 8),
        "spheroid": lambda: spheroid((0, 0, 10), 8, 5),
        "ellipsoid": lambda: ellipsoid((0, 0, 10), 8, 5, 4),
        "rounded_box": lambda: rounded_box([(0, 30, 24), (20, 31, 25), (50, 27, 19)], 9, lid_round=5, base_chamfer=4),
        "lobe": lambda: lobe([(3, 4, 3), (10, 9, 5), (16, 10, 6)], z0=0, cap=4, both=True),
        "rim_skirt": lambda: rim_skirt(tilted((0, 0, 20), 20), 12, 5),
        "capsule": lambda: capsule(Vector(0, 0, 0), Vector(10, 0, 10), 2),
        "support_cone": lambda: support_cone(Vector(10, 0, 10), 2, Vector(4, 0, 2)),
        "engrave": lambda: engrave(strokes([CenterArc((0, 25), 4, 20, 140)], 1.0), -24.5,
                                   skin(rounded_box([(0, 30, 24), (50, 27, 19)], 9),
                                        rounded_box([(0, 30, 24), (50, 27, 19)], 9, inset=1.0), front_of(-5))),
        "raised_ribs": lambda: raised_ribs(spheroid((0, 0, 0), 11, 8), spheroid((0, 0, 0), 10, 7), 16, 0.8, 30, 5, 10),
        "band_grooves": lambda: band_grooves(10, 12, 0.8, 0.5, 0, 5),
        "v_grooves": lambda: v_grooves(10, [2, 4], 0.5),
    }
    bad = 0
    for name, make in cases.items():
        try:
            shape = make()
            ok = shape.is_valid and shape.volume > 0
            print(f"[{'OK' if ok else 'BAD'}] {name:14} volume {shape.volume:9.2f}")
            bad += not ok
        except Exception as e:  # report every failing recipe, not just the first
            print(f"[FAIL] {name:14} {type(e).__name__}: {e}")
            bad += 1
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(_check())
