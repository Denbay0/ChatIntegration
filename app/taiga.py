from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

from app.models import ProjectMapping, TaigaProject, TaigaStatus, TaigaUser, TaigaUserStory

LOGGER = logging.getLogger(__name__)


class TaigaApiError(RuntimeError):
    def __init__(self, message: str, status_code: int | None = None, payload: Any | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.payload = payload


class TaigaClient:
    def __init__(
        self,
        api_url: str,
        base_url: str,
        username: str | None = None,
        password: str | None = None,
        token: str | None = None,
        accept_language: str = "ru",
        default_project_id: int | None = None,
        default_project_slug: str | None = None,
        timeout: float = 20.0,
    ) -> None:
        self.api_url = api_url.rstrip("/")
        self.base_url = base_url.rstrip("/")
        self.username = username
        self.password = password
        self.default_project_id = default_project_id
        self.default_project_slug = default_project_slug
        self._access_token = token.strip() if token else None
        self._refresh_token: str | None = None
        self._auth_lock = asyncio.Lock()
        self._client = httpx.AsyncClient(
            base_url=self.api_url,
            timeout=timeout,
            follow_redirects=True,
            headers={
                "Accept": "application/json",
                "Accept-Language": accept_language,
                "User-Agent": "taiga-matrix-bridge/1.0",
            },
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def create_user_story(
        self,
        project: ProjectMapping,
        title: str,
        description: str | None = None,
    ) -> TaigaUserStory:
        project_id = project.resolved_project_id(self.default_project_id)
        project_slug = project.resolved_project_slug(self.default_project_slug)
        if project_id is None and project_slug:
            project_id = await self.resolve_project_id(project_slug)
        if project_id is None:
            raise TaigaApiError("Taiga project id is not configured.")

        payload: dict[str, Any] = {
            "project": project_id,
            "subject": title,
        }
        if description:
            payload["description"] = description

        data = await self._request("POST", "/userstories", auth=True, json=payload)
        return self._parse_user_story(
            data,
            fallback_project_id=project_id,
            fallback_project_slug=project_slug,
        )

    async def get_user_story_by_ref(self, project: ProjectMapping, ref: int) -> TaigaUserStory:
        project_id, project_slug = await self._resolve_project_context(project)
        resolved_project_slug = project_slug
        if not resolved_project_slug:
            resolved_project_slug = (await self.get_project(project)).slug

        data = await self._request(
            "GET",
            "/userstories/by_ref",
            auth=True,
            params={
                "project__slug": resolved_project_slug,
                "ref": ref,
            },
        )
        if not isinstance(data, dict):
            raise TaigaApiError(f"Unexpected user story payload for ref '{ref}'.", payload=data)

        return self._parse_user_story(
            data,
            fallback_project_id=project_id,
            fallback_project_slug=resolved_project_slug,
        )

    async def add_comment_to_user_story(
        self,
        project: ProjectMapping,
        ref: int,
        comment: str,
    ) -> TaigaUserStory:
        story = await self.get_user_story_by_ref(project, ref)
        if story.version is None:
            raise TaigaApiError("Taiga user story response did not include version.", payload=story.raw)

        data = await self._request(
            "PATCH",
            f"/userstories/{story.id}",
            auth=True,
            json={
                "comment": comment,
                "version": story.version,
            },
        )
        if not isinstance(data, dict):
            raise TaigaApiError("Unexpected Taiga response while adding comment.", payload=data)

        return self._parse_user_story(
            data,
            fallback_project_id=story.project_id,
            fallback_project_slug=story.project_slug,
        )

    async def get_project(self, project: ProjectMapping) -> TaigaProject:
        project_id, project_slug = await self._resolve_project_context(project)
        if project_slug:
            data = await self.get_project_by_slug(project_slug)
        else:
            data = await self._request("GET", f"/projects/{project_id}", auth=True)

        if not isinstance(data, dict):
            raise TaigaApiError("Unexpected Taiga project payload.")

        return self._parse_project(data, fallback_project_id=project_id, fallback_project_slug=project_slug)

    async def list_user_story_statuses(self, project: ProjectMapping) -> list[TaigaStatus]:
        project_id, _ = await self._resolve_project_context(project)
        data = await self._request(
            "GET",
            "/userstory-statuses",
            auth=True,
            params={"project": project_id},
        )
        if not isinstance(data, list):
            raise TaigaApiError("Unexpected user story status payload from Taiga.")

        statuses = [self._parse_status(item) for item in data if isinstance(item, dict)]
        return sorted(statuses, key=lambda status: status.order or 0)

    async def list_user_stories(
        self,
        project: ProjectMapping,
        *,
        limit: int = 50,
    ) -> list[TaigaUserStory]:
        project_id, project_slug = await self._resolve_project_context(project)
        data = await self._request(
            "GET",
            "/userstories",
            auth=True,
            params={"project": project_id},
        )
        if not isinstance(data, list):
            raise TaigaApiError("Unexpected user story list payload from Taiga.")

        stories = [
            self._parse_user_story(
                item,
                fallback_project_id=project_id,
                fallback_project_slug=project_slug,
            )
            for item in data
            if isinstance(item, dict)
        ]
        stories.sort(key=lambda story: story.modified_date or story.created_date or "", reverse=True)
        return stories[:limit]

    async def list_project_users(self, project: ProjectMapping) -> list[TaigaUser]:
        project_id, _ = await self._resolve_project_context(project)
        data = await self._request(
            "GET",
            "/users",
            auth=True,
            params={"project": project_id},
        )
        if not isinstance(data, list):
            raise TaigaApiError("Unexpected user list payload from Taiga.")
        return [TaigaUser.model_validate(item) for item in data if isinstance(item, dict)]

    async def resolve_project_id(self, project_slug: str) -> int:
        data = await self._request("GET", "/resolver", auth=False, params={"project": project_slug})
        project_id = data.get("project")
        if project_id is None:
            raise TaigaApiError(f"Could not resolve Taiga project id for slug '{project_slug}'.")
        return int(project_id)

    async def get_project_by_slug(self, project_slug: str) -> dict[str, Any]:
        data = await self._request(
            "GET",
            "/projects/by_slug",
            auth=False,
            params={"slug": project_slug},
        )
        if not isinstance(data, dict):
            raise TaigaApiError(f"Unexpected project payload for slug '{project_slug}'.")
        return data

    async def list_webhooks(self, project_id: int) -> list[dict[str, Any]]:
        data = await self._request(
            "GET",
            "/webhooks",
            auth=True,
            params={"project": project_id},
        )
        if not isinstance(data, list):
            raise TaigaApiError("Unexpected webhook list payload from Taiga.")
        return [item for item in data if isinstance(item, dict)]

    async def ensure_webhook(
        self,
        project_id: int,
        name: str,
        url: str,
        key: str,
    ) -> dict[str, Any]:
        for webhook in await self.list_webhooks(project_id):
            if webhook.get("url") == url or webhook.get("name") == name:
                updates: dict[str, Any] = {}
                if webhook.get("name") != name:
                    updates["name"] = name
                if webhook.get("url") != url:
                    updates["url"] = url
                if webhook.get("key") != key:
                    updates["key"] = key

                if updates:
                    updated = await self._request(
                        "PATCH",
                        f"/webhooks/{webhook['id']}",
                        auth=True,
                        json=updates,
                    )
                    if not isinstance(updated, dict):
                        raise TaigaApiError("Unexpected webhook update payload from Taiga.")
                    return updated
                return webhook

        created = await self._request(
            "POST",
            "/webhooks",
            auth=True,
            json={
                "project": project_id,
                "name": name,
                "url": url,
                "key": key,
            },
        )
        if not isinstance(created, dict):
            raise TaigaApiError("Unexpected webhook create payload from Taiga.")
        return created

    async def test_webhook(self, webhook_id: int) -> dict[str, Any]:
        data = await self._request("POST", f"/webhooks/{webhook_id}/test", auth=True)
        if not isinstance(data, dict):
            raise TaigaApiError("Unexpected webhook test payload from Taiga.")
        return data

    async def authenticate(self, force: bool = False) -> str:
        async with self._auth_lock:
            return await self._authenticate_without_lock(force=force)

    async def refresh_auth_token(self) -> str:
        async with self._auth_lock:
            if not self._refresh_token:
                return await self._authenticate_without_lock(force=True)

            response = await self._client.post(
                "/auth/refresh",
                json={"refresh": self._refresh_token},
            )
            data = self._decode_response(response)

            if response.status_code >= 400:
                LOGGER.warning(
                    "Taiga refresh token failed with HTTP %s; falling back to login",
                    response.status_code,
                )
                self._access_token = None
                self._refresh_token = None
                return await self._authenticate_without_lock(force=True)

            if not isinstance(data, dict) or not data.get("auth_token"):
                raise TaigaApiError("Taiga refresh response did not include auth_token.", payload=data)

            self._access_token = str(data["auth_token"])
            refresh_token = data.get("refresh")
            if refresh_token:
                self._refresh_token = str(refresh_token)
            return self._access_token

    async def _authenticate_without_lock(self, force: bool) -> str:
        if self._access_token and not force:
            return self._access_token

        if not self.username or not self.password:
            raise TaigaApiError(
                "Taiga credentials are missing. Set TAIGA_TOKEN or TAIGA_USERNAME and TAIGA_PASSWORD."
            )

        response = await self._client.post(
            "/auth",
            json={
                "type": "normal",
                "username": self.username,
                "password": self.password,
            },
        )
        data = self._decode_response(response)

        if response.status_code >= 400:
            raise TaigaApiError(
                "Taiga authentication failed.",
                status_code=response.status_code,
                payload=data,
            )

        if not isinstance(data, dict) or not data.get("auth_token"):
            raise TaigaApiError("Taiga auth response did not include auth_token.", payload=data)

        self._access_token = str(data["auth_token"])
        refresh_token = data.get("refresh")
        self._refresh_token = str(refresh_token) if refresh_token else None
        return self._access_token

    async def _request(
        self,
        method: str,
        path: str,
        *,
        auth: bool,
        retry_on_401: bool = True,
        **kwargs: Any,
    ) -> Any:
        headers = dict(kwargs.pop("headers", {}))
        if auth:
            headers["Authorization"] = f"Bearer {await self.authenticate()}"
        if "json" in kwargs:
            headers.setdefault("Content-Type", "application/json")

        try:
            response = await self._client.request(method, path, headers=headers, **kwargs)
        except httpx.HTTPError as exc:
            raise TaigaApiError(f"Request to Taiga failed: {exc}") from exc

        if response.status_code == 401 and auth and retry_on_401:
            headers["Authorization"] = f"Bearer {await self.refresh_auth_token()}"
            response = await self._client.request(method, path, headers=headers, **kwargs)

        data = self._decode_response(response)
        if response.status_code >= 400:
            raise TaigaApiError(
                f"Taiga API returned HTTP {response.status_code}",
                status_code=response.status_code,
                payload=data,
            )
        return data

    def _parse_user_story(
        self,
        payload: dict[str, Any],
        *,
        fallback_project_id: int | None,
        fallback_project_slug: str | None,
    ) -> TaigaUserStory:
        owner_payload = payload.get("owner_extra_info") or payload.get("owner")
        owner = TaigaUser.model_validate(owner_payload) if isinstance(owner_payload, dict) else None
        assigned_to_payload = payload.get("assigned_to_extra_info") or payload.get("assigned_to")
        assigned_to = TaigaUser.model_validate(assigned_to_payload) if isinstance(assigned_to_payload, dict) else None

        permalink = _string_or_none(payload.get("permalink"))
        project_slug = (
            fallback_project_slug
            or _extract_project_slug_from_permalink(permalink)
            or _extract_project_slug_from_payload(payload)
            or self.default_project_slug
        )
        project_id = (
            _maybe_int(payload.get("project"))
            or _maybe_int((payload.get("project_extra_info") or {}).get("id"))
            or fallback_project_id
            or self.default_project_id
        )
        status_payload = payload.get("status_extra_info") or {}
        status_name = _string_or_none(status_payload.get("name"))
        status_color = _string_or_none(status_payload.get("color"))
        status_id = _maybe_int(payload.get("status"))

        ref = _maybe_int(payload.get("ref")) or _maybe_int(payload.get("id"))
        if ref is None:
            raise TaigaApiError("Taiga user story response did not include ref/id.", payload=payload)

        story_id = _maybe_int(payload.get("id"))
        if story_id is None:
            raise TaigaApiError("Taiga user story response did not include id.", payload=payload)

        subject = _string_or_none(payload.get("subject"))
        if not subject:
            raise TaigaApiError("Taiga user story response did not include subject.", payload=payload)

        if not permalink:
            permalink = _build_user_story_permalink(self.base_url, project_slug, ref)

        return TaigaUserStory(
            id=story_id,
            ref=ref,
            subject=subject,
            description=_string_or_none(payload.get("description")),
            permalink=permalink,
            project_id=project_id,
            project_slug=project_slug,
            version=_maybe_int(payload.get("version")),
            status_id=status_id,
            status_name=status_name,
            status_color=status_color,
            is_closed=_maybe_bool(payload.get("is_closed")),
            created_date=_string_or_none(payload.get("created_date")),
            modified_date=_string_or_none(payload.get("modified_date")),
            kanban_order=_maybe_int(payload.get("kanban_order")),
            owner=owner,
            assigned_to_id=_maybe_int(payload.get("assigned_to")),
            assigned_to=assigned_to,
            raw=payload,
        )

    async def _resolve_project_context(self, project: ProjectMapping) -> tuple[int, str | None]:
        project_id = project.resolved_project_id(self.default_project_id)
        project_slug = project.resolved_project_slug(self.default_project_slug)
        if project_id is None and project_slug:
            project_id = await self.resolve_project_id(project_slug)
        if project_id is None:
            raise TaigaApiError("Taiga project id is not configured.")
        return project_id, project_slug

    def _parse_project(
        self,
        payload: dict[str, Any],
        *,
        fallback_project_id: int | None,
        fallback_project_slug: str | None,
    ) -> TaigaProject:
        owner_payload = payload.get("owner")
        owner = TaigaUser.model_validate(owner_payload) if isinstance(owner_payload, dict) else None

        project_id = _maybe_int(payload.get("id")) or fallback_project_id
        if project_id is None:
            raise TaigaApiError("Taiga project response did not include id.", payload=payload)

        name = _string_or_none(payload.get("name"))
        if not name:
            raise TaigaApiError("Taiga project response did not include name.", payload=payload)

        slug = _string_or_none(payload.get("slug")) or fallback_project_slug
        if not slug:
            raise TaigaApiError("Taiga project response did not include slug.", payload=payload)

        return TaigaProject(
            id=project_id,
            name=name,
            slug=slug,
            description=_string_or_none(payload.get("description")),
            is_kanban_activated=_maybe_bool(payload.get("is_kanban_activated")),
            owner=owner,
            raw=payload,
        )

    def _parse_status(self, payload: dict[str, Any]) -> TaigaStatus:
        status_id = _maybe_int(payload.get("id"))
        name = _string_or_none(payload.get("name"))
        slug = _string_or_none(payload.get("slug"))
        if status_id is None or not name or not slug:
            raise TaigaApiError("Unexpected Taiga status payload.", payload=payload)

        return TaigaStatus(
            id=status_id,
            name=name,
            slug=slug,
            order=_maybe_int(payload.get("order")),
            is_closed=_maybe_bool(payload.get("is_closed")),
            is_archived=_maybe_bool(payload.get("is_archived")),
            color=_string_or_none(payload.get("color")),
            raw=payload,
        )

    @staticmethod
    def _decode_response(response: httpx.Response) -> Any:
        if response.status_code == 204:
            return {}
        try:
            return response.json()
        except ValueError:
            return response.text


def _maybe_int(value: Any) -> int | None:
    try:
        if value is None:
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _string_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _maybe_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    return None


def _extract_project_slug_from_payload(payload: dict[str, Any]) -> str | None:
    project = payload.get("project_extra_info")
    if isinstance(project, dict):
        slug = _string_or_none(project.get("slug"))
        if slug:
            return slug
    return None


def _extract_project_slug_from_permalink(permalink: str | None) -> str | None:
    if not permalink or "/project/" not in permalink:
        return None
    project_path = permalink.split("/project/", 1)[1]
    parts = [part for part in project_path.split("/") if part]
    if not parts:
        return None
    return parts[0]


def _build_user_story_permalink(base_url: str, project_slug: str | None, ref: int | None) -> str | None:
    if not project_slug or ref is None:
        return None
    return f"{base_url.rstrip('/')}/project/{project_slug}/us/{ref}"
