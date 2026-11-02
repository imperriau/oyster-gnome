#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Pack rendered turntable frames into one sprite sheet for the extension.

    python3 tools/pack_spin.py render/2420 extension/assets/2420 [--fps 24] [--columns 12]

Writes <dest>/hero-sheet.png (frames left to right, top to bottom) and <dest>/hero.json.
One texture keeps the animation cheap in GNOME Shell and avoids first-loop flicker.
"""

import argparse
import json
from pathlib import Path

import cairo


def main():
    p = argparse.ArgumentParser()
    p.add_argument("src", type=Path)
    p.add_argument("dest", type=Path)
    p.add_argument("--fps", type=int, default=24)
    p.add_argument("--columns", type=int, default=12)
    a = p.parse_args()

    frames = sorted(a.src.glob("frame_*.png"))
    if not frames:
        raise SystemExit(f"no frame_*.png in {a.src}")
    first = cairo.ImageSurface.create_from_png(str(frames[0]))
    fw, fh = first.get_width(), first.get_height()
    cols = min(a.columns, len(frames))
    rows = -(-len(frames) // cols)
    sheet = cairo.ImageSurface(cairo.FORMAT_ARGB32, cols * fw, rows * fh)
    cr = cairo.Context(sheet)
    for i, f in enumerate(frames):
        cr.set_source_surface(
            cairo.ImageSurface.create_from_png(str(f)), (i % cols) * fw, (i // cols) * fh
        )
        cr.paint()
    a.dest.mkdir(parents=True, exist_ok=True)
    sheet.write_to_png(str(a.dest / "hero-sheet.png"))
    meta = {
        "sheet": "hero-sheet.png",
        "frames": len(frames),
        "columns": cols,
        "rows": rows,
        "frameWidth": fw,
        "frameHeight": fh,
        "fps": a.fps,
    }
    (a.dest / "hero.json").write_text(json.dumps(meta, indent=2) + "\n")
    print(
        f"{len(frames)} frames {fw}x{fh} -> {cols}x{rows} sheet {cols * fw}x{rows * fh} in {a.dest}"
    )


if __name__ == "__main__":
    main()
