from __future__ import annotations

import os
import shutil
from pathlib import Path

from .audio.playlist import render_playlist
from .audio.quality import validate_mp3
from .clients.elevenlabs import ElevenLabsClient
from .config import Config, ensure_directories
from .filesystem import atomic_write_json, atomic_write_text, sha256_file
from .locks import EpisodeLock
from .models import Episode, Manifest, Script
from .observability import audit
from .script_import_export import markdown_is_in_sync
from .state import mark_failed, save_manifest, transition


def _cache_key(script: Script, index: int, voice_id: str, model: str, output_format: str) -> str:
    import hashlib
    segment = script.segments[index]
    return hashlib.sha256(f"{segment.text}\0{voice_id}\0{model}\0{output_format}".encode()).hexdigest()[:24]


def build_audio(slug: str, config: Config, *, dry_run: bool = False, regenerate: bool = False,
                intro: Path | None = None, outro: Path | None = None,
                image: Path | None = None) -> str:
    paths = config.paths.expanded(); ensure_directories(config)
    script_path, markdown_path = paths.scripts / f"{slug}.json", paths.scripts / f"{slug}.md"
    script = Script.model_validate_json(script_path.read_text(encoding="utf-8"))
    if not markdown_is_in_sync(markdown_path, script):
        raise ValueError("script Markdown and JSON are out of sync; use `podcaster script import`")
    if script.script_status != "approved":
        raise ValueError("script requires approval before audio generation")
    package = paths.podcasts / slug
    existing_final = package / "podcast.mp3"
    if existing_final.exists() and not regenerate:
        if (package / "episode.json").exists():
            try:
                existing_episode = Episode.model_validate_json((package / "episode.json").read_text(encoding="utf-8"))
                if existing_episode.ready_for_publish and sha256_file(existing_final) == existing_episode.audio_sha256:
                    return f"{slug}: SKIPPED (audio already ready)"
            except Exception:
                pass
        raise FileExistsError(f"audio package exists; use --regenerate to replace it: {package}")
    working = paths.working / slug / "segments"
    manifest_path = paths.working / slug / "manifest.json"
    manifest = Manifest(job_id=slug, slug=slug, stage="SCRIPT_APPROVED", source_sha256=script.source_sha256)
    save_manifest(manifest_path, manifest)
    with EpisodeLock(paths.working / f"{slug}.lock"):
        try:
            if dry_run:
                return f"{slug}: would synthesize {len(script.segments)} turns"
            transition(manifest, "AUDIO_GENERATING", manifest_path)
            working.mkdir(parents=True, exist_ok=True)
            api_key = os.getenv("ELEVENLABS_API_KEY", "")
            client = ElevenLabsClient(api_key, config.audio.elevenlabs_model, config.audio.output_format)
            tracks: list[Path] = []
            if intro and config.audio.intro_policy in {"external_only", "combine"}:
                tracks.append(intro)
            segments = sorted(script.segments, key=lambda item: item.index)
            if config.audio.intro_policy == "external_only":
                segments = [segment for segment in segments if segment.kind not in {"intro", "outro"}]
            if config.audio.tts_mode == "dialogue":
                group: list[tuple[str, str]] = []
                characters = 0
                group_number = 0
                for segment in segments + [None]:
                    voice_turn = (segment.text, config.hosts[segment.speaker].voice_id) if segment else None
                    if voice_turn and group and characters + len(voice_turn[0]) > 2000:
                        target = working / f"dialogue-{group_number:04d}.mp3"
                        if regenerate:
                            target.unlink(missing_ok=True)
                        if not target.exists() or target.stat().st_size < 256:
                            client.synthesize_dialogue(group, target)
                        validate_mp3(target); tracks.append(target); group_number += 1; group = []; characters = 0
                    if voice_turn:
                        group.append(voice_turn); characters += len(voice_turn[0])
                if group:
                    target = working / f"dialogue-{group_number:04d}.mp3"
                    if regenerate:
                        target.unlink(missing_ok=True)
                    if not target.exists() or target.stat().st_size < 256:
                        client.synthesize_dialogue(group, target)
                    validate_mp3(target); tracks.append(target)
            else:
                for segment in segments:
                    voice = config.hosts[segment.speaker].voice_id
                    target = working / f"{segment.index:04d}-{_cache_key(script, segment.index, voice, config.audio.elevenlabs_model, config.audio.output_format)}.mp3"
                    if regenerate:
                        target.unlink(missing_ok=True)
                    if not target.exists() or target.stat().st_size < 256:
                        client.synthesize(segment.text, voice, target)
                    validate_mp3(target)
                    tracks.append(target)
            if outro and config.audio.intro_policy in {"external_only", "combine"}:
                tracks.append(outro)
            transition(manifest, "AUDIO_PACKAGING", manifest_path)
            package.mkdir(parents=True, exist_ok=True)
            if image:
                if not image.is_file():
                    raise ValueError(f"artwork does not exist: {image}")
                shutil.copy2(image, package / "cover.jpg")
            final = package / "podcast.mp3"
            if regenerate and final.exists():
                backup = paths.working / slug / "backups"
                backup.mkdir(parents=True, exist_ok=True)
                shutil.copy2(final, backup / "podcast.mp3.bak")
            final_part = final.with_name("podcast.part.mp3")
            render_playlist(tracks, final_part, config.audio.silence_ms_between_turns, config.audio.mp3_bitrate, config.audio.target_lufs, config.audio.true_peak_db)
            seconds, _ = validate_mp3(final_part)
            os.replace(final_part, final)
            _tag_mp3(final, script, package)
            seconds, digest = validate_mp3(final)
            atomic_write_text(package / "title", script.title + "\n")
            atomic_write_text(package / "description.txt", script.description.strip() + "\n")
            atomic_write_text(package / "show notes.txt", script.show_notes.strip() + "\n")
            episode = Episode(local_episode_id=script.episode_id, slug=slug, title=script.title, summary=script.summary, description=script.description, show_notes=script.show_notes, topics=script.topics, tags=script.tags, duration_seconds=seconds, audio_sha256=digest, image_path="cover.jpg" if (package / "cover.jpg").exists() else None, ready_for_publish=True)
            atomic_write_json(package / "episode.json", episode.model_dump(mode="json"))
            manifest.artifact_hashes["podcast.mp3"] = sha256_file(final)
            manifest.checks.update({"decoded": True, "duration": seconds > 0, "package_complete": True})
            transition(manifest, "AUDIO_READY", manifest_path)
            atomic_write_json(package / "manifest.json", manifest.model_dump(mode="json"))
            # Only successful job-local intermediates are disposable.
            shutil.rmtree(working, ignore_errors=True)
            audit(paths.logs, slug, "AUDIO_READY", duration_seconds=seconds, characters=sum(len(segment.text) for segment in script.segments))
            return f"{slug}: AUDIO_READY"
        except Exception as error:
            audit(paths.logs, slug, "FAILED", error_type=type(error).__name__, error=str(error))
            mark_failed(manifest, manifest_path, manifest.stage, error)
            raise


def _tag_mp3(path: Path, script: Script, package: Path) -> None:
    """Write stable ID3 metadata without making tagging a network concern."""
    from mutagen.id3 import APIC, COMM, ID3, TALB, TIT2, TPE1
    from mutagen.mp3 import MP3

    audio = MP3(path)
    tags = audio.tags or ID3()
    tags.add(TIT2(encoding=3, text=script.title))
    tags.add(TPE1(encoding=3, text="Alex Zulu & Naomi Zed"))
    tags.add(TALB(encoding=3, text="Gumu-Gumu"))
    tags.add(COMM(encoding=3, lang="eng", desc="", text="Gumu-Gumu podcast"))
    cover = package / "cover.jpg"
    if cover.exists():
        tags.add(APIC(encoding=3, mime="image/jpeg", type=3, desc="Cover", data=cover.read_bytes()))
    audio.tags = tags
    audio.save()
