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

Do not pass a disk path to the script. It writes only within `.build/`. If the build fails, no usable image has been generated.

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

Booting on a physical Mi Pad 2 has not yet been tested. The touchscreen, rotation, suspend, battery, wireless networking, audio, and cameras still need testing; do not infer working hardware support merely because the kernel recipe builds.
