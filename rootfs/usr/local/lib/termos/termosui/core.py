"""Toolkit-independent helpers: settings files, processes, battery, sound, backlight."""
import glob
import json
import os
import re
import shlex
import subprocess
import tempfile

HOME = os.path.expanduser("~")
CFG = os.path.join(HOME, ".config", "termos")
SETTINGS_CONF = os.path.join(CFG, "settings.conf")
DISPLAY_CONF = os.path.join(CFG, "display.conf")
OUTPUTS_CONF = os.path.join(CFG, "outputs.conf")
LAYOUT_CONF = os.path.join(CFG, "layout.conf")
RUN_DIR = os.path.join(os.environ.get("XDG_RUNTIME_DIR") or f"/run/user/{os.getuid()}", "termos")
ROOT_HELPER = "/usr/local/bin/termos-root-helper"
PIN_HELPER = "/usr/local/bin/termos-pin"
PIN_SOCKET = "/run/termos-pin.sock"
POWER_CONF = "/etc/termos/power.conf"
PANEL_RE = re.compile(r"(eDP|DSI|LVDS)")


def slurp(path, default=""):
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return f.read().strip()
    except OSError:
        return default


def run(*args, timeout=20, stdin=None):
    try:
        return subprocess.run(args, capture_output=True, text=True, errors="replace",
                              timeout=timeout, input=stdin)
    except (OSError, subprocess.TimeoutExpired) as e:
        return subprocess.CompletedProcess(args, 1, "", str(e))


def spawn(*args):
    """Start a program detached from us, without leaving a zombie behind."""
    try:
        # double fork through setsid -f: the program is re-parented straight away
        subprocess.run(["setsid", "-f", *args], cwd=HOME, stdin=subprocess.DEVNULL,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5)
    except (OSError, subprocess.TimeoutExpired):
        pass


def write_atomic(path, text, mode=0o644):
    path = os.path.realpath(path)   # keep symlinked dotfiles as symlinks
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), prefix=".termos-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.chmod(tmp, mode)
        os.replace(tmp, path)
    except BaseException:
        os.unlink(tmp)
        raise


# The .conf files are also sourced by the shell helpers, so values are shell-quoted.
def read_conf(path=SETTINGS_CONF):
    vals = {}
    for line in slurp(path).splitlines():
        m = re.match(r"^\s*([A-Z_][A-Z0-9_]*)=(.*)$", line)
        if m:
            try:
                parts = shlex.split(m.group(2), comments=True)
                vals[m.group(1)] = parts[0] if parts else ""
            except ValueError:
                vals[m.group(1)] = m.group(2)
    return vals


def write_conf(key, value, path=SETTINGS_CONF):
    text = slurp(path) or "# termOS settings (written by the termOS apps)"
    lines = [ln for ln in text.splitlines() if not re.match(rf"^\s*{key}=", ln)]
    lines.append(f"{key}={shlex.quote(str(value))}")
    write_atomic(path, "\n".join(lines) + "\n")


def setting_on(key, default=True):
    return read_conf().get(key, "1" if default else "0") == "1"


def root_helper(*args, stdin=None):
    r = run("sudo", "-n", ROOT_HELPER, *args, timeout=40, stdin=stdin)
    return r.returncode == 0, (r.stderr or r.stdout).strip()


def system_supplies(kind):
    """Power supplies of the computer itself; mice, pens and headsets have scope=Device."""
    for d in sorted(glob.glob("/sys/class/power_supply/*")):
        if slurp(f"{d}/type") == kind and slurp(f"{d}/scope") != "Device":
            yield d


