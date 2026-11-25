#!/usr/bin/env python3
"""Test that the GNOME patch queue carries the exact AtomISP libcamera port."""

import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest


SCRIPT = Path(__file__).with_name("prepare-camera.py")
SPEC = importlib.util.spec_from_file_location("prepare_camera", SCRIPT)
prepare_camera = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(prepare_camera)
REPOSITORY = SCRIPT.resolve().parents[1]


class CameraIntegrationTests(unittest.TestCase):
    def make_checkout(self, root: Path, sdk_commit: str) -> Path:
        (root / "elements").mkdir(parents=True)
        (root / "patches/freedesktop-sdk").mkdir(parents=True)
        (root / "elements/freedesktop-sdk.bst").write_text(
            "kind: junction\nsources:\n- kind: git_repo\n"
            f"  ref: freedesktop-sdk-26.08.4-0-g{sdk_commit}\n",
            encoding="utf-8",
        )
        return root

    def test_prepare_adds_exact_camera_overlay(self):
        with tempfile.TemporaryDirectory() as directory:
            checkout = self.make_checkout(Path(directory), prepare_camera.SDK_COMMIT)
            destination = prepare_camera.prepare(checkout, REPOSITORY)
            overlay, port = prepare_camera.verify_bundle(REPOSITORY)
            self.assertEqual(destination.read_bytes(), overlay.read_bytes())

            sdk = Path(directory) / "sdk"
            (sdk / "elements/components").mkdir(parents=True)
            element = (
                "- components/systemd-libs.bst\n\n"
                "variables:\n  pipelines: 'auto'\n  arch-conf: ''\n  (?):\n"
                "  - target_arch == \"aarch64\":\n"
                "      pipelines: 'uvcvideo,simple,virtual,imx8-isi,mali-c55,rkisp1,rpi/vc4'\n"
                "      arch-conf: -Drpi-awb-nn=disabled\n\n"
                "  meson-local: >-\n    -Dgstreamer=enabled\n"
                "    -Dpipelines=%{pipelines}\n    -Dudev=enabled\n"
                "    -Dv4l2=true\n    -Dtracing=disabled\n    -Dtest=false\n"
                "    -Dlc-compliance=disabled\n    -Dqcam=disabled\n"
                "    -Ddocumentation=disabled\n    -Dpycamera=disabled\n"
                "    -Dcam-output-sdl2=disabled\n    %{arch-conf}\n\n"
                "sources:\n- kind: git_repo\n  url: git_https:git.libcamera.org/libcamera/libcamera.git\n"
                "  track: v*.*\n"
                f"  ref: v0.7.2-0-g{prepare_camera.LIBCAMERA_COMMIT}\n"
                "- kind: patch\n  path: patches/libcamera/disable-ipa-sign.patch\n"
                "- kind: git_module\n  path: subprojects/libyuv\n"
                "  url: chromium:libyuv/libyuv.git\n  ref: 500f45652c459cfccd20f83f297eb66cb7b015cb\n"
            )
            target = sdk / "elements/components/libcamera.bst"
            target.write_text(element, encoding="utf-8")
            subprocess.run(
                ["git", "init", "--quiet", str(sdk)],
                check=True,
                capture_output=True,
                text=True,
            )
            subprocess.run(
                ["git", "apply", "--check", str(destination)],
                cwd=sdk,
                check=True,
                capture_output=True,
                text=True,
            )
            subprocess.run(
                ["git", "apply", str(destination)],
                cwd=sdk,
                check=True,
                capture_output=True,
                text=True,
            )
            patched_element = target.read_text(encoding="utf-8")
            self.assertIn("pipelines: 'atomisp,simple,uvcvideo'", patched_element)
            self.assertIn("patches/libcamera/latte-atomisp.patch", patched_element)
            self.assertEqual(
                (sdk / "patches/libcamera/latte-atomisp.patch").read_text(
                    encoding="utf-8"
                ).replace("\r\n", "\n"),
                port.read_text(encoding="utf-8").replace("\r\n", "\n"),
            )

    def test_prepare_rejects_an_unreviewed_sdk_revision(self):
        with tempfile.TemporaryDirectory() as directory:
            checkout = self.make_checkout(Path(directory), "0" * 40)
            with self.assertRaisesRegex(SystemExit, "requires the validated"):
                prepare_camera.prepare(checkout, REPOSITORY)


if __name__ == "__main__":
    unittest.main()
