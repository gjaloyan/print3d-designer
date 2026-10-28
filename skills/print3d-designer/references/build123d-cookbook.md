# build123d cookbook for printable figurines

build123d 0.13 (OCC kernel), algebra mode (`a + b`, `a - b`, `a & b`). Copy
helpers from `templates/model_template.py`; this file explains why each
helper exists and lists the traps.

**Use the library first.**
- `scripts/shapes.py` holds every recipe below as a tested function:
  - `profile_solid`, `ball`, `ellipsoid`, `rounded_box`, `lobe`;
  - `tilted`, `rim_skirt`, `capsule`, `support_cone`;
  - `strokes`, `inlay`, `engrave`;
  - faces: `kawaii_face`, `check_face`, `face_preview`;
  - `raised_ribs`, `band_grooves`, `v_grooves`;
  - `scaled`, `export_parts`.
- `python shapes.py` builds them all.
- This file explains why each one is built the way it is; copy code from
  `shapes.py`, not from here.

## Contents
1. Conventions
2. Shapes that print smooth
3. Booleans and placement
4. Colour parts, inlays, engravings
5. Printability helpers
6. Export
7. Gotchas (each cost a rebuild)
8. Performance

## 1. Conventions

- Front faces **-Y**, Z up, units mm, bed at z = 0.
- Build at the **reference's scale** (e.g. the photo's object height = 80 mm)
  so measured numbers paste in directly. Scale once at the end:
  `scaled(part, HEIGHT / DESIGN_H)`.
- Keep printability-critical sizes in final mm via `mm(final)` or a
  `Variant` dataclass.
- The model script writes `<name>.stl` + `<name>.step` (one material,
  features engraved) and `parts/<colour>.stl` (colour split). Name colour
  files after colours: `render_parts.py` colours them by name.

## 2. Shapes that print smooth

```python
def revolved(curve, arc=360):            # closed (r, z) profile in XY, around Z
    return revolve(Plane.XZ * make_face(curve), Axis.Z, revolution_arc=arc)

# Body from measured (half-width, z) rows: PCHIP never overshoots between rows.
r = PchipInterpolator([z for _, z in BODY], [r for r, _ in BODY])
pts = [(float(r(z)), float(z)) for z in np.linspace(z0, z1, 40)]
curve = Line((0, 0), pts[0]) + Spline(*pts) + Line(pts[-1], (0, top)) + Line((0, top), (0, 0))
body = scale(revolved(curve), by=(1, DEPTH, 1))   # squeeze front-to-back
```

- **Balls**: use `Sphere(r)`. A revolved ellipse with equal radii tessellated into 2,670 loose
  triangles once a scarf and a hat had trimmed it (snowman in a beanie, 2026-10-26).
- **Ellipsoids**: revolve an `EllipticalCenterArc`.
  - `scale(Sphere(...), by=(a, b, c))` tessellates into a lumpy B-spline.
- **Bodies that are wider than deep**: either a revolve squeezed with
  `scale(by=(1, d, 1))`, or a loft through exact `Ellipse` sections.
  - Use 16–20 sections, with radii from a PCHIP of thinned points.
- **Thin the measured points**:
  - Keep every 2nd–3rd pixel row.
  - Pixel stair-steps fed straight into a spline or loft ripple the
    surface into visible horizontal bands.
- **Superellipse sections** when a side view is "boxier" than an ellipse:
  `fy = (1 - u**3) ** (1/3)` (snowman head: width elliptic, depth power 3).
- **Never end a profile spline ON the revolve axis.**
  - The pole tessellates into thousands of loose triangles.
  - `cleanmesh` now refuses to "clean" that.
  - Close flat inside another part, or end with an arc that meets the axis
    at 90°.

## 3. Booleans and placement

- `Pos(x, y, z) * Rot(ax, ay, az) * shape` places a shape. For a tilted
  hat, build it upright in its own frame (`hat_frame()`), then apply
  `frame * shape`.
- **`scale()` ignores a shape's own Location.** `Pos(...) * shape` keeps
  its offset unscaled, and a star once landed 50 mm above the tree. Bake
  first with `scale(shape & Box(1000, 1000, 1000), k)`.
- **`shape & [a, b]` intersects with EACH item in turn**, giving the common
  part of all of them. To intersect with the union, fuse first:
  `slabs[0].fuse(*slabs[1:])`.
- **Coplanar caps of fused lofts leave sliver faces.** Overlap the parts by
  0.2–0.3 mm (upper tree tiers start 0.3 below the top of the tier
  underneath).
- Half-spaces are big boxes: `front_of(y)`, `above(z)`,
  `slab_zh(lo, hi)` in a tilted frame.
- A "region below a 45° roof":
  `Pos(0, y0, z0) * Rot(-45, 0, 0) * Pos(0, 0, -150) * Box(400, 400, 300)`.
- `EllipticalCenterArc(center, rx, ry, start, arc_size=...)`: pass
  `arc_size` as a keyword. Six positional arguments fail.
- `Plane.XZ * Sketch()` on an empty sketch crashes. Sum the shapes first:
  `sum(shapes[1:], shapes[0])`.

## 4. Colour parts, inlays, engravings

