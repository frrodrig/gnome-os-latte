#!/usr/bin/env python3
"""Boot the produced UKI kernel/initrd with a read-only USB ISO in QEMU."""

import argparse
import json
from pathlib import Path
import re
import shutil
import stat
import struct
import subprocess
import tempfile

from importlib.util import module_from_spec, spec_from_file_location


ESP_TYPE = "c12a7328-f81f-11d2-ba4b-00a0c93ec93b"
VERITY_TYPE = "77ff5f63-e7b6-4633-acf4-1565b864c0e6"
USR_TYPE = "8484680c-9521-48c6-9c11-b0720656f69e"
PROBE_UNIT = """[Unit]
DefaultDependencies=no
IgnoreOnIsolate=yes
Requires=sysroot-usr.mount systemd-veritysetup@usr.service
After=sysroot-usr.mount systemd-veritysetup@usr.service
Before=initrd-cleanup.service initrd-switch-root.target
[Service]
Type=oneshot
ExecStart=/latte-boot-probe
StandardOutput=journal+console
StandardError=journal+console
"""


def cpio(entries: list[tuple[str, int, bytes]]) -> bytes:
    """Create a newc archive, including symlinks, without host root privileges."""
    archive = bytearray()
    for inode, (name, mode, data) in enumerate(
        entries + [("TRAILER!!!", 0, b"")], start=1
    ):
        encoded = name.encode() + b"\0"
        fields = (inode, mode, 0, 0, 1, 0, len(data), 0, 0, 0, 0, len(encoded), 0)
        archive.extend(b"070701" + "".join(f"{v:08x}" for v in fields).encode())
        archive.extend(encoded)
        archive.extend(b"\0" * (-len(archive) % 4))
        archive.extend(data)
        archive.extend(b"\0" * (-len(archive) % 4))
    return bytes(archive)


def verity_algorithm(header: bytes) -> str:
    if len(header) < 64 or header[:8] != b"verity\0\0":
        raise ValueError("Missing dm-verity superblock in the produced ISO")
    algorithm = header[32:64].split(b"\0", 1)[0].decode("ascii")
    if algorithm != "sha256":
        raise ValueError(f"Unvalidated dm-verity algorithm: {algorithm}")
    return algorithm


def validate_cmdline(cmdline: str) -> None:
    words = cmdline.split()
    if not any(re.fullmatch(r"usrhash=[0-9a-f]{64}", word) for word in words):
        raise ValueError("The UKI must contain its signed SHA-256 /usr root hash")
    if "mount.usrfstype=erofs" not in words:
        raise ValueError("The UKI must request EROFS")
    if "systemd.verity_usr_options=panic-on-corruption" not in words:
        raise ValueError("The UKI must preserve panic-on-corruption")
    if any(word.startswith(("rd.verity=", "verity=")) for word in words):
        raise ValueError("Unexpected verity override")


