# Build and test from USB

## Requirements

Use a Linux distribution or WSL2 with a working Linux distribution, Git, Python 3, GNU Make, GnuPG, BuildStream 2.6 or later, and the sandbox dependencies required by GNOME OS. The official GNOME OS build may take a long time and requires an Internet connection, substantial storage, and build tools compatible with BuildStream. Do not install tools or change host settings without authorization.

## Build

From the repository root:

```sh
bash build/build-usb.sh
```

The script:

1. Clones GNOME Build Meta into `.build/`, pins GNOME OS Preview 51, and verifies its commit.
2. Modifies the temporary checkout to replace the generic kernel with the Latte kernel, add the tablet-specific configuration, and omit incompatible image updates.
3. Generates the public `snakeoil` test keys required by GNOME OS in that checkout. These are not secure for personal use and must not be enrolled in firmware.
4. Runs BuildStream for `x86_64`, the `stable` channel, and at most two concurrent tasks by default (`BST_MAX_JOBS` can change this limit).
5. Checks out the official `gnomeos/live-image.bst` element into `.build/out/`.

The kernel revision is pinned as well. Transitive dependencies and the Freedesktop SDK junction use the revisions defined by the pinned GNOME Build Meta commit. BuildStream stores source and artifact data in its configured cache, usually outside `.build/`.

The hardware defconfig is merged with `files/kernel/latte-boot.config`. The build
checks the **resolved** `.config` after `olddefconfig`, not just the requested
fragment. Device mapper, dm-verity, SHA-256, EROFS (including Zstandard), USB
storage, and the live-root prerequisites are built in so they do not depend on
modules loaded from the not-yet-mounted `/usr`. Integrity verification remains
enabled with the original UKI root hash and `panic-on-corruption`.

The live trial also adds negative `root=live:gnomeos` conditions to bootloader
update, bootloader random-seed, sysfail-clear, boot-blessing, and boot-control
services. They must be skipped on this USB trial even if presets or socket
activation would otherwise start them. Autofs is built in because systemd
requires it for automounts; the old image logged a missing `autofs4` module.

Do not pass a disk path to the script. It writes only within `.build/`. If the build fails, no usable image has been generated.

## Automated early boot regression

The Actions workflow runs `python3 build/test-boot-validation.py` and, after
building, extracts the kernel, initrd, command line, and version from the actual
produced UKI. It checks the ISO's verity superblock uses SHA-256, then runs:

```sh
python3 build/smoke-test-image.py .build/out/disk.iso --output .build/boot-smoke
```

This requires QEMU, mtools, binutils, util-linux, and `veritysetup` (cryptsetup-bin).
Before starting QEMU, the test extracts the actual GPT data/hash partitions to
temporary regular files and runs `veritysetup verify` over every protected block
against the root hash extracted from the UKI. The partition UUIDs must match the
two halves of that hash. Temporary partition copies are removed after the check.
For an offline check without QEMU, add `--verify-only` to the command above.

QEMU uses TCG with only a
read-only virtual USB image attached; no host disks or network are exposed. A
test-only probe appended to the VM initrd checks that `/sysroot/usr` is mounted
read-only as EROFS over an active `verity` device-mapper target, and checks the
kernel configuration read from that mounted filesystem. It also reads the
entire `/dev/mapper/usr` device, requires valid (`V`) dm-verity status, and rejects
reported corruption or storage errors. Merely mounting `/usr` is not sufficient:
a corrupt block can remain undetected until an application first reads it.
The downloadable ISO
does not contain this probe. Logs, the effective config, and a JSON result are
retained with the build evidence. The ISO upload is gated on this test passing.

This checks the early-boot path that failed on the tablet, **not** UEFI/shim,
Secure Boot, GNOME desktop startup, or tablet peripherals. It cannot substitute
for another physical USB boot test.

## Diagnosing a later dm-verity panic

The replacement reached the GNOME interface briefly on the tablet, then reported
`dm-verity device corrupted`. That message alone does not distinguish an altered
download, incomplete USB write, failing USB media/adapter, an incorrect selected
partition, or an intermittent device/kernel/RAM problem. Do not disable verity,
remove `panic-on-corruption`, or run filesystem repair tools.

