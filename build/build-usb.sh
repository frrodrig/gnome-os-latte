#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"

with_updates=false
prepare_only=false
if [[ "${1:-}" == "--with-staging-updates" && $# == 1 ]]; then
    with_updates=true
elif [[ "${1:-}" == "--prepare-only" && $# == 1 ]]; then
    prepare_only=true
elif (( $# != 0 )); then
    printf 'Usage: bash build/build-usb.sh [--with-staging-updates | --prepare-only]\n' >&2
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
output="$build_root/out"
for tool in git python3; do
    if ! command -v "$tool" >/dev/null 2>&1; then
        printf 'Required tool is missing: %s\n' "$tool" >&2
        exit 1
    fi
done

if ! $prepare_only; then
    bst_bin="$(command -v "${BST_BIN:-bst}" || true)"
    if [[ -z "$bst_bin" || ! -x "$bst_bin" ]] || ! command -v make >/dev/null; then
        printf 'BuildStream (%s) and make are required to build the image.\n' "${BST_BIN:-bst}" >&2
        exit 1
    fi
    "$bst_bin" --version
    if [[ -e "$output/disk.iso" || -e "$output/upstream-revisions.json" ]]; then
        printf 'Existing output in %s; preserve it elsewhere before rebuilding.\n' "$output" >&2
        exit 1
    fi
    if $with_updates && [[ -e "$build_root/staging-updates" ]]; then
        printf '%s already exists; preserve it elsewhere before rebuilding.\n' "$build_root/staging-updates" >&2
        exit 1
    fi
fi

integration_commit="$(git -C "$repo_root" rev-parse --verify HEAD)"
mkdir -p "$build_root"
upstream="$(mktemp -d "$build_root/gnome-build-meta.XXXXXXXX")"
trap 'rm -rf -- "$upstream"' EXIT

revisions="$(python3 "$repo_root/build/resolve-upstreams.py" "$upstream/provenance.json" "$integration_commit")"
read -r gnome_url gnome_commit kernel_commit <<< "$revisions"
install -Dm644 "$upstream/provenance.json" "$build_root/upstream-revisions.json"

git -C "$upstream" init --quiet
git -C "$upstream" remote add origin "$gnome_url"
git -C "$upstream" fetch --no-tags --depth=1 origin "$gnome_commit"
git -C "$upstream" checkout --detach FETCH_HEAD
actual_commit="$(git -C "$upstream" rev-parse HEAD)"
if [[ "$actual_commit" != "$gnome_commit" ]]; then
    printf 'GNOME Build Meta revision mismatch: %s\n' "$actual_commit" >&2
    exit 1
fi

(
    prepare_args=("$upstream")
    if [[ -n "${LATTE_STAGING_VERSION:-}" ]]; then
        prepare_args+=("$LATTE_STAGING_VERSION")
    fi
    python3 "$repo_root/build/prepare-upstream.py" "${prepare_args[@]}"
    python3 "$repo_root/build/prepare-camera.py" "$upstream"
    install -Dm644 "$repo_root/files/latte/installer_transaction.py" \
        "$upstream/files/gnomeos/live/proto-installer/installer_transaction.py"

    install -Dm644 "$repo_root/elements/gnomeos/latte-kernel.bst" \
        "$upstream/elements/gnomeos/latte-kernel.bst"
    python3 "$repo_root/build/prepare-upstream.py" --kernel-ref \
        "$upstream/elements/gnomeos/latte-kernel.bst" "$kernel_commit"
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
    cp -a "$repo_root/files/latte/ucm" "$upstream/files/gnomeos/latte/"
    git -C "$upstream" add -- \
        elements/gnomeos/signed-boot.bst \
        elements/gnomeos/initramfs/deps.bst \
        elements/gnomeos/initramfs/filesystem.bst \
        elements/gnomeos/usr/deps.bst \
        elements/gnomeos/usr/layer.bst \
        elements/gnomeos/usr/manifest.bst \
        elements/gnomeos/latte-kernel.bst \
        elements/gnomeos/latte-signed-modules.bst \
        elements/gnomeos/latte-hardware.bst \
        elements/gnomeos/latte-update-images.bst \
        elements/gnomeos-deps/deps.bst \
        elements/gnomeos-deps/thermald.bst \
        files/gnomeos/latte-boot.config \
        files/gnomeos/live/proto-installer/daemon/main.rs \
        files/gnomeos/live/proto-installer/installer.py \
        files/gnomeos/live/proto-installer/meson.build \
        files/gnomeos/live/proto-installer/installer_transaction.py \
        include/image-version.yml \
        files/gnomeos/check-boot-config.py \
        files/gnomeos/latte/90-latte.hwdb \
        files/gnomeos/latte/latte.conf \
        files/gnomeos/latte/live-no-boot-writes.conf \
        files/gnomeos/latte/00-latte-disable-sysupdate.preset \
        files/gnomeos/latte/ucm \
        files/gnomeos/latte-camera-install.py \
        include/aliases.yml \
        elements/gnomeos/latte-libcamera.bst \
        elements/gnomeos/latte-libcamera-runtime.bst \
        elements/gnomeos/latte-libcamera-original-runtime.bst \
        elements/gnomeos/latte-libcamera-full.bst \
        elements/gnomeos/latte-libcamera-original-full.bst \
        elements/gnomeos/latte-camera-abi.bst \
        elements/gnomeos/latte-camera-install.bst \
        patches/latte-camera
)

if $prepare_only; then
    printf 'Upstream checkout and overlays prepared; no build requested.\n'
    exit 0
fi

make -C "$upstream/files/boot-keys" IMPORT_MODE=snakeoil

mkdir -p "$output"
bst_options=(
    --builders 2
    --max-jobs "${BST_MAX_JOBS:-2}"
    --option arch x86_64
    --option x86_64_v3 false
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
install -Dm644 "$upstream/provenance.json" "$output/upstream-revisions.json"
printf 'Image ready: %s\n' "$output/disk.iso"
