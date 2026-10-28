#!/usr/bin/env python3
"""Keep backed-up image digests, rebuilding the computer from its Dockerfile."""

import argparse
import json
import os
from pathlib import Path
import tempfile


def prepare(directory):
    source = directory / "compose.backup-images.json"
    document = json.loads(source.read_text())
    if not isinstance(document, dict) or not isinstance(document.get("services"), dict):
        raise ValueError("Backup image overrides must contain a services object")
    # Preserve the original manifest/overrides as evidence of the backed-up run.
    document["services"].pop("computer", None)
    target = directory / "compose.restore-images.json"
    fd, temporary = tempfile.mkstemp(prefix=".restore-images-", dir=directory)
    try:
        with os.fdopen(fd, "w") as stream:
            json.dump(document, stream, indent=2)
            stream.write("\n")
        os.replace(temporary, target)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return target


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path, help="directory with restored compose.backup-images.json")
    args = parser.parse_args()
    try:
        target = prepare(args.directory)
    except (OSError, ValueError) as error:
        parser.exit(1, f"Cannot prepare restore image overrides: {error}\n")
    print(f"Prepared {target}; build computer from the repository Dockerfile before starting.")


if __name__ == "__main__":
    main()
