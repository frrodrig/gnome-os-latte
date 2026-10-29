kind: manual

sources:
- kind: git_repo
  url: github:xiaomi-latte-dev/linux_latte.git
  track: main
  ref: 575dbb62ac89c5e3e49f98c386255178e29c9ec5
- kind: local
  path: files/boot-keys/modules/linux-module-cert.crt

build-depends:
- freedesktop-sdk.bst:public-stacks/runtime-gnu.bst
- freedesktop-sdk.bst:components/bc.bst
- freedesktop-sdk.bst:components/bison.bst
- freedesktop-sdk.bst:components/elfutils.bst
- freedesktop-sdk.bst:components/flex.bst
- freedesktop-sdk.bst:components/gcc.bst
- freedesktop-sdk.bst:components/grep.bst
- freedesktop-sdk.bst:components/kmod.bst
- freedesktop-sdk.bst:components/make.bst
- freedesktop-sdk.bst:components/openssl.bst
- freedesktop-sdk.bst:components/pahole.bst
- freedesktop-sdk.bst:components/perl.bst
- freedesktop-sdk.bst:components/rsync.bst
- freedesktop-sdk.bst:components/sed.bst
- freedesktop-sdk.bst:components/sign-file.bst
- freedesktop-sdk.bst:components/zstd.bst

variables:
  strip-binaries: ''

config:
  build-commands:
  - make ARCH=x86 xiaomipad2_defconfig
  - ./scripts/config --enable EFI_STUB --enable EFI_MIXED --enable MODULE_SIG --enable MODULE_SIG_FORCE --set-str SYSTEM_TRUSTED_KEYS linux-module-cert.crt
  - make ARCH=x86 olddefconfig
  - grep -qx 'CONFIG_MODULES=y' .config
  - make ARCH=x86 -j%{max-jobs} bzImage modules

  install-commands:
  - |
    version="$(make ARCH=x86 -s kernelrelease)"
    make ARCH=x86 INSTALL_MOD_PATH="%{install-root}/usr" modules_install
    rm -rf "%{install-root}/usr/lib/modules/${version}/build" \
      "%{install-root}/usr/lib/modules/${version}/source"
    install -Dm644 arch/x86/boot/bzImage \
      "%{install-root}/usr/lib/modules/${version}/vmlinuz"
    install -Dm644 System.map \
      "%{install-root}/usr/lib/modules/${version}/System.map"
    install -Dm644 .config \
      "%{install-root}/usr/lib/modules/${version}/config"
