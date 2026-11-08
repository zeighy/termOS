#!/bin/bash
# Build the termOS installer ISO inside an Arch Linux docker container.
# Output: ./out/termos-YYYY.MM.DD-x86_64.iso
set -euo pipefail
cd "$(dirname "$(readlink -f "$0")")"

# docker group added but not active in this shell yet? re-run through `sg`.
if ! docker info >/dev/null 2>&1; then
    if [[ -z ${TERMOS_SG:-} ]] && getent group docker | grep -qw "$USER"; then
        exec env TERMOS_SG=1 sg docker -c "$(printf '%q ' "$0" "$@")"
    fi
    echo "Cannot talk to docker (are you in the docker group?)" >&2; exit 1
fi

mkdir -p out .work
TERMOS_VERSION="$(date +%Y.%m.%d) ($(git rev-parse --short HEAD 2>/dev/null || echo dev))"
docker pull -q archlinux:latest >/dev/null
docker run --rm --privileged \
    -v "$PWD":/src:ro \
    -v "$PWD/out":/out \
    -v "$PWD/.work":/work \
    -e HOST_UID="$(id -u)" -e HOST_GID="$(id -g)" -e TERMOS_VERSION="$TERMOS_VERSION" \
    archlinux:latest bash /src/build/container-build.sh
rmdir .work 2>/dev/null || true
