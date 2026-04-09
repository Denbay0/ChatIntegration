from __future__ import annotations

import html
import re
from dataclasses import dataclass
from typing import Any

from app.models import NormalizedWebhookEvent, TaigaUserStory, TaskCommand

WHITESPACE_RE = re.compile(r"\s+")
TAG_RE = re.compile(r"<[^>]+>")


@dataclass(slots=True)
class MatrixMessage:
    body: str
    formatted_body: str | None = None


def parse_task_command(message: str) -> TaskCommand:
    payload = message.removeprefix("!task").strip()
    if not payload:
        raise ValueError("Usage: !task Title | description")

    title_part, separator, description_part = payload.partition("|")
    title = title_part.strip()
    description = description_part.strip() if separator else None

    if not title:
        raise ValueError("Task title cannot be empty.")

    return TaskCommand(title=title, description=description or None)


def build_help_message() -> MatrixMessage:
    body = (
        "Available commands:\n"
        "!help\n"
        "!task Title | description"
    )
    formatted_body = (
        "<p><strong>Available commands:</strong><br>"
        "<code>!help</code><br>"
        "<code>!task Title | description</code></p>"
    )
    return MatrixMessage(body=body, formatted_body=formatted_body)


def build_taiga_link(
    base_url: str,
    project_slug: str | None,
    entity_type: str,
    ref: int | None,
    permalink: str | None = None,
) -> str | None:
    if permalink:
        return permalink
    if not project_slug or ref is None:
        return None
    suffix = {
        "userstory": "us",
        "task": "task",
        "issue": "issue",
        "milestone": "milestone",
        "wikipage": "wiki",
    }.get(entity_type, entity_type)
    return f"{base_url.rstrip('/')}/project/{project_slug}/{suffix}/{ref}"


def normalize_webhook_event(payload: dict[str, Any], web_base_url: str) -> NormalizedWebhookEvent:
    data = _extract_mapping(payload, "data")
    change = _extract_mapping(payload, "change")
    actor = _extract_mapping(payload, "by")

    entity_type = _string_or_none(_pick_first(payload, "type")) or "event"
    action = _string_or_none(_pick_first(payload, "action")) or "change"
    ref = _coerce_int(_pick_first(data, "ref", "id"), default=None)
    title = _string_or_none(_pick_first(data, "subject", "name", "slug", "content"))
    comment_text = _extract_comment_text(payload, change, data)
    actor_name = _extract_actor_name(actor, data)
    project_slug = _extract_project_slug(data)
    link = build_taiga_link(
        base_url=web_base_url,
        project_slug=project_slug,
        entity_type=entity_type,
        ref=ref,
        permalink=_string_or_none(_pick_first(data, "permalink")),
    )

    return NormalizedWebhookEvent(
        action=action,
        entity_type=entity_type,
        entity_label=_entity_label(entity_type),
        ref=ref,
        title=title,
        actor_name=actor_name,
        comment_text=comment_text,
        link=link,
        raw=payload,
    )


def format_webhook_message(event: NormalizedWebhookEvent) -> MatrixMessage:
    first_line = f"[Taiga] {_human_action(event.action)}"
    if event.entity_type != "test":
        first_line += f" {event.entity_label}"
    first_line += ":"

    entity_part = None
    if event.ref is not None and event.title:
        entity_part = f"#{event.ref} {event.title}"
    elif event.ref is not None:
        entity_part = f"#{event.ref}"
    elif event.title:
        entity_part = event.title

    if entity_part:
        first_line += f" {entity_part}"
    if event.actor_name:
        first_line += f" - {event.actor_name}"

    body_lines = [first_line]
    html_lines = [f"<p>{html.escape(first_line)}</p>"]

    if event.comment_text:
        body_lines.append(f"Comment: {event.comment_text}")
        html_lines.append(f"<p><strong>Comment:</strong> {html.escape(event.comment_text)}</p>")

    if event.link:
        body_lines.append(event.link)
        html_lines.append(f'<p><a href="{html.escape(event.link)}">{html.escape(event.link)}</a></p>')

    return MatrixMessage(body="\n".join(body_lines), formatted_body="".join(html_lines))


