#!/usr/bin/env python3
"""Select published upstream releases and record immutable build inputs."""

import json
import os
from pathlib import Path
import re
import subprocess
import sys
from urllib.request import urlopen


GNOME_URL = "https://gitlab.gnome.org/GNOME/gnome-build-meta.git"
LATTE_URL = "https://github.com/xiaomi-latte-dev/linux_latte.git"
LATTE_RELEASES_URL = "https://api.github.com/repos/xiaomi-latte-dev/linux_latte/releases"
GNOME_TAG = re.compile(r"[0-9]+\.[0-9]+(?:\.[0-9]+)?")
LATTE_TAG = re.compile(r"v[0-9]+(?:\.[0-9]+){1,2}")


def checked_sha(value):
    if not re.fullmatch(r"[0-9a-f]{40}", value):
        raise ValueError(f"Expected a full Git commit SHA, got {value!r}")
    return value


def tag_refs(url, *patterns):
    listing = subprocess.check_output(
        ["git", "ls-remote", "--exit-code", "--tags", url, *patterns], text=True,
    )
    return dict((ref, sha) for sha, ref in (line.split("\t") for line in listing.splitlines()))


def tag_commit(refs, tag):
    ref = f"refs/tags/{tag}"
    if ref not in refs:
        raise ValueError(f"Published tag {tag!r} is missing from Git")
    return checked_sha(refs.get(f"{ref}^{{}}", refs[ref]))


def gnome_release(refs, commit=None):
    tags = [tag for ref in refs if ref.startswith("refs/tags/")
            and GNOME_TAG.fullmatch(tag := ref.removeprefix("refs/tags/"))
            and int(tag.split(".")[0]) >= 40
            and (commit is None or tag_commit(refs, tag) == commit)]
    if not tags:
        raise ValueError("No matching stable GNOME Build Meta release tag found")
    return max(tags, key=lambda tag: tuple(map(int, tag.split("."))))


def latte_release(release):
    if not isinstance(release, dict):
        raise ValueError("GitHub did not return Linux Latte release metadata")
    tag = release.get("tag_name")
    if (release.get("draft") is not False or release.get("prerelease") is not False
            or not isinstance(tag, str) or not LATTE_TAG.fullmatch(tag)):
        raise ValueError("GitHub did not return a stable Linux Latte release")
    return tag


def read_latte_release(path):
    with urlopen(f"{LATTE_RELEASES_URL}/{path}", timeout=30) as response:
        return latte_release(json.load(response))


def select(gnome_override, latte_override):
    if bool(gnome_override) != bool(latte_override):
        raise ValueError("Specify both upstream commit overrides for replay, or neither for stable releases")
    mode = "replay" if gnome_override else "stable-releases"
    if gnome_override:
        checked_sha(gnome_override)
        checked_sha(latte_override)
    refs = tag_refs(GNOME_URL)
    gnome_tag = gnome_release(refs, gnome_override or None)
    if latte_override:
        latte_refs = tag_refs(LATTE_URL)
        candidates = [tag for ref in latte_refs if ref.startswith("refs/tags/")
                      and LATTE_TAG.fullmatch(tag := ref.removeprefix("refs/tags/"))
                      and tag_commit(latte_refs, tag) == latte_override]
        if len(candidates) != 1:
            raise ValueError("Replay requires exactly one matching Linux Latte version tag")
        latte_tag = candidates[0]
        if read_latte_release(f"tags/{latte_tag}") != latte_tag:
            raise ValueError(f"GitHub release does not match Linux Latte tag {latte_tag}")
    else:
        latte_tag = read_latte_release("latest")
        latte_refs = tag_refs(LATTE_URL, f"refs/tags/{latte_tag}", f"refs/tags/{latte_tag}^{{}}")
    return mode, {
        "url": GNOME_URL, "tag": gnome_tag, "commit": tag_commit(refs, gnome_tag),
    }, {
        "url": LATTE_URL, "tag": latte_tag, "commit": tag_commit(latte_refs, latte_tag),
    }


def main():
    path, integration_commit = sys.argv[1:]
    try:
        mode, gnome, latte = select(os.getenv("GNOME_BUILD_META_COMMIT"), os.getenv("LATTE_KERNEL_COMMIT"))
        Path(path).write_text(json.dumps({
            "mode": mode, "latte_integration_commit": integration_commit,
            "gnome_build_meta": gnome, "latte_kernel": latte,
        }, indent=2) + "\n", encoding="utf-8")
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        raise SystemExit(f"Upstream release resolution failed: {error}") from error
    print(f"GNOME Build Meta {gnome.get('tag', 'replay')}: {gnome['commit']}", file=sys.stderr)
    print(f"Linux Latte {latte.get('tag', 'replay')}: {latte['commit']}", file=sys.stderr)
    print(gnome["url"], gnome["commit"], latte["commit"])


if __name__ == "__main__":
    main()
