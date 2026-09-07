"""Export upstream's existing Poetry lock to hash-checked pip input, without resolving."""

import re
import sys
import tomllib
from pathlib import Path


def export(path: Path) -> str:
    lock = tomllib.loads(path.read_text(encoding="utf-8"))
    lines = ["# Generated from the pinned scraper submodule's poetry.lock; do not edit."]
    for package in lock["package"]:
        if package.get("optional") or "main" not in package.get("groups", []):
            continue
        if package.get("source"):
            raise ValueError("Only hash-pinned index packages are supported")
        requirement = f"{package['name']}=={package['version']}"
        marker = package.get("markers")
        if isinstance(marker, dict):
            marker = marker.get("main")
        if marker:
            requirement += f" ; {marker}"
        hashes = [entry["hash"] for entry in package["files"]]
        if not hashes or any(not re.fullmatch(r"sha256:[0-9a-f]{64}", h) for h in hashes):
            raise ValueError("Every scraper dependency must have SHA-256 hashes")
        continuation = " " + chr(92) + "\n    "
        lines.append(requirement + continuation + continuation.join(f"--hash={h}" for h in hashes))
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    sys.stdout.write(export(Path(sys.argv[1])))
