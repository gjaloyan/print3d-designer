---
name: print3d-designer
description: Design, verify and slice 3D-printable models in code (build123d), including figurines copied from a reference picture, in one colour or several. Use whenever the user wants to make, fix, scale down, recolour or check a model for an FDM printer, for example STL/STEP/3MF files, a figurine or cake/cup topper from a photo or an AI reference sheet, parts that must fit, flush inlays or engraved faces, or a multi-colour project for an AMS/ACE-style filament changer. Also use it to slice with the user's own Bambu Studio, OrcaSlicer or Anycubic Slicer Next presets, to read a G-code for overhangs, dropped features, colour changes or flow limits, or to read a Klipper/Moonraker printer (status, loaded filament colours, history). Trigger even when the user does not say build123d or slicer, e.g. 'make this for my printer', 'why did the face disappear', 'make it smaller for the 0.2 nozzle', 'how many colour changes'.
compatibility: Python 3.11-3.14; scripts/setup.py installs scripts/requirements.txt (build123d, trimesh, pyvista/VTK, scipy, matplotlib, pillow) into ~/.print3d/venv. Optional - a Bambu Studio-family slicer with its CLI, ffmpeg, a Moonraker printer on the network.
license: MIT
metadata:
  version: 1.3.0
  author: gjaloyan (designs and print testing), with Claude
  hermes:
    short_description: Design, check and slice 3D-printable models.
    category: creative
    tags: [3d-printing, cad, build123d, slicer, multicolor, figurine]
---

# Print3D Designer Skill

This skill builds printable models as code (build123d) and checks them the
way a careful human would before printing:

- mesh checks;
- rendered previews compared against the reference;
- colour ray tests;
- a real slice with the user's own presets, read back layer by layer.

It produces STL/STEP files and ready-to-print colour 3MF projects. It does
not send anything to the printer, and it changes the user's slicer presets
only with their approval.

**Four rules the user cares about most:**

1. **Ask before modelling.** Ask the user about the model in a
   question round before writing any model code:
   - size and purpose;
   - one piece or parts, and colours, with change counts;
   - detail the size cannot hold;
   - every print-driven deviation from the reference.

   Use the agent's question tool, with multiple-choice options and your
   recommendation first. Wait for the answers. See
   `references/questions.md`.
2. **Measure, never eyeball.**
   - Every dimension comes from the picture: width from the front view,
     depth from the side view, and how both change with height.
   - Build with the tested shapes in `scripts/shapes.py`, not improvised
     geometry.
   - The model must pass `compare_views.py` against the picture before
     anything else. One agent eyeballed a gift box and got an even cube: 26%
     too deep, with a pancake for a bow. The gate failed it in one run.
3. **Look before handing over.**
   - Open every preview, overlay and `layers.png` with your image tool (see
     "Looking at images"), and fix what you see.
   - If you cannot look at images, say so and rely on the numeric gates.
4. **Ask again when a choice appears.** After slicing, trade-offs such as
   layer height or plates go back to the user as a table of numbers. An
   ambiguous request ("merge", "smaller") gets a question, not a guess.

## When to Use

- "Make a model of this" (photo, drawing, AI reference sheet), a topper,
  ornament, figurine, or a functional part with fits.
- "Make it printable / no supports / flat bottom / smaller / for the 0.2
  nozzle."
- Colour work: split a model into colour parts and build a 3MF with
  filaments and settings. Count colour changes, time and purge.
- Slicing questions: why a feature vanished, what will print in the air,
  flow too high, which layer height.
- Reading the printer: what is printing, which filaments are loaded, what
  failed before.

Not for:

