# Changelog

## 1.3.1 (2026-10-29)

From a Hermes run that shipped a hard cube for the gift box: it lost the
template to a compacted conversation, lowered the gate's limit and shipped
a failed model. See case study 10.

- The fidelity gate is binding. `compare_views.py` writes its verdict to
  `views_check.json`; `make_3mf.py` builds no project (NOT READY, exit 3)
  from parts that failed it or changed after it, unless the user accepts
  the difference (`--accept-views "their words"`, kept in the 3MF's
  recipe). `--min-iou` and `--max-aspect` only go stricter, and front,
  side, left and back can no longer be left ungated with `--info`.
- Pictures sent through a messenger: their JPEG noise added rows above a
  white top, so the right model failed (0.88 instead of 0.95).
  `compare_views.py` and `measure_reference.py` now drop specks and use
  `--threshold 20`; the template passes on the original and on copies
  recompressed down to JPEG quality 40.
- `measure_reference.py` splits views on the silhouette, not on the anchor
  colour: a ribbon across the body no longer splits one view into two.
  Hand-given `--views` / `--rows` ending at the picture's edge are clamped
  instead of crashing (a fix Hermes made in its own copy).
- `quiet_vtk.py`: no more EGL/VTK warnings on headless machines (a render
  printed ~5 KB of them into the agent's context).
- `SKILL.md`: rule 5, keep the work in files (copy the template first, a
  fresh conversation per model, reload the skill after a compaction);
  colour parts mutually exclusive (from Hermes's copy).
- `selftest.py` holds the gate to all of this: the recompressed picture
  passes, views out of order fail, `make_3mf.py` refuses and then builds
  once accepted, and `measure_reference.py` finds 4 views.

## 1.3.0 (2026-10-29)

- Faces that print: `shapes.py` gains `kawaii_face` (lays a cartoon face
  out from measured numbers and repairs what it can), `check_face` (stroke
  and dot widths, gaps between features, stroke length and smile radius
  against the nozzle) and `face_preview` (draws the face at print scale).
  `SKILL.md`, the design rules, the question round and the case studies
  say when to engrave, inlay, use a 0.2 nozzle or a bigger size.
- `shapes.cut_many`: many small cuts in one boolean (5 s instead of 19 s
  for 64 quills).
- OrcaSlicer support: `gcode_view.py` reads Bambu-style G-code comments
  and derives line widths from the extrusion when the G-code has none;
  `make_3mf.py` keeps the prime tower inside small beds.
- `gcode_view.py` writes `summary.json` next to the G-code: minutes,
  grams (with what the G-code extrudes and what the printer purges),
  colour changes, the prime tower's grams and the layer height. A project
  with several plates gets the totals of all plates. The print time comes
  from the slicer's footer when the G-code has no M73.
- `make_3mf.py` stores its recipe in the 3MF
  (`Metadata/print3d_spec.json`), so a project can be rebuilt and sliced
  for another printer. A filament with no preset takes the material from
  `printer.json`; with no slicer configured it writes a geometry-only 3MF
  (one object, a part per colour, centred on the bed).

## 1.2.0 (2026-10-28)

The first public release.

- `scripts/setup.py`: one command for the Python environment
  (`~/.print3d/venv`), a starter `printer.json` with the slicer's paths when
  one is found, and the self-test.
- `install.py`: copies the skill into the skills folder of 13 agents, or
  any folder, then runs the setup.
- Claude Code plugin and marketplace manifests.
- `slice.py --presets machine|process|filament`: lists the preset names
  that `printer.json` needs.
- `SKILL.md` lists every file of the skill, for agents that copy only the
  files a skill names.
- The author's printer config is no longer shipped.
  `templates/printer.json` is an example with placeholders.

## 1.1.0 (2026-10-28)

- `scripts/shapes.py`: a tested library of build123d shapes, 13 recipes.
- `scripts/compare_views.py`: the fidelity gate. It compares silhouettes
  per view (IoU and width-to-height ratio) and warns about the view order
  and mirrored sides.
- `templates/box_template.py` with `box_reference.jpg`: a box-like figure
  that passes the gate.
- Advice in `SKILL.md` on looking at images in any agent, and a table of
  shape recipes.

## 1.0.0 (2026-10-26)

- The first version:
  - a question round before modelling;
  - reference measuring;
  - model templates;
  - mesh, overhang and colour ray checks;
  - slicing with the user's presets and reading the G-code back;
  - colour 3MF projects;
  - read-only Moonraker queries.
