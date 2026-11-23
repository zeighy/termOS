"""Layer-shell windows."""
import gi

gi.require_version("GtkLayerShell", "0.1")
from gi.repository import Gdk, Gtk, GtkLayerShell  # noqa: E402

from .. import ui  # noqa: E402

Layer = GtkLayerShell.Layer
Edge = GtkLayerShell.Edge
Keys = GtkLayerShell.KeyboardMode
ALL = (Edge.TOP, Edge.BOTTOM, Edge.LEFT, Edge.RIGHT)


def window(name, layer, edges, monitor=None, keys=Keys.NONE, clear=True):
    win = ui.classes(Gtk.Window(), "termos", name)
    GtkLayerShell.init_for_window(win)
    GtkLayerShell.set_namespace(win, f"termos-{name}")
    GtkLayerShell.set_layer(win, layer)
    GtkLayerShell.set_keyboard_mode(win, keys)
    for edge in edges:
        GtkLayerShell.set_anchor(win, edge, True)
    if monitor is not None:
        GtkLayerShell.set_monitor(win, monitor)
    if clear:
        visual = win.get_screen().get_rgba_visual()
        if visual:
            win.set_visual(visual)
        win.set_app_paintable(True)
    return win


def reserve(win):
    GtkLayerShell.auto_exclusive_zone_enable(win)


def margin(win, edge, size):
    GtkLayerShell.set_margin(win, edge, size)


def monitor_of(widget):
    top = widget.get_toplevel() if widget else None
    return getattr(top, "termos_monitor", None)


def monitor_size(monitor):
    if monitor is None:
        display = Gdk.Display.get_default()
        monitor = display.get_monitor(0)
    if monitor is None:
        return 1280, 800
    geo = monitor.get_geometry()
    return geo.width, geo.height
