from __future__ import annotations

import html
import re
from dataclasses import dataclass
from typing import Any

from app.models import NormalizedWebhookEvent, TaigaUserStory, TaskCommand
from app.widget_i18n import localize_status_name

WHITESPACE_RE = re.compile(r"\s+")
TAG_RE = re.compile(r"<[^>]+>")
HELP_COMMAND_ALIASES = ("!help", "!помощь")
TASK_COMMAND_ALIASES = ("!task", "!задача")
TASKS_COMMAND_ALIASES = ("!tasks", "!задачи")
OPEN_COMMAND_ALIASES = ("!open", "!открыть")
MY_COMMAND_ALIASES = ("!my", "!мои")
COMMENT_COMMAND_ALIASES = ("!comment", "!коммент", "!комментарий")


@dataclass(slots=True)
class MatrixMessage:
    body: str
    formatted_body: str | None = None


@dataclass(slots=True)
class CommentCommand:
    ref: int
    text: str


def is_help_command(message: str) -> bool:
    return _extract_command(message) in HELP_COMMAND_ALIASES


def is_task_command(message: str) -> bool:
    return _extract_command(message) in TASK_COMMAND_ALIASES


def is_tasks_command(message: str) -> bool:
    return _extract_command(message) in TASKS_COMMAND_ALIASES


def is_open_command(message: str) -> bool:
    return _extract_command(message) in OPEN_COMMAND_ALIASES


def is_my_command(message: str) -> bool:
    return _extract_command(message) in MY_COMMAND_ALIASES


def is_comment_command(message: str) -> bool:
    return _extract_command(message) in COMMENT_COMMAND_ALIASES


def parse_task_command(message: str) -> TaskCommand:
    command = _extract_command(message)
    payload = message[len(command) :].strip() if command in TASK_COMMAND_ALIASES else ""
    if not payload:
        raise ValueError("Используйте: !task Название | описание")

    title_part, separator, description_part = payload.partition("|")
    title = title_part.strip()
    description = description_part.strip() if separator else None

    if not title:
        raise ValueError("Название задачи не может быть пустым.")

    return TaskCommand(title=title, description=description or None)


def parse_comment_command(message: str) -> CommentCommand:
    command = _extract_command(message)
    payload = message[len(command) :].strip() if command in COMMENT_COMMAND_ALIASES else ""
    if not payload:
        raise ValueError("Используйте: !comment 123 | текст комментария")

    ref_part, separator, text_part = payload.partition("|")
    ref_text = ref_part.strip().lstrip("#")
    comment_text = text_part.strip() if separator else ""

    if not ref_text.isdigit():
        raise ValueError("Номер задачи должен быть числом. Пример: !comment 123 | текст")
    if not comment_text:
        raise ValueError("Текст комментария не может быть пустым.")

    return CommentCommand(ref=int(ref_text), text=comment_text)


def build_help_message() -> MatrixMessage:
    body = (
        "Доступные команды:\n"
        "!help или !помощь — подсказка по командам\n"
        "!task Заголовок | описание — создать задачу\n"
        "!задача Заголовок | описание — русская команда\n"
        "!tasks или !задачи — последние задачи проекта\n"
        "!open или !открыть — ссылка на проект и доску\n"
        "!my или !мои — задачи, назначенные мне\n"
        "!comment 123 | текст — добавить комментарий к задаче"
    )
    formatted_body = (
        "<p><strong>Доступные команды:</strong><br>"
        "<code>!help</code> или <code>!помощь</code> — подсказка по командам<br>"
        "<code>!task Заголовок | описание</code> — создать задачу<br>"
        "<code>!задача Заголовок | описание</code> — русская команда<br>"
        "<code>!tasks</code> или <code>!задачи</code> — последние задачи проекта<br>"
        "<code>!open</code> или <code>!открыть</code> — ссылка на проект и доску<br>"
        "<code>!my</code> или <code>!мои</code> — задачи, назначенные мне<br>"
        "<code>!comment 123 | текст</code> — добавить комментарий к задаче</p>"
    )
    return MatrixMessage(body=body, formatted_body=formatted_body)


