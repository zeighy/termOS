"""The top panel: icon buttons that scroll, with arrows, when they don't all fit."""
import time

from gi.repository import Gdk, GLib, Gtk

from .. import apps, core, icons, ui
from . import surface

ARROW_WIDTH = 38


class Strip(Gtk.Box):
    """A row of icons that gets left and right arrows when it is wider than its space."""

    def __init__(self):
        super().__init__()
        self.row = ui.hbox(0)
        self.view = Gtk.ScrolledWindow()
        # EXTERNAL: scrolls by finger or arrow, without a scrollbar or a minimum width
        self.view.set_policy(Gtk.PolicyType.EXTERNAL, Gtk.PolicyType.NEVER)
        self.view.set_kinetic_scrolling(True)
        self.view.add(self.row)
        self.adj = self.view.get_hadjustment()
        self.prev = ui.button(None, lambda: self.page(-1), "arrow", icon_name="left", tip="Scroll icons left")
        self.next = ui.button(None, lambda: self.page(1), "arrow", icon_name="right", tip="Scroll icons right")
        for b in (self.prev, self.next):
            b.set_no_show_all(True)
            b.get_child().show_all()
        self.pack_start(self.prev, False, False, 0)
        self.pack_start(self.view, True, True, 0)
        self.pack_start(self.next, False, False, 0)
        self.overflowing = False
        self.check_queued = 0
        self.animation = 0
        self.connect("size-allocate", lambda *_a: self.queue_check())
        self.row.connect("size-allocate", lambda *_a: self.queue_check())
        self.adj.connect("value-changed", lambda _a: self.update_arrows())
        self.adj.connect("changed", lambda _a: self.queue_check())
        self.view.connect("scroll-event", self.wheel)
        self.connect("destroy", self.stop)

    def stop(self, _w):
        for source in (self.check_queued, self.animation):
            if source:
                GLib.source_remove(source)
        self.check_queued = self.animation = 0

    def queue_check(self):
        if not self.check_queued:
            self.check_queued = GLib.idle_add(self.check)

    def check(self):
        self.check_queued = 0
        wanted = self.row.get_preferred_width()[1]
        # compare with the space there is without arrows, so they can't make themselves needed
        overflow = wanted > self.get_allocated_width() + 1
        if overflow != self.overflowing:
            self.overflowing = overflow
            self.prev.set_visible(overflow)
            self.next.set_visible(overflow)
            if not overflow:
                self.adj.set_value(0)
        self.update_arrows()
        return False

    def end(self):
        return max(self.adj.get_upper() - self.adj.get_page_size(), 0)

    def update_arrows(self):
        pos = self.adj.get_value()
        self.prev.set_sensitive(pos > 1)
        self.next.set_sensitive(pos < self.end() - 1)

    def page(self, direction):
        self.glide(self.adj.get_value() + direction * max(self.adj.get_page_size() * 0.8, 100))

    def glide(self, target):
        target = min(max(target, 0), self.end())
        start, began = self.adj.get_value(), time.monotonic()
        if self.animation:
            GLib.source_remove(self.animation)

        def step():
            t = min((time.monotonic() - began) / 0.22, 1)
            self.adj.set_value(start + (target - start) * (1 - (1 - t) ** 3))
            if t < 1:
                return True
            self.animation = 0
            return False
        self.animation = GLib.timeout_add(16, step)

    def wheel(self, _w, event):
        if not self.overflowing:
            return False
        ok, dx, dy = event.get_scroll_deltas()
        if not ok:
            d = event.direction
            dy = 1 if d in (Gdk.ScrollDirection.DOWN, Gdk.ScrollDirection.RIGHT) else -1
            dx = 0
        self.adj.set_value(min(max(self.adj.get_value() + (dx + dy) * 52, 0), self.end()))
        return True

    def reveal(self, child):
        if not child or not self.overflowing:
            return
        where = child.translate_coordinates(self.row, 0, 0)
        if not where:
            return
        left, right = where[0], where[0] + child.get_allocated_width()
        pos, size = self.adj.get_value(), self.adj.get_page_size()
        if left < pos:
            self.glide(left - 8)
        elif right > pos + size:
            self.glide(right - size + 8)


