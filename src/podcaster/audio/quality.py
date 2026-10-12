from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

from ..filesystem import sha256_file


class AudioValidationError(ValueError):
    pass


def require_tools() -> None:
    missing = [tool for tool in ("ffmpeg", "ffprobe") if not shutil.which(tool)]
    if missing:
        raise AudioValidationError(f"missing required tools: {', '.join(missing)}")


def probe(path: Path) -> dict[str, object]:
    require_tools()
    result = subprocess.run(["ffprobe", "-v", "error", "-show_format", "-show_streams", "-of", "json", str(path)], check=False, capture_output=True, text=True)
    if result.returncode or not result.stdout:
        raise AudioValidationError(f"audio failed to decode: {path}")
    return json.loads(result.stdout)


def duration(path: Path) -> float:
    data = probe(path)
    value = data.get("format", {}).get("duration")
    if not value or float(value) <= 0:
        raise AudioValidationError("audio duration is zero")
    return float(value)


def validate_mp3(path: Path, minimum_seconds: float = 0.1) -> tuple[float, str]:
    if not path.exists() or path.stat().st_size < 256:
        raise AudioValidationError("audio output is missing or too small")
    data = probe(path)
    streams = data.get("streams", [])
    if not any(stream.get("codec_name") == "mp3" for stream in streams):
        raise AudioValidationError("final output is not an MP3")
    seconds = duration(path)
    if seconds < minimum_seconds:
        raise AudioValidationError("audio duration is too short")
    return seconds, sha256_file(path)
