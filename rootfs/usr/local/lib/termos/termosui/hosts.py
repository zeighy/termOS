"""The machines this device connects to: ~/.ssh/config and Remmina profiles.

Tailscale peers are only offered when adding a host, never listed by themselves.

~/.ssh/config stays the user's file: edits touch only the lines of the fields
changed, and keep comments, other options and the order.
"""
import configparser
import fcntl
import glob
import json
import os
import re
import shlex
import socket
import time
from concurrent.futures import ThreadPoolExecutor

from . import core, seckeys

SSH_DIR = os.path.join(core.HOME, ".ssh")
SSH_CONFIG = os.path.join(SSH_DIR, "config")
META = os.path.join(core.CFG, "hosts.json")
CONN_DIR = os.path.join(core.RUN_DIR, "connections")
FIELDS = {"hostname": "HostName", "user": "User", "port": "Port", "identityfile": "IdentityFile",
          "pkcs11provider": "PKCS11Provider", "identityagent": "IdentityAgent",
          "proxyjump": "ProxyJump", "forwardagent": "ForwardAgent"}
# options that can appear many times; the form edits them as a list
FORWARDS = {"localforward": "LocalForward", "remoteforward": "RemoteForward",
            "dynamicforward": "DynamicForward"}
# never accepted under "Other options": they would end or split the block
NOT_EXTRA = {"host", "match", "include"}
# choices for "Key" that aren't files
PIV, OPENPGP = "card:piv", "card:openpgp"
ALIAS_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,62}")
TARGET_RE = re.compile(r"(?:[A-Za-z0-9._][A-Za-z0-9._-]*@)?\[?[A-Za-z0-9:_][A-Za-z0-9._:%+-]*\]?")


def _option(line):
    """('hostname', 'example.com') for an option line, else (None, None)."""
    m = re.match(r"^\s*([A-Za-z0-9]+)(?:\s*=\s*|\s+)(.*?)\s*$", line)
    return (m.group(1).lower(), m.group(2).strip('"')) if m else (None, None)


def _blocks(lines):
    """[keyword, value, first line, end line] for every Host and Match block."""
    found = []
    for i, line in enumerate(lines):
        key, value = _option(line)
        if key in ("host", "match"):
            if found:
                found[-1][3] = i
            found.append([key, value, i, len(lines)])
    return found


def _trim(lines, start, end):
    """Comments and blank lines just above the next block belong to that block."""
    while end > start + 1 and (not lines[end - 1].strip() or
                               re.match(r"^#", lines[end - 1])):
        end -= 1
    return end


def ssh_hosts():
    result, seen, files = [], set(), set()

    def read(path, depth):
        real = os.path.realpath(path)
        if depth > 5 or real in files or not os.path.isfile(real):
            return
        files.add(real)
        lines = core.slurp(real).splitlines()
        for line in lines:
            key, value = _option(line)
            if key == "include":
                try:
                    patterns = shlex.split(value)
                except ValueError:
                    continue
                for pattern in patterns:
                    for inc in sorted(glob.glob(os.path.join(SSH_DIR, os.path.expanduser(pattern)))):
                        read(inc, depth + 1)
        for key, value, start, end in _blocks(lines):
            if key != "host":
                continue
            opts, forwards, extra = {}, [], []
            for line in lines[start + 1:_trim(lines, start, end)]:
                k, v = _option(line)
                if not k or line.lstrip().startswith("#"):
                    continue
                if k in FORWARDS:
                    forwards.append((k, v))
                elif k not in FIELDS:
                    extra.append(line.strip())
                if k not in opts:
                    opts[k] = v
            names = [n for n in value.split("#")[0].split() if not set(n) & set("*?!")]
            for name in names:
                if name in seen or name.startswith("-"):
                    continue
                seen.add(name)
                result.append({
                    "kind": "ssh", "name": name,
                    "host": opts.get("hostname", name).replace("%h", name),
                    "user": opts.get("user", ""), "port": opts.get("port", ""),
                    "identityfile": opts.get("identityfile", ""),
                    "pkcs11provider": opts.get("pkcs11provider", ""),
                    "identityagent": opts.get("identityagent", ""),
                    "proxyjump": opts.get("proxyjump", ""),
                    "forwardagent": opts.get("forwardagent", ""),
                    "forwards": forwards, "extra": extra,
                    "proxied": "proxyjump" in opts or "proxycommand" in opts,
                    "editable": real == os.path.realpath(SSH_CONFIG) and len(value.split()) == 1,
                })
    read(SSH_CONFIG, 0)
    return result


