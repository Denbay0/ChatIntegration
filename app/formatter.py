from __future__ import annotations

import html
import re
from dataclasses import dataclass
from typing import Any

from app.models import CardLookupCommand, KaitenCard, NormalizedWebhookEvent, TaskCommand

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


def parse_card_command(message: str) -> CardLookupCommand:
    payload = message.removeprefix("!card").strip()
    if not payload:
        raise ValueError("Usage: !card 123")

    try:
        card_id = int(payload)
    except ValueError as exc:
        raise ValueError("Card id must be an integer.") from exc

    return CardLookupCommand(card_id=card_id)


def build_help_message() -> MatrixMessage:
    body = (
        "Available commands:\n"
        "!help\n"
        "!task Title | description\n"
        "!card 123"
    )
    formatted_body = (
        "<p><strong>Available commands:</strong><br>"
        "<code>!help</code><br>"
        "<code>!task Title | description</code><br>"
        "<code>!card 123</code></p>"
    )
    return MatrixMessage(body=body, formatted_body=formatted_body)


def build_card_link(web_base_url: str, card_id: int | None) -> str | None:
    if card_id is None:
        return None
    return f"{web_base_url.rstrip('/')}/cards/{card_id}"


def normalize_webhook_event(payload: dict[str, Any], web_base_url: str) -> NormalizedWebhookEvent:
    card = _extract_mapping(payload, "card", "data", "entity")
    if "card" not in card and isinstance(payload.get("data"), dict):
        nested_card = _extract_mapping(payload["data"], "card", "entity")
        if nested_card:
            card = nested_card

    comment_text = _extract_comment_text(payload)
    actor_name = _extract_actor_name(payload, card)
    card_id = _coerce_int(_pick_first(card, "id"), default=None)
    link = _pick_first(payload, "link", "card_url", "url") or _pick_first(card, "url", "link")
    if not link:
        link = build_card_link(web_base_url, card_id)

    event_name = (
        str(_pick_first(payload, "event", "event_type", "type", "action") or "kaiten.event")
        .strip()
        .replace(" ", ".")
    )
    title = _string_or_none(_pick_first(card, "title", "name"))

    return NormalizedWebhookEvent(
        event_name=event_name,
        card_id=card_id,
        title=title,
        actor_name=actor_name,
        comment_text=comment_text,
        link=link,
        raw=payload,
    )


def format_webhook_message(event: NormalizedWebhookEvent) -> MatrixMessage:
    details: list[str] = [f"[Kaiten] {event.event_name}:"]

    card_part = None
    if event.card_id is not None and event.title:
        card_part = f"#{event.card_id} {event.title}"
    elif event.card_id is not None:
        card_part = f"#{event.card_id}"
    elif event.title:
        card_part = event.title

    if card_part:
        details.append(card_part)
    if event.actor_name:
        details.append(f"- {event.actor_name}")

    first_line = " ".join(details).strip()
    body_lines = [first_line]
    html_lines = [f"<p>{html.escape(first_line)}</p>"]

    if event.comment_text:
        body_lines.append(f"Comment: {event.comment_text}")
        html_lines.append(f"<p><strong>Comment:</strong> {html.escape(event.comment_text)}</p>")

    if event.link:
        body_lines.append(event.link)
        html_lines.append(f'<p><a href="{html.escape(event.link)}">{html.escape(event.link)}</a></p>')

    return MatrixMessage(body="\n".join(body_lines), formatted_body="".join(html_lines))


def format_created_card_message(card: KaitenCard, link: str) -> MatrixMessage:
    body = f"Created card #{card.id}: {card.title}\n{link}"
    formatted_body = (
        f"<p>Created card <strong>#{card.id}: {html.escape(card.title)}</strong><br>"
        f'<a href="{html.escape(link)}">{html.escape(link)}</a></p>'
    )
    return MatrixMessage(body=body, formatted_body=formatted_body)


def format_card_lookup_message(card: KaitenCard, link: str) -> MatrixMessage:
    body_lines = [f"#{card.id}: {card.title}", link]
    if card.description:
        body_lines.append(f"Description: {truncate_text(card.description, 300)}")

    description_html = ""
    if card.description:
        description_html = (
            f"<br><strong>Description:</strong> {html.escape(truncate_text(card.description, 300))}"
        )

    formatted_body = (
        f"<p><strong>#{card.id}: {html.escape(card.title)}</strong><br>"
        f'<a href="{html.escape(link)}">{html.escape(link)}</a>{description_html}</p>'
    )
    return MatrixMessage(body="\n".join(body_lines), formatted_body=formatted_body)


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


def _extract_comment_text(payload: dict[str, Any]) -> str | None:
    comment = payload.get("comment")
    if isinstance(comment, dict):
        return _string_or_none(_pick_first(comment, "text", "comment", "body"))
    if isinstance(comment, str):
        return _normalize_space(comment)

    for key in ("comment_text", "text", "body"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return _normalize_space(value)
    return None


def _extract_actor_name(payload: dict[str, Any], card: dict[str, Any]) -> str | None:
    candidate_keys = ("actor", "author", "user", "member", "creator", "updated_by")
    for key in candidate_keys:
        candidate = payload.get(key)
        if isinstance(candidate, dict):
            name = _display_name(candidate)
            if name:
                return name

    comment = payload.get("comment")
    if isinstance(comment, dict):
        author = comment.get("author")
        if isinstance(author, dict):
            name = _display_name(author)
            if name:
                return name

    owner = card.get("owner")
    if isinstance(owner, dict):
        return _display_name(owner)

    return None


def _display_name(value: dict[str, Any]) -> str | None:
    return _string_or_none(
        _pick_first(value, "full_name", "name", "title", "username", "email")
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
