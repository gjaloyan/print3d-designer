# Multi-colour printing (ACE Pro / AMS-style single-nozzle changers)

A single-nozzle changer pays for every colour change:

- ~280 mm³ purge (≈ 0.35 g PETG);
- ~1–3 min;
- a prime-tower segment.

Count changes before choosing a design. The user decides between faithful
colours and print time; give them the numbers.

## Contents
1. What a change costs
2. Designs that need few changes
3. Light over dark
4. The project file
5. Real numbers

## 1. What a change costs

- Changes ≈ 1–2 per layer that holds 2 colours, plus the switch back.
  - A 0.16 mm layer face band 3 mm tall is ~19 layers, so ~40 changes.
- Purge is done by the firmware.
  - It is **not in the G-code**: only the footer's grams include it.
  - `gcode_view` reports the changes plus a purge estimate
    (`flush_mm3_per_change` in printer.json).
- The CLI time estimate leaves out change time.
  - The Santa one-piece read 4 h 53 in the CLI and 6 h 20 in the slicer
    GUI. Budget ~1 min per change on top.
- `flush_into_infill` saves filament but tints the infill: set it to 0
  when a light colour is on the outside.

## 2. Designs that need few changes (pick with the user)

| Design | Changes | When |
|---|---|---|
| **One colour + engraved features** (`<name>.stl`) | 0 | quick, paintable |
| **Height split**: everything above one Z is colour B | 1 | hat tip + pom-pom, star on a tree; split at the boundary's highest point |
| **Parts**: each colour group printed separately, then glued or slid on | 0–1 per part | the beard plate plus brim ring of Santa; needs a pocket or seat |
| **Face-up plate**: a flat part lying on its back with inlays only in its top layers | ~2 per inlay layer | eyes on a beard plate: 14 changes, not 100 |
| **One piece, full colour** | many | the most faithful, slowest; the user chose it for Santa at 0.16 mm |

Tell the user how many changes and how much time each option costs, then
let them choose. They picked "parts, ~11 changes (recommended)" first, and
later "merge into one model". "Merge" meant **one solid object**, not one
file.

## 3. Light over dark

- A light skin over a dark part shows through:
  - two PETG walls of white over teal look teal-tinted;
  - purge-tinted infill shows too.
- Keep **≥ 2.5 mm of light material** behind visible light surfaces (a
  "white core"). For a dark part that dips into a light body, let the light
  body win inside (`dark = hat - body`).
- Keep rims outside the body all round, so no colour becomes a thin wedge
  over the other.
- Check: `ray_colors.py skin parts --light white --dark teal --min 1.0`.
  - Small patches along borders are normal.
  - A large patch in the middle of a light area is the defect.
- A thin dark shell over light is also weak. Keep it ≥ 1 mm, or let it
  print solid (the mini snowman's hat).

## 4. The project file

`templates/print.json` (one plate) and `templates/print_plates.json`
(several plates):

```json
{"title": "...", "output": "name.3mf", "nozzle": "0.2",
 "set": {"layer_height": "0.16", "flush_into_infill": "0"},
 "filaments": [{"preset": "<user filament preset name>", "colour": "#FFFFFF"}, ...],
 "parts": [{"stl": "parts/white.stl", "name": "Body", "filament": 1}, ...]}
```

- A filament preset can repeat with different colours: the colour is
  written per slot.
- Several parts can share a filament. The snowman's pink cheeks used
  filament 1 because only 4 slots were free.
- Match the colours to what is loaded in the changer:
  `python scripts/moonraker.py ace` lists the slots' type and colour.
  - Before the print, tell the user which colour must be loaded where, for
    example "load red PETG for Santa".
- `python scripts/make_3mf.py print.json --check`:
  - builds the project;
  - slices it;
  - draws the layers in filament colours, so you can check that colours
    land where intended;
  - reports changes, grams per filament, and flow alerts.

## 5. Real numbers (Kobra S1 + ACE Pro, PETG)

| Model | Size | Nozzle / layer | Changes | Time (CLI) | Filament |
|---|---|---|---|---|---|
| Snowman, mono, engraved | 87 mm | 0.4 / 0.2 | 0 | 1.6 h | 30 g |
| Snowman, 5 colours | 87 mm | 0.4 / 0.2 | 198 | 11.5 h | 117 g |
| Christmas tree + star | 25 mm | 0.2 / 0.12 | 9 | ~1.3 h | — |
| Mini snowman | 17.4 mm | 0.2 / 0.12 | 63 | 3 h 52 | 27 g |
| Mini snowman | 17.4 mm | 0.2 / 0.16 | 49 | 2 h 57 | 21 g |
| Santa, body (height split) | 25 mm | 0.2 | 1 | — | — |
| Santa, beard plate face-up | — | 0.2 | 14 | — | — |
| Santa, one piece | 25 mm | 0.2 / 0.12 | 113 | 6 h 35 | 47 g |
| Santa, one piece | 25 mm | 0.2 / 0.16 | 85 | 4 h 53 | 36 g |

In small colour figures the purge outweighs the model several times over:
the mini snowman scaled down naively used 8.7 g of purge for a 0.65 g
figure. Say so when proposing full colour.
