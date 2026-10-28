# Design rules for FDM figurines and parts (PETG-first)

Rules that held up on real prints (Kobra S1, PETG, 0.2 and 0.4 nozzles).
Numbers are starting points: confirm with `check_model.py`, `slice.py`
and `layers.png` for every model.

## Contents
1. Nozzle, line and layer
2. Minimum feature sizes
3. Overhangs and how to remove them
4. Bottoms, holes, ceilings
5. Fits and assembly
6. Small versions of a model
7. Flow (speed) limits

## 1. Nozzle, line and layer

| | 0.2 nozzle | 0.4 nozzle |
|---|---|---|
| line width | 0.22–0.25 mm | 0.42–0.45 mm |
| layer height | 0.06–0.16 mm | 0.12–0.28 mm |
| walls | 4 × ≈ 0.9 mm | 2 × ≈ 0.85 mm, 3 × ≈ 1.3 mm |
| smallest feature / rib | 0.4 mm | 0.8 mm |
| bold text, stroke height | ≥ 2.5 mm | ≥ 4 mm |
| print time | 3–4 × longer | 1 × |

- Pick 0.2 for anything under ~30 mm with a face, text or thin strokes.
  Pick 0.4 for everything else.
- A 0.2 nozzle needs a 0.2 PROCESS preset (thin lines, low speeds). Slicing a
  0.2 machine with a 0.4 process gives 0.42 mm lines and 25 mm³/s demands
  that a 0.2 nozzle cannot melt. Section 7, and slicer-cli.md, say how to
  make the preset.
- Make wall thicknesses a multiple of the line width. Otherwise gap fill or
  slits appear between the perimeters.

## 2. Minimum feature sizes

- A stroke (eye, mouth, groove) must be at least **2 line widths** wide:
  0.5 mm on a 0.2 nozzle, 0.9 mm on a 0.4.
  - A thinner stroke gets **0 mm of toolpath**. The slicer drops it silently.
  - The user's 87 mm snowman scaled to 17.4 mm lost its eyes and nose this
    way.
- Inlay depth: 0.6 mm or more (4 layers at 0.16). Engrave depth: 0.5–0.6 mm.
- A shell of one colour over another must be **at least 1 mm** thick.
  - A teal hat shell thinner than that tore into one broken line.
  - White patches showed through.
- Check every small feature in `layers.png`. It draws lines at their true
  width, so a dropped or torn feature is visible there.

## 3. Overhangs and how to remove them

Slope is measured from horizontal on a downward-facing surface:

- ≥ 45° is safe for PETG.
- 30–45° droops slightly.
- Below 30° needs support or a bridge.

`check_model.py` colours these areas; `overhang_spots.py` lists where they are.

| Problem | Fix that worked |
|---|---|
| Round bottom of a body | 50° chamfer from the bed: the first profile point rises at 50° (`(10.4,0) → (12.4,2.4)`) |
| Tilted hat brim / cuff / rim | **Rim skirt**: a ruled loft from the rim, scaled about Z and lowered, down and in at 50° into the part below. It reads as the rolled underside of the brim |
| Arm hanging off a body | Capsule arm (elbow sphere at each end), plus a **support cone** from inside the hip, tangent to the lower sphere, aimed 60° down |
| Ball resting on top (pom-pom) | Sink it until its lower half is inside the part below. Check the tilt: a tilted hat exposes the back |
| Grooves cut into a shallow dome | **Raised ribs** instead. Cut grooves end in wide flat ceilings over the crown |
| Slots or fringe cut upwards | Peaked 45° top (a gable), never a flat top |
| Pocket for a glued part | Roof rising at 45° towards the opening |
| Ring that slides onto a part | Seat **narrowing upwards**, so nothing overhangs; the ring drops on from the top |
| Downward-facing face feature | Make it flush (an inlay or engraving), not protruding |

The slicer prints a cantilever in the air as "Overhang wall" **without
warning**. A 12 mm one was invisible in the mesh preview and obvious in
`layers.png`. `gcode_view` lists Overhang wall / Bridge / Support layers
under ALERTS, so read them.

For multi-colour models, a downward face that rests on another colour is an
interface, not an overhang. `ray_colors.py support parts/` separates the
two.

## 4. Bottoms, holes, ceilings

- **Flat bottom**: cut everything at z = 0 (`- below_bed`). Feet and bases
  sit on the bed.
- **Bottom edges**: a 0.3–0.5 mm chamfer at 45°, never a fillet. A fillet
  underneath is an overhang.
- **Horizontal holes**: teardrop, or a flat top.
- **Bridges**: PETG bridges up to ~10 mm.
  - A tiny ceiling, such as the end of a groove or an inlay lip under
    1 mm², is fine.

## 5. Fits and assembly (starting values; calibrate with a tolerance coupon)

| Fit | Clearance per side |
|---|---|
| press / tight | 0.05–0.10 mm |
| sliding | 0.15–0.20 mm |
| loose | 0.30 mm + |

- On the user's setup, Santa's brim ring used 0.15 mm on a 25 mm figure, and
  the glued beard plate used 0.10 mm.
- A part printed separately should lie on its flattest face.
  - The beard plate printed on its flat back, with the eye inlays in its
    top layers.

## 6. Small versions of a model

Scaling a finished model down breaks it. Features fall under 2 line widths,
shells under 1 mm, and the auto brim grows. Give the model a `Variant` with
feature sizes in **final mm**, converted to design scale:

```python
k = target_height / design_height
def design(mm): return mm / k   # final mm -> design scale
eye = SlotArc(arc, design(0.5))  # stays 0.5 mm after scaling
```

The 17.4 mm snowman variant used:

- 0.5 mm eye strokes and 0.6 mm inlays;
- no knit ribs or fringe;
- no white core, since the hat is solid teal at that size;
- a 0.2 nozzle.

## 7. Flow (speed) limits

| Nozzle (PETG) | Melt limit |
|---|---|
| 0.2 | ≈ 5 mm³/s |
| 0.25 | ≈ 7 mm³/s |
| 0.4 | ≈ 15–20 mm³/s, depending on the hotend |

- PETG filament presets usually inherit the 0.4 cap of ~33 mm³/s, so they
  limit nothing on a small nozzle.
- `gcode_view` flags lines whose computed flow exceeds the limit:
  `flow = E per mm × filament area × feed rate`.
- Fix it with a process override. At 0.16 mm layers on a 0.2 nozzle,
  internal solid infill reached 5.8 mm³/s; `internal_solid_infill_speed`
  120 brought it under 5.
