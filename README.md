# termOS

A minimal, fast-booting Arch Linux setup for using small x86 machines (tablets
like the Lenovo Tablet 10 and IdeaPad Duet 3) as **remote-access terminals**.

It is plain Arch Linux, not a fork: every package comes from the official
repos, so the whole system is updated with

```sh
sudo pacman -Syu
```

## What's in it

| Part              | Package                                      |
|-------------------|----------------------------------------------|
| Desktop           | `labwc` (Wayland, stacking) + `termos-shell` (panel, home screen, Quick Settings, apps tray) |
| Lock screen       | `termos-lock`: PIN at every start and after sleep (`gtk-session-lock`) |
| Terminal          | `foot` (+ `tmux`, `openssh`, `mosh`)         |
| Browser           | `chromium` (native Wayland, touch enabled)   |
| File manager      | `thunar` (+ `gvfs` for USB drives / trash)   |
| Remote desktop    | `remmina` with RDP (`freerdp`) and VNC       |
| On-screen keyboard| `squeekboard` (off until you tap ⌨)          |
| Text / images     | `mousepad`, `ristretto`                      |
| Video / music     | `mpv`, `parole`                              |
| Settings          | `termos-settings` (GTK3, touch-friendly), `termos-welcome` on first run |
| Task Manager      | `termos-taskmgr` (end/force-quit apps; `Ctrl+Shift+Esc`) |
| Performance       | `termos-perfmon` (CPU, memory, disk, network, battery graphs) |
| Boot splash       | `plymouth` with the termOS logo and spinner (`artwork/make-splash.py` regenerates the images) |
| SSH hosts         | `termos-ssh` (add/edit hosts, keys, tmux resume, auto-reconnect, mosh) |
| Security keys     | `libfido2`, `opensc` + `pcscd`, `yubikey-manager`: YubiKey / FIDO2, passkeys, PIV and OpenPGP cards |
| Power             | `termos-power-profile` (saver / balanced / performance), `swayidle` + `wlopm` |
| Notifications     | `mako`                                       |
| Extras            | `grim`/`slurp` screenshots, `blueman`, `tailscale` |
| Network           | NetworkManager; Wi-Fi page in Settings (`nmtui` too) |
| Boot              | systemd-boot, systemd initramfs, straight to the PIN screen |
| Memory            | zram swap (compressed RAM)                   |

The installed package list is [`packages.x86_64`](packages.x86_64). Add or remove
lines there and rebuild.

## Building the ISO

Needs Docker (works from Ubuntu/any distro, no Arch host required):

```sh
./build.sh
# -> out/termos-YYYY.MM.DD-x86_64.iso   (~2 GB)
```

The ISO is the standard Arch live environment (`releng` profile) plus the
termOS installer and an **offline copy of every package**, so installing does
not need Wi-Fi.

For a smaller USB that downloads everything while installing (so the device
must be online: the menu's *Connect to Wi-Fi*, or a cable):

```sh
./build.sh --online
# -> out/termos-online-YYYY.MM.DD-x86_64.iso   (~1 GB)
```

Its menu offers only the online install.

Write it to a USB stick (replace `sdX`!):

```sh
sudo dd if=out/termos-*.iso of=/dev/sdX bs=4M status=progress oflag=sync
```

## Installing

1. In the tablet's firmware setup (Lenovo: power + Volume Up, or the Novo
   button): **disable Secure Boot**, boot from USB.
2. Attach the keyboard cover. The USB opens the **termOS menu**:
   - *Turn the screen*: the first entry. Pick it until the text is upright
     (portrait tablet panels start turned clockwise; some need another turn).
   - *Install termOS*: from the USB, no internet needed.
   - *Install with the newest packages*: from the Arch mirrors (needs internet).
   - *Connect to Wi-Fi*, *Open a terminal*, *Power off*, *Restart*.

   In the terminal, `termos-menu` brings the menu back, `rotscr` turns the
   screen 90 degrees per run (`rotscr normal|right|flip|left` picks one), and
   `termos-install [--online]` starts the installer directly.
