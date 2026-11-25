"""Demo Mode walkthrough, cache pre-warming, and offline-tolerant query endpoint."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.auth import User
from app.schemas import (
    DemoAskRequest,
    DemoAskResponse,
    DemoPrewarmResponse,
    DemoWalkthroughResponse,
)
from app.services.audit import record_audit_log
from app.services.auth.security import get_optional_user
from app.services.demo_cache import (
    get_demo_walkthrough_steps,
    load_demo_cache_raw,
    lookup_cached_demo_answer,
    prewarm_demo_cache,
)
from app.services.rag.service import RAGService

router = APIRouter(prefix="/api/demo", tags=["demo"])


@router.get("/walkthrough", response_model=DemoWalkthroughResponse)
def get_walkthrough(db: Session = Depends(get_db)) -> DemoWalkthroughResponse:
    raw = load_demo_cache_raw()
    entries = raw.get("entries") or {}
    steps = get_demo_walkthrough_steps(db)
    return DemoWalkthroughResponse(
        enabled=True,
        cache_warmed=len(entries) > 0,
        cached_query_count=len(entries),
        generated_at=raw.get("generated_at"),
        steps=steps,
    )


@router.post("/prewarm", response_model=DemoPrewarmResponse)
def prewarm_demo(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_optional_user),
) -> DemoPrewarmResponse:
    summary = prewarm_demo_cache(db)
    record_audit_log(
        db=db,
        action="demo.prewarm",
        resource_type="demo_cache",
        resource_id="default",
        user_id=current_user.id if current_user else None,
        request_id=getattr(request.state, "request_id", None),
        details=summary,
    )
    db.commit()
    return DemoPrewarmResponse(
        status=summary["status"],
        cached_queries=int(summary["cached_queries"]),
        generated_at=summary["generated_at"],
    )


@router.post("/ask", response_model=DemoAskResponse)
def demo_ask(
    req: DemoAskRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> DemoAskResponse:
    request_id = getattr(request.state, "request_id", f"demo-{uuid.uuid4().hex[:8]}")
    if req.use_cache:
        cached = lookup_cached_demo_answer(db=db, query=req.query, mission=req.mission)
        if cached is not None:
            return DemoAskResponse(cache_hit=True, response=cached)

    rag = RAGService()
    resp = rag.chat_and_persist(
        db=db,
        query=req.query,
        request_id=request_id,
        mission=req.mission,
        selector_mode=req.selector_mode,
    )
    return DemoAskResponse(cache_hit=False, response=resp)
