kind: script

build-depends:
- freedesktop-sdk.bst:components/jq.bst
- freedesktop-sdk.bst:public-stacks/runtime-gnu.bst
- filename: gnomeos/usr/image.bst
  config:
    location: /usr-image
- filename: gnomeos/signed-boot.bst
  config:
    location: /signed-boot

config:
  commands:
  - |
    set -eu
    usr_uuid="$(jq -er '(.[] | select(.file | endswith("/10-usr.conf"))).uuid' /usr-image/mini.repart.json)"
    verity_uuid="$(jq -er '(.[] | select(.type | test("^usr-.*-verity$"))).uuid' /usr-image/mini.repart.json)"
    cp /usr-image/mini.usr.raw "%{install-root}/latte-usr-%{systemd-arch}_%{image-version}_${usr_uuid}.raw"
    cp /usr-image/mini.usr-verity.raw "%{install-root}/latte-usr-%{systemd-arch}_%{image-version}_${verity_uuid}.verity"
    cp "/signed-boot/efi/EFI/Linux/gnomeos_%{image-version}.efi" \
      "%{install-root}/latte-kernel-%{systemd-arch}_%{image-version}.efi"
  - |
    cd "%{install-root}"
    sha256sum latte-* > SHA256SUMS
