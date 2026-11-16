#!/usr/bin/env bash
# Write a pre-installed GNOME OS Latte disk image (.raw) to the internal eMMC.
# Run as root from a live USB system, NOT from the target disk.
# Usage: sudo bash flash-installed-disk.sh /path/to/installed-disk.raw [/dev/mmcblk0]
set -euo pipefail

IMG=${1:?Usage: $0 IMAGE.raw [TARGET_DEVICE]}
DEV=${2:-/dev/mmcblk0}

[[ $EUID -eq 0 ]] || { echo "Run as root (sudo)." >&2; exit 1; }
[[ -f $IMG ]] || { echo "Image not found: $IMG" >&2; exit 1; }
[[ -b $DEV ]] || { echo "Not a block device: $DEV" >&2; exit 1; }

img_bytes=$(stat -c %s "$IMG")
dev_bytes=$(blockdev --getsize64 "$DEV")
(( img_bytes <= dev_bytes )) || { echo "Image is larger than $DEV." >&2; exit 1; }

# Refuse to overwrite the disk that holds the running system or the image.
for path in / /usr "$IMG"; do
    src=$(findmnt -n -o SOURCE --target "$path" 2>/dev/null || true)
    if [[ $src == "$DEV"* ]]; then
        echo "Refusing: $path is on $DEV. Boot from the USB and keep the image on another device." >&2
        exit 1
    fi
done

echo "Target:"
lsblk -o NAME,SIZE,MODEL,FSTYPE,MOUNTPOINT "$DEV"
echo "Image: $IMG ($img_bytes bytes)"
echo "ALL DATA ON $DEV WILL BE DESTROYED."
read -r -p "Type YES to continue: " answer
[[ $answer == YES ]] || { echo "Aborted."; exit 1; }

for p in "${DEV}"p*; do
    [[ -b $p ]] && umount "$p" 2>/dev/null || true
done

dd if="$IMG" of="$DEV" bs=4M conv=fsync status=progress
sync

echo "Verifying copy..."
cmp -n "$img_bytes" "$IMG" "$DEV" && echo "Verification OK"

if command -v sgdisk >/dev/null; then
    sgdisk -e "$DEV"
elif command -v sfdisk >/dev/null; then
    sfdisk --relocate gpt-end "$DEV"
else
    echo "Warning: no sgdisk/sfdisk; backup GPT not moved to end of disk." >&2
fi
partprobe "$DEV" || true
udevadm settle || true
lsblk -o NAME,PARTLABEL,SIZE,FSTYPE "$DEV"

# Grow the last partition (root) to fill the disk when its filesystem allows it.
last=$(lsblk -nrpo NAME,TYPE "$DEV" | awk '$2=="part"{p=$1} END{print p}')
fstype=$(blkid -o value -s TYPE "$last" || true)
num=${last##*[!0-9]}
echo "Last partition: $last (filesystem: ${fstype:-unknown})"
case $fstype in
    ext4|btrfs|xfs)
        parted -s "$DEV" resizepart "$num" 100%
        partprobe "$DEV" || true
        udevadm settle || true
        case $fstype in
            ext4)
                e2fsck -f -y "$last" || [[ $? -le 1 ]]
                resize2fs "$last" ;;
            btrfs)
                tmp=$(mktemp -d)
                mount "$last" "$tmp" && btrfs filesystem resize max "$tmp"
                umount "$tmp"; rmdir "$tmp" ;;
            xfs)
                tmp=$(mktemp -d)
                mount "$last" "$tmp" && xfs_growfs "$tmp"
                umount "$tmp"; rmdir "$tmp" ;;
        esac
        lsblk -o NAME,PARTLABEL,SIZE,FSTYPE "$DEV" ;;
    *)
        echo "Not growing root (filesystem '${fstype:-unknown}', possibly encrypted or absent)." >&2
        echo "It will keep its image size; resize manually if needed." >&2 ;;
esac
echo "Done. Power off, remove the USB and boot from the internal storage."