- organic sculpting from scratch with no reference;
- mesh repair of downloaded STLs (use the slicer's repair);
- controlling the printer.

## Prerequisites

1. **Python environment** (Python 3.11–3.14), once per machine. If
   `~/.print3d/venv` already exists, skip this step. Otherwise run:

   ```bash
   python SKILL_DIR/scripts/setup.py
   ```

   `SKILL_DIR` is this skill's folder. The script:
   - creates `~/.print3d/venv` and installs `scripts/requirements.txt`
     into it (5-10 minutes the first time);
   - writes a starter `~/.print3d/printer.json` if there is none, filling
     in the slicer's paths when it finds Anycubic Slicer Next, OrcaSlicer
     or Bambu Studio;
   - runs `selftest.py`.

   Run every script with that venv's python:
   `~/.print3d/venv/Scripts/python` on Windows, `~/.print3d/venv/bin/python`
   elsewhere. Any other environment with the requirements works too.
2. **printer.json**: the scripts look for it in this order:
   - `$PRINT3D_CONFIG`;
   - `./printer.json`;
   - `~/.print3d/printer.json`;
   - `SKILL_DIR/config/printer.json`, a machine-local fallback that is not
     shipped.

   Fill it in with the user. `templates/printer.json` is a complete example
   (an Anycubic Kobra S1). It needs:
   - bed size;
   - the Moonraker URL;
   - the slicer exe;
   - the user and system preset folders;
   - per nozzle: the machine, process and filament preset names, plus
     `flow_limit`;
   - filament diameter and density;
   - purge per colour change.

   List the real preset names with `slice.py --presets machine` (or
   `process`, `filament`; `--match TEXT` filters); never guess them.
   Without a slicer, everything except slicing still works.
3. **Optional**:
   - ffmpeg, for screen recordings (`winget install Gyan.FFmpeg`);
     Windows has a built-in fallback.
   - The printer's Moonraker URL, for read-only checks.
4. **Check the setup**: run `python SKILL_DIR/scripts/selftest.py`. It
   builds the demo model and runs every check plus slicing. All steps
   should PASS.

## How to Run

Scripts are in `SKILL_DIR/scripts/`. Each one prints a report and returns
non-zero on a real problem.

| Script | What it does |
|---|---|
| `measure_reference.py ref.jpg --colors red,white --height 80 --masks m.png --json p.json` | per-view, per-row silhouette and colour extents in mm, to paste into the model as profiles |
| `shapes.py` (library; `python shapes.py` self-checks) | tested build123d shapes: bodies of revolution, `rounded_box`, `lobe`, tilted rims and skirts, cones, strokes, inlays, 45° engraving, knit ribs, export. Copy it next to the model |
| `compare_views.py parts/ ref.jpg --views front,side,back,three-quarter --anchor red --info three-quarter` | **fidelity gate**: model silhouette against each picture view (IoU, aspect, width by height band, colour overlap). Also warns when the view order or a mirrored side view is wrong. Writes `views_check.png` |
| `check_model.py model.stl --png preview.png` | watertight, bodies, size, volume, grams, bed fit, overhang areas; 4 views plus 2 overhang maps |
| `overhang_spots.py model.stl` | WHERE the overhang patches are (x/y/z boxes), to find them in the code |
| `render_parts.py parts/ --png cmp.png --views front,side,back,three-quarter --reference ref.jpg` | colour render stacked under the reference picture |
| `render_parts.py parts/ --png close.png --closeup` | raking-light close-up: banding, lumps, inlay edges |
| `ray_colors.py support parts/` | downward faces of each colour: resting on another part, or hanging (the slicer sees one object) |
| `ray_colors.py skin parts/ --light white --dark teal --min 1.0` | a light colour too thin over a dark one (show-through) |
| `slice.py model.stl --nozzle 0.2 [--set layer_height=0.16]` | slices with the user's presets (flattened), part centred and not rotated; report plus `toolpaths.png` and `layers.png` |
| `slice.py --presets machine [--match S1]` | lists the slicer's preset names (the user's own first), for printer.json |
| `gcode_view.py plate_1.gcode --layers 3.2,7.5` | report and images for any G-code; called by slice and make_3mf |
| `make_3mf.py print.json --check` | 3MF project (one colour or several, one plate or several) with presets and colours; `--check` slices it and draws the layers in filament colours, with change counts. `"preset"` may be left out: the material printer.json names. With no slicer configured it writes a geometry-only 3MF instead: one object, a part per colour, centred on the bed |
| `video_frames.py rec.mp4 --out frames --sheet sheet.jpg` | frames plus a contact sheet from a user's screen recording |
| `moonraker.py info / status / ace / history / files / config / settings / snapshot` | read-only printer queries |
| `setup.py` | once per machine: venv, starter printer.json, self-test |
| `selftest.py` | end-to-end check of all of the above |

