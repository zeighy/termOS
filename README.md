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
| Desktop           | `labwc` (Wayland, stacking) + `waybar` panel |
| Terminal          | `foot` (+ `tmux`, `openssh`, `mosh`)         |
| Browser           | `chromium` (native Wayland, touch enabled)   |
| File manager      | `thunar` (+ `gvfs` for USB drives / trash)   |
| Remote desktop    | `remmina` with RDP (`freerdp`) and VNC       |
| On-screen keyboard| `squeekboard` (off until you tap ⌨)          |
| Network           | NetworkManager + tray applet (`nmtui` too)   |
| Boot              | systemd-boot, systemd initramfs, auto-login  |
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

Write it to a USB stick (replace `sdX`!):

```sh
sudo dd if=out/termos-*.iso of=/dev/sdX bs=4M status=progress oflag=sync
```

## Installing

1. In the tablet's firmware setup (Lenovo: power + Volume Up, or the Novo
   button): **disable Secure Boot**, boot from USB.
2. Attach the keyboard cover; at the root prompt run:

   ```sh
   termos-install            # offline, from the USB
   termos-install --online   # or: newest packages from the mirrors
   ```
   For `--online`, connect Wi-Fi first: `iwctl station wlan0 connect "SSID"`.
3. Answer the questions: disk, hostname, user, password, timezone, keyboard
   layout. **The selected disk is wiped completely.**
4. Reboot, remove the USB. It boots straight into the desktop.

### Hostname

The default hostname is `termOS-<serial>`, taken from the firmware's
serial number (`/sys/class/dmi/id/product_serial`, e.g. `termOS-HA1B2C3D`).
If the firmware reports a missing or placeholder serial, it uses the
board serial instead. If that is missing too, it uses a random
6-character hex ID (e.g. `termOS-3fa91c`). You can override it at the
prompt.

## Using it

* **Panel buttons** (single tap): Terminal, Browser, Files, Remote, then
  open windows, Wi-Fi tray icon, ⌨ keyboard, ⟳ rotate, brightness (tap
  cycles 100/70/40/15 %), volume (tap mutes), battery, clock, ⏻ power
  (tap to reveal Sleep / Restart / Shut down).
* **Tap the empty desktop** for a menu with the same apps plus display, Wi-Fi,
  "Update system" and power options.
* **Keyboard shortcuts**: `Super+Enter` or `Ctrl+Alt+T` terminal, `Super+B`
  browser, `Super+E` files, `Super+R` Remmina, `Super+K` on-screen keyboard,
  `Super+Q` close window, `Super+Space` menu.
* **Power button**: a short press suspends; holding it powers off.
* A text console is on `Ctrl+Alt+F2`.

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

Tapping ⟳ rotates by 90° and turns auto-rotate off. Use the desktop menu →
Display → *Auto-rotate on* to re-enable it.

### On-screen keyboard

Squeekboard does not run until you first tap ⌨ (or press `Super+K`), so
it uses no memory when you type on the keyboard cover. Tapping ⌨ again
hides it. For terminal keys (Ctrl, Esc, Tab, arrows), switch to its
*Terminal* layout with the layout key on the keyboard.

## Repo layout

```
build.sh                    host-side build wrapper (docker)
build/container-build.sh    runs in the Arch container: offline repo + mkarchiso
installer/termos-install    the installer (copied into the live ISO)
packages.x86_64             packages installed on the target
rootfs/                     copied onto the installed system
  etc/...                   zram, logind, journald, polkit, sudoers
  etc/skel/...              labwc, waybar, foot, chromium, gtk configs
  usr/local/bin/termos-*    session, rotation, keyboard, brightness helpers
```

Files under `/etc/skel` are only copied into the user's home directory
when the user is created. To change the desktop on an installed machine,
edit `~/.config/labwc`, `~/.config/waybar` and so on directly.

## Known limitations

* UEFI only (no legacy BIOS boot). Secure Boot must be off.
* Webcams on Intel Gemini Lake tablets (Tablet 10, Duet 3) are not
  supported by Linux.
* Audio on some Gemini Lake tablets may need extra configuration after
  install. `sof-firmware` and `alsa-ucm-conf` are already included.
* No screen lock (auto-login, no disk encryption). If a device is lost,
  treat anything stored on it as exposed. Use SSH keys with passphrases.
