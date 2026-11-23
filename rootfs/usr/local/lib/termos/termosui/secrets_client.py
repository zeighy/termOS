"""Client for the root-owned termos-pin helper."""
import json
import subprocess

from . import core

OK, WRONG, BAD, WAIT = 0, 1, 2, 3


def call(command, *lines, sudo=True):
    """(exit code, info). Anything unexpected is a failure, never a success."""
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
