"""Settings > Security keys."""
from gi.repository import Gtk

from . import bluetooth, core, seckeys, ui
from .widgets import secret_entry

TEST_SITE = "https://webauthn.io/"


def in_terminal(title, *args):
    core.spawn("foot", "-T", title, "-e", "termos-key", *args)


class KeyCard(Gtk.Box):
    """One plugged-in key. Forms open inside it, where the on-screen keyboard can't cover them."""

    def __init__(self, window, key):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.window = window
        self.key = key
        self.info = None
        self.pin = None         # only while the passkey list is open
        self.busy = False
        self.alive = True
        self.connect("destroy", self.gone)
        head = ui.hbox(14)
        head.pack_start(ui.icon("key", "accent", "lead"), False, False, 0)
        words = ui.vbox(2)
        words.pack_start(ui.label(key["name"], "row-label", wrap=True), False, False, 0)
        self.sub = ui.label("Reading…", "sub", wrap=True)
        words.pack_start(self.sub, False, False, 0)
        head.pack_start(words, True, True, 0)
        self.pack_start(head, False, False, 6)
        self.buttons = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, column_spacing=8, row_spacing=8)
        self.buttons.set_max_children_per_line(4)
        self.pack_start(self.buttons, False, False, 0)
        self.area = ui.vbox(8)
        self.pack_start(self.area, False, False, 0)
        self.note = ui.label("", "sub", wrap=True)
        self.pack_start(self.note, False, False, 4)
        self.read()

    def gone(self, _w):
        self.alive = False
        self.pin = None

    def say(self, text, bad=False):
        self.note.set_text(text)
        ui.set_class(self.note, "error", bad)
        ui.set_class(self.note, "good", bool(text) and not bad)

    def job(self, work, done):
        """work() off the UI thread; problems are shown on the card."""
        if self.busy:
            return
        self.busy = True
        self.area.set_sensitive(False)

        def guarded():
            try:
                return work(), None
            except seckeys.KeyProblem as e:
                return None, str(e)

        def finish(result):
            if not self.alive:
                return
            self.busy = False
            self.area.set_sensitive(True)
            value, problem = result or (None, "Something went wrong.")
            if problem:
                self.say(problem, True)
                self.read()
            else:
                done(value)
        ui.background(guarded, finish)

    def read(self):
        node = self.key["node"]

        def work():
            try:
                return seckeys.describe(node), None
            except seckeys.KeyProblem as e:
                return None, str(e)

        def done(result):
            if self.alive:
                self.show_info(*(result or (None, "Couldn't read the key.")))
        ui.background(work, done)

    def show_info(self, info, problem):
        self.info = info
        ui.clear(self.buttons)
        if problem:
            self.sub.set_text(problem)
            self.add_button("Try again", self.read)
        elif not info["fido2"]:
            self.sub.set_text("U2F key: works as a second step on websites and for SSH. "
                              "It can't hold passkeys or a PIN.")
        else:
            bits = ["FIDO2", "PIN set" if info["pin"] else "no PIN yet"]
            if info["retries"] is not None and info["retries"] < 8:
                tries = info["retries"]
                bits.append(f"{tries} PIN {'try' if tries == 1 else 'tries'} left")
            if info["space"] is not None:
                bits.append(f"room for {info['space']} more passkeys")
            self.sub.set_text("  ·  ".join(bits))
            if info["can_pin"]:
                self.add_button("Change PIN" if info["pin"] else "Set a PIN", self.pin_form,
                                None if info["pin"] else "primary")
            if info["manage"] and info["pin"]:
                self.add_button("Passkeys", self.passkey_form)
            if info["fingerprints"]:
                self.add_button("Fingerprints", lambda: in_terminal("Fingerprints", "fingerprints"))
            self.add_button("Reset…", lambda: in_terminal("Reset security key", "reset"))
        self.buttons.show_all()

    def add_button(self, text, action, *cls):
        child = Gtk.FlowBoxChild()
        child.set_can_focus(False)
        child.add(ui.button(text, action, *cls))
        self.buttons.add(child)

    def close_area(self):
        ui.clear(self.area)
        self.pin = None

    def pin_form(self):
        self.close_area()
        self.say("")
        had_pin = self.info["pin"]
        least = self.info["min_pin"]
        old = secret_entry("Current PIN")
        new = secret_entry(f"New PIN ({least} or more characters)")
        again = secret_entry("New PIN again")
        for e in ([old] if had_pin else []) + [new, again]:
            self.area.pack_start(e, False, False, 0)

        def submit():
            value = new.get_text()
            problem = seckeys.check_new_pin(value, least)
            if not problem and value != again.get_text():
                problem = "The new PINs don't match."
            if not problem and had_pin and not old.get_text():
                problem = "Enter the current PIN."
            if problem:
                self.say(problem, True)
                return
            current = old.get_text() if had_pin else None

            def done(_value):
                self.close_area()
                self.say("PIN changed." if had_pin else "PIN set.")
                self.read()
            self.job(lambda: seckeys.set_pin(self.key["node"], value, current), done)
        again.connect("activate", lambda _e: submit())
        line = ui.hbox(8)
        line.pack_start(ui.button("Cancel", lambda: (self.close_area(), self.say(""))), False, False, 0)
        line.pack_end(ui.button("Save PIN", submit, "primary"), False, False, 0)
        self.area.pack_start(line, False, False, 0)
        self.area.show_all()
        (old if had_pin else new).grab_focus()

    def passkey_form(self):
        self.close_area()
        self.say("")
        entry = secret_entry("The key's PIN")

        def submit():
            pin = entry.get_text()
            if not pin:
                return

            def done(found):
                self.pin = pin
                self.show_passkeys(found)
                self.read()
            self.job(lambda: seckeys.passkeys(self.key["node"], pin), done)
        entry.connect("activate", lambda _e: submit())
        line = ui.hbox(8)
        line.pack_start(entry, True, True, 0)
        line.pack_start(ui.button("Show", submit, "primary"), False, False, 0)
        self.area.pack_start(line, False, False, 0)
        self.area.show_all()
        entry.grab_focus()

    def show_passkeys(self, found):
        ui.clear(self.area)
        self.say("")
        for cred in found:
            line = ui.hbox(10)
            words = ui.vbox(0)
            rp = cred["rp"]
            is_ssh = rp.startswith("ssh:")
            title = "SSH key " + rp[4:] if is_ssh else rp
            words.pack_start(ui.label(title, "row-label", ellipsize=True), False, False, 0)
            user = cred["user"]
            if user and not (is_ssh and user == "openssh"):
                words.pack_start(ui.label(user, "sub", ellipsize=True), False, False, 0)
            line.pack_start(words, True, True, 0)
            line.pack_end(ui.button(None, lambda c=cred: self.delete(c), "round", icon_name="delete",
                                    tip=f"Delete {title}"), False, False, 0)
            self.area.pack_start(line, False, False, 0)
        if not found:
            self.area.pack_start(ui.label("Nothing is saved on this key.", "sub"), False, False, 0)
        self.area.pack_start(ui.button("Done", self.close_area), False, False, 4)
        self.area.show_all()

    def delete(self, cred):
        if not ui.confirm(self.window, f"Delete {cred['rp']}?",
                          "You won't be able to sign in with it again. "
                          "Check that you have another way into that account first.",
                          "Delete", danger=True):
            return
        node, pin = self.key["node"], self.pin

        def work():
            seckeys.delete_passkey(node, pin, cred["id"])
            return seckeys.passkeys(node, pin)

        def done(found):
            self.show_passkeys(found)
            self.say("Deleted.")
            self.read()
        self.job(work, done)


