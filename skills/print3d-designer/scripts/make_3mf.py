"""Build a multi-colour slicer project (.3mf) from colour parts.

Usage:
    python scripts/make_3mf.py models/<name>/print.json [--check]

Works with Bambu Studio-family slicers (Anycubic Slicer Next, Bambu Studio,
OrcaSlicer) configured in printer.json.

print.json describes the project:
    {"title": "Snowman", "output": "snowman.3mf", "nozzle": "0.4",
     "process": "...optional preset name...", "set": {"key": "value"},
     "filaments": [{"preset": "Kingroon PETG_White", "colour": "#FFFFFF"}, ...],
     "parts": [{"stl": "parts/white.stl", "name": "Body", "filament": 1}, ...]}
or, for several build plates in one project, instead of "parts":
     "plates": [{"name": "Body", "parts": [...]}, {"name": "Beard", "parts": [...]}]

The parts of a plate share one coordinate system; they are moved together to
the bed centre and assembled by the slicer's CLI into ONE object whose parts
carry their filament, with the user's machine/process/filament presets and
colours saved in the project. --check slices every plate of the finished 3MF
and renders the toolpaths coloured by filament.
"""

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

import numpy as np
import trimesh

sys.path.insert(0, str(Path(__file__).parent))
import config  # noqa: E402
import gcode_view  # noqa: E402
import slice as sl  # noqa: E402


def write_presets(spec: dict, work: Path) -> tuple[list[str], list[str]]:
    index = sl.index_presets()
    preset = config.nozzle(sl.CFG, spec.get("nozzle", "0.4"))
    machine = spec.get("machine", preset["machine"])
    process = spec.get("process", preset["process"])
    msys = sl.system_ancestor(index, "machine", machine)
    cfgs = {
        "machine": sl.finalize(sl.flatten(index, "machine", machine), "machine", msys),
        "process": sl.finalize(sl.flatten(index, "process", process), "process", msys),
        "filament": {},
    }
    sl.apply_overrides(cfgs, {**preset.get("overrides", {}), **spec.get("set", {})})
    if len(spec["filaments"]) > 1 and "wipe_tower_x" not in spec.get("set", {}):
        # The prime tower's default spot (OrcaSlicer: x 15, y 220) lies off a small bed;
        # put it in the back-right corner, clear of the centred model.
        bed_x, bed_y, _ = config.bed(sl.CFG)
        width = cfgs["process"].get("prime_tower_width", "35")
        width = float(width[0] if isinstance(width, list) else width)
        cfgs["process"]["wipe_tower_x"] = [f"{bed_x - width - 10:.0f}"]
        cfgs["process"]["wipe_tower_y"] = [f"{bed_y - width - 30:.0f}"]
    settings = []
    for kind in ("machine", "process"):
        path = work / f"{kind}.json"
        path.write_text(json.dumps(cfgs[kind], indent=1, ensure_ascii=False), encoding="utf-8")
        settings.append(str(path))
    filaments = []
    for i, fil in enumerate(spec["filaments"], 1):
        cfg = sl.finalize(sl.flatten(index, "filament", fil["preset"]), "filament", msys)
        cfg["filament_colour"] = [fil["colour"]]
        path = work / f"filament_{i}.json"
        path.write_text(json.dumps(cfg, indent=1, ensure_ascii=False), encoding="utf-8")
        filaments.append(str(path))
    print(f"machine : {machine}\nprocess : {process}")
    for i, fil in enumerate(spec["filaments"], 1):
        print(f"filament {i}: {fil['preset']}  {fil['colour']}")
    return settings, filaments


def place_parts(parts: list[dict], base: Path, work: Path, centre: tuple[float, float]) -> list[str]:
    """Move a plate's parts together so the group is centred on `centre` at z=0."""
    meshes = [trimesh.load_mesh(base / p["stl"], force="mesh") for p in parts]
    lo = np.min([m.bounds[0] for m in meshes], axis=0)
    hi = np.max([m.bounds[1] for m in meshes], axis=0)
    shift = [centre[0] - (lo[0] + hi[0]) / 2, centre[1] - (lo[1] + hi[1]) / 2, -lo[2]]
    files = []
    for part, mesh in zip(parts, meshes):
        folder = work / f"plate{id(parts)}"
        folder.mkdir(exist_ok=True)
        path = folder / f"{part['name']}.stl"  # the slicer names each part after its file
        mesh.apply_translation(shift)
        mesh.export(path)
        files.append(str(path))
    return files


