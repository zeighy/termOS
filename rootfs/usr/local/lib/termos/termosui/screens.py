"""Connected screens, saved screen choices and the automatic scale."""
import json
import math

from . import core

SCALES = ["1", "1.25", "1.5", "1.75", "2", "2.5", "3"]


def connected():
    try:
        outs = json.loads(core.run("wlr-randr", "--json").stdout)
        return [o for o in outs if o.get("enabled", True)]
    except (ValueError, TypeError):
        return []


def is_builtin(out):
    return bool(core.PANEL_RE.match(out.get("name", "")))


def mode_name(mode):
    return f"{mode['width']}x{mode['height']}@{mode['refresh']:.3f}Hz"


def current_mode(out):
    return next((mode_name(m) for m in out.get("modes", []) if m.get("current")), None)


def auto_scale(out):
    """A scale that keeps buttons about 7-9 mm on built-in (touch) screens."""
    mode = next((m for m in out.get("modes", []) if m.get("current")), None)
    if not mode:
        return 1.0
    width, height = mode["width"], mode["height"]
    size = out.get("physical_size") or {}
    diagonal_mm = math.hypot(size.get("width", 0), size.get("height", 0))
    # missing or nonsense sizes (projectors report 16x9) count as unknown
    ppi = math.hypot(width, height) / (diagonal_mm / 25.4) if diagonal_mm > 100 else None
    short = min(width, height)
    if is_builtin(out):
        if ppi is None:
            return 1.5 if short >= 1080 else 1.0
        scale = 2.0 if ppi >= 280 else 1.5 if ppi >= 190 else 1.25 if ppi >= 150 else 1.0
    else:
        # monitors are used from further away
        if ppi is None or short < 1400:
            return 1.0
        scale = 2.0 if ppi >= 220 else 1.5 if ppi >= 150 else 1.0
    while scale > 1 and short / scale < 600:
        scale -= 0.25
    return scale


def read_saved():
    saved = {}
    for line in core.slurp(core.OUTPUTS_CONF).splitlines():
        parts = line.split()
        if len(parts) == 3 and not line.startswith("#"):
            saved[parts[0]] = (parts[1], parts[2])
    return saved


# ---- arrangement ------------------------------------------------------------
# layout.conf keeps the main screen and where every other screen sits next to
# it, as a side plus an offset along that side. Positions are worked out again
# from that whenever a screen is plugged in, resized or rotated, so the screens
# always touch and never overlap.
#   main DSI-1
#   HDMI-A-1 right 0
SIDES = ("right", "left", "above", "below")
TOUCH = 100     # screens share at least this much edge, so the pointer can cross


def logical_size(out):
    mode = next((m for m in out.get("modes", []) if m.get("current")), None)
    if not mode:
        return 1, 1
    w, h = mode["width"], mode["height"]
    if str(out.get("transform", "normal")).endswith(("90", "270")):
        w, h = h, w
    scale = float(out.get("scale") or 1) or 1
    return max(1, round(w / scale)), max(1, round(h / scale))


def read_layout():
    main, sides = None, {}
    for line in core.slurp(core.LAYOUT_CONF).splitlines():
        parts = line.split()
        if line.startswith("#") or not parts:
            continue
        if parts[0] == "main" and len(parts) == 2:
            main = parts[1]
        elif len(parts) == 3 and parts[1] in SIDES:
            try:
                sides[parts[0]] = (parts[1], int(parts[2]))
            except ValueError:
                pass
    return main, sides


def save_layout(main, sides):
    old_main, saved = read_layout()
    saved.update(sides)     # keep screens that are unplugged right now
    text = "# termOS screen arrangement: main <output> / <output> <side> <offset>  (written by Settings)\n"
    if main or old_main:
        text += f"main {main or old_main}\n"
    text += "".join(f"{n} {s} {o}\n" for n, (s, o) in sorted(saved.items()) if n != (main or old_main))
    core.write_atomic(core.LAYOUT_CONF, text)


def main_screen(outs, saved_main=None):
    """The saved main screen if it is plugged in, else the built-in one, else the first."""
    names = [o["name"] for o in outs]
    if saved_main in names:
        return saved_main
    return next((o["name"] for o in outs if is_builtin(o)), names[0] if names else None)


def _clamp(offset, size, main_size):
    edge = min(TOUCH, size, main_size)
    return max(edge - size, min(main_size - edge, offset))


def arrange(outs, main, sides):
    """Top-left corner of every screen: main first, the others beside it."""
    size = {o["name"]: logical_size(o) for o in outs}
    if main not in size:
        return {}
    mw, mh = size[main]
    pos = {main: (0, 0)}
    reach = {"right": mw, "left": 0, "above": 0, "below": mh}
    for name in sorted(size):
        if name == main:
            continue
        w, h = size[name]
        side, offset = sides.get(name, ("right", 0))
        if side in ("right", "left"):
            offset = _clamp(offset, h, mh)
            if side == "right":
                pos[name] = (reach["right"], offset)
                reach["right"] += w
            else:
                reach["left"] -= w
                pos[name] = (reach["left"], offset)
        else:
            offset = _clamp(offset, w, mw)
            if side == "below":
                pos[name] = (offset, reach["below"])
                reach["below"] += h
            else:
                reach["above"] -= h
                pos[name] = (offset, reach["above"])
    # keep everything at or right/below 0,0 (some X11 apps get confused otherwise)
    dx = -min(x for x, _y in pos.values())
    dy = -min(y for _x, y in pos.values())
    return {n: (x + dx, y + dy) for n, (x, y) in pos.items()}


def sides_from(rects, main):
    """Side and offset of every screen next to the main one, from rough rectangles
    {name: (x, y, w, h)} such as where the user dropped them on the map. The
    offset snaps so the screens line up at a corner or at their centres."""
    mx, my, mw, mh = rects[main]
    out = {}
    for name, (x, y, w, h) in rects.items():
        if name == main:
            continue
        dx = (x + w / 2 - mx - mw / 2) / ((w + mw) / 2)
        dy = (y + h / 2 - my - mh / 2) / ((h + mh) / 2)
        if abs(dx) >= abs(dy):
            out[name] = ("right" if dx >= 0 else "left", _snap(y - my, h, mh))
        else:
            out[name] = ("below" if dy >= 0 else "above", _snap(x - mx, w, mw))
    return out


def _snap(offset, size, main_size):
    """Line a dropped screen up with the main one: start edges, centres or end edges."""
    return min((0, round((main_size - size) / 2), main_size - size), key=lambda c: abs(c - offset))


def save(name, mode=None, scale=None):
    saved = read_saved()
    old_mode, old_scale = saved.get(name, ("auto", "auto"))
    saved[name] = (mode or old_mode, scale or old_scale)
    text = "# termOS screens: <output> <mode|auto> <scale|auto>  (written by Settings)\n"
    text += "".join(f"{n} {m} {s}\n" for n, (m, s) in sorted(saved.items()))
    core.write_atomic(core.OUTPUTS_CONF, text)
