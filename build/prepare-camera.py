#!/usr/bin/env python3
"""Add the pinned AtomISP patch to GNOME's Freedesktop SDK junction."""

from pathlib import Path
import shutil
import sys


SDK_COMMIT = "114ae909ec9881958bd507c8b4414aa33f758d2b"
LIBCAMERA_COMMIT = "191e202178f02430b5942397c70d215cdd2056fa"
PATCH_QUEUE_FILE = "0002-latte-camera.patch"


def verify_bundle(repository: Path) -> tuple[Path, Path]:
    camera_dir = repository / "files/camera"
    port = camera_dir / "libcamera-0.7.2-atomisp.wip.patch"
    overlay = camera_dir / "enable-freedesktop-sdk-atomisp.patch"
    if not port.is_file() or not overlay.is_file():
        raise SystemExit("AtomISP patch bundle is incomplete.")

    port_text = port.read_text(encoding="utf-8")
    overlay_text = overlay.read_text(encoding="utf-8")
    marker = "+++ b/patches/libcamera/latte-atomisp.patch\n"
    if overlay_text.count(marker) != 1:
        raise SystemExit("SDK overlay must add exactly one libcamera patch source.")
    if f"ref: v0.7.2-0-g{LIBCAMERA_COMMIT}" not in overlay_text:
        raise SystemExit("SDK overlay does not target the validated libcamera revision.")
    if "pipelines: 'atomisp,simple,uvcvideo'" not in overlay_text:
        raise SystemExit("SDK overlay does not enable AtomISP and the simple IPA.")

    payload = overlay_text.split(marker, 1)[1]
    header, separator, body = payload.partition("\n")
    if not separator or not header.startswith("@@ -0,0 +1,"):
        raise SystemExit("SDK overlay has an invalid nested libcamera patch.")
    try:
        expected_lines = int(header.rsplit(",", 1)[1].split()[0])
    except (IndexError, ValueError) as error:
        raise SystemExit("SDK overlay has an invalid nested patch line count.") from error
    nested_lines = body.splitlines(keepends=True)
    if len(nested_lines) != expected_lines or any(not line.startswith("+") for line in nested_lines):
        raise SystemExit("SDK overlay nested patch is truncated or malformed.")
    nested = "".join(line[1:] for line in nested_lines)
    if nested != port_text:
        raise SystemExit("SDK overlay and validated AtomISP patch differ.")

    return overlay, port


def prepare(checkout: Path, repository: Path) -> Path:
    overlay, _ = verify_bundle(repository)
    junction = checkout / "elements/freedesktop-sdk.bst"
    if not junction.is_file() or SDK_COMMIT not in junction.read_text(encoding="utf-8"):
        raise SystemExit(
            "AtomISP port requires the validated Freedesktop SDK junction "
            f"at {SDK_COMMIT}; refusing an unreviewed upstream."
        )

    patch_dir = checkout / "patches/freedesktop-sdk"
    if not patch_dir.is_dir():
        raise SystemExit(f"Freedesktop SDK patch queue is missing: {patch_dir}")
    destination = patch_dir / PATCH_QUEUE_FILE
    if destination.exists():
        if destination.read_bytes() != overlay.read_bytes():
            raise SystemExit(f"Refusing to overwrite an existing patch: {destination}")
    else:
        shutil.copyfile(overlay, destination)
    return destination


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: prepare-camera.py GNOME-BUILD-META-CHECKOUT")
    repository = Path(__file__).resolve().parents[1]
    prepare(Path(sys.argv[1]).resolve(), repository)


if __name__ == "__main__":
    main()
