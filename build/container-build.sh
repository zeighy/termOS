#!/bin/bash
# Runs INSIDE an archlinux container (see ../build.sh). Produces out/termos-*.iso
set -euo pipefail
SRC=/src
OUT=/out
WORK=/work
PROFILE=$WORK/profile
FLAVOR=${TERMOS_FLAVOR:-full}   # full: packages on the USB; online: downloads them

echo "==> Updating container and installing archiso"
sed -i 's/^#ParallelDownloads.*/ParallelDownloads = 8/' /etc/pacman.conf
pacman -Syu --noconfirm --needed archiso >/dev/null

rm -rf "${WORK:?}"/*; mkdir -p "$WORK"
cp -r /usr/share/archiso/configs/releng "$PROFILE"

echo "==> Customising live ISO profile"
cat >> "$PROFILE/profiledef.sh" <<'PDEF'

# --- termOS overrides ---
iso_name="termos"
iso_label="TERMOS_$(date --date="@${SOURCE_DATE_EPOCH:-$(date +%s)}" +%Y%m)"
iso_publisher="termOS"
iso_application="termOS install medium"
file_permissions+=(["/usr/local/bin/termos-install"]="0:0:755")
file_permissions+=(["/usr/local/bin/termos-encrypt"]="0:0:755")
file_permissions+=(["/usr/local/bin/termos-console"]="0:0:755")
file_permissions+=(["/usr/local/bin/termos-menu"]="0:0:755")
file_permissions+=(["/usr/local/bin/termos-wifi"]="0:0:755")
file_permissions+=(["/usr/local/bin/rotscr"]="0:0:755")
PDEF
if [[ $FLAVOR == online ]]; then
    echo 'iso_name="termos-online"' >> "$PROFILE/profiledef.sh"
    echo 'iso_application="termOS online install medium"' >> "$PROFILE/profiledef.sh"
fi

AIR=$PROFILE/airootfs
# releng holds pacman-init (and the rest of boot) until internet time sync, with no
# timeout. timesyncd still sets the clock whenever there is a network.
rm -f "$AIR/etc/systemd/system/sysinit.target.wants/systemd-time-wait-sync.service"
# tablets: the console upright and readable (portrait-native panels), as when installed
install -Dm755 "$SRC/rootfs/usr/local/bin/termos-console" "$AIR/usr/local/bin/termos-console"
install -Dm755 "$SRC/rootfs/usr/local/bin/rotscr" "$AIR/usr/local/bin/rotscr"
# the first screen is the termOS menu (install, Wi-Fi, turn the screen, terminal)
install -Dm755 "$SRC/installer/termos-menu" "$AIR/usr/local/bin/termos-menu"
install -Dm755 "$SRC/installer/termos-wifi" "$AIR/usr/local/bin/termos-wifi"
cat >> "$AIR/root/.zlogin" <<'ZLOGIN'

# termOS: open the menu on the tablet's own screen, once per boot
if [[ $(tty) == /dev/tty1 && ! -e /run/termos/menu-shown ]]; then
    mkdir -p /run/termos && : > /run/termos/menu-shown
    termos-menu
fi
ZLOGIN
install -Dm644 "$SRC/rootfs/etc/systemd/system/termos-console.service" "$AIR/etc/systemd/system/termos-console.service"
ln -sf /etc/systemd/system/termos-console.service "$AIR/etc/systemd/system/multi-user.target.wants/termos-console.service"
install -Dm755 "$SRC/installer/termos-install" "$AIR/usr/local/bin/termos-install"
install -Dm755 "$SRC/rootfs/usr/local/bin/termos-encrypt" "$AIR/usr/local/bin/termos-encrypt"
mkdir -p "$AIR/opt/termos"
cp "$SRC/packages.x86_64" "$AIR/opt/termos/"
echo "${TERMOS_VERSION:-dev}" > "$AIR/opt/termos/version"
cp -a "$SRC/rootfs" "$AIR/opt/termos/rootfs"
cat > "$AIR/etc/motd" <<'MOTD'

  ==================  termOS live USB  ==================
    termos-menu   install, Wi-Fi, turn the screen
    rotscr        turn the screen 90 degrees
  =======================================================

MOTD

if [[ $FLAVOR == online ]]; then
    echo "==> Online flavor: no packages on the USB (the installer downloads them)"
else
    echo "==> Downloading target packages into offline repo"
    REPO=$AIR/opt/termos/repo
    mkdir -p "$REPO" "$WORK/emptydb"
    mapfile -t PKGS < <(grep -Ev '^\s*(#|$)' "$SRC/packages.x86_64")
    # empty dbpath => pacman resolves the FULL dependency tree, not just what the container lacks
    pacman -Syw --noconfirm --dbpath "$WORK/emptydb" --cachedir "$REPO" "${PKGS[@]}" >/dev/null
    repo-add -q "$REPO/termos.db.tar.gz" "$REPO"/*.pkg.tar.zst
    echo "    $(ls "$REPO"/*.pkg.tar.zst | wc -l) packages, $(du -sh "$REPO" | cut -f1)"
fi

echo "==> Building ISO (this takes a while)"
ISO_LOG=$WORK/mkarchiso.log
ISO_OUT=$(mktemp -d "$OUT/.build-XXXXXX")
trap 'rm -rf "$ISO_OUT"' EXIT

# Capture mkarchiso's real exit status while still streaming its high-level progress lines
rc=0
mkarchiso -v -r -w "$WORK/mkarchiso" -o "$ISO_OUT" "$PROFILE" 2>&1 \
    | tee "$ISO_LOG" \
    | { grep --line-buffered -E '^\[mkarchiso\] (INFO|WARNING|ERROR)' || true; } \
    || rc=${PIPESTATUS[0]}
if (( rc != 0 )); then
    echo "==> mkarchiso failed (exit $rc). Last 40 lines of log:" >&2
    tail -n 40 "$ISO_LOG" >&2
    exit "$rc"
fi

shopt -s nullglob
built=("$ISO_OUT"/termos-*.iso)
shopt -u nullglob
if (( ${#built[@]} != 1 )); then
    echo "==> Expected 1 ISO from mkarchiso, found ${#built[@]}" >&2
    tail -n 40 "$ISO_LOG" >&2
    exit 1
fi
iso_name=$(basename "${built[0]}")
mv -f "${built[0]}" "$OUT/$iso_name"
rm -rf "$ISO_OUT" "${WORK:?}"/*
chown -R "${HOST_UID:-0}:${HOST_GID:-0}" "$OUT"
echo "==> Done:"; ls -lh "$OUT/$iso_name"
