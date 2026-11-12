# GNOME OS for Xiaomi Mi Pad 2

An initial GNOME OS Preview 51 prototype for testing from an external USB drive. It does not install GNOME OS on the tablet or modify postmarketOS or the eMMC.

This adaptation is based on official GNOME OS and BuildStream, not Arch Linux. It pins GNOME Build Meta to commit `8a89846df11e86cee57c728a86a247e61d604b84` and the Xiaomi Mi Pad 2 kernel (`xiaomi-latte-dev/linux_latte`) to commit `575dbb62ac89c5e3e49f98c386255178e29c9ec5`. It keeps the generic x86-64 CPU baseline and does not enable `x86_64_v3`.

## Build

You need Linux, Git, Python 3, GNU Make, GnuPG, BuildStream 2.6 or later, and the sandbox dependencies required by GNOME OS. You also need an Internet connection and enough free storage for the checkout and complete GNOME OS build. See [GNOME OS build requirements](https://gitlab.gnome.org/GNOME/gnome-build-meta/-/blob/gnome-51/docs/contributing-os.md#building-and-booting-a-gnome-os-image) as well. From the repository root, run:

```sh
bash build/build-usb.sh
```

The script keeps the temporary GNOME checkout in `.build/` and writes `disk.iso` to `.build/out/`. BuildStream stores its cache in its configured location (typically under `~/.cache/buildstream`). The script does not accept disk paths and does not write to block devices.

For this test image, the script generates GNOME's public `snakeoil` test keys, recommended for local builds. They provide no security and are not private keys for this device; do not enroll them in firmware. If Secure Boot blocks the media, stop instead of changing firmware settings or enrolling keys.

**The image is not included in this repository.** Consider it available only if the build command succeeds and `.build/out/disk.iso` exists and is non-empty. Actions additionally gates the ISO upload on a QEMU test of the produced kernel/initrd mounting verity-protected EROFS `/usr`. Replacement boot on the tablet still requires manual validation.

## Compatibility and USB testing

The image is x86-64 and requires UEFI firmware capable of booting an x86-64 EFI application. The Mi Pad 2 may have 32-bit UEFI firmware even though its CPU is x86-64; do not assume compatibility just because it was originally a Windows model. Check non-destructively from postmarketOS:

```sh
cat /sys/firmware/efi/fw_platform_size
```

The value `64` is required for this image. If the file does not exist or shows `32`, do not try to boot this media.

To test it, write the image to an empty USB drive with an imaging tool, carefully checking the target device: writing the image erases the USB drive's contents. Boot using the firmware's one-time boot menu. Do not select any install, repair, or flash option. Do not change GPT, EFI variables, Secure Boot, the permanent boot order, or the internal bootloader. If Secure Boot blocks booting, stop; this guide does not authorize disabling it or enrolling keys. If it does not boot, power off, remove the USB drive, and boot normally into postmarketOS.

The configuration disables GNOME OS image-update services to prevent them from replacing the Latte kernel with a generic one. Extra community binary firmware and UCM profiles are not copied because their redistribution licenses have not been verified. Upstream GNOME OS firmware is still present, including the Xiaomi BCM4356 configuration from linux-firmware. Its exact redistribution audit remains unresolved, so there is no public prerelease. Normal Actions artifacts in this public repository are not private and expire after one day. Wi-Fi, Bluetooth, audio, and cameras may not work even though the kernel includes their drivers.

## Support status

Installation and OTA development is isolated in [installation and update
staging](docs/INSTALL-AND-UPDATES.md). It does not enable a production update
channel or establish a working installation on the tablet.

GNOME OS Preview is experimental. The first physical USB boot failed because the kernel lacked dm-verity and EROFS. The replacement reached GNOME briefly, then panicked with `dm-verity device corrupted`. The retained ISO passes full offline verification and a complete protected-device read in QEMU; the tablet's USB/read path remains under investigation. See [read-only USB diagnostics and boot-test details](docs/BUILD.md). Stable boot, touchscreen, rotation, suspend, battery, Wi-Fi, audio, and cameras remain unverified. Live bootloader-writing services are now explicitly guarded, separately from the corruption investigation.
