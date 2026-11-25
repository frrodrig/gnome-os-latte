#!/usr/bin/env python3
"""Prepare an isolated AtomISP libcamera without changing the SDK junction."""

from pathlib import Path
import shutil
import sys


SDK_COMMIT = "114ae909ec9881958bd507c8b4414aa33f758d2b"
LIBCAMERA_COMMIT = "191e202178f02430b5942397c70d215cdd2056fa"
ELEMENTS = (
    "latte-libcamera.bst",
    "latte-libcamera-runtime.bst",
    "latte-libcamera-original-runtime.bst",
    "latte-libcamera-full.bst",
    "latte-libcamera-original-full.bst",
    "latte-camera-abi.bst",
    "latte-camera-install.bst",
)

DEPENDENCIES = """- gnomeos/save-perms.bst
- gnomeos/latte-camera-abi.bst
- gnomeos/latte-camera-install.bst
- freedesktop-sdk.bst:bootstrap/grep.bst
- filename: gnomeos/latte-libcamera-original-runtime.bst
  config:
    location: /latte-original-camera
- filename: gnomeos/latte-libcamera-runtime.bst
  config:
    location: /latte-experimental-camera
"""

COMMANDS = """  - mkdir /fakecap
  - python3 /usr/bin/latte-camera-install.py /latte-original-camera /latte-experimental-camera /sysroot
  - |
    set -eu
    test -s /latte-camera-abi-checked
    libdir=/sysroot/usr/lib/x86_64-linux-gnu
    export LD_LIBRARY_PATH="$libdir"
    ldd -r "$libdir/spa-0.2/libcamera/libspa-libcamera.so" >/tmp/latte-pipewire-ldd.log 2>&1 || {
      cat /tmp/latte-pipewire-ldd.log >&2
      exit 1
    }
    if grep -E 'not found|undefined symbol' /tmp/latte-pipewire-ldd.log; then
      echo "PipeWire's libcamera backend has unresolved dependencies" >&2
      exit 1
    fi
    LIBCAMERA_LOG_LEVELS=Camera:DEBUG /sysroot/usr/bin/cam --list >/tmp/latte-camera-list.log 2>&1 || {
      cat /tmp/latte-camera-list.log >&2
      exit 1
    }
    cat /tmp/latte-camera-list.log
    for pipeline in atomisp ipu3 simple uvcvideo virtual; do
      grep -F "Found registered pipeline handler '$pipeline'" /tmp/latte-camera-list.log >/dev/null || {
        echo "Missing libcamera pipeline: $pipeline" >&2
        exit 1
      }
    done
"""


def insert_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    if text.count(old) != 1 or new in text:
        raise SystemExit(f"{path}: unexpected or already modified integration point")
    path.write_text(text.replace(old, new), encoding="utf-8")


def copy_new(source: Path, destination: Path) -> None:
    if not source.is_file():
        raise SystemExit(f"Camera integration file missing: {source}")
    if destination.exists():
        raise SystemExit(f"Refusing to overwrite an existing camera integration file: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)


def prepare(checkout: Path, repository: Path) -> None:
    junction = checkout / "elements/freedesktop-sdk.bst"
    if not junction.is_file() or SDK_COMMIT not in junction.read_text(encoding="utf-8"):
        raise SystemExit(f"AtomISP requires the validated Freedesktop SDK revision {SDK_COMMIT}.")
    if (checkout / "patches/freedesktop-sdk/0002-latte-camera.patch").exists():
        raise SystemExit("The old camera SDK overlay is present; refusing to invalidate upstream caches.")
    element = repository / "elements/gnomeos/latte-libcamera.bst"
    if not element.is_file() or f"ref: v0.7.2-0-g{LIBCAMERA_COMMIT}" not in element.read_text(encoding="utf-8"):
        raise SystemExit("The experimental libcamera recipe does not match the validated revision.")

    for name in ELEMENTS:
        copy_new(repository / "elements/gnomeos" / name, checkout / "elements/gnomeos" / name)
    camera = repository / "files/camera"
    copy_new(camera / "libcamera-0.7.2-atomisp.wip.patch", checkout / "patches/latte-camera/atomisp.patch")
    copy_new(camera / "disable-ipa-sign.patch", checkout / "patches/latte-camera/disable-ipa-sign.patch")
    copy_new(camera / "install-camera.py", checkout / "files/gnomeos/latte-camera-install.py")

    aliases = checkout / "include/aliases.yml"
    insert_once(
        aliases,
        "aliases:\n",
        "aliases:\n  latte_libcamera: https://git.libcamera.org/\n"
        "  latte_chromium: https://chromium.googlesource.com/\n",
    )
    layer = checkout / "elements/gnomeos/usr/layer.bst"
    insert_once(layer, "- gnomeos/save-perms.bst\n", DEPENDENCIES)
    insert_once(layer, "  - mkdir /fakecap\n", COMMANDS)
    insert_once(
        checkout / "elements/gnomeos/usr/manifest.bst",
        "- gnomeos/usr/deps.bst\n",
        "- gnomeos/usr/deps.bst\n- gnomeos/latte-libcamera.bst\n",
    )


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: prepare-camera.py GNOME-BUILD-META-CHECKOUT")
    prepare(Path(sys.argv[1]).resolve(), Path(__file__).resolve().parents[1])


if __name__ == "__main__":
    main()
