#!/usr/bin/env python3
"""Generate the built-in wallpapers from SVG (needs rsvg-convert, from librsvg).

  python3 artwork/make-wallpapers.py [OUTPUT_DIR]

default.png has no logo, so it stays out of the way of the home screen;
logo.png is artwork/wallpaper.svg.
"""
import math
import os
import runpy
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
# loaded by path: importing the package would need GTK on the build machine
C = runpy.run_path(os.path.join(HERE, "..", "rootfs", "usr", "local", "lib", "termos",
                                "termosui", "palette.py"))["COLORS"]

W, H = 2560, 1600


def svg(defs, body):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
            f'viewBox="0 0 {W} {H}"><defs>{defs}</defs>{body}</svg>')


def linear(name, top, bottom):
    return (f'<linearGradient id="{name}" x1="0" y1="0" x2="1" y2="1">'
            f'<stop offset="0" stop-color="{top}"/><stop offset="1" stop-color="{bottom}"/></linearGradient>')


def glow(name, colour, strength):
    return (f'<radialGradient id="{name}"><stop offset="0" stop-color="{colour}" stop-opacity="{strength}"/>'
            f'<stop offset="1" stop-color="{colour}" stop-opacity="0"/></radialGradient>')


def rect(fill):
    return f'<rect width="{W}" height="{H}" fill="url(#{fill})"/>'


def default():
    defs = linear("bg", C["crust"], "#252840") + glow("g", C["accent"], 0.13)
    rings = "".join(f'<circle cx="2300" cy="1500" r="{r}" fill="none" stroke="{C["accent"]}" '
                    f'stroke-opacity="0.07" stroke-width="3"/>' for r in range(320, 1500, 190))
    return svg(defs, rect("bg") + '<ellipse cx="2100" cy="1350" rx="1300" ry="1000" fill="url(#g)"/>' + rings)


def aurora():
    defs = (linear("bg", C["crust"], C["base"]) + glow("a", C["teal"], 0.22)
            + glow("b", C["accent"], 0.22) + glow("c", C["mauve"], 0.18))
    return svg(defs, rect("bg")
               + '<ellipse cx="520" cy="1450" rx="1250" ry="800" fill="url(#a)"/>'
               + '<ellipse cx="1500" cy="1150" rx="1100" ry="700" fill="url(#b)"/>'
               + '<ellipse cx="2350" cy="700" rx="900" ry="800" fill="url(#c)"/>')


def contours():
    lines = []
    for n in range(17):
        pts = []
        for i in range(65):
            x = W * i / 64
            y = (620 + n * 70 + 90 * math.sin(x / 420 + n * 0.22)
                 + 45 * math.sin(x / 190 - n * 0.35))
            pts.append(f"{x:.0f},{y:.0f}")
        lines.append(f'<polyline points="{" ".join(pts)}" fill="none" stroke="{C["accent"]}" '
                     f'stroke-opacity="{0.04 + n * 0.007:.3f}" stroke-width="3"/>')
    return svg(linear("bg", C["crust"], C["base"]), rect("bg") + "".join(lines))


def dusk():
    defs = (f'<linearGradient id="sky" x1="0" y1="0" x2="0" y2="1">'
            f'<stop offset="0" stop-color="{C["crust"]}"/><stop offset="0.75" stop-color="#3a2d4d"/>'
            f'<stop offset="1" stop-color="#5a3a52"/></linearGradient>') + glow("sun", C["orange"], 0.25)
    return svg(defs, rect("sky")
               + '<circle cx="1800" cy="1230" r="520" fill="url(#sun)"/>'
               + '<path d="M0 1260 Q500 1080 980 1250 T1900 1230 T2560 1180 V1600 H0 Z" fill="#1c1827"/>'
               + '<path d="M0 1430 Q640 1290 1300 1420 T2560 1380 V1600 H0 Z" fill="#13111c"/>')


def plain():
    return svg(linear("bg", C["base"], C["mantle"]), rect("bg"))


def main():
    out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        HERE, "..", "rootfs", "usr", "share", "backgrounds", "termos")
    with open(os.path.join(HERE, "wallpaper.svg"), encoding="utf-8") as f:
        sources = {"logo": f.read()}
    for fn in (default, aurora, contours, dusk, plain):
        sources[fn.__name__] = fn()
    for name, source in sources.items():
        path = os.path.join(out, f"{name}.png")
        subprocess.run(["rsvg-convert", "-w", str(W), "-h", str(H), "-o", path],
                       input=source.encode(), check=True)
        print("wrote", os.path.normpath(path))


if __name__ == "__main__":
    main()
