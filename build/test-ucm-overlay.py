#!/usr/bin/env python3
"""Check the Latte UCM source, BuildStream install list, and build staging."""

from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
UCM_ROOT = ROOT / "files/latte/ucm"
PROFILE_FILES = (
    "Intel/cht-bsw-rt5659/HiFi.conf",
    "codecs/rt5659/EnableSeq.conf",
    "codecs/rt5659/HeadPhones.conf",
    "codecs/rt5659/HeadsetMic.conf",
    "codecs/rt5659/IntMic.conf",
    "codecs/rt5659/Speaker.conf",
    "conf.d/cht-bsw-rt5659/cht-bsw-rt5659.conf",
)


class UcmOverlayTests(unittest.TestCase):
    def test_profile_files_are_installed_and_staged(self):
        recipe = (ROOT / "elements/gnomeos/latte-hardware.bst").read_text(encoding="utf-8")
        build_script = (ROOT / "build/build-usb.sh").read_text(encoding="utf-8")

        for path in PROFILE_FILES:
            with self.subTest(path=path):
                self.assertTrue((UCM_ROOT / path).is_file())
                self.assertIn(path, recipe)

        self.assertIn('/usr/share/alsa/ucm2', recipe)
        self.assertIn("ucm/LICENSE-MIT", recipe)
        self.assertIn("ucm/README.md", recipe)
        self.assertIn("/usr/share/licenses/gnomeos-latte/latte-ucm/LICENSE-MIT", recipe)
        self.assertIn('cp -a "$repo_root/files/latte/ucm"', build_script)
        self.assertIn('files/gnomeos/latte/ucm', build_script)

    def test_includes_resolve_within_the_vendor_overlay(self):
        hifi = (UCM_ROOT / PROFILE_FILES[0]).read_text(encoding="utf-8")
        codec_includes = re.findall(r'Include\.\w+\.File "/codecs/rt5659/([^"]+)"', hifi)

        self.assertEqual(
            set(codec_includes),
            {"EnableSeq.conf", "Speaker.conf", "IntMic.conf", "HeadPhones.conf", "HeadsetMic.conf"},
        )
        for path in codec_includes:
            with self.subTest(include=path):
                self.assertTrue((UCM_ROOT / "codecs/rt5659" / path).is_file())

        card = (UCM_ROOT / PROFILE_FILES[-1]).read_text(encoding="utf-8")
        self.assertIn('Syntax 3', card)
        self.assertIn('File "/Intel/cht-bsw-rt5659/HiFi.conf"', card)

    def test_amp_control_names_match_the_latte_codec_prefixes(self):
        enable = (UCM_ROOT / "codecs/rt5659/EnableSeq.conf").read_text(encoding="utf-8")

        self.assertIn('name=\'Left Amp Input\' Left', enable)
        self.assertIn('name=\'Right Amp Input\' Right', enable)
        self.assertNotIn('Amp Input1', enable)

    def test_attribution_and_license_provenance_are_kept(self):
        notice = (UCM_ROOT / "README.md").read_text(encoding="utf-8")
        license_text = (UCM_ROOT / "LICENSE-MIT").read_text(encoding="utf-8")

        self.assertIn("c0c672d128e4e0dac497b4af7b40fea64df6ec19", notice)
        self.assertIn("Qs315490", notice)
        self.assertIn("author confirmed the MIT license", notice)
        self.assertIn("b2516c69d3df3739190b83eff57dec007fe08798", notice)
        self.assertIn("The above copyright notice and this permission notice", license_text)


if __name__ == "__main__":
    unittest.main()
