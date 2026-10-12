from __future__ import annotations

from pathlib import Path

from .filesystem import atomic_write_json
from .models import Manifest

ALLOWED_TRANSITIONS = {
    "SOURCE_DISCOVERED": {"SCRIPT_GENERATING", "FAILED"},
    "SCRIPT_GENERATING": {"SCRIPT_READY", "AWAITING_APPROVAL", "FAILED"},
    "SCRIPT_READY": {"AWAITING_APPROVAL", "SCRIPT_APPROVED", "FAILED"},
    "AWAITING_APPROVAL": {"SCRIPT_APPROVED", "FAILED"},
    "SCRIPT_APPROVED": {"AUDIO_GENERATING", "AWAITING_APPROVAL", "FAILED"},
    "AUDIO_GENERATING": {"AUDIO_PACKAGING", "FAILED"},
    "AUDIO_PACKAGING": {"AUDIO_READY", "FAILED"},
    "AUDIO_READY": {"UPLOADING", "FAILED"},
    "UPLOADING": {"UPLOADED", "DRAFT_CREATE_UNKNOWN", "FAILED"},
    "UPLOADED": {"DRAFT_CREATING", "FAILED"},
    "DRAFT_CREATING": {"DRAFT_CREATED", "DRAFT_CREATE_UNKNOWN", "FAILED"},
    "DRAFT_CREATED": {"PUBLISH_REQUESTED", "FAILED"},
    "PUBLISH_REQUESTED": {"PUBLISHED_VERIFIED", "PUBLISH_UNKNOWN", "FAILED"},
    "PUBLISHED_VERIFIED": {"ARCHIVING", "FAILED"},
    "ARCHIVING": {"ARCHIVED", "PUBLISHED_ARCHIVE_PENDING", "FAILED"},
}


def save_manifest(path: Path, manifest: Manifest) -> None:
    atomic_write_json(path, manifest.model_dump(mode="json"))


def load_manifest(path: Path) -> Manifest:
    return Manifest.model_validate_json(path.read_text(encoding="utf-8"))


def transition(manifest: Manifest, new_stage: str, path: Path, **data: object) -> None:
    if new_stage != "FAILED" and new_stage not in ALLOWED_TRANSITIONS.get(manifest.stage, set()):
        raise ValueError(f"invalid state transition {manifest.stage} -> {new_stage}")
    previous = manifest.stage
    manifest.last_good_state = previous if new_stage != "FAILED" else manifest.last_good_state
    manifest.stage = new_stage
    manifest.event(new_stage, previous=previous, **data)
    save_manifest(path, manifest)


def mark_failed(manifest: Manifest, path: Path, stage: str, error: Exception) -> None:
    manifest.failed_stage = stage
    manifest.error_type = type(error).__name__
    manifest.last_error = str(error)[:2000]
    manifest.stage = "FAILED"
    manifest.event("FAILED", failed_stage=stage, error_type=type(error).__name__)
    save_manifest(path, manifest)
