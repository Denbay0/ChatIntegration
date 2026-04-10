from __future__ import annotations

from typing import Any

from app.widget_i18n import tr

WIDGET_EVENT_TYPE = "im.vector.modular.widgets"
WIDGET_LAYOUT_EVENT_TYPE = "io.element.widgets.layout"
DEFAULT_WIDGET_NAME = "Доска Taiga"
DEFAULT_WIDGET_TITLE = "Панель проекта Taiga"


def build_widget_state_content(
    *,
    widget_id: str,
    widget_name: str,
    widget_url: str,
    project_slug: str,
    creator_user_id: str,
    widget_title: str = DEFAULT_WIDGET_TITLE,
) -> dict[str, Any]:
    return {
        "creatorUserId": creator_user_id,
        "id": widget_id,
        "name": widget_name,
        "type": "m.custom",
        "url": widget_url,
        "waitForIframeLoad": True,
        "data": {
            "title": widget_title,
            "projectSlug": project_slug,
        },
    }


def build_widget_layout_content(widget_id: str) -> dict[str, Any]:
    return {
        "widgets": {
            widget_id: {
                "container": "top",
                "index": 0,
                "width": 66,
                "height": 72,
            }
        }
    }


def build_project_room_name(project_name: str) -> str:
    return f"Проект · {project_name}"


def build_project_room_topic(project_name: str, board_url: str) -> str:
    return (
        f"Проектная комната «{project_name}». "
        f"Виджет Taiga доступен в панели комнаты, полная доска: {board_url}"
    )


def default_widget_name() -> str:
    return tr("widget_room_name")
