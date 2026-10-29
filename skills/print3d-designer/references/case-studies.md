# Case studies (one session, October 2026)

This file records what was asked, what went wrong, and what fixed it.

The setup:

- printer: Anycubic Kobra S1 (CoreXY, 250³ mm bed) with Rinkhals firmware;
- hotend: Micro Swiss, 0.2 and 0.4 nozzles;
- colour changer: ACE Pro, 4 slots;
- filament: PETG from NIT and Kingroon;
- slicer: Anycubic Slicer Next 1.4.1.2.

The user checks every model against the reference picture and expects you
to have looked at renders and slices before you hand anything over.

## 1. Snowman: "all faces flat and a fully flat bottom" (87 mm, 0.4 nozzle)

The reference was a sitting snowman in a knit hat and scarf, in 3 views.

| Step | Detail |
|---|---|
| First build | flat cut base, flush engraved face |
| User feedback | "you changed the hat position and body gabarites" |
| Fix | re-measured all 3 views row by row and rebuilt to the numbers: hat tilted 20° back, cuff 57.8 mm high at the front, ~49 at the sides, ~42 at the back; head wider than deep, with a superellipse depth |
| Printability | 50° skirt under the tilted cuff (reads as the rolled brim); arms as capsules plus 60° support cones; feet as spheroids cut flat; scarf underside chamfered at ~51°; dome ribs raised (cut grooves made ceilings); fringe slots with 45° peaks |
| Colour (asked next) | `parts/<colour>.stl` → `make_3mf.py`: 5 colours (pink cheeks share the white slot), 198 changes, 11.5 h, 117 g, against mono at 1.6 h / 30 g |
| Lessons | `flush_into_infill` tinted the white, so it was turned off. A teal hat solid inside the head showed through the thin white face, so a white core of 2.5 mm went behind the face |

## 2. Christmas tree topper (25 mm, 0.2 nozzle)

- The user asked for it "like on the photo", and to be told first about any
  change.
- Proposed changes:
  - base;
  - star thickness;
  - groove width.

  The user accepted **only the base**: the photo's rolled-in bottom became
  a 50° chamfer.
- Built at the photo's scale (80 mm): three PCHIP-lofted tiers of
  ellipses, depth 0.85, a filleted puffy star, SlotArc smile and eyes.
- Bug: `scale()` left the star's Location unscaled, and it flew 50 mm
  above the tree. Fixed with `scaled()`, which bakes with a boolean first.
- Upper tiers overlap 0.3 mm, because coplanar caps made slivers.
- Green + yellow 3MF: 9 changes. It printed fine; the printer history shows
  "completed".

## 3. Mini snowman (17.4 mm, 0.2 nozzle)

- The user scaled the big snowman down in the slicer with the 0.4 nozzle
  and sent a screen recording. Read with video frames, it showed:
  - "where are the eyes and the whole face?": eyes and nose had **0 mm of
    toolpath** (thinner than a line);
  - the teal hat shell over the white core became one torn line, with
    white patches;
  - the auto brim grew to 5 mm;
  - 8.7 g of purge for a 0.65 g figure.
- Fix: a dedicated `Variant` with feature sizes in final mm:
  - 0.5 mm eye strokes, 0.6 mm inlays;
  - 1.0 mm scarf tail;
  - no ribs, fringe, cheeks or white core (the hat is solid teal).
- Print settings: 0.2 nozzle, brim `outer_only` 2.5 mm.
- Results: 0.12 mm layers gave 63 changes / 3 h 52; 0.16 mm gave 49 /
  2 h 57.
- The user chose 0.16. That pushed internal solid infill to 5.8 mm³/s, so
  it was capped at 120 mm/s.

## 4. Santa (25 mm, 0.2 nozzle), as parts

Agreed up front:

- size 25 mm;
- printed in parts;
- all proposed print changes;
- the "2 parts, ~11 changes" plan.

The design:

- **Body print**: red egg body plus a hat tilted 14°.
  - Everything above the pom-pom's lowest rim point is white: 1 change.
  - Bug 1: splitting at the rim's lowest point left a white band on the
    cone. The split moved to the **highest** point.
  - Bug 2: the pom-pom's lower half then went missing, and the slicer
    showed a 12 mm overhang. Fixed with `red = red + pom - above`.
- **White print**:
  - the beard plate lies on its flat back with red eye inlays in its top
    layers (14 changes);
  - the brim ring sits next to it;
  - the ring slides down the hat onto a seat that narrows upwards;
  - the beard is glued into a chest pocket with a 45° roof.
- **Surface banding**: the profile came from every pixel row and showed
  visible bands. Thinning to every other row fixed it.
