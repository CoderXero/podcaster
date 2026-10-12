from __future__ import annotations

from pathlib import Path

from .audio_maker import build_audio
from .config import Config
from .filesystem import discover_markdown, normalized_text, sha256_bytes
from .models import Script
from .publisher import publish_one
from .scripter import clean_article
from .scripter import run as run_scripter


def run(input_dir: Path, config: Config, *, stop_after: str | None = None, confirm_publish: bool = False) -> list[str]:
    sources = discover_markdown(input_dir, recursive=config.scripter.recursive)
    output = run_scripter(input_dir, config, continue_on_error=True)
    if stop_after == "script":
        return output
    scripts = []
    for json_path in config.paths.expanded().scripts.glob("*.json"):
        try:
            scripts.append(Script.model_validate_json(json_path.read_text(encoding="utf-8")))
        except Exception:
            continue
    source_hashes = {sha256_bytes(normalized_text(clean_article(path.read_text(encoding="utf-8-sig"))[1]).encode()) for path in sources}
    for script in scripts:
        if script.source_sha256 not in source_hashes or script.script_status != "approved":
            continue
        try:
            output.append(build_audio(script.slug, config))
            if stop_after == "audio":
                continue
            output.append(publish_one(script.slug, config, confirm_publish=confirm_publish))
        except Exception as error:
            output.append(f"{script.slug}: FAILED: {error}")
    return output
