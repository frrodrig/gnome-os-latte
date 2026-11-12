#!/usr/bin/env python3
"""Check update-set consistency; unsigned catalogs are not publisher authentication."""

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import shlex
import subprocess
import tempfile


def verify(directory: Path) -> dict:
    directory = directory.resolve(strict=True)
    entries = {}
    for line in (directory / "SHA256SUMS").read_text().splitlines():
        match = re.fullmatch(r"([0-9a-f]{64})  (latte-[a-zA-Z0-9_.-]+)", line)
        if not match or match[2] in entries:
            raise ValueError("Invalid or duplicate staging checksum entry")
        entries[match[2]] = match[1]
    if len(entries) != 3:
        raise ValueError("Expected exactly one kernel, /usr and verity payload")
    names = list(entries)
    kernel = [n for n in names if re.fullmatch(r"latte-kernel-x86-64_latte\.[1-9][0-9]*\.efi", n)]
    if len(kernel) != 1:
        raise ValueError("Missing versioned Latte UKI")
    version = kernel[0].removeprefix("latte-kernel-x86-64_").removesuffix(".efi")
    data = [n for n in names if re.fullmatch(rf"latte-usr-x86-64_{re.escape(version)}_[0-9a-f-]{{36}}\.raw", n)]
    hashes = [n for n in names if re.fullmatch(rf"latte-usr-x86-64_{re.escape(version)}_[0-9a-f-]{{36}}\.verity", n)]
    if len(data) != 1 or len(hashes) != 1:
        raise ValueError("Kernel, /usr and verity versions must agree")
    for name, expected in entries.items():
        with (directory / name).open("rb") as file:
            if hashlib.file_digest(file, "sha256").hexdigest() != expected:
                raise ValueError(f"Staging checksum mismatch: {name}")
    spec = importlib.util.spec_from_file_location("smoke", Path(__file__).with_name("smoke-test-image.py"))
    smoke = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(smoke)
    with tempfile.TemporaryDirectory(prefix="latte-update-check-") as temporary:
        cmdline = Path(temporary) / "cmdline"
        osrel = Path(temporary) / "osrel"
        subprocess.run([
            "objcopy", "--dump-section", f".cmdline={cmdline}",
            "--dump-section", f".osrel={osrel}", str(directory / kernel[0]),
            str(Path(temporary) / "inspection-copy.efi"),
        ], check=True)
        line = cmdline.read_bytes().rstrip(b"\0").decode()
        versions = [
            shlex.split(row.partition("=")[2])
            for row in osrel.read_bytes().rstrip(b"\0").decode().splitlines()
            if row.startswith("IMAGE_VERSION=")
        ]
        if versions != [[version]]:
            raise ValueError("UKI embedded image version does not match the update set")
    smoke.validate_cmdline(line)
    if "root=live:gnomeos" in line.split():
        raise ValueError("The installed UKI must not force live boot")
    root_hash = re.search(r"\busrhash=([0-9a-f]{64})\b", line).group(1)
    for name, half in ((data[0], root_hash[:32]), (hashes[0], root_hash[32:])):
        identifier = name.split("_")[-1].split(".")[0].replace("-", "")
        if identifier != half:
            raise ValueError("Payload UUID does not match the UKI root hash")
    subprocess.run([
        "veritysetup", "--verbose", "verify", str(directory / data[0]),
        str(directory / hashes[0]), root_hash,
    ], check=True)
    return {
        "version": version, "root_hash": root_hash, "sha256": entries,
        "result": "checksums and complete kernel/usr/verity consistency verified",
        "trust": "unsigned staging only; not publisher authentication or OTA validation",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    print(json.dumps(verify(args.directory), indent=2))
