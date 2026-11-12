#!/usr/bin/env python3
"""Apply the pinned Mi Pad 2 integration to a disposable GNOME OS checkout."""

from pathlib import Path
import re
import sys


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    if text.count(new) == 1:
        return
    old_count = text.count(old)
    if old_count == 1:
        path.write_text(text.replace(old, new), encoding="utf-8")
        return
    raise SystemExit(f"{path}: expected one integration point, found {old_count}")


def remove_once(path: Path, snippet: str) -> None:
    text = path.read_text(encoding="utf-8")
    count = text.count(snippet)
    if count == 1:
        path.write_text(text.replace(snippet, ""), encoding="utf-8")
    elif count != 0:
        raise SystemExit(f"{path}: expected at most one removable block, found {count}")


def patch_installer(root: Path) -> None:
    directory = root / "files/gnomeos/live/proto-installer"
    installer = directory / "installer.py"
    replace_once(installer, "import locale\n",
                 "import locale\nfrom installer_transaction import begin_installation\n")
    replace_once(
        installer,
        "    def install(self, device, oem_install):\n"
        "        return self._installer.Install(device, oem_install)\n",
        "    def install(self, device, oem_install, on_ready, on_error):\n"
        "        self._installer.Install(device, oem_install,\n"
        "                                reply_handler=on_ready, error_handler=on_error)\n",
    )
    replace_once(
        installer,
        '            self._selected_row.get_block().Format("empty", {}, signature=\'sa{sv}\', dbus_interface=\'org.freedesktop.UDisks2.Block\')\n'
        "            recovery_key = self._installer.install(self._selected_row.get_device_name(), self._oem_mode)\n"
        "            self._app.display_recovery(recovery_key)\n",
        "            self._app.begin_installation(self._selected_row, self._oem_mode, erase=True)\n",
    )
    replace_once(
        installer,
        "            recovery_key = self._installer.install(selected_row.get_device_name(), self._oem_mode)\n"
        "            self._app.display_recovery(recovery_key)\n",
        "            self._app.begin_installation(selected_row, self._oem_mode, erase=False)\n",
    )
    replace_once(
        installer,
        "    def _on_error(self, message):\n",
        "    def _on_error(self, message):\n"
        '        print(f"GNOME OS installation failed: {message}", file=sys.stderr, flush=True)\n',
    )
    replace_once(
        installer,
        "    def display_recovery(self, key):\n",
        "    def begin_installation(self, selected_row, oem_mode, erase):\n"
        "        self.display_recovery(None)\n"
        "        begin_installation(selected_row.get_block(), self.installer,\n"
        "                           selected_row.get_device_name(), oem_mode, erase,\n"
        "                           self.update_recovery, self._on_error)\n\n"
        "    def update_recovery(self, key):\n"
        "        if key:\n"
        "            self._status_content.RecoveryKey.set_label(key)\n"
        "            self._status_content.RecoveryKeyDisplay.set_visible(True)\n\n"
        "    def display_recovery(self, key):\n",
    )
    replace_once(
        directory / "meson.build", "  'installer.py',\n",
        "  'installer.py',\n  'installer_transaction.py',\n",
    )


def set_staging_version(root: Path, version: str) -> None:
    if not re.fullmatch(r"latte\.[1-9][0-9]*", version):
        raise SystemExit("Staging versions must be latte.N with a positive integer N")
    replace_once(root / "include/image-version.yml",
                 "image-version: 'l.1'", f"image-version: '{version}'")


def main() -> None:
    if len(sys.argv) not in (2, 3):
        raise SystemExit("usage: prepare-upstream.py GNOME-BUILD-META-CHECKOUT [STAGING-VERSION]")
    root = Path(sys.argv[1]).resolve()
    if len(sys.argv) == 3:
        set_staging_version(root, sys.argv[2])
    patch_installer(root)

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
