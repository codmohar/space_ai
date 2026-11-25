"""Admin API routes: RBAC user management, audit logs, retrieval logs, and runtime settings."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.core.errors import ApiError
from app.models.auth import AuditLog, Role, User
from app.models.rag import RetrievalLog
from app.schemas import (
    AdminRoleUpdateRequest,
    AdminUserOut,
    AuditLogOut,
    RetrievalLogOut,
    RuntimeSettingsOut,
    RuntimeSettingsUpdateRequest,
)
from app.services.audit import record_audit_log
from app.services.auth.security import require_role

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get("/users", response_model=list[AdminUserOut])
def list_users(
    db: Session = Depends(get_db),
    _: User = Depends(require_role("admin")),
) -> list[AdminUserOut]:
    rows = db.execute(
        select(User, Role)
        .join(Role, Role.id == User.role_id)
        .order_by(User.created_at.asc())
    ).all()
    return [
        AdminUserOut(
            id=u.id,
            email=u.email,
            full_name=u.full_name,
            role=r.name,
            is_active=u.is_active,
            created_at=u.created_at,
        )
        for u, r in rows
    ]


@router.patch("/users/{user_id}/role", response_model=AdminUserOut)
def update_user_role(
    user_id: uuid.UUID,
    req: AdminRoleUpdateRequest,
    request: Request,
    db: Session = Depends(get_db),
    admin_user: User = Depends(require_role("admin")),
) -> AdminUserOut:
    target = db.get(User, user_id)
    if target is None:
        raise ApiError("USER_NOT_FOUND", "User not found.", status_code=404)

    role = db.execute(select(Role).where(Role.name == req.role)).scalar_one_or_none()
    if role is None:
        raise ApiError("ROLE_NOT_FOUND", f"Role '{req.role}' not found.", status_code=404)

    prev_role = db.get(Role, target.role_id)
    target.role_id = role.id
    if req.is_active is not None:
        target.is_active = req.is_active

    record_audit_log(
        db=db,
        action="admin.user_role_updated",
        resource_type="user",
        resource_id=str(target.id),
        user_id=admin_user.id,
        request_id=getattr(request.state, "request_id", None),
        details={
            "email": target.email,
            "previous_role": prev_role.name if prev_role else None,
            "new_role": role.name,
            "is_active": target.is_active,
        },
    )
    db.commit()
    db.refresh(target)

    return AdminUserOut(
        id=target.id,
        email=target.email,
        full_name=target.full_name,
        role=role.name,
        is_active=target.is_active,
        created_at=target.created_at,
    )


@router.get("/audit-logs", response_model=list[AuditLogOut])
def list_audit_logs(
    limit: int = 100,
    db: Session = Depends(get_db),
    _: User = Depends(require_role("admin")),
) -> list[AuditLogOut]:
    clamped = min(500, max(1, limit))
    rows = (
        db.execute(select(AuditLog).order_by(AuditLog.created_at.desc()).limit(clamped))
        .scalars()
        .all()
    )
    return [
        AuditLogOut(
            id=row.id,
            user_id=row.user_id,
            action=row.action,
            resource_type=row.resource_type,
            resource_id=row.resource_id,
            request_id=row.request_id,
            details=row.details or {},
            created_at=row.created_at,
        )
        for row in rows
    ]


@router.get("/retrieval-logs", response_model=list[RetrievalLogOut])
def list_retrieval_logs(
    limit: int = 100,
    db: Session = Depends(get_db),
    _: User = Depends(require_role("admin")),
) -> list[RetrievalLogOut]:
    clamped = min(500, max(1, limit))
    rows = (
        db.execute(select(RetrievalLog).order_by(RetrievalLog.created_at.desc()).limit(clamped))
        .scalars()
        .all()
    )
    return [
        RetrievalLogOut(
            id=row.id,
            request_id=row.request_id,
            query_text=row.query_text,
            mission_scope=row.mission_scope,
            stair_level=row.stair_level,
            top_rerank_score=row.top_rerank_score,
            confidence_category=row.confidence_category,
            abstained=row.abstained,
            latency_ms=row.latency_ms,
            embedding_model=row.embedding_model,
            reranker_model=row.reranker_model,
            llm_model=row.llm_model,
            prompt_version=row.prompt_version,
            created_at=row.created_at,
        )
        for row in rows
    ]


@router.get("/settings", response_model=RuntimeSettingsOut)
def get_runtime_settings(
    _: User = Depends(require_role("admin")),
) -> RuntimeSettingsOut:
    s = get_settings()
    return RuntimeSettingsOut(
        llm_provider=s.llm_provider,
        gemini_model=s.gemini_model,
        embedding_model=s.embedding_model,
        reranker_model=s.reranker_model,
        prompt_version=s.prompt_version,
        section_selector_mode=s.section_selector_mode,
        min_rerank_score_threshold=s.min_rerank_score_threshold,
        min_rrf_score_threshold=s.min_rrf_score_threshold,
        rate_limit_per_minute=s.rate_limit_per_minute,
        chat_rate_limit_per_minute=s.chat_rate_limit_per_minute,
        max_upload_mb=s.max_upload_mb,
        max_upload_pages=s.max_upload_pages,
    )


@router.patch("/settings", response_model=RuntimeSettingsOut)
def update_runtime_settings(
    req: RuntimeSettingsUpdateRequest,
    request: Request,
    db: Session = Depends(get_db),
    admin_user: User = Depends(require_role("admin")),
) -> RuntimeSettingsOut:
    s = get_settings()
    changed: dict[str, object] = {}
    if req.section_selector_mode is not None:
        s.section_selector_mode = req.section_selector_mode
        changed["section_selector_mode"] = req.section_selector_mode
    if req.min_rerank_score_threshold is not None:
        s.min_rerank_score_threshold = req.min_rerank_score_threshold
        changed["min_rerank_score_threshold"] = req.min_rerank_score_threshold
    if req.min_rrf_score_threshold is not None:
        s.min_rrf_score_threshold = req.min_rrf_score_threshold
        changed["min_rrf_score_threshold"] = req.min_rrf_score_threshold
    if req.prompt_version is not None:
        s.prompt_version = req.prompt_version
        changed["prompt_version"] = req.prompt_version

    record_audit_log(
        db=db,
        action="admin.runtime_settings_updated",
        resource_type="settings",
        resource_id="runtime",
        user_id=admin_user.id,
        request_id=getattr(request.state, "request_id", None),
        details=changed,
    )
    db.commit()

    return RuntimeSettingsOut(
        llm_provider=s.llm_provider,
        gemini_model=s.gemini_model,
        embedding_model=s.embedding_model,
        reranker_model=s.reranker_model,
        prompt_version=s.prompt_version,
        section_selector_mode=s.section_selector_mode,
        min_rerank_score_threshold=s.min_rerank_score_threshold,
        min_rrf_score_threshold=s.min_rrf_score_threshold,
        rate_limit_per_minute=s.rate_limit_per_minute,
        chat_rate_limit_per_minute=s.chat_rate_limit_per_minute,
        max_upload_mb=s.max_upload_mb,
        max_upload_pages=s.max_upload_pages,
    )
