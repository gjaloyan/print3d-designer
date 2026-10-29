# Copying a reference picture faithfully

Users judge a figurine against the picture they gave. On the first model
the feedback was "you changed the hat position and the body proportions",
so the model had to be rebuilt. Measure first, then model, then compare.

## 1. Agree on deviations BEFORE modelling

- Read the picture.
- List every change you would make for printing:
  - flat bottom, chamfered base;
  - flush face instead of a protruding nose;
  - skirts under tilted brims;
  - parts versus one piece;
  - size, nozzle.
- Ask the user, with your recommendation first. Model only what was
  approved. Write the agreed list into the model's docstring.
- Example: for the tree the user accepted only the base fix ("only the
  bottom"). The star and grooves stayed as in the photo.
- Ask about size and purpose too. "25 mm, it's a coffee-cup topper" changed
  the nozzle, the feature sizes and the colour plan.

## 2. Name the views and read the photo right

**Name the sheet's views left to right**, before measuring. Use the
camera-position names the scripts use:

| Name | What the image shows |
|---|---|
| `front` | the face |
| `side` | camera at +X; the figure's front points LEFT in the image |
| `left` | camera at −X; the front points RIGHT |
| `back` | the back |
| `three-quarter` | front and the figure's left side, camera at front-right |
| `three-quarter-left` | the mirror image of `three-quarter` |

- Write the order down (e.g. `front,left,back,three-quarter-left` for the
  Santa sheet) and pass it unchanged to `render_parts.py` and
  `compare_views.py`.
- `compare_views` warns when another order or a mirrored side fits better.
  One agent compared a three-quarter render with the side photo and never
  saw that its box was a cube.

**AI product shots**:
- The camera is a little above the object (≈5°). A flat top shows as a band
  in the front view (the gift box lid: y 28–38), so the top is at the
  band's middle. `compare_views --elevation 5` renders the same way.
- A floor shadow widens the bottom rows and may join the views.
  - `--anchor <body colour>` cuts each view at the body's lowest row.
  - `compare_views` leaves out the bottom 10% of the height.
- Dark strokes on a coloured surface (the gift box face) are usually
  engraved grooves, darkened by shade, not a third colour. Ask in the
  question round.
- Two views of the same object rarely agree to the pixel. Decide which view
  rules each dimension.

## 3. Measure

```
python scripts/measure_reference.py reference.jpg --colors red,white --height 80 --step 3 \
    --masks masks.png --json profile.json
```

- **Look at `masks.png` first.**
  - Views are column bands of the silhouette, so a ribbon of another colour
    across the body does not split one. The anchor colour (the first in
    `--colors`) sets each view's bottom row and keeps a floor shadow from
    joining the views.
  - A picture sent through a messenger is recompressed. Specks of noise
    round the object are dropped; if `masks.png` still shows some, raise
    `--threshold` (default 20).
  - If the masks are wrong, pass `--views x0:x1,...`, `--rows y0:y1`, or a
    `#rrggbb` colour with `--tol`. Rows are the object's, not the
    picture's: `--rows 0:200` on a 200-pixel sheet scales every number by
    the empty margin too.
- `--height` is the design height you will build at, usually the object's
  height in the photo scaled to a round number such as 80.
- Rows give, in mm:
  - `z` from the bottom;
  - left/right of the object from the view's axis;
  - each colour's extent, with `n` = pixel count. A wide span with a small
    n is just edges.
- Measure per view:
  - **front**: the half-width profile `(r, z)`;
  - **side**: depth (depth/width ratio, e.g. 0.85–0.88), tilt of hats,
    where things sit front-to-back;
  - **back**: what shows behind, e.g. how low the hat goes.
- **A silhouette edge is not the front edge.** The lowest point of a tilted
  cuff in the front view is its SIDES hanging lower, not its front. Take
  front heights from the side view.
- **AI-generated reference sheets disagree between views.** Widths, heights
  and features shift. Decide which view rules each dimension, usually the
  front for widths and the side for depth and tilt, and say so in the
  docstring.
- Thin the profile before use: every 2nd–3rd row, and drop jagged outliers.

## 4. Model to the numbers

- Paste the profile as `BODY = [(r, z), ...]`, starting with the 50° base
  chamfer, and build at the design scale.
- Place secondary parts from measured numbers:
  - "brim front edge 57.5 high, back 48.8" gives the tilt;
  - "eyes at z 46.4, ±7.7".

## 5. The fidelity gate

```
python scripts/compare_views.py models/<name>/parts reference.jpg --views front,side,back,three-quarter --anchor red --info three-quarter
```

- Per view it reports:
  - IoU of the silhouettes;
  - aspect (model too wide or narrow);
  - which height bands differ, and by how much;
  - colour overlap.
- PASS needs IoU ≥ 0.92 and aspect within 8% on every gated view. Measured
  results:
  - good models: 0.93–0.96;
  - the cube copied by eye: 0.81–0.90, with "side: model wider by 64% at
    the top".
- Fix the numbers the bands point at, rebuild, and run the gate again.
- Differences the user approved (removed ribbons, chamfered bases) show up
  in the colour overlap or in the bottom band. Say so; do not tune them
  away.
- The limits are fixed. `--min-iou` and `--max-aspect` only go stricter, and
  front, side, left and back are always gated. One agent passed
  `--min-iou 0.40`, still failed, and shipped the model anyway.
- The verdict goes to `views_check.json` next to the parts folder.
  `make_3mf.py` builds no project from parts that failed or changed since.
  When the user has seen `views_check.png` and accepts the difference, run
  it with `--accept-views "<their words>"`; the words go into the 3MF's
  recipe.

## 6. Compare, with your own eyes

```
python scripts/render_parts.py parts --png compare.png --views front,side,back,three-quarter --reference reference.jpg
python scripts/render_parts.py parts --png closeup.png --views front,side --closeup
```

- `--reference` stacks the picture above the render, scaled to the same
  width. Compare proportions view by view: head/body ratio, hat height and
  tilt, feature positions, silhouette.
- `--closeup` lights from a low side angle. It shows surface banding,
  inlay edges, lumps and groove ends.
- Open the PNGs, actually look at them, and fix differences before showing
  the model. Then show the user the comparison image.
- Screen recordings from the user (for example the slicer showing a
  problem):
  `python scripts/video_frames.py rec.mp4 --out frames --count 12 --sheet sheet.jpg`,
  then read the sheet. The mini-snowman problems (missing eyes, white
  patches) were found this way.
