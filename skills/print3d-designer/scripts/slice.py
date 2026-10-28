"""Slice a model with the user's slicer presets and render the toolpaths.

Usage:
    python scripts/slice.py model.stl --nozzle 0.4 [--machine NAME] [--process NAME]
                            [--filament NAME] [--set key=value ...] [--layers 0.3,5,12.5] [--out DIR]
    python scripts/slice.py --presets machine|process|filament [--match TEXT]

Works with Bambu Studio-family slicers (Anycubic Slicer Next, Bambu Studio,
OrcaSlicer) through their command line. Presets are looked up by name in the
user's preset folders first, then the system folder (printer.json), and
flattened through their `inherits` chain, because the CLI wants complete
configs. The part is placed on the bed centre without rotation. Output:
<out>/plate_1.gcode, the flattened presets, toolpaths.png and layers.png.
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

import trimesh

sys.path.insert(0, str(Path(__file__).parent))
import config  # noqa: E402
import gcode_view  # noqa: E402

CFG = config.load()
SLICER = Path(CFG["slicer"]["exe"]) if CFG["slicer"].get("exe") else None
USER_DIRS = [Path(p) for p in CFG["slicer"].get("user_presets", [])]
SYSTEM_DIR = Path(CFG["slicer"]["system_presets"]) if CFG["slicer"].get("system_presets") else None
KINDS = ("machine", "process", "filament")
BED_CENTER = config.bed_centre(CFG)
DEFAULTS = CFG["nozzles"]  # nozzle size -> machine / process / filament / overrides


def require_slicer() -> Path:
    if SLICER is None or not SLICER.exists() or SYSTEM_DIR is None:
        raise SystemExit("slicer not configured: set slicer.exe and slicer.system_presets in printer.json")
    return SLICER


def index_presets() -> dict:
    """Map kind -> preset name -> source file; user presets shadow system ones."""
    require_slicer()
    index = {kind: {} for kind in KINDS}
    for root in [SYSTEM_DIR, *reversed(USER_DIRS)]:
        for kind in KINDS:
            for f in (root / kind).rglob("*.json"):
                try:
                    name = json.loads(f.read_text(encoding="utf-8")).get("name")
                except (json.JSONDecodeError, UnicodeDecodeError):
                    continue
                if name:
                    index[kind][name] = f
    return index


def flatten(index: dict, kind: str, name: str) -> dict:
    if name not in index[kind]:
        sys.exit(f"{kind} preset not found: {name!r}")
    own = json.loads(index[kind][name].read_text(encoding="utf-8"))
    parent = own.get("inherits")
    return {**flatten(index, kind, parent), **own} if parent else dict(own)


def system_ancestor(index: dict, kind: str, name: str) -> str:
    """Nearest preset in the inherits chain that ships with the slicer."""
    while not index[kind][name].is_relative_to(SYSTEM_DIR):
        name = json.loads(index[kind][name].read_text(encoding="utf-8"))["inherits"]
    return name


def finalize(cfg: dict, kind: str, machine_system: str) -> dict:
    # The CLI checks compatibility against the machine's system parent (its
    # `inherits`), not the machine's own name, and treats an empty list as
    # incompatible: keep that link on the machine, name it on the others.
    cfg.update(inherits="", type=kind, compatible_printers=[machine_system], compatible_prints=[])
    if kind == "machine" and cfg["name"] != machine_system:
        cfg["inherits"] = machine_system
    cfg["compatible_printers_condition"] = ""
    cfg["compatible_prints_condition"] = ""
    return cfg


def apply_overrides(cfgs: dict, overrides: dict) -> None:
    for key, value in overrides.items():
        target = next((k for k in ("process", "filament", "machine") if key in cfgs[k]), "process")
        old = cfgs[target].get(key)
        cfgs[target][key] = [value] * len(old) if isinstance(old, list) else value


def list_presets(kind: str, match: str) -> int:
    """Preset names of one kind, the user's own first: what printer.json's nozzles need."""
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # preset names are often not ASCII
    index = index_presets()[kind]
    rows = sorted((f.is_relative_to(SYSTEM_DIR), name) for name, f in index.items() if match.lower() in name.lower())
    for system, name in rows:
        print(f"{'system' if system else 'user  '}  {name}")
    print(f"{len(rows)} {kind} presets" + (f" matching {match!r}" if match else ""))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("model", type=Path, nargs="?")
    parser.add_argument("--nozzle", default=next(iter(DEFAULTS), "0.4"))
    parser.add_argument("--machine")
    parser.add_argument("--process")
    parser.add_argument("--filament")
    parser.add_argument("--set", action="append", default=[], metavar="KEY=VALUE")
    parser.add_argument("--layers", help="comma-separated Z heights to draw in layers.png")
    parser.add_argument("--out", type=Path)
    parser.add_argument("--presets", choices=KINDS, help="list the preset names of this kind and exit")
    parser.add_argument("--match", default="", help="with --presets: only names containing this text")
    args = parser.parse_args()
    if args.presets:
        return list_presets(args.presets, args.match)
    if args.model is None:
        parser.error("the model file is required")

    preset = config.nozzle(CFG, args.nozzle)
    names = {k: getattr(args, k) or preset[k] for k in KINDS}
    out = args.out or args.model.parent / f"slice_{args.nozzle}"
    out.mkdir(parents=True, exist_ok=True)
    for old in out.glob("*.gcode"):
        old.unlink()

    index = index_presets()
    machine_system = system_ancestor(index, "machine", names["machine"])
    cfgs = {k: finalize(flatten(index, k, names[k]), k, machine_system) for k in KINDS}
    overrides = dict(preset.get("overrides", {}))
    overrides.update(kv.split("=", 1) for kv in args.set)
    apply_overrides(cfgs, overrides)

    paths = {}
    for kind, cfg in cfgs.items():
        paths[kind] = out / f"preset_{kind}.json"
        paths[kind].write_text(json.dumps(cfg, indent=1, ensure_ascii=False), encoding="utf-8")
    for kind in KINDS:
        print(f"{kind:8}: {names[kind]}")
    if overrides:
        print("override:", ", ".join(f"{k}={v}" for k, v in overrides.items()))

    # Auto-arrange may rotate the part; place it on the bed centre ourselves so
    # the print keeps the orientation it was designed in.
    mesh = trimesh.load_mesh(args.model, force="mesh")
    lo, hi = mesh.bounds
    mesh.apply_translation([BED_CENTER[0] - (lo[0] + hi[0]) / 2, BED_CENTER[1] - (lo[1] + hi[1]) / 2, -lo[2]])
    placed = out / f"{args.model.stem}.stl"
    mesh.export(placed)

    cmd = [
        str(require_slicer()), "--slice", "0", "--arrange", "0", "--orient", "0",
        "--load-settings", f"{paths['machine']};{paths['process']}",
        "--load-filaments", str(paths["filament"]),
        "--outputdir", str(out), str(placed),
    ]
    run = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    gcodes = sorted(out.glob("*.gcode"))
    if run.returncode != 0 or not gcodes:
        tail = [l for l in (run.stdout + run.stderr).splitlines() if "error" in l.lower()][-15:]
        print(f"slicer failed (exit {run.returncode}):", *tail, sep="\n  ")
        return 1

    layers = [float(z) for z in args.layers.split(",")] if args.layers else None
    gcode_view.analyze(gcodes[0], out / "toolpaths.png", out / "layers.png", layers)
    return 0


if __name__ == "__main__":
    sys.exit(main())
