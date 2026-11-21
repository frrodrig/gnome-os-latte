#!/usr/bin/env python3
"""Test installer callbacks without GTK, DBus, or disk access."""

import importlib.util
from pathlib import Path
import sys
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
updates = load_build_module("updates", "verify-staging-updates.py")


class InstallerTransactionTests(unittest.TestCase):
    def setUp(self):
        self.installer = Mock()
        self.ready, self.error = Mock(), Mock()

    def start(self, erase=True):
        transaction.begin_installation(
            self.installer, "virtual-test-only", False, erase,
            self.ready, self.error,
        )

    def test_erase_returns_before_completion_and_install_waits(self):
        self.start()
        self.installer.install.assert_not_called()
        self.ready.assert_not_called()
        self.installer.erase_disk.call_args.kwargs["reply_handler"]()
        self.installer.install.assert_called_once()
        self.installer.install.call_args.args[2]("test-key")
        self.ready.assert_called_once_with("test-key")

    def test_failed_erase_never_starts_installation(self):
        self.start()
        self.installer.erase_disk.call_args.kwargs["error_handler"](DBusException("NoReply"))
        self.installer.install.assert_not_called()
        self.assertIn("Disk preparation failed", self.error.call_args.args[0])

    def test_immediate_dbus_errors_are_reported(self):
        for stage in ("erase", "install"):
            with self.subTest(stage=stage):
                self.setUp()
                target = self.installer.erase_disk if stage == "erase" else self.installer.install
                target.side_effect = DBusException("AccessDenied")
                self.start(erase=stage == "erase")
                self.error.assert_called_once()
                self.ready.assert_not_called()

    def test_empty_disk_skips_erase_and_install_failure_is_reported(self):
        self.start(erase=False)
        self.installer.erase_disk.assert_not_called()
        self.installer.install.call_args.args[3](DBusException("daemon unavailable"))
        self.assertIn("Starting installation failed", self.error.call_args.args[0])
        self.ready.assert_not_called()


