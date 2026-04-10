from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.config import Settings, load_bridge_config, save_bridge_config, setup_logging
from app.formatter import build_project_room_header_message
from app.matrix_admin import MatrixAdminClient, MatrixAdminError
from app.models import ProjectMapping
from app.project_rooms import (
    DEFAULT_WIDGET_NAME,
    DEFAULT_WIDGET_TITLE,
    WIDGET_EVENT_TYPE,
    WIDGET_LAYOUT_EVENT_TYPE,
    build_project_room_name,
    build_project_room_topic,
    build_widget_layout_content,
    build_widget_state_content,
)
from app.taiga import TaigaClient

LOGGER = logging.getLogger("bind-room")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Привязать Matrix-комнату к проекту Taiga и настроить project room template."
    )
    parser.add_argument("--slug", required=True, help="Внутренний slug связки bridge, например backend")
    parser.add_argument("--project-id", type=int, help="Числовой id проекта Taiga")
    parser.add_argument("--project-slug", help="Slug проекта Taiga")
    parser.add_argument("--project-name", help="Человекочитаемое имя проекта")
    parser.add_argument("--project-url", help="Полная ссылка на страницу проекта Taiga")
    parser.add_argument("--widget-name", default=DEFAULT_WIDGET_NAME, help="Название room widget")
    parser.add_argument("--widget-title", default=DEFAULT_WIDGET_TITLE, help="Заголовок widget metadata")
    parser.add_argument("--room-id", help="Уже существующая Matrix-комната")
    parser.add_argument("--create-room", action="store_true", help="Создать новую Matrix-комнату автоматически")
    parser.add_argument("--room-name", help="Название новой комнаты")
    parser.add_argument("--invite-user", action="append", default=[], help="Кого пригласить в новую комнату")
    parser.add_argument("--skip-header", action="store_true", help="Не публиковать русскую шапку в комнату")
    parser.add_argument("--skip-webhook-test", action="store_true", help="Не запускать Taiga webhook test после bind")
    parser.add_argument("--force", action="store_true", help="Разрешить обновить уже существующую привязку")
    args = parser.parse_args()
    if bool(args.room_id) == bool(args.create_room):
        parser.error("Укажите либо --room-id, либо --create-room.")
    return args


async def main() -> None:
    args = parse_args()
    settings = Settings()
    setup_logging(settings.log_level)

    bridge_config = load_bridge_config(settings.config_path)
    existing_project = bridge_config.get_project(args.slug)
    target_room_id = args.room_id or (existing_project.room_id if existing_project else None)

    if target_room_id:
        existing_room_binding = bridge_config.get_project_by_room(target_room_id)
        if existing_room_binding and existing_room_binding[0] != args.slug and not args.force:
            raise SystemExit(
                f"Комната {target_room_id} уже привязана к slug '{existing_room_binding[0]}'. "
                "Используйте --force, если хотите перепривязать её."
            )

    if existing_project and existing_project.room_id != target_room_id and not args.force:
        raise SystemExit(
            f"Slug '{args.slug}' уже привязан к комнате {existing_project.room_id}. "
            "Используйте --force, если хотите обновить привязку."
        )

    taiga_client = TaigaClient(
        api_url=settings.taiga_api_url,
        base_url=settings.taiga_base_url,
        username=settings.taiga_username,
        password=settings.taiga_password.get_secret_value() if settings.taiga_password else None,
        token=settings.taiga_token.get_secret_value() if settings.taiga_token else None,
        accept_language=settings.taiga_accept_language,
        default_project_id=settings.taiga_project_id,
        default_project_slug=settings.taiga_project_slug,
    )

    admin_user_id = settings.matrix_state_user_id or settings.matrix_user_id
    admin_password_secret = settings.matrix_state_password or settings.matrix_password
    admin_client = MatrixAdminClient(
        homeserver=settings.matrix_homeserver,
        user_id=admin_user_id,
        password=admin_password_secret.get_secret_value(),
    )

    try:
        await admin_client.login()
        project_data = await _resolve_project_data(
            args=args,
            settings=settings,
            taiga_client=taiga_client,
            existing_project=existing_project,
        )

        room_id = await _ensure_room(
            args=args,
            settings=settings,
            admin_client=admin_client,
            admin_user_id=admin_user_id,
            project_name=project_data["project_name"],
            board_url=project_data["board_url"],
        )

        widget_id = (existing_project or ProjectMapping(room_id=room_id)).resolved_widget_id(args.slug)
        widget_url = (existing_project or ProjectMapping(room_id=room_id)).resolved_widget_url(
            settings.bridge_public_url,
            args.slug,
        )
        webhook_url = (existing_project or ProjectMapping(room_id=room_id)).resolved_webhook_url(
            settings.bridge_public_url,
            args.slug,
        )
        webhook_secret = (existing_project.webhook_secret if existing_project else None) or settings.bridge_secret.get_secret_value()

        await _invite_user_if_needed(admin_client, room_id, settings.matrix_user_id, skip_if_same=admin_user_id)
        for invitee in args.invite_user:
            await _invite_user_if_needed(admin_client, room_id, invitee, skip_if_same=admin_user_id)

        await admin_client.put_state(
            room_id,
            WIDGET_EVENT_TYPE,
            build_widget_state_content(
                widget_id=widget_id,
                widget_name=args.widget_name,
                widget_url=widget_url,
                project_slug=project_data["project_slug"],
                creator_user_id=admin_user_id,
                widget_title=args.widget_title,
            ),
            state_key=widget_id,
        )
        await admin_client.put_state(
            room_id,
            WIDGET_LAYOUT_EVENT_TYPE,
            build_widget_layout_content(widget_id),
        )

        header_event_id: str | None = existing_project.header_event_id if existing_project else None
        if not args.skip_header:
            header_message = build_project_room_header_message(
                project_name=project_data["project_name"],
                widget_name=args.widget_name,
                board_url=project_data["board_url"],
                project_url=project_data["project_url"],
            )
            header_event_id = await admin_client.send_notice(room_id, header_message)
            await admin_client.pin_event(room_id, header_event_id)

        await taiga_client.ensure_webhook(
            project_data["project_id"],
            name=f"Matrix Bridge · {args.slug}",
            url=webhook_url,
            key=webhook_secret,
        )

        if not args.skip_webhook_test:
            webhooks = await taiga_client.list_webhooks(project_data["project_id"])
            matching = next((item for item in webhooks if item.get("url") == webhook_url), None)
            if matching and matching.get("id"):
                await taiga_client.test_webhook(int(matching["id"]))

        updated_project = ProjectMapping(
            room_id=room_id,
            project_id=project_data["project_id"],
            project_slug=project_data["project_slug"],
            project_name=project_data["project_name"],
            project_url=project_data["project_url"],
            widget_id=widget_id,
            widget_name=args.widget_name,
            widget_url=widget_url,
            webhook_url=webhook_url,
            header_event_id=header_event_id,
            user_mappings=existing_project.user_mappings if existing_project else {},
            webhook_secret=webhook_secret,
        )
        bridge_config.set_project(args.slug, updated_project)
        save_bridge_config(settings.config_path, bridge_config)
        reload_result = await admin_client.reload_bridge_config(
            settings.bridge_public_url,
            settings.bridge_secret.get_secret_value(),
        )

        result = {
            "status": "ok",
            "slug": args.slug,
            "room_id": room_id,
            "project_id": project_data["project_id"],
            "project_slug": project_data["project_slug"],
            "project_name": project_data["project_name"],
            "widget_id": widget_id,
            "widget_url": widget_url,
            "webhook_url": webhook_url,
            "board_url": project_data["board_url"],
            "project_url": project_data["project_url"],
            "config_reload": reload_result,
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))
    finally:
        await taiga_client.close()
        await admin_client.close()


