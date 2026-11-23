"""Toolkit-independent helpers: settings files, processes, battery, sound, backlight."""
import glob
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
RUN_DIR = os.path.join(os.environ.get("XDG_RUNTIME_DIR") or f"/run/user/{os.getuid()}", "termos")
ROOT_HELPER = "/usr/local/bin/termos-root-helper"
PIN_HELPER = "/usr/local/bin/termos-pin"
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
    for d in system_supplies("Battery"):
        try:
            percent = int(slurp(f"{d}/capacity"))
        except ValueError:
            continue
        info = {"path": d, "percent": percent, "status": slurp(f"{d}/status", "Unknown")}
        info["charging"] = info["status"] == "Charging"
        full = slurp(f"{d}/energy_full") or slurp(f"{d}/charge_full")
        design = slurp(f"{d}/energy_full_design") or slurp(f"{d}/charge_full_design")
        info["health"] = None
        if full.isdigit() and design.isdigit() and int(design):
            info["health"] = min(int(full) * 100 // int(design), 100)
        power = slurp(f"{d}/power_now")
        info["watts"] = int(power) / 1e6 if power.isdigit() else None
        return info
    return None


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


def hostname():
    return slurp("/proc/sys/kernel/hostname", "termOS")
