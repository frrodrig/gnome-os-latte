#!/usr/bin/env python3
"""Install only into a newly created virtual disk, then boot it without the ISO."""

import argparse
import importlib.util
import json
import os
from pathlib import Path
import shutil
import stat
import struct
import subprocess
import uuid


DISK_BYTES = 16 * 1024**3
SERIAL = "LATTE_STAGING_ONLY"
GUEST = r'''
import json, os, pathlib, subprocess, sys
import dbus, dbus.mainloop.glib
from gi.repository import GLib

def command(*args):
    return subprocess.check_output(args, text=True)

phase, proof = sys.argv[1:]
if phase == "auto":
    phase = "install" if "root=live:gnomeos" in pathlib.Path("/proc/cmdline").read_text() else "installed"
assert pathlib.Path("/sys/firmware/efi").is_dir(), "Not a UEFI boot"
assert "QEMU" in command("systemd-detect-virt", "--vm").upper(), "Not QEMU"
print("LATTE_STAGING_PHASE=" + phase, flush=True)
print(command("lsblk", "-b", "-o", "NAME,SIZE,TYPE,FSTYPE,LABEL"), flush=True)
print(command("dmsetup", "status", "usr"), flush=True)
marker = pathlib.Path("/var/lib/latte-staging-proof")
if phase == "installed":
    assert "root=live:gnomeos" not in pathlib.Path("/proc/cmdline").read_text()
    assert marker.read_text() == proof, "Persistent root was not preserved"
    subprocess.run(["dd", "if=/dev/mapper/usr", "of=/dev/null", "bs=4M"], check=True)
    assert "verity V" in command("dmsetup", "status", "usr")
    print("LATTE_STAGING_INSTALLED_BOOT_OK", flush=True)
else:
    assert "root=live:gnomeos" in pathlib.Path("/proc/cmdline").read_text()
    devices = json.loads(command("lsblk", "-J", "-b", "-d", "-o", "NAME,SIZE,SERIAL,RO,TYPE"))["blockdevices"]
    targets = [d for d in devices if d.get("serial") == "LATTE_STAGING_ONLY"
               and d["size"] == 17179869184 and not d["ro"] and d["type"] == "disk"]
    assert len(targets) == 1, "Missing unique disposable virtual target"
    name = targets[0]["name"]
    assert not pathlib.Path("/sys/class/block", name, "partition").exists()
    marker.write_text(proof)
    dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
    bus = dbus.SystemBus()
    obj = bus.get_object("org.gnome.Installer1", "/org/gnome/Installer")
    installer = dbus.Interface(obj, "org.gnome.Installer1")
    loop = GLib.MainLoop()
    result = []
    def finished():
        result.append(True)
        loop.quit()
    def failed(message):
        print("LATTE_STAGING_INSTALL_ERROR: " + str(message), flush=True)
        result.append(False)
        loop.quit()
    installer.connect_to_signal("InstallationFinished", finished)
    installer.connect_to_signal("InstallationFailed", failed)
    installer.Install(name, False, reply_handler=lambda key: None, error_handler=failed)
    GLib.timeout_add_seconds(1200, lambda: failed("Install timed out"))
    loop.run()
    assert result == [True], "Installer did not report success"
    print("LATTE_STAGING_INSTALL_OK", flush=True)
subprocess.run(["systemctl", "--no-block", "poweroff"], check=True)
'''


def regular(path: Path) -> Path:
    path = path.resolve(strict=True)
    if any(character in str(path) for character in ",\r\n"):
        raise ValueError(f"Unsafe QEMU file path: {path}")
    if not stat.S_ISREG(path.stat().st_mode):
        raise ValueError(f"Only regular files are accepted: {path}")
    return path


def addon_initrd_address(data: bytes) -> int:
    pe = struct.unpack_from("<I", data, 0x3C)[0]
    if data[pe:pe + 4] != b"PE\0\0" or struct.unpack_from("<H", data, pe + 24)[0] != 0x20B:
        raise ValueError("Expected a PE32+ EFI addon")
    image_base = struct.unpack_from("<Q", data, pe + 48)[0]
    count = struct.unpack_from("<H", data, pe + 6)[0]
    table = pe + 24 + struct.unpack_from("<H", data, pe + 20)[0]
    ends = []
    for index in range(count):
        size, address, raw_size = struct.unpack_from("<III", data, table + index * 40 + 8)
        ends.append(address + max(size, raw_size))
    return image_base + ((max(ends) + 4095) & ~4095)


