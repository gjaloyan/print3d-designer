"""Smiling gift box with a white bow: template for BOX-LIKE figures from a picture.

(For round figures - snowmen, eggs, Santas - start from model_template.py.)

This is the real gift box of 2026-10-27, rebuilt only from shapes.py; it
passes compare_views.py against its picture (IoU 0.94-0.96). Copy this file
AND scripts/shapes.py into models/<name>/ (or set PRINT3D_SCRIPTS), then
replace the numbers with the reference's:

- WALLS: (z, half-width, half-depth) rows. Half-width from the FRONT view,
  half-depth from the SIDE view, measured separately - this box is only 0.8
  as deep as wide, and narrower at the lid than at the bottom. A box copied
  "by eye" as an even cube fails compare_views on the side view.
- The base: rounded_box(base_chamfer=...) cuts a 50-degree chamfer instead of
  the photo's rounded bottom edge (it would hang). The lid edges: lid_round.
- The bow: two lobes (one loft each through ellipses across the loop,
  capped round), centred ON the lid so only upper halves show, plus a knot.
- The face: engraved with engrave(): the grooves run into the wall 45
  degrees down, so they have no flat ceilings.
- Colours by height: everything above the flat lid is the bow colour - one
  filament change for the whole print.

Asked by the user: no ribbon stripes, only the white bow on top.
Front faces -Y, Z is up; 1 unit = 1 pixel of the reference sheet (front
view x from the box axis, z = 185 - y).
"""

import os
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path[:0] = [str(HERE), os.environ.get("PRINT3D_SCRIPTS", "")]
from shapes import *  # noqa: E402,F401,F403

STEM = Path(__file__).stem
HEIGHT = 25.0  # final height with the bow, mm
LID_Z = 152.0  # flat lid: in the front view the top face shows as a band y 28..38; take its middle
WALLS = [(0.0, 75.5, 59.0), (12.0, 76.5, 60.0), (25.0, 78.5, 62.0), (65.0, 78.5, 62.5), (95.0, 76.8, 57.5),
         (115.0, 74.5, 55.0), (135.0, 71.0, 51.0), (LID_Z, 68.0, 48.0)]
CORNER_R, LID_ROUND, BASE_CHAMFER = 22.0, 14.0, 10.0
# One bow loop along +X: (x, half-depth, height) across it; mirrored to -X.
LOOP = [(8.0, 9.0, 7.0), (16.0, 16.0, 10.5), (26.0, 23.0, 13.5), (36.0, 27.0, 15.0), (44.0, 25.0, 13.5)]
LOOP_CAP, KNOT = 10.0, (12.0, 15.0, 11.5)
CREASE_R = 2.6  # a sunk rod presses the ribbon's fold into each loop
DESIGN_H = LID_Z + max(c for _, _, c in LOOP)
S = HEIGHT / DESIGN_H


def mm(final: float) -> float:
    return final / S


STROKE, ENGRAVE = mm(0.6), mm(0.6)
FACE_Y = -61.0  # front wall at eye height (side-view half-depth there)
EYES = [((sx * 33.5, 72.9), 14.1, 17.0, 146.0) for sx in (-1, 1)]  # centre, radius, start, sweep
SMILE = ((0.0, 76.3), 12.3, 201.0, 138.0)


def bow() -> Part:
    loop = lobe(LOOP, z0=LID_Z, cap=LOOP_CAP)
    peak = max(c for _, _, c in LOOP)
    rod = Pos(35, 0, LID_Z + peak - 1.2 + CREASE_R) * Rot(0, 90, 0) * Cylinder(CREASE_R, 22)
    loop -= rod
    return (loop + mirror(loop, Plane.YZ) + ellipsoid((0, 0, LID_Z), *KNOT)) & above(LID_Z)


def build() -> dict[str, Part]:
    box = rounded_box(WALLS, CORNER_R, lid_round=LID_ROUND, base_chamfer=BASE_CHAMFER)
    lines = [CenterArc(c, r, a, sweep) for c, r, a, sweep in EYES + [SMILE]]
    wall_skin = skin(rounded_box(WALLS, CORNER_R), rounded_box(WALLS, CORNER_R, inset=ENGRAVE), front_of(-20))
    red = box - engrave(strokes(lines, STROKE), FACE_Y, wall_skin)
    white = bow()
    return {colour: scaled(part, S) for colour, part in {"red": red, "white": white, "mono": red + white}.items()}


if __name__ == "__main__":
    export_parts(build(), HERE, STEM, tolerance=0.003, angular_tolerance=0.05)
