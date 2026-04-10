from __future__ import annotations

import logging
from pathlib import Path
from urllib.parse import urlparse

import yaml
from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.models import BridgeConfig


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    taiga_base_url: str = "https://tree.taiga.io"
    taiga_api_url: str = "https://api.taiga.io/api/v1"
    taiga_username: str | None = None
    taiga_password: SecretStr | None = None
    taiga_token: SecretStr | None = None
    taiga_accept_language: str = "ru"
    taiga_project_id: int | None = None
    taiga_project_slug: str | None = None

    matrix_homeserver: str = "https://matrix.fishingteam.su"
    matrix_user_id: str = "@kbot:matrix.fishingteam.su"
    matrix_password: SecretStr
    matrix_state_user_id: str | None = None
    matrix_state_password: SecretStr | None = None

    bridge_public_url: str = "https://bridge.fishingteam.su"
    bridge_secret: SecretStr
    log_level: str = "INFO"
    config_path: Path = Field(default=Path("config.yaml"))
    data_dir: Path = Field(default=Path("data"))
    widget_frame_ancestors: str = "https://fishingteam.su https://matrix.fishingteam.su"

    @field_validator("taiga_api_url")
    @classmethod
    def normalize_taiga_api_url(cls, value: str) -> str:
        trimmed = value.rstrip("/")
        parsed = urlparse(trimmed)
        if "/api/" in parsed.path:
            return trimmed
        suffix = "/api/v1" if parsed.path in ("", "/") else f"{parsed.path}/api/v1"
        return parsed._replace(path=suffix).geturl().rstrip("/")

    @field_validator("taiga_base_url", "matrix_homeserver", "bridge_public_url")
    @classmethod
    def trim_trailing_slash(cls, value: str) -> str:
        return value.rstrip("/")

    @field_validator("matrix_state_user_id")
    @classmethod
    def normalize_optional_user_id(cls, value: str | None) -> str | None:
        if value is None:
            return None
        text = value.strip()
        return text or None

    @field_validator("taiga_project_slug")
    @classmethod
    def normalize_taiga_project_slug(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip().strip("/")

    @field_validator("taiga_accept_language")
    @classmethod
    def normalize_taiga_accept_language(cls, value: str) -> str:
        normalized = value.strip()
        return normalized or "ru"


def load_bridge_config(path: Path) -> BridgeConfig:
    if not path.exists():
        raise FileNotFoundError(f"Bridge config file not found: {path}")

    with path.open("r", encoding="utf-8") as handle:
        raw_data = yaml.safe_load(handle) or {}

    return BridgeConfig.model_validate(raw_data)


def save_bridge_config(path: Path, config: BridgeConfig) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    serialized = config.model_dump(mode="json", exclude_none=True)
    with path.open("w", encoding="utf-8") as handle:
        yaml.safe_dump(serialized, handle, allow_unicode=True, sort_keys=False)


def setup_logging(log_level: str) -> None:
    resolved_level = getattr(logging, log_level.upper(), logging.INFO)
    logging.basicConfig(
        level=resolved_level,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    )