def key_choice(host):
    if host.get("pkcs11provider") == seckeys.PIV_MODULE:
        return PIV
    if host.get("identityagent") == seckeys.OPENPGP_AGENT:
        return OPENPGP
    return host.get("identityfile", "")


def key_fields(host, choice):
    """The config fields to write for a choice under "Key"."""
    if choice == key_choice(host):
        return {}       # untouched, so the user's own lines stay as they are
    fields = {"identityfile": "" if choice in (PIV, OPENPGP) else choice}
    # only take out card settings that we would have written ourselves
    if choice == PIV or host.get("pkcs11provider") == seckeys.PIV_MODULE:
        fields["pkcs11provider"] = seckeys.PIV_MODULE if choice == PIV else ""
    if choice == OPENPGP or host.get("identityagent") == seckeys.OPENPGP_AGENT:
        fields["identityagent"] = seckeys.OPENPGP_AGENT if choice == OPENPGP else ""
    return fields


def check_fields(old, name, f):
    if not ALIAS_RE.fullmatch(name):
        return "The name can use letters, digits, dots, dashes and underscores."
    if name != old and any(h["name"] == name for h in ssh_hosts()):
        return "There is already a host with that name."
    if not f.get("hostname") or not re.fullmatch(r"[A-Za-z0-9:_\[][A-Za-z0-9._:%\[\]-]*", f["hostname"]):
        return "Enter the address, for example 192.168.1.10 or box.example.com."
    if f.get("user") and not re.fullmatch(r"[A-Za-z0-9._][A-Za-z0-9._@\\-]*", f["user"]):
        return "That user name can't be used."
    port = f.get("port")
    if port and not (port.isdigit() and 0 < int(port) < 65536):
        return "The port is a number from 1 to 65535."
    jump = f.get("proxyjump")
    if jump and not re.fullmatch(r"[A-Za-z0-9._@:,%\[\]-]+", jump):
        return "Write the jump host like me@bastion.example.com, or several separated by commas."
    if f.get("forwardagent") not in (None, "", "yes", "no"):
        return "Forward agent is yes or no."
    if any("\n" in v or "\r" in v or '"' in v for v in f.values()):
        return "Quotes and line breaks can't be used."
    return None


def _port_ok(text):
    return text.isdigit() and 0 < int(text) < 65536


def check_forward(kind, listen, dest):
    """An error message for one port forward, or None."""
    m = re.fullmatch(r"(?:(\[[0-9A-Fa-f:.]+\]|[A-Za-z0-9.*_-]+):)?(\d{1,5})", listen)
    if not m or not _port_ok(m.group(2)):
        return f"'{listen or '(empty)'}' isn't a port. Use a number like 8080, or 0.0.0.0:8080."
    if kind == "dynamicforward":
        return None
    m = re.fullmatch(r"(\[[0-9A-Fa-f:.]+\]|[A-Za-z0-9._%-]+):(\d{1,5})", dest)
    if not m or not _port_ok(m.group(2)):
        return f"'{dest or '(empty)'}' isn't an address. Write it as host:port, like localhost:80."
    return None


def split_forward(kind, value):
    """('8080', 'localhost:80') from a LocalForward value."""
    parts = value.split()
    if kind == "dynamicforward" or len(parts) < 2:
        return (parts[0] if parts else ""), ""
    return parts[0], parts[1]


def parse_extra(text):
    """(lines, error) for the "Other options" box: one option per line."""
    found = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        key, value = _option(line)
        if not key or not value or not key[0].isalpha():
            return None, f"'{line}' isn't an option. Write it as Name value, like ServerAliveInterval 30."
        if key in NOT_EXTRA:
            return None, f"{line.split()[0]} can't be used here. Edit ~/.ssh/config as text for that."
        if key in FIELDS or key in FORWARDS:
            return None, f"Set {line.split()[0]} with its own field above."
        found.append(line)
    return found, None


