from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import quote

import httpx

from app.formatter import MatrixMessage


class MatrixAdminError(RuntimeError):
    pass


@dataclass(slots=True)
class MatrixAdminClient:
    homeserver: str
    user_id: str
    password: str
    device_id: str = "TAIGAADMIN"
    device_name: str = "taiga-room-admin"
    timeout: float = 30.0
    _client: httpx.AsyncClient = field(init=False, repr=False)
    _access_token: str | None = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        self.homeserver = self.homeserver.rstrip("/")
        self._client = httpx.AsyncClient(timeout=self.timeout)

    async def login(self) -> None:
        response = await self._client.post(
            f"{self.homeserver}/_matrix/client/v3/login",
            json={
                "type": "m.login.password",
                "identifier": {"type": "m.id.user", "user": self.user_id},
                "password": self.password,
                "device_id": self.device_id,
                "initial_device_display_name": self.device_name,
            },
        )
        data = self._decode_response(response)
        if response.status_code >= 400:
            raise MatrixAdminError(f"Matrix login failed: {data}")
        self._access_token = str(data["access_token"])

    async def close(self) -> None:
        await self._client.aclose()

    async def create_room(
        self,
        *,
        name: str,
        topic: str | None = None,
        invite: list[str] | None = None,
        power_level_override: dict[str, Any] | None = None,
    ) -> str:
        data = await self._request(
            "POST",
            "/_matrix/client/v3/createRoom",
            json={
                "name": name,
                "topic": topic,
                "preset": "private_chat",
                "invite": invite or [],
                "power_level_content_override": power_level_override or {},
            },
        )
        room_id = data.get("room_id")
        if not room_id:
            raise MatrixAdminError(f"Matrix room creation did not return room_id: {data}")
        return str(room_id)

    async def join_room(self, room_id: str) -> None:
        await self._request("POST", f"/_matrix/client/v3/join/{quote(room_id, safe='')}", json={})

    async def invite_user(self, room_id: str, user_id: str) -> None:
        await self._request(
            "POST",
            f"/_matrix/client/v3/rooms/{quote(room_id, safe='')}/invite",
            json={"user_id": user_id},
        )

    async def send_notice(self, room_id: str, message: MatrixMessage) -> str:
        content: dict[str, Any] = {
            "msgtype": "m.notice",
            "body": message.body,
        }
        if message.formatted_body:
            content["format"] = "org.matrix.custom.html"
            content["formatted_body"] = message.formatted_body

        data = await self._request(
            "PUT",
            f"/_matrix/client/v3/rooms/{quote(room_id, safe='')}/send/m.room.message/{self._txn_id()}",
            json=content,
        )
        event_id = data.get("event_id")
        if not event_id:
            raise MatrixAdminError(f"Matrix send did not return event_id: {data}")
        return str(event_id)

    async def put_state(self, room_id: str, event_type: str, content: dict[str, Any], state_key: str = "") -> str | None:
        encoded_state_key = quote(state_key, safe="")
        data = await self._request(
            "PUT",
            f"/_matrix/client/v3/rooms/{quote(room_id, safe='')}/state/{quote(event_type, safe='')}/{encoded_state_key}",
            json=content,
        )
        event_id = data.get("event_id")
        return str(event_id) if event_id else None

    async def get_state(self, room_id: str) -> list[dict[str, Any]]:
        data = await self._request(
            "GET",
            f"/_matrix/client/v3/rooms/{quote(room_id, safe='')}/state",
        )
        if not isinstance(data, list):
            raise MatrixAdminError(f"Matrix state response is not a list: {data}")
        return [item for item in data if isinstance(item, dict)]

    async def get_state_event(self, room_id: str, event_type: str, state_key: str = "") -> dict[str, Any] | None:
        encoded_state_key = quote(state_key, safe="")
        response = await self._client.get(
            f"{self.homeserver}/_matrix/client/v3/rooms/{quote(room_id, safe='')}/state/{quote(event_type, safe='')}/{encoded_state_key}",
            headers=self._headers,
        )
        if response.status_code == 404:
            return None
        data = self._decode_response(response)
        if response.status_code >= 400:
            raise MatrixAdminError(f"Matrix state event request failed: {data}")
        if not isinstance(data, dict):
            raise MatrixAdminError(f"Matrix state event response is not an object: {data}")
        return data

    async def pin_event(self, room_id: str, event_id: str, *, keep_existing: bool = True, limit: int = 8) -> None:
        current = await self.get_state_event(room_id, "m.room.pinned_events")
        pinned = list(current.get("pinned", [])) if isinstance(current, dict) else []
        if keep_existing:
            updated = [event_id, *[value for value in pinned if value != event_id]]
        else:
            updated = [event_id]
        await self.put_state(room_id, "m.room.pinned_events", {"pinned": updated[:limit]})

    async def reload_bridge_config(self, bridge_base_url: str, bridge_secret: str) -> dict[str, Any]:
        response = await self._client.post(
            f"{bridge_base_url.rstrip('/')}/admin/reload-config",
            headers={"X-Bridge-Secret": bridge_secret},
        )
        data = self._decode_response(response)
        if response.status_code >= 400:
            raise MatrixAdminError(f"Bridge config reload failed: {data}")
        if not isinstance(data, dict):
            raise MatrixAdminError(f"Bridge reload response is not an object: {data}")
        return data

    @property
    def _headers(self) -> dict[str, str]:
        if not self._access_token:
            raise MatrixAdminError("Matrix client is not logged in")
        return {"Authorization": f"Bearer {self._access_token}"}

    async def _request(
        self,
        method: str,
        path: str,
        *,
        headers: dict[str, str] | None = None,
        **kwargs: Any,
    ) -> Any:
        merged_headers = dict(self._headers)
        if headers:
            merged_headers.update(headers)
        response = await self._client.request(
            method,
            f"{self.homeserver}{path}",
            headers=merged_headers,
            **kwargs,
        )
        data = self._decode_response(response)
        if response.status_code >= 400:
            raise MatrixAdminError(f"Matrix API returned HTTP {response.status_code}: {data}")
        return data

    @staticmethod
    def _decode_response(response: httpx.Response) -> Any:
        if response.status_code == 204:
            return {}
        try:
            return response.json()
        except ValueError:
            return response.text

    @staticmethod
    def _txn_id() -> str:
        return uuid.uuid4().hex
