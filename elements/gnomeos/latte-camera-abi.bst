kind: script

build-depends:
- freedesktop-sdk.bst:public-stacks/buildsystem-meson.bst
- freedesktop-sdk.bst:components/libabigail.bst
- freedesktop-sdk.bst:bootstrap/grep.bst
- filename: gnomeos/latte-libcamera-original-full.bst
  config:
    location: /original-camera
- filename: gnomeos/latte-libcamera-full.bst
  config:
    location: /experimental-camera

config:
  commands:
  - |
    set -eu
    for lib in libcamera libcamera-base; do
      original="/original-camera/usr/lib/x86_64-linux-gnu/${lib}.so.0.7.2"
      candidate="/experimental-camera/usr/lib/x86_64-linux-gnu/${lib}.so.0.7.2"
      old_debug="/original-camera/usr/lib/debug/usr/lib/x86_64-linux-gnu/${lib}.so.0.7.2.debug"
      new_debug="/experimental-camera/usr/lib/debug/usr/lib/x86_64-linux-gnu/${lib}.so.0.7.2.debug"
      test -s "$old_debug" && test -s "$new_debug"
      old_soname="$(readelf -d "$original" | grep '(SONAME)')"
      new_soname="$(readelf -d "$candidate" | grep '(SONAME)')"
      test -n "$old_soname" && test "$old_soname" = "$new_soname"
      result=0
      abidiff --no-show-locs "$old_debug" "$new_debug" || result="$?"
      if [ "$result" -ne 0 ] && [ "$result" -ne 4 ]; then
        echo "Incompatible ABI for $lib (abidiff exit $result)" >&2
        exit 1
      fi
    done
    mkdir -p "%{install-root}"
    echo "libcamera ABI checked" >"%{install-root}/latte-camera-abi-checked"
