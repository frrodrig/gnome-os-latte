#!/usr/bin/env python3
"""Replace only the original libcamera runtime files in a composed sysroot."""

import filecmp
import hashlib
import os
from pathlib import Path
import shutil
import stat
import sys


LIBDIR = Path("usr/lib/x86_64-linux-gnu")
REQUIRED = {
    Path("usr/bin/cam"),
    LIBDIR / "libcamera.so.0.7.2",
    LIBDIR / "libcamera-base.so.0.7.2",
    LIBDIR / "libcamera/ipa/ipa_ipu3.so",
    LIBDIR / "libcamera/ipa/ipa_soft_simple.so",
    LIBDIR / "gstreamer-1.0/libgstlibcamera.so",
    Path("usr/share/libcamera/ipa/simple/uncalibrated_atomisp.yaml"),
}
ORIGINAL_LICENSES = Path("usr/share/licenses/freedesktop-sdk/libcamera")
LICENSES = Path("usr/share/licenses/gnome/latte-libcamera/LICENSES")
# Exact files from the pinned libcamera source commit in build/prepare-camera.py.
EXPECTED_LICENSE_SHA256 = {
    LICENSES / "GPL-2.0-or-later.txt": "606aa26338f69ce178f1cbc648b7574aec4b5bbaeb20f4df36ff49010cb8fbbd",
    LICENSES / "LGPL-2.1-or-later.txt": "1ccf09bf2f598308df4bed9cd8e9657dc5cd0973d2800318f2e241486e2edf3f",
    LICENSES / "CC0-1.0.txt": "6a573fb2f9082662978cf21fb153096df0a1981deaea7dbc10a11046fe005d9f",
}
PIPEWIRE_BACKEND = LIBDIR / "spa-0.2/libcamera/libspa-libcamera.so"


def files(root: Path) -> set[Path]:
    result = set()
    for directory, dirs, names in os.walk(root, followlinks=False):
        for name in dirs[:]:
            path = Path(directory) / name
            if path.is_symlink():
                result.add(path.relative_to(root))
                dirs.remove(name)
        result.update((Path(directory) / name).relative_to(root) for name in names)
    return result


def check_parents(root: Path, relative: Path) -> None:
    current = root
    for part in relative.parts[:-1]:
        current /= part
        if current.is_symlink():
            raise ValueError(f"Refusing a symlinked destination directory: {current}")


def same_file(source: Path, target: Path) -> bool:
    if source.is_symlink():
        return target.is_symlink() and os.readlink(source) == os.readlink(target)
    if not source.is_file() or source.is_symlink():
        raise ValueError(f"Unexpected libcamera payload entry: {source}")
    return (
        target.is_file()
        and not target.is_symlink()
        and stat.S_IMODE(source.stat().st_mode) == stat.S_IMODE(target.stat().st_mode)
        and filecmp.cmp(source, target, shallow=False)
    )


def describe_file(path: Path) -> str:
    if path.is_symlink():
        return f"symlink->{os.readlink(path)}"
    if not path.is_file():
        return "missing or non-regular"

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    info = path.stat()
    return (
        f"mode={stat.S_IMODE(info.st_mode):04o}, size={info.st_size}, "
        f"sha256={digest.hexdigest()}"
    )


def install(original: Path, candidate: Path, sysroot: Path) -> None:
    if any(not root.is_dir() or root.is_symlink() for root in (original, candidate, sysroot)):
        raise ValueError("Expected three existing, non-symlink directories")
    old_files, new_files = files(original), files(candidate)
    if not REQUIRED <= new_files:
        raise ValueError(f"Experimental camera runtime is incomplete: {sorted(REQUIRED - new_files)}")
    missing_licenses = set(EXPECTED_LICENSE_SHA256) - new_files
    if missing_licenses:
        raise ValueError(f"Experimental component is missing license files: {sorted(missing_licenses)}")
    for path, expected in EXPECTED_LICENSE_SHA256.items():
        license_file = candidate / path
        if license_file.is_symlink() or not license_file.is_file():
            raise ValueError(f"Experimental component license is not a regular file: {path}")
        actual = hashlib.sha256(license_file.read_bytes()).hexdigest()
        if actual != expected:
            raise ValueError(
                f"Experimental component license digest mismatch: {path} "
                f"(expected sha256={expected}, actual sha256={actual})"
            )
    if not (sysroot / PIPEWIRE_BACKEND).is_file():
        raise ValueError("The composed image has no PipeWire libcamera backend")
    missing = {path for path in old_files - new_files if not path.is_relative_to(ORIGINAL_LICENSES)}
    if missing:
        raise ValueError(f"Experimental runtime omits original files: {sorted(missing)}")
    for path in old_files | new_files:
        check_parents(sysroot, path)
    for path in old_files:
        if not same_file(original / path, sysroot / path):
            raise ValueError(
                f"Composed image differs from original libcamera: {path} "
                f"(component: {describe_file(original / path)}; "
                f"sysroot: {describe_file(sysroot / path)})"
            )
    for path in new_files - old_files:
        if os.path.lexists(sysroot / path):
            raise ValueError(f"Experimental runtime would overwrite an unrelated file: {path}")
    for path in sorted(new_files):
        source, target = candidate / path, sysroot / path
        target.parent.mkdir(parents=True, exist_ok=True)
        if os.path.lexists(target):
            target.unlink()
        if source.is_symlink():
            target.symlink_to(os.readlink(source))
        elif source.is_file():
            shutil.copy2(source, target)
        else:
            raise ValueError(f"Unexpected libcamera payload entry: {source}")


def main() -> None:
    if len(sys.argv) != 4:
        raise SystemExit("usage: install-camera.py ORIGINAL CANDIDATE SYSROOT")
    try:
        install(*(Path(arg) for arg in sys.argv[1:]))
    except (OSError, ValueError) as error:
        raise SystemExit(f"Cannot install experimental libcamera: {error}") from error


if __name__ == "__main__":
    main()