3. Answer the questions in the menus: disk, device name, user, password,
   lock-screen PIN, time zone, keyboard layout, and optionally Wi-Fi (the
   installed system joins the same network, and keeps the screen turn you
   chose). Nothing is changed until you
   confirm the summary; then **the selected disk is wiped completely.**
4. Let it power off, then remove the USB (not before: the installer runs
   from it) and switch on. It boots to the lock screen; the PIN opens the
   desktop, and a short Welcome guide runs the first time.

### If the installer stops before erasing

It checks the package keys and every package on the USB first, and says
*Nothing was erased* if that fails. The usual cause is a wrong clock (package
signatures look expired): the installer prints the date it sees and the command
to set it. A very old USB fails the same way as Arch's signing keys expire;
write a new one, or use `--online`.

### Firmware boot entry

The installer adds a **termOS** entry to the firmware and puts it first in the
boot order. When reinstalling, it removes the entries of the termOS it erased.
If the firmware refuses, the installer says so at the end; termOS is still
bootable through the standard `EFI/BOOT/BOOT*.EFI` file. The installer also
skips this on 32-bit UEFI with RAM mapped above 4 GB, where the Linux kernel
can't write firmware variables safely (it corrupts memory or hangs).

Installs made before 2026-11-22 have no entry, and `termos-update` does not
change the firmware. To add one on such a device (it is listed as *Linux Boot
Manager*), first check that `cat /sys/firmware/efi/fw_platform_size` prints
`64`, then run:

```sh
sudo bootctl install
```

### Hostname

The default hostname is `termOS-<serial>`, taken from the firmware's
serial number (`/sys/class/dmi/id/product_serial`, e.g. `termOS-HA1B2C3D`).
If the firmware reports a missing or placeholder serial, it uses the
board serial instead. If that is missing too, it uses a random
6-character hex ID (e.g. `termOS-3fa91c`). You can override it at the
prompt.

## Using it

* **Panel** (icons, single tap): **Apps**, Home, Terminal, SSH, Browser, Files,
  Remote desktop, then the open windows (tap to show, tap again to
  minimize). When they don't all fit, **◀ ▶ arrows** appear at both ends;
  swiping or scrolling the icons works too. On the right: open windows (with
  close buttons), on-screen keyboard, and the status pill.
* **Status pill** (Wi-Fi, volume, battery, clock) opens **Quick Settings**:
  Wi-Fi, Bluetooth, brightness and volume sliders, rotation, keep awake,
  keyboard, screenshot, lock, power mode, Settings and power.
* **Home screen**: the SSH hosts and remote desktops (RDP/VNC) you added,
  with online status. Tap one to connect. The Home button
  minimizes the open apps to show it, and brings them back.
* **Power**: in Quick Settings or the apps tray. Restart, Shut down and
  Restart desktop ask before they act.
* **Keyboard shortcuts**: `Super+A` apps, `Super+C` Quick Settings, `Super+D`
  home screen, `Super+Tab` windows, `Super+L` lock, `Super+S` SSH hosts,
  `Super+Enter` or `Ctrl+Alt+T` terminal, `Super+B` browser, `Super+E` files,
  `Super+R` Remmina, `Super+I` settings, `Super+K` on-screen keyboard,
  `Super+Q` close window, `Super+Space` menu.
* **App windows open maximized.** When the on-screen keyboard appears they
  shrink to fit above it, so text boxes at the bottom stay visible. Turn
  this off in Settings › Display › *Open apps full-screen*.
* **Power button**: a short press suspends; holding it powers off.
* A text console is on `Ctrl+Alt+F2` (it asks for the account password).

### Lock screen

The device **always starts at the PIN screen**, and locks before it sleeps
and (unless turned off in Settings › Lock screen) when the screen turns off.

* **Forgot the PIN?** Tap *Use password*, enter the account password (there is
  a keyboard on the lock screen) and choose a new PIN.
* After 5 wrong PINs each try waits longer (30 s up to 10 min). After 10, only
  the password unlocks. Restarting doesn't reset this.
