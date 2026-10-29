kind: manual

build-depends:
- filename: gnomeos/latte-kernel.bst
  strict: true
- freedesktop-sdk.bst:components/findutils.bst
- freedesktop-sdk.bst:components/sign-file.bst
- freedesktop-sdk.bst:components/zstd.bst
- freedesktop-sdk.bst:public-stacks/runtime-gnu.bst

variables:
  strip-binaries: ''

config:
  install-commands:
  - |
    mkdir -p "%{install-root}/usr/lib"
    cp -rT /usr/lib/modules "%{install-root}/usr/lib/modules"
  - |
    version="$(ls -1 /usr/lib/modules | head -n1)"
    cp "/usr/lib/modules/${version}/vmlinuz" \
      "%{install-root}/usr/lib/modules/${version}/vmlinuz"
  - |
    openssl x509 -inform PEM -outform DER \
      -in linux-module-cert.crt \
      -out "%{install-root}/usr/lib/modules/linux-module-cert.cer"
  - |
    find "%{install-root}/usr/lib/modules" -type f -name "*.ko.zst" \
      -exec unzstd --rm {} ';'
  - |
    find "%{install-root}/usr/lib/modules" -type f -name "*.ko" \
      -exec sign-file sha512 MODULES.key \
        "%{install-root}/usr/lib/modules/linux-module-cert.cer" {} ';' \
      -exec zstd --rm {} ';'

sources:
- kind: local
  path: files/boot-keys/MODULES.key
- kind: local
  path: files/boot-keys/modules/linux-module-cert.crt
