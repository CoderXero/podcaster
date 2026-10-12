from __future__ import annotations

import subprocess
from pathlib import Path


def render_playlist(tracks: list[Path], output: Path, silence_ms: int, bitrate: str = "160k",
                    target_lufs: float = -16, true_peak_db: float = -1.0) -> None:
    if not tracks:
        raise ValueError("playlist has no tracks")
    output.parent.mkdir(parents=True, exist_ok=True)
    # Build input/filter indexes explicitly because silence inputs are interleaved.
    inputs, filters, labels = [], [], []
    source_index = 0
    for index, track in enumerate(tracks):
        inputs += ["-i", str(track)]
        filters.append(f"[{source_index}:a]aresample=48000,aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo[a{index}]")
        labels.append(f"[a{index}]")
        source_index += 1
        if index < len(tracks) - 1 and silence_ms:
            inputs += ["-f", "lavfi", "-t", f"{silence_ms / 1000:.3f}", "-i", "anullsrc=r=48000:cl=stereo"]
            filters.append(f"[{source_index}:a]anull[a_s{index}]")
            labels.append(f"[a_s{index}]")
            source_index += 1
    filters.append("".join(labels) + f"concat=n={len(labels)}:v=0:a=1[concatout]")
    filters.append(f"[concatout]loudnorm=I={target_lufs}:TP={true_peak_db}:LRA=11[out]")
    command = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *inputs, "-filter_complex", ";".join(filters), "-map", "[out]", "-codec:a", "libmp3lame", "-b:a", bitrate, "-ar", "44100", "-ac", "2", str(output)]
    result = subprocess.run(command, check=False, capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError(f"ffmpeg playlist failed: {result.stderr[-1000:]}")
