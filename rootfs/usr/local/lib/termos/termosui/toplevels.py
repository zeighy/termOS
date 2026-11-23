"""The open windows, through wlr-foreign-toplevel-management.

GTK can't speak this protocol and there is no packaged binding for it, so this
is a very small Wayland client of its own: it only needs a handful of messages,
none of which carry file descriptors.
"""
import os
import socket
import struct
import sys
import traceback

from gi.repository import GLib

_MANAGER = "zwlr_foreign_toplevel_manager_v1"
_DISPLAY, _REGISTRY = 1, 2
_MINIMIZED, _ACTIVATED = 1, 2


def _string(text):
    raw = text.encode() + b"\0"
    return struct.pack("=I", len(raw)) + raw + b"\0" * (-len(raw) % 4)


def _read_string(body):
    size = struct.unpack_from("=I", body)[0]
    return body[4:4 + max(size - 1, 0)].decode(errors="replace")


class Window:
    def __init__(self, owner, oid):
        self.owner = owner
        self.oid = oid
        self.title = ""
        self.app_id = ""
        self.active = False
        self.minimized = False
        self.ready = False

    def activate(self):
        if self.owner.seat:
            self.owner.send(self.oid, 3)        # unset_minimized
            self.owner.send(self.oid, 4, struct.pack("=I", self.owner.seat))

    def minimize(self):
        self.owner.send(self.oid, 2)

    def restore(self):
        self.owner.send(self.oid, 3)

    def close(self):
        self.owner.send(self.oid, 5)


class Toplevels:
    def __init__(self, on_change, on_lost=None):
        self.on_change = on_change
        self.on_lost = on_lost
        self.windows = {}
        self.manager = self.seat = 0
        self.next_id = 3
        self.buf = b""
        self.queued = 0
        self.hidden = []
        path = os.path.join(os.environ["XDG_RUNTIME_DIR"], os.environ.get("WAYLAND_DISPLAY", "wayland-0"))
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.connect(path)
        self.send(_DISPLAY, 1, struct.pack("=I", _REGISTRY))    # get_registry
        GLib.unix_fd_add_full(GLib.PRIORITY_DEFAULT, self.sock.fileno(),
                              GLib.IOCondition.IN | GLib.IOCondition.HUP | GLib.IOCondition.ERR,
                              self.readable)

    def send(self, oid, opcode, body=b""):
        try:
            self.sock.sendall(struct.pack("=II", oid, (8 + len(body)) << 16 | opcode) + body)
        except OSError:
            pass    # the read side notices a lost compositor

    def bind(self, name, interface, version):
        oid = self.next_id
        self.next_id += 1
        self.send(_REGISTRY, 0, struct.pack("=I", name) + _string(interface) + struct.pack("=II", version, oid))
        return oid

    def readable(self, _fd, _cond, *_a):
        try:
            data = self.sock.recv(65536)
        except OSError:
            data = b""
        if not data:
            return self.lost()
        self.buf += data
        while len(self.buf) >= 8:
            oid, word = struct.unpack_from("=II", self.buf)
            size = word >> 16
            if size < 8:
                return self.lost()
            if len(self.buf) < size:
                break
            body, self.buf = self.buf[8:size], self.buf[size:]
            try:
                self.event(oid, word & 0xffff, body)
            except (struct.error, IndexError):
                traceback.print_exc()
        return True

    def lost(self):
        self.sock.close()
        if self.on_lost:
            self.on_lost()
        return False

    def event(self, oid, op, body):
        if oid == _DISPLAY and op == 0:
            print("termos-shell: Wayland error:", _read_string(body[8:]), file=sys.stderr)
        elif oid == _REGISTRY and op == 0:
            name = struct.unpack_from("=I", body)[0]
            interface = _read_string(body[4:])
            if interface == "wl_seat" and not self.seat:
                self.seat = self.bind(name, interface, 1)
            elif interface == _MANAGER:
                self.manager = self.bind(name, interface, 1)
        elif oid == self.manager and op == 0:
            new = struct.unpack("=I", body)[0]
            self.windows[new] = Window(self, new)
        elif oid in self.windows:
            win = self.windows[oid]
            if op == 0:
                win.title = _read_string(body)
            elif op == 1:
                win.app_id = _read_string(body)
            elif op == 4:
                count = struct.unpack_from("=I", body)[0] // 4
                states = struct.unpack_from(f"={count}I", body, 4)
                win.active, win.minimized = _ACTIVATED in states, _MINIMIZED in states
            elif op == 5:
                win.ready = True
                self.changed()
            elif op == 6:
                del self.windows[oid]
                self.send(oid, 7)
                self.changed()

    def changed(self):
        if not self.queued:
            self.queued = GLib.timeout_add(40, self.flush)

    def flush(self):
        self.queued = 0
        self.on_change()
        return False

    def all(self):
        return [w for w in self.windows.values() if w.ready]

    def active(self):
        return next((w for w in self.all() if w.active and not w.minimized), None)

    def home_visible(self):
        return all(w.minimized for w in self.all())

    def toggle_desktop(self):
        showing = [w for w in self.all() if not w.minimized]
        if showing:
            showing.sort(key=lambda w: w.active)    # the active one comes back on top
            self.hidden = [w.oid for w in showing]
            for w in showing:
                w.minimize()
            return
        back = [self.windows[i] for i in self.hidden if i in self.windows]
        self.hidden = []
        for w in back[:-1]:
            w.restore()
        if back:
            back[-1].activate()