The retained image from run
[42804693142](https://github.com/frrodrig/gnome-os-latte/actions/runs/42804693142)
was independently checked in full:

| Property | Verified value |
| --- | --- |
| ISO size | 3,360,621,056 bytes |
| ISO SHA-256 | `cead8c2913afe1901825465c8ad2b5860960bd3ad9dd375be947c7a51c0f13d7` |
| UKI `usrhash` | `fcd22b94efdeaeee9a53d6a951d6e071e0d8b4ba880f0291ae60ec71ca4b8b5a` |
| Data partition | sector 541008, 6022672 sectors (512 bytes each) |
| Hash partition | sector 493568, 47440 sectors |
| Protected data | 752834 blocks of 4096 bytes |
| Hash tree | 5929 blocks of 4096 bytes, SHA-256 |
| Full `veritysetup verify` | Passed against the root hash extracted from this ISO's UKI |

This rules out a static data/hash mismatch **in that retained file**, not faults
in the tablet's read path. No replacement kernel or image is justified solely
by the panic without further evidence.

### Windows: verify the existing USB without writing it

First verify the downloaded ISO with `Get-FileHash -Algorithm SHA256` and compare
it to the checksum for its exact run. Do not compare images from different runs.
Power off the tablet, unplug its USB drive, and connect only that external drive
to the Windows computer. Safely reconnect after writing so the check reads the
device again. Decline any Windows prompt to format, initialize, or repair it.

In an elevated PowerShell terminal, identify the USB by its model and capacity:

```powershell
Get-Disk | Format-Table Number,FriendlyName,BusType,Size,IsBoot,IsSystem
```

After confirming the number belongs to the external test USB, substitute it
for `N` below (the script has no default target):

```powershell
.\build\Compare-UsbImage.ps1 -Image 'C:\path\disk.iso' -DiskNumber N
```

The script opens both files with **read-only access**, refuses non-USB and
running system/boot disks, and hashes exactly the image's byte length from USB
offset zero. It does not hash unused space at the end of the drive, unmount
partitions, change attributes, or repair GPT. `Match=True` is required. A
mismatch or read error is evidence to investigate the write/media path before
another boot. An identical read on Windows does not exclude intermittent faults
in the tablet's USB hub, adapter, power supply, controller, or RAM. Avoid extra
cloned GNOME test drives during testing because identical copies share UUIDs.

### Rufus 4.15 assertion when opening the image

Rufus DD mode was used for the reported test. A separate Rufus/libcdio assertion
on opening the ISO has a reproducible layout explanation: the minimal ISO9660
volume declares 21 blocks (2048 bytes each), while its El Torito catalog at
block 19 points to the valid EFI partition at block 512 (byte 1048576), with
sector count zero. Rufus 4.15 asserts that the boot-image block must be within
the ISO9660 volume (`512 <= 21`), which fails. `xorriso` 1.5.6 successfully reads
the hybrid GPT/El Torito layout and locates that EFI image.

The pinned [GNOME live-image recipe](https://gitlab.gnome.org/GNOME/gnome-build-meta/-/blob/8a89846df11e86cee57c728a86a247e61d604b84/elements/gnomeos/live-image.bst)
uses `systemd-repart --el-torito`; the
[included systemd repart implementation](https://github.com/systemd/systemd/blob/73612ea502d53baf9b0df4336cfc296a7ee0d524/src/repart/repart.c)
deliberately emits a small ISO9660 filesystem with the boot entry pointing at
the ESP. The failing assertion is in
[Rufus v4.15's libcdio](https://github.com/pbatard/rufus/blob/v4.15/src/libcdio/iso9660/iso9660_fs.c#L561).
This establishes a parser/layout incompatibility; it does not prove that Rufus
changed a completed DD write or explain the tablet's corruption by itself.
Do not select Ignore or Retry on the assertion dialog.

If a new write is needed after diagnosis, use a raw-disk writer that accepts
the image without ISO extraction (for example USBImager), selecting **only**
the external disposable USB. Writing erases that USB; never select the tablet
or an internal disk. Eject/reconnect, then perform the read-only comparison
above. No alternative writer has yet been tested with this exact image here.

### Capture useful device evidence

Photograph/video the text before the panic, especially lines naming a corrupt
data/hash block, `I/O error`, USB resets/disconnects, and device major/minor
numbers. If a shell is available before the panic, these are read-only:

```sh
cat /proc/cmdline
lsblk -o NAME,MAJ:MIN,SIZE,TRAN,FSTYPE,PARTLABEL,PARTUUID,MOUNTPOINTS
dmsetup table usr
dmsetup status usr
dmesg | grep -Ei 'verity|corrupt|I/O error|usb|reset'
```

Compare the two backing devices in the verity table to the GPT UUIDs and the
UKI hash; do not assume `/dev/sda` always identifies the USB. Do not save logs
to the eMMC or change EFI settings. Live logs disappear after power-off, and
the graphical panic photo alone does not identify a corrupt block or device.

### Other boot messages and ESP safety

The additional photographs confirm `/usr` is verified and mounted successfully
before the later panic. Missing `brcm/BCM4356A2.hcd` is consistent with the
intentionally omitted extra Bluetooth firmware. Dummy camera/BT regulators,
AtomISP staging warnings, pinctrl/SPI probe failures, and i915 PMIC errors need
separate peripheral investigation; none has been shown to cause the verity
panic. The missing `autofs4` message is addressed by built-in `CONFIG_AUTOFS_FS`.

The old image contains systemd 262.1. Its `systemd-boot-update.service` runs
`bootctl --variables=no --graceful update`: the option suppresses EFI-variable
updates but does not prohibit ESP file updates. Its random-seed service runs
`bootctl --graceful random-seed`, which can update an ESP seed and may initialize
`LoaderSystemToken` if an appropriate ESP/firmware context is available.
`--graceful` can also return success when there is no ESP to update. Therefore
the photographs' successful unit status is **not proof of an internal write**.

The pinned GNOME live generator prepares an installer ESP mount at
`/var/lib/gnomeos/installer-esp` read-only and an installation-target `/efi`
mount that it does not enable. This does not justify leaving unrelated
boot-mutating services active in a non-installing trial. The new drop-ins
skip them when `root=live:gnomeos` is present; these are a separate safety fix,
not a claimed fix for the unexplained verity panic. They do not retroactively
change the previously generated ISO.

No prerelease is published while the firmware redistribution audit remains
unresolved. Normal Actions artifacts in this public repository are accessible
to users with repository read access and expire after one day; they are not
private or permanent release downloads.

## Checks before testing

From postmarketOS, inspect the UEFI mode without modifying the device:

```sh
cat /sys/firmware/efi/fw_platform_size
```

The image requires an x86-64 CPU and 64-bit UEFI. `fw_platform_size` must return `64`. A missing file does not confirm that the firmware is x86-64; if the value is `32` or you cannot confirm it, stop and do not boot this image.

Confirm that `.build/out/disk.iso` exists and is non-empty. Only then write it to an empty USB drive using an imaging tool; writing it erases the drive's contents. Check the target device name several times. Do not select the tablet's internal storage or run commands to flash the eMMC.

Do not change Secure Boot, enroll keys, or modify EFI variables as part of this test. If Secure Boot blocks booting, stop and request authorization before making any firmware changes. Select the USB drive from the one-time boot menu and do not choose any permanent install, repair, or update option.

## Recovery and limitations

If the media does not boot or something goes wrong, power off the tablet, disconnect the USB drive, and boot normally. This procedure does not change the internal disk or bootloader and should not require recovery of the internal system.

The kernel includes Latte hardware support, capacitive-button mappings, and loading of the RT5659 audio module. The community files `BCM4356A2.hcd`, `shisp_2401a0_v21.bin`, Wi-Fi calibration data, and ALSA UCM profiles are not copied because their redistribution licenses have not been verified. The image may boot while some device-specific features remain unavailable.

The first physical USB boot reached the initramfs but failed to activate
dm-verity because the original hardware defconfig omitted `CONFIG_DM_VERITY`;
it also omitted `CONFIG_EROFS_FS`. The boot fragment and automated mount test
address these omissions. The replacement reached GNOME briefly on a physical
Mi Pad 2 but then panicked with a verity corruption message; stable boot is not
confirmed. The touchscreen, rotation, suspend, battery,
wireless networking, audio, and cameras still need testing; do not infer
working hardware support merely because the kernel recipe builds.
