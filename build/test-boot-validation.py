#!/usr/bin/env python3
"""Regression tests for the resolved-config and image smoke-test gates."""

import importlib.util
from pathlib import Path
import re
import shutil
import stat
import subprocess
import tempfile
import unittest
import uuid


def load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(filename))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


config = load("config", "check-boot-config.py")
smoke = load("smoke", "smoke-test-image.py")
fragment = Path(__file__).resolve().parent.parent / "files/kernel/latte-boot.config"


class BootValidationTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("veritysetup"), "veritysetup is required for corruption injection")
    def test_full_verifier_rejects_data_and_hash_corruption(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            data = root / "data"
            hashes = root / "hashes"
            data.write_bytes(b"a" * 4096 + b"b" * 4096 + b"c" * 4096)
            result = subprocess.check_output(
                ["veritysetup", "format", "--hash=sha256", str(data), str(hashes)],
                text=True,
            )
            root_hash = re.search(r"Root hash:\s*([0-9a-f]{64})", result).group(1)
            original = data.read_bytes() + hashes.read_bytes()
            image = root / "image"
            image.write_bytes(original)
            layout = {
                "sectorsize": 512,
                "partitions": [
                    {"type": smoke.USR_TYPE, "uuid": str(uuid.UUID(root_hash[:32])),
                     "start": 0, "size": data.stat().st_size // 512},
                    {"type": smoke.VERITY_TYPE, "uuid": str(uuid.UUID(root_hash[32:])),
                     "start": data.stat().st_size // 512, "size": hashes.stat().st_size // 512},
                ],
            }
            cmdline = (
                f"usrhash={root_hash} mount.usrfstype=erofs "
                "systemd.verity_usr_options=panic-on-corruption"
            )
            smoke.verify_usr(image, layout, cmdline, root)
            for offset in (4096, data.stat().st_size + 4096):
                with self.subTest(corrupt_byte=offset):
                    damaged = bytearray(original)
                    damaged[offset] ^= 1
                    image.write_bytes(damaged)
                    with self.assertRaises(subprocess.CalledProcessError):
                        smoke.verify_usr(image, layout, cmdline, root)

    def test_full_read_evidence(self):
        valid = (
            "LATTE_FULL_VERITY_READ_OK\nLATTE_VERITY_STATUS_BEGIN\n"
            "0 6022672 verity V\nLATTE_VERITY_STATUS_END\n"
        )
        smoke.check_full_read(valid)
        smoke.check_full_read(valid.replace("verity V", "verity V -"))
        smoke.check_full_read(valid.replace("0 6022672", "[ OK ] Console status\n0 6022672"))
        for invalid in (
            valid.replace("verity V", "verity C"),
            valid.replace("verity V", "verity V 1"),
            valid.replace("LATTE_FULL_VERITY_READ_OK", "not-finished"),
            valid + "device-mapper: verity: 8:3: data block 17 is corrupted",
            valid + "I/O error, dev sda, sector 10",
        ):
            with self.subTest(evidence=invalid), self.assertRaises(ValueError):
                smoke.check_full_read(invalid)

    def test_probe_finishes_before_initrd_isolation(self):
        self.assertIn("IgnoreOnIsolate=yes", smoke.PROBE_UNIT)
        self.assertIn("Before=initrd-cleanup.service initrd-switch-root.target", smoke.PROBE_UNIT)
        self.assertIn("After=sysroot-usr.mount systemd-veritysetup@usr.service", smoke.PROBE_UNIT)

    def test_builtin_requirements(self):
        required = config.requirements(fragment)
        for key in ("DM_CRYPT", "CRYPTO_AES", "CRYPTO_XTS", "DM_VERITY",
                    "EROFS_FS", "EROFS_FS_ZIP_ZSTD", "CRYPTO_SHA256", "AUTOFS_FS"):
            self.assertIn(f"CONFIG_{key}=y", required)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config"
            path.write_text("\n".join(required))
            config.check(path, fragment)
            for key in ("DM_CRYPT", "DM_VERITY", "EROFS_FS", "EROFS_FS_ZIP_ZSTD"):
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

    def test_compressed_initrd_probe_alignment(self):
        archive = smoke.cpio([("probe", stat.S_IFREG | 0o755, b"script\n")])
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "original"
            destination = Path(directory) / "test-initrd"
            for length in range(1, 9):
                with self.subTest(length=length):
                    original = b"\x28\xb5\x2f\xfd" + b"x" * length
                    source.write_bytes(original)
                    smoke.append_archive(source, destination, archive)
                    combined = destination.read_bytes()
                    offset = (len(original) + 3) & ~3
                    self.assertEqual(combined[:len(original)], original)
                    self.assertEqual(combined[len(original):offset], b"\0" * (offset - len(original)))
                    self.assertEqual(combined[offset:], archive)
                    self.assertEqual(source.read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
