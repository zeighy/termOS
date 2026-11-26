"""The home screen: your machines, on the desktop."""
import os
import time

from gi.repository import GLib, Gtk

from .. import core, hosts, ui
from . import surface

STATE_TEXT = {True: ("Online", "good"), False: ("Offline", "error"), None: ("", None)}
KIND_ICON = {"ssh": "server", "remote": "remote"}


class Machines:
    """The list and its online state, shared by the home screens of all monitors."""

    def __init__(self, shell):
        self.shell = shell
        self.items = []
        self.online = {}
        self.meta = {}
        self.listeners = []
        self.busy = False
        self.loaded = False
        self.signature = None
        self.last = 0
        GLib.timeout_add_seconds(5, self.tick)

    def watched(self):
        # no network chatter behind apps or the lock screen
        return (self.listeners and (not self.shell.windows or self.shell.windows.home_visible())
                and not os.path.exists(os.path.join(core.RUN_DIR, "lock-wanted")))

    def stamp(self):
        data_home = os.environ.get("XDG_DATA_HOME") or os.path.join(core.HOME, ".local", "share")
        out = []
        for path in (hosts.SSH_CONFIG, hosts.META, os.path.join(data_home, "remmina")):
            try:
                out.append(os.stat(path).st_mtime_ns)
            except OSError:
                out.append(0)
        return out

    def tick(self):
        if self.watched():
            stamp = self.stamp()
            if stamp != self.signature or time.monotonic() - self.last > 60:
                self.refresh()
        return True

    def refresh(self):
        if self.busy:
            return
        self.busy = True
        self.signature = self.stamp()
        self.last = time.monotonic()
        ui.background(lambda: (hosts.machines(), hosts.all_meta()), self.got_items)

    def got_items(self, result):
        items, meta = result or ([], {})

        def used(m):
            key = hosts.machine_key(m) if m["kind"] == "remote" else m["name"]
            return meta.get(key, {}).get("used", 0)
        for m in items:
            m["used"] = used(m)
        items.sort(key=lambda m: -m["used"])
        self.items, self.meta, self.loaded = items, meta, True
        self.emit()
        ui.background(lambda: hosts.probe(items), self.got_online)

    def got_online(self, result):
        self.busy = False
        self.online = result or {}
        self.emit()

    def emit(self):
        for fn in list(self.listeners):
            fn()


