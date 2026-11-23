"""Live status shown by the panel and Quick Settings."""
import subprocess

from gi.repository import GLib

from .. import core, hosts, netinfo, ui


class Status:
    def __init__(self):
        self.listeners = []
        self.battery = None
        self.net = {"kind": "none", "name": "", "strength": 0, "wifi": None, "ip": ""}
        self.volume = None
        self.connections = {}
        self.sound = None
        self.volume_busy = self.volume_again = False
        self.poll()
        self.watch_sound()
        GLib.timeout_add_seconds(5, self.poll)

    def poll(self):
        new = (core.battery(), netinfo.status(), hosts.connections())
        if new != (self.battery, self.net, self.connections):
            self.battery, self.net, self.connections = new
            self.emit()
        return True

    def emit(self):
        for fn in list(self.listeners):
            fn()

    def listen(self, widget, fn):
        self.listeners.append(fn)
        widget.connect("destroy", lambda _w: fn in self.listeners and self.listeners.remove(fn))

    # ---- sound: pactl tells us when something changes, so there is no polling
    def watch_sound(self):
        try:
            self.sound = subprocess.Popen(["pactl", "subscribe"], stdout=subprocess.PIPE,
                                          stderr=subprocess.DEVNULL, bufsize=0)
        except OSError:
            return False
        GLib.io_add_watch(self.sound.stdout.fileno(), GLib.PRIORITY_DEFAULT,
                          GLib.IOCondition.IN | GLib.IOCondition.HUP, self.sound_event)
        self.read_volume()
        return False

    def sound_event(self, _fd, cond):
        data = self.sound.stdout.read(4096) if cond & GLib.IOCondition.IN else b""
        if not data:
            self.sound.stdout.close()
            self.sound.wait()
            GLib.timeout_add_seconds(5, self.watch_sound)
            return False
        if b"sink #" in data or b"server" in data:
            self.read_volume()
        return True

    def read_volume(self):
        if self.volume_busy:
            self.volume_again = True
            return
        self.volume_busy = True
        ui.background(core.get_volume, self.got_volume)

    def got_volume(self, value):
        self.volume_busy = False
        if value != self.volume:
            self.volume = value
            self.emit()
        if self.volume_again:
            self.volume_again = False
            self.read_volume()
