from __future__ import annotations

import json
import os
import tempfile
import time
from pathlib import Path

import typer

from .audio_maker import build_audio
from .config import Config, ensure_directories, load_config
from .models import Script
from .publisher import eligible, publish_one
from .script_import_export import export_script, import_markdown
from .scripter import run as run_scripter
from .state import load_manifest, transition

app = typer.Typer(help="Reliable Markdown-to-podcast pipeline.", no_args_is_help=True)
script_app = typer.Typer(help="Review and manage scripts.")
app.add_typer(script_app, name="script")


def cfg(config: Path | None) -> Config:
    value = load_config(config)
    ensure_directories(value)
    return value


@app.command()
def scripter(input: Path = typer.Option(..., "--input", exists=True, file_okay=False), recursive: bool = True,
             dry_run: bool = False, force: bool = False, on_success: str | None = None,
             confirm_delete: bool = False, max_files: int | None = None, continue_on_error: bool = False,
             config: Path | None = None) -> None:
    """Turn Markdown articles into reviewable structured scripts."""
    for result in run_scripter(input, cfg(config), recursive=recursive, dry_run=dry_run, force=force, on_success=on_success, confirm_delete=confirm_delete, max_files=max_files, continue_on_error=continue_on_error):
        typer.echo(result)


@app.command("audio-maker")
def audio_maker(slug: str | None = None, dry_run: bool = False, regenerate: bool = False,
                tts_mode: str | None = None, intro: Path | None = None, outro: Path | None = None,
                image: Path | None = None, config: Path | None = None) -> None:
    """Synthesize approved scripts and package validated MP3 episodes."""
    value = cfg(config)
    if tts_mode:
        value = value.model_copy(update={"audio": value.audio.model_copy(update={"tts_mode": tts_mode})})
    slugs = [slug] if slug else sorted(path.stem for path in value.paths.expanded().scripts.glob("*.json"))
    for item in slugs:
        try:
            typer.echo(build_audio(item, value, dry_run=dry_run, regenerate=regenerate, intro=intro, outro=outro, image=image))
        except Exception as error:
            typer.echo(f"{item}: FAILED: {error}", err=True)
            raise typer.Exit(code=1)


@app.command()
def publisher(slug: str | None = None, all: bool = False, dry_run: bool = False,
              confirm_publish: bool = False, resume: bool = False, upload_only: bool = False,
              create_draft_only: bool = False, config: Path | None = None) -> None:
    """Upload, create, verify, publish, and archive an episode."""
    value = cfg(config)
    slugs = [slug] if slug else eligible(value) if all or not slug else []
    if not slugs:
        typer.echo("No eligible episodes.")
        return
    for item in slugs:
        try:
            typer.echo(publish_one(item, value, dry_run=dry_run, confirm_publish=confirm_publish, resume=resume, upload_only=upload_only, create_draft_only=create_draft_only))
        except Exception as error:
            typer.echo(f"{item}: FAILED: {error}", err=True)
            raise typer.Exit(code=1)


@app.command()
def doctor(test_paid_api: bool = False, config: Path | None = None) -> None:
    """Check local configuration and Ollama; paid API checks require the explicit flag."""
    value = cfg(config)
    typer.echo(json.dumps({"paths": {key: str(path) for key, path in value.paths.expanded().model_dump().items()}, "ollama": {"base_url": value.ollama.base_url, "model": value.ollama.model}, "ffmpeg": bool(__import__("shutil").which("ffmpeg") and __import__("shutil").which("ffprobe")), "publishing_configured": bool(value.publishing.api_base_url and value.publishing.storage_adapter)}, indent=2))
    from .clients.ollama import OllamaClient
    try:
        typer.echo(json.dumps(OllamaClient(value.ollama.base_url, value.ollama.model, value.ollama.timeout_seconds).doctor(), indent=2))
    except Exception as error:
        typer.echo(f"Ollama: unavailable ({error})", err=True)
        raise typer.Exit(code=4)
    if os.getenv("ELEVENLABS_API_KEY"):
        from .clients.elevenlabs import ElevenLabsClient
        try:
            client = ElevenLabsClient(os.environ["ELEVENLABS_API_KEY"], value.audio.elevenlabs_model, value.audio.output_format)
            voices = client.list_voices()
            paid_test = False
            if test_paid_api:
                with tempfile.TemporaryDirectory() as directory:
                    destination = Path(directory) / "test.mp3"
                    client.synthesize("This is a short paid API test.", value.hosts["ALEX"].voice_id, destination)
                    paid_test = destination.stat().st_size > 0
            typer.echo(json.dumps({"elevenlabs": {"reachable": True, "configured_voices_available": {key: host.voice_id in voices for key, host in value.hosts.items()}, "paid_test_passed": paid_test}}, indent=2))
        except Exception as error:
            typer.echo(f"ElevenLabs: unavailable ({error})", err=True)
    else:
        typer.echo("ElevenLabs: ELEVENLABS_API_KEY is not configured")


