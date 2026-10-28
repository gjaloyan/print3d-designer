"""Egg buddy in a tilted beanie: template for ROUND figurines from a picture.

(For box-like figures - gift boxes, blocks, cushions - start from
box_template.py instead.)

Copy this file AND scripts/shapes.py into models/<name>/ (or set
PRINT3D_SCRIPTS to the skill's scripts folder), rename it, and replace the
demo numbers with the reference's. The demo uses the patterns the real
models needed:

- Built at the reference's own scale (rows measured with
  measure_reference.py, widths from the FRONT view, depth from the SIDE
  view) and scaled to HEIGHT at the end; sizes that must survive printing
  (strokes, inlay depth) are in FINAL mm via mm().
- The body is a revolved PCHIP profile squeezed front-to-back by DEPTH; the
  profile starts with a 50-degree rise: a flat base with no overhang.
- A tilted rim (hat brim) gets a 50-degree ruled skirt into the body.
- Face features are skin-deep inlays (colour parts) or engravings (mono).
- The agreed answers of the question round go in this docstring.

Front faces -Y, Z is up. Outputs next to this file:
  <stem>.stl / <stem>.step    one material, face engraved
  parts/<colour>.stl          colour split for make_3mf.py / compare_views.py
"""

import os
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path[:0] = [str(HERE), os.environ.get("PRINT3D_SCRIPTS", "")]
from shapes import *  # noqa: E402,F401,F403  (shapes.py next to this file, or in PRINT3D_SCRIPTS)

STEM = Path(__file__).stem
HEIGHT = 30.0  # final height, mm
DESIGN_H = 35.0  # the height everything below is drawn at (the reference's scale)
S = HEIGHT / DESIGN_H


def mm(final: float) -> float:
    """Final-size mm -> design units."""
    return final / S


DEPTH = 0.9  # side-view width / front-view width
# (half-width, z) from the front view, every other measured row. The first
# segment rises at 50 degrees (the base); the top closes flat inside the cap.
BODY = [(10.4, 0.0), (12.4, 2.4), (14.4, 5.4), (15.6, 9.0), (15.8, 13.0), (14.9, 17.5), (13.2, 21.5),
        (10.6, 25.0), (7.0, 28.0)]
# The rim must stay outside the head all round: where it dips under the
# surface one colour becomes a thin wedge over the other (ray_colors skin).
CAP_TILT, CAP_POS = 8.0, (0.0, 0.0, 23.0)  # rim-bottom centre; the top leans back (+Y)
CAP_R, CAP_BAND, DOME_H, POM_R = 13.6, 3.0, 9.5, 3.2
SKIRT_IN, SKIRT_DEG = 4.0, 50.0
STROKE, INLAY, ENGRAVE = mm(0.5), mm(0.6), mm(0.5)  # 0.5 mm strokes: >= 2 lines of a 0.2 nozzle


def cap() -> Part:
    """Band + dome + pom-pom, upright in its own frame (rim at z = 0), then tilted."""
    r, h = CAP_R, CAP_BAND
    curve = (Line((0, 0), (r, 0)) + Line((r, 0), (r, h)) + EllipticalCenterArc((0, h), r, DOME_H, 0, arc_size=90)
             + Line((0, h + DOME_H), (0, 0)))
    pom = ball((0, 0, h + DOME_H + POM_R * 0.4), POM_R)
    return tilted(CAP_POS, CAP_TILT) * (revolved(curve) + pom)


def face() -> dict[str, Sketch]:
    """Front-view drawings of the features, at design scale."""
    eyes = strokes([CenterArc((sx * 4.6, 15.6), 1.8, 25, 130) for sx in (-1, 1)], STROKE)
    nose = Pos(0, 13.4) * Circle(1.5)
    return {"black": eyes, "orange": nose}


def build() -> dict[str, Part]:
    body = profile_solid(BODY, DEPTH)
    hat = cap() + rim_skirt(tilted(CAP_POS, CAP_TILT), CAP_R, SKIRT_IN, SKIRT_DEG)

    inlay_skin = skin(body, profile_solid(BODY, DEPTH, -INLAY), front_of())
    inlays = {colour: inlay(sk, inlay_skin) for colour, sk in face().items()}
    engrave_skin = skin(body, profile_solid(BODY, DEPTH, -ENGRAVE), front_of())
    engraved = [inlay(sk, engrave_skin) for sk in face().values()]

    # White wins inside the body: the colour border is the visible line where
    # the cap leaves the head, never a thin teal wedge under white.
    teal = hat - body
    parts = {"teal": teal, **inlays}
    parts["white"] = body - teal - list(inlays.values())
    parts["mono"] = body + hat - engraved
    return {colour: scaled(part, S) for colour, part in parts.items()}


if __name__ == "__main__":
    # Squeezed revolves and lofts are B-splines: export them fine or they facet.
    export_parts(build(), HERE, STEM, tolerance=0.003, angular_tolerance=0.05)
