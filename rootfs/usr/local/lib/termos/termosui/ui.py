"""GTK3 building blocks with the termOS look."""
import signal
import sys
import threading
import traceback

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, Gio, GLib, Gtk, Pango  # noqa: E402

from . import icons  # noqa: E402
from .palette import COLORS, ICON_FONT, UI_FONT, gtk_named_colors  # noqa: E402

_BASE_CSS = """
.termos {{ font-family: "{font}"; font-size: 15px; color: {text}; }}
window.termos.background {{ background-color: {base}; }}
.icon {{ font-family: "{icons}"; font-weight: normal; }}
.termos .title {{ font-size: 24px; font-weight: bold; }}
.termos .heading {{ font-size: 14px; font-weight: bold; color: {muted}; }}
.termos .row-label {{ font-size: 16px; }}
.termos .sub {{ font-size: 13px; color: {muted}; }}
.termos .error {{ color: {red}; }}
.termos .good {{ color: {green}; }}
.termos .warn {{ color: {yellow}; }}
.termos .accent {{ color: {accent}; }}
.termos .card {{ background-color: {card}; border-radius: 14px; padding: 6px 16px; }}
.termos button {{ min-height: 46px; min-width: 22px; padding: 0 14px; border-radius: 12px;
    background-image: none; background-color: {raised}; color: {text}; border: none;
    box-shadow: none; text-shadow: none; }}
.termos button:hover {{ background-color: {hover}; }}
.termos button:active {{ background-color: {hover}; }}
.termos button:disabled {{ opacity: 0.45; }}
.termos button.primary {{ background-color: {accent}; color: {crust}; font-weight: bold; }}
.termos button.danger {{ background-color: {danger}; color: {bright}; }}
.termos button.flat {{ background-color: transparent; }}
.termos button.flat:hover {{ background-color: {raised}; }}
.termos button.round {{ min-width: 48px; min-height: 48px; padding: 0; }}
.termos button .icon {{ font-size: 22px; }}
.termos entry {{ min-height: 46px; padding: 0 12px; border-radius: 12px; background-color: {mantle};
    color: {text}; border: 1px solid {hover}; box-shadow: none; }}
.termos entry:focus {{ border-color: {accent}; }}
.termos combobox button.combo {{ padding: 0 12px; }}
.termos switch {{ min-width: 64px; min-height: 34px; border-radius: 20px; border: none;
    background-image: none; background-color: {hover}; }}
.termos switch:checked {{ background-color: {accent}; }}
.termos switch slider {{ min-width: 30px; min-height: 30px; border-radius: 20px; border: none;
    margin: 2px; background-image: none; background-color: {bright}; }}
.termos scale trough {{ min-height: 10px; border-radius: 6px; border: none; background-color: {hover}; }}
.termos scale highlight {{ border-radius: 6px; border: none; background-color: {accent}; }}
.termos scale slider {{ min-width: 30px; min-height: 30px; border-radius: 20px; border: none;
    background-image: none; background-color: {bright}; }}
.termos radio {{ min-width: 24px; min-height: 24px; }}
.termos list {{ background-color: transparent; }}
.termos .nav {{ background-color: {mantle}; }}
.termos .nav row {{ padding: 12px 14px; margin: 3px 8px; border-radius: 12px; }}
.termos .nav row:selected {{ background-color: {raised}; color: {accent}; }}
.termos .nav .icon {{ font-size: 23px; }}
.termos .hero {{ font-size: 44px; color: {muted}; }}
.termos .lead {{ font-size: 30px; }}
"""


def css(text):
    """Add CSS. {name} expands to a palette colour; literal braces are doubled."""
    prov = Gtk.CssProvider()
    prov.load_from_data(text.format(font=UI_FONT, icons=ICON_FONT, **COLORS).encode())
    # above the user's gtk.css, so our own apps always look the same
    Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(), prov,
                                             Gtk.STYLE_PROVIDER_PRIORITY_USER + 1)