def build_tasks_message(
    stories: list[TaigaUserStory],
    *,
    board_url: str,
    project_name: str | None = None,
    title: str = "Последние задачи",
) -> MatrixMessage:
    heading = title if not project_name else f"{title} проекта «{project_name}»"
    if not stories:
        body = f"{heading}:\nПока нет задач.\n\nОткрыть доску: {board_url}"
        formatted_body = (
            f"<p><strong>{html.escape(heading)}:</strong><br>"
            "Пока нет задач.</p>"
            f'<p><a href="{html.escape(board_url)}">Открыть доску</a></p>'
        )
        return MatrixMessage(body=body, formatted_body=formatted_body)

    body_lines = [f"{heading}:"]
    html_items: list[str] = []
    for story in stories:
        status_name = localize_status_name(slug=None, name=story.status_name)
        link = story.permalink or "#"
        body_lines.append(f"#{story.ref} {story.subject} — {status_name}")
        html_items.append(
            "<li>"
            f'<a href="{html.escape(link)}">#{story.ref} {html.escape(story.subject)}</a>'
            f" — {html.escape(status_name)}"
            "</li>"
        )
    body_lines.append("")
    body_lines.append(f"Открыть доску: {board_url}")
    formatted_body = (
        f"<p><strong>{html.escape(heading)}:</strong></p>"
        f"<ul>{''.join(html_items)}</ul>"
        f'<p><a href="{html.escape(board_url)}">Открыть доску</a></p>'
    )
    return MatrixMessage(body="\n".join(body_lines), formatted_body=formatted_body)


def build_open_project_message(
    *,
    project_name: str | None,
    project_url: str,
    board_url: str,
) -> MatrixMessage:
    heading = "Открыть проект Taiga" if not project_name else f"Открыть проект Taiga «{project_name}»"
    body = f"{heading}:\nДоска: {board_url}\nПроект: {project_url}"
    formatted_body = (
        f"<p><strong>{html.escape(heading)}:</strong><br>"
        f'Доска: <a href="{html.escape(board_url)}">{html.escape(board_url)}</a><br>'
        f'Проект: <a href="{html.escape(project_url)}">{html.escape(project_url)}</a></p>'
    )
    return MatrixMessage(body=body, formatted_body=formatted_body)


def build_comment_added_message(story: TaigaUserStory, web_base_url: str) -> MatrixMessage:
    link = story.permalink or build_taiga_link(
        base_url=web_base_url,
        project_slug=story.project_slug,
        entity_type="userstory",
        ref=story.ref,
    ) or ""
    body_lines = [
        f"Комментарий добавлен к задаче #{story.ref}: {story.subject}",
        "Обновление также вернётся в комнату через webhook.",
    ]
    html_lines = [
        f"<p><strong>Комментарий добавлен к задаче #{story.ref}: {html.escape(story.subject)}</strong></p>",
        "<p>Обновление также вернётся в комнату через webhook.</p>",
    ]
    if link:
        body_lines.append(f"Ссылка: {link}")
        html_lines.append(
            f'<p><strong>Ссылка:</strong> <a href="{html.escape(link)}">{html.escape(link)}</a></p>'
        )
    return MatrixMessage(body="\n".join(body_lines), formatted_body="".join(html_lines))


def build_project_room_header_message(
    *,
    project_name: str,
    widget_name: str,
    board_url: str,
    project_url: str,
) -> MatrixMessage:
    body = (
        f"Проектная комната «{project_name}»\n\n"
        "В этой комнате подключены:\n"
        f"- бот задач Taiga\n- виджет проекта «{widget_name}»\n- уведомления из Taiga\n\n"
        "Как пользоваться:\n"
        "- откройте виджет через панель widgets/apps в комнате\n"
        "- !task Заголовок | описание — создать задачу\n"
        "- !tasks — показать последние задачи\n"
        "- !open — открыть проект и доску\n"
        "- !my — показать мои задачи\n"
        "- !comment 123 | текст — добавить комментарий\n\n"
        "Ссылки:\n"
        f"- Доска: {board_url}\n"
        f"- Проект: {project_url}\n\n"
        "Бот создаёт задачи в Taiga, показывает список задач, даёт ссылки на проект и возвращает webhook-уведомления обратно в комнату."
    )
    formatted_body = (
        f"<p><strong>Проектная комната «{html.escape(project_name)}»</strong></p>"
        "<p>В этой комнате подключены:<br>"
        f"• бот задач Taiga<br>• виджет проекта «{html.escape(widget_name)}»<br>• уведомления из Taiga</p>"
        "<p><strong>Как пользоваться</strong><br>"
        "• откройте виджет через панель widgets/apps в комнате<br>"
        "<code>!task Заголовок | описание</code> — создать задачу<br>"
        "<code>!tasks</code> — показать последние задачи<br>"
        "<code>!open</code> — открыть проект и доску<br>"
        "<code>!my</code> — показать мои задачи<br>"
        "<code>!comment 123 | текст</code> — добавить комментарий</p>"
        "<p><strong>Ссылки</strong><br>"
        f'Доска: <a href="{html.escape(board_url)}">{html.escape(board_url)}</a><br>'
        f'Проект: <a href="{html.escape(project_url)}">{html.escape(project_url)}</a></p>'
        "<p>Бот создаёт задачи в Taiga, показывает список задач, даёт ссылки на проект и возвращает webhook-уведомления обратно в комнату.</p>"
    )
    return MatrixMessage(body=body, formatted_body=formatted_body)


