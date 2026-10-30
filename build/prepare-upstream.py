#!/usr/bin/env python3
"""Apply the pinned Mi Pad 2 integration to a disposable GNOME OS checkout."""

from pathlib import Path
import sys


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    old_count = text.count(old)
    if old_count == 1:
        path.write_text(text.replace(old, new), encoding="utf-8")
        return
    if old_count == 0 and text.count(new) == 1:
        return
    raise SystemExit(f"{path}: expected one integration point, found {old_count}")


def remove_once(path: Path, snippet: str) -> None:
    text = path.read_text(encoding="utf-8")
    count = text.count(snippet)
    if count == 1:
        path.write_text(text.replace(snippet, ""), encoding="utf-8")
    elif count != 0:
        raise SystemExit(f"{path}: expected at most one removable block, found {count}")


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: prepare-upstream.py GNOME-BUILD-META-CHECKOUT")
    root = Path(sys.argv[1]).resolve()

    replace_once(
        root / "elements/gnomeos/signed-boot.bst",
        "- filename: freedesktop-sdk.bst:components/linux.bst\n  strict: true",
        "- filename: gnomeos/latte-kernel.bst\n  strict: true",
    )

    initramfs_deps = root / "elements/gnomeos/initramfs/deps.bst"
    replace_once(
        initramfs_deps,
        "- gnomeos/initramfs/signed-modules.bst",
        "- gnomeos/latte-signed-modules.bst",
    )
    remove_once(
        initramfs_deps,
        '\n(?):\n- arch in ["x86_64"]:\n'
        "    depends:\n"
        "      (>):\n"
        "      - gnomeos/initramfs/signed-nvidia-modules.bst\n",
    )

    remove_once(
        root / "elements/gnomeos/initramfs/filesystem.bst",
        "  - |\n"
        "    case '%{arch}' in\n"
        "      x86_64)\n"
        '        version="$(ls -1 /lib/modules | head -n1)"\n'
        "        mkdir -p %{install-root}/usr/lib/modules/\"${version}\"/kernel/drivers/video\n"
        '        cp /usr/lib/modules/"${version}"/kernel/drivers/video/nvidia*.ko* %{install-root}/usr/lib/modules/"${version}"/kernel/drivers/video/\n'
        '        depmod -a -b %{install-root}/usr "${version}"\n'
        '        rm -rf %{install-root}/usr/lib/modules/"${version}"/kernel/drivers/video/nvidia*.ko*\n'
        "        ;;\n"
        "    esac\n",
    )

    usr_layer = root / "elements/gnomeos/usr/layer.bst"
    remove_once(
        usr_layer,
        '(?):\n- arch in ["x86_64"]:\n'
        "    build-depends:\n"
        "      (>):\n"
        "      - gnomeos/initramfs/signed-nvidia-modules.bst\n",
    )
    remove_once(
        usr_layer,
        "  - |\n"
        "    case '%{arch}' in\n"
        "      x86_64)\n"
        '        version="$(ls -1 /lib/modules | head -n1)"\n'
        '        mkdir -p /sysroot/usr/lib/modules/"${version}"/kernel/drivers/video\n'
        '        cp /usr/lib/modules/"${version}"/kernel/drivers/video/nvidia*.ko* /sysroot/usr/lib/modules/"${version}"/kernel/drivers/video/\n'
        '        depmod -a -b /sysroot/usr "${version}"\n'
        '        rm -rf /sysroot/usr/lib/modules/"${version}"/kernel/drivers/video/nvidia*.ko*\n'
        "        ;;\n"
        "    esac\n",
    )

    usr_deps = root / "elements/gnomeos/usr/deps.bst"
    replace_once(
        usr_deps,
        "- gnomeos/initramfs/signed-modules.bst",
        "- gnomeos/latte-signed-modules.bst",
    )
    replace_once(
        usr_deps,
        "- gnomeos/sysupdate-config.bst",
        "- gnomeos/latte-hardware.bst",
    )
    remove_once(
        usr_deps,
        '\n(?):\n- arch in ["x86_64"]:\n'
        "    depends:\n"
        "      (>):\n"
        "      - gnomeos/sysupdate-nvidia-config.bst\n",
    )

    remove_once(
        root / "elements/gnomeos-deps/deps.bst",
        "- gnomeos-deps/sysupdate-config.bst\n",
    )


if __name__ == "__main__":
    main()
