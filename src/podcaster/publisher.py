from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any

from .clients.gumu_api import GumuAPI, GumuAPIError
from .clients.oauth import ClientCredentialsToken
from .config import Config, ensure_directories
from .filesystem import collision_safe_destination, sha256_file
from .locks import EpisodeLock
from .models import Episode, Manifest
from .observability import audit
from .state import mark_failed, save_manifest, transition
from .storage.azure_blob import AzureBlobUploader


def _selector(value: dict[str, Any], selector: str) -> Any:
    current: Any = value
    for part in selector.split("."):
        if not isinstance(current, dict) or part not in current:
            raise ValueError(f"response does not contain configured ID field: {selector}")
        current = current[part]
    return current


def _sanitized(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _sanitized(item) for key, item in value.items() if not any(secret in key.lower() for secret in ("token", "secret", "password", "sig"))}
    if isinstance(value, list):
        return [_sanitized(item) for item in value]
    return value


def _same_tree(left: Path, right: Path) -> bool:
    left_files = sorted(path.relative_to(left) for path in left.rglob("*") if path.is_file())
    right_files = sorted(path.relative_to(right) for path in right.rglob("*") if path.is_file())
    return left_files == right_files and all(sha256_file(left / path) == sha256_file(right / path) for path in left_files)


def _archive_package(package: Path, published_root: Path, slug: str) -> Path:
    destination = collision_safe_destination(published_root / slug)
    staging = destination.with_name(f".{destination.name}.staging-{os.getpid()}")
    shutil.copytree(package, staging)
    if not _same_tree(package, staging):
        raise OSError("archive checksum verification failed")
    os.replace(staging, destination)
    return destination


