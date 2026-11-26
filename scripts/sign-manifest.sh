#!/bin/bash
# Generate, sign, or verify MANIFEST.sha256 for termOS updates.
#
#   ./scripts/sign-manifest.sh --init [--sk] [KEY_PATH]
#       Create an SSH signing key (or use an existing one) and pin its public
#       key in rootfs/etc/termos/update.pub.
#   ./scripts/sign-manifest.sh [--key KEY_PATH]
#       Write MANIFEST.sha256 (covering packages.x86_64 and rootfs/) and sign
#       it into MANIFEST.sha256.sig using ssh-keygen -Y sign.
#   ./scripts/sign-manifest.sh --check
#       Verify MANIFEST.sha256 (and MANIFEST.sha256.sig if update.pub has a key).
set -euo pipefail
cd "$(dirname "$(readlink -f "$0")")/.."

PUBFILE=rootfs/etc/termos/update.pub
MANIFEST=MANIFEST.sha256
SIG=MANIFEST.sha256.sig
NAMESPACE=termos-update
PRINCIPAL=termos-update

die() { echo "sign-manifest: $*" >&2; exit 1; }

has_pinned_key() {
    [ -r "$PUBFILE" ] && awk '!/^[[:space:]]*(#|$)/ { found=1 } END { exit !found }' "$PUBFILE"
}

list_tracked() {
    if [ -n "$(find packages.x86_64 rootfs -not -type f -not -type d 2>/dev/null)" ]; then
        die "packages.x86_64 and rootfs/ may only contain regular files and directories"
    fi
    LC_ALL=C find packages.x86_64 rootfs -type f -print0 | LC_ALL=C sort -z
}

write_manifest() {
    list_tracked | xargs -0 sha256sum > "$1"
}

verify_manifest_tree() {
    local tmp
    [ -f "$MANIFEST" ] || die "$MANIFEST is missing"
    if has_pinned_key; then
        [ -f "$SIG" ] || die "$SIG is missing (signing key is pinned in $PUBFILE)"
        ssh-keygen -Y verify -f "$PUBFILE" -I "$PRINCIPAL" -n "$NAMESPACE" -s "$SIG" < "$MANIFEST" >/dev/null \
            || die "signature verification failed for $MANIFEST"
    fi
    tmp=$(mktemp -d); trap 'rm -rf "$tmp"' RETURN
    awk '
        !/^[0-9a-f]{64}  (packages\.x86_64|rootfs\/.+)$/ { exit 1 }
        /(^|\/)\.\.(\/|$)/ { exit 1 }
        { print substr($0, 67) }
    ' "$MANIFEST" | LC_ALL=C sort > "$tmp/listed" || die "invalid line in $MANIFEST"
    list_tracked | tr '\0' '\n' > "$tmp/actual"
    if ! cmp -s "$tmp/listed" "$tmp/actual"; then
        echo "File list mismatch between $MANIFEST and working tree:" >&2
        diff -u "$tmp/listed" "$tmp/actual" >&2 || true
        exit 1
    fi
    sha256sum -c --quiet "$MANIFEST" || die "checksum mismatch in $MANIFEST"
}

# is this key's public half pinned in update.pub? (reads KEY.pub, so no passphrase prompt)
key_is_pinned() {
    local pub=$1.pub blob
    [ -r "$pub" ] || return 1
    blob=$(awk '{ print $2; exit }' "$pub")
    [ -n "$blob" ] && awk -v b="$blob" '!/^[[:space:]]*#/ && $3 == b { found=1 } END { exit !found }' "$PUBFILE"
}

