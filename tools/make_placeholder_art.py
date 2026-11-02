#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Generate original placeholder artwork (no Apple renders) for the extension.

Writes extension/assets/<dir>/{case,left,right}.png at 2x size with transparent backgrounds.
Usage: python3 tools/make_placeholder_art.py
"""

import math
from pathlib import Path

import cairo

ROOT = Path(__file__).resolve().parent.parent / "extension" / "assets"
FILL = (0.97, 0.97, 0.98)
SHADE = (0.80, 0.81, 0.84)
LINE = (0.55, 0.56, 0.60)


def rounded_rect(cr, x, y, w, h, r):
    cr.new_sub_path()
    cr.arc(x + w - r, y + r, r, -math.pi / 2, 0)
    cr.arc(x + w - r, y + h - r, r, 0, math.pi / 2)
    cr.arc(x + r, y + h - r, r, math.pi / 2, math.pi)
    cr.arc(x + r, y + r, r, math.pi, 3 * math.pi / 2)
    cr.close_path()


def shaded_fill(cr, x0, y0, x1, y1):
    g = cairo.LinearGradient(x0, y0, x1, y1)
    g.add_color_stop_rgb(0, *FILL)
    g.add_color_stop_rgb(1, *SHADE)
    cr.set_source(g)


def draw_case(path: Path, size=240, stemmed=True):
    s = cairo.ImageSurface(cairo.FORMAT_ARGB32, size, size)
    cr = cairo.Context(s)
    w, h = size * 0.86, size * 0.66
    x, y = (size - w) / 2, (size - h) / 2 + size * 0.04
    rounded_rect(cr, x, y, w, h, h * 0.42)
    shaded_fill(cr, x, y, x + w * 0.3, y + h)
    cr.fill_preserve()
    cr.set_source_rgb(*LINE)
    cr.set_line_width(3)
    cr.stroke()
    # lid seam
    seam = y + h * 0.36
    cr.move_to(x + 6, seam)
    cr.line_to(x + w - 6, seam)
    cr.set_line_width(2)
    cr.set_source_rgba(*LINE, 0.8)
    cr.stroke()
    # status light
    cr.arc(size / 2, y + h * 0.62, size * 0.018, 0, 2 * math.pi)
    cr.set_source_rgb(0.30, 0.82, 0.40)
    cr.fill()
    if not stemmed:
        # generic: little speaker grille dots instead
        for i in range(-2, 3):
            cr.arc(size / 2 + i * 10, y + h * 0.8, 2, 0, 2 * math.pi)
        cr.set_source_rgba(*LINE, 0.7)
        cr.fill()
    path.parent.mkdir(parents=True, exist_ok=True)
    s.write_to_png(str(path))


def draw_pod(path: Path, size=128, mirror=False, stemmed=True):
    s = cairo.ImageSurface(cairo.FORMAT_ARGB32, size, size)
    cr = cairo.Context(s)
    if mirror:
        cr.translate(size, 0)
        cr.scale(-1, 1)
    # head
    hx, hy, hr = size * 0.46, size * 0.30, size * 0.22
    if stemmed:
        sw = size * 0.13
        sx = hx + hr * 0.25
        rounded_rect(cr, sx, hy, sw, size * 0.62, sw / 2)
        shaded_fill(cr, sx, 0, sx + sw, 0)
        cr.fill_preserve()
        cr.set_source_rgb(*LINE)
        cr.set_line_width(2.5)
        cr.stroke()
    cr.arc(hx, hy, hr, 0, 2 * math.pi)
    shaded_fill(cr, hx - hr, hy - hr, hx + hr, hy + hr)
    cr.fill_preserve()
    cr.set_source_rgb(*LINE)
    cr.set_line_width(2.5)
    cr.stroke()
    # ear tip
    cr.arc(hx - hr * 0.55, hy + hr * 0.05, hr * 0.42, 0, 2 * math.pi)
    cr.set_source_rgb(*SHADE)
    cr.fill_preserve()
    cr.set_source_rgb(*LINE)
    cr.set_line_width(2)
    cr.stroke()
    if not stemmed:
        cr.arc(hx, hy + hr * 1.6, hr * 0.7, 0, 2 * math.pi)
        shaded_fill(cr, hx - hr, hy, hx + hr, hy + 2 * hr)
        cr.fill_preserve()
        cr.set_source_rgb(*LINE)
        cr.stroke()
    path.parent.mkdir(parents=True, exist_ok=True)
    s.write_to_png(str(path))


def main():
    for name, stemmed in (("2420", True), ("generic", False)):
        d = ROOT / name
        draw_case(d / "case.png", stemmed=stemmed)
        draw_pod(d / "left.png", mirror=False, stemmed=stemmed)
        draw_pod(d / "right.png", mirror=True, stemmed=stemmed)
        print("wrote", d)


if __name__ == "__main__":
    main()
