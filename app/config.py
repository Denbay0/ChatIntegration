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

    kaiten_api_base_url: str
    kaiten_web_base_url: str
    kaiten_token: SecretStr

    matrix_homeserver: str = "https://matrix.fishingteam.su"
    matrix_user_id: str = "@kbot:matrix.fishingteam.su"
    matrix_password: SecretStr

    bridge_secret: SecretStr
    log_level: str = "INFO"
    config_path: Path = Field(default=Path("config.yaml"))
    data_dir: Path = Field(default=Path("data"))

    @field_validator("kaiten_api_base_url")
    @classmethod
    def normalize_kaiten_api_base_url(cls, value: str) -> str:
        trimmed = value.rstrip("/")
        parsed = urlparse(trimmed)
        if "/api/" in parsed.path:
            return trimmed
        suffix = "/api/latest" if parsed.path in ("", "/") else f"{parsed.path}/api/latest"
        return parsed._replace(path=suffix).geturl().rstrip("/")

    @field_validator("kaiten_web_base_url", "matrix_homeserver")
    @classmethod
    def trim_trailing_slash(cls, value: str) -> str:
        return value.rstrip("/")


def load_bridge_config(path: Path) -> BridgeConfig:
    if not path.exists():
        raise FileNotFoundError(f"Bridge config file not found: {path}")

    with path.open("r", encoding="utf-8") as handle:
        raw_data = yaml.safe_load(handle) or {}

    return BridgeConfig.model_validate(raw_data)


def setup_logging(log_level: str) -> None:
    resolved_level = getattr(logging, log_level.upper(), logging.INFO)
    logging.basicConfig(
        level=resolved_level,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    )