```python
skin  = (body & front_of()) - body_offset(-depth)           # skin-deep layer of the front
prism = extrude(Plane.XZ * sketch, amount=100, both=True)   # front-view drawing pushed along Y
inlay = skin & prism                                        # flush colour piece
parts = {"black": inlay, "white": body - inlay}             # every colour = body minus the others
mono  = body - inlay                                        # same features engraved, one material
```

- Strokes: `SlotArc(CenterArc(c, r, start, sweep).edge(), width)`.
- **Engraved strokes on a wall without ceilings**: cut them with an oblique prism,
  `extrude(Plane.XZ.offset(-y_wall) * sketch, amount=40, dir=(0, 1, -1), both=True)`, intersected
  with the wall's skin. From the front the strokes look the same; every groove's top wall slopes
  at 45 degrees (gift box: overhang < 30 deg went from 3.7 mm^2 to 0). Sum
  several `SlotArc`s into one sketch.
- Use an offset body for skins (`profile_solid(..., grow=-depth)`,
  `head(shrink)`), not `offset()` on a complex solid. Offsetting is slow and
  fragile.
- **Who wins inside?** When a dark part (a hat or skirt) dips into a light
  body:
  - `dark = hat - body`: the light body wins inside, and the colour border
    is the visible intersection line.
  - Keep the rim outside the body all round. Where it dips under the
    surface at a shallow angle, one colour becomes a thin wedge over the
    other.
  - `ray_colors.py skin` measures this.
- **Light core**: a light surface over a buried dark part needs ≥ 2.5 mm of
  light material. The snowman used
  `white_core = head(2.5) & Pos(0, 0, 28) * Box(100, 100, 56)` and
  `teal -= white_core`.
- **Split by height for one colour change**: everything above `z_split` is
  colour B (`top = (red + pom) & above(z_split)`).
  - Pick `z_split` at the **highest** point of the boundary, because a tilted
    rim is not level.
  - Keep what lies below the split in colour A (`red = red + pom - above`),
    or that piece silently disappears.

## 5. Printability helpers

```python
def rim_skirt(frame, radius, inset, deg=50):   # printable underside of a tilted brim
    rim = frame * Circle(radius)
    k = (radius - inset) / radius
    inner = Pos(0, 0, -inset * math.tan(math.radians(deg))) * scale(rim, by=(k, k, 1))
    return loft([rim, inner], ruled=True)

def support_cone(center, radius, apex):        # holds a hanging sphere (arm end)
    axis = center - apex; L = axis.length
    h = (L**2 - radius**2) / L; top_r = radius * math.sqrt(L**2 - radius**2) / L
    return Plane(origin=apex, z_dir=axis) * Cone(0, top_r, h, align=(Align.CENTER, Align.CENTER, Align.MIN))
```

- Raised ribs on a dome: intersect a shell
  `(spheroid(R + d) - spheroid(R)) & band` with the fused rib slabs.
- Gabled slot (no ceiling): a polygon with a 45° peak, extruded.
- Seat for a slide-on ring: radius a hair smaller at the top
  (`SEAT_R_BOT 15.4`, `SEAT_R_TOP 15.2`).

## 6. Export

```python
export_clean_stl(part, path, tolerance=0.003, angular_tolerance=0.05)
export_step(mono, "name.step")   # for CAD edits (Fusion etc.)
```

- Tolerances are in final mm, after scaling.
  - Revolves: 0.01 / 0.08.
  - B-spline surfaces (lofts, squeezed revolves): 0.003–0.005 / 0.05–0.06.
  - Facets show at 25 mm.
- `export_clean_stl` drops the 1–3 degenerate triangles OCC leaves at
  sphere poles. It refuses when there are more, because that is a broken
  surface. Never use trimesh repair: it needs networkx and silently fills
  real holes.

## 7. Gotchas (each cost a rebuild)

| Symptom | Cause | Fix |
|---|---|---|
| Lumpy ellipsoid | non-uniform `scale(Sphere)` | revolve an `EllipticalCenterArc` |
| Horizontal bands on the body | spline or loft through every pixel row | thin points to every 2nd–3rd row |
| Part 50 mm off after scaling | `scale()` keeps the Location | `scale(shape & Box(1000,...), k)` |
| Ribs vanished | `& [list]` | fuse the list first |
| Thousands of "debris" pieces | spline profile ends on the axis | close it flat or with a 90° arc |
| Thousands of loose triangles on a trimmed ball | `spheroid()` (revolved ellipse) with EQUAL radii, after booleans | a true ball is `Pos(c) * Sphere(r)`; keep `spheroid()` for unequal radii |
| Box cut off at 9 mm, bow floating above | intersected with a finite helper (a 60-unit chamfer frustum) | make every cutter/limiter taller than the part |
| Loop bulged 1.3 mm too high, a face failed to mesh | loft ended with ever smaller sections | end the loft at its widest section and cap it with an ellipsoid of that section |
| Sliver faces / open edges | coplanar loft caps | overlap 0.2–0.3 mm |
| Piece missing after a colour split | `red - above` also removed what was below | `red + pom - above` |
| `TypeError` in EllipticalCenterArc | positional `arc_size` | keyword `arc_size=` |

## 8. Performance

- Boolean chains with scaled revolves are slow. The one-piece Santa took
  ~29 min to build: run long builds in the background, and cache parts
  when iterating on one feature.
- Iterate on a coarse export (tolerance 0.02), then export fine at the end.
- `bounding_box(optimal=True)` is exact but slower. Use it when a split
  height depends on it.
