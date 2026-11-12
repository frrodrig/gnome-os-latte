#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck disable=SC1091
source "$repo_root/build/versions.env"

with_updates=false
if [[ "${1:-}" == "--with-staging-updates" && $# == 1 ]]; then
    with_updates=true
elif (( $# != 0 )); then
    printf 'Usage: LATTE_STAGING_VERSION=latte.N bash build/build-usb.sh [--with-staging-updates]\n' >&2
    exit 1
fi
if [[ -n "${LATTE_STAGING_VERSION:-}" ]] &&
   [[ ! "$LATTE_STAGING_VERSION" =~ ^latte\.[1-9][0-9]*$ ]]; then
    printf 'LATTE_STAGING_VERSION must be latte.N, with a positive integer N.\n' >&2
    exit 1
fi
if $with_updates && [[ -z "${LATTE_STAGING_VERSION:-}" ]]; then
    printf 'Staging updates require an explicit LATTE_STAGING_VERSION=latte.N.\n' >&2
    exit 1
fi

build_root="$repo_root/.build"
upstream="$build_root/gnome-build-meta"
output="$build_root/out"
prepared_marker="$build_root/gnomeos-latte-prepared.commit"
integration_fingerprint="$(
    sha256sum \
        "$repo_root/build/build-usb.sh" \
        "$repo_root/build/prepare-upstream.py" \
        "$repo_root/build/check-boot-config.py" \
        "$repo_root/files/kernel/latte-boot.config" \
        "$repo_root/elements/gnomeos/latte-kernel.bst" \
        "$repo_root/elements/gnomeos/latte-signed-modules.bst" \
        "$repo_root/elements/gnomeos/latte-hardware.bst" \
        "$repo_root/elements/gnomeos/latte-update-images.bst" \
        "$repo_root/files/latte/90-latte.hwdb" \
        "$repo_root/files/latte/latte.conf" \
        "$repo_root/files/latte/live-no-boot-writes.conf" \
        "$repo_root/files/latte/installer_transaction.py" \
        "$repo_root/files/latte/00-latte-disable-sysupdate.preset" |
        sha256sum | cut -d' ' -f1
)"
expected_marker="$GNOME_BUILD_META_COMMIT:$integration_fingerprint:${LATTE_STAGING_VERSION:-l.1}"

for tool in git python3 make sha256sum; do
    if ! command -v "$tool" >/dev/null 2>&1; then
        printf 'Required tool is missing: %s\n' "$tool" >&2
        exit 1
    fi
done

if [[ -n "${BST_BIN:-}" ]]; then
    bst_bin="$BST_BIN"
else
    bst_bin="$(command -v bst || true)"
fi
if [[ -z "$bst_bin" || ! -x "$bst_bin" ]]; then
    printf 'Required BuildStream executable is missing: %s\n' "${BST_BIN:-bst}" >&2
    exit 1
fi
"$bst_bin" --version

if [[ ! -d "$upstream/.git" ]]; then
    mkdir -p "$build_root"
    git clone --filter=blob:none "$GNOME_BUILD_META_URL" "$upstream"
fi

if [[ -f "$prepared_marker" ]]; then
    if [[ "$(cat "$prepared_marker")" != "$expected_marker" ]]; then
        printf 'The existing checkout integration is stale; remove .build/gnome-build-meta and rebuild.\n' >&2
        exit 1
    fi
else
    if [[ -n "$(git -C "$upstream" status --porcelain)" ]]; then
        printf 'The existing GNOME Build Meta checkout has changes; it will not be modified.\n' >&2
        exit 1
    fi
    git -C "$upstream" fetch --filter=blob:none origin "$GNOME_BUILD_META_COMMIT"
    git -C "$upstream" checkout --detach "$GNOME_BUILD_META_COMMIT"
fi

actual_commit="$(git -C "$upstream" rev-parse HEAD)"
if [[ "$actual_commit" != "$GNOME_BUILD_META_COMMIT" ]]; then
    printf 'GNOME Build Meta revision mismatch: %s\n' "$actual_commit" >&2
    exit 1
fi

if [[ ! -f "$prepared_marker" ]]; then
    prepare_args=("$upstream")
    if [[ -n "${LATTE_STAGING_VERSION:-}" ]]; then
        prepare_args+=("$LATTE_STAGING_VERSION")
    fi
    python3 "$repo_root/build/prepare-upstream.py" "${prepare_args[@]}"
    install -Dm644 "$repo_root/files/latte/installer_transaction.py" \
        "$upstream/files/gnomeos/live/proto-installer/installer_transaction.py"

    install -Dm644 "$repo_root/elements/gnomeos/latte-kernel.bst" \
        "$upstream/elements/gnomeos/latte-kernel.bst"
    install -Dm644 "$repo_root/elements/gnomeos/latte-signed-modules.bst" \
        "$upstream/elements/gnomeos/latte-signed-modules.bst"
    install -Dm644 "$repo_root/elements/gnomeos/latte-hardware.bst" \
        "$upstream/elements/gnomeos/latte-hardware.bst"
    install -Dm644 "$repo_root/elements/gnomeos/latte-update-images.bst" \
        "$upstream/elements/gnomeos/latte-update-images.bst"
    install -Dm644 "$repo_root/files/kernel/latte-boot.config" \
        "$upstream/files/gnomeos/latte-boot.config"
    install -Dm644 "$repo_root/build/check-boot-config.py" \
        "$upstream/files/gnomeos/check-boot-config.py"
    install -d "$upstream/files/gnomeos/latte"
    install -Dm644 "$repo_root/files/latte/90-latte.hwdb" \
        "$upstream/files/gnomeos/latte/90-latte.hwdb"
    install -Dm644 "$repo_root/files/latte/latte.conf" \
        "$upstream/files/gnomeos/latte/latte.conf"
    install -Dm644 "$repo_root/files/latte/live-no-boot-writes.conf" \
        "$upstream/files/gnomeos/latte/live-no-boot-writes.conf"
    install -Dm644 "$repo_root/files/latte/00-latte-disable-sysupdate.preset" \
        "$upstream/files/gnomeos/latte/00-latte-disable-sysupdate.preset"
    git -C "$upstream" add -- \
        elements/gnomeos/signed-boot.bst \
        elements/gnomeos/initramfs/deps.bst \
        elements/gnomeos/usr/deps.bst \
        elements/gnomeos/usr/layer.bst \
        elements/gnomeos/latte-kernel.bst \
        elements/gnomeos/latte-signed-modules.bst \
        elements/gnomeos/latte-hardware.bst \
        elements/gnomeos/latte-update-images.bst \
        elements/gnomeos-deps/deps.bst \
        files/gnomeos/latte-boot.config \
        files/gnomeos/live/proto-installer/installer.py \
        files/gnomeos/live/proto-installer/meson.build \
        files/gnomeos/live/proto-installer/installer_transaction.py \
        include/image-version.yml \
        files/gnomeos/check-boot-config.py \
        files/gnomeos/latte/90-latte.hwdb \
        files/gnomeos/latte/latte.conf \
        files/gnomeos/latte/live-no-boot-writes.conf \
        files/gnomeos/latte/00-latte-disable-sysupdate.preset
fi

if [[ ! -s "$upstream/files/boot-keys/MODULES.key" ||
      ! -s "$upstream/files/boot-keys/modules/linux-module-cert.crt" ]]; then
    make -C "$upstream/files/boot-keys" IMPORT_MODE=snakeoil
fi

if [[ ! -f "$prepared_marker" ]]; then
    printf '%s\n' "$expected_marker" > "$prepared_marker"
fi

mkdir -p "$output"
if [[ -e "$output/disk.iso" ]]; then
    printf '%s already exists; move or remove it before rebuilding.\n' "$output/disk.iso" >&2
    exit 1
fi
if $with_updates && [[ -e "$build_root/staging-updates" ]]; then
    printf '%s already exists; preserve it elsewhere before rebuilding.\n' "$build_root/staging-updates" >&2
    exit 1
fi
bst_options=(
    --builders 2
    --max-jobs "${BST_MAX_JOBS:-2}"
    --option arch x86_64
    --option channel stable
    --option recc passthrough
)
(
    cd "$upstream"
    "$bst_bin" "${bst_options[@]}" build gnomeos/live-image.bst
    "$bst_bin" "${bst_options[@]}" artifact checkout gnomeos/live-image.bst \
        --directory "$output"
    if $with_updates; then
        "$bst_bin" "${bst_options[@]}" build gnomeos/latte-update-images.bst
        "$bst_bin" "${bst_options[@]}" artifact checkout gnomeos/latte-update-images.bst \
            --directory "$build_root/staging-updates"
    fi
)

if [[ ! -s "$output/disk.iso" ]]; then
    printf 'The build completed without producing disk.iso.\n' >&2
    exit 1
fi
printf 'Image ready: %s\n' "$output/disk.iso"