Templates in `SKILL_DIR/templates/`. Copy one, together with
`scripts/shapes.py`, into `models/<name>/`:

| Template | Use for |
|---|---|
| `model_template.py` | round figures: an egg body plus a tilted beanie with skirt, inlaid face |
| `box_template.py` | box-like figures. It is the real gift box: `rounded_box` with base chamfer and lid round, bow lobes, an engraved face, colour by height. It passes `compare_views` against its picture, `box_reference.jpg` |
| `print.json`, `print_plates.json` | colour project specs |
| `printer.json` | the config |

## Looking at images (any agent)

The scripts write PNGs: previews, overlays, close-ups, layers. You must
actually look at them.

| Agent | How to look |
|---|---|
| Claude Code | the Read tool on the PNG |
| Hermes | `vision_analyze` with the image path |
| Other agents | their image or vision tool |

- Open the image and describe what you see before deciding anything. An
  unopened preview is not a check.
- With no vision, say so to the user and send them the PNGs. Treat every
  numeric gate as mandatory: `check_model` RESULT, `compare_views` PASS,
  `ray_colors` RESULT, and `gcode_view` ALERTS.

## Shape recipes (picture → `shapes.py`)

| In the picture | Use | Note |
|---|---|---|
| ball, egg, cone, round tiers | `profile_solid(rows, depth)`, `ball`, `spheroid`, `ellipsoid` | rows = (half-width, z) from the front view; `depth` = side width / front width |
| soft box, block, cushion, pudding | `rounded_box(levels, corner_r, lid_round, base_chamfer)` | levels = (z, half-width from the FRONT view, half-depth from the SIDE view) |
| bow loops, petals, ears, leaves, wings | `lobe(sections, z0, cap)` | sections across the lobe; centre it on the surface it lies on |
| tilted hat cuff, brim, rim | `tilted(pos, deg)` + `rim_skirt(...)` | sharp rim bottom edge; the skirt ends inside the part below |
| arms, legs, hanging balls | `capsule`, `support_cone` | cone 55–60° down into the body |
| a face (eyes, nose, smile) | `kawaii_face(nozzle, ...)` → `layout.report()`, `face_preview(layout, png)`, then `inlay(layout.sketch, skin)` or `engrave(...)` | numbers in FINAL mm from the picture; `layout.problems` must be empty |
| other lines (arms, folds) | `strokes`, `tapered_stroke`, then `inlay` (colour) or `engrave` (45°, no ceilings) | strokes ≥ 2 line widths in final mm |
| knit, ribs | `raised_ribs`, `band_grooves`, `v_grooves` | ribs ≥ 0.5 mm on a 0.2 nozzle |
| one colour above a height | `& above(z)` / `- above(z)` | split at the boundary's highest point |
| many small cuts (quills, grooves, holes) | `cut_many(body, cutters)` | one boolean: 64 quills in 5 s instead of 19 s one by one; a cutter that breaks the solid is left out and reported |

## Quick Reference

