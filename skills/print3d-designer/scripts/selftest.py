"""End-to-end check that the toolchain works on this machine.

Usage:
    python scripts/selftest.py [--out DIR] [--no-slice]

Builds the demo figurine from templates/model_template.py, then runs every
check the workflow relies on: mesh report + preview, overhang spots, colour
render, both ray tests and - when printer.json names a slicer - slicing and a
colour 3MF project with its own check. The gift box template is held to its
picture: the fidelity gate must pass it on the picture and on a recompressed
copy, fail it when the views are named out of order, and then make_3mf.py
must refuse to build its project until the user accepts. Prints PASS/FAIL per
step and leaves all outputs in DIR (default: a fresh folder in the system temp
dir) so the images can be looked at.
"""

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent
SKILL = HERE.parent
sys.path.insert(0, str(HERE))
import config  # noqa: E402


def run(label: str, args: list, results: list, code: int = 0, check=None) -> bool:
    """Run a script; the step passes on the expected exit code and, given `check`, output it accepts."""
    start = time.time()
    proc = subprocess.run([sys.executable, *map(str, args)], capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    out = proc.stdout + proc.stderr
    ok = proc.returncode == code and (check is None or check(out))
    tail = out.strip().splitlines()[-6:]
    results.append((label, ok, time.time() - start))
    print(f"[{'PASS' if ok else 'FAIL'}] {label} ({time.time() - start:.0f} s)")
    for line in tail:
        print("        " + line)
    return ok


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path)
    parser.add_argument("--no-slice", action="store_true")
    args = parser.parse_args()
    out = args.out or Path(tempfile.mkdtemp(prefix="print3d_selftest_"))
    out.mkdir(parents=True, exist_ok=True)
    model = out / "buddy.py"
    shutil.copyfile(SKILL / "templates" / "model_template.py", model)
    shutil.copyfile(HERE / "shapes.py", out / "shapes.py")  # templates import it from their own folder
    box_dir = out / "box"
    box_dir.mkdir(exist_ok=True)
    shutil.copyfile(SKILL / "templates" / "box_template.py", box_dir / "gift.py")
    shutil.copyfile(HERE / "shapes.py", box_dir / "shapes.py")
    results = []

    cfg = config.load()
    print(f"config : {cfg.get('_path', 'none (generic defaults)')}")
    print(f"python : {sys.executable}")
    print(f"output : {out}\n")

    run("shapes.py self-check (every recipe builds)", [HERE / "shapes.py"], results)
    if not run("build the round template", [model], results):
        return 1
    if run("build the box template (the real gift box)", [box_dir / "gift.py"], results):
        picture = SKILL / "templates" / "box_reference.jpg"
        compare = [HERE / "compare_views.py", box_dir / "parts"]
        gated = ["--anchor", "red", "--info", "three-quarter"]
        run("compare_views: box against its picture (must PASS)",
            [*compare, picture, "--views", "front,side,back,three-quarter", *gated], results)
        # A picture sent through a messenger comes back recompressed; the gate must judge it the same.
        Image.open(picture).save(box_dir / "picture_q60.jpg", quality=60)
        run("compare_views: the same picture recompressed, as a messenger sends it (must PASS)",
            [*compare, box_dir / "picture_q60.jpg", "--views", "front,side,back,three-quarter", *gated], results)
        run("measure_reference: 4 views, the ribbons do not split them",
            [HERE / "measure_reference.py", picture, "--colors", "red,white", "--height", "80", "--step", "40"],
            results, check=lambda out: out.count("== view") == 4)
        run("compare_views: the views named out of order (must FAIL)",
            [*compare, picture, "--views", "side,front,back,three-quarter", *gated], results, code=1)
        box_spec = {"title": "Gift box", "output": "gift.3mf", "nozzle": next(iter(cfg.get("nozzles") or {}), "0.4"),
                    "filaments": [{"colour": "#C8102E"}, {"colour": "#FFFFFF"}],
                    "parts": [{"stl": "parts/red.stl", "name": "Box", "filament": 1},
                              {"stl": "parts/white.stl", "name": "Bow", "filament": 2}]}
        (box_dir / "print.json").write_text(json.dumps(box_spec, indent=1), encoding="utf-8")
        run("make_3mf: no project from parts that failed compare_views",
            [HERE / "make_3mf.py", box_dir / "print.json"], results, code=3, check=lambda out: "NOT READY" in out)
        run("make_3mf: the project once the user accepts the difference",
            [HERE / "make_3mf.py", box_dir / "print.json", "--accept-views", "selftest: accepted"], results)
    run("check_model (mesh + preview.png)", [HERE / "check_model.py", out / "buddy.stl", "--png", out / "preview.png"],
        results)
    run("overhang_spots", [HERE / "overhang_spots.py", out / "buddy.stl"], results)
    run("render_parts --closeup", [HERE / "render_parts.py", out / "parts", "--png", out / "parts.png",
                                   "--views", "front,side,three-quarter", "--closeup"], results)
    run("ray_colors support", [HERE / "ray_colors.py", "support", out / "parts"], results)
    run("ray_colors skin (white over teal)", [HERE / "ray_colors.py", "skin", out / "parts", "--light", "white",
                                              "--dark", "teal", "--min", "1.0"], results)

    slicer = cfg["slicer"].get("exe")
    if args.no_slice or not slicer or not Path(slicer).exists():
        print("[SKIP] slicing: no slicer in printer.json (or --no-slice)")
    else:
        nozzle = next(iter(cfg["nozzles"]), None)
        if nozzle is None:
            print("[SKIP] slicing: no nozzles in printer.json")
        else:
            run(f"slice.py (nozzle {nozzle})", [HERE / "slice.py", out / "buddy.stl", "--nozzle", nozzle,
                                                "--out", out / "slice"], results)
            spec = json.loads((SKILL / "templates" / "print.json").read_text(encoding="utf-8"))
            spec["nozzle"] = nozzle
            preset = cfg["nozzles"][nozzle].get("filament")
            if preset:  # use a filament preset that surely exists here
                for fil in spec["filaments"]:
                    fil["preset"] = preset
            (out / "print.json").write_text(json.dumps(spec, indent=1), encoding="utf-8")
            run("make_3mf.py --check (4 colours)", [HERE / "make_3mf.py", out / "print.json", "--check"], results)

    failed = [r for r in results if not r[1]]
    print(f"\n{len(results) - len(failed)}/{len(results)} steps passed; look at the images in {out}:")
    for png in sorted(out.rglob("*.png")):
        print(f"  {png}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
