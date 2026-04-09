from __future__ import annotations

import logging
from typing import Any

import httpx

from app.models import KaitenCard, KaitenUser, ProjectMapping

LOGGER = logging.getLogger(__name__)


class KaitenApiError(RuntimeError):
    def __init__(self, message: str, status_code: int | None = None, payload: Any | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.payload = payload


class KaitenClient:
    def __init__(self, base_url: str, web_base_url: str, token: str, timeout: float = 20.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.web_base_url = web_base_url.rstrip("/")
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=timeout,
            follow_redirects=True,
            headers={
                "Authorization": _authorization_header(token),
                "Accept": "application/json",
                "Content-Type": "application/json",
                "User-Agent": "kaiten-matrix-bridge/1.0",
            },
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def create_card(
        self,
        project: ProjectMapping,
        title: str,
        description: str | None = None,
    ) -> KaitenCard:
        payload: dict[str, Any] = {
            "title": title,
            "board_id": project.board_id,
            "position": project.position,
            "text_format_type_id": 1,
        }
        if description:
            payload["description"] = description
        if project.column_id is not None:
            payload["column_id"] = project.column_id
        if project.lane_id is not None:
            payload["lane_id"] = project.lane_id

        data = await self._request("POST", "/cards", json=payload)
        return self._parse_card(data)

    async def get_card(self, card_id: int) -> KaitenCard:
        data = await self._request("GET", f"/cards/{card_id}", params={"broken_api": "false"})
        return self._parse_card(data)

    def card_url(self, card_id: int) -> str:
        return f"{self.web_base_url}/cards/{card_id}"

    async def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        try:
            response = await self._client.request(method, path, **kwargs)
        except httpx.HTTPError as exc:
            raise KaitenApiError(f"Request to Kaiten failed: {exc}") from exc

        if response.status_code >= 400:
            payload: Any
            try:
                payload = response.json()
            except ValueError:
                payload = response.text

            raise KaitenApiError(
                f"Kaiten API returned HTTP {response.status_code}",
                status_code=response.status_code,
                payload=payload,
            )

        if response.status_code == 204:
            return {}

        try:
            return response.json()
        except ValueError as exc:
            LOGGER.error("Kaiten returned non-JSON response for %s %s", method, path)
            raise KaitenApiError("Kaiten API returned a non-JSON response") from exc

    def _parse_card(self, payload: dict[str, Any]) -> KaitenCard:
        owner_payload = payload.get("owner")
        owner = KaitenUser.model_validate(owner_payload) if isinstance(owner_payload, dict) else None
        return KaitenCard(
            id=int(payload["id"]),
            title=str(payload["title"]),
            description=payload.get("description"),
            board_id=_maybe_int(payload.get("board_id")),
            column_id=_maybe_int(payload.get("column_id")),
            lane_id=_maybe_int(payload.get("lane_id")),
            owner=owner,
            raw=payload,
        )


def _authorization_header(token: str) -> str:
    stripped = token.strip()
    if stripped.lower().startswith("bearer "):
        return stripped
    return f"Bearer {stripped}"


def _maybe_int(value: Any) -> int | None:
    try:
        if value is None:
            return None
        return int(value)
    except (TypeError, ValueError):
        return None