def build_my_tasks_message(
    stories: list[TaigaUserStory],
    *,
    board_url: str,
    project_name: str | None = None,
    lookup_note: str | None = None,
) -> MatrixMessage:
    message = build_tasks_message(
        stories,
        board_url=board_url,
        project_name=project_name,
        title="Мои задачи",
    )
    if not lookup_note:
        return message

    body = f"{message.body}\n\n{lookup_note}"
    formatted_body = (message.formatted_body or "") + f"<p>{html.escape(lookup_note)}</p>"
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
    change_summary = _extract_change_summary(change, data, action=action)
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
        change_summary=change_summary,
        link=link,
        raw=payload,
    )


def format_webhook_message(event: NormalizedWebhookEvent) -> MatrixMessage:
    first_line = _build_event_headline(event)
    body_lines = [first_line]
    html_lines = [f"<p><strong>{html.escape(first_line)}</strong></p>"]

    if event.actor_name:
        body_lines.append(f"Автор: {event.actor_name}")
        html_lines.append(f"<p><strong>Автор:</strong> {html.escape(event.actor_name)}</p>")

    if event.change_summary:
        body_lines.append(f"Изменение: {event.change_summary}")
        html_lines.append(f"<p><strong>Изменение:</strong> {html.escape(event.change_summary)}</p>")

    if event.comment_text:
        body_lines.append(f"Комментарий: {event.comment_text}")
        html_lines.append(f"<p><strong>Комментарий:</strong> {html.escape(event.comment_text)}</p>")

    if event.link:
        body_lines.append(f"Ссылка: {event.link}")
        html_lines.append(
            f'<p><strong>Ссылка:</strong> <a href="{html.escape(event.link)}">{html.escape(event.link)}</a></p>'
        )

    return MatrixMessage(body="\n".join(body_lines), formatted_body="".join(html_lines))


def format_created_user_story_message(story: TaigaUserStory, web_base_url: str) -> MatrixMessage:
    link = story.permalink or build_taiga_link(
        base_url=web_base_url,
        project_slug=story.project_slug,
        entity_type="userstory",
        ref=story.ref,
    ) or ""
    owner = story.owner.display_name if story.owner else None
    body_lines = [f"[Taiga] Создана задача #{story.ref}: {story.subject}"]
    html_lines = [f"<p><strong>[Taiga] Создана задача #{story.ref}: {html.escape(story.subject)}</strong></p>"]

    if owner:
        body_lines.append(f"Автор: {owner}")
        html_lines.append(f"<p><strong>Автор:</strong> {html.escape(owner)}</p>")

    if link:
        body_lines.append(f"Ссылка: {link}")
        html_lines.append(
            f'<p><strong>Ссылка:</strong> <a href="{html.escape(link)}">{html.escape(link)}</a></p>'
        )

    return MatrixMessage(body="\n".join(body_lines), formatted_body="".join(html_lines))


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
    return None


def _extract_change_summary(change: dict[str, Any], data: dict[str, Any], *, action: str) -> str | None:
    if action != "change":
        return None

    diff = change.get("diff")
    if not isinstance(diff, dict) or not diff:
        return None

    if "status" in diff or "status_extra_info" in diff:
        status_name = _extract_status_display_name(data, diff)
        if status_name:
            return f"статус изменён на «{status_name}»"
        return "статус обновлён"

    if "is_closed" in diff:
        closed_value = _extract_to_value(diff.get("is_closed"))
        if closed_value is True:
            return "задача закрыта"
        if closed_value is False:
            return "задача снова открыта"
        return "состояние задачи изменено"

    if "subject" in diff:
        return "название обновлено"

    if "description" in diff:
        return "описание обновлено"

    if "assigned_to" in diff or "assigned_to_extra_info" in diff:
        assignee = _extract_assignee_name(data, diff)
        if assignee:
            return f"исполнитель изменён на «{assignee}»"
        return "исполнитель обновлён"

    field_labels = [_field_label(name) for name in diff]
    unique_labels: list[str] = []
    for label in field_labels:
        if label and label not in unique_labels:
            unique_labels.append(label)

    if unique_labels:
        if len(unique_labels) == 1:
            return f"обновлено поле «{unique_labels[0]}»"
        preview = ", ".join(f"«{label}»" for label in unique_labels[:3])
        suffix = " и другие" if len(unique_labels) > 3 else ""
        return f"изменены поля: {preview}{suffix}"

    for value in diff.values():
        if isinstance(value, dict):
            from_value = value.get("from")
            to_value = value.get("to")
            if isinstance(from_value, str) and isinstance(to_value, str):
                if _normalize_space(from_value) != _normalize_space(to_value):
                    return f"значение изменено с «{truncate_text(from_value, 60)}» на «{truncate_text(to_value, 60)}»"

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
        "userstory": "задача",
        "task": "задача",
        "issue": "проблема",
        "milestone": "эпик",
        "wikipage": "страницу wiki",
        "test": "тест",
    }.get(entity_type, entity_type.replace("_", " "))


