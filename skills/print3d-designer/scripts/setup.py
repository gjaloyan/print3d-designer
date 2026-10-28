"""Set up the Python environment and printer.json for the print3d scripts.

Usage:
    python scripts/setup.py [--home DIR] [--python EXE] [--no-test]

Creates DIR/venv (default ~/.print3d/venv) with scripts/requirements.txt,
writes a starter DIR/printer.json when there is none (with the slicer's
paths when a Bambu Studio-family slicer is found), then runs selftest.py
with the new environment. Safe to run again: the venv is updated and an
existing printer.json is kept.

build123d needs Python 3.11-3.14. When this interpreter is outside that
range, the script looks for one inside it (the py launcher on Windows,
python3.X on PATH elsewhere); --python picks one explicitly.
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKILL = HERE.parent
SUPPORTED = ((3, 11), (3, 14))  # build123d 0.13 and its cadquery-ocp wheels
WINDOWS = os.name == "nt"
DEFAULT_HOME = Path.home() / ".print3d"


def version_of(cmd: list[str]) -> tuple[int, int] | None:
    try:
        out = subprocess.run([*cmd, "-c", "import sys; print(*sys.version_info[:2])"],
                             capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if out.returncode != 0:
        return None
    major, minor = map(int, out.stdout.split())
    return major, minor


def pick_python(requested: str | None) -> list[str]:
    """The requested interpreter, this one, or another one on the machine inside SUPPORTED."""
    if requested:
        candidates = [[requested]]
    else:
        candidates = [[sys.executable]]
        for minor in (13, 12, 14, 11):
            candidates.append(["py", f"-3.{minor}"] if WINDOWS else [f"python3.{minor}"])
    tried = []
    for cmd in candidates:
        if shutil.which(cmd[0]) is None and not Path(cmd[0]).is_file():
            continue
        found = version_of(cmd)
        tried.append(f"{' '.join(cmd)} -> {'%d.%d' % found if found else 'not runnable'}")
        if found and SUPPORTED[0] <= found <= SUPPORTED[1]:
            return cmd
    raise SystemExit("no Python 3.11-3.14 found (build123d needs one). Tried:\n  " + "\n  ".join(tried)
                     + "\nInstall Python 3.13 from python.org, or pass --python PATH.")


def venv_python(venv: Path) -> Path:
    return venv / ("Scripts/python.exe" if WINDOWS else "bin/python")


def make_venv(home: Path, base: list[str]) -> Path:
    venv = home / "venv"
    py = venv_python(venv)
    if venv.exists() and version_of([str(py)]) is None:
        if not (venv / "pyvenv.cfg").is_file():
            raise SystemExit(f"{venv} exists but is not a venv; move it away or pass --home")
        print(f"rebuilding the broken venv {venv}")
        shutil.rmtree(venv)
    if not venv.exists():
        print(f"creating {venv} with {' '.join(base)}")
        subprocess.run([*base, "-m", "venv", str(venv)], check=True)
    pip = [str(py), "-m", "pip", "--disable-pip-version-check"]
    subprocess.run([*pip, "install", "-q", "--upgrade", "pip"], check=True)
    print("installing scripts/requirements.txt (5-10 minutes the first time) ...")
    start = time.time()
    if subprocess.run([*pip, "install", "-q", "-r", str(HERE / "requirements.txt")]).returncode != 0:
        raise SystemExit("pip failed (see above). Check the network, or try another Python with --python.")
    print(f"packages ready ({time.time() - start:.0f} s)")
    return py


def known_slicers() -> list[tuple[str, Path | None, Path, str | None]]:
    """(name, executable, data folder, own vendor folder) where each slicer installs by default."""
    home = Path.home()
    if WINDOWS:
        programs = Path(os.environ.get("ProgramFiles", "C:/Program Files"))
        data = Path(os.environ.get("APPDATA", home / "AppData/Roaming"))
        return [("Anycubic Slicer Next", programs / "AnycubicSlicerNext/AnycubicSlicerNext.exe",
                 data / "AnycubicSlicerNext", "Anycubic"),
                ("OrcaSlicer", programs / "OrcaSlicer/orca-slicer.exe", data / "OrcaSlicer", None),
                ("Bambu Studio", programs / "Bambu Studio/bambu-studio.exe", data / "BambuStudio", "BBL")]
    if sys.platform == "darwin":
        apps, data = Path("/Applications"), home / "Library/Application Support"
        return [("Anycubic Slicer Next", apps / "AnycubicSlicerNext.app/Contents/MacOS/AnycubicSlicerNext",
                 data / "AnycubicSlicerNext", "Anycubic"),
                ("OrcaSlicer", apps / "OrcaSlicer.app/Contents/MacOS/OrcaSlicer", data / "OrcaSlicer", None),
                ("Bambu Studio", apps / "BambuStudio.app/Contents/MacOS/BambuStudio", data / "BambuStudio", "BBL")]
    which = lambda *names: next((Path(p) for p in map(shutil.which, names) if p), None)  # noqa: E731
    data = home / ".config"
    return [("OrcaSlicer", which("orca-slicer", "OrcaSlicer"), data / "OrcaSlicer", None),
            ("Bambu Studio", which("bambu-studio", "BambuStudio"), data / "BambuStudio", "BBL")]


def starter_config() -> dict:
    cfg = {
        "_comment": "Written by scripts/setup.py. Fill in your printer; templates/printer.json is a complete "
                    "example. List preset names with: python scripts/slice.py --presets machine",
        "printer": {"name": "my printer", "bed": [250, 250, 250], "moonraker": None, "colour_slots": 1},
        "slicer": {"exe": None, "user_presets": [], "system_presets": None},
        "nozzles": {},
        "filament": {"diameter": 1.75, "density": 1.27},
        "flush_mm3_per_change": 280,
    }
    for name, exe, data, own in known_slicers():
        if exe is None or not exe.is_file():
            continue
        kinds = ("machine", "process", "filament")
        users = sorted((d for d in (data / "user").glob("*") if any((d / k).is_dir() for k in kinds)),
                       key=lambda d: d.name == "default")  # account folders first, then "default"
        vendors = sorted(d for d in (data / "system").glob("*") if (d / "machine").is_dir())
        chosen = next((d for d in vendors if d.name == own), vendors[0] if len(vendors) == 1 else None)
        print(f"found {name}: {exe}")
        cfg["slicer"] = {"exe": exe.as_posix(), "user_presets": [d.as_posix() for d in users],
                         "system_presets": chosen.as_posix() if chosen else None}
        if chosen is None and vendors:
            print("  several printer vendors in its system presets; set slicer.system_presets to yours:")
            for d in vendors:
                print(f"    {d.as_posix()}")
        break
    else:
        print("no Bambu Studio-family slicer found in the default places; slicing stays off until "
              "slicer.exe and the preset folders are set")
    return cfg


def write_config(home: Path) -> Path:
    path = home / "printer.json"
    if path.is_file():
        print(f"keeping {path}")
        return path
    path.write_text(json.dumps(starter_config(), indent=2) + "\n", encoding="utf-8")
    print(f"wrote {path}")
    return path


def main() -> int:
    sys.stdout.reconfigure(line_buffering=True)  # keep our lines in order with the child processes
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--home", type=Path, default=DEFAULT_HOME, help="where the venv and printer.json go")
    parser.add_argument("--python", help="the interpreter to build the venv from")
    parser.add_argument("--no-test", action="store_true", help="skip selftest.py")
    args = parser.parse_args()
    home = args.home.expanduser().resolve()
    home.mkdir(parents=True, exist_ok=True)

    py = make_venv(home, pick_python(args.python))
    config = write_config(home)
    status = 0
    if not args.no_test:
        print("running selftest.py with the new environment (2-3 min) ...")
        env = dict(os.environ, PRINT3D_CONFIG=str(config))
        status = subprocess.run([str(py), str(HERE / "selftest.py"), "--out", str(home / "selftest")], env=env).returncode

    print("\nRun every print3d script with:")
    print(f"  {py}")
    print(f"printer config: {config}")
    if home != DEFAULT_HOME.resolve():
        print(f"(not the default place: set PRINT3D_CONFIG={config})")
    cfg = json.loads(config.read_text(encoding="utf-8"))
    if not cfg.get("nozzles"):
        print("Next: fill in printer.json - bed size, slicer, and per nozzle the machine/process/filament "
              "preset names (python scripts/slice.py --presets machine). templates/printer.json is an example.")
    return status


if __name__ == "__main__":
    sys.exit(main())
