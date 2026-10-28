"""Printer and slicer configuration shared by the print3d scripts.

The config is a JSON file (see templates/printer.json), looked up in order:
  $PRINT3D_CONFIG, ./printer.json, ~/.print3d/printer.json, <skill>/config/printer.json
Strings may use %APPDATA%, $HOME, ~ - they are expanded.
"""

import json
import os
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parents[1]
DEFAULTS = {
    "printer": {"name": "generic", "bed": [250, 250, 250], "moonraker": None},
    "slicer": {"exe": None, "user_presets": [], "system_presets": None},
    "nozzles": {},
    "filament": {"diameter": 1.75, "density": 1.27},
    "flush_mm3_per_change": 280,
}


def _expand(value):
    if isinstance(value, str):
        return os.path.expandvars(os.path.expanduser(value))
    if isinstance(value, list):
        return [_expand(v) for v in value]
    if isinstance(value, dict):
        return {k: _expand(v) for k, v in value.items()}
    return value


def find() -> Path | None:
    for c in (os.environ.get("PRINT3D_CONFIG"), "printer.json", "~/.print3d/printer.json",
              SKILL_DIR / "config" / "printer.json"):
        if c and Path(_expand(str(c))).is_file():
            return Path(_expand(str(c)))
    return None


def load(required: bool = False) -> dict:
    """The merged config; without a file, the generic defaults (or exit if required)."""
    path = find()
    if path is None:
        if required:
            raise SystemExit("printer.json not found: copy templates/printer.json to ~/.print3d/printer.json "
                             "(or set PRINT3D_CONFIG) and fill in your slicer and printer")
        return dict(DEFAULTS)
    cfg = _expand(json.loads(path.read_text(encoding="utf-8")))
    merged = {k: (dict(v, **cfg.get(k, {})) if isinstance(v, dict) else cfg.get(k, v)) for k, v in DEFAULTS.items()}
    merged["_path"] = str(path)
    return merged


def bed(cfg: dict) -> tuple[float, float, float]:
    x, y, z = cfg["printer"]["bed"]
    return float(x), float(y), float(z)


def bed_centre(cfg: dict) -> tuple[float, float]:
    x, y, _ = bed(cfg)
    return x / 2, y / 2


def nozzle(cfg: dict, size: str) -> dict:
    if size not in cfg["nozzles"]:
        raise SystemExit(f"nozzle {size} not in printer.json (have: {', '.join(cfg['nozzles']) or 'none'})")
    return cfg["nozzles"][size]


def flow_limits(cfg: dict) -> dict[float, float]:
    """mm^3/s a nozzle really melts, when set in the config (else nothing)."""
    out = {}
    for size, n in cfg["nozzles"].items():
        if n.get("flow_limit"):
            out[float(size)] = float(n["flow_limit"])
    return out
