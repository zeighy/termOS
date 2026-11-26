"""The shell process: one surface set per monitor, and the actions behind termos-show."""
import os

from gi.repository import Gdk, Gio, GLib, Gtk

from .. import core, ui
from ..toplevels import Toplevels
from . import home, osd, overlays, panel, status, style

AWAKE = os.path.join(os.environ.get("XDG_RUNTIME_DIR", "/tmp"), "termos-awake")


class Shell(Gtk.Application):
    def __init__(self):
        super().__init__(application_id="org.termos.Shell", flags=Gio.ApplicationFlags.FLAGS_NONE)
        self.windows = None
        self.panels = []
        self.homes = []
        self.overlay = None
        self.overlay_kind = None
        self.rebuild_queued = 0
        self.outputs_queued = 0
        self.restore_queued = 0
        self.focused = None
        self.known_windows = set()
        self.was_home = True


    def do_startup(self):
        Gtk.Application.do_startup(self)
        ui.setup(style.CSS)
        self.hold()
        for name, fn in (("apps", lambda: self.toggle("apps")),
                         ("quick", lambda: self.toggle("quick")),
                         ("power", lambda: self.toggle("power")),
                         ("windows", lambda: self.toggle("windows")),
                         ("desktop", self.show_desktop),
                         ("volume", lambda: self.osd.show_volume()),
                         ("brightness", lambda: self.osd.show_brightness()),
                         ("reload", self.queue_rebuild)):
            action = Gio.SimpleAction.new(name, None)
            action.connect("activate", lambda _a, _p, f=fn: f())
            self.add_action(action)
        self.status = status.Status()
        self.osd = osd.Osd()
        try:
            self.windows = Toplevels(self.windows_changed, self.quit)
        except (OSError, KeyError) as e:
            print(f"termos-shell: no window list: {e}")
        self.machines = home.Machines(self)
        display = Gdk.Display.get_default()
        display.connect("monitor-added", self.monitors_changed)
        display.connect("monitor-removed", self.monitors_changed)
        self.rebuild()
        self.machines.refresh()
        GLib.timeout_add_seconds(2, self.first_run)

    def do_activate(self):
        pass

    # ---- screens ----------------------------------------------------------
    def monitors_changed(self, _display, _monitor):
        # apply saved/auto scale, rearrange remaining screens, and keep main-screen rule current
        if self.outputs_queued:
            GLib.source_remove(self.outputs_queued)

        def apply_outputs():
            self.outputs_queued = 0
            core.spawn("termos-outputs", "apply")
            return False
        self.outputs_queued = GLib.timeout_add(800, apply_outputs)
        self.queue_rebuild()

    def watch_monitor(self, monitor):
        if not getattr(monitor, "termos_watched", False):
            monitor.termos_watched = True
            monitor.connect("notify::geometry", lambda *_a: self.queue_rebuild())

    def queue_rebuild(self):
        if self.rebuild_queued:
            GLib.source_remove(self.rebuild_queued)
        self.rebuild_queued = GLib.timeout_add(350, self.rebuild)

    def rebuild(self):
        self.rebuild_queued = 0
        self.close_overlay()
        for item in self.panels + self.homes:
            item.destroy()
        self.panels, self.homes = [], []
        display = Gdk.Display.get_default()
        show_home = core.setting_on("HOME_SCREEN")
        for i in range(display.get_n_monitors()):
            monitor = display.get_monitor(i)
            self.watch_monitor(monitor)
            self.panels.append(panel.Panel(self, monitor))
            if show_home:
                self.homes.append(home.Home(self, monitor))
        return False

    # ---- overlays ---------------------------------------------------------
    def toggle(self, kind, monitor=None):
        same = self.overlay_kind == kind
        self.close_overlay()
        if same:
            return
        self.overlay = overlays.KINDS[kind](self, monitor)
        self.overlay_kind = kind
        if kind == "apps":
            self.queue_keyboard_restore()

    def close_overlay(self):
        if self.overlay:
            self.overlay.destroy()
        self.overlay = self.overlay_kind = None

    def launch(self, *cmd):
        self.close_overlay()
        core.spawn(*cmd)

    def show_desktop(self):
        self.close_overlay()
        if self.windows:
            self.windows.toggle_desktop()

    # ---- windows ----------------------------------------------------------
    def windows_changed(self):
        live = {w.oid for w in self.windows.all()}
        if live - self.known_windows and self.overlay:
            self.close_overlay()        # something opened; don't leave a sheet on top of it
        self.known_windows = live
        for p in self.panels:
            p.update_windows()
        if self.overlay_kind == "windows":
            self.overlay.refresh()
        at_home = self.windows.home_visible()
        if at_home and not self.was_home:
            self.machines.refresh()
        self.was_home = at_home
        active = self.windows.active()
        oid = active.oid if active else None
        if oid != self.focused:
            self.focused = oid
            self.queue_keyboard_restore()

    def queue_keyboard_restore(self):
        # squeekboard hides when the focus moves; bring it back if the user had it open
        wanted = os.path.join(os.environ.get("XDG_RUNTIME_DIR", "/tmp"), "termos-osk-wanted")
        if not os.path.exists(wanted):
            return
        if self.restore_queued:
            GLib.source_remove(self.restore_queued)

        def restore():
            self.restore_queued = 0
            core.spawn("termos-osk", "restore")
            return False
        self.restore_queued = GLib.timeout_add(350, restore)

    # ---- keep awake -------------------------------------------------------
    def keep_awake(self):
        return os.path.exists(AWAKE)

    def set_keep_awake(self, on):
        if on:
            core.write_atomic(AWAKE, "1\n")
        elif os.path.exists(AWAKE):
            os.unlink(AWAKE)
        core.spawn("termos-idle", "restart")
        self.status.emit()

    def first_run(self):
        if not os.path.exists(os.path.join(core.CFG, "welcome-done")):
            core.spawn("termos-welcome")
        return False