def publish_one(slug: str, config: Config, *, dry_run: bool = False, confirm_publish: bool = False,
                upload_only: bool = False, create_draft_only: bool = False, resume: bool = False) -> str:
    if not dry_run and not resume and not confirm_publish and not config.publishing.auto_publish and not (upload_only or create_draft_only):
        raise ValueError("publishing requires --confirm-publish")
    paths = config.paths.expanded(); ensure_directories(config)
    package = paths.podcasts / slug
    episode = Episode.model_validate_json((package / "episode.json").read_text(encoding="utf-8"))
    audio = package / episode.audio_path
    if not episode.ready_for_publish or not audio.exists() or sha256_file(audio) != episode.audio_sha256:
        raise ValueError("package is not ready or audio checksum does not match")
    if config.publishing.require_image and (not episode.image_path or not (package / episode.image_path).is_file()):
        raise ValueError("publication requires cover.jpg")
    if not upload_only and not config.publishing.api_base_url.startswith("https://"):
        raise ValueError("live publishing requires an HTTPS api_base_url")
    manifest_path = paths.working / slug / "manifest.json"
    if dry_run:
        return f"{slug}: eligible for publication"
    pending_archive = False
    if manifest_path.exists():
        from .state import load_manifest
        previous = load_manifest(manifest_path)
        if previous.stage in {"DRAFT_CREATE_UNKNOWN", "PUBLISH_UNKNOWN"}:
            raise RuntimeError(f"reconciliation required before retrying {previous.stage}")
        pending_archive = previous.stage == "PUBLISHED_ARCHIVE_PENDING"
    manifest = Manifest(job_id=slug, slug=slug, stage="AUDIO_READY")
    if not pending_archive:
        save_manifest(manifest_path, manifest)
    else:
        manifest = previous
    with EpisodeLock(paths.working / f"{slug}.lock"):
        try:
            if pending_archive:
                transition(manifest, "ARCHIVING", manifest_path)
                _archive_package(package, paths.published, slug)
                transition(manifest, "ARCHIVED", manifest_path)
                shutil.rmtree(package)
                audit(paths.logs, slug, "ARCHIVED", remote_episode_id=episode.publish.remote_episode_id)
                return f"{slug}: ARCHIVED"
            if config.publishing.storage_adapter != "azure_blob":
                raise ValueError("no validated remote storage adapter configured; refusing to publish file:// or invented URIs")
            uploader = AzureBlobUploader(config.publishing.storage_account_url, config.publishing.audio_container, config.publishing.image_container)
            transition(manifest, "UPLOADING", manifest_path)
            audio_uri = uploader.upload(audio, episode_key=str(episode.local_episode_id), mime_type="audio/mpeg")
            if not uploader.verify(audio_uri, expected_sha256=episode.audio_sha256):
                raise ValueError("uploaded audio could not be verified")
            image_uri = None
            if episode.image_path:
                image = package / episode.image_path
                image_uri = uploader.upload(image, episode_key=str(episode.local_episode_id), mime_type="image/jpeg")
                if not uploader.verify(image_uri):
                    raise ValueError("uploaded artwork could not be verified")
            episode.publish.audio_blob_uri, episode.publish.image_blob_uri, episode.publish.state = audio_uri, image_uri, "UPLOADED"
            from .filesystem import atomic_write_json
            atomic_write_json(package / "episode.json", episode.model_dump(mode="json"))
            transition(manifest, "UPLOADED", manifest_path)
            if upload_only:
                return f"{slug}: UPLOADED"
            token_provider = ClientCredentialsToken(config.publishing.idp_discovery_url, os.getenv("PODCAST_CLIENT_ID", ""), os.getenv("PODCAST_CLIENT_SECRET", ""), config.publishing.oauth_scope)
            api = GumuAPI(config.publishing.api_base_url, token_provider)
            transition(manifest, "DRAFT_CREATING", manifest_path)
            payload = {"title": episode.title, "summary": episode.summary, "description": episode.description, "show_notes": episode.show_notes, "topics": episode.topics, "tags": episode.tags, "audio_blob_uri": audio_uri, "audio_mime_type": episode.audio_mime_type}
            if image_uri:
                payload["image_blob_uri"] = image_uri
            try:
                response = api.create_draft(payload)
            except GumuAPIError as error:
                if error.uncertain:
                    transition(manifest, "DRAFT_CREATE_UNKNOWN", manifest_path)
                raise
            remote_id = str(_selector(response, config.publishing.create_response_id_field))
            episode.publish.remote_episode_id, episode.publish.state = remote_id, "DRAFT_CREATED"
            manifest.event("DRAFT_RESPONSE", response=_sanitized(response), remote_episode_id=remote_id)
            atomic_write_json(package / "episode.json", episode.model_dump(mode="json"))
            transition(manifest, "DRAFT_CREATED", manifest_path)
            if create_draft_only or (not confirm_publish and not config.publishing.auto_publish):
                return f"{slug}: DRAFT_CREATED"
            transition(manifest, "PUBLISH_REQUESTED", manifest_path)
            episode.publish.state = "PUBLISH_REQUESTED"
            atomic_write_json(package / "episode.json", episode.model_dump(mode="json"))
            try:
                api.publish(remote_id)
            except GumuAPIError as error:
                if error.uncertain:
                    transition(manifest, "PUBLISH_UNKNOWN", manifest_path)
                raise
            if not config.publishing.publish_verification_enabled:
                raise ValueError("publish verification is required before archiving")
            status = api.get_episode(remote_id)
            if str(status.get("state", status.get("status", ""))).upper() not in {"PUBLISHED", "LIVE"}:
                raise ValueError("remote publish state was not verified")
            episode.publish.state = "PUBLISHED"
            from .models import now_utc
            episode.publish.published_at = now_utc()
            atomic_write_json(package / "episode.json", episode.model_dump(mode="json"))
            transition(manifest, "PUBLISHED_VERIFIED", manifest_path)
            transition(manifest, "ARCHIVING", manifest_path)
            _archive_package(package, paths.published, slug)
            transition(manifest, "ARCHIVED", manifest_path)
            shutil.rmtree(package)
            audit(paths.logs, slug, "ARCHIVED", remote_episode_id=episode.publish.remote_episode_id)
            return f"{slug}: ARCHIVED"
        except Exception as error:
            audit(paths.logs, slug, "FAILED", error_type=type(error).__name__, error=str(error))
            if manifest.stage == "ARCHIVING":
                transition(manifest, "PUBLISHED_ARCHIVE_PENDING", manifest_path, error=str(error))
            elif manifest.stage not in {"DRAFT_CREATE_UNKNOWN", "PUBLISH_UNKNOWN", "PUBLISHED_ARCHIVE_PENDING"}:
                mark_failed(manifest, manifest_path, manifest.stage, error)
            raise


def eligible(config: Config) -> list[str]:
    paths = config.paths.expanded()
    result: list[str] = []
    if not paths.podcasts.exists():
        return result
    for directory in sorted(paths.podcasts.iterdir()):
        episode_path = directory / "episode.json"
        if not directory.is_dir() or not episode_path.exists():
            continue
        try:
            episode = Episode.model_validate_json(episode_path.read_text(encoding="utf-8"))
            if episode.ready_for_publish and episode.publish.state != "PUBLISHED":
                result.append(directory.name)
        except Exception:
            continue
    return result
