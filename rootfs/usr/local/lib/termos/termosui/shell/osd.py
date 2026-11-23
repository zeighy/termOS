"""The volume and brightness indicator."""
import cairo
from gi.repository import GLib, Gtk

from .. import core, icons, ui
from . import surface


class Osd:
    def __init__(self):
        self.window = None
        self.timer = 0

    def show_volume(self):
        ui.background(core.get_volume, self.got_volume)

    def got_volume(self, value):
        if value:
            percent, muted = value
            self.show(icons.volume_glyph(percent, muted), 0 if muted else percent,
                      "Muted" if muted else f"{percent}%")

    def show_brightness(self):
        percent = core.get_brightness()
        if percent is not None:
            self.show(icons.glyph("brightness"), percent, f"{percent}%")

    def create(self):
        win = surface.window("osd", surface.Layer.OVERLAY, (surface.Edge.BOTTOM,))
        surface.margin(win, surface.Edge.BOTTOM, 48)
        box = ui.hbox(14, "box")
        self.icon = ui.classes(Gtk.Label(), "icon")
        self.bar = Gtk.ProgressBar()
        self.bar.set_size_request(220, -1)
        self.bar.set_valign(Gtk.Align.CENTER)
        self.text = ui.label("", xalign=1.0)
        self.text.set_width_chars(6)
        for w in (self.icon, self.bar, self.text):
            box.pack_start(w, False, False, 0)
        win.add(box)
        # taps go through to whatever is underneath
        win.connect("map", lambda w: w.get_window().input_shape_combine_region(cairo.Region(), 0, 0))
        self.window = win

    def show(self, glyph, percent, text):
        if not self.window:
            self.create()
        self.icon.set_text(glyph)
        self.bar.set_fraction(min(max(percent / 100, 0), 1))
        self.text.set_text(text)
        self.window.show_all()
        if self.timer:
            GLib.source_remove(self.timer)
        self.timer = GLib.timeout_add(1600, self.hide)

    def hide(self):
        self.timer = 0
        if self.window:
            self.window.destroy()       # a fresh one lands on the screen in use
            self.window = None
        return False
