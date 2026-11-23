"""Security keys (FIDO2) and smart cards.

Finding them only reads sysfs. Talking to a key is done on demand: a key does
one thing at a time, and asking it questions in the background could break a
sign-in that is happening in the browser.
"""
import glob
import os
import re

from . import core

FIDO_USAGE_PAGE = b"\x06\xd0\xf1"
PIV_MODULE = "/usr/lib/opensc-pkcs11.so"
OPENPGP_AGENT = "${XDG_RUNTIME_DIR}/gnupg/S.gpg-agent.ssh"


class KeyProblem(Exception):
    """Something to tell the user."""


def find_keys():
    """[{node, name, serial}] of the plugged-in FIDO keys."""
    found = []
    for d in sorted(glob.glob("/sys/class/hidraw/hidraw*")):
        try:
            with open(f"{d}/device/report_descriptor", "rb") as f:
                if FIDO_USAGE_PAGE not in f.read():
                    continue
        except OSError:
            continue
        node = f"/dev/{os.path.basename(d)}"
        name = re.search(r"^HID_NAME=(.*)$", core.slurp(f"{d}/device/uevent"), re.M)
        found.append({"node": node, "name": (name.group(1).strip() if name else "") or "Security key",
                      # changes on every plug-in, even when the node number is reused
                      "plugged": os.path.basename(os.path.realpath(f"{d}/device"))})
    return found


def find_readers():
    """Names of the USB smart-card interfaces (YubiKeys have one too)."""
    found = []
    for path in sorted(glob.glob("/sys/bus/usb/devices/*:*/bInterfaceClass")):
        if core.slurp(path).lower() == "0b":
            usb = os.path.dirname(os.path.realpath(os.path.dirname(path)))
            found.append(core.slurp(f"{usb}/product", "Smart-card reader"))
    return found


def is_security_key_file(path):
    """A private key file that only works together with the hardware key."""
    try:
        with open(os.path.expanduser(path) + ".pub", encoding="ascii", errors="replace") as f:
            return f.read(64).startswith("sk-")
    except OSError:
        return False


def _explain(error):
    from fido2.ctap import CtapError

    if isinstance(error, KeyProblem):
        return error
    if isinstance(error, CtapError):
        err = CtapError.ERR
        text = {
            err.PIN_INVALID: "That PIN is wrong.",
            err.PIN_BLOCKED: "The PIN is blocked after too many wrong tries. The key has to be reset.",
            err.PIN_AUTH_BLOCKED: "Too many wrong tries in a row. Unplug the key, plug it back in and try again.",
            err.PIN_NOT_SET: "This key has no PIN yet. Set one first.",
            err.PIN_POLICY_VIOLATION: "The key doesn't accept that PIN. Try a longer, less simple one.",
            err.CHANNEL_BUSY: "The key is busy with another app. Finish there and try again.",
            err.NO_CREDENTIALS: "That passkey is no longer on the key.",
        }.get(error.code, f"The key refused ({error.code}).")
        return KeyProblem(text)
    if isinstance(error, PermissionError):
        return KeyProblem("No permission to use the key. Unplug it and plug it back in.")
    return KeyProblem("Couldn't talk to the key. Is it still plugged in?")


class _Session:
    def __init__(self, node):
        self.node = node

    def __enter__(self):
        from fido2.ctap2 import Ctap2
        from fido2.hid import CAPABILITY, open_device

        self.device = open_device(self.node)
        try:
            self.ctap = Ctap2(self.device) if self.device.capabilities & CAPABILITY.CBOR else None
        except BaseException:
            self.device.close()
            raise
        return self

    def __exit__(self, *_exc):
        self.device.close()
        return False


def _run(node, work):
    try:
        with _Session(node) as key:
            return work(key)
    except Exception as e:
        raise _explain(e) from e


def describe(node):
    """What the key can do. Needs neither the PIN nor a touch."""
    def work(key):
        if key.ctap is None:
            return {"fido2": False}
        from fido2.ctap2.credman import CredentialManagement
        from fido2.ctap2.pin import ClientPin

        info = key.ctap.info
        opts = info.options
        out = {"fido2": True, "can_pin": "clientPin" in opts, "pin": bool(opts.get("clientPin")),
               "min_pin": info.min_pin_length or 4, "retries": None,
               "manage": CredentialManagement.is_supported(info),
               "fingerprints": "bioEnroll" in opts or "userVerificationMgmtPreview" in opts,
               "space": info.remaining_disc_creds}
        if out["pin"]:
            out["retries"] = ClientPin(key.ctap).get_pin_retries()[0]
        return out
    return _run(node, work)


def check_new_pin(pin, minimum):
    if len(pin) < minimum:
        return f"Use at least {minimum} characters."
    if len(pin.encode()) > 63:
        return "That PIN is too long."
    return None


def set_pin(node, new, old=None):
    def work(key):
        from fido2.ctap2.pin import ClientPin

        client = ClientPin(key.ctap)
        if old is None:
            client.set_pin(new)
        else:
            client.change_pin(old, new)
    _run(node, work)


def _manager(key, pin):
    from fido2.ctap2.credman import CredentialManagement
    from fido2.ctap2.pin import ClientPin

    client = ClientPin(key.ctap)
    token = client.get_pin_token(pin, ClientPin.PERMISSION.CREDENTIAL_MGMT)
    return CredentialManagement(key.ctap, client.protocol, token)


def passkeys(node, pin):
    """[{rp, user, id}] saved on the key."""
    def work(key):
        manager = _manager(key, pin)
        res = manager.RESULT
        if not manager.get_metadata().get(res.EXISTING_CRED_COUNT):
            return []
        found = []
        for rp in manager.enumerate_rps():
            for cred in manager.enumerate_creds(rp[res.RP_ID_HASH]):
                user = cred.get(res.USER) or {}
                found.append({"rp": rp[res.RP].get("id", ""),
                              "user": user.get("name") or user.get("displayName") or "",
                              "id": cred[res.CREDENTIAL_ID]})
        return sorted(found, key=lambda c: (c["rp"], c["user"]))
    return _run(node, work)


def delete_passkey(node, pin, cred_id):
    _run(node, lambda key: _manager(key, pin).delete_cred(cred_id))
