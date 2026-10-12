from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
from collections.abc import Iterable
from pathlib import Path
from typing import Any


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def normalized_text(text: str) -> str:
    return "\n".join(line.rstrip() for line in text.replace("\r\n", "\n").splitlines()).strip() + "\n"


def safe_slug(value: str, max_length: int = 80) -> str:
    value = value.lower().encode("ascii", "ignore").decode()
    value = re.sub(r"[^a-z0-9]+", "-", value).strip("-") or "episode"
    return value[:max_length].rstrip("-")


def atomic_write_bytes(path: Path, data: bytes, mode: int | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    part = path.with_name(f".{path.name}.{os.getpid()}.part")
    try:
        with part.open("wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        if mode is not None:
            os.chmod(part, mode)
        os.replace(part, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        part.unlink(missing_ok=True)


def atomic_write_text(path: Path, text: str, mode: int | None = None) -> None:
    atomic_write_bytes(path, text.encode("utf-8"), mode=mode)


def atomic_write_json(path: Path, value: Any) -> None:
    atomic_write_text(path, json.dumps(value, indent=2, ensure_ascii=False, default=str) + "\n")


def discover_markdown(root: Path, recursive: bool = True, max_files: int | None = None) -> list[Path]:
    root = root.expanduser().resolve()
    if not root.is_dir():
        raise ValueError(f"input directory does not exist: {root}")
    paths: list[Path] = []
    iterator: Iterable[Path] = root.rglob("*") if recursive else root.glob("*")
    for path in iterator:
        if len(paths) == max_files:
            break
        if not path.is_file() or path.is_symlink() or path.suffix.lower() not in {".md", ".markdown"}:
            continue
        relative_parts = path.relative_to(root).parts
        if any(part.startswith(".") or part in {".git", "output", "archived-sources"} for part in relative_parts):
            continue
        paths.append(path)
    return sorted(paths, key=lambda item: item.relative_to(root).as_posix())


def collision_safe_destination(destination: Path) -> Path:
    if not destination.exists():
        return destination
    for number in range(1, 10000):
        candidate = destination.with_name(f"{destination.name}-{number}")
        if not candidate.exists():
            return candidate
    raise RuntimeError(f"could not find collision-safe destination for {destination}")


def archive_file(source: Path, archive_root: Path, relative: Path) -> Path:
    destination = collision_safe_destination(archive_root / relative)
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(source), str(destination))
    return destination