def _human_action(action: str) -> str:
    return {
        "create": "Создана",
        "change": "Обновлена",
        "delete": "Удалена",
        "test": "Тест",
    }.get(action, action)


def _extract_command(message: str) -> str:
    return message.strip().split(maxsplit=1)[0].lower() if message.strip() else ""


def _build_event_headline(event: NormalizedWebhookEvent) -> str:
    if event.action == "test" or event.entity_type == "test":
        return "[Taiga] Тест webhook"

    label, gender = _entity_info(event.entity_type)
    action_word = _action_word(event.action, gender)
    headline = f"[Taiga] {action_word} {label}"

    if event.ref is not None and event.title:
        headline += f" #{event.ref}: {event.title}"
    elif event.ref is not None:
        headline += f" #{event.ref}"
    elif event.title:
        headline += f" «{event.title}»"

    return headline


def _entity_info(entity_type: str) -> tuple[str, str]:
    return {
        "userstory": ("задача", "f"),
        "task": ("задача", "f"),
        "issue": ("проблема", "f"),
        "milestone": ("эпик", "m"),
        "wikipage": ("страница wiki", "f"),
        "test": ("тест webhook", "m"),
    }.get(entity_type, (entity_type.replace("_", " "), "m"))


def _action_word(action: str, gender: str) -> str:
    variants = {
        "create": {"f": "Создана", "m": "Создан", "n": "Создано"},
        "change": {"f": "Обновлена", "m": "Обновлён", "n": "Обновлено"},
        "delete": {"f": "Удалена", "m": "Удалён", "n": "Удалено"},
        "test": {"f": "Тест", "m": "Тест", "n": "Тест"},
    }
    action_variants = variants.get(action)
    if not action_variants:
        return action
    return action_variants.get(gender, action_variants["m"])


def _extract_status_display_name(data: dict[str, Any], diff: dict[str, Any]) -> str | None:
    current_status = data.get("status_extra_info")
    if isinstance(current_status, dict):
        return localize_status_name(
            slug=_string_or_none(current_status.get("slug")),
            name=_string_or_none(current_status.get("name")),
        )

    diff_status = diff.get("status_extra_info")
    if isinstance(diff_status, dict):
        candidate = _extract_to_value(diff_status)
        if isinstance(candidate, dict):
            return localize_status_name(
                slug=_string_or_none(candidate.get("slug")),
                name=_string_or_none(candidate.get("name")),
            )

    status_name = _string_or_none(data.get("status_name"))
    if status_name:
        return localize_status_name(slug=None, name=status_name)
    return None


def _extract_assignee_name(data: dict[str, Any], diff: dict[str, Any]) -> str | None:
    current_assignee = data.get("assigned_to_extra_info") or data.get("assigned_to")
    if isinstance(current_assignee, dict):
        display_name = _display_name(current_assignee)
        if display_name:
            return display_name

    for key in ("assigned_to_extra_info", "assigned_to"):
        candidate = diff.get(key)
        if isinstance(candidate, dict):
            to_value = _extract_to_value(candidate)
            if isinstance(to_value, dict):
                display_name = _display_name(to_value)
                if display_name:
                    return display_name
            text = _string_or_none(to_value)
            if text:
                return text

    return None


def _extract_to_value(value: Any) -> Any:
    if isinstance(value, dict):
        return value.get("to")
    return None


def _field_label(name: str) -> str | None:
    return {
        "subject": "название",
        "description": "описание",
        "status": "статус",
        "status_extra_info": "статус",
        "assigned_to": "исполнитель",
        "assigned_to_extra_info": "исполнитель",
        "milestone": "спринт",
        "is_closed": "состояние задачи",
    }.get(name)
