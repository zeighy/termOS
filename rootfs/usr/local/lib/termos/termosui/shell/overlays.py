"""Things that open over the desktop: Quick Settings, power, windows and apps."""


from gi.repository import Gdk, GLib, Gtk

from .. import apps, bluetooth, core, icons, netinfo, ui
from . import surface


class Overlay:
    """Covers the space below the panel; a tap outside the sheet closes it."""
    solid = False
    keys = surface.Keys.ON_DEMAND
    align = (Gtk.Align.CENTER, Gtk.Align.CENTER)
    width = 420

    def __init__(self, shell, monitor):
        self.shell = shell
        self.monitor = monitor
        self.screen = surface.monitor_size(monitor)
        # TOP, not OVERLAY: the on-screen keyboard has to be able to sit beside it
        win = surface.window("overlay", surface.Layer.TOP, surface.ALL, monitor, self.keys)
        self.window = win
        back = ui.classes(Gtk.EventBox(), "backdrop", "solid" if self.solid else None)
        back.connect("button-release-event", self.backdrop_tap)
        win.add(back)
        self.build(back)
        win.connect("key-press-event", self.key)
        win.show_all()

    def build(self, back):
        sheet = ui.vbox(10, "sheet")
        width = min(self.width, self.screen[0] - 12)
        sheet.set_size_request(width, -1)
        self.fill(sheet)
        catcher = Gtk.EventBox()        # taps on the sheet don't reach the backdrop
        catcher.set_visible_window(False)
        catcher.connect("button-release-event", lambda *_a: True)
        catcher.add(sheet)
        view = ui.scrolled(catcher)
        view.set_propagate_natural_height(True)
        view.set_propagate_natural_width(True)
        view.set_halign(self.align[0])
        view.set_valign(self.align[1])
        view.set_margin_top(6)
        view.set_margin_bottom(6)
        view.set_margin_start(6)
        view.set_margin_end(6)
        back.add(view)

    def backdrop_tap(self, widget, event):
        if event.window == widget.get_window():
            self.shell.close_overlay()
        return True

    def key(self, _w, event):
        if event.keyval == Gdk.KEY_Escape:
            self.shell.close_overlay()
            return True
        return False

    def destroy(self):
        self.window.destroy()

    def run_and_close(self, *cmd):
        self.shell.close_overlay()
        core.spawn(*cmd)