def retitle(path: Path, titles: list[str], plate_names: list[str] | None = None) -> None:
    """Name the objects (in order) and plates, and drop file suffixes from part names."""
    tmp = path.with_suffix(".tmp")
    names = iter(titles)
    plates = iter(plate_names or [])
    with zipfile.ZipFile(path) as src, zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as dst:
        for item in src.infolist():
            data = src.read(item.filename)
            if item.filename == "Metadata/model_settings.config":
                text = data.decode("utf-8")
                text = re.sub(r'(<object id="\d+">\s*<metadata key="name" value=")[^"]*(")',
                              lambda m: m.group(1) + next(names, "Model") + m.group(2), text)
                text = re.sub(r'(key="name" value="[^"]*?)(\.stl)?(\._\d+)?"', r'\1"', text)
                if plate_names:  # left empty for the CLI, which crashes drawing plate names
                    text = re.sub(r'(key="plater_name" value=")[^"]*(")',
                                  lambda m: m.group(1) + next(plates, "") + m.group(2), text)
                data = text.encode("utf-8")
            dst.writestr(item, data)
    tmp.replace(path)


def check(project: Path, out: Path) -> None:
    out.mkdir(exist_ok=True)
    for old in out.glob("*.gcode"):
        old.unlink()
    # The CLI crashes drawing plate names, so slice a copy without them.
    nameless = out / f"_check_{project.name}"
    with zipfile.ZipFile(project) as src, zipfile.ZipFile(nameless, "w", zipfile.ZIP_DEFLATED) as dst:
        for item in src.infolist():
            data = src.read(item.filename)
            if item.filename == "Metadata/model_settings.config":
                data = re.sub(rb'(key="plater_name" value=")[^"]*(")', rb"\1\2", data)
            dst.writestr(item, data)
    run = subprocess.run([str(sl.require_slicer()), "--slice", "0", "--outputdir", str(out), str(nameless)],
                         capture_output=True, text=True, encoding="utf-8", errors="replace")
    nameless.unlink()
    gcodes = sorted(out.glob("plate_*.gcode"))
    if run.returncode != 0 or not gcodes:
        tail = [l for l in (run.stdout + run.stderr).splitlines() if "error" in l.lower()][-10:]
        sys.exit("slicing the project failed:\n  " + "\n  ".join(tail))
    for gcode in gcodes:
        tag = "" if len(gcodes) == 1 else f"_{gcode.stem}"
        print(f"==== {gcode.name}")
        gcode_view.analyze(gcode, out / f"toolpaths{tag}.png", out / f"layers{tag}.png")


def export_single(spec: dict, base: Path, work: Path, settings, filaments, name: str):
    files = place_parts(spec["parts"], base, work, sl.BED_CENTER)
    return [str(sl.require_slicer()), "--arrange", "0", "--orient", "0", "--assemble",
            "--load-settings", ";".join(settings), "--load-filaments", ";".join(filaments),
            "--load-filament-ids", ",".join(str(p["filament"]) for p in spec["parts"]),
            "--export-3mf", name, "--outputdir", str(work), *files]


def export_plates(spec: dict, base: Path, work: Path, settings, filaments, name: str):
    """Several plates: the CLI's assemble list. Objects sharing an assemble_index
    (>= 1; 0 leaves them separate) become one object per plate; each object
    lands at pos + its own coordinates, so groups are centred on the origin."""
    plates = []
    for plate in spec["plates"]:
        files = place_parts(plate["parts"], base, work, (0.0, 0.0))
        objects = [{"path": f, "count": 1, "filaments": [p["filament"]], "assemble_index": [1],
                    "pos_x": [sl.BED_CENTER[0]], "pos_y": [sl.BED_CENTER[1]], "pos_z": [0.0]}
                   for f, p in zip(files, plate["parts"])]
        plates.append({"plate_name": "", "need_arrange": False, "objects": objects})
    plan = work / "assemble.json"
    plan.write_text(json.dumps({"plates": plates}), encoding="utf-8")
    return [str(sl.require_slicer()), "--load-assemble-list", str(plan),
            "--load-settings", ";".join(settings), "--load-filaments", ";".join(filaments),
            "--export-3mf", name, "--outputdir", str(work)]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("spec", type=Path)
    parser.add_argument("--check", action="store_true", help="slice the project and render it")
    args = parser.parse_args()
    spec = json.loads(args.spec.read_text(encoding="utf-8"))
    base = args.spec.parent
    project = base / spec.get("output", f"{base.name}.3mf")

    plates = spec.get("plates")
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        settings, filaments = write_presets(spec, work)
        export = export_plates if plates else export_single
        cmd = export(spec, base, work, settings, filaments, project.name)
        run = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
        made = work / project.name
        if run.returncode != 0 or not made.exists():
            tail = [l for l in (run.stdout + run.stderr).splitlines() if "error" in l.lower()][-10:]
            print("export failed:", *tail, sep="\n  ")
            return 1
        if plates:
            retitle(made, [p["name"] for p in plates], [p["name"] for p in plates])
        else:
            retitle(made, [spec.get("title", base.name)])
        shutil.copyfile(made, project)
    for i, plate in enumerate(plates or [{"name": spec.get("title", base.name), "parts": spec["parts"]}], 1):
        print(f"plate {i}: {plate['name']}")
        for p in plate["parts"]:
            print(f"  part {p['name']:16} -> filament {p['filament']}")
    print(f"project : {project}")
    if args.check:
        check(project, base / f"slice_{project.stem}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
