"""Installed applications: names and icons for windows, launching."""
import re
import shlex

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gio, GLib, Gtk  # noqa: E402

from . import core  # noqa: E402

_cache = {}
_monitor = None


def installed():
    global _monitor
    if _monitor is None:
        _monitor = Gio.AppInfoMonitor.get()
        _monitor.connect("changed", lambda _m: _cache.clear())
    if "all" not in _cache:
        _cache["all"] = sorted((a for a in Gio.AppInfo.get_all() if a.should_show()),
                               key=lambda a: (a.get_display_name() or "").lower())
    return _cache["all"]


def for_window(app_id):
    """The application behind a Wayland app-id, or None."""
    key = ("win", app_id)
    if key not in _cache:
        wanted = app_id.lower()
        found = None
        for a in installed():
            stem = (a.get_id() or "")[:-len(".desktop")].lower()
            if stem == wanted:
                found = a
                break
            if not found and wanted and (stem.split(".")[-1] == wanted.split(".")[-1]
                                         or (a.get_executable() or "").split("/")[-1] == wanted):
                found = a
        _cache[key] = found
    return _cache[key]


def window_name(app_id):
    a = for_window(app_id)
    return a.get_display_name() if a else app_id or "Window"


def image(app, size, fallback="application-x-executable"):
    gicon = app.get_icon() if app else None
    img = (Gtk.Image.new_from_gicon(gicon, Gtk.IconSize.DIALOG) if gicon
           else Gtk.Image.new_from_icon_name(fallback, Gtk.IconSize.DIALOG))
    img.set_pixel_size(size)
    return img


def window_image(app_id, size):
    return image(for_window(app_id), size, app_id or "application-x-executable")


def launch(app):
    try:
        if app.get_boolean("Terminal"):
            # GLib doesn't know about foot
            cmd = re.sub(r"\s%[a-zA-Z]", "", app.get_string("Exec") or "")
            core.spawn("foot", "-T", app.get_display_name(), "-e", *shlex.split(cmd))
        else:
            app.launch([], None)
        return True
    except (GLib.Error, ValueError, AttributeError):
        return False