class Panel:
    def __init__(self, shell, monitor):
        self.shell = shell
        self.monitor = monitor
        self.tasks = {}
        self.active = None
        e = surface.Edge
        win = surface.window("panel", surface.Layer.TOP, (e.TOP, e.LEFT, e.RIGHT), monitor, clear=False)
        surface.reserve(win)
        win.termos_monitor = monitor
        self.window = win

        bar = ui.hbox(2)
        bar.pack_start(ui.button(None, lambda: shell.toggle("apps", monitor), "apps",
                                 icon_name="apps", tip="Apps"), False, False, 0)
        self.strip = Strip()
        bar.pack_start(self.strip, True, True, 0)

        def pin(name, tip, action):
            self.strip.row.pack_start(ui.button(None, action, icon_name=name, tip=tip), False, False, 0)
        pin("home", "Home screen", shell.show_desktop)
        pin("terminal", "Terminal", lambda: shell.launch("foot"))
        pin("server", "SSH hosts", lambda: shell.launch("termos-ssh"))
        pin("web", "Browser", lambda: shell.launch("chromium"))
        pin("folder", "Files", lambda: shell.launch("thunar"))
        pin("remote", "Remote desktop", lambda: shell.launch("remmina"))
        self.divider = ui.hbox(0, "divider")
        self.divider.set_no_show_all(True)
        self.strip.row.pack_start(self.divider, False, False, 0)
        self.task_box = ui.hbox(0)
        self.strip.row.pack_start(self.task_box, False, False, 0)

        self.windows_btn = ui.button(None, lambda: shell.toggle("windows", monitor),
                                     icon_name="windows", tip="Open windows")
        self.windows_btn.set_no_show_all(True)
        self.windows_btn.get_child().show_all()
        bar.pack_start(self.windows_btn, False, False, 0)
        bar.pack_start(ui.button(None, lambda: core.spawn("termos-osk", "toggle"),
                                 icon_name="keyboard", tip="On-screen keyboard"), False, False, 0)
        bar.pack_start(self.status_button(), False, False, 0)
        win.add(bar)
        self.compact = None
        win.connect("size-allocate", self.resized)
        shell.status.listen(win, self.update_status)
        ui.every(win, 5, self.update_clock)
        win.show_all()
        self.update_windows()
        self.update_status()
        self.update_clock()

    def status_button(self):
        b = ui.classes(Gtk.Button(), "status")
        box = ui.hbox(9)
        self.link_icon = ui.icon("link")
        self.awake_icon = ui.icon("coffee", "warn")
        self.net_icon = ui.icon("wifi-off")
        self.vol_icon = ui.icon("volume-high")
        self.bat_icon = ui.icon("battery")
        self.bat_text = ui.label("")
        self.clock = ui.label("", "clock")
        for w in (self.link_icon, self.awake_icon, self.net_icon, self.vol_icon,
                  self.bat_icon, self.bat_text, self.clock):
            w.set_no_show_all(True)
            box.pack_start(w, False, False, 0)
        self.clock.show()
        b.add(box)
        b.get_accessible().set_name("Quick Settings")
        b.connect("clicked", lambda _b: self.shell.toggle("quick", self.monitor))
        return b

    def resized(self, _w, alloc):
        compact = alloc.width < 600
        if compact != self.compact:
            self.compact = compact
            GLib.idle_add(lambda: (self.update_status(), self.update_windows(), False)[2])

    def update_clock(self):
        self.clock.set_text(time.strftime("%H:%M"))

    def update_status(self):
        st = self.shell.status
        roomy = not self.compact
        net = st.net
        self.net_icon.set_visible(True)
        self.net_icon.set_text(icons.wifi_glyph(net["strength"]) if net["kind"] == "wifi"
                               else icons.glyph("ethernet" if net["kind"] == "ethernet" else "wifi-off"))
        ui.set_class(self.net_icon, "sub", net["kind"] == "none")

        self.vol_icon.set_visible(roomy and st.volume is not None)
        if st.volume is not None:
            self.vol_icon.set_text(icons.volume_glyph(*st.volume))

        bat = st.battery
        self.bat_icon.set_visible(bool(bat))
        self.bat_text.set_visible(bool(bat) and roomy)
        if bat:
            pct = bat["percent"]
            self.bat_icon.set_text(icons.battery_glyph(pct, bat["charging"]))
            self.bat_text.set_text(f"{pct}%")
            for w in (self.bat_icon, self.bat_text):
                ui.set_class(w, "warn", not bat["charging"] and 10 < pct <= 25)
                ui.set_class(w, "error", not bat["charging"] and pct <= 10)

        states = list(st.connections.values())
        broken = "reconnecting" in states
        self.link_icon.set_visible(broken or roomy and "connected" in states)
        self.link_icon.set_text(icons.glyph("link-off" if broken else "link"))
        ui.set_class(self.link_icon, "warn", broken)
        ui.set_class(self.link_icon, "good", not broken)
        self.awake_icon.set_visible(self.shell.keep_awake())

    def update_windows(self):
        windows = self.shell.windows.all() if self.shell.windows else []
        live = {w.oid for w in windows}
        for oid in [o for o in self.tasks if o not in live]:
            self.tasks.pop(oid)[0].destroy()
        active = None
        for w in windows:
            entry = self.tasks.get(w.oid)
            if entry and entry[1] != w.app_id:
                entry[0].destroy()
                entry = None
            if not entry:
                b = ui.classes(Gtk.Button(), "task")
                b.add(apps.window_image(w.app_id, 30))
                b.connect("clicked", self.task_clicked, w.oid)
                b.connect("button-press-event", self.task_pressed)
                b.show_all()
                self.task_box.pack_start(b, False, False, 0)
                entry = self.tasks[w.oid] = (b, w.app_id)
            b = entry[0]
            b.get_accessible().set_name(w.title or apps.window_name(w.app_id))
            ui.set_class(b, "active", w.active and not w.minimized)
            ui.set_class(b, "minimized", w.minimized)
            if w.active and not w.minimized:
                active = w.oid
        self.divider.set_visible(bool(windows))
        self.windows_btn.set_visible(bool(windows) and not self.compact)
        self.strip.queue_check()
        if active != self.active:
            self.active = active
            if active:
                # after the new button has its place
                GLib.timeout_add(120, lambda: (active in self.tasks and
                                               self.strip.reveal(self.tasks[active][0]), False)[1])

    def task_clicked(self, _b, oid):
        self.shell.close_overlay()
        win = self.shell.windows.windows.get(oid)
        if win:
            if win.active and not win.minimized:
                win.minimize()
            else:
                win.activate()

    def task_pressed(self, _b, event):
        if event.button == 3:
            self.shell.toggle("windows", self.monitor)
            return True
        return False

    def destroy(self):
        self.window.destroy()
