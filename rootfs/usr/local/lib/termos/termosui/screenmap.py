"""A small map of the screens that can be rearranged by dragging (finger or mouse)."""
import math

from gi.repository import Gdk, Gtk, Pango, PangoCairo

from .palette import COLORS, UI_FONT


def _rgb(name):
    h = COLORS[name].lstrip("#")
    return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))


class ScreenMap(Gtk.DrawingArea):
    """screens: [(name, label, x, y, w, h)] in desktop pixels.
    on_drop(rects) gets {name: (x, y, w, h)} after a screen was dragged somewhere."""

    PAD = 14

    def __init__(self, screens, main, on_drop, height=230):
        super().__init__()
        self.rects = {n: [x, y, w, h] for n, _l, x, y, w, h in screens}
        self.labels = {n: lbl for n, lbl, *_r in screens}
        self.main = main
        self.on_drop = on_drop
        self.drag = None            # (name, start x, start y) in desktop pixels
        self.frame = None           # (factor, ox, oy, minx, miny) of the last draw
        self.set_size_request(-1, height)
        self.add_events(Gdk.EventMask.BUTTON_PRESS_MASK | Gdk.EventMask.BUTTON_RELEASE_MASK
                        | Gdk.EventMask.BUTTON_MOTION_MASK | Gdk.EventMask.TOUCH_MASK)
        self.connect("draw", self.on_draw)
        # a gesture of our own, which claims the touch so the page doesn't scroll instead
        self.gesture = Gtk.GestureDrag.new(self)
        self.gesture.set_touch_only(False)
        self.gesture.connect("drag-begin", self.begin)
        self.gesture.connect("drag-update", self.update)
        self.gesture.connect("drag-end", self.end)
        self.get_accessible().set_name("Screen arrangement")

    # ---- geometry -----------------------------------------------------------
    def bounds(self):
        xs = [x for x, _y, _w, _h in self.rects.values()] + [x + w for x, _y, w, _h in self.rects.values()]
        ys = [y for _x, y, _w, _h in self.rects.values()] + [y + h for _x, y, _w, h in self.rects.values()]
        return min(xs), min(ys), max(xs), max(ys)

    def fit(self):
        alloc = self.get_allocation()
        minx, miny, maxx, maxy = self.bounds()
        # leave room so a screen can be dragged past the others
        spanx, spany = max(1, maxx - minx), max(1, maxy - miny)
        factor = min((alloc.width - 2 * self.PAD) / (spanx * 1.5),
                     (alloc.height - 2 * self.PAD) / (spany * 1.3))
        factor = max(factor, 0.01)
        ox = (alloc.width - spanx * factor) / 2
        oy = (alloc.height - spany * factor) / 2
        self.frame = (factor, ox, oy, minx, miny)

    def to_view(self, x, y):
        f, ox, oy, minx, miny = self.frame
        return ox + (x - minx) * f, oy + (y - miny) * f

    def hit(self, vx, vy):
        f = self.frame[0]
        for name, (x, y, w, h) in self.rects.items():
            sx, sy = self.to_view(x, y)
            if sx <= vx <= sx + w * f and sy <= vy <= sy + h * f:
                return name
        return None

    # ---- drawing ------------------------------------------------------------
    def on_draw(self, _w, cr):
        if not self.rects:
            return
        if self.drag is None:
            self.fit()          # keep the scale steady while something is being dragged
        f = self.frame[0]
        dragged = self.drag[0] if self.drag else None
        for name, (x, y, w, h) in sorted(self.rects.items(), key=lambda kv: kv[0] == dragged):  # dragged on top
            sx, sy = self.to_view(x, y)
            sw, sh = w * f, h * f
            self.rounded(cr, sx + 2, sy + 2, sw - 4, sh - 4, 8)
            dragging = name == dragged
            cr.set_source_rgba(*_rgb("hover" if dragging else "raised"), 0.92 if dragging else 1)
            cr.fill_preserve()
            if name == self.main:
                cr.set_source_rgb(*_rgb("accent"))
                cr.set_line_width(3)
            else:
                cr.set_source_rgb(*_rgb("muted"))
                cr.set_line_width(1)
            cr.stroke()
            text = self.labels.get(name, name)
            if name == self.main:
                text += "\nMain"
            self.text(cr, text, sx, sy, sw, sh, "accent" if name == self.main else "text")

    @staticmethod
    def rounded(cr, x, y, w, h, r):
        r = min(r, w / 2, h / 2)
        cr.new_sub_path()
        cr.arc(x + w - r, y + r, r, -math.pi / 2, 0)
        cr.arc(x + w - r, y + h - r, r, 0, math.pi / 2)
        cr.arc(x + r, y + h - r, r, math.pi / 2, math.pi)
        cr.arc(x + r, y + r, r, math.pi, 3 * math.pi / 2)
        cr.close_path()

    def text(self, cr, text, x, y, w, h, color):
        layout = PangoCairo.create_layout(cr)
        layout.set_font_description(Pango.FontDescription(f"{UI_FONT} 11"))
        layout.set_alignment(Pango.Alignment.CENTER)
        layout.set_width(int(max(1, w - 8) * Pango.SCALE))
        layout.set_ellipsize(Pango.EllipsizeMode.END)
        layout.set_text(text, -1)
        tw, th = layout.get_pixel_size()
        if th > h - 4:
            return
        cr.set_source_rgb(*_rgb(color))
        cr.move_to(x + (w - tw) / 2 if tw < w - 8 else x + 4, y + (h - th) / 2)
        PangoCairo.show_layout(cr, layout)

    # ---- dragging -----------------------------------------------------------
    def begin(self, gesture, vx, vy):
        if self.frame is None:
            self.fit()
        name = self.hit(vx, vy)
        if name is None:
            gesture.set_state(Gtk.EventSequenceState.DENIED)
            return
        gesture.set_state(Gtk.EventSequenceState.CLAIMED)
        x, y, _w, _h = self.rects[name]
        self.drag = (name, x, y)

    def update(self, _gesture, dx, dy):
        if not self.drag:
            return
        name, x0, y0 = self.drag
        f = self.frame[0]
        self.rects[name][0] = x0 + dx / f
        self.rects[name][1] = y0 + dy / f
        self.queue_draw()

    def end(self, _gesture, dx, dy):
        if not self.drag:
            return
        name = self.drag[0]
        moved = math.hypot(dx, dy) > 6
        self.drag = None
        if moved:
            self.on_drop({n: tuple(r) for n, r in self.rects.items()})
        self.queue_draw()

    def set_screens(self, screens, main):
        self.rects = {n: [x, y, w, h] for n, _l, x, y, w, h in screens}
        self.labels = {n: lbl for n, lbl, *_r in screens}
        self.main = main
        self.queue_draw()

