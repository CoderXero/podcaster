from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

from .filesystem import atomic_write_text, normalized_text, sha256_bytes
from .models import Script, Segment


def parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    text = text.replace("\r\n", "\n")
    if not text.startswith("---\n"):
        return {}, text
    marker = text.find("\n---", 4)
    if marker < 0:
        raise ValueError("unterminated YAML frontmatter")
    metadata = yaml.safe_load(text[4:marker]) or {}
    if not isinstance(metadata, dict):
        raise ValueError("frontmatter must be a mapping")
    return metadata, text[marker + 4 :].lstrip("\n")


def render_markdown(script: Script) -> str:
    frontmatter = {
        "schema_version": script.schema_version,
        "source_id": f"sha256:{script.source_sha256}",
        "episode_id": str(script.episode_id),
        "title": script.title,
        "show": "Gumu-Gumu",
        "status": script.script_status,
        "topics": script.topics,
        "tags": script.tags,
    }
    lines = ["---", yaml.safe_dump(frontmatter, sort_keys=False).rstrip(), "---", "", f"# {script.title}", "",
             "## Production notes", f"- Language: {script.language}",
             f"- Speakers: {', '.join(host.name for host in script.speakers.values())}.", "", "## Script", ""]
    for segment in script.segments:
        display = script.speakers[segment.speaker].name.upper()
        lines.append(f"**{display}:** {segment.text}")
        lines.append("")
    if script.show_notes:
        lines.extend(["## Show notes", "", script.show_notes, ""])
    return "\n".join(lines).rstrip() + "\n"


def export_script(script: Script, markdown_path: Path, json_path: Path) -> Script:
    rendered = render_markdown(script)
    script = script.model_copy(update={"markdown_sha256": sha256_bytes(normalized_text(rendered).encode())})
    atomic_write_text(json_path, script.model_dump_json(indent=2) + "\n")
    atomic_write_text(markdown_path, render_markdown(script))
    return script


def _display_to_key(value: str, script: Script) -> str:
    normalized = value.strip().lower().rstrip(":")
    for key, host in script.speakers.items():
        if normalized in {key.lower(), host.name.lower()}:
            return key
    raise ValueError(f"unknown speaker label: {value}")


def import_markdown(markdown_path: Path, existing: Script) -> Script:
    metadata, body = parse_frontmatter(markdown_path.read_text(encoding="utf-8-sig"))
    segments: list[Segment] = []
    pattern = re.compile(r"^\*\*(?P<speaker>[^*]+):\*\*\s*(?P<text>.+?)\s*$")
    for line in body.splitlines():
        match = pattern.match(line.strip())
        if match:
            text = re.sub(r"\s+", " ", match.group("text")).strip()
            segments.append(Segment(index=len(segments), speaker=_display_to_key(match.group("speaker"), existing), text=text))
    if not segments:
        raise ValueError("Markdown contains no recognized speaker turns")
    title = str(metadata.get("title") or existing.title)
    return existing.model_copy(update={
        "title": title,
        "segments": segments,
        "script_revision": existing.script_revision + 1,
        "script_status": "awaiting_review",
        "markdown_sha256": sha256_bytes(normalized_text(markdown_path.read_text(encoding="utf-8-sig")).encode()),
    })


def markdown_is_in_sync(markdown_path: Path, script: Script) -> bool:
    if not markdown_path.exists() or not script.markdown_sha256:
        return False
    current = sha256_bytes(normalized_text(markdown_path.read_text(encoding="utf-8-sig")).encode())
    return current == script.markdown_sha256
