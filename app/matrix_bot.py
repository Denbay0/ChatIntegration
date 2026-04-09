from __future__ import annotations

import asyncio
import logging

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
    build_help_message,
    format_created_user_story_message,
    parse_task_command,
)
from app.models import BridgeConfig
from app.taiga import TaigaApiError, TaigaClient

LOGGER = logging.getLogger(__name__)


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
            reply = await self._dispatch_command(room.room_id, message)
        except ValueError as exc:
            reply = MatrixMessage(body=str(exc))
        except TaigaApiError as exc:
            LOGGER.warning("Taiga command failed: %s payload=%s", exc, exc.payload)
            reply = MatrixMessage(body=f"Taiga API error: {exc}")
        except Exception:
            LOGGER.exception("Unexpected error while handling Matrix command")
            reply = MatrixMessage(body="Unexpected bridge error while processing the command.")

        await self.send_notice(room.room_id, reply)

    async def _dispatch_command(self, room_id: str, message: str) -> MatrixMessage:
        lookup = self.bridge_config.get_project_by_room(room_id)
        if lookup is None:
            raise ValueError("This room is not mapped in config.yaml.")

        _, project = lookup

        if message.startswith("!help"):
            return build_help_message()

        if message.startswith("!task"):
            command = parse_task_command(message)
            story = await self.taiga_client.create_user_story(
                project=project,
                title=command.title,
                description=command.description,
            )
            return format_created_user_story_message(story, self.taiga_client.base_url)

        raise ValueError("Unsupported command. Send !help to see available commands.")

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
