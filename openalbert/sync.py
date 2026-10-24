#!/usr/bin/env python3
"""Download one upstream revision without changing the running installation."""

import json
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile
from urllib.error import URLError
from urllib.parse import quote
from urllib.request import Request, urlopen


REPOSITORY = "mishankov/OpenAlbert"
CACHE = Path(__file__).resolve().parent / ".upstream"


def download(url):
    request = Request(url, headers={"User-Agent": "homelab-openalbert"})
    with urlopen(request, timeout=30) as response:
        return response.read()


def sync(ref):
    commit = json.loads(download(
        f"https://api.github.com/repos/{REPOSITORY}/commits/{quote(ref, safe='')}"
    ))["sha"]
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ValueError("GitHub returned an invalid commit SHA")

    CACHE.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".download-", dir=CACHE))
    try:
        for filename in ("compose.yaml", ".env.release.example"):
            content = download(
                f"https://raw.githubusercontent.com/{REPOSITORY}/{commit}/{filename}"
            )
            if not content.strip():
                raise ValueError(f"Upstream {filename} is empty")
            (staging / filename).write_bytes(content)

        destination = CACHE / commit
        if not destination.exists():
            staging.rename(destination)
        # Readers see either the old or new complete revision, even during sync.
        with tempfile.NamedTemporaryFile(mode="w", dir=CACHE, delete=False) as pointer:
            pointer.write(commit + "\n")
        try:
            os.replace(pointer.name, CACHE / "current")
        finally:
            Path(pointer.name).unlink(missing_ok=True)
    finally:
        shutil.rmtree(staging, ignore_errors=True)

    print(f"Selected OpenAlbert {commit} (images: sha-{commit}).")
    print(f"Upstream environment template: {destination / '.env.release.example'}")
    print("No services changed. Review upstream changes, back up data, then run up.sh.")


if __name__ == "__main__":
    if len(sys.argv) > 2:
        sys.exit("Usage: sync.py [upstream-ref] (default: master)")
    try:
        sync(sys.argv[1] if len(sys.argv) == 2 else "master")
    except (URLError, OSError, ValueError, KeyError) as error:
        sys.exit(f"OpenAlbert sync failed: {error}")
