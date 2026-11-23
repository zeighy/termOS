"""Bluetooth on and off.

"Off" powers the adapter down instead of blocking the radio with rfkill: a
blocked radio can't be turned on by the browser, so its "Turn on Bluetooth"
button (phone passkeys by QR code) would hang. BlueZ powers adapters up at boot
and after sleep, so the choice is saved and re-applied then.
"""
import glob
import time

from gi.repository import Gio, GLib

from . import core

BLUEZ = "org.bluez"
ADAPTER = "org.bluez.Adapter1"


def _radios():
    return [d for d in glob.glob("/sys/class/rfkill/*") if core.slurp(f"{d}/type") == "bluetooth"]


def blocked():
    return any("1" in (core.slurp(f"{d}/soft"), core.slurp(f"{d}/hard")) for d in _radios())


def _call(path, iface, method, params=None):
    bus = Gio.bus_get_sync(Gio.BusType.SYSTEM, None)
    # NO_AUTO_START: just asking shouldn't start bluetoothd
    return bus.call_sync(BLUEZ, path, iface, method, params, None,
                         Gio.DBusCallFlags.NO_AUTO_START, 4000, None)


def adapters():
    """[(object path, powered)]"""
    try:
        objects = _call("/", "org.freedesktop.DBus.ObjectManager", "GetManagedObjects").unpack()[0]
    except GLib.Error:
        return []
    return [(path, bool(ifs[ADAPTER].get("Powered"))) for path, ifs in objects.items() if ADAPTER in ifs]


def state():
    """True on, False off, None no adapter."""
    if blocked():
        return False
    found = adapters()
    if found:
        return any(powered for _path, powered in found)
    return False if _radios() else None


def _set_power(path, on):
    try:
        _call(path, "org.freedesktop.DBus.Properties", "Set",
              GLib.Variant("(ssv)", (ADAPTER, "Powered", GLib.Variant("b", on))))
        return True
    except GLib.Error:
        return False        # BlueZ answers "busy" just after an unblock


def turn(on):
    """Switch and remember it. True if it worked. Blocks: call it off the UI thread."""
    core.write_conf("BLUETOOTH", "1" if on else "0")
    if on and blocked():
        core.run("rfkill", "unblock", "bluetooth")
    for _ in range(25):
        found = adapters()
        if found and all(powered == on for _path, powered in found):
            return True
        for path, powered in found:
            if powered != on:
                _set_power(path, on)
        time.sleep(0.2)
    return False


def restore():
    """At login and after sleep."""
    if not _radios() and not adapters():
        return
    was_blocked = blocked()
    if was_blocked:
        if "BLUETOOTH" not in core.read_conf():
            core.write_conf("BLUETOOTH", "0")       # switched off by an older termOS
        core.run("rfkill", "unblock", "bluetooth")
    if core.setting_on("BLUETOOTH"):
        return
    # BlueZ may power the adapter up a moment after an unblock or a resume
    quiet = 0
    for _ in range(40):
        on = [path for path, powered in adapters() if powered]
        for path in on:
            _set_power(path, False)
        quiet = 0 if on else quiet + 1
        if quiet >= 15:
            return
        time.sleep(0.2)
