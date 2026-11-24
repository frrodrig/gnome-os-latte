kind: manual

sources:
- kind: local
  path: files/gnomeos/latte

build-depends:
- freedesktop-sdk.bst:public-stacks/runtime-gnu.bst

variables:
  strip-binaries: ''

config:
  install-commands:
  - install -Dm644 90-latte.hwdb "%{install-root}%{indep-libdir}/udev/hwdb.d/90-latte.hwdb"
  - install -Dm644 latte.conf "%{install-root}%{indep-libdir}/modules-load.d/latte.conf"
  - install -Dm644 00-latte-disable-sysupdate.preset "%{install-root}%{indep-libdir}/systemd/system-preset/00-latte-disable-sysupdate.preset"
  - |
    ucm_root="%{install-root}/usr/share/alsa/ucm2"
    for path in \
        Intel/cht-bsw-rt5659/HiFi.conf \
        codecs/rt5659/EnableSeq.conf \
        codecs/rt5659/HeadPhones.conf \
        codecs/rt5659/HeadsetMic.conf \
        codecs/rt5659/IntMic.conf \
        codecs/rt5659/Speaker.conf \
        conf.d/cht-bsw-rt5659/cht-bsw-rt5659.conf; do
      install -Dm644 "ucm/${path}" "${ucm_root}/${path}"
    done
    install -Dm644 ucm/LICENSE-MIT \
      "%{install-root}/usr/share/licenses/gnomeos-latte/latte-ucm/LICENSE-MIT"
    install -Dm644 ucm/README.md \
      "%{install-root}/usr/share/licenses/gnomeos-latte/latte-ucm/README"
  - |
    for unit in systemd-boot-update.service systemd-boot-random-seed.service \
        systemd-boot-clear-sysfail.service systemd-bless-boot.service \
        systemd-bootctl@.service; do
      install -Dm644 live-no-boot-writes.conf \
        "%{install-root}%{indep-libdir}/systemd/system/${unit}.d/00-latte-live.conf"
    done