| Topic | Rule |
|---|---|
| Overhang | ≥ 45° from horizontal (PETG); below 30° needs support. Design it away |
| Base | flat at z = 0; first profile segment rises at 50° (chamfer) |
| Tilted brim / rim | 50° ruled skirt from the rim down into the part below |
| Hanging arm or ball | capsule plus a support cone into the body; sink balls ≥ half |
| Detail on a shallow dome | raised ribs, not cut grooves |
| Slots, pockets | 45° peaked or rising roofs; no flat ceilings |
| Stroke width | ≥ 2 line widths: 0.5 mm (0.2 nozzle) / 0.9 mm (0.4) |
| Face features | each stroke or dot ≥ 2 line widths, ≥ 2 line widths of body between any two, strokes ≥ 2.5 x as long as wide; `check_face` / `kawaii_face` measure it |
| Face technique | inlaid dark colour reads best; engraving reads only by shadow, so engrave only a face that passes the check with room to spare |
| Inlay / engrave depth | 0.6 / 0.5 mm |
| Shell of one colour over another | ≥ 1 mm; light over dark needs a ≥ 2.5 mm light core |
| Fits per side | press 0.05–0.10, slide 0.15–0.20, loose 0.30 mm |
| Small model (< 30 mm) | 0.2 nozzle, 0.12–0.16 layers, feature sizes in FINAL mm |
| 0.2 nozzle flow | ≤ ~5 mm³/s; cap `internal_solid_infill_speed` at 0.16 layers |
| Colour change cost | ~280 mm³ purge + ~1–3 min; 1–2 changes per mixed layer |
| Light colours | `flush_into_infill = 0` |

## Procedure

1. **Read before asking.**
   - Study the reference: enlarge each view and note colours, textures,
     overhangs, thin features and the tilt. Dark strokes on a coloured
     surface are often engraved grooves, not a third colour: ask.
   - **Name the sheet's views left to right**, using the camera convention
     (camera position seen from the model):
     - `front` (face to you);
     - `side` (camera at +X; the face points LEFT in the image);
     - `left` (camera at −X; the face points RIGHT);
     - `back`;
     - `three-quarter` / `three-quarter-left`.

     Write the list down, e.g. `front,side,back,three-quarter`, and use the
     same order in every tool. `compare_views` warns when the order or a
     side is wrong.
   - Run `measure_reference.py` and check its `masks.png` (see
     `references/reference-photos.md`).
   - Check what is loaded in the changer (`moonraker.py ace`) and which
     nozzles printer.json has.
2. **Question round, a hard gate: no model code before the answers.**
   - Ask about size and purpose, one piece or parts, colours, detail level,
     and each deviation (multiSelect).
   - Each option carries its estimated cost: changes, time, grams
     (`references/questions.md` §2).
   - Recommend one option per question.
   - Write the answers, with the date, into the model's docstring.
3. **Measure for the chosen design.**
   - Measure widths against height in the front view, and depths against
     height in the side view: two separate tables. Never assume
     depth = width, or straight walls.
   - Take tilts and feature positions from the side view.
   - AI product shots are taken from slightly above: a flat top shows as a
     band, so take its middle as the top's height.
   - Paste the rows at the design scale, thinned to every 2nd–3rd row.
   - **Lay out the face before modelling.**
     - Measure the eye spacing, eye size, nose and smile in the front view and convert them to FINAL mm.
     - Run `kawaii_face(nozzle, ...)` (or `check_face` for a face of your own).
     - Look at `face_preview`. It shows the face at print scale, with red lines where two features would merge.
     - If `layout.problems` is not empty, the face is too small for this nozzle. That is a question-round topic, not something to ship: offer a 0.2 nozzle, a bigger size, an inlaid colour face or fewer features (`references/questions.md`).
4. **Model.**
   - Copy the matching template (`model_template.py` for round figures,
     `box_template.py` for box-like ones) plus `scripts/shapes.py` into
     `models/<name>/`.
   - Build every part from the recipes table above.
   - Build at the reference's scale; scale to the final height at the end
     with `scaled()`.
   - Export with `export_parts` (mono STL + STEP, `parts/<colour>.stl`).
   - Long boolean builds (minutes) run in the background.
   - Iterate fast:
     - export previews coarsely (`tolerance=0.01`) and finely once, at the end;
     - test a risky boolean on the part alone, not with a full rebuild;
     - cut many features with `cut_many`. A hedgehog cut quill by quill took 80–110 s per rebuild.