_ready = False


def setup(extra_css=None):
    global _ready
    if not _ready:
        _ready = True
        st = Gtk.Settings.get_default()
        st.set_property("gtk-theme-name", "adw-gtk3-dark")
        st.set_property("gtk-icon-theme-name", "Papirus-Dark")
        st.set_property("gtk-font-name", f"{UI_FONT} 11")
        prov = Gtk.CssProvider()
        prov.load_from_data(gtk_named_colors().encode())
        Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(), prov,
                                                 Gtk.STYLE_PROVIDER_PRIORITY_USER)
        css(_BASE_CSS)
    if extra_css:
        css(extra_css)


def classes(widget, *names):
    ctx = widget.get_style_context()
    for n in names:
        if n:
            ctx.add_class(n)
    return widget


def set_class(widget, name, on):
    ctx = widget.get_style_context()
    (ctx.add_class if on else ctx.remove_class)(name)


def clear(container):
    for child in container.get_children():
        child.destroy()


def vbox(spacing=0, *cls):
    return classes(Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=spacing), *cls)


def hbox(spacing=0, *cls):
    return classes(Gtk.Box(spacing=spacing), *cls)


def label(text="", *cls, xalign=0.0, wrap=False, ellipsize=False):
    lb = Gtk.Label(label=text, xalign=xalign)
    if wrap:
        lb.set_line_wrap(True)
        lb.set_line_wrap_mode(Pango.WrapMode.WORD_CHAR)
        # a low minimum lets the window get narrow; the natural width stays readable
        lb.set_width_chars(12)
        lb.set_max_width_chars(56)
    if ellipsize:
        lb.set_ellipsize(Pango.EllipsizeMode.END)
    return classes(lb, *cls)


def icon(name, *cls):
    return classes(Gtk.Label(label=icons.glyph(name)), "icon", *cls)


def mouse_only_tooltip(widget):
    """After a tap a tooltip pops up and stays, covering things: mice and touchpads only."""
    def track(w, event):
        if event.type == Gdk.EventType.TOUCH_BEGIN:
            w.set_has_tooltip(False)
        elif event.type == Gdk.EventType.MOTION_NOTIFY:
            device = event.get_source_device()
            if device and device.get_source() != Gdk.InputSource.TOUCHSCREEN:
                w.set_has_tooltip(True)
        return False
    widget.add_events(Gdk.EventMask.POINTER_MOTION_MASK | Gdk.EventMask.TOUCH_MASK)
    widget.connect("event", track)


def button(text=None, on_click=None, *cls, icon_name=None, tip=None):
    b = Gtk.Button()
    inner = hbox(8)
    inner.set_halign(Gtk.Align.CENTER)
    b.icon_widget = None
    b.label_widget = None
    if icon_name:
        b.icon_widget = icon(icon_name)
        inner.pack_start(b.icon_widget, False, False, 0)
    if text is not None:
        b.label_widget = label(text)
        inner.pack_start(b.label_widget, False, False, 0)
    b.add(inner)
    name = tip or text
    if name:
        b.get_accessible().set_name(name)
    if tip:
        b.set_tooltip_text(tip)
        mouse_only_tooltip(b)
    if on_click:
        b.connect("clicked", lambda _b: on_click())
    return classes(b, *cls)


def ignore_scroll(widget):
    """Scrolling a page must never change the control under the pointer."""
    def block(w, _event):
        w.stop_emission_by_name("scroll-event")
        return False    # hand the event on, so the page scrolls instead

    def hook(w):
        w.connect("scroll-event", block)
        if isinstance(w, Gtk.Container):
            w.forall(hook)
    hook(widget)
    return widget


def combo(options, active, on_change=None):
    c = Gtk.ComboBoxText()
    for key, text in options:
        c.append(str(key), text)
    c.set_active_id(str(active))
    if on_change:
        c.connect("changed", lambda w: on_change(w.get_active_id()))
    return ignore_scroll(c)


