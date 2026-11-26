"""Client for the root-owned termos-pin helper (via termos-pin.socket, with sudo fallback)."""
import json
import socket
import subprocess

from . import core

OK, WRONG, BAD, WAIT = 0, 1, 2, 3


def _call_socket(command, lines):
    """Talk to termos-pin.socket. Returns None only if the socket isn't available yet."""
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.settimeout(30)
    try:
        try:
            sock.connect(core.PIN_SOCKET)
        except (FileNotFoundError, ConnectionRefusedError, PermissionError):
            return None
        payload = f"{command}\n" + "".join(f"{line}\n" for line in lines)
        sock.sendall(payload.encode())
        sock.shutdown(socket.SHUT_WR)
        chunks = []
        while True:
            chunk = sock.recv(4096)
            if not chunk:
                break
            chunks.append(chunk)
        info = json.loads(b"".join(chunks))
    except (OSError, ValueError):
        return BAD, {"error": "The lock helper isn't responding."}
    finally:
        sock.close()
    if not isinstance(info, dict) or not isinstance(info.get("code"), int) or isinstance(info.get("code"), bool):
        return BAD, {"error": "The lock helper gave a bad answer."}
    code = info.pop("code")
    return code, info


def call(command, *lines, sudo=True):
    """(exit code, info). Anything unexpected is a failure, never a success."""
    if sudo:
        res = _call_socket(command, lines)
        if res is not None:
            return res
    argv = (["sudo", "-n"] if sudo else []) + [core.PIN_HELPER, command]
    data = "".join(f"{line}\n" for line in lines).encode()
    try:
        # no timeout that kills it: a killed attempt still counts as a failed one
        r = subprocess.run(argv, input=data, capture_output=True, timeout=30)
        info = json.loads(r.stdout)
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return BAD, {"error": "The lock helper isn't responding."}
    if not isinstance(info, dict):
        return BAD, {"error": "The lock helper gave a bad answer."}
    return r.returncode, info


def wait_text(seconds):
    minutes, secs = divmod(int(seconds), 60)
    return f"{minutes}:{secs:02d}" if minutes else f"{secs} s"
