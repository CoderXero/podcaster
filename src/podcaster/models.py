from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def now_utc() -> datetime:
    return datetime.now(UTC)


class Host(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    voice_id: str = Field(min_length=1, max_length=200)


class Segment(BaseModel):
    index: int = Field(ge=0)
    speaker: str = Field(min_length=1, max_length=32)
    text: str = Field(min_length=1, max_length=6000)
    kind: Literal["intro", "dialogue", "outro"] = "dialogue"

    @field_validator("text")
    @classmethod
    def no_markup_or_label(cls, value: str) -> str:
        value = " ".join(value.split())
        if not value or "```" in value or value.startswith("**") or re.match(r"^(?:ALEX|NAOMI|HOST\d*)\s*:", value, re.IGNORECASE):
            raise ValueError("segment text must be speakable plain text")
        return value


class Script(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int = 1
    episode_id: UUID = Field(default_factory=uuid4)
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    title: str = Field(min_length=1, max_length=200)
    slug: str = Field(min_length=1, max_length=80, pattern=r"^[a-z0-9][a-z0-9-]*$")
    language: str = Field(default="en", min_length=2, max_length=16)
    summary: str = Field(min_length=1, max_length=1000)
    description: str = Field(min_length=1, max_length=4000)
    show_notes: str = Field(min_length=1, max_length=12000)
    topics: list[str] = Field(default_factory=list, max_length=20)
    tags: list[str] = Field(default_factory=list, max_length=40)
    source_urls: list[str] = Field(default_factory=list, max_length=20)
    speakers: dict[str, Host]
    segments: list[Segment] = Field(min_length=1, max_length=500)
    script_status: Literal["draft", "approved", "awaiting_review"] = "draft"
    script_revision: int = Field(default=1, ge=1)
    prompt_version: str = "script-v1"
    created_at: datetime = Field(default_factory=now_utc)
    markdown_sha256: str | None = None

    @field_validator("title")
    @classmethod
    def single_line_title(cls, value: str) -> str:
        value = " ".join(value.split())
        if not value:
            raise ValueError("title must not be empty")
        return value

    @field_validator("topics", "tags")
    @classmethod
    def clean_labels(cls, values: list[str]) -> list[str]:
        if any(not x.strip() or len(x) > 80 for x in values):
            raise ValueError("topics and tags must contain bounded non-empty strings")
        return [x.strip() for x in values]

    @field_validator("source_urls")
    @classmethod
    def valid_urls(cls, values: list[str]) -> list[str]:
        from urllib.parse import urlparse

        for value in values:
            parsed = urlparse(value)
            if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                raise ValueError(f"invalid source URL: {value}")
        return values

    @model_validator(mode="after")
    def validate_script(self) -> Script:
        if len(self.speakers) != 2:
            raise ValueError("exactly two configured speakers are required")
        names = set(self.speakers)
        if any(segment.speaker not in names for segment in self.segments):
            raise ValueError("every segment speaker must be configured")
        if [segment.index for segment in self.segments] != list(range(len(self.segments))):
            raise ValueError("segment indices must be contiguous, starting at zero")
        if sum(len(segment.text.split()) for segment in self.segments) < 20:
            raise ValueError("script is too short to be a useful episode")
        return self


class PublishInfo(BaseModel):
    state: str = "NOT_STARTED"
    remote_episode_id: str | None = None
    audio_blob_uri: str | None = None
    image_blob_uri: str | None = None
    last_error: str | None = None
    published_at: datetime | None = None


class Episode(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int = 1
    local_episode_id: UUID
    slug: str
    title: str
    summary: str
    description: str
    show_notes: str
    topics: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    audio_path: str = "podcast.mp3"
    image_path: str | None = "cover.jpg"
    audio_mime_type: str = "audio/mpeg"
    duration_seconds: float = Field(gt=0)
    audio_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    ready_for_publish: bool = False
    publish: PublishInfo = Field(default_factory=PublishInfo)


class Manifest(BaseModel):
    schema_version: int = 1
    job_id: str
    slug: str
    stage: str
    source_path: str | None = None
    source_sha256: str | None = None
    last_good_state: str | None = None
    failed_stage: str | None = None
    error_type: str | None = None
    last_error: str | None = None
    attempts: dict[str, int] = Field(default_factory=dict)
    artifact_hashes: dict[str, str] = Field(default_factory=dict)
    checks: dict[str, bool] = Field(default_factory=dict)
    events: list[dict[str, Any]] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=now_utc)
    updated_at: datetime = Field(default_factory=now_utc)

    def event(self, stage: str, **data: Any) -> None:
        self.events.append({"at": now_utc().isoformat(), "stage": stage, **data})
        self.updated_at = now_utc()
