#!/usr/bin/env python3
"""Test installer callbacks without GTK, DBus, or disk access."""

import importlib.util
from pathlib import Path
import sys
import struct
import tempfile
import types
import unittest
from unittest.mock import Mock, patch


class DBusException(Exception):
    pass


spec = importlib.util.spec_from_file_location(
    "transaction", Path(__file__).resolve().parents[1] / "files/latte/installer_transaction.py"
)
transaction = importlib.util.module_from_spec(spec)
with patch.dict(sys.modules, {"dbus": types.SimpleNamespace(DBusException=DBusException)}):
    spec.loader.exec_module(transaction)

def load_build_module(name, filename):
    module_spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(filename))
    module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(module)
    return module


prepare = load_build_module("prepare", "prepare-upstream.py")
vm = load_build_module("vm", "test-install-vm.py")
updates = load_build_module("updates", "verify-staging-updates.py")


class InstallerTransactionTests(unittest.TestCase):
    def setUp(self):
        self.block, self.installer = Mock(), Mock()
        self.ready, self.error = Mock(), Mock()

    def start(self, erase=True):
        transaction.begin_installation(
            self.block, self.installer, "virtual-test-only", False, erase,
            self.ready, self.error,
        )

    def test_erase_returns_before_completion_and_install_waits(self):
        self.start()
        self.installer.install.assert_not_called()
        self.ready.assert_not_called()
        self.block.Format.call_args.kwargs["reply_handler"]()
        self.installer.install.assert_called_once()
        self.installer.install.call_args.args[2]("test-key")
        self.ready.assert_called_once_with("test-key")

    def test_failed_erase_never_starts_installation(self):
        self.start()
        self.block.Format.call_args.kwargs["error_handler"](DBusException("NoReply"))
        self.installer.install.assert_not_called()
        self.assertIn("Disk preparation failed", self.error.call_args.args[0])

    def test_immediate_dbus_errors_are_reported(self):
        for stage in ("erase", "install"):
            with self.subTest(stage=stage):
                self.setUp()
                target = self.block.Format if stage == "erase" else self.installer.install
                target.side_effect = DBusException("AccessDenied")
                self.start(erase=stage == "erase")
                self.error.assert_called_once()
                self.ready.assert_not_called()

    def test_empty_disk_skips_erase_and_install_failure_is_reported(self):
        self.start(erase=False)
        self.block.Format.assert_not_called()
        self.installer.install.call_args.args[3](DBusException("daemon unavailable"))
        self.assertIn("Starting installation failed", self.error.call_args.args[0])
        self.ready.assert_not_called()


class StagingTests(unittest.TestCase):
    def test_update_verifier_rejects_mixed_versions_and_malformed_catalog(self):
        names = [
            "latte-kernel-x86-64_latte.1.efi",
            "latte-usr-x86-64_latte.2_aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa.raw",
            "latte-usr-x86-64_latte.1_bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb.verity",
        ]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            catalog = root / "SHA256SUMS"
            for contents in (
                "0" * 64 + "  ../outside\n",
                "\n".join("0" * 64 + "  " + name for name in names),
                "\n".join("0" * 64 + "  " + names[0] for _ in range(3)),
            ):
                with self.subTest(catalog=contents), self.assertRaises(ValueError):
                    catalog.write_text(contents)
                    updates.verify(root)

    def test_addon_section_uses_absolute_address_above_existing_sections(self):
        data = bytearray(512)
        struct.pack_into("<I", data, 0x3C, 64)
        data[64:68] = b"PE\0\0"
        struct.pack_into("<H", data, 70, 1)
        struct.pack_into("<H", data, 84, 112)
        struct.pack_into("<H", data, 88, 0x20B)
        struct.pack_into("<Q", data, 112, 0x1DD510000)
        struct.pack_into("<III", data, 208, 0x1111, 0x4000, 0x1200)
        self.assertEqual(vm.addon_initrd_address(data), 0x1DD516000)

    def test_explicit_versions_and_idempotent_preparation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "include").mkdir()
            version = root / "include/image-version.yml"
            version.write_text("image-version: 'l.1'\n")
            for invalid in ("", "l.2", "latte.0", "latte.01", "latte.1\nbad", "../latte.1"):
                with self.subTest(version=invalid), self.assertRaises(SystemExit):
                    prepare.set_staging_version(root, invalid)
            prepare.set_staging_version(root, "latte.2")
            expected = version.read_text()
            prepare.set_staging_version(root, "latte.2")
            self.assertEqual(expected, version.read_text())
            with self.assertRaises(SystemExit):
                prepare.set_staging_version(root, "latte.3")

    def test_vm_uses_new_regular_disk_and_removes_iso_for_second_boot(self):
        commands = []

        def fake_run(command, **kwargs):
            commands.append(command)
            marker = ("LATTE_STAGING_INSTALL_OK" if len(commands) == 1
                      else "LATTE_STAGING_INSTALLED_BOOT_OK")
            kwargs["stdout"].write(marker.encode())
            return types.SimpleNamespace(returncode=0)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = [root / name for name in ("iso", "code", "vars")]
            for path in paths:
                path.write_bytes(b"fixture")
            with patch.object(vm.shutil, "which", return_value="qemu"), \
                    patch.object(vm, "DISK_BYTES", 512), \
                    patch.object(vm, "instrument_iso"), \
                    patch.object(vm.subprocess, "run", side_effect=fake_run):
                vm.run(paths[0], root / "output", paths[1], paths[2], 1)
                self.assertEqual((root / "output/disposable.raw").stat().st_size, 512)
                self.assertTrue(any("id=live" in arg for arg in commands[0]))
                self.assertFalse(any("id=live" in arg for arg in commands[1]))
                self.assertTrue(any("readonly=on" in arg and "id=live" in arg for arg in commands[0]))
                with self.assertRaises(FileExistsError):
                    vm.run(paths[0], root / "output", paths[1], paths[2], 1)

    def test_vm_rejects_nonregular_input(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):
                vm.regular(Path(directory))


if __name__ == "__main__":
    unittest.main()