def instrument_iso(iso: Path, destination: Path, directory: Path, proof: str) -> None:
    """Instrument only an ESP copy; preserve the produced kernel and /usr."""
    spec = importlib.util.spec_from_file_location("smoke", Path(__file__).with_name("smoke-test-image.py"))
    smoke = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(smoke)
    unit = (
        "[Unit]\n"
        "After=systemd-tmpfiles-setup.service dbus.service\n"
        "Wants=dbus.service\n[Service]\nType=oneshot\n"
        f"ExecStart=/usr/bin/python3 /etc/latte-staging.py auto {proof}\n"
        "StandardOutput=journal+console\nStandardError=journal+console\nTimeoutStartSec=1300\n"
        "ExecStopPost=/usr/bin/journalctl -b --no-pager -u gnomeos-installer.service\n"
        "ExecStopPost=/usr/bin/systemctl --no-block poweroff\n"
    )
    dropin = "[Service]\nEnvironment=GNOMEOS_INSTALL_DISABLE_TPM=1\nEnvironment=RUST_LOG=debug\n"
    setup = """#!/bin/sh
set -eu
root=/sysroot/etc/systemd/system
mkdir -p "$root/multi-user.target.wants" "$root/gnomeos-installer.service.d"
cp /latte-staging.py /sysroot/etc/latte-staging.py
cp /latte-staging.service "$root/latte-staging.service"
cp /latte-staging-dropin.conf "$root/gnomeos-installer.service.d/staging.conf"
ln -s ../latte-staging.service "$root/multi-user.target.wants/latte-staging.service"
echo LATTE_STAGING_ROOT_SETUP_OK
"""
    setup_unit = (
        "[Unit]\nDefaultDependencies=no\nIgnoreOnIsolate=yes\n"
        "Requires=sysroot-usr.mount initrd-create-mutable-etc.service\n"
        "After=sysroot-usr.mount initrd-create-mutable-etc.service systemd-confext-sysroot.service\n"
        "Before=initrd-cleanup.service initrd-switch-root.target\n"
        "[Service]\nType=oneshot\nExecStart=/latte-staging-setup\n"
        "StandardOutput=journal+console\nStandardError=journal+console\n"
    )
    entries = [
        ("latte-staging.py", stat.S_IFREG | 0o644, GUEST.encode()),
        ("latte-staging.service", stat.S_IFREG | 0o644, unit.encode()),
        ("latte-staging-dropin.conf", stat.S_IFREG | 0o644, dropin.encode()),
        ("latte-staging-setup", stat.S_IFREG | 0o755, setup.encode()),
        ("usr/lib/systemd/system/latte-staging-setup.service",
         stat.S_IFREG | 0o644, setup_unit.encode()),
        ("usr/lib/systemd/system/initrd.target.wants/latte-staging-setup.service",
         stat.S_IFLNK | 0o777, b"../latte-staging-setup.service"),
    ]
    archive = directory / "staging.cpio"
    archive.write_bytes(smoke.cpio(entries))
    layout = json.loads(subprocess.check_output(["sfdisk", "--json", str(iso)], text=True))["partitiontable"]
    esp = next(p for p in layout["partitions"] if p["type"].lower() == smoke.ESP_TYPE)
    shutil.copyfile(iso, destination)
    image = f"{destination}@@{esp['start'] * layout['sectorsize']}"
    subprocess.run(["mcopy", "-i", image, "::/EFI/Linux/*.efi", str(directory)], check=True)
    ukis = list(directory.glob("gnomeos_*.efi"))
    if len(ukis) != 1:
        raise ValueError("Expected exactly one produced UKI")
    addon_path = f"::/EFI/Linux/{ukis[0].name}.extra.d/live.addon.efi"
    addon = directory / "original.addon.efi"
    instrumented = directory / "staging.addon.efi"
    subprocess.run(["mcopy", "-i", image, addon_path, str(addon)], check=True)
    address = addon_initrd_address(addon.read_bytes())
    subprocess.run([
        "objcopy", "--add-section", f".initrd={archive}",
        "--change-section-vma", f".initrd={address:#x}", str(addon), str(instrumented),
    ], check=True)
    subprocess.run(["mcopy", "-o", "-i", image, str(instrumented), addon_path], check=True)


