# Questions to ask before modelling (and after the first slice)

The user owns every decision that changes how the model looks or how long it
prints. Ask BEFORE writing model code, using the agent's question tool:
`AskUserQuestion` in Claude Code, `clarify` in Hermes, or a numbered list
in plain chat.

- Give 2–4 options per question, with **your recommendation first**.
- Under each option, write what it costs (time, colour changes, grams) and
  what it changes visually.
- Ask at most ~4 questions per round, and ask a second round when the
  answers open new choices.
- Never bundle an approval into a statement ("I'll add a skirt under the
  hat"): ask.
- Do not ask what the reference or the setup already answers. Read the
  picture, the printer's loaded filaments (`moonraker.py ace`) and
  printer.json first.

## Contents
1. Round 1: before modelling
2. Estimating costs before a model exists
3. Round 2: after the first slice
4. Ambiguous requests
5. Real rounds from past sessions

## 1. Round 1: before modelling (always)

| # | Topic | Why it matters | Typical options |
|---|---|---|---|
| 1 | **Size and purpose** | sets the nozzle, the minimum features, what detail survives | "80 mm figurine, 0.4 nozzle (Recommended)", "50 mm", "25 mm topper, 0.2 nozzle"; ask the purpose if unclear ("for a coffee cup?") |
| 2 | **One piece or parts; which colours** | colour changes dominate time and waste | "one piece, N colours (~X changes, ~Y h)", "parts glued or slid on (0–Z changes)", "one colour, features engraved (0 changes)" |
| 3 | **Detail the size cannot hold** | knit, fur, tiny text, stitches | "simplified ribs (Recommended)", "smooth", "full texture (needs ≥ 80 mm, slow build)" |
| 4 | **Print-driven deviations** (multiSelect) | each one changes the look | one option per change: "50° chamfer at the base: the ball rolls in at the bed", "50° skirt under the tilted cuff", "chamfer under the scarf", "flush face instead of a raised nose" |

Also cover, when relevant:

- **Colours vs what is loaded.** Example: "teal is not in the ACE (white,
  magenta, yellow, black): load it in slot 2?"
- **Fit or assembly** for parts: glue, slide-on ring, peg.
- **What must stay exactly as in the reference**, e.g. "only the base" for
  the tree.

## 2. Estimating costs before a model exists

Round 1 needs numbers. Estimate them from the reference's proportions:

```
mixed_height = height of the zone where two or more colours share a layer (mm)
layers       = mixed_height / layer_height
changes      ≈ 2 × layers per extra colour in that zone (back and forth)
purge        ≈ changes × flush_mm3 × density / 1000  g   (280 mm³ ≈ 0.35 g PETG)
extra time   ≈ changes × 1–3 min   (the slicer's CLI estimate leaves this out)
```

- A face band of black inside a white/teal zone adds ~2 changes per layer of
  the face.
- A height split (everything above one Z is colour B) costs 1 change.
- Parts cost 0 changes; inlays in the top layers of a plate printed face-up
  cost ~2 per inlay layer.
- Say these are estimates, and give exact numbers after slicing
  (`make_3mf.py --check`).

## 3. Round 2: after the first slice

- **Layer height**, as a table: changes, time and grams for 0.12 against
  0.16 (or 0.2 against 0.28).
  - The mini snowman: 63 changes / 3 h 52 / 27 g against 49 / 2 h 57 /
    21 g; the user picked 0.16.
- **Anything the check found** that needs a visible change, for example a
  stroke too thin for the nozzle, or a shell that tears.
- **Plates**: one project with several plates, or separate files.

## 4. Ambiguous requests: ask, do not guess

| Request | Possible meanings | Ask |
|---|---|---|
| "merge these 2 models" | one 3MF file with 2 plates, or ONE solid object | "One file with two plates, or one solid model printed in one go (N changes)?" |
| "make it smaller" | scale only (features vanish), or a size variant | "Scale as is (eyes disappear below X mm), or a small version with thicker features?" |
| "like on the photo" | exact, or printable | list the deviations and let the user pick (multiSelect) |
| "colour" | full colour, or a few accents | give options with change counts |

## 5. Real rounds from past sessions

- **Christmas tree.** The user said: "if you need to change any detail for
  printing, tell me first."
  - Q1: boundary? They answered "exactly as the photo".
  - Q2: size? They answered "25 mm, a coffee-cup topper", which meant a 0.2
    nozzle.
  - Q3: which changes? They chose "only the base". The star and grooves
    stayed as in the photo.
- **Santa.**
  - Size: 25 mm.
  - Printing: "in parts (Recommended)".
  - Changes: "yes, all (Recommended)".
  - Second round: "2 parts, ~11 changes (Recommended)".
  - Later, "merge" meant one solid object, so a new one-piece build was
    needed.
- **Mini snowman.** After the slice the question was layer 0.12 against
  0.16, with the numbers; the user chose 0.16.
