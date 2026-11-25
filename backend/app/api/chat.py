"""Chat endpoint orchestrating the shared RAG service."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas import ChatRequest, ChatResponse
from app.services.rag.service import RAGService

router = APIRouter(prefix="/api", tags=["chat"])


@router.post("/chat", response_model=ChatResponse)
def chat_endpoint(
    req: ChatRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> ChatResponse:
    request_id = getattr(request.state, "request_id", "unknown")
    service = RAGService()
    return service.chat_and_persist(
        db=db,
        query=req.query,
        request_id=request_id,
        conversation_id=req.conversation_id,
        mission=req.mission,
        document_ids=req.document_ids,
    )
