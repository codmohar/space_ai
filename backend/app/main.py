"""FastAPI application entry point for MISSIONWISE AI."""

from __future__ import annotations

import uuid

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware

from app.api.chat import router as chat_router
from app.api.citations import router as citations_router
from app.api.documents import router as documents_router
from app.api.eval import router as eval_router
from app.api.health import router as health_router
from app.api.retrieval import router as retrieval_router
from app.api.stair import router as stair_router
from app.core.config import get_settings
from app.core.errors import (
    ApiError,
    api_error_handler,
    http_exception_handler,
    validation_exception_handler,
)

settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="Space Mission Engineering Intelligence Platform — Grounded RAG & Citation API",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def attach_request_id(request: Request, call_next):
    req_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
    request.state.request_id = req_id
    response = await call_next(request)
    response.headers["X-Request-ID"] = req_id
    return response


app.add_exception_handler(ApiError, api_error_handler)
app.add_exception_handler(HTTPException, http_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)

app.include_router(health_router)
app.include_router(documents_router)
app.include_router(retrieval_router)
app.include_router(stair_router)
app.include_router(chat_router)
app.include_router(citations_router)
app.include_router(eval_router)
