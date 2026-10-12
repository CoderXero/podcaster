from __future__ import annotations

from pathlib import Path
from typing import Protocol


class MediaUploader(Protocol):
    def upload(self, local_path: Path, *, episode_key: str, mime_type: str) -> str: ...
    def verify(self, uri: str, *, expected_sha256: str | None = None) -> bool: ...


class NoopUploader:
    """Explicitly test-only adapter; publisher refuses to use its local URIs."""

    def upload(self, local_path: Path, *, episode_key: str, mime_type: str) -> str:
        return f"file://{local_path.resolve()}"

    def verify(self, uri: str, *, expected_sha256: str | None = None) -> bool:
        return uri.startswith("file://")
