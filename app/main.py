from __future__ import annotations

import hashlib
import hmac
import logging
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse

from app.config import Settings, load_bridge_config, setup_logging
from app.formatter import format_webhook_message, normalize_webhook_event
from app.matrix_bot import MatrixBot
from app.models import BridgeConfig, ProjectMapping
from app.taiga import TaigaClient

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

    return app


def _runtime_from_request(request: Request) -> BridgeRuntime:
    runtime = getattr(request.app.state, "runtime", None)
    if runtime is None:
        raise HTTPException(status_code=503, detail="Bridge runtime is not initialized")
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
