# Low memory and graphics diagnostics

The pinned GNOME OS Build Meta includes `zram-generator` and a custom
`zswap-generator`. They are different mechanisms: zram is a compressed RAM
block device, while zswap compresses pages destined for a separate swap
backing device. In the installed GNOME OS policy, the generator creates a
swap backing file at `/swap/default-swap`, defaulting to four times physical
RAM, and configures zswap. On a 2 GiB device that is an 8 GiB logical backing
file; it is not an 8 GiB RAM reservation or a hibernation image.

The Latte kernel must start with zswap enabled for this generator to activate
that policy. One retained QEMU smoke artifact (`usrhash` beginning
`fcd22b94`) had `CONFIG_ZSWAP=y` but not `CONFIG_ZSWAP_DEFAULT_ON=y`; its
command line set the zswap pool limit but did not enable zswap. This does not
identify the image currently installed on the tablet. The generator checks
the runtime sysfs `enabled` value and, when it is not `Y`, skips swap-file
setup and masks the associated sysctl. The live image also deliberately skips
this installed-system setup because its root is ephemeral. Requiring
`CONFIG_ZSWAP_DEFAULT_ON=y` in the Latte kernel fragment restores GNOME OS's
existing installed policy in a future image; it does not change an already
installed tablet.

This policy is not exercised by the Actions workflow, which only builds and smoke-tests the live ISO. It does not benchmark the tablet or emulate its eMMC.

The upstream 4x backing size is a starting point, not a device measurement.
The swap file grows as pages are written; eMMC capacity, free space, latency,
and write endurance still matter. zswap's compressed pool is capped separately
by the configured 35% of RAM. This policy is disk-backed zswap, not zram swap.
Do not create a partition or swap file manually on the tablet as part of this
change. A future zram-first policy would be a separate tuning decision and
should be evaluated against the installed-system policy and disk-backed
fallback, without assuming hibernation.

## Read-only runtime checks

Run these on the tablet and share the output if confirming the installed
system is needed. They do not enable swap, alter partitions, or write to the
eMMC:

```sh
uname -r
grep -o 'usrhash=[^ ]*' /proc/cmdline
free -h
cat /proc/swaps
swapon --show
zramctl
cat /sys/module/zswap/parameters/enabled
cat /sys/module/zswap/parameters/max_pool_percent
systemctl status systemd-oomd --no-pager
journalctl -k -b --no-pager | grep -Ei 'oom|out of memory|killed process|zram|zswap'
```

An empty `swapon --show` and `/proc/swaps` mean no active swap device at the
time of the check. `zramctl` by itself does not establish that zram is being
used as swap; compare with `/proc/swaps`. `zswap` being enabled also does not
prove that a backing swap device was activated.

## Wallpaper and icon failures

These are separate from swap exhaustion. GNOME Backgrounds, Glycin,
gdk-pixbuf, and the Adwaita icon theme are included in the pinned image, so
their presence alone does not establish that the selected wallpaper or
individual image loaders work at runtime. The earlier Glycin/bubblewrap
traceback showed an SVG loader failure but did not include enough sandbox
diagnostics to identify its cause; do not disable the sandbox as a workaround.

Read the selected background and recent loader/core-dump messages:

```sh
gsettings get org.gnome.desktop.background picture-uri
gsettings get org.gnome.desktop.background picture-uri-dark
journalctl --user -b -o short-precise --no-pager | grep -Ei 'glycin|gdk-pixbuf|gtkiconhelper|bwrap|segfault|core dumped'
coredumpctl --no-pager list | grep -Ei 'gnome-shell|glycin|gnome-disks'
```

The image used for the reported runtime issue has not been identified by
`usrhash` or build ID, and the tablet's current swap, OOM, wallpaper, and
loader state have not been independently observed. A VM boot or kernel
configuration check cannot establish those physical-device runtime facts.
