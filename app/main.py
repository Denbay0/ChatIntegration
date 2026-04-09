from __future__ import annotations

import hashlib
import hmac
import logging
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse

from app.config import Settings, load_bridge_config, setup_logging
from app.formatter import format_webhook_message, normalize_webhook_event
from app.matrix_bot import MatrixBot
from app.models import BridgeConfig, ProjectMapping, TaigaProject, TaigaStatus, TaigaUserStory
from app.taiga import TaigaApiError, TaigaClient
from app.widget import (
    EmbedSupport,
    WidgetStatusColumn,
    WidgetViewModel,
    build_widget_headers,
    build_widget_page,
    inspect_embed_support,
)
from app.widget_i18n import localize_taiga_error, tr

LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class BridgeRuntime:
    settings: Settings
    bridge_config: BridgeConfig
    taiga_client: TaigaClient
    matrix_bot: MatrixBot


def create_app() -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        settings = Settings()
        setup_logging(settings.log_level)
        bridge_config = load_bridge_config(settings.config_path)
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
        matrix_bot = MatrixBot(
            settings=settings,
            bridge_config=bridge_config,
            taiga_client=taiga_client,
        )

        runtime = BridgeRuntime(
            settings=settings,
            bridge_config=bridge_config,
            taiga_client=taiga_client,
            matrix_bot=matrix_bot,
        )
        app.state.runtime = runtime

        try:
            await matrix_bot.start()
            yield
        finally:
            await matrix_bot.stop()
            await taiga_client.close()

    app = FastAPI(title="Taiga Matrix Bridge", lifespan=lifespan)

    @app.api_route("/healthz", methods=["GET", "HEAD"])
    async def healthz(request: Request) -> JSONResponse:
        runtime = _runtime_from_request(request)
        status_code = 200 if runtime.matrix_bot.is_running else 503
        return JSONResponse(
            status_code=status_code,
            content={
                "status": "ok" if status_code == 200 else "degraded",
                "matrix_bot_running": runtime.matrix_bot.is_running,
                "project_count": len(runtime.bridge_config.projects),
            },
        )

    @app.post("/webhook/taiga/{slug}")
    @app.post("/webhook/kaiten/{slug}")
    async def taiga_webhook(
        slug: str,
        request: Request,
        x_bridge_secret: str | None = Header(default=None, alias="X-Bridge-Secret"),
        x_taiga_webhook_signature: str | None = Header(
            default=None,
            alias="X-TAIGA-WEBHOOK-SIGNATURE",
        ),
    ) -> dict[str, Any]:
        runtime = _runtime_from_request(request)
        project = runtime.bridge_config.get_project(slug)
        if project is None:
            raise HTTPException(status_code=404, detail="Unknown webhook slug")

        body = await request.body()
        _validate_webhook_auth(
            project=project,
            request=request,
            body=body,
            header_secret=x_bridge_secret,
            taiga_signature=x_taiga_webhook_signature,
            global_secret=runtime.settings.bridge_secret.get_secret_value(),
        )

        try:
            payload = await request.json()
        except Exception as exc:
            raise HTTPException(status_code=400, detail="Invalid JSON payload") from exc

        if not isinstance(payload, dict):
            raise HTTPException(status_code=400, detail="Webhook payload must be a JSON object")

        normalized_event = normalize_webhook_event(
            payload=payload,
            web_base_url=runtime.settings.taiga_base_url,
        )
        message = format_webhook_message(normalized_event)
        await runtime.matrix_bot.send_notice(project.room_id, message)

        LOGGER.info(
            "Forwarded Taiga webhook for slug=%s type=%s action=%s",
            slug,
            normalized_event.entity_type,
            normalized_event.action,
        )
        return {
            "status": "ok",
            "type": normalized_event.entity_type,
            "action": normalized_event.action,
        }

    @app.api_route("/widget/taiga/{slug}", methods=["GET", "HEAD"], response_class=HTMLResponse)
    async def taiga_widget(slug: str, request: Request) -> HTMLResponse:
        runtime = _runtime_from_request(request)
        project = runtime.bridge_config.get_project(slug)
        if project is None:
            raise HTTPException(status_code=404, detail=tr("widget_error_unknown_slug"))

        headers = build_widget_headers(runtime.settings.widget_frame_ancestors)
        view = await _build_widget_view(runtime, slug, project)
        return HTMLResponse(content=build_widget_page(view), headers=headers)

    @app.post("/widget/taiga/{slug}/task")
    async def taiga_widget_create_task(slug: str, request: Request) -> JSONResponse:
        runtime = _runtime_from_request(request)
        project = runtime.bridge_config.get_project(slug)
        if project is None:
            raise HTTPException(status_code=404, detail=tr("widget_error_unknown_slug"))

        try:
            payload = await request.json()
        except Exception as exc:
            raise HTTPException(status_code=400, detail=tr("widget_error_invalid_json")) from exc

        if not isinstance(payload, dict):
            raise HTTPException(status_code=400, detail=tr("widget_error_payload_object"))

        title = str(payload.get("title") or "").strip()
        description = str(payload.get("description") or "").strip() or None
        if not title:
            raise HTTPException(status_code=400, detail=tr("widget_error_empty_title"))

        try:
            story = await runtime.taiga_client.create_user_story(
                project=project,
                title=title,
                description=description,
            )
        except TaigaApiError as exc:
            LOGGER.warning("Widget task creation failed for slug=%s: %s payload=%s", slug, exc, exc.payload)
            raise HTTPException(
                status_code=502,
                detail=localize_taiga_error(str(exc), status_code=exc.status_code),
            ) from exc

        return JSONResponse(
            content={
                "status": "ok",
                "story": {
                    "id": story.id,
                    "ref": story.ref,
                    "subject": story.subject,
                    "permalink": story.permalink,
                    "status_name": story.status_name,
                },
            },
            headers={"Cache-Control": "no-store"},
        )

    return app


