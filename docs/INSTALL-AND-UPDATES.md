# Installation and update staging

This is development infrastructure, not a validated tablet installation guide.
Do not run an installer, fastboot, or partitioning commands against the tablet
based on these tests. The earlier physical "Erase all disk" attempt has no
diagnostic log; its cause and resulting disk state are unknown.

## Shared installation and update layout

The pinned GNOME installer creates an ESP, two `/usr` and verity partition
pairs, and a persistent root filesystem. Each deployment consists of the
Latte UKI (kernel, initrd, command line and root hash), EROFS `/usr`, and its
verity tree. These must be built and transferred together. The upstream
two-partition postmarketOS fastboot package is not compatible with this layout.

The UI adaptation submits erase and install requests asynchronously, shows
progress before preparing the disk, and reports DBus errors without starting
installation after failed preparation. A timeout does not mean an erase was
rolled back. Do not retry destructive operations without inspecting the state.
The installer daemon's actual partitioning transaction remains upstream.
The kernel also requires dm-crypt for the installer's TPM-encrypted-root path.

## Disposable UEFI VM test

On Linux, with QEMU and OVMF available:

```sh
python3 build/test-install-vm.py .build/out/disk.iso \
  --output .build/install-test \
  --ovmf-code /usr/share/OVMF/OVMF_CODE_4M.fd \
  --ovmf-vars /usr/share/OVMF/OVMF_VARS_4M.fd
```

The output directory must not exist. The runner creates a new 16 GiB regular
file, exposes only that virtual disk and a read-only ISO, uses a private copy
of UEFI variables, and disconnects networking. It never accepts a destination
block-device argument. A private ISO copy is instrumented with an additional
initrd in its live EFI addon to inject the test service; the kernel and protected
`/usr` are unchanged. No automation is added to the original downloadable ISO.
The guest identifies
the unique virtual target by USB sysfs serial and size before calling the
installer. This does not depend on `lsblk` having a populated serial property.

The first boot invokes the **installer daemon**, not the graphical erase
dialog, against an initially empty virtual disk. A second boot without the ISO
checks UEFI, persistent root data, and a complete active dm-verity read. Success
requires both markers and writes `result.json`; failures preserve logs and the
virtual disk. This test disables TPM encryption explicitly and does not test
Secure Boot, the tablet, GUI responsiveness, OTA, or recovery. A successful
kernel/initrd-only smoke test is not a substitute for this test.
Both VM boots select the multi-user target rather than starting the desktop.

### Observed local installation baseline

The retained ISO from Actions run `43027903872` (source
`403cbe13e1f216629226e58daa5a590749a9a087`, SHA256
`82ed2cef6db3d156aab69325768d67f55d38e772bcbaee8ab3426384751c4673`)
completed the installer-daemon transaction on a new virtual disk. A second UEFI
boot without the ISO preserved the root marker and read all 3,083,628,544 bytes
through `/dev/mapper/usr`, which remained healthy (`verity V`).
Logs and the result are in `.build/uefi-install-usb-serial/`.

This used QEMU 8.2.2 TCG and OVMF 2024.02 with the development ESP-addon harness,
before its multi-user-target optimization. It does not validate the new GUI
callbacks, TPM encryption, a new candidate ISO, physical installation, or OTA.

## Build isolated update candidates

```sh
LATTE_STAGING_VERSION=latte.1 bash build/build-usb.sh --with-staging-updates
```

Use an empty build output and a clean disposable upstream checkout for each
version. Preserve the previous outputs before building `latte.2`. The prepared
checkout marker includes the version and integration fingerprint; stale
checkouts are rejected rather than silently reused.

The optional `gnomeos/latte-update-images.bst` builds only the adapted UKI,
`/usr` and verity payloads, with `latte-` source filenames to distinguish them
from generic GNOME OS updates. `.build/staging-updates/SHA256SUMS` is deliberately
**unsigned**. A checksum alone is not authentication.
`build/verify-staging-updates.py` checks the three payload digests, matching
versions, UKI root hash and partition UUIDs, then performs full verity
verification. This consistency check is not a signature check or an OTA test.