5. **Verify the geometry.**
   - `check_model.py`: watertight, 1 body, fits; look at `preview.png`.
   - **`compare_views.py` must PASS**: IoU ≥ 0.92 and aspect within 8% on
     every gated view.
     - On FAIL, read which height bands are too wide or narrow, fix the
       numbers and rebuild.
     - If the picture differs where the user approved a change (a removed
       ribbon, a chamfer), say so with the number.
     - Look at `views_check.png`.
   - `overhang_spots.py` for anything red or orange that is not intended.
   - `render_parts.py --reference` and `--closeup`: compare looks, then
     check banding, lumps and feature edges.
   - Colour models: run `ray_colors.py support` and `ray_colors.py skin`
     for every light-over-dark pair.
6. **Slice and read it.**
   - `slice.py` (mono), or `make_3mf.py print.json --check` (colour).
   - Read ALERTS: Overhang wall, Bridge, Support, flow over limit.
   - Open `layers.png`, adding `--layers` at the heights of the face, rims
     and split heights. Check:
     - every small feature has toolpaths;
     - the colours land where intended;
     - no shell tears.
   - Fix and repeat.
7. **Hand over.**
   - Give the file paths:
     - STL;
     - 3MF (with presets, colours and plates);
     - STEP.
   - Show the comparison image.
   - Give the numbers: size, time, grams, colour changes.
   - Say which filament goes in which slot.
   - List what is not verified (for example, real-world fit before a
     tolerance test).
   - Offer alternatives as a short table when there is a real trade-off,
     such as layer 0.12 vs 0.16, or parts vs one piece.
8. **Follow up** on feedback such as screenshots, recordings or "you
   changed X":
   - re-measure;
   - rebuild;
   - re-verify;
   - say what changed.

## Pitfalls

- **Scaling a finished model down** drops features thinner than a line, and
  turns shells into torn single lines. Make a size variant with final-mm
  features instead.
- **Eyeballing the shape.** A box copied by eye came out as an even cube:
  depth = width, straight walls, rounded bottom (an overhang), and a
  pancake bow.
  - Measure both views.
  - Use `rounded_box` and `lobe`.
  - Gate with `compare_views`.
- **Views out of order or mirrored.** Rendering `front,three-quarter,side,back`
  under a sheet ordered `front,side,back,three-quarter` makes every
  comparison meaningless. A sheet whose side view faces right shows `left`,
  not `side`.
- **The silhouette is not the front edge.** Tilted cuffs and brims hang
  lower at the sides. AI reference sheets disagree between views.
- **A face drawn by eye on a small figure prints as a grimace.**
  - The first service order was a 25 mm snowman on a 0.4 nozzle. It had 0.7 mm strokes and only 0.41 mm of body between the nose and the smile.
  - The slicer merged the nose and the smile into one blob.
  - Lay faces out with `kawaii_face` and fix every problem before building.
- **Pixel-row profiles band the surface.** Thin the points; use PCHIP.
- **build123d traps**:
  - `scale()` ignores a shape's Location (bake with `& Box`);
  - `shape & [a, b]` intersects with each item;
  - a non-uniform `scale(Sphere)` comes out lumpy;
  - a spline ending on the revolve axis shatters the mesh;
  - coplanar loft caps leave slivers;
  - `EllipticalCenterArc` needs `arc_size=` as a keyword.
- **Colour splits by height**: split at the boundary's highest point, and
  keep what lies below it.
- **Who wins inside**: a dark part buried in a light body shows through.
  Let the light body win inside, and keep rims outside the body.
- **Slicer CLI**:
  - flatten presets;
  - `compatible_printers` must name the machine's system ancestor;
  - `--arrange 0` with pre-centred parts;
  - plate names must be empty for the CLI;
  - `assemble_index` must be ≥ 1;
  - the CLI time estimate leaves out colour changes.

  See `references/slicer-cli.md`.
