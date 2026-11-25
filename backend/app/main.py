"""FastAPI application entry point for MISSIONWISE AI."""

from __future__ import annotations

from contextlib import asynccontextmanager
import uuid

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.admin import router as admin_router
from app.api.auth import router as auth_router
from app.api.chat import router as chat_router
from app.api.citations import router as citations_router
from app.api.demo import router as demo_router
from app.api.documents import router as documents_router
from app.api.eval import router as eval_router
from app.api.failures import router as failures_router
from app.api.health import router as health_router
from app.api.kg import router as kg_router
from app.api.retrieval import router as retrieval_router
from app.api.similar_failures import router as similar_failures_router
from app.api.stair import router as stair_router
from app.api.voice import router as voice_router
from app.core.config import get_settings
from app.core.database import SessionLocal
from app.core.errors import (
    ApiError,
    api_error_handler,
    http_exception_handler,
    validation_exception_handler,
)
from app.core.rate_limit import client_rate_key, rate_limiter
from app.services.auth.security import ensure_default_roles_and_users

settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI):
    try:
        with SessionLocal() as db:
            ensure_default_roles_and_users(db)
    except Exception:  # noqa: BLE001
        pass
    yield


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="Space Mission Engineering Intelligence Platform — Grounded RAG & Citation API",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def attach_request_id_and_rate_limit(request: Request, call_next):
    req_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
    request.state.request_id = req_id

    if request.url.path.startswith("/api/") and request.url.path not in ("/api/health", "/api/ready"):
        try:
            rate_limiter.check(
                client_rate_key(request, "api"),
                limit=settings.rate_limit_per_minute,
                window_seconds=60,
            )
        except ApiError as exc:
            return JSONResponse(
                status_code=exc.status_code,
                content={
                    "code": exc.code,
                    "message": exc.message,
                    "details": exc.details,
                    "request_id": req_id,
                },
                headers={"X-Request-ID": req_id},
            )

    response = await call_next(request)
    response.headers["X-Request-ID"] = req_id
    return response


app.add_exception_handler(ApiError, api_error_handler)
app.add_exception_handler(HTTPException, http_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)

app.include_router(health_router)
app.include_router(auth_router)
app.include_router(admin_router)
app.include_router(demo_router)
app.include_router(documents_router)
app.include_router(retrieval_router)
app.include_router(stair_router)
app.include_router(chat_router)
app.include_router(citations_router)
app.include_router(eval_router)
app.include_router(voice_router)
app.include_router(failures_router)
app.include_router(similar_failures_router)
app.include_router(kg_router)