The three `files/latte/staging-sysupdate/*.transfer` templates target the
installed GNOME partition layout. They require signature verification and
matching versions across the three transfers, protect the running version,
keep two UKIs, and request three boot attempts for a newly downloaded UKI.
They are **not installed or enabled by the image build**. No production keyring,
URL, timer, publisher, or automatic reboot is configured.
Workflow runs with a staging version, update candidates, or installation tests
upload diagnostic evidence only, not the ISO or update payloads.

For isolated staging, a maintainer must separately sign the checksum catalog
with a throwaway test key and provision only that test public key in the
disposable VM. The templates use QEMU's host gateway on port 8080, not GitHub or
an Internet channel. Never disable verification to make staging pass, import
test trust on the tablet, or describe the public snakeoil keys as secure.
Transfers, installation, first reboot, a second update, failed downloads,
invalid signatures, interrupted updates, and boot-count fallback must all be
exercised before claiming end-to-end installation and OTA support. The templates
alone do not demonstrate transactional recovery or automatic rollback.

## GitHub hosting and production gates

GitHub HTTPS can transport updates, but it does not replace publisher
authentication. A production channel needs a separately provisioned signing
public key and fingerprint, controlled private-key custody, signed versioned
metadata, a key rotation/revocation process, and explicit release approval.
Credentials and private keys must not be embedded in the image or repository.
Trust must persist on installed root storage across image updates.

There is a concrete size constraint: GitHub requires every release asset to be
**under 2 GiB**. The retained image's EROFS `/usr` is 3,083,628,544 bytes, already
larger than that limit. Therefore these raw update payloads cannot simply be
uploaded as release assets and used as a direct sysupdate URL. Additional
compression must be measured, not assumed effective on compressed EROFS.
For the retained run `43027903872`, streaming the complete `/usr` partition
through XZ preset 0 produced 2,506,144,460 bytes, still over 2 GiB. Stronger
compression with XZ preset 6 also exceeded the limit: it had already emitted
2,149,836,019 bytes after reading only 2,805,989,376 bytes of the partition.
That test stopped at the threshold; the emitted size is a lower bound, not a
completed archive size. Neither tested preset fits this image. Other compression
settings have not been measured.
Possible alternatives are reducing the image, using another permitted
large-file origin, or implementing a separately reviewed signed chunk-download
and local-staging layer. Splitting a file without authenticating its manifest,
order, final digest and version is not a safe update mechanism.

A stable signed catalog and previous deployments must remain available;
expiring Actions artifacts and `/releases/latest/download` by themselves do
not provide a versioned update repository. No generic upstream update feed may
replace the Latte kernel. Failed networking or verification must leave the
running deployment bootable; root data must not be reformatted during updates.
Boot counting is not health validation: actual failure and fallback tests are
required, and rollback of OS images does not necessarily roll back user-data
migrations.

Production publication remains blocked by the firmware redistribution audit.
Before enabling it, decide the signing-key owner and secure provisioning
process, approve a size-compatible hosting design, finish redistribution
review, and validate installation/update/recovery on the target hardware.
Until then, the existing disabled update policy remains in effect.

## References

- [Pinned GNOME installer](https://gitlab.gnome.org/GNOME/gnome-build-meta/-/blob/8a89846df11e86cee57c728a86a247e61d604b84/files/gnomeos/live/proto-installer/daemon/main.rs)
- [Pinned upstream deployment workflow](https://gitlab.gnome.org/GNOME/gnome-build-meta/-/blob/8a89846df11e86cee57c728a86a247e61d604b84/docs/contributing-os.md)
- [GitHub release asset limits](https://docs.github.com/en/repositories/releasing-projects-on-github/about-releases#storage-and-bandwidth-quotas)