* Change the PIN in Settings › Lock screen.
* The disk is **not encrypted**. The PIN protects a device someone picks up,
  not storage that is removed or a device booted from USB.

How it works, for anyone changing it:

1. `termos-desktop@<user>.service` runs `termos-session` on tty1. There is no
   auto-login shell.
2. `termos-session` first starts a bare compositor (no shortcuts, menus or
   apps) that runs only `termos-lock --gate`. The desktop is started only
   after that unlocks. Any failure restarts at the lock screen.
3. In the desktop, `termos-session-watch` holds a logind delay lock, so the
   screen is locked before sleep, and restarts the locker if it dies (the
   compositor keeps the screen locked meanwhile).
4. `termos-pin` is the only thing that can read the PIN hash
   (`/var/lib/termos/lock`, root only). It runs through a sudo rule limited
   to that script, takes secrets on stdin and counts every attempt before
   checking it.

### Screen rotation

On first login `termos-display-setup` finds the built-in panel. It maps
the touch screen to it, and if the panel is natively portrait (like
the Duet 3's) it rotates it to landscape. If the accelerometer works,
the screen then auto-rotates. Settings are in `~/.config/termos/display.conf`:

```sh
BASE=90   # if the screen is upside down after first login, change 90 <-> 270
AUTO=1    # 0 = never auto-rotate
SENSOR_OFFSET=180   # add this if auto-rotate turns the screen upside down
```

*Rotate 90°* in Quick Settings rotates and turns auto-rotate off. Tap
*Auto-rotate* there to re-enable it.

The text console (boot messages, ttys) follows its own setting: run
`rotscr` until it is upright. The choice is kept in
`/etc/termos/console-rotation`.

### Settings app

Open it from Quick Settings (⚙) or the apps tray.

| Page        | What you can change |
|-------------|---------------------|
| Display     | brightness; **resolution and scale (automatic, or 100–300 %) for every connected screen**; **screen arrangement (drag on a map) and main screen, where new apps open**; auto-rotate, rotate, sensor-upside-down fix; open apps full-screen; home screen on/off |
| Power       | power mode, battery health, automatic battery saver, dim / screen-off / sleep timers, power button |
| Lock screen | change PIN, lock when the screen turns off, lock now |
| Security keys | key PIN, passkeys on the key, SSH keys on hardware, phone passkeys, smart cards |
| Wi-Fi       | join, forget and switch networks |
| Network     | IP address, SSH server, Bluetooth, Tailscale |
| Sound       | volume, mute |
| Wallpaper   | built-in or own pictures (`~/Pictures/Wallpapers`), any image, or a plain colour |
| Keyboard    | hardware keyboard layout, scroll direction, show/hide on-screen keyboard |
| System      | device name, timezone, update, optional CJK fonts, device info |

Settings that need admin rights (SSH server, hostname, timezone and
power button) go through `/usr/local/bin/termos-root-helper`. sudo
allows the wheel group to run only that script without a password, and
the script accepts only those specific, validated commands.

### Screens, resolution and scaling

Settings › Display lists every connected screen (built-in, external or a
desktop monitor), each with its own **Resolution** and **Scale**. After
a change, a dialog asks whether to keep it and **reverts automatically
after 15 seconds**. A wrong mode can't leave you with a black screen.
The choices are saved in `~/.config/termos/outputs.conf`
(`<output> <mode|auto> <scale>`) and applied at every login by
`termos-outputs`, and again when a monitor is plugged in.

A screen without a saved choice gets an **automatic scale** from its
physical size: about 150 % on 10" full-HD tablets, 100 % on 10" 1280×800
ones and on ordinary monitors.

### Power modes

`termos-power-profile` sets real hardware limits. This matters on CPUs
like Gemini Lake, where the usual `power-profiles-daemon` can do very
little.

| | Battery saver | Balanced (default) | Performance |
|---|---|---|---|
| CPU | base clock, no turbo | turbo on demand, power-leaning hint | always full speed |
| Intel/AMD GPU | max clock ~halfway | full | full |
| PCIe link power saving | max (`powersupersave`) | on | off |
| Wi-Fi power saving | on | on | off |
| Disk write-back | every 15 s | every 5 s | every 5 s |

The chosen mode is stored in `/etc/termos/power.conf` and applied at boot
by `termos-power.service`. With *Automatic battery saver* on, termOS
switches to Battery saver below the set level (20 % by default). It
switches back to your chosen mode once the charger is connected.

**When not in use:** the screen dims after 2 min, turns off after 5 min,
and the device sleeps after 15 min on battery (never when plugged in).
Video playback and *Keep awake* in Quick Settings keep it awake. Low (15 %) and
critical (5 %) battery warnings appear as notifications. Batteries in
mice, pens and headsets don't count. SSH connections drop when the device
sleeps and reconnect on wake; turn on *Resume where I left off* (tmux) or
mosh for a host to keep the session itself.

### SSH hosts, screenshots, Bluetooth, Tailscale

* **SSH Hosts** shows every `Host` in `~/.ssh/config` as a card with its
  address, online state and last use, plus a quick-connect box
  (`user@host` or `user@host:port`). *Add host* and the pencil edit hosts
  without touching the file (comments and other options are preserved; the
  previous file is kept as `config.termos-bak`). Per host: *Resume where I
  left off* (tmux), *Reconnect automatically*, *mosh*. *Port forwarding*
  adds `LocalForward` (a server port reachable here), `RemoteForward` (a port
  here reachable from the server) and `DynamicForward` (SOCKS proxy) lines;
  they're up while the connection is (not with mosh). *Advanced* sets a jump
  host (`ProxyJump`), agent forwarding, and any other `ssh_config` options,
  one per line. The editor can also create a key and copy it to the host. *Add host* also makes RDP and VNC
  connections (saved as Remmina profiles), and with Tailscale on, *From
  Tailscale* fills in a machine from your tailnet.
* **Screenshots**: `Print` (whole screen), `Shift+Print` (area), or the
  desktop menu (also "in 3 seconds"), Quick Settings or apps tray. Saved to
  `~/Pictures/Screenshots` and copied to the clipboard.
* **Bluetooth**: Settings › Network. The switch turns the radio off to
  save battery; *Devices…* opens the pairing manager. Phone passkeys need it on.
* **Tailscale**: Settings › Network. Turn it on, then *Sign in…* opens the
  login page in Chromium. It's off by default and uses no resources until
  enabled. Tailnet machines aren't listed on their own: add the ones you use
  with *Add host › From Tailscale*, then set their user and key like any host.
  Once signed in, *Exit node* lists the tailnet machines that offer
  themselves as one; picking one sends internet traffic through it, while
  the local network (printers, LAN hosts) stays reachable.

### Security keys, passkeys and smart cards

Everything is in **Settings › Security keys** (also *Security Keys* in the
apps tray). Any FIDO2/U2F USB key works without setup.

**SSH with a key (YubiKey and other FIDO2 keys)**

* *Create SSH key* makes an `ed25519-sk` key (`ecdsa-sk` for older keys). The
  file in `~/.ssh` is useless without the hardware key. Servers need
  OpenSSH 8.2 or newer.
* *Keep it on the security key* stores it as a resident key, so *Bring it in*
  can restore it on another computer. This needs a key PIN.
* *Ask for the PIN every time* adds the PIN to the touch at every login.
* Put it on a server with SSH Hosts › pencil › *Copy key*.

**Passkeys in Chromium**

* **On a security key:** choose the security key option, then PIN and touch.
* **On a phone (QR code):** choose the phone option and scan the code with
  the phone's camera. Both devices need Bluetooth (to prove they are close)
  and internet. No pairing is needed. If Bluetooth is off, the browser
  offers to turn it on.
* **On this device:** not possible yet. Linux has no built-in passkey store
  like Windows Hello. A password manager's browser extension is the usual
  substitute.

**Smart cards (the PIV and OpenPGP parts of a YubiKey, other CCID cards)**

* For SSH, edit a host and pick *Smart card (PIV)* or *Smart card (OpenPGP)*
  under Key, then *Copy key*. PIV uses `PKCS11Provider` (OpenSC), OpenPGP uses
  gpg-agent's SSH socket.
* gpg is set to go through `pcscd` (`/etc/gnupg/scdaemon.conf`), so it and
  PIV can share a key.
* *One-time codes* shows the authenticator codes saved on a YubiKey.

**Inside a Remote Desktop session:** in the Remmina connection turn on
*Share WebAuthn (FIDO2) credentials*, or *Share a smart card* for PIV. This
also depends on what the Windows side allows.

Security keys do **not** unlock the lock screen or sudo: those still take
the PIN and the password.

How it fits together, for anyone changing it: `ssh-agent` is socket-activated
for the user and asks through `termos-askpass`, as does ssh started without
a terminal. `gcr` is installed because gpg's other graphical PIN prompt
needs X11. Bluetooth "off" powers the adapter down rather than using
rfkill, because a blocked radio can't be switched on by the browser.

### On-screen keyboard

Squeekboard does not run until you first tap the keyboard button (or press `Super+K`), so
it uses no memory when you type on the keyboard cover. Tapping ⌨ again
hides it; until then it stays up as you move between windows. In a
terminal it adds Tab, Ctrl, Alt and arrow keys.

## Updating

*Settings › System › Update…* (or *Update termOS* in the apps tray) shows
progress and what changed. It runs `termos-update`, which also works in a
terminal and:

1. runs `sudo pacman -Syu` (all Arch packages),
2. downloads the latest termOS scripts/configs from this GitHub repo,
3. installs any packages newly added to `packages.x86_64`,
4. updates your desktop config files: files you edited are kept, and termOS's
   changes are merged into them. If both changed the same lines the new
   version wins and yours is saved in `~/.config/termos/backup-<date>/`.

Your settings (`~/.config/termos/*.conf`) are kept. Restart afterwards.

**Updating from a version without the lock screen:** that update switches
the device from auto-login to the lock screen. At the next start it asks
for the account password once and has you choose a PIN. `waybar`,
`nwg-drawer` and `network-manager-applet` are no longer used and can be
removed with pacman. (That first update still runs the old updater, which
replaces edited configs after backing them up.)

Devices installed before `termos-update` existed can get it once with:

```sh
bash <(curl -fsSL https://raw.githubusercontent.com/zeighy/termOS/main/rootfs/usr/local/bin/termos-update)
```

## Repo layout

```
build.sh                    host-side build wrapper (docker)
build/container-build.sh    runs in the Arch container: offline repo + mkarchiso
installer/termos-install    the installer (copied into the live ISO)
packages.x86_64             packages installed on the target
artwork/                    wallpapers, boot splash and theme generators
rootfs/                     copied onto the installed system
  etc/...                   zram, logind, journald, polkit, sudoers
  etc/skel/...              labwc, foot, mako, chromium, gtk configs
  usr/local/bin/termos-*    session, lock, shell, apps and helpers
  usr/local/lib/termos/     shared Python code (palette, widgets, shell)
  usr/local/share/          app-tray entries (Settings, Update) and hidden clutter
  usr/share/backgrounds/    wallpapers
  usr/share/themes/termOS/  title-bar buttons
```

Files under `/etc/skel` are only copied into the user's home directory
when the user is created. To change the desktop on an installed machine,
edit `~/.config/labwc` and so on directly.

Colours live in one file, `termosui/palette.py`. After changing it run
`artwork/make-theme.py` to regenerate the GTK, labwc, foot and mako configs.

## Known limitations

* UEFI only (no legacy BIOS boot). Secure Boot must be off.
* Webcams on Intel Gemini Lake tablets (Tablet 10, Duet 3) are not
  supported by Linux.
* Audio on some Gemini Lake tablets may need extra configuration after
  install. `sof-firmware` and `alsa-ucm-conf` are already included.
* No disk encryption. If a device is lost, treat anything stored on it as
  exposed despite the PIN. Use SSH keys with passphrases.
* X11-only apps don't run (no Xwayland is installed).
* Most testing so far is in virtual machines (UEFI 64/32-bit, eMMC, NVMe,
  offline installs). Real-hardware reports are welcome.
