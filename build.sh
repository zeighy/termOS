#!/bin/bash
# Build the termOS installer ISO inside an Arch Linux docker container.
#   ./build.sh            -> out/termos-YYYY.MM.DD-x86_64.iso         (~2.4 GB, installs offline)
#   ./build.sh --online   -> out/termos-online-YYYY.MM.DD-x86_64.iso  (~1 GB, downloads the packages)
set -euo pipefail
cd "$(dirname "$(readlink -f "$0")")"

# docker group added but not active in this shell yet? re-run through `sg`.
if ! docker info >/dev/null 2>&1; then
    if [[ -z ${TERMOS_SG:-} ]] && getent group docker | grep -qw "$USER"; then
        exec env TERMOS_SG=1 sg docker -c "$(printf '%q ' "$0" "$@")"
    fi
    echo "Cannot talk to docker (are you in the docker group?)" >&2; exit 1
fi

FLAVOR=full
case "${1:-}" in
    "") ;;
    --online) FLAVOR=online ;;
    *) echo "usage: $0 [--online]" >&2; exit 1 ;;
esac

mkdir -p out .work
# "-test" marks a build of code that isn't on GitHub's main yet: termos-update would
# replace it with the older main, so it asks first (see termos-update).
rev=$(git rev-parse --short HEAD 2>/dev/null || echo dev)
if [[ $rev == dev ]] || ! git diff --quiet HEAD -- || [[ -n $(git ls-files --others --exclude-standard) ]] \
   || ! git merge-base --is-ancestor HEAD origin/main 2>/dev/null; then
    rev+="-test"
fi
TERMOS_VERSION="$(date +%Y.%m.%d) ($rev)"
docker pull -q archlinux:latest >/dev/null
docker run --rm --privileged \
    -v "$PWD":/src:ro \
    -v "$PWD/out":/out \
    -v "$PWD/.work":/work \
    -e HOST_UID="$(id -u)" -e HOST_GID="$(id -g)" -e TERMOS_VERSION="$TERMOS_VERSION" \
    -e TERMOS_FLAVOR="$FLAVOR" \
    archlinux:latest bash /src/build/container-build.sh
rmdir .work 2>/dev/null || true
