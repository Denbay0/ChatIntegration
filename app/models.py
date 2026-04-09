from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ProjectMapping(BaseModel):
    model_config = ConfigDict(extra="forbid")

    room_id: str
    board_id: int
    position: int = Field(default=2, description="1 = first in cell, 2 = last in cell")
    column_id: int | None = None
    lane_id: int | None = None
    webhook_secret: str | None = None

    @field_validator("position")
    @classmethod
    def validate_position(cls, value: int) -> int:
        if value not in (1, 2):
            raise ValueError("position must be 1 or 2")
        return value


class BridgeConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    projects: dict[str, ProjectMapping]

    def get_project(self, slug: str) -> ProjectMapping | None:
        return self.projects.get(slug)

    def get_project_by_room(self, room_id: str) -> tuple[str, ProjectMapping] | None:
        for slug, project in self.projects.items():
            if project.room_id == room_id:
                return slug, project
        return None


class KaitenUser(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: int | None = None
    full_name: str | None = None
    username: str | None = None
    email: str | None = None

    @property
    def display_name(self) -> str | None:
        for value in (self.full_name, self.username, self.email):
            if value:
                return value
        return None


class KaitenCard(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: int
    title: str
    description: str | None = None
    board_id: int | None = None
    column_id: int | None = None
    lane_id: int | None = None
    owner: KaitenUser | None = None
    raw: dict[str, Any] = Field(default_factory=dict)


class NormalizedWebhookEvent(BaseModel):
    model_config = ConfigDict(extra="allow")

    event_name: str
    card_id: int | None = None
    title: str | None = None
    actor_name: str | None = None
    comment_text: str | None = None
    link: str | None = None
    raw: dict[str, Any] = Field(default_factory=dict)


class TaskCommand(BaseModel):
    title: str
    description: str | None = None


class CardLookupCommand(BaseModel):
    card_id: int
