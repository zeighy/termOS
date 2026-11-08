#!/bin/bash
# Runs INSIDE an archlinux container (see ../build.sh). Produces out/termos-*.iso
set -euo pipefail
SRC=/src
OUT=/out
WORK=/work
PROFILE=$WORK/profile

echo "==> Updating container and installing archiso"
sed -i 's/^#ParallelDownloads.*/ParallelDownloads = 8/' /etc/pacman.conf
pacman -Syu --noconfirm --needed archiso >/dev/null

rm -rf "$WORK"/*; mkdir -p "$WORK"
cp -r /usr/share/archiso/configs/releng "$PROFILE"

echo "==> Customising live ISO profile"
cat >> "$PROFILE/profiledef.sh" <<'PDEF'

# --- termOS overrides ---
iso_name="termos"
iso_label="TERMOS_$(date --date="@${SOURCE_DATE_EPOCH:-$(date +%s)}" +%Y%m)"
iso_publisher="termOS"
iso_application="termOS install medium"
file_permissions+=(["/usr/local/bin/termos-install"]="0:0:755")
PDEF

AIR=$PROFILE/airootfs
install -Dm755 "$SRC/installer/termos-install" "$AIR/usr/local/bin/termos-install"
mkdir -p "$AIR/opt/termos"
cp "$SRC/packages.x86_64" "$AIR/opt/termos/"
echo "${TERMOS_VERSION:-dev}" > "$AIR/opt/termos/version"
cp -a "$SRC/rootfs" "$AIR/opt/termos/rootfs"
cat >> "$AIR/etc/motd" <<'MOTD'

  ==================  termOS  ==================
  To install termOS (ERASES the chosen disk):
      termos-install            offline, from this USB
      termos-install --online   newest packages (needs network: iwctl)
  ==============================================

MOTD

echo "==> Downloading target packages into offline repo"
REPO=$AIR/opt/termos/repo
mkdir -p "$REPO" "$WORK/emptydb"
mapfile -t PKGS < <(grep -Ev '^\s*(#|$)' "$SRC/packages.x86_64")
# empty dbpath => pacman resolves the FULL dependency tree, not just what the container lacks
pacman -Syw --noconfirm --dbpath "$WORK/emptydb" --cachedir "$REPO" "${PKGS[@]}" >/dev/null
repo-add -q "$REPO/termos.db.tar.gz" "$REPO"/*.pkg.tar.zst
echo "    $(ls "$REPO"/*.pkg.tar.zst | wc -l) packages, $(du -sh "$REPO" | cut -f1)"

echo "==> Building ISO (this takes a while)"
mkarchiso -v -r -w "$WORK/mkarchiso" -o "$OUT" "$PROFILE" 2>&1 | grep -E '^\[mkarchiso\] (INFO|WARNING|ERROR)' || true
rm -rf "$WORK"/*
ls "$OUT"/termos-*.iso >/dev/null
chown -R "${HOST_UID:-0}:${HOST_GID:-0}" "$OUT"
echo "==> Done:"; ls -lh "$OUT"