- **Two plates in one 3MF** (the user said "merge these 2 models"): built
  with `--load-assemble-list`. Plate names crash the CLI, so they are
  written into the zip afterwards. `assemble_index` 1 merges each plate's
  parts.

## 5. Santa as ONE piece

- "I mean merge in one model, not one file": the user wanted one solid
  object.
- The design:
  - the brim gets a 50° white skirt into the body, because its rolled
    underside would hang;
  - the beard is a thick white inlay, so no red shows through;
  - the pom-pom is white all round;
  - the eyes are red inlays.
- The boolean build took ~29 min (scaled revolves), so it ran in the
  background.
- Results: 0.12 mm layers gave 113 changes / 6 h 35 / 47 g; 0.16 mm gave
  85 / 4 h 53 / 36 g.
- The user chose 0.16 (`print_one.json`), with solid infill capped at
  120 mm/s.
- On the printer the GUI-sliced file reads 6 h 20: change time is not in
  the CLI estimate.

## 6. Snowman in a knit beanie (25 mm, 0.2 nozzle): the first model made with this skill

- **Question round** (`references/questions.md`), with the costs estimated
  before modelling:
  - size: the user typed "25 mm" over the offered 80 / 50 / 30;
  - one piece in 3 colours;
  - knit as ribs;
  - all 4 deviations: base, cuff skirt, scarf chamfer, nose bead plus
    pointed arm grooves.
- **Measuring**: a pixel grid over enlarged views, plus
  `measure_reference.py` with the white body as anchor.
  - The floor shadow widened the bottom rows on one side, so widths came
    from the clean right edge.
  - Findings:
    - the body ball is still 52° steep where it is cut at the bed, so no
      chamfer was needed: only the photo's rolled-in rim was dropped;
    - the cuff tilts back 31° and its rim passes through the head centre;
    - the body's shoulders are wider than the scarf, so the scarf sits on
      them.
- **Knit at 25 mm**:
  - 30 raised crown ribs, 0.5 × 0.3 mm, merging at the top;
  - 44 cuff grooves, 0.45 × 0.3 mm, running out through both cuff edges;
  - two 45° V-grooves on the scarf.

  The ribs printed as teeth on the outer wall in `layers.png`.
- **Bugs caught by the checks**:
  - The head as `spheroid(r, r)` shattered into 2,670 loose triangles;
    `cleanmesh` refused to hide them, and `Sphere` fixed it.
  - The mono STL came out 2.7 mm short because of the same broken boolean.
  - The cuff's rounded bottom edge stuck out 0.1 mm below the skirt, a ring
    of 30–45° overhang, so the edge was made sharp.
  - Cuff grooves running above the cuff notched the crown ribs, so they
    stop at the cuff top.
- **Colour logic**: teal wins inside the hat (above the rim plane) and the
  scarf; white wins under the rim (`skirt - white`). Both `ray_colors skin`
  directions were OK.
- **Results**: 0.16 mm layers gave 61 changes / 3 h 50 / 24 g; 0.12 mm gave
  84 / 5 h 18 / 32 g. The pre-model estimate was ~160 changes, which was
  pessimistic.

## 7. Gift box with a bow (25 mm, 0.2 nozzle): height split, 1 colour change

- **Request**: "remove white lines, save only white bow on top". The ribbon
  stripes were dropped and the bow kept.
- **Question round**:
  - 25 mm;
  - face engraved like the photo (its dark strokes are grooves, not a
    colour);
  - red (not loaded in the ACE, so the user loads it);
  - a 50° chamfer instead of the rounded bottom edge;
  - bow loops lying on the lid.
- **Box**: a loft through rounded rectangles that follow the measured
  walls (wider low down: a "pudding").
  - The 50° base comes from intersecting with a ruled frustum.
  - The lid edges are filleted.
  - Views were set with `--views` by hand, because the red anchor split
    each view at the white ribbon.
- **Bow**:
  - Each loop is ONE loft through YZ ellipses, narrow at the knot and
    puffy outside, capped with an ellipsoid. Two joined ellipsoids read as
    a row of bumps.
  - A sunk rod presses a fold.
  - Everything is centred on the lid, so only upper halves show.
- **Colour by height**: everything above the flat lid is white, giving
  exactly 1 change.
- **Results**: 0.16 mm layers gave 51 min / 6.2 g; 0.12 mm gave 1 h 06.
  No alerts.
- **Bugs caught by the checks**:
  - The chamfer frustum was only 60 units tall, so the intersection cut
    the box at 9 mm. `ray_colors` showed the bow hanging over nothing.
  - Tiny end sections made the loop loft overshoot and break.
  - Engraved eye tops were flat ceilings until they were cut with an
    oblique prism.

