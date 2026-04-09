from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ProjectMapping(BaseModel):
    model_config = ConfigDict(extra="forbid")

    room_id: str
    project_id: int | None = None
    project_slug: str | None = None
    webhook_secret: str | None = None

    @field_validator("project_slug")
    @classmethod
    def normalize_project_slug(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip().strip("/")

    def resolved_project_id(self, default_project_id: int | None) -> int | None:
        return self.project_id if self.project_id is not None else default_project_id

    def resolved_project_slug(self, default_project_slug: str | None) -> str | None:
        return self.project_slug or default_project_slug


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


class TaigaUser(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: int | None = None
    full_name: str | None = None
    full_name_display: str | None = None
    username: str | None = None
    email: str | None = None

    @property
    def display_name(self) -> str | None:
        for value in (self.full_name_display, self.full_name, self.username, self.email):
            if value:
                return value
        return None


class TaigaUserStory(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: int
    ref: int
    subject: str
    description: str | None = None
    permalink: str | None = None
    project_id: int | None = None
    project_slug: str | None = None
    status_name: str | None = None
    owner: TaigaUser | None = None
    raw: dict[str, Any] = Field(default_factory=dict)


class NormalizedWebhookEvent(BaseModel):
    model_config = ConfigDict(extra="allow")

    action: str
    entity_type: str
    entity_label: str
    ref: int | None = None
    title: str | None = None
    actor_name: str | None = None
    comment_text: str | None = None
    link: str | None = None
    raw: dict[str, Any] = Field(default_factory=dict)


class TaskCommand(BaseModel):
    title: str
    description: str | None = None
