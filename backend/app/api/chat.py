"""Chat endpoint orchestrating the shared RAG service."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.core.rate_limit import client_rate_key, rate_limiter
from app.models.auth import User
from app.schemas import ChatRequest, ChatResponse
from app.services.audit import record_audit_log
from app.services.auth.security import get_optional_user
from app.services.rag.service import RAGService

router = APIRouter(prefix="/api", tags=["chat"])


@router.post("/chat", response_model=ChatResponse)
def chat_endpoint(
    req: ChatRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_optional_user),
) -> ChatResponse:
    settings = get_settings()
    rate_limiter.check(
        client_rate_key(request, "chat"),
        limit=settings.chat_rate_limit_per_minute,
        window_seconds=60,
    )
    request_id = getattr(request.state, "request_id", "unknown")
    allowed_classifications = ["public"]
    if current_user:
        role_name = getattr(current_user.role, "name", "")
        if role_name == "admin":
            allowed_classifications = ["public", "internal", "restricted"]
        elif role_name == "engineer":
            allowed_classifications = ["public", "internal"]

    service = RAGService()
    response = service.chat_and_persist(
        db=db,
        query=req.query,
        request_id=request_id,
        conversation_id=req.conversation_id,
        mission=req.mission,
        document_ids=req.document_ids,
        selector_mode=req.selector_mode,
        allowed_classifications=allowed_classifications,
    )
    record_audit_log(
        db=db,
        action="rag.chat",
        resource_type="conversation",
        resource_id=str(response.conversation_id),
        user_id=current_user.id if current_user else None,
        request_id=request_id,
        details={
            "confidence": response.confidence,
            "abstained": response.abstained,
            "citation_count": len(response.citations),
            "stair_level": response.stair_level,
        },
    )
    db.commit()
    return response