class Quick(Overlay):
    align = (Gtk.Align.END, Gtk.Align.START)
    width = 430

    def fill(self, box):
        st = self.shell.status

        radios = ui.hbox(8)
        radios.set_homogeneous(True)
        self.wifi = self.radio_tile("wifi", "Wi-Fi", self.toggle_wifi, "wifi")
        self.bt = self.radio_tile("bluetooth", "Bluetooth", self.toggle_bt, "network")
        radios.add(self.wifi[0])
        radios.add(self.bt[0])
        box.pack_start(radios, False, False, 0)
        self.bt_on = bluetooth.state()

        level = core.get_brightness()
        if level is not None:
            line = ui.hbox(10)
            bright = ui.icon("brightness")
            bright.set_size_request(48, -1)
            line.pack_start(bright, False, False, 0)
            sl = ui.slider(5, 100, level, lambda v: ui.background(lambda: core.set_brightness(v)))
            sl.get_accessible().set_name("Brightness")
            line.pack_start(sl, True, True, 0)
            box.pack_start(line, False, False, 0)

        self.volume = None
        if st.volume is not None:
            line = ui.hbox(10)
            self.mute = ui.button(None, self.toggle_mute, "flat", "round", icon_name="volume-high", tip="Mute")
            line.pack_start(self.mute, False, False, 0)
            self.volume = ui.slider(0, 100, min(st.volume[0], 100),
                                    lambda v: ui.background(lambda: core.set_volume(v)))
            self.volume.get_accessible().set_name("Volume")
            line.pack_start(self.volume, True, True, 0)
            box.pack_start(line, False, False, 0)

        grid = Gtk.Grid(row_spacing=8, column_spacing=8, column_homogeneous=True)
        tiles = []
        dconf = core.read_conf(core.DISPLAY_CONF)
        if dconf.get("PANEL"):
            auto = dconf.get("AUTO", "1") == "1"
            tiles.append(("rotate" if auto else "rotate-lock", "Auto-rotate", auto,
                          lambda: self.run_and_close("termos-rotate", "lock" if auto else "auto")))
            tiles.append(("rotate", "Rotate 90°", False, lambda: self.run_and_close("termos-rotate", "cw")))
        tiles += [
            ("coffee", "Keep awake", self.shell.keep_awake(), self.toggle_awake),
            ("keyboard", "Keyboard", False, lambda: self.run_and_close("termos-osk", "toggle")),
            ("camera", "Screenshot", False, lambda: self.run_and_close("termos-screenshot", "full")),
            ("lock", "Lock", False, lambda: self.run_and_close("termos-lock-now")),
        ]
        for i, (name, text, on, action) in enumerate(tiles):
            b = ui.classes(Gtk.Button(), "tile", "on" if on else None)
            inner = ui.vbox(4)
            inner.set_valign(Gtk.Align.CENTER)
            inner.pack_start(ui.icon(name), False, False, 0)
            inner.pack_start(ui.label(text, xalign=0.5, ellipsize=True), False, False, 0)
            b.add(inner)
            b.connect("clicked", lambda _b, fn=action: fn())
            grid.attach(b, i % 3, i // 3, 1, 1)
        box.pack_start(grid, False, False, 0)

        box.pack_start(ui.label("Power mode", "heading"), False, False, 0)
        modes = ui.hbox(8)
        modes.set_homogeneous(True)
        self.modes = {}
        for key, text in (("power-saver", "Saver"), ("balanced", "Balanced"), ("performance", "Performance")):
            b = ui.button(text, lambda k=key: self.set_mode(k), "mode")
            self.modes[key] = b
            modes.add(b)
        box.pack_start(modes, False, False, 0)
        self.error = ui.label("", "error", "sub", wrap=True)
        self.error.set_no_show_all(True)
        box.pack_start(self.error, False, False, 0)

        foot = ui.hbox(6)
        self.summary = ui.label("", "sub", ellipsize=True)
        foot.pack_start(self.summary, True, True, 4)
        foot.pack_end(ui.button(None, lambda: self.shell.toggle("power", self.monitor), "round",
                                icon_name="power", tip="Power"), False, False, 0)
        foot.pack_end(ui.button(None, lambda: self.shell.launch("termos-settings"), "round",
                                icon_name="settings", tip="Settings"), False, False, 0)
        box.pack_start(foot, False, False, 0)
        self.show_mode()
        st.listen(box, self.update)
        self.update()

    def radio_tile(self, name, title, toggle, page):
        box = ui.hbox(2)
        main = ui.classes(Gtk.Button(), "wide")
        inner = ui.hbox(9)
        inner.pack_start(ui.icon(name), False, False, 0)
        words = ui.vbox(0)
        words.set_valign(Gtk.Align.CENTER)
        words.pack_start(ui.label(title), False, False, 0)
        sub = ui.label("", "sub", ellipsize=True)
        sub.set_width_chars(4)
        sub.set_max_width_chars(9)
        words.pack_start(sub, False, False, 0)
        inner.pack_start(words, True, True, 0)
        main.add(inner)
        main.connect("clicked", lambda _b: toggle())
        box.pack_start(main, True, True, 0)
        more = ui.button(None, lambda: self.shell.launch("termos-settings", page), "flat",
                         icon_name="right", tip=f"{title} settings")
        ui.classes(more, "more")
        more.set_size_request(40, -1)
        box.pack_start(more, False, False, 0)
        return box, main, sub

    def update(self):
        st = self.shell.status
        net = st.net
        _box, main, sub = self.wifi
        main.set_sensitive(net["wifi"] is not None)
        ui.set_class(main, "on", bool(net["wifi"]))
        sub.set_text("No adapter" if net["wifi"] is None else "Off" if not net["wifi"]
                     else net["name"] if net["kind"] == "wifi" else "Not joined")
        _box, main, sub = self.bt
        main.set_sensitive(self.bt_on is not None)
        ui.set_class(main, "on", bool(self.bt_on))
        sub.set_text("No adapter" if self.bt_on is None else "On" if self.bt_on else "Off")

        if self.volume is not None and st.volume is not None:
            percent, muted = st.volume
            # don't fight the finger that is dragging it
            if not self.volume.get_state_flags() & Gtk.StateFlags.ACTIVE:
                ui.set_quietly(self.volume, min(percent, 100))
            self.mute.get_child().get_children()[0].set_text(icons.volume_glyph(percent, muted))

        parts = []
        if st.battery:
            parts.append(f"Battery {st.battery['percent']}%" + (", charging" if st.battery["charging"] else ""))
        if net["ip"]:
            parts.append(net["ip"])
        self.summary.set_text("  ·  ".join(parts))

    def show_mode(self):
        pconf = core.read_conf(core.POWER_CONF)
        now = pconf.get("ACTIVE", pconf.get("PROFILE", "balanced"))
        for key, b in self.modes.items():
            ui.set_class(b, "on", key == now)

    def fail(self, text):
        self.error.set_text(text)
        self.error.show()

    def set_mode(self, key):
        def done(result):
            if self.shell.overlay is not self:
                return
            if result and result[0]:
                self.show_mode()
            else:
                self.fail("Couldn't change the power mode.")
        ui.background(lambda: core.root_helper("power", "set", key), done)

    def toggle_wifi(self):
        turn_on = not self.shell.status.net["wifi"]
        if netinfo.set_wifi(turn_on):
            self.shell.status.net = dict(self.shell.status.net, wifi=turn_on)
            self.update()
            GLib.timeout_add(1500, lambda: (self.shell.status.poll(), False)[1])

    def toggle_bt(self):
        turn_on = not self.bt_on

        def done(result):
            if self.shell.overlay is not self:
                return
            self.bt_on = bluetooth.state()
            if not result:
                self.fail("Couldn't switch Bluetooth.")
            self.update()
        ui.background(lambda: bluetooth.turn(turn_on), done)

    def toggle_mute(self):
        st = self.shell.status.volume
        if st:
            ui.background(lambda: core.set_muted(not st[1]))

    def toggle_awake(self):
        self.shell.set_keep_awake(not self.shell.keep_awake())
        self.shell.close_overlay()


class Power(Overlay):
    width = 360

    def fill(self, box):
        self.box = box
        self.main()

    def main(self):
        ui.clear(self.box)
        self.box.pack_start(ui.label("Power", "title"), False, False, 2)
        for name, text, action in (
            ("lock", "Lock", lambda: self.run_and_close("termos-lock-now")),
            ("sleep", "Sleep", lambda: self.run_and_close("systemctl", "suspend")),
            ("restart", "Restart", lambda: self.ask(
                "Restart now?", "Open apps and connections will close.", "Restart",
                ("systemctl", "reboot"))),
            ("power", "Shut down", lambda: self.ask(
                "Shut down now?", "Open apps and connections will close.", "Shut down",
                ("systemctl", "poweroff"))),
            ("refresh", "Restart desktop", lambda: self.ask(
                "Restart the desktop?", "Open apps will close and you'll need your PIN.", "Restart desktop",
                ("labwc", "--exit"))),
        ):
            self.box.pack_start(ui.button(text, action, "big", icon_name=name), False, False, 0)
        self.box.pack_start(ui.button("Cancel", self.shell.close_overlay, "flat"), False, False, 0)
        self.box.show_all()

    def ask(self, title, body, yes, cmd):
        ui.clear(self.box)
        self.box.pack_start(ui.label(title, "title", wrap=True), False, False, 2)
        self.box.pack_start(ui.label(body, "sub", wrap=True), False, False, 2)
        line = ui.hbox(8)
        line.set_homogeneous(True)
        # Cancel sits where the button just tapped was, so a double tap can't confirm
        line.add(ui.button("Cancel", self.main, "big"))
        line.add(ui.button(yes, lambda: self.run_and_close(*cmd), "big", "danger"))
        self.box.pack_start(line, False, False, 4)
        self.box.show_all()


class Windows(Overlay):
    width = 560
    align = (Gtk.Align.CENTER, Gtk.Align.START)

    def fill(self, box):
        head = ui.hbox(8)
        head.pack_start(ui.label("Open windows", "title"), True, True, 4)
        head.pack_end(ui.button("Home", self.go_home, icon_name="home"), False, False, 0)
        box.pack_start(head, False, False, 0)
        self.list = ui.vbox(6)
        box.pack_start(self.list, False, False, 0)
        self.refresh()

    def go_home(self):
        self.shell.close_overlay()
        if self.shell.windows and not self.shell.windows.home_visible():
            self.shell.windows.toggle_desktop()

    def refresh(self):
        ui.clear(self.list)
        windows = self.shell.windows.all() if self.shell.windows else []
        if not windows:
            self.list.pack_start(ui.label("No windows are open.", "sub"), False, False, 12)
        for w in windows:
            line = ui.hbox(6)
            b = ui.classes(Gtk.Button(), "wide", "on" if w.active and not w.minimized else None)
            inner = ui.hbox(12)
            inner.pack_start(apps.window_image(w.app_id, 34), False, False, 0)
            words = ui.vbox(0)
            words.set_valign(Gtk.Align.CENTER)
            name = ui.label(apps.window_name(w.app_id), ellipsize=True)
            words.pack_start(name, False, False, 0)
            title = ui.label(w.title + ("  (minimized)" if w.minimized else ""), "sub", ellipsize=True)
            title.set_max_width_chars(40)
            words.pack_start(title, False, False, 0)
            inner.pack_start(words, True, True, 0)
            b.add(inner)
            b.connect("clicked", lambda _b, w=w: (self.shell.close_overlay(), w.activate()))
            line.pack_start(b, True, True, 0)
            line.pack_start(ui.button(None, w.close, "round", icon_name="close", tip="Close window"),
                            False, False, 0)
            self.list.pack_start(line, False, False, 0)
        self.list.show_all()


class Launcher(Overlay):
    solid = True
    keys = surface.Keys.EXCLUSIVE      # so typing searches straight away

    def build(self, back):
        box = ui.vbox(10, "launcher")
        box.set_border_width(10)
        top = ui.hbox(8)
        self.search = Gtk.SearchEntry(placeholder_text="Search apps")
        self.search.connect("search-changed", self.filter_changed)
        self.search.connect("stop-search", lambda _e: self.shell.close_overlay())
        top.pack_start(self.search, True, True, 0)
        top.pack_start(ui.button(None, lambda: self.shell.toggle("power", self.monitor), "round",
                                 icon_name="power", tip="Power"), False, False, 0)
        top.pack_start(ui.button(None, self.shell.close_overlay, "round",
                                 icon_name="close", tip="Close"), False, False, 0)
        box.pack_start(ui.Clamp(top, 640), False, False, 4)

        width = self.screen[0]
        tile = 120 if width >= 700 else 100
        icon_size = 64 if min(self.screen) >= 600 else 48
        self.flow = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, homogeneous=True,
                                column_spacing=8, row_spacing=10)
        self.flow.set_valign(Gtk.Align.START)
        per_line = max(2, min((width - 24) // (tile + 8), 8))
        self.flow.set_max_children_per_line(per_line)
        self.flow.set_min_children_per_line(2)
        for app in apps.installed():
            b = ui.classes(Gtk.Button(), "app")
            b.set_size_request(tile, -1)
            inner = ui.vbox(6)
            inner.pack_start(apps.image(app, icon_size), False, False, 0)
            name = ui.label(app.get_display_name(), xalign=0.5, wrap=True, ellipsize=True)
            name.set_lines(2)
            name.set_width_chars(11)
            name.set_max_width_chars(13)
            name.set_justify(Gtk.Justification.CENTER)
            inner.pack_start(name, False, False, 0)
            b.add(inner)
            b.connect("clicked", lambda _b, a=app: self.launch(a))
            child = Gtk.FlowBoxChild()
            child.set_can_focus(False)
            child.add(b)
            child.app = app
            child.words = " ".join(filter(None, (app.get_display_name(), app.get_executable(),
                                                 app.get_description()))).lower()
            self.flow.add(child)
        self.flow.set_filter_func(lambda child: self.matches(child))
        box.pack_start(ui.scrolled(self.flow), True, True, 0)
        self.empty = ui.label("No apps match.", "sub", xalign=0.5)
        self.empty.set_no_show_all(True)
        box.pack_start(self.empty, False, False, 8)
        back.add(box)
        GLib.idle_add(lambda: (self.shell.overlay is self and self.search.grab_focus(), False)[1])

    def backdrop_tap(self, _w, _event):
        return False

    def key(self, window, event):
        if event.keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter) and self.search.has_focus():
            self.launch_first(self.search)
            return True
        return super().key(window, event)

    def matches(self, child):
        return all(word in child.words for word in self.search.get_text().lower().split())

    def filter_changed(self, _e):
        self.flow.invalidate_filter()
        self.empty.set_visible(not any(self.matches(c) for c in self.flow.get_children()))

    def launch_first(self, _e):
        for child in self.flow.get_children():
            if self.matches(child):
                self.launch(child.app)
                return

    def launch(self, app):
        self.shell.close_overlay()
        apps.launch(app)


KINDS = {"quick": Quick, "power": Power, "windows": Windows, "apps": Launcher}