class StagingTests(unittest.TestCase):
    def test_stable_installer_confirms_only_the_selected_partitioned_disk(self):
        source = (
            "class Udisks:\n"
            "    def get_disks(self):\n"
            + prepare.STABLE_PARTITION_ERROR
            + "                pass\n"
            "            elif size != 0 and size < 30*1024*1024*1024:\n"
            "                pass\n"
            "            ret.append((os.path.relpath(device, '/dev'), model, size, media, invalid))\n"
            "class DiskRow:\n"
            "    def __init__(self, name, description, size, media, invalid):\n"
            "        super().__init__()\n"
            "class App:\n"
            "    def load(self):\n"
            "        for name, description, size, media, invalid in self.udisks.get_disks():\n"
            "            disk_selector.DiskList.append(DiskRow(name, description, size, media, invalid))\n"
            "class InstallButton:\n"
            "    def doInstall(self, *args):\n"
            "        selected_row = self._selector.DiskList.get_selected_row()\n"
            "        recovery_key = self._installer.install(selected_row.get_device_name(), self._oem_mode)\n"
            "        self._app.display_recovery(recovery_key)\n"
        )
        # The discovery fixture supplies the preceding body to match the real method.
        source = source.replace("            if path in partition_table_type:", "        for path in blocks:\n            if path in partition_table_type:", 1)
        with tempfile.TemporaryDirectory() as directory:
            installer = Path(directory) / "installer.py"
            installer.write_text(source)
            prepare.patch_stable_installer(installer)
            dialog = Mock()
            adw = types.SimpleNamespace(AlertDialog=Mock(return_value=dialog),
                                        ResponseAppearance=types.SimpleNamespace(DESTRUCTIVE=object()))
            namespace = {"Adw": adw, "_": lambda message: message}
            exec(compile(installer.read_text(), str(installer), "exec"), namespace)

        for action in ("cancel", "changed", "erase", "empty", "no-selection", "invalid"):
            with self.subTest(action=action):
                button = namespace["InstallButton"]()
                button._app = Mock()
                button._oem_mode = False
                button._selector = Mock()
                button.set_sensitive = Mock()
                row = Mock(needs_erase=(action != "empty"))
                row.get_selectable.return_value = action != "invalid"
                row.get_device_name.return_value = "virtual-only"
                selected = button._selector.DiskList.get_selected_row
                selected.return_value = None if action == "no-selection" else row
                adw.AlertDialog.reset_mock()
                button.doInstall()
                if action in ("empty", "no-selection", "invalid"):
                    adw.AlertDialog.assert_not_called()
                    if action == "empty":
                        button._app.begin_installation.assert_called_once_with(row, False, erase=False)
                    else:
                        button._app.begin_installation.assert_not_called()
                    continue
                button._app.begin_installation.assert_not_called()
                self.assertIn("/dev/virtual-only", adw.AlertDialog.call_args.kwargs["body"])
                callback = dialog.choose.call_args.args[2]
                dialog.choose_finish.return_value = "cancel" if action == "cancel" else "erase"
                if action == "changed":
                    selected.return_value = Mock()
                callback(dialog, object())
                if action == "erase":
                    button._app.begin_installation.assert_called_once_with(row, False, erase=True)
                else:
                    button._app.begin_installation.assert_not_called()

    def test_selects_latest_cached_stable_gnome_and_published_latte(self):
        refs = load_build_module("upstreams", "resolve-upstreams.py")
        branches = [{"name": "gnome-50"}, {"name": "gnome-51"}, {"name": "gnome-9"}, {"name": "main"}]
        self.assertEqual(refs.stable_gnome_branch(branches), "gnome-51")
        pipelines = [{"id": 3, "sha": "a" * 40}, {"id": 2, "sha": "b" * 40}]
        jobs = {3: [{"name": "build-x86_64", "status": "failed"}],
                2: [{"name": "build-x86_64", "status": "success"}]}
        self.assertEqual(refs.cached_gnome_release("gnome-51", pipelines, jobs.get),
                         {"branch": "gnome-51", "pipeline": 2, "commit": "b" * 40})
        with self.assertRaisesRegex(ValueError, "No cached"):
            refs.cached_gnome_release("gnome-51", pipelines[:1], jobs.get)
        latte = {"refs/tags/v1.2.0": "e" * 40}
        gnome = {"branch": "gnome-51", "pipeline": 2, "commit": "b" * 40}
        with patch.object(refs, "read_cached_gnome_release", return_value=gnome), \
                patch.object(refs, "tag_refs", return_value=latte), \
                patch.object(refs, "read_latte_release", return_value="v1.2.0") as release:
            mode, desktop, kernel = refs.select(None, None)
        release.assert_called_once_with("latest")
        self.assertEqual((mode, desktop["commit"], kernel["commit"]),
                         ("stable-releases", "b" * 40, "e" * 40))

    def test_prereleases_and_unreleased_replay_are_rejected(self):
        refs = load_build_module("upstreams", "resolve-upstreams.py")
        for draft, prerelease in ((True, False), (False, True)):
            with self.assertRaises(ValueError):
                refs.latte_release({"tag_name": "v1.2.0", "draft": draft, "prerelease": prerelease})
        with patch.object(refs, "tag_refs", return_value={"refs/tags/v1.2.0-alpha": "b" * 40}), \
                self.assertRaisesRegex(ValueError, "matching Linux Latte"):
            refs.select("a" * 40, "b" * 40)

    def test_stable_replay_checks_the_exact_latte_release(self):
        refs = load_build_module("upstreams", "resolve-upstreams.py")
        with patch.object(refs, "tag_refs", return_value={"refs/tags/v1.2.0": "b" * 40}), \
                patch.object(refs, "read_latte_release", return_value="v1.2.0") as release:
            mode, desktop, kernel = refs.select("a" * 40, "b" * 40)
        release.assert_called_once_with("tags/v1.2.0")
        self.assertEqual((mode, desktop["commit"], kernel["commit"]), ("replay", "a" * 40, "b" * 40))

    def test_kernel_recipe_uses_only_the_resolved_commit(self):
        template = (Path(__file__).resolve().parents[1] /
                    "elements/gnomeos/latte-kernel.bst").read_text(encoding="utf-8")
        with tempfile.TemporaryDirectory() as directory:
            element = Path(directory) / "kernel.bst"
            for commit in ("a" * 40, "b" * 40):
                element.write_text(template, encoding="utf-8")
                prepare.pin_kernel_commit(element, commit)
                self.assertEqual(element.read_text(), template.replace("LATTE_KERNEL_COMMIT", commit))
            with self.assertRaises(SystemExit):
                prepare.pin_kernel_commit(element, "c" * 40)
            with self.assertRaises(SystemExit):
                prepare.pin_kernel_commit(element, "main")

    def test_missing_removal_anchor_fails_preparation(self):
        with tempfile.TemporaryDirectory() as directory:
            element = Path(directory) / "deps.bst"
            element.write_text("- upstream/rewritten.bst\n", encoding="utf-8")
            with self.assertRaisesRegex(SystemExit, "expected one removable block"):
                prepare.remove_once(element, "- upstream/old.bst\n")

    def test_thermald_pin_preserves_commit_without_requiring_tag(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            element = root / "elements/gnomeos-deps/thermald.bst"
            element.parent.mkdir(parents=True)
            commit = "88369b42ec523787081b9bf8811b364e2a3d5f2d"
            source = "sources:\n- kind: git_repo\n  url: github:intel/thermal_daemon.git\n"
            element.write_text(f"{source}  ref: v2.15.10-0-g{commit}\n")
            for _ in range(2):
                prepare.pin_thermald_commit(root)
                self.assertEqual(element.read_text(), f"{source}  ref-format: sha1\n  ref: {commit}\n")

    def test_daemon_preserves_runtime_for_zbus_process_requests(self):
        source = (
            "struct InstallerObject {\n    has_tpm2 : bool,\n}\n"
            "impl InstallerObject {\n"
            "    fn new() -> Self {\n        Self {\n"
            "            has_tpm2 : has_tpm2,\n        }\n    }\n}\n"
            '#[interface(name = "org.gnome.Installer1")]\n'
            "impl InstallerObject {\n"
            "    #[zbus(signal)]\n    async fn installation_finished(\n"
            "}\n"
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            daemon = root / "files/gnomeos/live/proto-installer/daemon/main.rs"
            daemon.parent.mkdir(parents=True)
            daemon.write_text(source)
            prepare.patch_daemon(root)
            patched = daemon.read_text()
            prepare.patch_daemon(root)
            self.assertEqual(patched, daemon.read_text())
            self.assertIn("runtime: tokio::runtime::Handle::current()", patched)
            self.assertIn("self.runtime.spawn(async move { erase_device(&device).await })", patched)
            self.assertNotIn("let _ = run_tool", patched)

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


if __name__ == "__main__":
    unittest.main()
