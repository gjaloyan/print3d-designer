"""Render a multi-colour model from one STL per colour, to check the colour split.

Usage:
    python scripts/render_parts.py models/<name>/parts --png models/<name>/parts.png
        [--views front,side,back,three-quarter] [--reference picture.jpg]
        [--colors teal=#3f9e95,body=#ffffff] [--closeup] [--zoom 1.3]

Each file is coloured by its name (white, teal, orange, black, pink, ...), by
--colors, or by a hex stem (b81d14.stl); unknown names are grey. With
--reference, the picture the model was made from is stacked above the render
(same width), so the two can be compared directly. --closeup lights the model
from a low side angle so grooves, inlay edges, ribs and surface banding show.
"""

import argparse
import re
from pathlib import Path

import quiet_vtk  # noqa: F401  (before pyvista)
import pyvista as pv
from PIL import Image

COLORS = {
    "white": "#f2f2ee", "teal": "#3f9e95", "orange": "#f08a2c", "black": "#202020",
    "pink": "#f2a3a3", "red": "#b81d14", "blue": "#1f5fbf", "green": "#42694c", "yellow": "#dfa636",
    "magenta": "#c2187a", "grey": "#8a8a8a", "brown": "#7a4a2a", "skin": "#f1c7a5",
}
# Camera direction from the model (front faces -Y).
VIEWS = {
    "front": (0, -1, 0.05), "side": (1, 0, 0.05), "back": (0, 1, 0.05), "left": (-1, 0, 0.05),
    "top": (0, -0.01, 1), "bottom": (0, -0.01, -1),
    "three-quarter": (0.6, -1, 0.15), "three-quarter-left": (-0.6, -1, 0.15),
    "front-left": (-1, -1, 0.5), "back-high": (0.6, 1, 0.4),
}


def colour_of(stem: str, extra: dict) -> str:
    if stem in extra:
        return extra[stem]
    if stem.lower() in COLORS:
        return COLORS[stem.lower()]
    if re.fullmatch(r"#?[0-9a-fA-F]{6}", stem):
        return "#" + stem.lstrip("#")
    return "#888888"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("parts", type=Path, help="folder of <colour>.stl files")
    parser.add_argument("--png", type=Path, required=True)
    parser.add_argument("--views", default="front,front-left,side,back-high")
    parser.add_argument("--reference", type=Path)
    parser.add_argument("--colors", default="", help="name=#hex,... for files not named after a colour")
    parser.add_argument("--closeup", action="store_true", help="raking light, bigger frames")
    parser.add_argument("--zoom", type=float, default=1.0)
    args = parser.parse_args()

    extra = dict(kv.split("=", 1) for kv in args.colors.split(",") if "=" in kv)
    names = args.views.split(",")
    meshes = [(f.stem, pv.read(str(f))) for f in sorted(args.parts.glob("*.stl"))]
    size = (1000, 1300) if args.closeup else (500, 800)
    plotter = pv.Plotter(shape=(1, len(names)), off_screen=True, window_size=(size[0] * len(names), size[1]),
                         lighting="none" if args.closeup else "light kit")
    plotter.set_background("#ffffff" if args.reference or args.closeup else "#d8dde3")
    centre = pv.merge([m for _, m in meshes]).center if meshes else (0, 0, 0)
    for col, name in enumerate(names):
        plotter.subplot(0, col)
        if args.closeup:
            plotter.set_background("white")
        for part, mesh in meshes:
            plotter.add_mesh(mesh, color=colour_of(part, extra), specular=0.25 if args.closeup else 0.2,
                             smooth_shading=True, split_sharp_edges=True)
        if args.closeup:
            d = VIEWS[name]
            # Key light from high on one side, a weak fill from the other.
            key = (centre[0] + 60 * (d[0] - d[1] * 0.7), centre[1] + 60 * (d[1] + d[0] * 0.7), centre[2] + 50)
            fill = (centre[0] - 60 * (d[0] - d[1] * 0.7), centre[1] + 60 * d[1], centre[2] + 5)
            plotter.add_light(pv.Light(position=key, focal_point=centre, intensity=1.0, light_type="scene light"))
            plotter.add_light(pv.Light(position=fill, focal_point=centre, intensity=0.3, light_type="scene light"))
        plotter.add_text(name, font_size=10)
        plotter.view_vector(VIEWS[name], viewup=(0, 1, 0) if name in ("top", "bottom") else (0, 0, 1))
        plotter.enable_parallel_projection()
        plotter.reset_camera()
        zoom = args.zoom * (1.3 if args.closeup and args.zoom == 1.0 else 1.0)
        if zoom != 1.0:
            plotter.camera.zoom(zoom)
    plotter.screenshot(str(args.png))
    plotter.close()

    if args.reference:
        render = Image.open(args.png).convert("RGB")
        ref = Image.open(args.reference).convert("RGB")
        ref = ref.resize((render.width, round(ref.height * render.width / ref.width)))
        both = Image.new("RGB", (render.width, ref.height + render.height), "white")
        both.paste(ref, (0, 0))
        both.paste(render, (0, ref.height))
        both.save(args.png)
    print(f"parts preview: {args.png} ({', '.join(n for n, _ in meshes)})")


if __name__ == "__main__":
    main()