async def _resolve_project_data(
    *,
    args: argparse.Namespace,
    settings: Settings,
    taiga_client: TaigaClient,
    existing_project: ProjectMapping | None,
) -> dict[str, Any]:
    provisional = ProjectMapping(
        room_id=args.room_id or (existing_project.room_id if existing_project else "!pending:matrix"),
        project_id=args.project_id or (existing_project.project_id if existing_project else None),
        project_slug=args.project_slug or (existing_project.project_slug if existing_project else None),
        project_name=args.project_name or (existing_project.project_name if existing_project else None),
        project_url=args.project_url or (existing_project.project_url if existing_project else None),
        webhook_secret=existing_project.webhook_secret if existing_project else None,
    )
    taiga_project = await taiga_client.get_project(provisional)
    project_slug = provisional.project_slug or taiga_project.slug
    project_name = provisional.project_name or taiga_project.name
    project_id = provisional.project_id or taiga_project.id
    project_url = provisional.project_url or f"{settings.taiga_base_url.rstrip('/')}/project/{project_slug}"
    board_url = f"{project_url.rstrip('/')}/kanban"
    return {
        "project_id": project_id,
        "project_slug": project_slug,
        "project_name": project_name,
        "project_url": project_url,
        "board_url": board_url,
    }


async def _ensure_room(
    *,
    args: argparse.Namespace,
    settings: Settings,
    admin_client: MatrixAdminClient,
    admin_user_id: str,
    project_name: str,
    board_url: str,
) -> str:
    if args.create_room:
        invitees = [user_id for user_id in args.invite_user if user_id and user_id != admin_user_id]
        if settings.matrix_user_id != admin_user_id and settings.matrix_user_id not in invitees:
            invitees.append(settings.matrix_user_id)
        room_name = args.room_name or build_project_room_name(project_name)
        return await admin_client.create_room(
            name=room_name,
            topic=build_project_room_topic(project_name, board_url),
            invite=invitees,
        )

    room_id = str(args.room_id)
    try:
        await admin_client.get_state(room_id)
    except MatrixAdminError:
        try:
            await admin_client.join_room(room_id)
            await admin_client.get_state(room_id)
        except MatrixAdminError as exc:
            raise SystemExit(
                f"Не удалось получить доступ к комнате {room_id}. "
                "Для существующей комнаты сервисный пользователь должен уже быть в комнате или получить приглашение. "
                f"Детали: {exc}"
            ) from exc
    return room_id


async def _invite_user_if_needed(
    admin_client: MatrixAdminClient,
    room_id: str,
    user_id: str,
    *,
    skip_if_same: str,
) -> None:
    if not user_id or user_id == skip_if_same:
        return
    try:
        await admin_client.invite_user(room_id, user_id)
    except MatrixAdminError as exc:
        message = str(exc).lower()
        if "already" in message or "invited" in message:
            LOGGER.info("Skipping invite for %s in %s: %s", user_id, room_id, exc)
            return
        raise


if __name__ == "__main__":
    asyncio.run(main())
