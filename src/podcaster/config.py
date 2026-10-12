from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

from .models import Host


class AppConfig(BaseModel):
    show_name: str = "Gumu-Gumu"
    language: str = "en"
    log_level: str = "INFO"


class PathsConfig(BaseModel):
    scripts: Path = Path("~/Downloads/output/scripts")
    podcasts: Path = Path("~/Downloads/output/podcasts")
    working: Path = Path("~/Downloads/output/working")
    archived_sources: Path = Path("~/Downloads/output/archived-sources")
    completed_scripts: Path = Path("~/Downloads/output/completed-scripts")
    published: Path = Path("~/Music/podcasts/published")
    logs: Path = Path("~/Downloads/output/logs")

    def expanded(self) -> PathsConfig:
        return self.__class__(**{name: value.expanduser() for name, value in self.model_dump().items()})


class ScripterConfig(BaseModel):
    recursive: bool = True
    source_disposition: str = Field(default="archive", pattern="^(keep|archive|delete)$")
    require_review: bool = True
    target_minutes: float = 10
    min_minutes: float = 5
    max_minutes: float = 15
    speech_words_per_minute: int = 150
    max_retries: int = 3
    max_input_bytes: int = 5_000_000


class OllamaConfig(BaseModel):
    base_url: str = "http://127.0.0.1:11434"
    model: str = "gpt-oss:20b"
    num_ctx: int = 32768
    temperature: float = 0.5
    timeout_seconds: float = 240
    max_output_tokens: int = 5000


class AudioConfig(BaseModel):
    tts_mode: str = Field(default="turns", pattern="^(turns|dialogue)$")
    elevenlabs_model: str = "eleven_multilingual_v2"
    output_format: str = "mp3_44100_128"
    silence_ms_between_turns: int = Field(default=200, ge=0, le=5000)
    intro_policy: str = Field(default="script_only", pattern="^(script_only|external_only|combine)$")
    target_lufs: float = -16
    true_peak_db: float = -1.0
    mp3_bitrate: str = "160k"


class PublishingConfig(BaseModel):
    api_base_url: str = ""
    idp_discovery_url: str = "https://iam.zambeziblue.com/.well-known/openid-configuration"
    oauth_scope: str = ""
    auto_publish: bool = False
    storage_adapter: str = ""
    storage_account_url: str = ""
    audio_container: str = ""
    image_container: str = ""
    require_image: bool = True
    create_response_id_field: str = "id"
    publish_verification_enabled: bool = True


class Config(BaseModel):
    app: AppConfig = Field(default_factory=AppConfig)
    paths: PathsConfig = Field(default_factory=PathsConfig)
    scripter: ScripterConfig = Field(default_factory=ScripterConfig)
    ollama: OllamaConfig = Field(default_factory=OllamaConfig)
    hosts: dict[str, Host] = Field(default_factory=lambda: {
        "ALEX": Host(name="Alex Zulu", voice_id="orS9zubkf3wfUBO5E2mK"),
        "NAOMI": Host(name="Naomi Zed", voice_id="g0IlXuNNtW9CjDtDGv70"),
    })
    audio: AudioConfig = Field(default_factory=AudioConfig)
    publishing: PublishingConfig = Field(default_factory=PublishingConfig)


def load_config(path: Path | None = None, overrides: dict[str, Any] | None = None) -> Config:
    path = path or Path(os.getenv("PODCASTER_CONFIG", "~/.config/podcaster/config.yaml")).expanduser()
    data: dict[str, Any] = {}
    if path.exists():
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    data = dict(data)
    env_map = {
        "ELEVENLABS_API_KEY": ("audio", "elevenlabs_api_key"),
        "PODCAST_API_BASE_URL": ("publishing", "api_base_url"),
        "PODCAST_CLIENT_ID": ("publishing", "client_id"),
        "PODCAST_CLIENT_SECRET": ("publishing", "client_secret"),
    }
    for env_name, (section, key) in env_map.items():
        if os.getenv(env_name):
            data.setdefault(section, {})[key] = os.environ[env_name]
    for key, value in (overrides or {}).items():
        section, field = key.split(".", 1)
        data.setdefault(section, {})[field] = value
    return Config.model_validate(data).model_copy(update={"paths": PathsConfig(**Config.model_validate(data).paths.expanded().model_dump())})


def ensure_directories(config: Config) -> None:
    paths = config.paths.expanded()
    for path in paths.model_dump().values():
        Path(path).mkdir(parents=True, exist_ok=True)
