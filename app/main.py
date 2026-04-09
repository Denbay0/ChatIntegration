from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse

from app.config import Settings, load_bridge_config, setup_logging
from app.formatter import format_webhook_message, normalize_webhook_event
from app.kaiten import KaitenClient
from app.matrix_bot import MatrixBot
from app.models import BridgeConfig, ProjectMapping

LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class BridgeRuntime:
    settings: Settings
    bridge_config: BridgeConfig
    kaiten_client: KaitenClient
    matrix_bot: MatrixBot


def create_app() -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        settings = Settings()
        setup_logging(settings.log_level)
        bridge_config = load_bridge_config(settings.config_path)
        kaiten_client = KaitenClient(
            base_url=settings.kaiten_api_base_url,
            web_base_url=settings.kaiten_web_base_url,
            token=settings.kaiten_token.get_secret_value(),
        )
        matrix_bot = MatrixBot(
            settings=settings,
            bridge_config=bridge_config,
            kaiten_client=kaiten_client,
        )

        runtime = BridgeRuntime(
            settings=settings,
            bridge_config=bridge_config,
            kaiten_client=kaiten_client,
            matrix_bot=matrix_bot,
        )
        app.state.runtime = runtime

        try:
            await matrix_bot.start()
            yield
        finally:
            await matrix_bot.stop()
            await kaiten_client.close()

    app = FastAPI(title="Kaiten Matrix Bridge", lifespan=lifespan)

    @app.get("/healthz")
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

    @app.post("/webhook/kaiten/{slug}")
    async def kaiten_webhook(
        slug: str,
        request: Request,
        x_bridge_secret: str | None = Header(default=None, alias="X-Bridge-Secret"),
    ) -> dict[str, Any]:
        runtime = _runtime_from_request(request)
        project = runtime.bridge_config.get_project(slug)
        if project is None:
            raise HTTPException(status_code=404, detail="Unknown webhook slug")

        _validate_secret(
            project=project,
            request=request,
            header_secret=x_bridge_secret,
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
            web_base_url=runtime.settings.kaiten_web_base_url,
        )
        message = format_webhook_message(normalized_event)
        await runtime.matrix_bot.send_notice(project.room_id, message)

        LOGGER.info("Forwarded Kaiten webhook for slug=%s event=%s", slug, normalized_event.event_name)
        return {"status": "ok", "event": normalized_event.event_name}

    return app


def _runtime_from_request(request: Request) -> BridgeRuntime:
    runtime = getattr(request.app.state, "runtime", None)
    if runtime is None:
        raise HTTPException(status_code=503, detail="Bridge runtime is not initialized")
    return runtime


def _validate_secret(
    project: ProjectMapping,
    request: Request,
    header_secret: str | None,
    global_secret: str,
) -> None:
    provided_secret = request.query_params.get("secret") or header_secret
    expected_secret = project.webhook_secret or global_secret
    if not provided_secret or provided_secret != expected_secret:
        raise HTTPException(status_code=401, detail="Invalid bridge secret")