def battery():
    """Combined info across all system batteries (e.g. tablet + keyboard dock)."""
    def _int(path):
        v = slurp(path)
        return int(v) if v.isdigit() else None

    found = []
    for d in system_supplies("Battery"):
        cap = _int(f"{d}/capacity")
        if cap is None:
            continue
        efull, edesign, enow = _int(f"{d}/energy_full"), _int(f"{d}/energy_full_design"), _int(f"{d}/energy_now")
        cfull, cdesign, cnow = _int(f"{d}/charge_full"), _int(f"{d}/charge_full_design"), _int(f"{d}/charge_now")
        if efull:
            unit, full, design, now = "energy", efull, edesign, enow
        elif cfull:
            unit, full, design, now = "charge", cfull, cdesign, cnow
        else:
            unit, full, design, now = None, None, None, None
        pw = _int(f"{d}/power_now")
        if pw is not None:
            watts = pw / 1e6
        else:
            cur, volt = _int(f"{d}/current_now"), _int(f"{d}/voltage_now")
            watts = cur * volt / 1e12 if cur is not None and volt is not None else None
        found.append({"path": d, "percent": cap, "status": slurp(f"{d}/status", "Unknown"),
                      "unit": unit, "full": full, "design": design, "now": now, "watts": watts})
    if not found:
        return None
    units = {b["unit"] for b in found}
    if len(units) == 1 and None not in units and all(b["full"] for b in found):
        total_full = sum(b["full"] for b in found)
        if all(b["now"] is not None for b in found):
            percent = min(max(round(sum(b["now"] for b in found) * 100 / total_full), 0), 100)
        else:
            percent = min(max(round(sum(b["percent"] * b["full"] for b in found) / total_full), 0), 100)
    else:
        percent = round(sum(b["percent"] for b in found) / len(found))
    statuses = [b["status"] for b in found]
    if "Charging" in statuses:
        status = "Charging"
    elif "Discharging" in statuses:
        status = "Discharging"
    elif all(s == "Full" for s in statuses):
        status = "Full"
    else:
        status = statuses[0]
    health = None
    with_design = [b for b in found if b["full"] and b["design"]]
    if with_design:
        if len({b["unit"] for b in with_design}) == 1:
            health = min(sum(b["full"] for b in with_design) * 100 // sum(b["design"] for b in with_design), 100)
        else:
            health = min(round(sum(b["full"] * 100 / b["design"] for b in with_design) / len(with_design)), 100)
    watts_vals = [b["watts"] for b in found if b["watts"] is not None]
    return {"path": found[0]["path"], "percent": percent, "status": status,
            "charging": status == "Charging", "health": health,
            "watts": sum(watts_vals) if watts_vals else None}


def on_battery():
    return any(slurp(f"{d}/status") == "Discharging" for d in system_supplies("Battery"))


def backlight_path():
    found = sorted(glob.glob("/sys/class/backlight/*"))
    return found[0] if found else None


def get_brightness():
    d = backlight_path()
    try:
        return round(int(slurp(f"{d}/brightness")) * 100 / int(slurp(f"{d}/max_brightness")))
    except (ValueError, ZeroDivisionError):
        return None


def set_brightness(percent):
    run("brightnessctl", "-c", "backlight", "-q", "set", f"{max(int(percent), 3)}%")


def get_volume():
    """(percent, muted), or None without a sound server."""
    m = re.search(r"(\d+)%", run("pactl", "get-sink-volume", "@DEFAULT_SINK@", timeout=4).stdout)
    if not m:
        return None
    muted = "yes" in run("pactl", "get-sink-mute", "@DEFAULT_SINK@", timeout=4).stdout
    return int(m.group(1)), muted


def set_volume(percent):
    run("pactl", "set-sink-volume", "@DEFAULT_SINK@", f"{int(percent)}%", timeout=4)
    if percent > 0:
        run("pactl", "set-sink-mute", "@DEFAULT_SINK@", "0", timeout=4)


def set_muted(muted):
    run("pactl", "set-sink-mute", "@DEFAULT_SINK@", "1" if muted else "0", timeout=4)


def _audio_list(kind):
    """[(name, description)] for PipeWire/Pulse sinks or non-monitor sources."""
    try:
        items = json.loads(run("pactl", "-f", "json", "list", kind, timeout=4).stdout)
    except ValueError:
        return []
    out = []
    for item in items if isinstance(items, list) else ():
        name = item.get("name") or ""
        if not name or (kind == "sources" and item.get("monitor_source")):
            continue
        if kind == "sources" and name.endswith(".monitor"):
            continue
        desc = (item.get("description") or item.get("properties", {}).get("node.description") or name).strip()
        out.append((name, desc))
    return out


def audio_sinks():
    return _audio_list("sinks")


def audio_sources():
    return _audio_list("sources")


def default_sink():
    return run("pactl", "get-default-sink", timeout=4).stdout.strip()


def default_source():
    return run("pactl", "get-default-source", timeout=4).stdout.strip()


def set_default_sink(name):
    return run("pactl", "set-default-sink", name, timeout=4).returncode == 0


def set_default_source(name):
    return run("pactl", "set-default-source", name, timeout=4).returncode == 0


def get_mic():
    """(percent, muted) for @DEFAULT_SOURCE@, or None without a mic."""
    m = re.search(r"(\d+)%", run("pactl", "get-source-volume", "@DEFAULT_SOURCE@", timeout=4).stdout)
    if not m:
        return None
    muted = "yes" in run("pactl", "get-source-mute", "@DEFAULT_SOURCE@", timeout=4).stdout
    return int(m.group(1)), muted


def set_mic_volume(percent):
    run("pactl", "set-source-volume", "@DEFAULT_SOURCE@", f"{int(percent)}%", timeout=4)
    if percent > 0:
        run("pactl", "set-source-mute", "@DEFAULT_SOURCE@", "0", timeout=4)


def set_mic_muted(muted):
    run("pactl", "set-source-mute", "@DEFAULT_SOURCE@", "1" if muted else "0", timeout=4)


def removable_mounts():
    """Mounted removable/USB partitions: [{device, disk, mountpoint, label}]."""
    try:
        data = json.loads(run("lsblk", "-Jpo", "NAME,RM,HOTPLUG,TYPE,MOUNTPOINT,LABEL,MODEL,PKNAME",
                              timeout=4).stdout)
    except ValueError:
        return []
    found = []

    def walk(nodes, parent_rm=False, parent_model="", parent_disk=""):
        for n in nodes or ():
            is_rm = bool(n.get("rm")) or bool(n.get("hotplug")) or parent_rm
            disk = n.get("name") if n.get("type") == "disk" else (parent_disk or n.get("pkname") or "")
            model = (n.get("model") or "").strip() or parent_model
            mp = n.get("mountpoint") or ""
            if (is_rm and mp.startswith("/") and mp not in ("/", "/boot", "/boot/efi")
                    and not mp.startswith("/run/archiso")):
                label = (n.get("label") or "").strip() or os.path.basename(mp) or model or os.path.basename(n["name"])
                found.append({"device": n["name"], "disk": disk, "mountpoint": mp, "label": label})
            walk(n.get("children"), is_rm, model, disk)
    walk(data.get("blockdevices"))
    return found


def eject_mount(item):
    """Unmount and safely power off a removable drive. Returns (ok, error)."""
    r = run("udisksctl", "unmount", "--no-user-interaction", "-b", item["device"], timeout=15)
    if r.returncode != 0:
        return False, (r.stderr or r.stdout).strip() or "Drive is busy"
    disk = item.get("disk")
    if disk:
        # Power-off only succeeds if no other partition on the same disk is mounted
        run("udisksctl", "power-off", "--no-user-interaction", "-b", disk, timeout=10)
    return True, ""


def disk_encrypted():
    """(is_encrypted, backing_device) for the root filesystem."""
    r = run("termos-encrypt", "--status", timeout=4)
    parts = r.stdout.strip().split()
    if parts and parts[0] == "encrypted":
        return True, parts[1] if len(parts) > 1 else ""
    return False, parts[1] if len(parts) > 1 else ""


def hostname():
    return slurp("/proc/sys/kernel/hostname", "termOS")