find_key() {
    local cand
    for cand in "${TERMOS_SIGN_KEY:-}" "$(git config --get user.signingkey 2>/dev/null || true)" \
        "$HOME/.ssh/termosupdatesign" "$HOME/.ssh/termos_update_ed25519" "$HOME/.ssh/termos_update_ed25519_sk" \
        "$HOME/.ssh/id_ed25519_sk" "$HOME/.ssh/id_ed25519"; do
        [ -n "$cand" ] || continue
        cand=${cand/#\~/$HOME}
        [ -f "$cand" ] || continue
        # once a key is pinned, never fall back to some other key (like a personal id_ed25519)
        if has_pinned_key && ! key_is_pinned "$cand"; then
            continue
        fi
        printf '%s\n' "$cand"
        return 0
    done
    return 1
}

# devices download the git tree, so the manifest must not list files git doesn't have
check_tree_matches_git() {
    command -v git >/dev/null && git rev-parse --is-inside-work-tree >/dev/null 2>&1 || return 0
    local extra
    extra=$(git ls-files --others -- packages.x86_64 rootfs)
    if [ -n "$extra" ]; then
        echo "These files are not tracked by git (add them, or delete them if they are" >&2
        echo "build leftovers like __pycache__), so devices would never receive them:" >&2
        printf '%s\n' "$extra" | sed 's/^/  /' >&2
        die "refusing to sign"
    fi
}

init_key() {
    local sk=0 key=""
    while (( $# )); do
        case "$1" in
            --sk) sk=1 ;;
            -*) die "unknown option: $1" ;;
            *) key=$1 ;;
        esac
        shift
    done
    if [ -z "$key" ]; then
        key="$HOME/.ssh/termos_update_ed25519"
        (( sk )) && key="${key}_sk"
    fi
    key=${key/#\~/$HOME}
    if [ ! -f "$key" ] && [ ! -f "$key.pub" ]; then
        mkdir -p "$(dirname "$key")"
        chmod 700 "$(dirname "$key")" 2>/dev/null || true
        if (( sk )); then
            echo "==> Creating resident FIDO2/YubiKey signing key: $key"
            ssh-keygen -t ed25519-sk -O resident -O application=ssh:termos-update -f "$key" -C "termOS update signing key"
        else
            echo "==> Creating portable Ed25519 signing key: $key"
            ssh-keygen -t ed25519 -f "$key" -C "termOS update signing key"
        fi
    fi
    local pub="$key"
    [[ $pub == *.pub ]] || pub="$key.pub"
    [ -r "$pub" ] || die "public key not found: $pub"
    local line
    line=$(awk '{ print $1 " " $2; exit }' "$pub")
    [[ -n $line ]] || die "could not read public key from $pub"
    if grep -Fq "$line" "$PUBFILE" 2>/dev/null; then
        echo "Public key is already pinned in $PUBFILE."
    else
        printf '%s %s\n' "$PRINCIPAL" "$line" >> "$PUBFILE"
        echo "Pinned public key in $PUBFILE."
    fi
    echo "Next: run ./scripts/sign-manifest.sh to generate and sign $MANIFEST."
}

case "${1:-}" in
    -h|--help)
        sed -n '2,12p' "$0"
        exit 0 ;;
    --check)
        verify_manifest_tree
        if has_pinned_key; then
            echo "OK: $MANIFEST checksums and signature verified."
        else
            echo "OK: $MANIFEST checksums verified (no key pinned in $PUBFILE yet)."
        fi
        exit 0 ;;
    --init)
        shift
        init_key "$@"
        exit 0 ;;
esac

KEY=""
if [ "${1:-}" = --key ]; then
    KEY=${2:-}
    [ -n "$KEY" ] || die "--key needs a path"
elif [ -n "${1:-}" ]; then
    KEY=$1
fi
if [ -z "$KEY" ]; then
    KEY=$(find_key) || die "no SSH signing key found. Run: ./scripts/sign-manifest.sh --init"
fi
KEY=${KEY/#\~/$HOME}
[ -r "$KEY" ] || die "signing key not readable: $KEY"
if has_pinned_key && [ -r "$KEY.pub" ] && ! key_is_pinned "$KEY"; then
    die "$KEY is not pinned in $PUBFILE (devices would reject it). Pin it with --init first."
fi
check_tree_matches_git

write_manifest "$MANIFEST"
rm -f "$SIG"
ssh-keygen -Y sign -f "$KEY" -n "$NAMESPACE" "$MANIFEST"
if has_pinned_key; then
    verify_manifest_tree
    echo "Signed and verified $MANIFEST ($SIG)."
    echo "Commit both files as the last commit before merging (and keep the branch up to date with main)."
else
    echo "Signed $MANIFEST ($SIG). Pin your public key in $PUBFILE to enforce verification on devices."
fi