def switch(active, on_change):
    """on_change may return False to say it failed; the switch then goes back."""
    s = Gtk.Switch(active=bool(active))
    reverting = []

    def changed(w, _p):
        if reverting:
            return
        if on_change(w.get_active()) is False:
            reverting.append(1)
            w.set_active(not w.get_active())
            reverting.clear()
    s.connect("notify::active", changed)
    s.set_valign(Gtk.Align.CENTER)
    return s


def slider(lo, hi, value, on_change, width=220):
    s = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, lo, hi, 1)
    s.set_value(value)
    s.set_digits(0)
    s.set_draw_value(False)
    s.set_size_request(width, 46)
    pending = []

    def fire():
        pending.clear()
        on_change(int(s.get_value()))
        return False

    def changed(w):
        if getattr(w, "quiet", False):
            return
        if pending:
            GLib.source_remove(pending.pop())
        pending.append(GLib.timeout_add(80, fire))
    s.connect("value-changed", changed)
    return ignore_scroll(s)


def set_quietly(scale, value):
    scale.quiet = True
    scale.set_value(value)
    scale.quiet = False


class Clamp(Gtk.Bin):
    """Keeps content in a readable column on wide screens and lets it shrink on narrow ones."""
    __gtype_name__ = "TermosClamp"

    def __init__(self, child, width=700):
        super().__init__()
        self.limit = width
        self.add(child)

    def do_get_preferred_width(self):
        low, natural = self.get_child().get_preferred_width() if self.get_child() else (0, 0)
        return low, max(low, min(natural, self.limit))

    def do_get_request_mode(self):
        return Gtk.SizeRequestMode.HEIGHT_FOR_WIDTH

    def do_get_preferred_height(self):
        return self.get_child().get_preferred_height() if self.get_child() else (0, 0)

    def do_get_preferred_height_for_width(self, width):
        child = self.get_child()
        if not child:
            return 0, 0
        low = child.get_preferred_width()[0]
        return child.get_preferred_height_for_width(max(min(width, self.limit), low))

    def do_size_allocate(self, alloc):
        self.set_allocation(alloc)
        child = self.get_child()
        if child:
            rect = Gdk.Rectangle()
            rect.width = min(alloc.width, max(self.limit, child.get_preferred_width()[0]))
            rect.height = alloc.height
            rect.x = alloc.x + (alloc.width - rect.width) // 2
            rect.y = alloc.y
            child.size_allocate(rect)


def scrolled(child):
    sw = Gtk.ScrolledWindow()
    sw.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
    sw.set_kinetic_scrolling(True)
    sw.add(child)
    return sw


class Page:
    """A scrolling column of titled cards that hold rows."""

    def __init__(self, width=700):
        self.box = vbox(0)
        self.box.set_border_width(16)
        self.widget = scrolled(Clamp(self.box, width))
        self.card = None

    def section(self, title=None):
        if title:
            head = label(title, "heading", wrap=True)
            head.set_margin_top(14)
            head.set_margin_bottom(6)
            head.set_margin_start(4)
            self.box.pack_start(head, False, False, 0)
        self.card = vbox(0, "card")
        self.box.pack_start(self.card, False, False, 0)
        return self.card

    def row(self, title, widget=None, sub=None):
        if self.card is None:
            self.section()
        line = hbox(14)
        text = vbox(2)
        text.set_valign(Gtk.Align.CENTER)
        text.pack_start(label(title, "row-label", wrap=True), False, False, 0)
        if sub:
            text.pack_start(label(sub, "sub", wrap=True), False, False, 0)
        line.pack_start(text, True, True, 0)
        if widget is not None:
            widget.set_valign(Gtk.Align.CENTER)
            line.pack_end(widget, False, False, 0)
            if not widget.get_accessible().get_name():
                widget.get_accessible().set_name(title)
        self.card.pack_start(line, False, False, 9)
        return line

    def note(self, text, *cls):
        lb = label(text, *(cls or ("sub",)), wrap=True)
        (self.card or self.box).pack_start(lb, False, False, 8)
        return lb

    def add(self, widget):
        (self.card or self.box).pack_start(widget, False, False, 8)
        return widget


