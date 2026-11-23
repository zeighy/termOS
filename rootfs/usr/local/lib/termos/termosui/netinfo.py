"""NetworkManager through libnm: connection state and Wi-Fi.

Wi-Fi passwords go over D-Bus, so they never show up in a process's arguments.
"""
import uuid

import gi

try:
    gi.require_version("NM", "1.0")
    from gi.repository import GLib, NM
except (ImportError, ValueError):
    NM = None

_client = None


def client():
    global _client
    if _client is None and NM:
        try:
            _client = NM.Client.new(None)
        except GLib.Error:
            return None
    return _client if _client and _client.get_nm_running() else None


def ssid_text(ap):
    raw = ap.get_ssid() if ap else None
    return NM.utils_ssid_to_utf8(raw.get_data()) if raw else ""


def wifi_device():
    c = client()
    if not c:
        return None
    found = [d for d in c.get_devices() if d.get_device_type() == NM.DeviceType.WIFI
             and d.get_state() != NM.DeviceState.UNMANAGED]
    # with a second adapter (USB dongle), the one that is in use comes first
    found.sort(key=lambda d: d.get_active_access_point() is None)
    return found[0] if found else None


def status():
    """{kind: wifi|ethernet|none, name, strength, wifi: True|False|None (no adapter), ip}"""
    info = {"kind": "none", "name": "", "strength": 0, "wifi": None, "ip": ""}
    c = client()
    if not c:
        return info
    dev = wifi_device()
    if dev:
        info["wifi"] = c.wireless_get_enabled()
    main = c.get_primary_connection()
    if not main:
        return info
    info["name"] = main.get_id() or ""
    devices = main.get_devices() or []
    kinds = [d.get_device_type() for d in devices]
    if NM.DeviceType.WIFI in kinds:
        info["kind"] = "wifi"
        ap = devices[kinds.index(NM.DeviceType.WIFI)].get_active_access_point()
        if ap:
            info["strength"] = ap.get_strength()
            info["name"] = ssid_text(ap) or info["name"]
    else:
        info["kind"] = "ethernet"
    cfg = main.get_ip4_config()
    addrs = cfg.get_addresses() if cfg else []
    if addrs:
        info["ip"] = addrs[0].get_address()
    return info


def set_wifi(enabled):
    c = client()
    if not c:
        return False
    c.dbus_set_property(NM.DBUS_PATH, NM.DBUS_INTERFACE, "WirelessEnabled",
                        GLib.Variant("b", bool(enabled)), -1, None, None)
    return True


def rescan():
    dev = wifi_device()
    if dev:
        dev.request_scan_async(None, lambda *_a: None)


def security(ap):
    """open | psk | sae (WPA3 only) | enterprise | wep"""
    sec = getattr(NM, "80211ApSecurityFlags")
    flags = ap.get_wpa_flags() | ap.get_rsn_flags()
    if flags & sec.KEY_MGMT_802_1X:
        return "enterprise"
    if flags & sec.KEY_MGMT_PSK:
        return "psk"        # includes WPA2/WPA3 mixed networks
    if flags & sec.KEY_MGMT_SAE:
        return "sae"
    if ap.get_flags() & getattr(NM, "80211ApFlags").PRIVACY:
        return "wep"
    return "open"


def saved(ssid):
    c = client()
    for con in c.get_connections() if c else ():
        w = con.get_setting_wireless()
        if w and w.get_ssid() and NM.utils_ssid_to_utf8(w.get_ssid().get_data()) == ssid:
            return con
    return None


def networks():
    """Visible networks, one per name (strongest): the connected one, saved ones, then by signal."""
    dev = wifi_device()
    if not dev:
        return []
    current = ssid_text(dev.get_active_access_point())
    best = {}
    for ap in dev.get_access_points():
        name = ssid_text(ap)
        if name and (name not in best or ap.get_strength() > best[name]["strength"]):
            best[name] = {"ssid": name, "strength": ap.get_strength(), "ap": ap,
                          "security": security(ap), "active": name == current}
    for net in best.values():
        net["saved"] = saved(net["ssid"]) is not None
    return sorted(best.values(), key=lambda n: (not n["active"], not n["saved"], -n["strength"]))


def connect(net, password, done):
    """Join a network. done(None) on success, done(message) on failure."""
    c, dev = client(), wifi_device()
    if not c or not dev:
        done("Wi-Fi isn't available.")
        return
    known = saved(net["ssid"])
    created = known is None

    def failed(con, text):
        if created and con:
            con.delete_async(None, lambda *_a: None)    # don't keep a wrong password
        done(text)

    def watch(active):
        handlers = []
        finished = []

        def check(*_a):
            if finished:
                return False
            state = active.get_state()
            if state in (NM.ActiveConnectionState.ACTIVATING, NM.ActiveConnectionState.UNKNOWN):
                return False
            finished.append(1)
            for h in handlers:
                active.disconnect(h)
            if state == NM.ActiveConnectionState.ACTIVATED:
                done(None)
            else:
                failed(active.get_connection(), "Couldn't connect. Check the password and try again.")
            return False

        def timeout():
            if not finished:
                finished.append(1)
                for h in handlers:
                    active.disconnect(h)
                failed(active.get_connection(), "That took too long. Try again.")
            return False
        handlers.append(active.connect("state-changed", check))
        GLib.timeout_add_seconds(45, timeout)
        check()

    def activate(con):
        def cb(cl, res):
            try:
                watch(cl.activate_connection_finish(res))
            except GLib.Error as e:
                done(e.message)
        c.activate_connection_async(con, dev, net["ap"].get_path(), None, cb)

    def add():
        con = NM.SimpleConnection.new()
        base = NM.SettingConnection.new()
        base.set_property(NM.SETTING_CONNECTION_ID, net["ssid"])
        base.set_property(NM.SETTING_CONNECTION_UUID, str(uuid.uuid4()))
        base.set_property(NM.SETTING_CONNECTION_TYPE, "802-11-wireless")
        con.add_setting(base)
        radio = NM.SettingWireless.new()
        radio.set_property(NM.SETTING_WIRELESS_SSID, net["ap"].get_ssid())
        con.add_setting(radio)
        if net["security"] in ("psk", "sae"):
            sec = NM.SettingWirelessSecurity.new()
            sec.set_property(NM.SETTING_WIRELESS_SECURITY_KEY_MGMT,
                             "sae" if net["security"] == "sae" else "wpa-psk")
            sec.set_property(NM.SETTING_WIRELESS_SECURITY_PSK, password)
            con.add_setting(sec)

        def cb(cl, res):
            try:
                watch(cl.add_and_activate_connection_finish(res))
            except GLib.Error as e:
                done(e.message)
        c.add_and_activate_connection_async(con, dev, net["ap"].get_path(), None, cb)

    if known and password:
        # a new password for a saved network
        sec = known.get_setting_wireless_security()
        if not sec:
            done("Forget this network and join it again.")
            return
        sec.set_property(NM.SETTING_WIRELESS_SECURITY_PSK, password)

        def committed(con, res):
            try:
                con.commit_changes_finish(res)
                activate(con)
            except GLib.Error as e:
                done(e.message)
        known.commit_changes_async(True, None, committed)
    elif known:
        activate(known)
    else:
        add()


def forget(ssid):
    con = saved(ssid)
    if con:
        con.delete_async(None, lambda *_a: None)


def disconnect():
    dev = wifi_device()
    if dev:
        dev.disconnect_async(None, lambda *_a: None)
