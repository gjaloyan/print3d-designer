"""Read-only look at a Klipper/Moonraker printer (Mainsail/Fluidd, Rinkhals, Creality K-series...).

Usage:
    python scripts/moonraker.py [--url http://192.168.1.50] COMMAND
      info                 printer and Moonraker versions, state
      status               current job: state, file, progress, temperatures
      ace                  multi-colour unit slots (Anycubic ACE via filament_hub), if any
      objects [WORD]       Klipper objects, optionally filtered (find what a printer exposes)
      history [--limit N]  last jobs: file, result, duration, filament
      files                G-code files on the printer, newest first
      config [FILE]        list config files, or print one (printer.cfg, ...)
      settings FILE [--keys a,b]   slicer settings embedded in a G-code, read from its tail
      snapshot OUT.jpg     webcam still, if a stream is running

Only GET requests: nothing here starts, stops, moves or changes the printer.
The URL defaults to printer.moonraker in printer.json. `settings` reads just
the last 64 KB of the file with an HTTP Range request - the slicer writes its
config there - so a large G-code is never downloaded while the printer (often
a single-core ARM board) is busy printing.
"""

import argparse
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import config  # noqa: E402

TIMEOUT = 8


def get(base: str, path: str, headers: dict | None = None, raw: bool = False):
    req = urllib.request.Request(base.rstrip("/") + path, headers=headers or {}, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            data = resp.read()
    except urllib.error.HTTPError as e:
        raise SystemExit(f"GET {path}: HTTP {e.code}")
    except (urllib.error.URLError, TimeoutError) as e:
        raise SystemExit(f"GET {path}: {e} - is the printer on and the URL right?")
    return data if raw else json.loads(data)["result"]


def query(base: str, *objects: str) -> dict:
    return get(base, "/printer/objects/query?" + "&".join(urllib.parse.quote(o) for o in objects))["status"]


def cmd_info(base, args):
    info = get(base, "/printer/info")
    server = get(base, "/server/info")
    print(f"hostname : {info.get('hostname')}")
    print(f"state    : {info.get('state')} - {info.get('state_message', '').strip()}")
    print(f"klipper  : {info.get('software_version')}")
    print(f"moonraker: {server.get('moonraker_version')}, components: {', '.join(server.get('components', []))}")


def cmd_status(base, args):
    s = query(base, "print_stats", "display_status", "virtual_sdcard", "extruder", "heater_bed")
    ps, ex, bed = s.get("print_stats", {}), s.get("extruder", {}), s.get("heater_bed", {})
    progress = s.get("display_status", {}).get("progress") or s.get("virtual_sdcard", {}).get("progress") or 0
    print(f"state    : {ps.get('state')}  file: {ps.get('filename') or '-'}")
    print(f"progress : {100 * progress:.1f}%  printed {ps.get('print_duration', 0) / 60:.0f} min,"
          f" filament {ps.get('filament_used', 0) / 1000:.2f} m")
    print(f"nozzle   : {ex.get('temperature', 0):.0f} / {ex.get('target', 0):.0f} C")
    print(f"bed      : {bed.get('temperature', 0):.0f} / {bed.get('target', 0):.0f} C")


def cmd_ace(base, args):
    # Anycubic's ACE answers to `filament_hub` although /printer/objects/list
    # shows only `ota_filament_hub` (an updater) and a macro.
    name, s = "filament_hub", query(base, "filament_hub").get("filament_hub")
    if not s:
        objects = get(base, "/printer/objects/list")["objects"]
        listed = [o for o in objects if " " not in o and ("hub" in o.lower() or "ace" in o.lower() or "mmu" in o.lower())]
        listed = [o for o in listed if "ota" not in o.lower()]
        if not listed:
            print("no filament_hub/ace/mmu object: no multi-colour unit Moonraker can see")
            return
        name = listed[0]
        s = query(base, name)[name]
    hubs = [name]
    print(f"{hubs[0]}: current {s.get('current_filament', '-')}, auto refill {s.get('auto_refill')}")
    for hub in s.get("filament_hubs", []):
        dry = hub.get("dryer_status", {})
        print(f" unit {hub.get('id')}: {hub.get('status')}, {hub.get('temp')} C, dryer {dry.get('status')}")
        for slot in hub.get("slots", []):
            rgb = slot.get("color") or [0, 0, 0]
            print(f"   slot {slot.get('index')}: {slot.get('type') or '?':6} #{''.join(f'{c:02X}' for c in rgb[:3])}"
                  f"  {slot.get('status')}{'  rfid' if slot.get('rfid') else ''}")


def cmd_objects(base, args):
    objects = get(base, "/printer/objects/list")["objects"]
    word = (args.word or "").lower()
    picked = [o for o in objects if word in o.lower()]
    print(f"{len(picked)} of {len(objects)} objects")
    for o in picked:
        print(" ", o)


def cmd_history(base, args):
    jobs = get(base, f"/server/history/list?limit={args.limit}&order=desc")["jobs"]
    for job in jobs:
        start = datetime.fromtimestamp(job.get("start_time", 0)).strftime("%Y-%m-%d %H:%M")
        print(f"{start}  {job.get('status'):10} {job.get('print_duration', 0) / 60:6.0f} min"
              f"  {job.get('filament_used', 0) / 1000:6.2f} m  {job.get('filename')}")


def cmd_files(base, args):
    files = get(base, "/server/files/list?root=gcodes")
    for f in sorted(files, key=lambda f: -f.get("modified", 0))[:args.limit]:
        when = datetime.fromtimestamp(f.get("modified", 0)).strftime("%Y-%m-%d %H:%M")
        print(f"{when}  {f.get('size', 0) / 1e6:7.2f} MB  {f.get('path')}")


def cmd_config(base, args):
    if not args.file:
        for f in sorted(get(base, "/server/files/list?root=config"), key=lambda f: f.get("path")):
            print(f"{f.get('size', 0):8} B  {f.get('path')}")
        return
    path = "/server/files/config/" + urllib.parse.quote(args.file)
    print(get(base, path, raw=True).decode("utf-8", errors="replace"))


def cmd_settings(base, args):
    path = "/server/files/gcodes/" + urllib.parse.quote(args.file)
    tail = get(base, path, headers={"Range": "bytes=-65536"}, raw=True).decode("utf-8", errors="replace")
    keys = [k.strip() for k in (args.keys or "").split(",") if k.strip()]
    found = 0
    for line in tail.splitlines():
        if line.startswith("; ") and " = " in line:
            key, value = line[2:].split(" = ", 1)
            if not keys or key in keys:
                print(f"{key} = {value[:200]}")
                found += 1
    if not found:
        print("no '; key = value' settings in the last 64 KB (not a Bambu/Orca-family G-code?)")


def cmd_snapshot(base, args):
    host = urllib.parse.urlparse(base)
    root = f"{host.scheme}://{host.hostname}"
    for url in (f"{root}/webcam/?action=snapshot", f"{root}:8080/?action=snapshot", f"{root}:8080/snapshot"):
        try:
            with urllib.request.urlopen(url, timeout=TIMEOUT) as resp:
                data = resp.read()
            if data[:2] == b"\xff\xd8":
                Path(args.out).write_bytes(data)
                print(f"snapshot: {args.out} from {url}")
                return
        except (urllib.error.URLError, TimeoutError):
            continue
    print("no webcam snapshot (stream off, or a different URL on this firmware)")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", help="Moonraker base URL (default: printer.moonraker in printer.json)")
    sub = parser.add_subparsers(dest="cmd", required=True)
    for name in ("info", "status", "ace"):
        sub.add_parser(name)
    p = sub.add_parser("objects")
    p.add_argument("word", nargs="?")
    for name in ("history", "files"):
        p = sub.add_parser(name)
        p.add_argument("--limit", type=int, default=10)
    p = sub.add_parser("config")
    p.add_argument("file", nargs="?")
    p = sub.add_parser("settings")
    p.add_argument("file")
    p.add_argument("--keys")
    p = sub.add_parser("snapshot")
    p.add_argument("out")
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # file names are often not ASCII

    base = args.url or config.load()["printer"].get("moonraker")
    if not base:
        sys.exit("no printer URL: pass --url or set printer.moonraker in printer.json")
    if not base.startswith("http"):
        base = "http://" + base
    globals()[f"cmd_{args.cmd}"](base, args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