## 8. The same gift box by another agent (Hermes) with an early version of this skill

The user sent its result: an even rounded cube with a rounded bottom, a flat
pancake bow with a fin, and black face inlays. Why it failed, and what now
prevents it:

| Failure | Cause in the skill | Fix |
|---|---|---|
| Comparison renders in the order `front,three-quarter,side,back` under a sheet ordered `front,side,back,three-quarter` | nothing said to name the sheet's views in order | naming rule in SKILL.md; `compare_views` order and mirror warnings |
| Depth = width (the picture: 0.8), straight walls, rounded bottom | "measure" was advice, never checked | `compare_views` gate: the copy scored side IoU 0.809, "model wider by 64% at the top" |
| Bow as a pancake with a fin | no recipe for loops; the template only knew bodies of revolution | `shapes.lobe`, `box_template.py` |
| No real visual check | "Read the PNG" assumed Claude Code; Hermes looks with `vision_analyze` | "Looking at images (any agent)", plus numeric gates for agents without vision |

Lesson: a skill is used by agents with other tools and weaker eyes. Ship
the knowledge as code (`shapes.py`) and the judgement as numbers
(`compare_views`), not only as prose.

## 9. The first service order: a face that printed as a grimace

**The order.** A snowman in a knit beanie, 25 mm, on a 0.4 nozzle, made
by Sonnet 5.5 through the web service. It ran 39 steps and cost $1.46.

**What went well.**
- The silhouette matched (IoU 0.94–0.96).
- The colours by layer, the tilted cuff and the ribs were right.

**What went wrong: the face.** The agent recommended an engraved face and
drew it by hand:
- strokes 0.7 mm wide, when a 0.4 nozzle needs 0.9;
- 0.41 mm of body between the nose dot and the smile;
- a nose made as a dimple.

The slicer merged the nose and the smile into one shape, which read as a
grimace.

**Why.** The stroke rule was in the docs but nothing checked it, and there
was no rule at all for gaps between features.

**The fix.**
- `check_face` measures widths, gaps and stroke length.
- `kawaii_face` lays a face out from measured numbers and repairs what it
  can: wider strokes, the nose below the eyes, the smile below the nose.
  What it cannot repair it reports.
- `face_preview` draws the face at print scale with the merging pairs in
  red.
- The question round offers only face options that pass.

With the same numbers: the face fails at 25 mm on a 0.4 nozzle, and passes
on a 0.2 nozzle or at 40 mm.

## 10. The gift box by Hermes again, with the template in hand

The user asked Hermes (skill 1.1) for the box without its ribbons. Hermes
read `box_template.py` and confirmed that the user's picture was the
template's own. The job ran in a Telegram chat already full of other
topics, and six minutes in Hermes compacted the conversation: the skill, its
references and the template became one-line stubs. It then wrote the model
from memory: a hard cube 22 × 21 × 27 mm with two upright slabs for a bow.
`compare_views` failed it (front 0.82, back 0.81) even at `--min-iou 0.40`,
and the user got "3MF checked, no errors".

| Failure | Cause | Fix |
|---|---|---|
| Model written from memory | the template lived only in the conversation | rule 5: copy the template into the model folder first and edit the copy; a fresh conversation per model; reload the skill after a compaction |
| A failed gate shipped | the limits were options; nothing downstream read the result | fixed limits, front/side/left/back always gated; `make_3mf.py` builds nothing from failed or changed parts unless the user accepts |
| The template itself failed on the user's copy: 0.88 instead of 0.95 | the picture came through Telegram; JPEG noise above the white bow added 9% to the height | `--threshold` 20 and dropped specks: 0.95 on both copies, the cube still fails (0.76–0.82) |
| `measure_reference` found 8 views instead of 4 | views were split on the red colour, and the white ribbon cut each box in two | views split on the silhouette |
| Each render printed ~5 KB of EGL/VTK warnings into the agent's context | headless OpenGL chatter | `quiet_vtk.py` |

Lesson: a gate the agent can loosen, or whose result nothing reads, is only
advice. Put the verdict where the deliverable is built.

## Patterns worth repeating

1. Ask before deviating from the reference, with options and a
   recommendation.
2. Measure the reference per row and view; model at the reference's scale.
3. After every build:
   - `check_model`;
   - a comparison render with `--reference`;
   - a close-up;
   - `ray_colors` for colour models;
   - a slice, with `layers.png` read at the critical heights.
4. Give cost tables (changes, time, grams) whenever colour or layer height
   is a choice.
5. Write a dated note of every agreed choice in the model's docstring and
   in the project README.
