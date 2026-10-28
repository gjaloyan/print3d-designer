# Reading the printer (Moonraker), read-only

Klipper printers expose Moonraker's HTTP API:

- Mainsail / Fluidd installs;
- Anycubic Kobra S1/3 with Rinkhals custom firmware;
- Creality K1/K2 rooted;
- Voron, and others.

Use it to learn the setup, see the loaded colours and check past jobs.
**Only GET.**

- Never start, stop, pause or home the printer.
- Never send G-code, change config, or restart services, unless the user
  explicitly asks in chat.
- The user's own words for this setup were "you can check all", meaning
  read.

`python scripts/moonraker.py [--url http://IP] <command>`. The URL comes
from `printer.moonraker` in printer.json.

| Command | Endpoint(s) | Use |
|---|---|---|
| `info` | `/printer/info`, `/server/info` | state; which components exist (e.g. `mmu_ace`, `kobra`) |
| `status` | `/printer/objects/query?print_stats&display_status&virtual_sdcard&extruder&heater_bed` | is it printing, which file, progress, temperatures |
| `ace` | `/printer/objects/query?filament_hub` | ACE Pro slots: type, colour, ready, RFID |
| `objects [word]` | `/printer/objects/list` | discover what this firmware exposes |
| `history` | `/server/history/list?limit=N&order=desc` | what was printed, result, duration, filament |
| `files` | `/server/files/list?root=gcodes` | G-codes on the printer |
| `config [file]` | `/server/files/list?root=config`, `/server/files/config/<file>` | printer.cfg, moonraker conf |
| `settings FILE` | `/server/files/gcodes/<file>` + `Range: bytes=-65536` | slicer settings embedded at the end of a G-code |
| `snapshot out.jpg` | `/webcam/?action=snapshot`, `:8080/?action=snapshot`, `:8080/snapshot` | webcam still (503 when the stream is off) |

## Notes from the Kobra S1 + Rinkhals

- The ACE answers to the object `filament_hub`, although
  `/printer/objects/list` shows only `ota_filament_hub` (an updater) and a
  `gcode_macro OTA_FILAMENT_HUB_START`.
  - `filament_hub.filament_hubs[].slots[]` has `index`, `type`, `color`
    `[r, g, b]`, `status`, `rfid`.
  - `current_filament` reads like `"0-1"` (unit 0, slot 1).
- Print files sent from the slicer land in `.3mf_temp/` with names like
  `1026-0152-Santa one piece_plate(01)_PETG_0.16_6h20m32s.gcode`. The name
  carries the GUI time estimate.
- The board is a single-core ARM. **Do not download a whole G-code while
  it prints**: read its tail with a Range request (`settings`).
- `printer/info` returns empty `hostname` and `software_version` on
  Rinkhals. That is normal.
- Rinkhals' own web UI may sit on port 80, with Moonraker on port 80 or
  7125. Try both.

## Useful checks

- Before a colour print, run `ace`. Compare the slots with the project's
  filament colours and tell the user what to load. For example: "Santa
  needs red, and slot 1 holds magenta."
- After a print, `history` shows whether it was cancelled and when. Ask
  why before redesigning.
- `settings <file> --keys layer_height,nozzle_diameter,filament_colour,flush_into_infill`
  confirms the user sliced what you prepared.
