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


def save(name, mode=None, scale=None):
    saved = read_saved()
    old_mode, old_scale = saved.get(name, ("auto", "auto"))
    saved[name] = (mode or old_mode, scale or old_scale)
    text = "# termOS screens: <output> <mode|auto> <scale|auto>  (written by Settings)\n"
    text += "".join(f"{n} {m} {s}\n" for n, (m, s) in sorted(saved.items()))
    core.write_atomic(core.OUTPUTS_CONF, text)
