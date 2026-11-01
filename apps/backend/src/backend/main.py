from contextlib import asynccontextmanager
from pathlib import Path
from uuid import uuid4

from agil_shared.errors import DomainError
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from backend.api import demo, operator, payments, webhooks
from backend.config import get_settings
from backend.integrations.observability import configure_logging
from backend.runtime import Runtime


def create_app(settings=None):
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app):
        configure_logging()
        runtime = Runtime(settings)
        app.state.runtime = runtime
        app.state.operator_central = runtime.operator_central
        app.state.campaign_service = runtime.campaigns
        app.state.identity_service = runtime.identity
        app.state.demo_service = runtime.demo
        try:
            yield
        finally:
            await runtime.close()

    app = FastAPI(title="Proyecto Ágil", lifespan=lifespan, docs_url=None, redoc_url=None)
    app.state.settings = settings
    operator.configure_operator(app, settings)

    @app.middleware("http")
    async def safety_headers(request: Request, call_next):
        request.state.correlation_id = str(uuid4())
        runtime = getattr(app.state, "runtime", None)
        if runtime and request.method not in {"GET", "HEAD"} and request.url.path not in {"/api/demo/reset", "/login", "/logout"}:
            try:
                if runtime.maintenance():
                    return JSONResponse({"code": "maintenance", "message": "Demo en restauración.", "retryable": True,
                                         "correlation_id": request.state.correlation_id}, status_code=429 if request.url.path == "/webhooks/chatwoot" else 503)
            except SQLAlchemyError:
                return JSONResponse({"code": "database_unavailable", "message": "Base operativa no disponible.", "retryable": True,
                                     "correlation_id": request.state.correlation_id}, status_code=429 if request.url.path == "/webhooks/chatwoot" else 503)
        response = await call_next(request)
        # Native login form POSTs need their same-origin Origin header.
        # https://fetch.spec.whatwg.org/#append-a-request-origin-header
        referrer_policy = "same-origin" if request.url.path == "/login" else "no-referrer"
        response.headers.update({"Cache-Control": "no-store", "Referrer-Policy": referrer_policy,
                                 "X-Content-Type-Options": "nosniff", "X-Correlation-ID": request.state.correlation_id})
        return response

    @app.exception_handler(DomainError)
    async def domain_error(request, exc):
        return JSONResponse(exc.as_dict(request.state.correlation_id), status_code=exc.status)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        return JSONResponse({"code": "invalid_request", "message": "Solicitud inválida.", "retryable": False,
                             "correlation_id": request.state.correlation_id}, status_code=422)

    @app.exception_handler(SQLAlchemyError)
    async def database_error(request, exc):
        return JSONResponse({"code": "database_unavailable", "message": "Base de datos no disponible.", "retryable": True,
                             "correlation_id": request.state.correlation_id}, status_code=429 if request.url.path == "/webhooks/chatwoot" else 503)

    @app.get("/health")
    async def health():
        return {"status": "ok", "service": "backend"}

    @app.get("/ready")
    async def ready(request: Request):
        runtime = request.app.state.runtime
        with runtime.sessions() as session:
            session.execute(text("SELECT 1 FROM verified_context LIMIT 1"))
            session.execute(text("SELECT 1 FROM checkpoints LIMIT 1"))
        if runtime.maintenance():
            raise DomainError("maintenance", "Demo en restauración.", 503, True)
        await runtime.operator_central.request("GET", "/debts", params={"page_size": 1})
        return {"status": "ready", "service": "backend"}

    app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")
    for module in (operator, payments, webhooks, demo):
        app.include_router(module.router)
    return app


app = create_app()
