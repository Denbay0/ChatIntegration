from __future__ import annotations

from typing import Any


RU_TEXTS = {
    "widget_page_title": "{project_name} · Доска Taiga",
    "widget_html_lang": "ru",
    "widget_room_name": "Доска Taiga",
    "widget_room_title": "Виджет проекта Taiga",
    "hero_eyebrow": "Taiga · виджет комнаты Matrix",
    "project_description_fallback": "Виджет проекта Taiga",
    "subtitle_live": "Русскоязычный виджет проекта, работающий через bridge Matrix ↔ Taiga.",
    "subtitle_error": "Виджет открыт, но свежие данные из Taiga сейчас недоступны.",
    "embedded_frame_title": "Доска Taiga",
    "hero_project_slug": "Проект",
    "hero_project_id": "ID проекта",
    "hero_room": "Комната",
    "hero_bridge": "Bridge",
    "hero_bridge_online": "онлайн",
    "hero_bridge_degraded": "с проблемой",
    "open_board": "Открыть доску",
    "open_project": "Открыть проект",
    "refresh_snapshot": "Обновить данные",
    "error_snapshot_title": "Не удалось обновить данные проекта.",
    "metric_mode": "Режим",
    "metric_mode_hint": "Как этот виджет показывает проект в комнате",
    "metric_stories": "Задачи",
    "metric_stories_hint": "Последние user stories, загруженные из Taiga",
    "metric_active": "В работе",
    "metric_active_hint": "Ещё не закрыты",
    "metric_done": "Готово",
    "metric_done_hint": "Закрытые или завершённые",
    "mode_direct": "Прямое встраивание",
    "mode_fallback": "Self-hosted виджет",
    "embed_heading": "Статус встраивания",
    "embed_description": "Здесь видно, можно ли встроить cloud-доску Taiga напрямую внутрь Element.",
    "board_direct_heading": "Встроенная доска Taiga",
    "board_direct_description": "Cloud-страница доски разрешает iframe и открывается прямо в панели виджета.",
    "board_fallback_heading": "Сводка по доске",
    "help_heading": "Как пользоваться",
    "help_step_1": "Нажмите «Открыть доску», чтобы открыть полную Taiga-доску в новой вкладке.",
    "help_step_2": "Используйте форму ниже, чтобы быстро создать задачу, не уходя из комнаты.",
    "help_step_3": "Последние задачи и статусы видны прямо в виджете.",
    "help_step_4": "Новые изменения придут и в Taiga, и обратно в чат через webhook.",
    "chat_heading": "Как открыть и закрыть виджет",
    "chat_open": "Если виджет не виден, откройте информацию о комнате и найдите «Доска Taiga» в разделе виджетов/приложений.",
    "chat_close": "Чтобы вернуться к сообщениям, просто переключитесь обратно на чат или сверните панель виджета. Точное название кнопки зависит от версии Element.",
    "chat_board": "Если нужна полная доска, откройте её кнопкой «Открыть доску» в новой вкладке.",
    "chat_lang": "Язык самого клиента Element настраивается пользователем в All Settings → Account → Language and Region.",
    "create_heading": "Быстрое создание задачи",
    "create_description": "Создаёт новую user story в Taiga и оставляет уведомление в комнате через обычный bridge.",
    "field_title": "Название задачи",
    "field_title_placeholder": "Что нужно сделать?",
    "field_description": "Описание",
    "field_description_placeholder": "Добавьте контекст, критерии готовности или короткий комментарий",
    "create_helper": "Taiga webhook остаётся активным, поэтому уведомления о создании и изменениях продолжают приходить в чат.",
    "create_button": "Создать задачу",
    "create_button_loading": "Создание...",
    "create_success": "Задача <a href=\"{permalink}\" target=\"_blank\" rel=\"noopener noreferrer\">#{ref} {subject}</a> создана. Обновляем виджет...",
    "create_error_default": "Не удалось создать задачу.",
    "create_error_unexpected": "Что-то пошло не так внутри виджета.",
    "recent_heading": "Последние задачи",
    "recent_description": "Свежие user stories и недавние изменения в проекте.",
    "stories_empty_title": "Пока нет задач.",
    "stories_empty_body": "Создайте первую задачу через форму ниже или командой !task в комнате.",
    "activity_empty_title": "Пока нет свежей активности.",
    "activity_empty_body": "Как только в проекте появится новая задача, она будет показана здесь.",
    "status_column_empty": "В этой колонке пока нет карточек.",
    "story_owner_missing": "Автор не указан",
    "story_status_unknown": "Неизвестно",
    "story_updated_recently": "Обновлено недавно",
    "unknown_status_name": "Неизвестно",
    "widget_error_project_not_found": "Проект для этого виджета не найден.",
    "widget_error_invalid_json": "Неверный JSON в запросе виджета.",
    "widget_error_payload_object": "Тело запроса должно быть JSON-объектом.",
    "widget_error_empty_title": "Название задачи не может быть пустым.",
    "widget_error_unknown_slug": "Неизвестный адрес виджета.",
    "widget_error_runtime": "Bridge ещё не инициализирован.",
    "widget_error_snapshot_generic": "Не удалось получить свежие данные из Taiga.",
    "widget_error_create_generic": "Taiga сейчас не приняла создание задачи.",
    "taiga_error_project_id_missing": "Не задан идентификатор проекта Taiga.",
    "taiga_error_auth": "Не удалось авторизоваться в Taiga.",
    "taiga_error_credentials_missing": "В bridge не настроены учётные данные Taiga.",
    "taiga_error_request_failed": "Не удалось выполнить запрос к Taiga.",
    "taiga_error_http": "Taiga API вернула HTTP {status_code}.",
    "taiga_error_unexpected": "Taiga вернула неожиданный ответ.",
    "embed_reason_xfo_deny": "Taiga Cloud запрещает iframe-встраивание этой страницы через X-Frame-Options: DENY.",
    "embed_reason_xfo_sameorigin": "Taiga Cloud разрешает встраивание только для своего origin через X-Frame-Options: SAMEORIGIN.",
    "embed_reason_csp_none": "Taiga Cloud запрещает встраивание через CSP frame-ancestors 'none'.",
    "embed_reason_csp_restricted": "Taiga Cloud ограничивает встраивание CSP frame-ancestors и не разрешает этот Matrix-клиент.",
    "embed_reason_unknown": "Не удалось подтвердить безопасное встраивание cloud-доски, поэтому используется self-hosted виджет.",
    "embed_reason_allowed": "Cloud-доска не показала iframe-блокировку в этой проверке.",
}


