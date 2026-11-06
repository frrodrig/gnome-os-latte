#!/usr/bin/env python3
"""Reject resolved kernel configurations missing built-in early boot support."""

from pathlib import Path
import sys


def requirements(path: Path) -> list[str]:
    return [
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.startswith("CONFIG_")
    ]


def check(config: Path, fragment: Path) -> None:
    resolved = set(config.read_text(encoding="utf-8").splitlines())
    missing = [entry for entry in requirements(fragment) if entry not in resolved]
    if missing:
        raise SystemExit("Missing built-in boot prerequisites: " + ", ".join(missing))
    print("Resolved kernel boot prerequisites verified.")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit("usage: check-boot-config.py CONFIG BOOT-FRAGMENT")
    check(Path(sys.argv[1]), Path(sys.argv[2]))