class KeysPage:
    def __init__(self, window, p):
        self.window = window
        self.keys = None
        self.readers = None
        self.alive = True

        p.section("Plugged in")
        self.list = ui.vbox(8)
        p.add(self.list)
        self.list.connect("destroy", self.gone)

        p.section("SSH with a security key")
        self.name = Gtk.Entry(placeholder_text="optional")
        self.name.set_width_chars(10)
        self.name.set_max_length(32)
        self.store = Gtk.Switch(active=False)
        self.need_pin = Gtk.Switch(active=False)
        p.row("Name", self.name, "Only needed for a second key")
        p.row("Keep it on the security key", self.store,
              "Then you can bring it in on any computer. Needs a PIN")
        p.row("Ask for the PIN every time", self.need_pin, "Otherwise a touch is enough")
        line = ui.hbox(8)
        line.pack_start(ui.button("Create SSH key", self.create, "primary", icon_name="plus"), False, False, 0)
        p.add(line)
        p.row("Already made one on another computer?",
              ui.button("Bring it in", lambda: in_terminal("Bring in SSH keys", "import")),
              "Finds SSH keys kept on the security key")
        p.note("Servers need OpenSSH 8.2 or newer.")

        p.section("Passkeys in the browser")
        p.row("Test passkeys", ui.button("Open test site", lambda: core.spawn("xdg-open", TEST_SITE)),
              "webauthn.io works with a key or a phone")
        bt = ui.hbox(12)
        words = ui.vbox(2)
        words.pack_start(ui.label("Passkey on your phone (QR code)", "row-label", wrap=True), False, False, 0)
        self.phone = ui.label("Checking…", "sub", wrap=True)
        words.pack_start(self.phone, False, False, 0)
        bt.pack_start(words, True, True, 0)
        self.bt_button = ui.button("Turn on", self.bluetooth_on, "primary")
        self.bt_button.set_valign(Gtk.Align.CENTER)
        self.bt_button.get_child().show_all()
        self.bt_button.set_no_show_all(True)
        bt.pack_end(self.bt_button, False, False, 0)
        p.add(bt)
        p.note("In the browser choose the phone option and scan the code with the phone's camera. "
               "Both devices need Bluetooth and internet. No pairing is needed. "
               "If an iPhone stalls, switch its Bluetooth off and on and scan again.")
        p.note("Passkeys can't be saved on this device itself yet: Linux has no built-in store like "
               "Windows Hello. Use a key, a phone or a password manager's browser extension.")

        p.section("Smart cards and YubiKey apps")
        self.card_state = p.note("")
        p.row("One-time codes", ui.button("Show", lambda: in_terminal("YubiKey codes", "codes")),
              "Authenticator accounts saved on a YubiKey")
        p.row("Card details", ui.button("Show", lambda: in_terminal("Smart card", "card")),
              "PIV certificates and OpenPGP keys")
        p.note("To use a card for SSH, edit a host in SSH Hosts and pick it under Key.")

        p.section("Over Remote Desktop")
        p.note("To use a key inside a Windows session, edit the connection in Remote Desktop and turn on "
               "Share WebAuthn (FIDO2) credentials, or Share a smart card for PIV.")

        self.scan()
        self.check_bluetooth()
        ui.every(self.list, 2, self.scan)
        ui.every(self.list, 4, self.check_bluetooth)

    def gone(self, _w):
        self.alive = False

    def scan(self):
        # only reads sysfs; the keys themselves are asked when a card is first shown
        keys = seckeys.find_keys()
        # don't start talking to a key that was plugged in for another app
        if self.keys is not None and keys != self.keys and keys and not self.window.is_active():
            return
        if keys != self.keys:
            self.keys = keys
            ui.clear(self.list)
            for key in keys:
                self.list.pack_start(KeyCard(self.window, key), False, False, 0)
            if not keys:
                self.list.pack_start(ui.empty_state(
                    "key", "No security key plugged in",
                    "Plug in a YubiKey or any FIDO2 key. It appears here by itself."), False, False, 0)
            self.list.show_all()
        readers = seckeys.find_readers()
        if readers != self.readers:
            self.readers = readers
            self.card_state.set_text("Found: " + ", ".join(readers) if readers
                                     else "No smart-card reader or YubiKey card interface found.")

    def create(self):
        args = ["create"]
        if self.store.get_active():
            args.append("--store")
        if self.need_pin.get_active():
            args.append("--pin")
        name = self.name.get_text().strip()
        if name:
            args.append(f"--name={name}")
        in_terminal("Create SSH key", *args)

    def check_bluetooth(self):
        ui.background(bluetooth.state, self.show_bluetooth)

    def show_bluetooth(self, state):
        if not self.alive:
            return
        self.phone.set_text("Ready" if state else "Needs Bluetooth, which is off" if state is False
                            else "Needs Bluetooth, and no adapter was found")
        ui.set_class(self.phone, "good", bool(state))
        ui.set_class(self.phone, "warn", state is False)
        self.bt_button.set_visible(state is False)

    def bluetooth_on(self):
        self.phone.set_text("Turning on…")
        ui.background(lambda: bluetooth.turn(True), lambda _ok: self.check_bluetooth())