def _runtime_from_request(request: Request) -> BridgeRuntime:
    runtime = getattr(request.app.state, "runtime", None)
    if runtime is None:
        raise HTTPException(status_code=503, detail=tr("widget_error_runtime"))
    return runtime


def _validate_webhook_auth(
    project: ProjectMapping,
    request: Request,
    body: bytes,
    header_secret: str | None,
    taiga_signature: str | None,
    global_secret: str,
) -> None:
    expected_secret = project.webhook_secret or global_secret
    if taiga_signature:
        mac = hmac.new(expected_secret.encode("utf-8"), msg=body, digestmod=hashlib.sha1)
        if not hmac.compare_digest(mac.hexdigest(), taiga_signature):
            raise HTTPException(status_code=401, detail="Invalid Taiga webhook signature")
        return

    provided_secret = request.query_params.get("secret") or header_secret
    if provided_secret and hmac.compare_digest(provided_secret, expected_secret):
        return

    raise HTTPException(status_code=401, detail="Missing or invalid webhook authentication")


async def _build_widget_view(runtime: BridgeRuntime, slug: str, project: ProjectMapping) -> WidgetViewModel:
    project_slug = project.resolved_project_slug(runtime.settings.taiga_project_slug) or slug
    project_id = project.resolved_project_id(runtime.settings.taiga_project_id) or 0
    board_url = f"{runtime.settings.taiga_base_url}/project/{project_slug}/kanban"
    project_url = f"{runtime.settings.taiga_base_url}/project/{project_slug}"
    frame_ancestors = runtime.settings.widget_frame_ancestors.split()
    try:
        embed_support = await inspect_embed_support(board_url, frame_ancestors)
    except Exception as exc:
        LOGGER.warning("Widget embed probe failed for slug=%s: %s", slug, exc)
        embed_support = EmbedSupport(
            is_allowed=False,
            reason=tr("embed_reason_unknown"),
        )

    try:
        taiga_project = await runtime.taiga_client.get_project(project)
        stories = await runtime.taiga_client.list_user_stories(project, limit=40)
        statuses = await runtime.taiga_client.list_user_story_statuses(project)
        columns = _build_status_columns(stories, statuses)
        load_error = None
    except TaigaApiError as exc:
        LOGGER.warning("Widget snapshot failed for slug=%s: %s payload=%s", slug, exc, exc.payload)
        taiga_project = TaigaProject(
            id=project_id,
            name=project_slug.replace("-", " ").title(),
            slug=project_slug,
            description=tr("project_description_fallback"),
        )
        stories = []
        columns = []
        load_error = localize_taiga_error(str(exc), status_code=exc.status_code)

    return WidgetViewModel(
        slug=slug,
        project=taiga_project,
        room_id=project.room_id,
        board_url=board_url,
        project_url=project_url,
        create_url=f"/widget/taiga/{slug}/task",
        recent_stories=stories,
        columns=columns,
        embed_support=embed_support,
        bridge_ok=runtime.matrix_bot.is_running,
        load_error=load_error,
    )


def _build_status_columns(
    stories: list[TaigaUserStory],
    statuses: list[TaigaStatus],
) -> list[WidgetStatusColumn]:
    status_lookup = {status.id: status for status in statuses}
    columns: list[WidgetStatusColumn] = []

    for status in statuses:
        column_stories = [story for story in stories if story.status_id == status.id]
        column_stories.sort(
            key=lambda story: (
                story.kanban_order if story.kanban_order is not None else 10**18,
                story.modified_date or "",
            )
        )
        if column_stories or not getattr(status, "is_archived", False):
            columns.append(
                WidgetStatusColumn(
                    status=status,
                    stories=column_stories,
                    count=len(column_stories),
                )
            )

    orphaned = [story for story in stories if story.status_id not in status_lookup]
    if orphaned:
        orphaned.sort(key=lambda story: story.modified_date or "", reverse=True)
        columns.append(
            WidgetStatusColumn(
                status=TaigaStatus(
                    id=-1,
                    name="Unknown",
                    slug="unknown",
                    color="#70728F",
                ),
                stories=orphaned,
                count=len(orphaned),
            )
        )

    return columns
