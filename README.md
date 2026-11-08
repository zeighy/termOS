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
| Apps tray         | `nwg-drawer` (Papirus icons)                 |
| Text / images     | `mousepad`, `ristretto`                      |
| Video / music     | `mpv`, `parole`                              |
| Settings          | `termos-settings` (GTK3, touch-friendly)     |
| SSH hosts         | `termos-ssh` (one-tap hosts from `~/.ssh/config`, mosh option) |
| Power             | `termos-power-profile` (saver / balanced / performance), `swayidle` + `wlopm` |
| Notifications     | `mako`                                       |
| Extras            | `grim`/`slurp` screenshots, `blueman`, `tailscale` |
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

* **Panel buttons** (single tap): **Apps** (full-screen app tray), Terminal,
  SSH, Browser, Files, Remote, then open windows (as icons), Wi-Fi tray icon,
  ☾/☕ keep-awake, ⚙ Settings,
  ⌨ keyboard, ⟳ rotate, brightness (tap cycles 100/70/40/15 %), volume (tap
  cycles 25/50/75/100 %/mute; right-click opens sound settings), battery,
  clock, ⏻ power (tap to reveal Sleep / Restart / Shut down). Tapping the
  battery opens the Power settings.
* **Tap the empty desktop** for a menu with the same apps plus display, Wi-Fi,
  "Update system" and power options.
* **Keyboard shortcuts**: `Super+A` apps, `Super+S` SSH hosts, `Super+Enter`
  or `Ctrl+Alt+T` terminal, `Super+B` browser, `Super+E` files, `Super+R` Remmina, `Super+I`
  settings, `Super+K` on-screen keyboard, `Super+Q` close window,
  `Super+Space` menu.
* **App windows open maximized.** When the on-screen keyboard appears they
  shrink to fit above it, so text boxes at the bottom stay visible. Turn
  this off in Settings › Display › *Open apps full-screen*.
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

### Settings app

Tap ⚙ in the panel, or open *Settings* from the apps tray.

| Page      | What you can change |
|-----------|---------------------|
| Display   | brightness; **resolution and scale (100–300 %) for every connected screen**; auto-rotate, rotate, flip auto-rotate (built-in screens); open apps full-screen |
| Power     | power mode, battery health, automatic battery saver, dim / screen-off / sleep timers, power button |
| Sound     | volume, mute |
| Wallpaper | built-in or own pictures (`~/Pictures/Wallpapers`), any image, or a plain colour |
| Keyboard  | hardware keyboard layout, show/hide on-screen keyboard |
| Network   | Wi-Fi connections, IP address, SSH server, Bluetooth, Tailscale |
| System    | hostname, timezone, update, device info |

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
`termos-outputs`. A monitor plugged in after login uses its default
mode until the next login.

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
Video playback and the ☕/☾ panel button keep it awake. Low (15 %) and
critical (5 %) battery warnings appear as notifications. SSH
connections drop when the device sleeps, but mosh sessions reconnect
(use the mosh switch in *SSH Hosts*).

### SSH hosts, screenshots, Bluetooth, Tailscale

* **SSH** in the panel lists every `Host` in your `~/.ssh/config` as a big
  button, has a quick-connect box, and an optional *use mosh* switch.
  *Edit host list* opens the file (creating a commented example).
* **Screenshots**: `Print` (whole screen), `Shift+Print` (area), or the
  desktop menu / apps tray (also "in 3 seconds"). Saved to
  `~/Pictures/Screenshots` and copied to the clipboard.
* **Bluetooth**: Settings › Network. The switch turns the radio off to
  save battery; *Devices…* opens the pairing manager.
* **Tailscale**: Settings › Network. Turn it on, then *Sign in…* opens the
  login page in Chromium. It's off by default and uses no resources until
  enabled.

### On-screen keyboard

Squeekboard does not run until you first tap ⌨ (or press `Super+K`), so
it uses no memory when you type on the keyboard cover. Tapping ⌨ again
hides it. For terminal keys (Ctrl, Esc, Tab, arrows), switch to its
*Terminal* layout with the layout key on the keyboard.

## Updating

*Settings › System › Update now* (or *Update system* in the desktop menu)
runs `termos-update`, which:

1. runs `sudo pacman -Syu` (all Arch packages),
2. downloads the latest termOS scripts/configs from this GitHub repo,
3. installs any packages newly added to `packages.x86_64`,
4. refreshes your desktop config files, saving any you changed in
   `~/.config/termos/backup-<date>/`.

Your settings (`~/.config/termos/*.conf`) are kept. Restart the desktop
afterwards: tap the desktop › Power › Restart desktop.

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
artwork/                    wallpaper source (SVG)
rootfs/                     copied onto the installed system
  etc/...                   zram, logind, journald, polkit, sudoers
  etc/skel/...              labwc, waybar, foot, chromium, gtk configs
  usr/local/bin/termos-*    session, settings, update, rotation, keyboard, volume helpers
  usr/local/share/          app-tray entries (Settings, Update) and hidden clutter
  usr/share/backgrounds/    default wallpaper
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
