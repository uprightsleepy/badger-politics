"""Bounded archives: regular files only, verified before manual extraction."""

import gzip
import shutil
import tarfile
from pathlib import Path, PurePosixPath

MAX_EXPANDED = 12 * 1024**3
MAX_FILES = 200_000


def pack(source: Path, name: str, target: Path) -> int:
    if not source.is_dir() or source.is_symlink():
        raise ValueError(f"Required source directory missing: {name}")
    expanded = 0
    count = 0
    with target.open("wb") as out, gzip.GzipFile(
        fileobj=out, mode="wb", mtime=0, compresslevel=6
    ) as gz:
        with tarfile.open(fileobj=gz, mode="w|") as archive:
            for path in sorted(source.rglob("*")):
                if path.is_symlink() or not (path.is_dir() or path.is_file()):
                    raise ValueError("Source archives cannot contain links or special files")
                if path.is_file():
                    expanded += path.stat().st_size
                    count += 1
                    if expanded > MAX_EXPANDED or count > MAX_FILES:
                        raise ValueError("Source archive exceeds the extraction budget")
                    archive.add(path, arcname=f"{name}/{path.relative_to(source).as_posix()}",
                                recursive=False)
    return expanded


def unpack(source: Path, name: str, root: Path, expected_bytes: int):
    if (root / name).exists():
        raise ValueError(f"Restore requires an empty destination: {name}")
    (root / name).mkdir(parents=True)
    expanded = 0
    count = 0
    seen = set()
    with tarfile.open(source, mode="r|gz") as archive:
        for member in archive:
            path = PurePosixPath(member.name)
            if (path.is_absolute() or not path.parts or path.parts[0] != name
                    or ".." in path.parts or "\\" in member.name or ":" in member.name
                    or not member.isfile() or member.name in seen):
                raise ValueError("Unsafe or duplicate archive member")
            seen.add(member.name)
            expanded += member.size
            count += 1
            if expanded > min(expected_bytes, MAX_EXPANDED) or count > MAX_FILES:
                raise ValueError("Archive exceeds its declared extraction budget")
            target = root.joinpath(*path.parts)
            if not target.resolve().is_relative_to(root.resolve()):
                raise ValueError("Archive path escapes the restore directory")
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.extractfile(member) as src, target.open("xb") as dst:
                shutil.copyfileobj(src, dst)
    if expanded != expected_bytes:
        raise ValueError("Expanded archive size does not match manifest")
