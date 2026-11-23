"""Pieces shared by Settings and the Welcome app: Wi-Fi, time zone, Tailscale, PIN."""
import json
import os
import zoneinfo

from gi.repository import GLib, Gtk

from . import core, icons, netinfo, secrets_client as secret, ui


def secret_entry(hint, digits=False):
    e = Gtk.Entry(placeholder_text=hint, visibility=False)
    e.set_input_purpose(Gtk.InputPurpose.PIN if digits else Gtk.InputPurpose.PASSWORD)
    if digits:
        e.set_max_length(10)
    e.set_width_chars(8)
    return e


class WifiList(Gtk.Box):
    """Wi-Fi switch and networks. The password box opens inside the list, where
    the on-screen keyboard can't cover it."""

    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.open = None        # ssid of the expanded row
        self.working = None
        self.error = ("", "")
        self.drawn = None
        self.ticks = 0
        self.entry = None
        self.alive = True
        self.connect("destroy", self.gone)
        top = ui.hbox(12)
        top.pack_start(ui.label("Wi-Fi", "row-label"), True, True, 0)
        self.state = ui.label("", "sub")
        top.pack_start(self.state, False, False, 0)
        self.reverting = False
        self.power = ui.switch(False, self.switched)
        top.pack_start(self.power, False, False, 0)
        self.pack_start(top, False, False, 8)
        self.list = ui.vbox(4)
        self.pack_start(self.list, False, False, 0)
        netinfo.rescan()
        self.refresh()
        ui.every(self, 3, self.tick)

    def gone(self, _w):
        self.alive = False

    def tick(self):
        self.ticks += 1
        if self.ticks % 5 == 0:
            netinfo.rescan()
        self.refresh()

    def switched(self, on):
        if self.reverting:
            return True
        if not netinfo.set_wifi(on):
            return False
        GLib.timeout_add(1200, lambda: (self.alive and self.refresh(), False)[1])
        return True

    def refresh(self):
        if not self.alive:
            return
        enabled = netinfo.status()["wifi"]
        self.power.set_sensitive(enabled is not None)
        self.reverting = True
        self.power.set_active(bool(enabled))
        self.reverting = False
        self.state.set_text("No Wi-Fi adapter" if enabled is None else "" if enabled else "Off")
        nets = netinfo.networks()[:30] if enabled else []
        shape = ([(n["ssid"], n["active"], n["saved"], min(n["strength"] // 25, 3)) for n in nets],
                 self.open, self.working, self.error, enabled)
        if shape == self.drawn:
            return
        # while a password is being typed the list stays put
        if self.entry and self.drawn and shape[1:] == self.drawn[1:]:
            return
        self.drawn = shape
        self.entry = None
        ui.clear(self.list)
        for net in nets:
            self.list.pack_start(self.network(net), False, False, 0)
        if enabled and not nets:
            self.list.pack_start(ui.label("Looking for networks…", "sub"), False, False, 10)
        self.list.show_all()
        if self.entry:
            self.entry.grab_focus()

    def network(self, net):
        box = ui.vbox(6)
        name = net["ssid"]
        b = ui.classes(Gtk.Button(), "flat")
        line = ui.hbox(12)
        sig = ui.classes(Gtk.Label(label=icons.wifi_glyph(net["strength"])), "icon",
                         "accent" if net["active"] else None)
        line.pack_start(sig, False, False, 0)
        words = ui.vbox(0)
        words.set_valign(Gtk.Align.CENTER)
        words.pack_start(ui.label(name, "row-label", ellipsize=True), False, False, 0)
        sub, cls = "", "sub"
        if self.working == name:
            sub = "Connecting…"
        elif self.error[0] == name:
            sub, cls = self.error[1], "error"
        elif net["active"]:
            sub = "Connected"
        elif net["saved"]:
            sub = "Saved"
        if sub:
            words.pack_start(ui.label(sub, cls, "sub", wrap=True), False, False, 0)
        line.pack_start(words, True, True, 0)
        if net["security"] != "open":
            line.pack_end(ui.icon("lock", "sub"), False, False, 0)
        b.add(line)
        b.connect("clicked", lambda _b: self.tapped(net))
        box.pack_start(b, False, False, 0)
        if self.open != name:
            return box

        line = ui.hbox(8)
        line.set_margin_bottom(8)
        failed = self.error[0] == name
        wants_password = net["security"] in ("psk", "sae") and not net["active"] and (not net["saved"] or failed)
        if net["active"]:
            line.pack_start(ui.button("Disconnect", lambda: self.act(netinfo.disconnect)), True, True, 0)
        elif net["security"] in ("enterprise", "wep"):
            line.pack_start(ui.button("Set up in network settings",
                                      lambda: core.spawn("nm-connection-editor")), True, True, 0)
        elif wants_password:
            entry = secret_entry("Password")
            entry.connect("activate", lambda _e: self.join(net, entry.get_text()))
            self.entry = entry
            line.pack_start(entry, True, True, 0)
            line.pack_start(ui.button("Show", lambda: entry.set_visibility(not entry.get_visibility())),
                            False, False, 0)
            line.pack_start(ui.button("Join", lambda: self.join(net, entry.get_text()), "primary"),
                            False, False, 0)
        else:
            line.pack_start(ui.button("Connect", lambda: self.join(net, ""), "primary"), True, True, 0)
        if net["saved"]:
            line.pack_start(ui.button("Forget", lambda: self.act(lambda: netinfo.forget(name))), False, False, 0)
        box.pack_start(line, False, False, 0)
        return box

    def tapped(self, net):
        self.entry = None
        if self.open == net["ssid"]:
            self.open = None
        elif not net["active"] and not self.working and self.error[0] != net["ssid"] and (
                net["saved"] or net["security"] == "open"):
            self.join(net, "")      # nothing to ask, so one tap joins
            return
        else:
            self.open = net["ssid"]
        self.refresh()

    def act(self, fn):
        fn()
        self.open = self.entry = None
        self.error = ("", "")
        GLib.timeout_add(800, lambda: (self.alive and self.refresh(), False)[1])

    def join(self, net, password):
        name = net["ssid"]
        if self.working:
            return
        if password and not 8 <= len(password) <= 64 and net["security"] == "psk":
            self.entry = None
            self.error = (name, "A Wi-Fi password has at least 8 characters.")
            self.refresh()
            return
        self.working, self.open, self.entry = name, None, None
        self.error = ("", "")
        self.refresh()

        def done(problem):
            if not self.alive:
                return
            self.working = None
            self.error = (name, problem) if problem else ("", "")
            self.open = name if problem else None
            self.entry = None
            self.refresh()
        netinfo.connect(net, password, done)


def current_timezone():
    try:
        link = os.readlink("/etc/localtime")
    except OSError:
        return "UTC"
    return link.split("zoneinfo/", 1)[-1]


class TimezonePicker(Gtk.Box):
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.zones = sorted(zoneinfo.available_timezones())
        self.now = ui.label("", "row-label", wrap=True)
        self.pack_start(self.now, False, False, 6)
        self.search = Gtk.SearchEntry(placeholder_text="Type a city, e.g. Toronto")
        self.search.connect("search-changed", lambda _e: self.show_matches())
        self.pack_start(self.search, False, False, 0)
        self.matches = ui.vbox(4)
        self.pack_start(self.matches, False, False, 0)
        self.error = ui.label("", "error", wrap=True)
        self.pack_start(self.error, False, False, 0)
        self.show_current()

    def show_current(self):
        self.now.set_text(f"Time zone: {current_timezone().replace('_', ' ')}")

    def show_matches(self):
        ui.clear(self.matches)
        q = self.search.get_text().strip().lower().replace(" ", "_")
        if not q:
            return
        found = [z for z in self.zones if q in z.lower()]
        found.sort(key=lambda z: not z.lower().split("/")[-1].startswith(q))
        for zone in found[:6]:
            self.matches.pack_start(ui.button(zone.replace("_", " "), lambda z=zone: self.choose(z)),
                                    False, False, 0)
        if not found:
            self.matches.pack_start(ui.label("No time zone matches. Try the nearest big city.", "sub",
                                             wrap=True), False, False, 4)
        self.matches.show_all()

    def choose(self, zone):
        ok, err = core.root_helper("timezone", zone)
        self.error.set_text("" if ok else f"Couldn't change it: {err}")
        if ok:
            self.search.set_text("")
            ui.clear(self.matches)
            self.show_current()


class TailscaleControls(Gtk.Box):
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.alive = True
        self.connect("destroy", self.gone)
        line = ui.hbox(12)
        words = ui.vbox(2)
        words.pack_start(ui.label("Tailscale", "row-label"), False, False, 0)
        words.pack_start(ui.label("Reach your machines from any network without opening ports",
                                  "sub", wrap=True), False, False, 0)
        line.pack_start(words, True, True, 0)
        self.on = core.run("systemctl", "is-enabled", "tailscaled.service").stdout.strip() == "enabled"
        self.switch = ui.switch(self.on, self.switched)
        line.pack_start(self.switch, False, False, 0)
        self.pack_start(line, False, False, 9)
        line = ui.hbox(12)
        self.state = ui.label("", "sub", wrap=True)
        line.pack_start(self.state, True, True, 0)
        self.login = ui.button("Sign in…", lambda: core.spawn("foot", "-T", "Tailscale sign-in", "-e",
                                                              "termos-tailscale-login"))
        line.pack_start(self.login, False, False, 0)
        self.pack_start(line, False, False, 9)
        self.refresh()
        ui.every(self, 5, self.refresh)

    def gone(self, _w):
        self.alive = False

    def switched(self, on):
        self.state.set_text("Starting…" if on else "Stopping…")
        ok, err = core.root_helper("tailscale", "on" if on else "off")
        if not ok:
            self.state.set_text(f"Couldn't change Tailscale: {err}")
            return False
        self.on = on
        self.refresh()
        return True

    def refresh(self):
        self.login.set_sensitive(self.on)
        if not self.on:
            self.state.set_text("Off. Uses no resources until you turn it on.")
            return

        def read():
            try:
                return json.loads(core.run("tailscale", "status", "--json", timeout=5).stdout)
            except ValueError:
                return None

        def show(data):
            if not self.alive or not self.on:
                return
            if not data:
                self.state.set_text("Starting…")
                return
            text = {"Running": "Connected", "NeedsLogin": "Not signed in",
                    "Stopped": "Stopped"}.get(data.get("BackendState"), data.get("BackendState", "?"))
            ips = (data.get("Self") or {}).get("TailscaleIPs") or []
            if data.get("BackendState") == "Running" and ips:
                text += f"  ·  {ips[0]}"
            self.state.set_text(text)
        ui.background(read, show)


class PinChanger(Gtk.Box):
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.alive = True
        self.connect("destroy", self.gone)
        self.kind = "pin"
        self.old = secret_entry("Current PIN", True)
        self.new = secret_entry("New PIN (4 to 10 digits)", True)
        self.again = secret_entry("New PIN again", True)
        for e in (self.old, self.new, self.again):
            self.pack_start(e, False, False, 0)
            e.connect("activate", lambda _e: self.submit())
        self.note = ui.label("", "sub", wrap=True)
        self.pack_start(self.note, False, False, 0)
        line = ui.hbox(8)
        self.other = ui.button("Forgot PIN", self.swap_kind)
        line.pack_start(self.other, False, False, 0)
        self.save = ui.button("Change PIN", self.submit, "primary")
        line.pack_end(self.save, False, False, 0)
        self.pack_start(line, False, False, 4)

    def gone(self, _w):
        self.alive = False

    def swap_kind(self):
        self.kind = "password" if self.kind == "pin" else "pin"
        by_pin = self.kind == "pin"
        self.old.set_text("")
        self.old.set_max_length(10 if by_pin else 128)
        self.old.set_placeholder_text("Current PIN" if by_pin else "Account password")
        self.other.get_child().get_children()[0].set_text("Forgot PIN" if by_pin else "Use PIN")
        self.old.grab_focus()

    def say(self, text, good=False):
        self.note.set_text(text)
        ui.set_class(self.note, "error", bool(text) and not good)
        ui.set_class(self.note, "good", good)

    def submit(self):
        old, new = self.old.get_text(), self.new.get_text()
        if not old or not new:
            self.say("Fill in all three boxes.")
            return
        if new != self.again.get_text():
            self.say("The new PINs don't match.")
            return
        self.save.set_sensitive(False)
        kind = self.kind
        ui.background(lambda: secret.call("set", kind, old, new), self.done)

    def done(self, result):
        if not self.alive:
            return
        self.save.set_sensitive(True)
        code, info = result or (secret.BAD, {})
        if code == secret.OK:
            for e in (self.old, self.new, self.again):
                e.set_text("")
            self.say("PIN changed.", True)
        elif info.get("error"):
            self.say(info["error"])
        elif code == secret.WAIT:
            wait = info.get("pin_wait" if self.kind == "pin" else "password_wait", 0)
            self.say(f"Too many attempts. Try again in {secret.wait_text(wait)}.")
        elif code == secret.BAD and info.get("pin_blocked"):
            self.say("The PIN is blocked. Tap Forgot PIN and use your password.")
        elif code == secret.WRONG:
            self.say("That current PIN is wrong." if self.kind == "pin" else "That password is wrong.")
        else:
            self.say("No PIN is set. Tap Forgot PIN and use your password.")
