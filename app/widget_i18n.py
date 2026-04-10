from __future__ import annotations

from typing import Any


RU_TEXTS = {
    "widget_page_title": "{project_name} · Панель Taiga",
    "widget_html_lang": "ru",
    "widget_room_name": "Панель Taiga",
    "widget_room_title": "Панель проекта Taiga",
    "hero_eyebrow": "Taiga · проектная панель Matrix",
    "project_description_fallback": "Короткая панель проекта Taiga внутри комнаты Matrix.",
    "subtitle_live": "Задачи, статусы и быстрое создание доступны прямо в комнате.",
    "subtitle_error": "Панель открыта, но свежий снимок проекта из Taiga сейчас недоступен.",
    "embedded_frame_title": "Панель Taiga",
    "hero_project_slug": "Проект",
    "hero_project_id": "ID проекта",
    "hero_room": "Комната",
    "hero_bridge": "Bridge",
    "hero_bridge_online": "работает",
    "hero_bridge_degraded": "требует проверки",
    "integration_badge_ok": "Синхронизация активна",
    "integration_badge_problem": "Проверьте подключение к Taiga",
    "open_board": "Открыть доску",
    "open_project": "Открыть проект",
    "refresh_snapshot": "Обновить",
    "error_snapshot_title": "Не удалось обновить данные проекта.",
    "metric_mode": "Режим",
    "metric_mode_hint": "Служебная информация о встраивании",
    "metric_stories": "Задачи",
    "metric_stories_hint": "Последние user stories, загруженные из Taiga",
    "metric_active": "В работе",
    "metric_active_hint": "Ещё не закрыты",
    "metric_total": "Всего",
    "metric_total_hint": "Задачи в текущем срезе",
    "metric_new": "Новые",
    "metric_new_hint": "Новые и готовые к работе",
    "metric_in_progress": "В работе",
    "metric_in_progress_hint": "Активные и на тестировании",
    "metric_done": "Готово",
    "metric_done_hint": "Закрытые задачи",
    "mode_direct": "Прямое встраивание",
    "mode_fallback": "Self-hosted виджет",
    "focus_heading": "Фокус по задачам",
    "focus_description": "Короткий рабочий срез, который удобно держать открытым в боковой панели комнаты.",
    "tasks_heading": "Задачи проекта",
    "tasks_description": "Один главный рабочий блок без дублирования: новые карточки, активная работа и последние обновления.",
    "task_tab_new": "Новые",
    "task_tab_new_description": "Новые карточки и задачи, готовые к старту.",
    "task_tab_active": "В работе",
    "task_tab_active_description": "Текущая работа команды и карточки на тестировании.",
    "task_tab_recent": "Последние",
    "task_tab_recent_description": "Свежие user stories и недавние изменения в проекте.",
    "lane_new_heading": "Новые",
    "lane_new_description": "Новые карточки и задачи, готовые к старту.",
    "lane_new_empty_title": "Новых задач пока нет.",
    "lane_new_empty_body": "Когда появятся новые карточки, они будут видны здесь.",
    "lane_active_heading": "В работе",
    "lane_active_description": "Текущая работа команды и карточки на тестировании.",
    "lane_active_empty_title": "Нет задач в работе.",
    "lane_active_empty_body": "Как только появится активная работа, она окажется здесь.",
    "statuses_heading": "По статусам",
    "statuses_description": "Компактный обзор по всем колонкам проекта с прокруткой внутри каждой секции.",
    "help_heading": "Как пользоваться",
    "help_description": "Короткая инструкция для ежедневной работы из Matrix.",
    "help_step_1": "Нажмите «Открыть доску», чтобы открыть полную Taiga-доску в новой вкладке.",
    "help_step_2": "Используйте форму ниже, чтобы быстро создать задачу, не уходя из комнаты.",
    "help_step_3": "Последние задачи, новые карточки и работа в процессе видны прямо в панели.",
    "help_step_4": "Изменения из Taiga автоматически приходят обратно в комнату через webhook.",
    "chat_heading": "Команды в чате",
    "chat_open": "Если панель скрыта, откройте её из списка widgets/apps в информации о комнате.",
    "chat_close": "Чтобы вернуться к сообщениям, просто сверните панель или переключитесь обратно на чат.",
    "chat_board": "Если нужна полная доска, откройте её кнопкой «Открыть доску».",
    "chat_lang": "Язык клиента Element меняется в настройках пользователя.",
    "chat_sync_hint": "Любая новая задача и изменения статусов продолжают синхронизироваться между Taiga и Matrix.",
    "create_heading": "Создать задачу",
    "create_description": "Быстрое создание user story без перехода в полную Taiga.",
    "field_title": "Название задачи",
    "field_title_placeholder": "Что нужно сделать?",
    "field_description": "Описание",
    "field_description_placeholder": "Добавьте контекст, критерии готовности или короткий комментарий",
    "create_helper": "После создания карточка появится в Taiga, а уведомление вернётся в комнату автоматически.",
    "create_button": "Создать задачу",
    "create_button_loading": "Создание...",
    "create_success": "Задача <a href=\"{permalink}\" target=\"_blank\" rel=\"noopener noreferrer\">#{ref} {subject}</a> создана. Обновляем виджет...",
    "create_success_prefix": "Задача ",
    "create_success_suffix": " создана. Обновляем панель...",
    "create_error_default": "Не удалось создать задачу.",
    "create_error_unexpected": "Что-то пошло не так внутри панели.",
    "recent_heading": "Последние задачи",
    "recent_description": "Свежие user stories и недавние изменения в проекте.",
    "stories_empty_title": "Пока нет задач.",
    "stories_empty_body": "Создайте первую задачу через форму ниже или командой !task в комнате.",
    "activity_empty_title": "Пока нет свежей активности.",
    "activity_empty_body": "Как только в проекте появится новая задача, она будет показана здесь.",
    "status_column_empty": "В этой колонке пока нет карточек.",
    "story_open_link": "Открыть в Taiga",
    "story_owner_missing": "Автор не указан",
    "story_status_unknown": "Неизвестно",
    "story_updated_recently": "Обновлено недавно",
    "unknown_status_name": "Неизвестно",
    "technical_heading": "Техническая информация",
    "technical_summary_pill": "скрыто по умолчанию",
    "technical_description": "Служебные детали интеграции и причины fallback-режима для администратора.",
    "technical_mode": "Режим панели",
    "technical_mode_direct": "Прямое iframe-встраивание доступно",
    "technical_mode_fallback": "Используется self-hosted панель",
    "technical_embed_reason": "Причина fallback",
    "technical_project_slug": "Slug проекта",
    "technical_project_id": "ID проекта",
    "technical_room": "Комната Matrix",
    "technical_bridge_state": "Состояние bridge",
    "technical_bridge_ok": "Bridge отвечает",
    "technical_bridge_problem": "Bridge требует проверки",
    "technical_frame_options": "X-Frame-Options",
    "technical_frame_ancestors": "CSP frame-ancestors",
    "technical_board_link": "Полная доска",
    "technical_project_link": "Страница проекта",
    "technical_value_missing": "не указано",
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
    "embed_reason_unknown": "Не удалось подтвердить безопасное встраивание cloud-доски, поэтому используется self-hosted панель.",
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
