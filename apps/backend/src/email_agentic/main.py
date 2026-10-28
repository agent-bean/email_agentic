from contextlib import asynccontextmanager

import jwt
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST

from email_agentic.api.routes import router
from email_agentic.bootstrap import build_container
from email_agentic.platform.config import get_settings
from email_agentic.platform.errors import Conflict, NotFound
from email_agentic.platform.telemetry import configure


def create_app(settings=None):
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app):
        provider = configure("email-api", settings.telemetry_endpoint)
        async with build_container(settings) as container:
            app.state.container = container
            yield
        provider.shutdown()

    app = FastAPI(
        title="Email Assistant",
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/api/docs" if settings.environment == "local" else None,
        openapi_url="/api/openapi.json" if settings.environment == "local" else None,
    )
    app.state.jwt_client = (
        jwt.PyJWKClient(settings.cf_team_domain.rstrip("/") + "/cdn-cgi/access/certs", cache_keys=True)
        if settings.cf_team_domain
        else None
    )
    app.include_router(router)
    FastAPIInstrumentor.instrument_app(app, excluded_urls="health/live,metrics")

    @app.exception_handler(Conflict)
    async def conflict(request: Request, exc: Conflict):
        return JSONResponse({"detail": str(exc)}, status_code=409)

    @app.exception_handler(NotFound)
    async def not_found(request: Request, exc: NotFound):
        return JSONResponse({"detail": "Not found"}, status_code=404)

    @app.get("/health/live", include_in_schema=False)
    async def live():
        return {"status": "alive"}

    @app.get("/health/ready", include_in_schema=False)
    async def ready(request: Request):
        row = await request.app.state.container.db.one(
            "SELECT EXISTS(SELECT 1 FROM schema_migrations WHERE name='001-foundation.sql') AND to_regclass('checkpoints') IS NOT NULL AS ready"
        )
        if not row["ready"]:
            return JSONResponse({"status": "migration_required"}, status_code=503)
        return {"status": "ready"}

    @app.get("/metrics", include_in_schema=False)
    async def metrics():
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

    return app


def app_factory():
    return create_app()