def format_created_user_story_message(story: TaigaUserStory, web_base_url: str) -> MatrixMessage:
    link = story.permalink or build_taiga_link(
        base_url=web_base_url,
        project_slug=story.project_slug,
        entity_type="userstory",
        ref=story.ref,
    ) or ""
    body = f"Created Taiga user story #{story.ref}: {story.subject}\n{link}".rstrip()
    formatted_body = (
        f"<p>Created Taiga user story <strong>#{story.ref}: {html.escape(story.subject)}</strong>"
        + (
            f'<br><a href="{html.escape(link)}">{html.escape(link)}</a>'
            if link
            else ""
        )
        + "</p>"
    )
    return MatrixMessage(body=body, formatted_body=formatted_body)


def truncate_text(value: str, limit: int) -> str:
    cleaned = WHITESPACE_RE.sub(" ", TAG_RE.sub(" ", value)).strip()
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 1].rstrip() + "..."


def _pick_first(mapping: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = mapping.get(key)
        if value not in (None, "", [], {}):
            return value
    return None


def _extract_mapping(payload: dict[str, Any], *keys: str) -> dict[str, Any]:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, dict):
            return value
    return {}


def _extract_comment_text(payload: dict[str, Any], change: dict[str, Any], data: dict[str, Any]) -> str | None:
    for candidate in (
        change.get("comment"),
        payload.get("comment"),
        data.get("comment"),
        change.get("comment_html"),
    ):
        if isinstance(candidate, str) and candidate.strip():
            return _normalize_space(candidate)

    diff = change.get("diff")
    if isinstance(diff, dict):
        for value in diff.values():
            if isinstance(value, dict):
                from_value = value.get("from")
                to_value = value.get("to")
                if isinstance(from_value, str) and isinstance(to_value, str):
                    if _normalize_space(from_value) != _normalize_space(to_value):
                        return f"Changed from '{truncate_text(from_value, 80)}' to '{truncate_text(to_value, 80)}'"
    return None


def _extract_actor_name(actor: dict[str, Any], data: dict[str, Any]) -> str | None:
    name = _display_name(actor)
    if name:
        return name
    owner = data.get("owner")
    if isinstance(owner, dict):
        return _display_name(owner)
    assigned_to = data.get("assigned_to")
    if isinstance(assigned_to, dict):
        return _display_name(assigned_to)
    return None


def _extract_project_slug(data: dict[str, Any]) -> str | None:
    permalink = _string_or_none(_pick_first(data, "permalink"))
    if permalink and "/project/" in permalink:
        project_path = permalink.split("/project/", 1)[1]
        parts = [part for part in project_path.split("/") if part]
        if parts:
            return parts[0]
    project = data.get("project")
    if isinstance(project, dict):
        project_permalink = _string_or_none(_pick_first(project, "permalink"))
        if project_permalink and "/project/" in project_permalink:
            project_path = project_permalink.split("/project/", 1)[1]
            parts = [part for part in project_path.split("/") if part]
            if parts:
                return parts[0]
    return None


def _display_name(value: dict[str, Any]) -> str | None:
    return _string_or_none(
        _pick_first(value, "full_name_display", "full_name", "name", "title", "username", "email")
    )


def _string_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return _normalize_space(text) if text else None


def _normalize_space(value: str) -> str:
    return WHITESPACE_RE.sub(" ", TAG_RE.sub(" ", value)).strip()


def _coerce_int(value: Any, default: int | None) -> int | None:
    try:
        if value is None:
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


def _entity_label(entity_type: str) -> str:
    return {
        "userstory": "user story",
        "task": "task",
        "issue": "issue",
        "milestone": "milestone",
        "wikipage": "wiki page",
        "test": "test event",
    }.get(entity_type, entity_type.replace("_", " "))


def _human_action(action: str) -> str:
    return {
        "create": "created",
        "change": "updated",
        "delete": "deleted",
        "test": "test",
    }.get(action, action)