def empty_state(icon_name, title, text, *actions):
    box = vbox(10)
    box.set_border_width(24)
    box.pack_start(icon(icon_name, "hero"), False, False, 0)
    box.pack_start(label(title, "row-label", xalign=0.5), False, False, 0)
    hint = label(text, "sub", xalign=0.5, wrap=True)
    hint.set_justify(Gtk.Justification.CENTER)
    box.pack_start(hint, False, False, 0)
    if actions:
        line = hbox(8)
        line.set_halign(Gtk.Align.CENTER)
        for a in actions:
            line.pack_start(a, False, False, 0)
        box.pack_start(line, False, False, 6)
    return box


def dialog(parent, title, body=None):
    dlg = Gtk.Dialog(title=title, transient_for=parent, modal=True)
    classes(dlg, "termos")
    dlg.set_default_size(400, -1)
    area = dlg.get_content_area()
    area.set_border_width(16)
    area.set_spacing(10)
    area.pack_start(label(title, "row-label", wrap=True), False, False, 0)
    if body:
        area.pack_start(label(body, "sub", wrap=True), False, False, 0)
    return dlg, area


def message(parent, title, body=None):
    dlg, area = dialog(parent, title, body)
    area.pack_start(button("OK", lambda: dlg.response(Gtk.ResponseType.OK), "primary"), False, False, 6)
    dlg.show_all()
    dlg.run()
    dlg.destroy()


def confirm(parent, title, body=None, yes="OK", danger=False, no="Cancel"):
    dlg, area = dialog(parent, title, body)
    line = hbox(8)
    line.set_homogeneous(True)
    line.add(button(no, lambda: dlg.response(Gtk.ResponseType.CANCEL)))
    line.add(button(yes, lambda: dlg.response(Gtk.ResponseType.OK), "danger" if danger else "primary"))
    area.pack_start(line, False, False, 6)
    dlg.show_all()
    ok = dlg.run() == Gtk.ResponseType.OK
    dlg.destroy()
    return ok


def background(work, done=None):
    """Run work() in a thread; done(result) runs on the UI thread (None if work raised)."""
    def finish(result):
        done(result)
        return False

    def body():
        try:
            result = work()
        except Exception:
            traceback.print_exc()
            result = None
        if done:
            GLib.idle_add(finish, result)
    threading.Thread(target=body, daemon=True).start()


def every(widget, seconds, fn):
    """Call fn every so many seconds until widget is destroyed."""
    def tick():
        fn()
        return True
    source = GLib.timeout_add_seconds(seconds, tick)
    widget.connect("destroy", lambda _w: GLib.source_remove(source))


class App(Gtk.Application):
    """A single-instance app: launching it again raises the window it already has."""

    def __init__(self, name, window_class, program):
        # GTK uses prgname as the Wayland app-id, which picks the icon and .desktop file
        GLib.set_prgname(program)
        super().__init__(application_id=f"org.termos.{name}",
                         flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE)
        self.window_class = window_class
        self.window = None

    def do_command_line(self, command_line):
        args = command_line.get_arguments()[1:]
        setup()
        if self.window is None:
            self.window = classes(self.window_class(), "termos")
            self.window.connect("destroy", self._gone)
            self.add_window(self.window)
            self.window.show_all()
        if args and hasattr(self.window, "open_arg"):
            self.window.open_arg(*args)
        self.window.present_with_time(Gdk.CURRENT_TIME)
        return 0

    def _gone(self, _w):
        self.window = None
        self.quit()


def main(name, window_class, program):
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    return App(name, window_class, program).run(sys.argv)
