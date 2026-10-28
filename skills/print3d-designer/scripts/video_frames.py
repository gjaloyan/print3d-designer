"""Pull frames out of a video (a screen recording of the slicer, a print timelapse).

Usage:
    python scripts/video_frames.py recording.mp4 --out frames/ [--count 12 | --every 2.5]
        [--sheet sheet.jpg] [--width 1600]

Frames are spread evenly over the video (or taken every N seconds) and saved
as frame_NN_<t>s.jpg; --sheet also tiles them into one contact sheet, which is
the quickest way to look at a whole recording at once. Uses ffmpeg when it is
on PATH (or in the usual winget folder); on Windows without ffmpeg it falls
back to the built-in Windows.Media.Editing API (frames_windows.ps1).
"""

import argparse
import math
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw

HERE = Path(__file__).parent


def find_ffmpeg() -> str | None:
    found = shutil.which("ffmpeg")
    if found:
        return found
    links = Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "WinGet" / "Links" / "ffmpeg.exe"
    return str(links) if links.exists() else None


def duration(ffmpeg: str, video: Path) -> float:
    run = subprocess.run([ffmpeg, "-hide_banner", "-i", str(video)], capture_output=True, text=True,
                         encoding="utf-8", errors="replace")
    m = re.search(r"Duration: (\d+):(\d+):([\d.]+)", run.stderr)
    if not m:
        sys.exit(f"cannot read the duration of {video}")
    h, mnt, s = m.groups()
    return int(h) * 3600 + int(mnt) * 60 + float(s)


def with_ffmpeg(ffmpeg: str, video: Path, out: Path, times: list[float], width: int) -> list[Path]:
    frames = []
    for i, t in enumerate(times):
        path = out / f"frame_{i:02d}_{t:.0f}s.jpg"
        subprocess.run([ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-ss", f"{t:.3f}", "-i", str(video),
                        "-frames:v", "1", "-vf", f"scale='min({width},iw)':-2", "-q:v", "3", str(path)], check=True)
        frames.append(path)
    return frames


def with_windows(video: Path, out: Path, count: int) -> list[Path]:
    script = HERE / "frames_windows.ps1"
    run = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script),
                          "-Video", str(video.resolve()), "-OutDir", str(out.resolve()), "-Count", str(count)],
                         capture_output=True, text=True, encoding="utf-8", errors="replace")
    if run.returncode != 0:
        sys.exit("Windows frame extraction failed:\n" + run.stderr[-2000:])
    print(run.stdout.splitlines()[0] if run.stdout else "")
    return sorted(out.glob("frame_*.jpg"))


def contact_sheet(frames: list[Path], path: Path, cols: int = 4, tile_w: int = 640) -> None:
    images = [Image.open(f).convert("RGB") for f in frames]
    tile_h = max(round(im.height * tile_w / im.width) for im in images)
    rows = math.ceil(len(images) / cols)
    sheet = Image.new("RGB", (cols * tile_w, rows * (tile_h + 22)), "white")
    draw = ImageDraw.Draw(sheet)
    for i, (im, f) in enumerate(zip(images, frames)):
        x, y = (i % cols) * tile_w, (i // cols) * (tile_h + 22)
        sheet.paste(im.resize((tile_w, round(im.height * tile_w / im.width))), (x, y + 22))
        draw.text((x + 6, y + 4), f.stem, fill="black")
    sheet.save(path, quality=88)
    print(f"sheet : {path}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("video", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--count", type=int, default=12)
    parser.add_argument("--every", type=float, help="seconds between frames (instead of --count)")
    parser.add_argument("--width", type=int, default=1600)
    parser.add_argument("--sheet", type=Path, help="also write a contact sheet of all frames")
    args = parser.parse_args()
    if not args.video.exists():
        sys.exit(f"no such video: {args.video}")
    args.out.mkdir(parents=True, exist_ok=True)

    ffmpeg = find_ffmpeg()
    if ffmpeg:
        total = duration(ffmpeg, args.video)
        if args.every:
            times = [t for t in (args.every * (i + 0.5) for i in range(int(total / args.every) + 1)) if t < total]
        else:
            times = [total * (i + 0.5) / args.count for i in range(args.count)]
        print(f"duration {total:.1f} s, {len(times)} frames via ffmpeg")
        frames = with_ffmpeg(ffmpeg, args.video, args.out, times, args.width)
    elif sys.platform == "win32":
        count = args.count
        print("ffmpeg not found: using Windows.Media.Editing (install ffmpeg: winget install Gyan.FFmpeg)")
        frames = with_windows(args.video, args.out, count)
    else:
        sys.exit("ffmpeg not found: install it (apt install ffmpeg / brew install ffmpeg)")
    for f in frames:
        print(f)
    if args.sheet and frames:
        contact_sheet(frames, args.sheet)
    return 0


if __name__ == "__main__":
    sys.exit(main())
