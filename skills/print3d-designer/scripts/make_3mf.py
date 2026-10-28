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

The 3MF also carries this recipe (Metadata/print3d_spec.json, with the folder
the part paths are relative to), so the project can be rebuilt for another printer.
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
        fil.setdefault("colour", "#FFFFFF")
        if fil.get("preset", "default") == "default":  # the material printer.json names for this nozzle
            fil["preset"] = preset["filament"]
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
    plates = []
    for gcode in gcodes:
        tag = "" if len(gcodes) == 1 else f"_{gcode.stem}"
        print(f"==== {gcode.name}")
        plates.append(gcode_view.summary(gcode_view.analyze(gcode, out / f"toolpaths{tag}.png",
                                                            out / f"layers{tag}.png")))
    if len(plates) > 1:  # each plate wrote its own summary.json over the last one: the whole project's
        (out / "summary.json").write_text(json.dumps(gcode_view.combine(plates), indent=1), encoding="utf-8")


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


def write_plain_3mf(plates: list[dict], base: Path, path: Path, centre: tuple[float, float],
                    title: str = "Model") -> None:
    """A geometry-only 3MF any slicer opens: per plate ONE object whose parts are the colour
    parts (separate touching objects make Bambu-family slicers fail), centred on the bed
    (plates side by side), part colours as materials."""
    colours, objects, items = [], [], []
    offset = 0.0
    for plate in plates:
        meshes = [trimesh.load_mesh(base / p["stl"], force="mesh") for p in plate["parts"]]
        lo = np.min([m.bounds[0] for m in meshes], axis=0)
        hi = np.max([m.bounds[1] for m in meshes], axis=0)
        shift = [centre[0] + offset - (lo[0] + hi[0]) / 2, centre[1] - (lo[1] + hi[1]) / 2, -lo[2]]
        offset += hi[0] - lo[0] + 10
        components = []
        for part, mesh in zip(plate["parts"], meshes):
            colour = part.get("colour", "#FFFFFF").upper()
            if colour not in colours:
                colours.append(colour)
            v = mesh.vertices + shift
            verts = "".join(f'<vertex x="{x:.4f}" y="{y:.4f}" z="{z:.4f}"/>' for x, y, z in v)
            tris = "".join(f'<triangle v1="{a}" v2="{b}" v3="{c}"/>' for a, b, c in mesh.faces)
            oid = len(objects) + 2
            name = part.get("name", Path(part["stl"]).stem).replace('"', "'")
            objects.append(f'<object id="{oid}" type="model" name="{name}" pid="1" pindex="{colours.index(colour)}">'
                           f"<mesh><vertices>{verts}</vertices><triangles>{tris}</triangles></mesh></object>")
            components.append(f'<component objectid="{oid}"/>')
        oid = len(objects) + 2
        name = str(plate.get("name") or title).replace('"', "'")
        objects.append(f'<object id="{oid}" type="model" name="{name}"><components>{"".join(components)}'
                       "</components></object>")
        items.append(f'<item objectid="{oid}"/>')
    materials = "".join(f'<base name="{c}" displaycolor="{c}FF"/>' for c in colours)
    model = ('<?xml version="1.0" encoding="UTF-8"?>\n<model unit="millimeter" xml:lang="en-US" '
             'xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02"><resources>'
             f'<basematerials id="1">{materials}</basematerials>{"".join(objects)}</resources>'
             f'<build>{"".join(items)}</build></model>')
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", '<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.'
                   'openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/'
                   'vnd.openxmlformats-package.relationships+xml"/><Default Extension="model" ContentType="application/'
                   'vnd.ms-package.3dmanufacturing-3dmodel+xml"/></Types>')
        z.writestr("_rels/.rels", '<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.'
                   'openxmlformats.org/package/2006/relationships"><Relationship Target="/3D/3dmodel.model" Id="rel0" '
                   'Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/></Relationships>')
        z.writestr("3D/3dmodel.model", model)


SPEC_ENTRY = "Metadata/print3d_spec.json"


def embed_spec(project: Path, spec: dict, base: Path) -> None:
    """Keep the project's recipe (parts, filaments, settings) inside the 3MF, so it can be sliced
    again on another printer: the web service prices print orders on its own printer from it."""
    with zipfile.ZipFile(project, "a", zipfile.ZIP_DEFLATED) as z:
        z.writestr(SPEC_ENTRY, json.dumps({"spec": spec, "base": base.resolve().as_posix()}, ensure_ascii=False))


def slicer_ready() -> bool:
    return bool(sl.SLICER and sl.SLICER.exists() and sl.SYSTEM_DIR and sl.DEFAULTS)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("spec", type=Path)
    parser.add_argument("--check", action="store_true", help="slice the project and render it")
    args = parser.parse_args()
    spec = json.loads(args.spec.read_text(encoding="utf-8"))
    base = args.spec.parent
    project = base / spec.get("output", f"{base.name}.3mf")

    plates = spec.get("plates")
    if not slicer_ready():
        # No slicer or printer presets: still a 3MF that opens anywhere, with the model centred.
        for plate in plates or [{"parts": spec["parts"]}]:
            for part in plate["parts"]:
                part.setdefault("colour", spec["filaments"][part["filament"] - 1].get("colour", "#FFFFFF"))
        write_plain_3mf(plates or [{"parts": spec["parts"]}], base, project, sl.BED_CENTER,
                        spec.get("title", base.name))
        embed_spec(project, spec, base)
        print(f"project : {project}")
        print("no slicer in printer.json: geometry only (one object, a part per colour, centred on the bed); the "
              "printer, material and print settings are chosen in the slicer")
        return 0
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
    embed_spec(project, spec, base)
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