def _write_config(lines):
    os.makedirs(SSH_DIR, 0o700, exist_ok=True)
    before = core.slurp(SSH_CONFIG)
    if before:
        core.write_atomic(SSH_CONFIG + ".termos-bak", before + "\n", 0o600)
    core.write_atomic(SSH_CONFIG, "\n".join(lines).rstrip("\n") + "\n", 0o600)


def _find_block(lines, name):
    for key, value, start, end in _blocks(lines):
        if key == "host" and value.split() == [name]:
            return start, _trim(lines, start, end)
    return None


def save_host(old, name, fields, forwards=None, extra=None):
    """Add (old=None) or change a host. Returns an error message, or None.

    forwards is [(kind, listen, dest)] and extra a list of option lines; None
    leaves those lines of the file as they are."""
    problem = check_fields(old, name, fields)
    if problem:
        return problem
    for kind, listen, dest in forwards or []:
        problem = kind not in FORWARDS and "Unknown kind of forward." or check_forward(kind, listen, dest)
        if problem:
            return problem
    if extra:
        _lines, problem = parse_extra("\n".join(extra))
        if problem:
            return problem
    lines = core.slurp(SSH_CONFIG).splitlines()

    def fmt(key, value):
        return f'{FIELDS[key]} "{value}"' if " " in value else f"{FIELDS[key]} {value}"

    # groups of lines that are replaced as a whole: (owns this option?, new lines)
    groups = []
    if forwards is not None:
        groups.append((lambda k: k in FORWARDS,
                       [f"{FORWARDS[k]} {listen}" + (f" {dest}" if dest else "")
                        for k, listen, dest in forwards]))
    if extra is not None:
        groups.append((lambda k: k not in FIELDS and k not in FORWARDS, list(extra)))

    if old:
        where = _find_block(lines, old)
        if not where:
            return "That host is no longer in ~/.ssh/config."
        start, end = where
        body, done = [], set()
        placed = [False] * len(groups)
        for line in lines[start + 1:end]:
            key, value = _option(line)
            mine = next((i for i, (owns, _n) in enumerate(groups)
                         if key and not line.lstrip().startswith("#") and owns(key)), None)
            if mine is not None:
                # the new list goes where the first old line was
                if not placed[mine]:
                    placed[mine] = True
                    indent = re.match(r"\s*", line).group(0) or "    "
                    body += [indent + n for n in groups[mine][1]]
                continue
            if key in fields and key in FIELDS and key not in done:
                done.add(key)
                if not fields[key]:
                    continue
                if fields[key] != value:
                    line = re.match(r"\s*", line).group(0) + fmt(key, fields[key])
            body.append(line)
        added = ["    " + fmt(k, v) for k, v in fields.items() if v and k not in done]
        for (_owns, new), was_placed in zip(groups, placed):
            if not was_placed:
                body += ["    " + n for n in new]
        head = lines[start] if old == name else f"Host {name}"
        lines[start:end] = [head] + added + body
    else:
        new = [f"Host {name}"] + ["    " + fmt(k, v) for k, v in fields.items() if v]
        new += ["    " + n for _owns, group in groups for n in group]
        # ssh uses the first value it finds, so hosts go above "Host *" and Match blocks
        at = len(lines)
        for key, value, start, _end in _blocks(lines):
            if key == "match" or set(value) & set("*?"):
                at = start
                while at and lines[at - 1].startswith("#"):
                    at -= 1
                break
        if at < len(lines):
            new.append("")
        if at and lines[at - 1].strip():
            new.insert(0, "")
        lines[at:at] = new
    _write_config(lines)
    if old and old != name:
        rename_meta(old, name)
    return None


def delete_host(name):
    lines = core.slurp(SSH_CONFIG).splitlines()
    where = _find_block(lines, name)
    if not where:
        return False
    start, end = where
    while end < len(lines) and not lines[end].strip():
        end += 1
    del lines[start:end]
    _write_config(lines)
    rename_meta(name, None)
    return True


# ---- per-host options ---------------------------------------------------
def all_meta():
    try:
        data = json.loads(core.slurp(META) or "{}")
        return data if isinstance(data, dict) else {}
    except ValueError:
        return {}


