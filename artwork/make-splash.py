#!/usr/bin/env python3
"""Generate the Plymouth boot-splash images (logo.png, spinner.png) with no dependencies.
Run: python3 artwork/make-splash.py   (outputs into rootfs/usr/share/plymouth/themes/termos)"""
import math
import os
import struct
import zlib

OUT = os.path.join(os.path.dirname(__file__), "..", "rootfs", "usr", "share", "plymouth", "themes", "termos")
SS = 3  # supersampling per axis


def png(path, w, h, px):
    raw = b"".join(b"\0" + bytes(c for p in px[y * w:(y + 1) * w] for c in p) for y in range(h))

    def chunk(t, d):
        c = struct.pack(">I", len(d)) + t + d
        return c + struct.pack(">I", zlib.crc32(t + d))
    with open(path, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0))
                + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


def render(w, h, shade):
    """shade(x, y) -> (r, g, b, a) with a in 0..1 (non-premultiplied)."""
    px = []
    for y in range(h):
        for x in range(w):
            ar = ag = ab = aa = 0.0
            for sy in range(SS):
                for sx in range(SS):
                    r, g, b, a = shade(x + (sx + .5) / SS, y + (sy + .5) / SS)
                    ar += r * a; ag += g * a; ab += b * a; aa += a
            n = SS * SS
            if aa:
                px.append((round(ar / aa), round(ag / aa), round(ab / aa), round(255 * aa / n)))
            else:
                px.append((0, 0, 0, 0))
    return px


def seg_dist(px, py, ax, ay, bx, by):
    dx, dy = bx - ax, by - ay
    t = max(0, min(1, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
    return math.hypot(px - ax - t * dx, py - ay - t * dy)


def rrect_dist(px, py, cx, cy, hw, hh, r):
    qx, qy = abs(px - cx) - hw + r, abs(py - cy) - hh + r
    return math.hypot(max(qx, 0), max(qy, 0)) + min(max(qx, qy), 0) - r


BLUE, TEXT, PANEL = (137, 180, 250), (205, 214, 244), (24, 24, 37)
RED, YEL, GRN = (243, 139, 168), (249, 226, 175), (166, 227, 161)


def logo(x, y):
    # 280x200 canvas, same prompt mark as the wallpaper (scaled 0.62)
    d = rrect_dist(x, y, 140, 100, 130, 92, 22)
    if d < -3:
        base = (*PANEL, 1.0)
    elif d < 0:
        base = (*BLUE, 1.0)
    else:
        return (0, 0, 0, 0)
    for cx, col in ((36, RED), (58, YEL), (80, GRN)):
        if math.hypot(x - cx, y - 34) < 7:
            return (*col, 1.0)
    if seg_dist(x, y, 62, 84, 108, 118) < 9 or seg_dist(x, y, 62, 152, 108, 118) < 9:
        return (*BLUE, 1.0)
    if rrect_dist(x, y, 168, 150, 38, 8, 6) < 0:
        return (*TEXT, 1.0)
    return base


def spinner(x, y):
    # 96x96 ring, 270 degree arc fading toward the tail
    cx = cy = 48
    r = math.hypot(x - cx, y - cy)
    if abs(r - 38) > 5:
        return (0, 0, 0, 0)
    ang = (math.degrees(math.atan2(y - cy, x - cx)) + 360) % 360
    span = 270
    if ang > span:
        # round cap at the leading end
        ex, ey = cx + 38 * math.cos(math.radians(span)), cy + 38 * math.sin(math.radians(span))
        if math.hypot(x - ex, y - ey) > 5:
            return (0, 0, 0, 0)
        ang = span
    return (*BLUE, 0.12 + 0.88 * ang / span)


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    png(os.path.join(OUT, "logo.png"), 280, 200, render(280, 200, logo))
    png(os.path.join(OUT, "spinner.png"), 96, 96, render(96, 96, spinner))
    print("wrote", os.path.normpath(OUT))
