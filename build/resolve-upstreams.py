#!/usr/bin/env python3
"""Select cached stable GNOME and published Latte releases and record immutable build inputs."""

import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen


GNOME_URL = "https://gitlab.gnome.org/GNOME/gnome-build-meta.git"
LATTE_URL = "https://github.com/xiaomi-latte-dev/linux_latte.git"
LATTE_RELEASES_URL = "https://api.github.com/repos/xiaomi-latte-dev/linux_latte/releases"
GNOME_API = "https://gitlab.gnome.org/api/v4/projects/GNOME%2Fgnome-build-meta"
GNOME_BRANCH = re.compile(r"gnome-([0-9]+)")
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


def fetch_json(url, headers=None):
    for attempt in range(5):
        try:
            with urlopen(Request(url, headers=headers or {}), timeout=30) as response:
                return json.load(response)
        except HTTPError as error:
            if error.code not in (403, 429, 500, 502, 503, 504) or attempt == 4:
                raise ValueError(f"{url}: HTTP {error.code}") from error
            time.sleep(min(int(error.headers.get("Retry-After") or 0), 120) or 15 * 2 ** attempt)


def gitlab_json(path):
    return fetch_json(f"{GNOME_API}{path}")


def stable_gnome_branch(branches):
    versions = {int(m[1]): b["name"] for b in branches
                if (m := GNOME_BRANCH.fullmatch(b.get("name", ""))) and int(m[1]) >= 40}
    if not versions:
        raise ValueError("No stable GNOME Build Meta branch found")
    return versions[max(versions)]


def cached_gnome_release(branch, pipelines, jobs_for):
    """Latest scheduled CI success on the stable branch; its artifacts are in GNOME's cache."""
    for pipeline in pipelines:
        if pipeline.get("sha") and any(
                job.get("name") == "build-x86_64" and job.get("status") == "success"
                for job in jobs_for(pipeline["id"])):
            return {"branch": branch, "pipeline": pipeline["id"],
                    "commit": checked_sha(pipeline["sha"])}
    raise ValueError(f"No cached successful scheduled build found on {branch}")


def read_cached_gnome_release():
    branch = stable_gnome_branch(gitlab_json("/repository/branches?search=%5Egnome-&per_page=100"))
    pipelines = gitlab_json(f"/pipelines?ref={branch}&source=schedule&status=success"
                            "&order_by=id&sort=desc&per_page=20")
    return cached_gnome_release(branch, pipelines,
                                lambda pid: gitlab_json(f"/pipelines/{pid}/jobs?per_page=100"))


def latte_release(release):
    if not isinstance(release, dict):
        raise ValueError("GitHub did not return Linux Latte release metadata")
    tag = release.get("tag_name")
    if (release.get("draft") is not False or release.get("prerelease") is not False
            or not isinstance(tag, str) or not LATTE_TAG.fullmatch(tag)):
        raise ValueError("GitHub did not return a stable Linux Latte release")
    return tag


def read_latte_release(path):
    token = os.getenv("GITHUB_TOKEN")
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    return latte_release(fetch_json(f"{LATTE_RELEASES_URL}/{path}", headers))


def select(gnome_override, latte_override):
    if bool(gnome_override) != bool(latte_override):
        raise ValueError("Specify both upstream commit overrides for replay, or neither for stable releases")
    mode = "replay" if gnome_override else "stable-releases"
    if gnome_override:
        checked_sha(gnome_override)
        checked_sha(latte_override)
        gnome = {"commit": gnome_override}
    else:
        gnome = read_cached_gnome_release()
    gnome["url"] = GNOME_URL
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
    return mode, gnome, {
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
    print(f"GNOME Build Meta {gnome.get('branch', 'replay')}: {gnome['commit']}", file=sys.stderr)
    print(f"Linux Latte {latte.get('tag', 'replay')}: {latte['commit']}", file=sys.stderr)
    print(gnome["url"], gnome["commit"], latte["commit"])


if __name__ == "__main__":
    main()
