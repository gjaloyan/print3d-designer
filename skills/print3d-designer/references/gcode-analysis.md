# Reading a sliced G-code (`gcode_view.py`)

The mesh can look fine while the print fails: features thinner than a line
are dropped, cantilevers print in the air, small nozzles get asked for more
flow than they can melt. Slice, then look at what the printer will actually
lay down.

```
python scripts/gcode_view.py plate_1.gcode [--layers 0.3,5,12.5]
```

`slice.py` and `make_3mf.py --check` call it for you.

## Report

This is the real report for the one-piece Santa: 25 mm tall, 0.2 nozzle,
0.16 mm layers, red and white. Notes on the right are not part of the
output.

```
layers           : 155 (first 0.15 mm, then 0.16 mm)
height           : 24.79 mm
print time       : 4 h 53 min (slicer estimate)            <- M73 R; no colour-change time (GUI said 6 h 20)
filament         : 2.25 m, 6.7 g extruded by the G-code; slicer total 36.2 g incl. colour-change purge
filament changes : 85                                       <- T<n> switches after the first layer
  T0 #B81D14    18.9 g used,  35.03 m of path on the model
  T1 #FFFFFF    17.3 g used,  15.77 m of path on the model
  prime tower: 107.7 m of 158.5 m path; purge between colours is not drawn (it goes to the chute or into infill)
  purge estimate: 85 x 280 mm^3 = 29.5 g (flush_mm3_per_change in printer.json)
nozzle           : 0.2 mm, flow limit 5 mm^3/s
by feature (path length, share, median line width, max flow):
  Prime tower             107.67 m   67.9%  0.25 mm    3.7 mm^3/s
  Inner wall               22.33 m   14.1%  0.24 mm    4.1 mm^3/s
  Internal solid infill     8.78 m    5.5%  0.22 mm    4.6 mm^3/s   <- 5.8 before the speed cap
  Outer wall                8.64 m    5.5%  0.22 mm    1.9 mm^3/s
  ...
ALERTS           :
  Overhang wall          13 layers, z=7.19..7.35 (1 mm), 8.79..9.91 (2 mm), 10.55 (0 mm), ...
```

The few millimetres of Overhang wall here are the beard's lower edge and
groove ends: acceptable. Tens of millimetres on one run are not.

## ALERTS: what each means and what to do

| Alert | Meaning | Usual fix |
|---|---|---|
| **Overhang wall** | perimeters printed with nothing (or little) below | find the z in layers.png, then the feature in the model: skirt, cone, chamfer |
| **Bridge** | a span printed in the air between supports | fine below ~10 mm in PETG; long ones mean a ceiling to redesign (gable, 45° roof) |
| **Support / Support interface** | the slicer added supports | design them away (design-rules.md) unless the user agreed |
| **Flow over limit** | commanded mm³/s above the nozzle's melt limit | lower that feature's speed via `set` (e.g. `internal_solid_infill_speed`) |

"none" means no bridges, supports, overhang walls, or flow over the limit.
Tiny bridges such as groove ends are normal.

Always open the alerted layer before acting on an alert. Example: the demo
model reported "Bridge 1 layer, z=24.20 (83 mm)".

- The layer view showed a teal cap starting over the **sparse infill** of
  the white body's flat top, which is hidden inside the cap.
- Because the colours are one object, the top of the lower colour is
  internal, and the first layer of the next colour is drawn as a bridge
  over infill.
- It is invisible and harmless.

A bridge on the outside of the model is a real problem.

## Images

- **toolpaths.png**: 3D extrusion paths from two sides. Colours are by
  feature type, or by filament when there are several. The prime tower is
  hidden.
- **layers.png**: top-down views of chosen layers, every line drawn at its
  **true width**. Default layers are:
  - first, second and last;
  - the first layer of every alert run;
  - a spread of others.

  Use `--layers` to look at a feature's heights (eyes, rim, split height).

## What to look for in layers.png

- A face feature missing on the layers where it should be. It was thinner
  than 2 lines and got dropped.
- Colours in the wrong place, for example white showing inside a teal
  shell, or a stray colour crescent. That one came from a tilted rim split
  at a single height.
- A one-line shell that tears: it needs ≥ 1 mm.
- Gaps between perimeters: the wall is not a multiple of the line width.
- Islands in the air: the start of an Overhang wall run.

## Sanity numbers

- Time and grams per colour change: multi-colour printing changes the cost
  completely (multicolor.md).
- A brim that is much wider than expected on a tiny part: set `brim_type` /
  `brim_width`.
- First layer 0.2 mm on a 0.2 nozzle is normal (the initial layer height).
