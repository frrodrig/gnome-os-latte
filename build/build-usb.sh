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

for tool in git python3 bst make sha256sum; do
    if ! command -v "$tool" >/dev/null 2>&1; then
        printf 'Falta la herramienta requerida: %s\n' "$tool" >&2
        exit 1
    fi
done

if [[ ! -d "$upstream/.git" ]]; then
    mkdir -p "$build_root"
    git clone --filter=blob:none "$GNOME_BUILD_META_URL" "$upstream"
fi

if [[ -f "$prepared_marker" ]]; then
    if [[ "$(cat "$prepared_marker")" != "$expected_marker" ]]; then
        printf 'La integración del checkout existente está desactualizada; retira .build/gnome-build-meta y vuelve a compilar.\n' >&2
        exit 1
    fi
else
    if [[ -n "$(git -C "$upstream" status --porcelain)" ]]; then
        printf 'El checkout GNOME Build Meta existente tiene cambios; no se modificará.\n' >&2
        exit 1
    fi
    git -C "$upstream" fetch --filter=blob:none origin "$GNOME_BUILD_META_COMMIT"
    git -C "$upstream" checkout --detach "$GNOME_BUILD_META_COMMIT"
fi

actual_commit="$(git -C "$upstream" rev-parse HEAD)"
if [[ "$actual_commit" != "$GNOME_BUILD_META_COMMIT" ]]; then
    printf 'La revisión de GNOME Build Meta no coincide: %s\n' "$actual_commit" >&2
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
    printf 'Ya existe %s; muévelo o quítalo antes de reconstruir.\n' "$output/disk.iso" >&2
    exit 1
fi
(
    cd "$upstream"
    bst build \
        --max-jobs "${BST_MAX_JOBS:-2}" \
        --option arch x86_64 \
        --option channel stable \
        --option recc passthrough \
        gnomeos/live-image.bst
    bst artifact checkout gnomeos/live-image.bst --directory "$output"
)

if [[ ! -s "$output/disk.iso" ]]; then
    printf 'El build finalizó sin producir disk.iso.\n' >&2
    exit 1
fi
printf 'Imagen lista: %s\n' "$output/disk.iso"