STATUS_TRANSLATIONS_BY_SLUG = {
    "new": "Новые",
    "ready": "Готово к работе",
    "in-progress": "В работе",
    "ready-for-test": "Готово к тестированию",
    "done": "Готово",
    "archived": "Архив",
    "unknown": "Неизвестно",
}

STATUS_TRANSLATIONS_BY_NAME = {
    "New": "Новые",
    "Ready": "Готово к работе",
    "In progress": "В работе",
    "Ready for test": "Готово к тестированию",
    "Done": "Готово",
    "Archived": "Архив",
    "Unknown": "Неизвестно",
}


def tr(key: str, **kwargs: object) -> str:
    template = RU_TEXTS[key]
    return template.format(**kwargs)


def localize_status_name(*, slug: str | None, name: str | None) -> str:
    if slug and slug in STATUS_TRANSLATIONS_BY_SLUG:
        return STATUS_TRANSLATIONS_BY_SLUG[slug]
    if name and name in STATUS_TRANSLATIONS_BY_NAME:
        return STATUS_TRANSLATIONS_BY_NAME[name]
    return name or tr("unknown_status_name")


def localize_embed_reason(support: Any) -> str:
    x_frame_options = getattr(support, "x_frame_options", None)
    if x_frame_options:
        normalized = str(x_frame_options).upper()
        if "DENY" in normalized:
            return tr("embed_reason_xfo_deny")
        if "SAMEORIGIN" in normalized:
            return tr("embed_reason_xfo_sameorigin")

    frame_ancestors = getattr(support, "frame_ancestors", None)
    if frame_ancestors:
        ancestors = str(frame_ancestors).split()
        if "'none'" in ancestors:
            return tr("embed_reason_csp_none")
        return tr("embed_reason_csp_restricted")

    if getattr(support, "is_allowed", False):
        return tr("embed_reason_allowed")

    return tr("embed_reason_unknown")


def localize_taiga_error(message: str, *, status_code: int | None = None) -> str:
    if "Taiga project id is not configured" in message:
        return tr("taiga_error_project_id_missing")
    if "Taiga authentication failed" in message:
        return tr("taiga_error_auth")
    if "Taiga credentials are missing" in message:
        return tr("taiga_error_credentials_missing")
    if "Request to Taiga failed" in message:
        return tr("taiga_error_request_failed")
    if "Taiga API returned HTTP" in message:
        return tr("taiga_error_http", status_code=status_code or _extract_status_code(message) or "?")
    if "Unexpected" in message:
        return tr("taiga_error_unexpected")
    return message


def _extract_status_code(message: str) -> int | None:
    parts = message.split()
    for part in parts:
        if part.isdigit():
            return int(part)
    return None
