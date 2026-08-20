"""Invoke openstates-scrapers as a subprocess CLI (GPL boundary: never
imported). Applies patches/ first, then archives output to _data/ because
os-update clears its own output dir each run. Never run two concurrently.

Usage: python -m scraper.scrape bills|events [--session ID] [--no-fastmode]
"""

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

PIPELINE_DIR = Path(__file__).resolve().parents[1]
VENDOR_DIR = PIPELINE_DIR / "vendor" / "openstates-scrapers"
PATCHES_DIR = PIPELINE_DIR / "patches"
RAW_DIR = VENDOR_DIR / "_data" / "wi"
ARCHIVE_DIR = PIPELINE_DIR / "_data" / "wi"

SCRAPERS = {
    # target -> (os-update args, output file prefixes this run owns)
    "bills": (["wi", "bills", "--scrape"], ("bill", "vote_event")),
    "events": (["wi", "events", "--scrape"], ("event",)),
}
SHARED_PREFIXES = ("jurisdiction", "organization")


def apply_patches() -> None:
    for patch in sorted(PATCHES_DIR.glob("*.patch")):
        already = subprocess.run(
            ["git", "apply", "--reverse", "--check", str(patch)],
            cwd=VENDOR_DIR,
            capture_output=True,
        )
        if already.returncode == 0:
            continue  # already applied
        subprocess.run(["git", "apply", str(patch)], cwd=VENDOR_DIR, check=True)
        print(f"applied patch: {patch.name}")


def archive_output(prefixes: tuple[str, ...], archive_dir: Path) -> int:
    archive_dir.mkdir(parents=True, exist_ok=True)
    copied = 0
    for prefix in (*prefixes, *SHARED_PREFIXES):
        fresh = list(RAW_DIR.glob(f"{prefix}_*.json"))
        if not fresh:
            continue
        for stale in archive_dir.glob(f"{prefix}_*.json"):
            stale.unlink()
        for path in fresh:
            shutil.copy2(path, archive_dir / path.name)
            copied += 1
    return copied


def build_command(target: str, fastmode: bool, extra: list[str]) -> list[str]:
    """os-update args for a scrape target; fastmode caches + disables throttling."""
    args = list(SCRAPERS[target][0])
    if fastmode and target == "bills":
        args.append("--fastmode")
    args.extend(extra)
    if shutil.which("os-update"):
        # Inside the pipeline image: os-update is on PATH.
        return ["os-update", *args]
    # Local dev: run through the vendored compose 'scrape' service.
    return ["docker", "compose", "run", "--rm", "scrape", *args]


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", choices=sorted(SCRAPERS))
    parser.add_argument("--no-fastmode", action="store_true")
    parser.add_argument(
        "--session",
        help="scrape one historical session (exact scraper identifier, e.g."
        " '2023' or '2013 Regular Session'); archives to _data/sessions/",
    )
    parser.add_argument("--archive-dir", type=Path)
    parser.add_argument("extra", nargs="*", help="extra args passed through to os-update")
    ns = parser.parse_args(argv)

    if not VENDOR_DIR.exists():
        print("submodule missing: run `git submodule update --init`", file=sys.stderr)
        return 2

    apply_patches()
    extra = list(ns.extra)
    archive_dir = ns.archive_dir
    if ns.session:
        extra.append(f"session={ns.session}")
        if archive_dir is None:
            slug = ns.session.replace(" ", "-").lower()
            archive_dir = PIPELINE_DIR / "_data" / "sessions" / slug
    cmd = build_command(ns.target, fastmode=not ns.no_fastmode, extra=extra)
    print(f"+ {' '.join(cmd)} (cwd={VENDOR_DIR})", flush=True)
    result = subprocess.run(cmd, cwd=VENDOR_DIR, check=False)
    if result.returncode == 0:
        copied = archive_output(SCRAPERS[ns.target][1], archive_dir or ARCHIVE_DIR)
        print(f"scrape ok: archived {copied} JSON files -> {archive_dir or ARCHIVE_DIR}")
    return result.returncode


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