- **The slicer prints cantilevers in the air without a warning**, and the
  mesh preview hides them. Only `layers.png` and ALERTS show them.
- **A trimesh repair needs networkx and silently fills holes.** Ray casting
  via trimesh needs rtree. The scripts avoid both; VTK's OBB tree crashed,
  so `ray_colors` uses the BSP tree.
- **Printer**: GET requests only. Never download a whole G-code while it
  prints (single-core board); read the tail with a Range request.
- **Permissions**:
  - Writing into the user's slicer preset folders needs their OK.
  - Never send jobs to the printer.
  - Keep the user's own files intact: write new versions next to them.

## Verification

A model is done when all of these hold:

- [ ] The question round happened before modelling. The answers are in the
  model's docstring, and nothing in the model deviates from them.
- [ ] `check_model.py` RESULT OK: watertight, 1 body, fits the bed.
  Overhang areas are explained.
- [ ] `compare_views.py` RESULT PASS with the views named in the sheet's
  order. Any failing band is explained by a change the user approved.
- [ ] You have looked at `views_check.png` and the comparison render with
  your image tool: the proportions match view by view, and every deviation
  was approved.
- [ ] Faces: `kawaii_face` / `check_face` report no problems, and you have looked at `face_preview`.
- [ ] The close-up shows no banding, lumps or broken inlays.
- [ ] Colour models: `ray_colors.py support` is OK, and `skin` is OK for
  each light/dark pair.
- [ ] Sliced with the user's presets. ALERTS are none or explained, and
  flow is under the limit.
- [ ] In `layers.png`, every face feature has toolpaths at its heights and
  the colours are in place.
- [ ] Handed over: paths, numbers (time, grams, changes), slot colours, and
  open risks.

## References (load when needed)

| File | Read it when |
|---|---|
| `references/questions.md` | before modelling (question round, cost estimates) and after slicing (trade-offs) |
| `references/design-rules.md` | choosing nozzle, sizes, overhang fixes, fits, small variants, flow |
| `references/build123d-cookbook.md` | writing model code: helpers, colour parts, export, gotchas |
| `references/reference-photos.md` | copying a picture: proposal, measuring, comparing |
| `references/multicolor.md` | colour strategy, change costs, light over dark, project spec |
| `references/slicer-cli.md` | anything about presets, the CLI, 3MF, multi-plate, user presets |
| `references/gcode-analysis.md` | reading the slice report and `layers.png` |
| `references/printer-moonraker.md` | reading the printer, ACE slots, history |
| `references/case-studies.md` | real examples with numbers and the mistakes that were fixed |

## Files in this skill

The scripts import each other, so install the whole folder. Some agents
copy only the files a skill names; this is every file:

- `scripts/setup.py`, `scripts/selftest.py`, `scripts/config.py`,
  `scripts/requirements.txt`
- `scripts/shapes.py`, `scripts/measure_reference.py`,
  `scripts/compare_views.py`, `scripts/check_model.py`,
  `scripts/overhang_spots.py`, `scripts/render_parts.py`,
  `scripts/ray_colors.py`, `scripts/cleanmesh.py`
- `scripts/slice.py`, `scripts/gcode_view.py`, `scripts/make_3mf.py`,
  `scripts/moonraker.py`, `scripts/video_frames.py`,
  `scripts/frames_windows.ps1`
- `templates/model_template.py`, `templates/box_template.py`,
  `templates/box_reference.jpg`, `templates/print.json`,
  `templates/print_plates.json`, `templates/printer.json`
- `references/questions.md`, `references/design-rules.md`,
  `references/build123d-cookbook.md`, `references/reference-photos.md`,
  `references/multicolor.md`, `references/slicer-cli.md`,
  `references/gcode-analysis.md`, `references/printer-moonraker.md`,
  `references/case-studies.md`
