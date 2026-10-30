#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck disable=SC1091
source "$repo_root/build/versions.env"

build_root="$repo_root/.build"
upstream="$build_root/gnome-build-meta"
output="$build_root/out"
prepared_marker="$build_root/gnomeos-latte-prepared.commit"
integration_fingerprint="$(
    sha256sum \
        "$repo_root/build/build-usb.sh" \
        "$repo_root/build/prepare-upstream.py" \
        "$repo_root/elements/gnomeos/latte-kernel.bst" \
        "$repo_root/elements/gnomeos/latte-signed-modules.bst" \
        "$repo_root/elements/gnomeos/latte-hardware.bst" \
        "$repo_root/files/latte/90-latte.hwdb" \
        "$repo_root/files/latte/latte.conf" \
        "$repo_root/files/latte/00-latte-disable-sysupdate.preset" |
        sha256sum | cut -d' ' -f1
)"
expected_marker="$GNOME_BUILD_META_COMMIT:$integration_fingerprint"

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
    python3 "$repo_root/build/prepare-upstream.py" "$upstream"

    install -Dm644 "$repo_root/elements/gnomeos/latte-kernel.bst" \
        "$upstream/elements/gnomeos/latte-kernel.bst"
    install -Dm644 "$repo_root/elements/gnomeos/latte-signed-modules.bst" \
        "$upstream/elements/gnomeos/latte-signed-modules.bst"
    install -Dm644 "$repo_root/elements/gnomeos/latte-hardware.bst" \
        "$upstream/elements/gnomeos/latte-hardware.bst"
    install -d "$upstream/files/gnomeos/latte"
    install -Dm644 "$repo_root/files/latte/90-latte.hwdb" \
        "$upstream/files/gnomeos/latte/90-latte.hwdb"
    install -Dm644 "$repo_root/files/latte/latte.conf" \
        "$upstream/files/gnomeos/latte/latte.conf"
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
        elements/gnomeos-deps/deps.bst \
        files/gnomeos/latte/90-latte.hwdb \
        files/gnomeos/latte/latte.conf \
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
)

if [[ ! -s "$output/disk.iso" ]]; then
    printf 'The build completed without producing disk.iso.\n' >&2
    exit 1
fi
printf 'Image ready: %s\n' "$output/disk.iso"