@script_app.command("list")
def script_list(config: Path | None = None) -> None:
    value = cfg(config)
    for path in sorted(value.paths.expanded().scripts.glob("*.json")):
        try:
            item = Script.model_validate_json(path.read_text(encoding="utf-8"))
            typer.echo(f"{item.slug}\t{item.script_status}\t{item.title}")
        except Exception:
            typer.echo(f"{path.stem}\tINVALID")


@script_app.command("show")
def script_show(slug: str, config: Path | None = None) -> None:
    value = cfg(config)
    path = value.paths.expanded().scripts / f"{slug}.json"
    typer.echo(path.read_text(encoding="utf-8"))


@script_app.command("approve")
def script_approve(slug: str, config: Path | None = None) -> None:
    value = cfg(config); path = value.paths.expanded().scripts / f"{slug}.json"
    item = Script.model_validate_json(path.read_text(encoding="utf-8"))
    item = item.model_copy(update={"script_status": "approved"})
    export_script(item, value.paths.expanded().scripts / f"{slug}.md", path)
    manifest_path = value.paths.expanded().working / slug / "manifest.json"
    if manifest_path.exists():
        manifest = load_manifest(manifest_path)
        if manifest.stage == "AWAITING_APPROVAL":
            transition(manifest, "SCRIPT_APPROVED", manifest_path)
    typer.echo(f"{slug}: approved")


@script_app.command("import")
def script_import(slug: str, config: Path | None = None) -> None:
    value = cfg(config); root = value.paths.expanded().scripts
    json_path, md_path = root / f"{slug}.json", root / f"{slug}.md"
    item = import_markdown(md_path, Script.model_validate_json(json_path.read_text(encoding="utf-8")))
    export_script(item, md_path, json_path)
    manifest_path = value.paths.expanded().working / slug / "manifest.json"
    if manifest_path.exists():
        manifest = load_manifest(manifest_path)
        if manifest.stage == "SCRIPT_APPROVED":
            transition(manifest, "AWAITING_APPROVAL", manifest_path)
    typer.echo(f"{slug}: imported and awaiting review")


@app.command()
def validate(slug: str, config: Path | None = None) -> None:
    value = cfg(config); root = value.paths.expanded().scripts
    item = Script.model_validate_json((root / f"{slug}.json").read_text(encoding="utf-8"))
    typer.echo(json.dumps({"slug": slug, "valid": True, "status": item.script_status}, indent=2))


@app.command()
def status(json_output: bool = typer.Option(False, "--json"), config: Path | None = None) -> None:
    value = cfg(config); rows = []
    for path in sorted(value.paths.expanded().working.glob("*/manifest.json")):
        try:
            rows.append(load_manifest(path).model_dump(mode="json"))
        except Exception:
            pass
    typer.echo(json.dumps(rows, indent=2) if json_output else "\n".join(f"{row['slug']}\t{row['stage']}" for row in rows))


@app.command()
def review(slug: str, config: Path | None = None) -> None:
    """Print a script for human review; approval remains an explicit command."""
    script_show(slug, config)


@app.command()
def retry(slug: str, stage: str = "audio", confirm_publish: bool = False, config: Path | None = None) -> None:
    """Retry a safe local stage or reconcile a publish stage explicitly."""
    value = cfg(config)
    if stage == "audio":
        typer.echo(build_audio(slug, value, regenerate=False))
    elif stage == "publish":
        typer.echo(publish_one(slug, value, confirm_publish=confirm_publish, resume=True))
    else:
        raise typer.BadParameter("stage must be audio or publish")


@app.command()
def cleanup(older_than: str = "7d", dry_run: bool = False, config: Path | None = None) -> None:
    """Remove only stale job-local failed scratch directories."""
    value = cfg(config); cutoff = time.time() - int(older_than.rstrip("d")) * 86400; removed = 0
    for path in value.paths.expanded().working.glob("*/segments"):
        if path.stat().st_mtime < cutoff:
            typer.echo(f"would remove {path}" if dry_run else f"removed {path}")
            if not dry_run:
                import shutil
                shutil.rmtree(path)
            removed += 1
    if not removed:
        typer.echo("No stale scratch directories.")


@app.command()
def run(input: Path = typer.Option(..., "--input", exists=True, file_okay=False), stop_after: str | None = None,
        confirm_publish: bool = False, config: Path | None = None) -> None:
    from .pipeline import run as run_pipeline
    for result in run_pipeline(input, cfg(config), stop_after=stop_after, confirm_publish=confirm_publish):
        typer.echo(result)


def main() -> None:
    app()


def scripter_main() -> None:
    # Standalone command maps directly to the same Typer command surface.
    typer.run(scripter)


def audio_maker_main() -> None:
    typer.run(audio_maker)


def publisher_main() -> None:
    typer.run(publisher)