def verify_usr(image: Path, layout: dict, cmdline: str, output: Path) -> dict:
    """Verify every protected block against the root hash from the actual UKI."""
    validate_cmdline(cmdline)
    root_hash = re.search(r"\busrhash=([0-9a-f]{64})\b", cmdline).group(1)
    partitions = layout["partitions"]
    data = next(p for p in partitions if p["type"].lower() == USR_TYPE)
    hashes = next(p for p in partitions if p["type"].lower() == VERITY_TYPE)
    if data["uuid"].replace("-", "").lower() != root_hash[:32]:
        raise ValueError("Data partition UUID does not match the UKI root hash")
    if hashes["uuid"].replace("-", "").lower() != root_hash[32:]:
        raise ValueError("Hash partition UUID does not match the UKI root hash")
    sector_size = layout["sectorsize"]
    with image.open("rb") as source:
        source.seek(hashes["start"] * sector_size)
        header = source.read(512)
    algorithm = verity_algorithm(header)
    data_block_size, hash_block_size, data_blocks = struct.unpack_from("<IIQ", header, 64)
    if data_block_size != 4096 or hash_block_size != 4096:
        raise ValueError("Unvalidated dm-verity block size")
    data_bytes = data_blocks * data_block_size
    if not data_bytes or data_bytes != data["size"] * sector_size:
        raise ValueError("Verity protected size does not match the data partition")

    with tempfile.TemporaryDirectory(prefix="latte-verity-", dir=output) as directory:
        files = []
        for partition, name in ((data, "usr.raw"), (hashes, "usr-verity.raw")):
            path = Path(directory) / name
            with image.open("rb") as source, path.open("wb") as target:
                source.seek(partition["start"] * sector_size)
                remaining = partition["size"] * sector_size
                while remaining:
                    chunk = source.read(min(remaining, 8 * 1024 * 1024))
                    if not chunk:
                        raise ValueError("Truncated image partition")
                    target.write(chunk)
                    remaining -= len(chunk)
            files.append(str(path))
        result = subprocess.run(
            ["veritysetup", "--verbose", "verify", *files, root_hash],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        )
        (output / "verity-verify.log").write_text(result.stdout)
        print(result.stdout, flush=True)
        result.check_returncode()
    report = {
        "root_hash": root_hash, "algorithm": algorithm,
        "data_blocks": data_blocks, "data_block_size": data_block_size,
        "data_bytes": data_bytes, "result": "all protected data/hash blocks verified",
    }
    (output / "verity-verify.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


def check_full_read(text: str) -> None:
    if "LATTE_FULL_VERITY_READ_OK" not in text:
        raise ValueError("The VM did not finish reading every protected /usr block")
    status = re.search(
        r"LATTE_VERITY_STATUS_BEGIN\n(.*?)LATTE_VERITY_STATUS_END", text, re.DOTALL
    )
    lines = [] if not status else [
        line.strip() for line in status[1].splitlines()
        if re.match(r"\s*\d+ \d+ verity\b", line)
    ]
    if len(lines) != 1 or not re.fullmatch(r"0 \d+ verity V(?: -)?", lines[0]):
        raise ValueError("The active dm-verity target did not report valid status")
    if re.search(
        r"device-mapper: verity:.*corrupt|Buffer I/O error|I/O error, dev|"
        r"blk_update_request:.*error|USB disconnect|reset .*USB device",
        text, re.IGNORECASE,
    ):
        raise ValueError("The VM reported storage or dm-verity errors")


def append_archive(original: Path, destination: Path, archive: bytes) -> None:
    with destination.open("wb") as target, original.open("rb") as source:
        shutil.copyfileobj(source, target)
        # The kernel requires uncompressed newc headers at four-byte offsets,
        # including after a compressed initrd whose length is not aligned.
        target.write(b"\0" * (-target.tell() % 4))
        target.write(archive)


def run(image: Path, output: Path, fragment: Path, timeout: int, verify_only: bool = False) -> None:
    output.mkdir(parents=True, exist_ok=True)
    layout = json.loads(
        subprocess.check_output(["sfdisk", "--json", str(image)], text=True)
    )["partitiontable"]
    sector_size = layout["sectorsize"]
    partitions = layout["partitions"]
    esp = next(p for p in partitions if p["type"].lower() == ESP_TYPE)
    verity = next(p for p in partitions if p["type"].lower() == VERITY_TYPE)
    with image.open("rb") as disk:
        disk.seek(verity["start"] * sector_size)
        algorithm = verity_algorithm(disk.read(512))
    (output / "partition-table.json").write_text(json.dumps(layout, indent=2) + "\n")
    print(f"Produced image dm-verity algorithm: {algorithm}", flush=True)

    uki_dir = output / "uki"
    uki_dir.mkdir()
    subprocess.run(
        [
            "mcopy", "-i", f"{image}@@{esp['start'] * sector_size}",
            "::/EFI/Linux/*.efi", str(uki_dir),
        ],
        check=True,
    )
    ukis = list(uki_dir.glob("*.efi"))
    if len(ukis) != 1:
        raise ValueError(f"Expected one UKI, found {len(ukis)}")
    for section in ("linux", "initrd", "cmdline", "uname"):
        subprocess.run(
            ["objcopy", "--dump-section", f".{section}={output / section}", str(ukis[0])],
            check=True,
        )
    cmdline = (output / "cmdline").read_bytes().rstrip(b"\0").decode()
    version = (output / "uname").read_bytes().rstrip(b"\0").decode()
    if not re.fullmatch(r"[a-zA-Z0-9.+_-]+", version):
        raise ValueError("Invalid kernel version in UKI")
    validate_cmdline(cmdline)
    verification = verify_usr(image, layout, cmdline, output)
    if verify_only:
        print(json.dumps(verification), flush=True)
        return

    spec = spec_from_file_location("boot_config", Path(__file__).with_name("check-boot-config.py"))
    checker = module_from_spec(spec)
    spec.loader.exec_module(checker)
    required = checker.requirements(fragment)
    # The probe is appended only to the VM initrd, never to the downloadable ISO.
    probe = f"""#!/bin/sh
set -eu
exec > /dev/console 2>&1
/usr/bin/dmsetup table usr > /run/latte-verity-table
grep -q ' verity ' /run/latte-verity-table
/usr/bin/dmsetup targets > /run/latte-dm-targets
grep -Eq '^crypt[[:space:]]' /run/latte-dm-targets
echo LATTE_DM_CRYPT_TARGET_OK
grep -Eq '^[^ ]+ /sysroot/usr erofs ro(,| )' /proc/mounts
test -s /sysroot/usr/lib/os-release
test -s /sysroot/usr/lib/gnomeos-installer/installer_transaction.py
grep -q 'reply_handler=on_ready' /sysroot/usr/lib/gnomeos-installer/installer.py
test -s /sysroot/usr/lib/udev/hwdb.d/90-latte.hwdb
test -s /sysroot/usr/lib/modules-load.d/latte.conf
test -s /sysroot/usr/lib/systemd/system-preset/00-latte-disable-sysupdate.preset
for unit in systemd-boot-update.service systemd-boot-random-seed.service \\
    systemd-boot-clear-sysfail.service systemd-bless-boot.service \\
    systemd-bootctl@.service; do
    grep -qx 'ConditionKernelCommandLine=!root=live:gnomeos' \\
        "/sysroot/usr/lib/systemd/system/$unit.d/00-latte-live.conf"
done
echo LATTE_LIVE_BOOT_WRITE_GUARDS_OK
echo LATTE_FULL_VERITY_READ_BEGIN
cat /dev/mapper/usr > /dev/null
echo LATTE_FULL_VERITY_READ_OK
echo LATTE_VERITY_STATUS_BEGIN
/usr/bin/dmsetup status usr
echo LATTE_VERITY_STATUS_END
dmesg
config=/sysroot/usr/lib/modules/{version}/config
while IFS= read -r required; do
    grep -qx "$required" "$config"
done < /latte-boot.config
echo LATTE_CONFIG_BEGIN
cat "$config"
echo LATTE_CONFIG_END
cat /run/latte-verity-table
echo LATTE_BOOT_SMOKE_OK_VERITY_EROFS
/usr/bin/systemctl --no-block poweroff
"""
    archive = cpio([
        ("latte-boot-probe", stat.S_IFREG | 0o755, probe.encode()),
        ("latte-boot.config", stat.S_IFREG | 0o644, ("\n".join(required) + "\n").encode()),
        ("usr/lib/systemd/system/latte-boot-probe.service", stat.S_IFREG | 0o644, PROBE_UNIT.encode()),
        ("usr/lib/systemd/system/initrd.target.wants/latte-boot-probe.service",
         stat.S_IFLNK | 0o777, b"../latte-boot-probe.service"),
    ])
    initrd = output / "test-initrd"
    append_archive(output / "initrd", initrd, archive)

    command = [
        "qemu-system-x86_64", "-machine", "q35,accel=tcg", "-cpu", "max",
        "-m", "2048", "-smp", "2", "-display", "none", "-monitor", "none",
        "-serial", "stdio", "-no-reboot", "-net", "none",
        "-kernel", str(output / "linux"), "-initrd", str(initrd),
        "-append", cmdline + " root=live:gnomeos console=ttyS0 loglevel=6 "
        "systemd.show_status=1 systemd.log_target=console",
        "-device", "qemu-xhci,id=xhci",
        "-drive", f"if=none,id=usb,file={image},format=raw,readonly=on",
        "-device", "usb-storage,bus=xhci.0,drive=usb,removable=on",
    ]
    log = output / "qemu-boot.log"
    timed_out = False
    with log.open("wb") as stream:
        try:
            result = subprocess.run(command, stdout=stream, stderr=subprocess.STDOUT, timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
    text = log.read_text(errors="replace").replace("\r", "")
    match = re.search(r"LATTE_CONFIG_BEGIN\n(.*?)LATTE_CONFIG_END", text, re.DOTALL)
    if match:
        config = output / "kernel.config"
        config.write_text(match[1])
        checker.check(config, fragment)
    if (
        timed_out or result.returncode or not match
        or "LATTE_BOOT_SMOKE_OK_VERITY_EROFS" not in text
        or "LATTE_DM_CRYPT_TARGET_OK" not in text
        or "LATTE_LIVE_BOOT_WRITE_GUARDS_OK" not in text
        or "Initramfs unpacking failed" in text
    ):
        print(text[-24000:])
        raise SystemExit("QEMU did not confirm required device-mapper targets and read-only EROFS /usr")
    check_full_read(text)
    report = {
        "kernel_version": version, "verity_algorithm": algorithm,
        "result": "all protected /usr blocks read through active dm-verity; read-only EROFS mounted",
        "full_verification": verification,
        "scope": "Produced UKI kernel/initrd, read-only USB ISO, TCG; not UEFI or hardware validation",
    }
    (output / "boot-smoke.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--timeout", type=int, default=600)
    parser.add_argument("--verify-only", action="store_true", help="Verify every data/hash block without QEMU")
    args = parser.parse_args()
    run(
        args.image.resolve(), args.output.resolve(),
        Path(__file__).resolve().parent.parent / "files/kernel/latte-boot.config",
        args.timeout, args.verify_only,
    )
