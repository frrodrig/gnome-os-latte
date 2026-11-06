#!/usr/bin/env python3
"""Regression tests for the resolved-config and image smoke-test gates."""

import importlib.util
from pathlib import Path
import stat
import tempfile
import unittest


def load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(filename))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


config = load("config", "check-boot-config.py")
smoke = load("smoke", "smoke-test-image.py")
fragment = Path(__file__).resolve().parent.parent / "files/kernel/latte-boot.config"


class BootValidationTests(unittest.TestCase):
    def test_builtin_requirements(self):
        required = config.requirements(fragment)
        for key in ("DM_VERITY", "EROFS_FS", "EROFS_FS_ZIP_ZSTD", "CRYPTO_SHA256"):
            self.assertIn(f"CONFIG_{key}=y", required)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config"
            path.write_text("\n".join(required))
            config.check(path, fragment)
            for key in ("DM_VERITY", "EROFS_FS", "EROFS_FS_ZIP_ZSTD"):
                with self.subTest(key=key):
                    path.write_text("\n".join(required).replace(f"CONFIG_{key}=y", f"CONFIG_{key}=m"))
                    with self.assertRaises(SystemExit):
                        config.check(path, fragment)

    def test_verity_algorithm(self):
        header = b"verity\0\0" + b"\0" * 24 + b"sha256\0" + b"\0" * 25
        self.assertEqual(smoke.verity_algorithm(header), "sha256")
        with self.assertRaises(ValueError):
            smoke.verity_algorithm(header.replace(b"sha256", b"sha512"))
        with self.assertRaises(ValueError):
            smoke.verity_algorithm(b"\0" * 512)

    def test_integrity_cmdline(self):
        line = "usrhash=" + "a" * 64 + " mount.usrfstype=erofs systemd.verity_usr_options=panic-on-corruption"
        smoke.validate_cmdline(line)
        for invalid in (line + " rd.verity=0", line.replace("panic-on-corruption", "ignore-corruption"), line.replace("usrhash=", "missing=")):
            with self.subTest(cmdline=invalid), self.assertRaises(ValueError):
                smoke.validate_cmdline(invalid)

    def test_probe_archive(self):
        data = smoke.cpio([
            ("probe", stat.S_IFREG | 0o755, b"script\n"),
            ("wants/probe", stat.S_IFLNK | 0o777, b"../probe"),
        ])
        offset = 0
        entries = {}
        while True:
            self.assertEqual(data[offset:offset + 6], b"070701")
            fields = [int(data[offset + 6 + i * 8:offset + 14 + i * 8], 16) for i in range(13)]
            size, name_size = fields[6], fields[11]
            offset += 110
            name = data[offset:offset + name_size - 1].decode()
            offset = (offset + name_size + 3) & ~3
            contents = data[offset:offset + size]
            offset = (offset + size + 3) & ~3
            if name == "TRAILER!!!":
                break
            entries[name] = (fields[1], contents)
        self.assertEqual(entries["probe"], (stat.S_IFREG | 0o755, b"script\n"))
        self.assertEqual(entries["wants/probe"], (stat.S_IFLNK | 0o777, b"../probe"))


if __name__ == "__main__":
    unittest.main()