def run(iso: Path, output: Path, code: Path, variables: Path, timeout: int) -> None:
    iso, code, variables = (regular(p) for p in (iso, code, variables))
    for tool in ("qemu-system-x86_64", "mcopy", "sfdisk", "objcopy"):
        if not shutil.which(tool):
            raise SystemExit(f"Missing tool: {tool}")
    output = output.resolve()
    if any(character in str(output) for character in ",\r\n"):
        raise ValueError("Unsafe QEMU output path")
    # No existing disk path or host block device can be supplied as a target.
    output.mkdir(parents=True, exist_ok=False)
    if shutil.disk_usage(output).free < DISK_BYTES + iso.stat().st_size + 1024**3:
        raise SystemExit("Insufficient free space for the disposable disk and instrumented ISO copy")
    disk = output / "disposable.raw"
    with disk.open("xb") as file:
        file.truncate(DISK_BYTES)
    nvram = output / "vm-only-vars.fd"
    shutil.copyfile(variables, nvram)
    proof = uuid.uuid4().hex
    test_iso = output / "instrumented.iso"
    instrument_iso(iso, test_iso, output, proof)
    for phase in ("install", "installed"):
        command = [
            "qemu-system-x86_64", "-machine", "q35,accel=tcg", "-cpu", "max,vendor=GenuineIntel",
            "-m", "4096", "-smp", "2", "-display", "none", "-monitor", "none",
            "-serial", "stdio", "-no-reboot", "-net", "none",
            "-drive", f"if=pflash,format=raw,readonly=on,file={code}",
            "-drive", f"if=pflash,format=raw,file={nvram}",
            "-device", "qemu-xhci,id=xhci",
            "-drive", f"if=none,id=target,format=raw,file={disk}",
            "-device", f"usb-storage,bus=xhci.0,drive=target,removable=off,serial={SERIAL},bootindex=1",
            "-smbios", "type=11,value=io.systemd.stub.kernel-cmdline-extra=console=ttyS0 systemd.show_status=1",
        ]
        if os.environ.get("QEMU_DATA_DIR"):
            command.extend(["-L", os.environ["QEMU_DATA_DIR"]])
        if phase == "install":
            command.extend([
                "-drive", f"if=none,id=live,format=raw,readonly=on,file={test_iso}",
                "-device", "usb-storage,bus=xhci.0,drive=live,removable=on,bootindex=2",
            ])
        log = output / f"{phase}.log"
        with log.open("wb") as stream:
            result = subprocess.run(command, stdout=stream, stderr=subprocess.STDOUT, timeout=timeout)
        text = log.read_text(errors="replace")
        expected = "LATTE_STAGING_INSTALL_OK" if phase == "install" else "LATTE_STAGING_INSTALLED_BOOT_OK"
        if result.returncode or expected not in text:
            raise SystemExit(f"VM {phase} failed; inspect {log}. The disposable disk is preserved.")
    (output / "result.json").write_text(json.dumps({
        "result": "installer daemon completed; UEFI installed boot without ISO and persistent root verified",
        "iso": str(iso), "virtual_disk_bytes": DISK_BYTES,
        "scope": "ESP-addon-instrumented ISO copy; QEMU TCG, no TPM or Secure Boot; not physical hardware or OTA validation",
    }, indent=2) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("iso", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--ovmf-code", type=Path, required=True)
    parser.add_argument("--ovmf-vars", type=Path, required=True)
    parser.add_argument("--timeout", type=int, default=1500)
    args = parser.parse_args()
    run(args.iso, args.output, args.ovmf_code, args.ovmf_vars, args.timeout)
