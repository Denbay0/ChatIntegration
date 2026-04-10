from __future__ import annotations

import asyncio
import logging
import re

from nio import (
    AsyncClient,
    AsyncClientConfig,
    InviteMemberEvent,
    JoinError,
    JoinResponse,
    LoginError,
    LoginResponse,
    MatrixRoom,
    RoomMessageText,
    RoomSendError,
    RoomSendResponse,
)

from app.config import Settings
from app.formatter import (
    MatrixMessage,
    build_comment_added_message,
    build_help_message,
    build_my_tasks_message,
    build_open_project_message,
    build_tasks_message,
    format_created_user_story_message,
    is_comment_command,
    is_help_command,
    is_my_command,
    is_open_command,
    is_task_command,
    is_tasks_command,
    parse_comment_command,
    parse_task_command,
)
from app.models import BridgeConfig, ProjectMapping, TaigaUser, TaigaUserStory
from app.taiga import TaigaApiError, TaigaClient
from app.widget_i18n import localize_taiga_error

LOGGER = logging.getLogger(__name__)
WHITESPACE_RE = re.compile(r"\s+")


class MatrixBot:
    def __init__(self, settings: Settings, bridge_config: BridgeConfig, taiga_client: TaigaClient) -> None:
        self.settings = settings
        self.bridge_config = bridge_config
        self.taiga_client = taiga_client
        self.client: AsyncClient | None = None
        self._sync_task: asyncio.Task[None] | None = None
        self._ready = asyncio.Event()
        self._send_lock = asyncio.Lock()

    @property
    def is_running(self) -> bool:
        return bool(self._sync_task and not self._sync_task.done())

    async def start(self) -> None:
        LOGGER.info("Starting Matrix bot for %s", self.settings.matrix_user_id)
        self.settings.data_dir.mkdir(parents=True, exist_ok=True)

        client_config = AsyncClientConfig(encryption_enabled=False, store_sync_tokens=True)
        self.client = AsyncClient(
            homeserver=self.settings.matrix_homeserver,
            user=self.settings.matrix_user_id,
            device_id="TAIGABRIDGE",
            store_path=str(self.settings.data_dir / "nio-store"),
            config=client_config,
        )

        login_response = await self.client.login(
            password=self.settings.matrix_password.get_secret_value(),
            device_name="taiga-matrix-bridge",
        )

        if isinstance(login_response, LoginError):
            raise RuntimeError(f"Matrix login failed: {login_response.message}")
        if not isinstance(login_response, LoginResponse):
            raise RuntimeError("Matrix login did not return a success response")

        LOGGER.info("Matrix login succeeded for device %s", login_response.device_id)

        initial_sync = await self.client.sync(timeout=0, full_state=True)
        LOGGER.info("Initial Matrix sync completed; next_batch=%s", getattr(initial_sync, "next_batch", None))

        for room_id in list(self.client.invited_rooms):
            await self._join_room(room_id)

        self.client.add_event_callback(self._handle_invite, InviteMemberEvent)
        self.client.add_event_callback(self._handle_message, RoomMessageText)

        self._sync_task = asyncio.create_task(self._sync_forever(), name="matrix-sync-forever")
        self._ready.set()

    async def stop(self) -> None:
        self._ready.clear()

        if self.client is not None:
            self.client.stop_sync_forever()

        if self._sync_task is not None:
            self._sync_task.cancel()
            try:
                await self._sync_task
            except asyncio.CancelledError:
                pass

        if self.client is not None:
            await self.client.close()

        LOGGER.info("Matrix bot stopped")

    async def send_notice(self, room_id: str, message: MatrixMessage) -> None:
        await self._ready.wait()
        if self.client is None:
            raise RuntimeError("Matrix client is not available")

        content: dict[str, object] = {
            "msgtype": "m.notice",
            "body": message.body,
        }
        if message.formatted_body:
            content["format"] = "org.matrix.custom.html"
            content["formatted_body"] = message.formatted_body

        async with self._send_lock:
            response = await self.client.room_send(
                room_id=room_id,
                message_type="m.room.message",
                content=content,
                ignore_unverified_devices=True,
            )

        if isinstance(response, RoomSendError):
            raise RuntimeError(f"Matrix send failed: {response.message}")
        if not isinstance(response, RoomSendResponse):
            raise RuntimeError("Matrix send returned an unexpected response")

    async def _sync_forever(self) -> None:
        if self.client is None:
            return

        try:
            await self.client.sync_forever(
                timeout=30_000,
                since=self.client.next_batch,
                full_state=True,
                set_presence="online",
            )
        except asyncio.CancelledError:
            raise
        except Exception:
            LOGGER.exception("Matrix sync_forever loop crashed")
            raise

    async def _handle_invite(self, room: MatrixRoom, event: InviteMemberEvent) -> None:
        if event.membership != "invite" or event.state_key != self.settings.matrix_user_id:
            return
        await self._join_room(room.room_id)

    async def _handle_message(self, room: MatrixRoom, event: RoomMessageText) -> None:
        if event.sender == self.settings.matrix_user_id:
            return

        if room.room_id not in {project.room_id for project in self.bridge_config.projects.values()}:
            return

        if event.source.get("content", {}).get("m.relates_to"):
            return

        message = (event.body or "").strip()
        if not message.startswith("!"):
            return

        LOGGER.info("Received Matrix command in %s from %s: %s", room.room_id, event.sender, message)

        try:
            sender_display_name = room.user_name(event.sender) if hasattr(room, "user_name") else None
            reply = await self._dispatch_command(
                room.room_id,
                message,
                sender_id=event.sender,
                sender_display_name=sender_display_name,
            )
        except ValueError as exc:
            reply = MatrixMessage(body=str(exc))
        except TaigaApiError as exc:
            LOGGER.warning("Taiga command failed: %s payload=%s", exc, exc.payload)
            reply = MatrixMessage(body=f"Ошибка Taiga API: {localize_taiga_error(str(exc), status_code=exc.status_code)}")
        except Exception:
            LOGGER.exception("Unexpected error while handling Matrix command")
            reply = MatrixMessage(body="Внутренняя ошибка bridge при обработке команды.")

        await self.send_notice(room.room_id, reply)

    async def _dispatch_command(
        self,
        room_id: str,
        message: str,
        *,
        sender_id: str,
        sender_display_name: str | None,
    ) -> MatrixMessage:
        lookup = self.bridge_config.get_project_by_room(room_id)
        if lookup is None:
            raise ValueError("Эта комната не привязана к проекту в config.yaml.")

        _, project = lookup
        project_name = await self._resolve_project_display_name(project)
        board_url = project.resolved_board_url(self.taiga_client.base_url, self.taiga_client.default_project_slug)
        project_url = project.resolved_project_url(self.taiga_client.base_url, self.taiga_client.default_project_slug)

        if is_help_command(message):
            return build_help_message()

        if is_task_command(message):
            command = parse_task_command(message)
            story = await self.taiga_client.create_user_story(
                project=project,
                title=command.title,
                description=command.description,
            )
            return format_created_user_story_message(story, self.taiga_client.base_url)

        if is_tasks_command(message):
            stories = await self.taiga_client.list_user_stories(project, limit=8)
            return build_tasks_message(
                stories,
                board_url=board_url,
                project_name=project_name,
            )

        if is_open_command(message):
            return build_open_project_message(
                project_name=project_name,
                project_url=project_url,
                board_url=board_url,
            )

        if is_my_command(message):
            stories = await self.taiga_client.list_user_stories(project, limit=60)
            assigned_stories, lookup_note = self._filter_my_stories(
                stories,
                project=project,
                sender_id=sender_id,
                sender_display_name=sender_display_name,
            )
            return build_my_tasks_message(
                assigned_stories[:8],
                board_url=board_url,
                project_name=project_name,
                lookup_note=lookup_note,
            )

        if is_comment_command(message):
            command = parse_comment_command(message)
            story = await self.taiga_client.add_comment_to_user_story(project, command.ref, command.text)
            return build_comment_added_message(story, self.taiga_client.base_url)

        raise ValueError("Команда не поддерживается. Отправьте !help или !помощь, чтобы увидеть подсказку.")

    async def _resolve_project_display_name(self, project: ProjectMapping) -> str | None:
        if project.project_name:
            return project.project_name
        try:
            taiga_project = await self.taiga_client.get_project(project)
        except TaigaApiError:
            return project.resolved_project_slug(self.taiga_client.default_project_slug)
        return taiga_project.name

    def _filter_my_stories(
        self,
        stories: list[TaigaUserStory],
        *,
        project: ProjectMapping,
        sender_id: str,
        sender_display_name: str | None,
    ) -> tuple[list[TaigaUserStory], str | None]:
        candidates = self._identity_candidates(
            project=project,
            sender_id=sender_id,
            sender_display_name=sender_display_name,
        )
        matched = [
            story for story in stories if story.assigned_to and self._user_matches_candidates(story.assigned_to, candidates)
        ]
        matched.sort(key=lambda story: story.modified_date or story.created_date or "", reverse=True)

        if matched:
            return matched, None

        mapped_identity = project.user_mappings.get(sender_id)
        if mapped_identity:
            note = f"Поиск выполнен по привязке Taiga-пользователя «{mapped_identity}», назначенные задачи не найдены."
        elif sender_display_name:
            note = (
                f"Поиск выполнен по имени «{sender_display_name}» и Matrix-профилю. "
                "Если у вас другой логин в Taiga, добавьте user_mappings в config.yaml."
            )
        else:
            note = "Назначенные задачи не найдены. При необходимости добавьте user_mappings в config.yaml."
        return [], note

    def _identity_candidates(
        self,
        *,
        project: ProjectMapping,
        sender_id: str,
        sender_display_name: str | None,
    ) -> set[str]:
        raw_values = [
            project.user_mappings.get(sender_id),
            sender_id,
            sender_id.split(":", 1)[0].lstrip("@"),
            sender_display_name,
        ]
        candidates: set[str] = set()
        for value in raw_values:
            if not value:
                continue
            normalized = self._normalize_identity(value)
            if normalized:
                candidates.add(normalized)
            if "@" in value and not value.startswith("@"):
                email_localpart = value.split("@", 1)[0].strip()
                normalized_localpart = self._normalize_identity(email_localpart)
                if normalized_localpart:
                    candidates.add(normalized_localpart)
        return candidates

    def _user_matches_candidates(self, user: TaigaUser, candidates: set[str]) -> bool:
        user_values = {
            self._normalize_identity(value)
            for value in (
                user.full_name_display,
                user.full_name,
                user.username,
                user.email,
            )
            if value
        }
        user_values.discard("")
        if candidates & user_values:
            return True

        for candidate in candidates:
            if len(candidate) < 4:
                continue
            for user_value in user_values:
                if len(user_value) < 4:
                    continue
                if candidate in user_value or user_value in candidate:
                    return True
        return False

    @staticmethod
    def _normalize_identity(value: str) -> str:
        text = WHITESPACE_RE.sub(" ", value.strip().lower())
        if text.startswith("@") and ":" in text:
            text = text[1:].split(":", 1)[0]
        return text.strip()

    async def _join_room(self, room_id: str) -> None:
        if self.client is None:
            return

        LOGGER.info("Joining invited Matrix room %s", room_id)
        response = await self.client.join(room_id)
        if isinstance(response, JoinError):
            LOGGER.warning("Failed to join room %s: %s", room_id, response.message)
            return
        if isinstance(response, JoinResponse):
            LOGGER.info("Joined Matrix room %s", room_id)
