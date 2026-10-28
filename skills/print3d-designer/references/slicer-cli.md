# Driving a Bambu Studio-family slicer from the command line

Covers Anycubic Slicer Next, Bambu Studio and OrcaSlicer: same engine, same
CLI, same preset JSON. Tested on Anycubic Slicer Next 1.4.1.2 (Windows).
`scripts/slice.py` and `scripts/make_3mf.py` implement everything below.

## Contents
1. Where presets live
2. Flattening presets
3. The compatibility trap
4. Slicing one model
5. Colour project (one plate)
6. Several plates in one project
7. Checking a 3MF
8. Making a user preset
9. Useful override keys

## 1. Where presets live

| Kind of preset | Location |
|---|---|
| system | `%APPDATA%/<Slicer>/system/<Vendor>/{machine,process,filament}/*.json` |
| user | `%APPDATA%/<Slicer>/user/<user-id>/{machine,process,filament}/*.json`, plus `user/default/` |

- A file's `"name"` is what the GUI shows, not the file name.
- User presets are **diffs**: only the changed keys plus
  `"inherits": "<parent name>"`.
- Each user preset has a `.info` file beside it (`sync_info = update`,
  `base_id = <parent setting_id>`, …).

## 2. Flattening presets

The CLI wants complete configs. Merge the `inherits` chain from the root
down: `{**flatten(parent), **own}`. User presets shadow system presets of
the same name.

## 3. The compatibility trap

The CLI checks a process or filament's `compatible_printers` against the
machine's **system ancestor** (its `inherits`), not against the machine's
own name. It also treats an empty list as incompatible. So, after
flattening:

- **machine**: `inherits` = the nearest system ancestor. Keep that link.
- **process / filament**:
  - `compatible_printers = [<machine's system ancestor>]`;
  - `compatible_printers_condition = ""`;
  - `inherits = ""`.

Without this the CLI refuses with "process not compatible with printer".

## 4. Slicing one model

```
<slicer> --slice 0 --arrange 0 --orient 0 \
  --load-settings "machine.json;process.json" --load-filaments filament.json \
  --outputdir out model.stl
```

- `--arrange 1` (auto-arrange) **rotates parts**. Instead, pre-centre the
  mesh on the bed centre yourself and use `--arrange 0`. `slice.py` does
  this.
- The output is `out/plate_1.gcode`. On failure, grep the CLI output for
  "error".

## 5. Colour project (one plate, one object of several parts)

```
<slicer> --arrange 0 --orient 0 --assemble \
  --load-settings "machine.json;process.json" \
  --load-filaments "f1.json;f2.json;f3.json" --load-filament-ids 1,2,3 \
  --export-3mf name.3mf --outputdir work part_body.stl part_hat.stl part_eyes.stl
```

- `--assemble` merges the STLs into ONE object whose parts keep their
  coordinates. `--load-filament-ids` gives each part its filament (1-based,
  in STL order).
- Each filament JSON is a flattened preset with
  `filament_colour = ["#RRGGBB"]`.
- Parts are named after their STL file names. `make_3mf.py` renames the
  object and strips `.stl` inside `Metadata/model_settings.config`.

## 6. Several plates in one project (`--load-assemble-list`)

```json
{"plates": [
  {"plate_name": "", "need_arrange": false, "objects": [
    {"path": "body.stl", "count": 1, "filaments": [1], "assemble_index": [1],
     "pos_x": [125], "pos_y": [125], "pos_z": [0]},
    {"path": "pom.stl",  "count": 1, "filaments": [2], "assemble_index": [1],
     "pos_x": [125], "pos_y": [125], "pos_z": [0]}]},
  {"plate_name": "", "need_arrange": false, "objects": [ ... ]}]}
```

```
<slicer> --load-assemble-list plan.json --load-settings "m.json;p.json" \
  --load-filaments "f1.json;f2.json" --export-3mf out.3mf --outputdir work
```

Quirks:

- `plate_name` must exist but be **""**. The CLI crashes drawing plate
  names. Write the names into the zip afterwards
  (`key="plater_name" value="..."` in `model_settings.config`).
- `assemble_index` 0 leaves the parts as separate objects; a lifted part
  then "floats" and slicing fails. Use **≥ 1** to merge a plate's parts
  into one object.
- Each object lands at `pos + its own coordinates`, so centre each group
  on the origin first.
- This mode cannot be combined with `--assemble`.

## 7. Checking a 3MF

`<slicer> --slice 0 --outputdir out project.3mf` writes one
`plate_N.gcode` per plate. A 3MF with plate names crashes the CLI too, so
slice a copy with the names blanked. `make_3mf.py --check` does this and
runs `gcode_view` on every plate.

## 8. Making a user preset (e.g. a real 0.2 nozzle process)

1. Find the closest system process for a similar nozzle, for example
   "0.12mm Standard @<printer> 0.25 nozzle".
2. Write `user/<id>/process/<Name>.json`, copying the `version` from a
   sibling preset. The real one:

   ```json
   {"name": "0.12mm Standard @AC KS1 0.2 Microswiss", "print_settings_id": "<same as name>",
    "inherits": "0.12mm Standard @Anycubic Kobra S1 0.25 nozzle", "from": "User", "is_custom_defined": "0",
    "compatible_printers": ["Anycubic Kobra S1 0.2 Microswiss nozzle"],
    "line_width": "0.22", "outer_wall_line_width": "0.22", "top_surface_line_width": "0.22",
    "internal_solid_infill_line_width": "0.22", "support_line_width": "0.22",
    "inner_wall_line_width": "0.24", "sparse_infill_line_width": "0.24",
    "initial_layer_line_width": "0.25", "version": "1.3.2604.18"}
   ```

   - Speeds and 4 walls come from the 0.25 parent and keep flow ≤ 3.7 mm³/s
     at 0.12 mm layers.
3. Add `<Name>.info` beside it:

   ```
   sync_info = update
   user_id =
   setting_id =
   base_id = GP004
   updated_time = <unix time>
   ```

   - `base_id` is the parent's `setting_id`.
4. Ask the user before creating it. Then tell them where it appears: only
   when that machine is selected, after a slicer restart.

## 9. Useful override keys (`--set key=value`, or `"set"` in print.json)

| Key | Use |
|---|---|
| `layer_height` | 0.12 / 0.16 on a 0.2 nozzle |
| `internal_solid_infill_speed`, `sparse_infill_speed`, `outer_wall_speed` | flow limits |
| `flush_into_infill` | **0** for light colours (purge tints infill, which shows through white) |
| `enable_prime_tower` | keep 1 for multi-colour |
| `brim_type` (`outer_only`, `no_brim`), `brim_width` | small parts: the auto brim grew to 5 mm on a 17 mm figure; 2.5 mm `outer_only` was enough |
| `wall_loops`, `top_shell_layers`, `bottom_shell_layers` | shell thickness |
| `support_threshold_angle`, `enable_support` | normally off: design the overhangs away |
| `xy_hole_compensation`, `xy_contour_compensation`, `filament_shrink` | dimensional accuracy; check what the user's presets already set |

`slice.py` routes each key to the preset that has it (process first, then
filament, then machine), and expands list-valued keys.