def _change_meta(change):
    os.makedirs(core.CFG, exist_ok=True)
    with open(META + ".lock", "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        data = all_meta()
        change(data)
        core.write_atomic(META, json.dumps(data, indent=1) + "\n", 0o600)


def set_meta(key, **values):
    _change_meta(lambda d: d.setdefault(key, {}).update(values))


def rename_meta(old, new):
    def change(d):
        val = d.pop(old, None)
        if new and val is not None:
            d[new] = val
    _change_meta(change)


def options(name, meta=None):
    meta = all_meta() if meta is None else meta
    mine = meta.get(name, {})
    default_mosh = core.setting_on("SSH_MOSH", False)
    return {"mosh": mine.get("mosh", default_mosh), "tmux": mine.get("tmux", False),
            "reconnect": mine.get("reconnect", True), "tunnel": mine.get("tunnel", False),
            "used": mine.get("used", 0)}


def ago(stamp):
    if not stamp:
        return ""
    s = max(0, time.time() - stamp)
    if s < 90:
        return "just now"
    if s < 5400:
        return f"{round(s / 60)} min ago"
    if s < 129600:
        return f"{round(s / 3600)} h ago"
    return f"{round(s / 86400)} days ago"


# ---- other sources ------------------------------------------------------
def remote_desktops():
    data_home = os.environ.get("XDG_DATA_HOME") or os.path.join(core.HOME, ".local", "share")
    found = []
    for path in sorted(glob.glob(os.path.join(data_home, "remmina", "*.remmina"))):
        cp = configparser.ConfigParser(interpolation=None, strict=False)
        try:
            cp.read(path, encoding="utf-8")
            sec = cp["remmina"]
        except (configparser.Error, KeyError, UnicodeDecodeError):
            continue
        proto, server = sec.get("protocol", ""), sec.get("server", "")
        host, port = split_port(server)
        found.append({"kind": "remote", "name": sec.get("name") or server, "path": path,
                      "protocol": proto, "host": host,
                      "port": port or {"RDP": "3389", "VNC": "5900", "SSH": "22"}.get(proto, ""),
                      "user": sec.get("username", ""),
                      "proxied": sec.get("ssh_tunnel_enabled", "0") == "1"})
    return found


def split_port(server):
    m = re.fullmatch(r"\[(.+)\](?::(\d+))?", server) or re.fullmatch(r"([^:]+)(?::(\d+))?", server)
    return (m.group(1), m.group(2) or "") if m else (server, "")


def save_remote(name, protocol, host, port, user, old_path=None):
    """Write or update a Remmina profile for an RDP or VNC machine. Returns an error message, or None."""
    if not name or len(name) > 60 or not name.isprintable():
        return "Give it a name."
    if any(m["name"].lower() == name.lower() and m["path"] != old_path for m in remote_desktops()):
        return "There is already a remote desktop with that name."
    if not host or not re.fullmatch(r"[A-Za-z0-9:_\[][A-Za-z0-9._:%\[\]-]*", host):
        return "Enter the address, for example 192.168.1.10 or box.example.com."
    if port and not (port.isdigit() and 0 < int(port) < 65536):
        return "The port is a number from 1 to 65535."
    if user and not re.fullmatch(r"[A-Za-z0-9._][A-Za-z0-9._@\\ -]*", user):
        return "That user name can't be used."
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    server = f"{host}:{port}" if port else host
    updates = {"name": name, "protocol": protocol, "server": server, "username": user}
    if old_path and os.path.isfile(old_path):
        raw_lines = core.slurp(old_path).splitlines()
        out, seen, in_sec = [], set(), False
        for line in raw_lines:
            stripped = line.strip()
            if stripped.startswith("[") and stripped.endswith("]"):
                if in_sec:
                    for k, v in updates.items():
                        if k not in seen:
                            out.append(f"{k}={v}")
                            seen.add(k)
                in_sec = stripped.lower() == "[remmina]"
                out.append(line)
                continue
            if in_sec and "=" in line:
                k = line.split("=", 1)[0].strip().lower()
                if k in updates:
                    if k not in seen:
                        out.append(f"{k}={updates[k]}")
                        seen.add(k)
                    continue
            out.append(line)
        if not any(ln.strip().lower() == "[remmina]" for ln in out):
            out.insert(0, "[remmina]")
        for k, v in updates.items():
            if k not in seen:
                out.append(f"{k}={v}")
        core.write_atomic(old_path, "\n".join(out) + "\n", 0o600)
        return None
    data_home = os.environ.get("XDG_DATA_HOME") or os.path.join(core.HOME, ".local", "share")
    folder = os.path.join(data_home, "remmina")
    os.makedirs(folder, 0o700, exist_ok=True)
    slug = re.sub(r"[^A-Za-z0-9]+", "-", name).strip("-").lower() or "host"
    path = os.path.join(folder, f"termos-{protocol.lower()}-{slug}.remmina")
    n = 2
    while os.path.exists(path):
        path = os.path.join(folder, f"termos-{protocol.lower()}-{slug}-{n}.remmina")
        n += 1
    lines = ["[remmina]", f"name={name}", f"protocol={protocol}",
             f"server={server}", f"username={user}"]
    core.write_atomic(path, "\n".join(lines) + "\n", 0o600)
    return None


def delete_remote(path):
    """Remove a saved Remmina profile."""
    if not path or not path.endswith(".remmina"):
        return False
    try:
        os.unlink(path)
    except OSError:
        return False
    rename_meta(f"remote:{path}", None)
    return True


def tailscale_peers():
    """Machines on the tailnet, offered by the Add host form."""
    if not os.path.exists("/run/tailscale/tailscaled.sock"):
        return []
    try:
        data = json.loads(core.run("tailscale", "status", "--json", timeout=4).stdout)
    except ValueError:
        return []
    peers = []
    if data.get("BackendState") != "Running":
        return peers
    for p in (data.get("Peer") or {}).values():
        dns = (p.get("DNSName") or "").rstrip(".")
        ips = p.get("TailscaleIPs") or []
        target = dns or (ips[0] if ips else "")
        if p.get("OS") in ("android", "iOS") or not TARGET_RE.fullmatch(target):
            continue
        peers.append({"name": dns.split(".")[0] or target, "host": target,
                      "os": p.get("OS") or "", "online": bool(p.get("Online"))})
    return sorted(peers, key=lambda p: (not p["online"], p["name"].lower()))


def machines():
    """Everything for the home screen: only the machines the user added."""
    return ssh_hosts() + remote_desktops()


def machine_key(m):
    return f"{m['kind']}:{m.get('path') or m['name']}"


def probe(items):
    """{key: True online | False offline | None can't tell} - a plain TCP connect."""
    def one(m):
        if m.get("proxied"):
            return None
        port = m["port"] or "22"
        if not m["host"] or not port.isdigit():
            return None
        try:
            with socket.create_connection((m["host"].strip("[]"), int(port)), timeout=2.5):
                return True
        except (OSError, ValueError, OverflowError):
            return False
    if not items:
        return {}
    with ThreadPoolExecutor(max_workers=10) as pool:
        return dict(zip(map(machine_key, items), pool.map(one, items)))


# ---- connecting ---------------------------------------------------------
def connect_ssh(target, port=""):
    args = ["--port", str(port)] if port else []
    core.spawn("foot", "-T", f"SSH: {target}", "-e", "termos-connect", *args, "--", target)


def browse_sftp(machine):
    """Open an SSH host's files in Thunar via GVFS SFTP (uses ~/.ssh/config)."""
    target = machine["name"] if isinstance(machine, dict) else str(machine)
    core.spawn("thunar", f"sftp://{target}/")


def connect(machine):
    if machine["kind"] == "remote":
        set_meta(machine_key(machine), used=time.time())
        core.spawn("remmina", "-c", machine["path"])
    else:
        connect_ssh(machine["name"])


def connections():
    """{target: 'connected'|'reconnecting'|'connecting'} of the open SSH windows."""
    rank = {"connecting": 0, "reconnecting": 1, "connected": 2}
    found = {}
    for path in glob.glob(os.path.join(CONN_DIR, "*")):
        pid = os.path.basename(path)
        if not pid.isdigit():
            continue
        if not os.path.exists(f"/proc/{pid}"):
            try:
                os.unlink(path)
            except OSError:
                pass
            continue
        state, _, target = core.slurp(path).partition("\t")
        if state in rank and rank[state] >= rank.get(found.get(target), -1):
            found[target] = state
    return found
