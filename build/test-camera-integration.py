#!/usr/bin/env python3
"""Test isolated camera preparation and guarded sysroot replacement."""

import hashlib
import importlib.util
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


prepare_camera = load("prepare_camera", ROOT / "build/prepare-camera.py")
install_camera = load("install_camera", ROOT / "files/camera/install-camera.py")


class PrepareTests(unittest.TestCase):
    def make_checkout(self, root, sdk_commit=prepare_camera.SDK_COMMIT):
        (root / "elements/gnomeos/usr").mkdir(parents=True)
        (root / "include").mkdir()
        (root / "patches/freedesktop-sdk").mkdir(parents=True)
        (root / "elements/freedesktop-sdk.bst").write_text(f"ref: {sdk_commit}\n")
        (root / "include/aliases.yml").write_text("aliases:\n  gnome: https://example.test/\n")
        (root / "elements/gnomeos/usr/layer.bst").write_text(
            "kind: script\nbuild-depends:\n- gnomeos/save-perms.bst\n"
            "config:\n  commands:\n  - mkdir /fakecap\n"
        )
        (root / "elements/gnomeos/usr/manifest.bst").write_text(
            "kind: collect_manifest\nbuild-depends:\n- gnomeos/usr/deps.bst\n"
        )
        return root

    def test_prepares_without_modifying_sdk_junction(self):
        with tempfile.TemporaryDirectory() as directory:
            checkout = self.make_checkout(Path(directory))
            junction = checkout / "elements/freedesktop-sdk.bst"
            before = junction.read_bytes()
            prepare_camera.prepare(checkout, ROOT)
            self.assertEqual(junction.read_bytes(), before)
            self.assertEqual(list((checkout / "patches/freedesktop-sdk").iterdir()), [])
            self.assertEqual(
                (checkout / "patches/latte-camera/atomisp.patch").read_bytes(),
                (ROOT / "files/camera/libcamera-0.7.2-atomisp.wip.patch").read_bytes(),
            )
            for name in prepare_camera.ELEMENTS:
                self.assertTrue((checkout / "elements/gnomeos" / name).is_file())
            layer = (checkout / "elements/gnomeos/usr/layer.bst").read_text()
            self.assertIn("gnomeos/latte-camera-abi.bst", layer)
            self.assertIn("python3 /usr/bin/latte-camera-install.py", layer)
            self.assertIn("libspa-libcamera.so", layer)
            self.assertIn("atomisp ipu3 simple uvcvideo virtual", layer)
            self.assertLess(layer.index("mkdir /fakecap"), layer.index("latte-camera-install.py"))
            self.assertIn(
                "- gnomeos/latte-libcamera.bst\n",
                (checkout / "elements/gnomeos/usr/manifest.bst").read_text(),
            )

    def test_rejects_unreviewed_sdk_and_old_overlay(self):
        with tempfile.TemporaryDirectory() as directory:
            checkout = self.make_checkout(Path(directory), "0" * 40)
            with self.assertRaisesRegex(SystemExit, "validated Freedesktop SDK"):
                prepare_camera.prepare(checkout, ROOT)
        with tempfile.TemporaryDirectory() as directory:
            checkout = self.make_checkout(Path(directory))
            (checkout / "patches/freedesktop-sdk/0002-latte-camera.patch").touch()
            with self.assertRaisesRegex(SystemExit, "old camera SDK overlay"):
                prepare_camera.prepare(checkout, ROOT)


class InstallTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.original, self.candidate, self.sysroot = (
            root / "original", root / "candidate", root / "sysroot"
        )
        for path in (self.original, self.candidate, self.sysroot):
            path.mkdir()
        for path in install_camera.REQUIRED:
            self.write(self.candidate, path, b"new")
            if not str(path).endswith("uncalibrated_atomisp.yaml"):
                self.write(self.original, path, b"old")
                self.write(self.sysroot, path, b"old")
        self.write(self.sysroot, install_camera.PIPEWIRE_BACKEND, b"pipewire")
        self.original_license = (
            install_camera.ORIGINAL_LICENSES / "LICENSES/GPL-2.0-or-later.txt"
        )
        self.original_license_bytes = b"original component license\n"
        self.write(self.original, self.original_license, self.original_license_bytes)
        self.write(self.sysroot, self.original_license, self.original_license_bytes)
        self.candidate_licenses = {
            path: f"candidate license {path.name}\n".encode()
            for path in install_camera.EXPECTED_LICENSE_SHA256
        }
        for path, content in self.candidate_licenses.items():
            self.write(self.candidate, path, content)
        self.license_digest_patch = patch.object(
            install_camera,
            "EXPECTED_LICENSE_SHA256",
            {
                path: hashlib.sha256(content).hexdigest()
                for path, content in self.candidate_licenses.items()
            },
        )
        self.license_digest_patch.start()
        link = install_camera.LIBDIR / "libcamera.so.0.7"
        for root in (self.original, self.candidate, self.sysroot):
            (root / link).symlink_to("libcamera.so.0.7.2")

    def tearDown(self):
        self.license_digest_patch.stop()
        self.tmp.cleanup()

    @staticmethod
    def write(root, path, content):
        target = root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)

    def run_install(self):
        install_camera.install(self.original, self.candidate, self.sysroot)

    def test_replaces_only_camera_files_and_preserves_licenses(self):
        self.run_install()
        self.assertEqual((self.sysroot / install_camera.LIBDIR / "libcamera.so.0.7.2").read_bytes(), b"new")
        self.assertEqual(os.readlink(self.sysroot / install_camera.LIBDIR / "libcamera.so.0.7"), "libcamera.so.0.7.2")
        self.assertEqual(
            (self.sysroot / self.original_license).read_bytes(),
            self.original_license_bytes,
        )
        for path, content in self.candidate_licenses.items():
            self.assertEqual((self.sysroot / path).read_bytes(), content)
        self.assertEqual((self.sysroot / install_camera.PIPEWIRE_BACKEND).read_bytes(), b"pipewire")

    def test_rejects_missing_candidate_and_conflicting_destination_before_writing(self):
        (self.candidate / "usr/bin/cam").unlink()
        with self.assertRaisesRegex(ValueError, "incomplete"):
            self.run_install()
        self.write(self.candidate, Path("usr/bin/cam"), b"new")
        self.write(self.sysroot, Path("usr/share/libcamera/ipa/simple/uncalibrated_atomisp.yaml"), b"unrelated")
        with self.assertRaisesRegex(ValueError, "unrelated file"):
            self.run_install()
        self.assertEqual((self.sysroot / "usr/bin/cam").read_bytes(), b"old")

    def test_rejects_changed_original_and_missing_pipewire(self):
        self.write(self.sysroot, Path("usr/bin/cam"), b"modified")
        with self.assertRaisesRegex(ValueError, "differs from original"):
            self.run_install()
        self.write(self.sysroot, Path("usr/bin/cam"), b"old")
        (self.sysroot / install_camera.PIPEWIRE_BACKEND).unlink()
        with self.assertRaisesRegex(ValueError, "no PipeWire"):
            self.run_install()

    def test_rejects_mismatched_composed_original_license_with_digests(self):
        changed_license = b"changed composed license\n"
        self.write(self.sysroot, self.original_license, changed_license)
        before_digest = hashlib.sha256(
            (self.sysroot / self.original_license).read_bytes()
        ).hexdigest()
        with self.assertRaisesRegex(ValueError, "differs from original libcamera") as error:
            self.run_install()
        message = str(error.exception)
        self.assertIn(hashlib.sha256(self.original_license_bytes).hexdigest(), message)
        self.assertIn(before_digest, message)
        self.assertEqual((self.sysroot / "usr/bin/cam").read_bytes(), b"old")
        after_digest = hashlib.sha256(
            (self.sysroot / self.original_license).read_bytes()
        ).hexdigest()
        self.assertEqual(after_digest, before_digest)

    def test_rejects_modified_candidate_license(self):
        path = next(
            path for path in self.candidate_licenses
            if path.name == "LGPL-2.1-or-later.txt"
        )
        self.write(self.candidate, path, b"modified candidate license\n")
        with self.assertRaisesRegex(ValueError, "license digest mismatch"):
            self.run_install()
        self.assertEqual((self.sysroot / "usr/bin/cam").read_bytes(), b"old")

    def test_rejects_missing_candidate_license(self):
        path = next(
            path for path in self.candidate_licenses
            if path.name == "LGPL-2.1-or-later.txt"
        )
        (self.candidate / path).unlink()
        with self.assertRaisesRegex(ValueError, "missing license files"):
            self.run_install()
        self.assertEqual((self.sysroot / "usr/bin/cam").read_bytes(), b"old")

    def test_rejects_missing_original_runtime_file(self):
        self.write(self.original, Path("usr/share/libcamera/pipeline/original.yaml"), b"old")
        self.write(self.sysroot, Path("usr/share/libcamera/pipeline/original.yaml"), b"old")
        with self.assertRaisesRegex(ValueError, "omits original files"):
            self.run_install()
        self.assertEqual((self.sysroot / "usr/bin/cam").read_bytes(), b"old")

    def test_rejects_symlinked_destination_directory(self):
        path = self.sysroot / "usr/share/licenses"
        shutil.rmtree(path)
        path.symlink_to(self.original, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "symlinked destination"):
            self.run_install()


if __name__ == "__main__":
    unittest.main()