class Home:
    def __init__(self, shell, monitor):
        self.shell = shell
        self.monitor = monitor
        win = surface.window("home", surface.Layer.BOTTOM, surface.ALL, monitor)
        self.window = win
        self.drawn = None
        width = surface.monitor_size(monitor)[0]

        page = ui.vbox(14)
        page.set_border_width(20)
        head = ui.hbox(10)
        words = ui.vbox(2)
        words.pack_start(ui.label("Your machines", "greeting", ellipsize=True), False, False, 0)
        self.device = ui.label("", "sub", ellipsize=True)
        words.pack_start(self.device, False, False, 0)
        head.pack_start(words, True, True, 0)
        roomy = width >= 600
        head.pack_end(ui.button("Add host" if roomy else None, lambda: shell.launch("termos-ssh", "add"),
                                "primary", icon_name="plus", tip="Add host"), False, False, 0)
        refresh = ui.button(None, shell.machines.refresh, "round", icon_name="refresh", tip="Check again")
        head.pack_end(refresh, False, False, 0)
        for child in head.get_children():
            child.set_valign(Gtk.Align.CENTER)
        page.pack_start(head, False, False, 0)
        self.search = Gtk.SearchEntry(placeholder_text="Filter machines")
        self.search.connect("search-changed", lambda _e: self.update())
        self.search.set_no_show_all(True)
        page.pack_start(self.search, False, False, 0)
        self.body = ui.vbox(10)
        page.pack_start(self.body, False, False, 0)
        win.add(ui.scrolled(ui.Clamp(page, 1100)))
        self.columns = max(1, min((width - 40) // 290, 3))

        shell.machines.listeners.append(self.update)
        win.connect("destroy", lambda _w: shell.machines.listeners.remove(self.update))
        shell.status.listen(win, self.update)
        win.show_all()
        self.update()

    def update(self):
        st = self.shell.status
        bits = [core.hostname()]
        if st.net["kind"] == "none":
            bits.append("Not connected to a network")
        else:
            bits += [b for b in (st.net["name"], st.net["ip"]) if b]
        self.device.set_text("   ·   ".join(bits))

        m = self.shell.machines
        if not m.loaded:
            return
        query = self.search.get_text().strip().lower()
        self.search.set_visible(len(m.items) >= 6 or bool(query))
        shown = [x for x in m.items if not query or all(
            w in " ".join(str(x.get(k) or "") for k in ("name", "host", "user", "protocol")).lower()
            for w in query.split())]
        cards = [self.card_state(x) for x in shown]
        if (cards, query) == self.drawn:
            return
        self.drawn = (cards, query)
        ui.clear(self.body)
        if not m.items:
            box = ui.empty_state(
                "server", "No machines yet",
                "Add an SSH host, or save an RDP or VNC connection in Remote Desktop. "
                "They appear here, one tap away.",
                ui.button("Add SSH host", lambda: self.shell.launch("termos-ssh", "add"), "primary"),
                ui.button("Remote Desktop", lambda: self.shell.launch("remmina")))
            ui.classes(box, "panelcard")
            self.body.pack_start(box, False, False, 10)
        elif not shown:
            self.body.pack_start(ui.label("No machines match your filter.", "sub", xalign=0.5),
                                 False, False, 16)
        else:
            flow = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, homogeneous=True,
                               column_spacing=10, row_spacing=10)
            flow.set_max_children_per_line(self.columns)
            flow.set_min_children_per_line(self.columns)
            for machine, state in zip(shown, cards):
                child = Gtk.FlowBoxChild()
                child.set_can_focus(False)
                child.add(self.card(machine, state))
                flow.add(child)
            self.body.pack_start(flow, False, False, 0)
        self.body.show_all()

    def card_state(self, machine):
        key = hosts.machine_key(machine)
        live = self.shell.status.connections.get(machine["name"]) if machine["kind"] != "remote" else None
        if live == "connected":
            state = ("Connected", "good")
        elif live == "reconnecting":
            state = ("Reconnecting", "warn")
        elif key not in self.shell.machines.online:
            state = ("Checking", None)
        else:
            state = STATE_TEXT[self.shell.machines.online[key]]
        if machine["kind"] == "remote":
            detail = " ".join(x for x in (machine["protocol"], machine["host"]) if x)
        else:
            detail = (machine["user"] + "@" if machine["user"] else "") + machine["host"]
            if machine["port"] and machine["port"] != "22":
                detail += ":" + machine["port"]
        return (key, machine["name"], detail, state, hosts.ago(machine.get("used")))

    def card(self, machine, card_state):
        _key, name, detail, (word, css), used = card_state
        b = ui.classes(Gtk.Button(), "machine")
        line = ui.hbox(14)
        line.pack_start(ui.icon(KIND_ICON[machine["kind"]], "accent"), False, False, 0)
        words = ui.vbox(3)
        words.set_valign(Gtk.Align.CENTER)
        for text, cls in ((name, "name"), (detail, "sub")):
            lb = ui.label(text, cls, ellipsize=True)
            lb.set_max_width_chars(24)
            words.pack_start(lb, False, False, 0)
        state = ui.hbox(6)
        if word:
            state.pack_start(ui.label("●", "dot", css), False, False, 0)
        tail = ui.label("  ·  ".join(x for x in (word, used) if x) or " ", "sub", ellipsize=True)
        state.pack_start(tail, False, False, 0)
        words.pack_start(state, False, False, 0)
        line.pack_start(words, True, True, 0)
        b.add(line)
        b.get_accessible().set_name(f"Connect to {name}")
        b.connect("clicked", lambda _b: hosts.connect(machine))
        return b

    def destroy(self):
        self.window.destroy()
