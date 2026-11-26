"""Voice API routes: capabilities, transcribe, synthesize, and WS /api/voice/stream."""

from __future__ import annotations

import asyncio
import base64
import json
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, File, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database import SessionLocal, get_db
from app.services.audit import record_audit_log
from app.services.rag.service import RAGService
from app.services.voice.aerospace_vocab import build_aerospace_vocab_prompt
from app.services.voice.stt import get_stt_service
from app.services.voice.tts import get_tts_service

router = APIRouter(prefix="/api/voice", tags=["voice"])


class SynthesizeRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=4000)


@router.get("/capabilities")
def voice_capabilities() -> dict:
    stt = get_stt_service()
    tts = get_tts_service()
    return {
        "server_stt_available": stt.is_available(),
        "server_stt_engine": stt.active_engine,
        "server_tts_available": tts.is_available(),
        "server_tts_engine": tts.active_engine,
    }


@router.post("/transcribe")
async def transcribe_audio(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> dict:
    audio_bytes = await file.read()
    stt = get_stt_service()
    vocab_prompt = build_aerospace_vocab_prompt(db)
    suffix = ".wav" if (file.filename or "").lower().endswith(".wav") else ".webm"
    res = stt.transcribe_bytes(audio_bytes, initial_prompt=vocab_prompt, suffix=suffix)
    return {
        "text": res.text,
        "language": res.language,
        "duration_s": res.duration_s,
        "used_fallback": res.used_fallback,
        "error": res.error,
        "engine": getattr(res, "engine", "faster-whisper"),
        "vocab_prompt": vocab_prompt,
    }


@router.post("/synthesize")
def synthesize_speech(req: SynthesizeRequest) -> Response:
    tts = get_tts_service()
    res = tts.synthesize(req.text)
    if res.audio_bytes and not res.used_fallback:
        return Response(content=res.audio_bytes, media_type=res.mime_type)
    return JSONResponse(
        status_code=200,
        content={
            "mode": "browser_speech_synthesis",
            "used_fallback": True,
            "text": res.text,
        },
    )


def get_rag_service() -> RAGService:
    return RAGService()


@router.websocket("/stream")
async def voice_stream_ws(websocket: WebSocket) -> None:
    await websocket.accept()

    audio_buffer = bytearray()
    conversation_id: Optional[uuid.UUID] = None
    mission: Optional[str] = None
    selector_mode: Optional[str] = None
    document_ids: Optional[list[uuid.UUID]] = None
    active_turn_id = 0
    active_task: Optional[asyncio.Task] = None

    stt = get_stt_service()
    tts = get_tts_service()
    rag = get_rag_service()

    async def process_query_turn(turn_id: int, transcript_text: str) -> None:
        nonlocal conversation_id
        db = SessionLocal()
        try:
            request_id = f"ws-{uuid.uuid4()}"
            chat_res = await asyncio.to_thread(
                rag.chat_and_persist,
                db=db,
                query=transcript_text,
                request_id=request_id,
                conversation_id=conversation_id,
                mission=mission,
                document_ids=document_ids,
                selector_mode=selector_mode,
                allowed_classifications=["public", "internal", "restricted"],
            )
            if turn_id != active_turn_id:
                return  # Barge-in occurred before response finished

            record_audit_log(
                db=db,
                action="rag.chat.voice",
                resource_type="conversation",
                resource_id=str(chat_res.conversation_id),
                request_id=request_id,
                details={
                    "confidence": chat_res.confidence,
                    "abstained": chat_res.abstained,
                    "citation_count": len(chat_res.citations),
                    "stair_level": chat_res.stair_level,
                },
            )
            db.commit()

            conversation_id = chat_res.conversation_id
            await websocket.send_json(
                {
                    "type": "answer",
                    "turn_id": turn_id,
                    "chat_response": chat_res.model_dump(mode="json"),
                    "spoken_text": chat_res.spoken_text,
                    "citations": [c.model_dump(mode="json") for c in chat_res.citations],
                    "claims": [c.model_dump(mode="json") for c in chat_res.claims],
                    "confidence": chat_res.confidence,
                    "abstained": chat_res.abstained,
                }
            )

            tts_res = await asyncio.to_thread(tts.synthesize, chat_res.spoken_text)
            if turn_id != active_turn_id:
                return

            if tts_res.audio_bytes and not tts_res.used_fallback:
                await websocket.send_json(
                    {
                        "type": "tts_audio",
                        "turn_id": turn_id,
                        "mime": tts_res.mime_type,
                        "audio_b64": base64.b64encode(tts_res.audio_bytes).decode("ascii"),
                    }
                )
            else:
                await websocket.send_json(
                    {
                        "type": "tts_fallback",
                        "turn_id": turn_id,
                        "mode": "browser_speech_synthesis",
                        "text": chat_res.spoken_text,
                    }
                )
        except asyncio.CancelledError:
            return
        except Exception as exc:  # noqa: BLE001
            if turn_id == active_turn_id:
                await websocket.send_json(
                    {
                        "type": "error",
                        "turn_id": turn_id,
                        "code": "VOICE_PIPELINE_ERROR",
                        "message": str(exc),
                    }
                )
        finally:
            db.close()

    try:
        while True:
            message = await websocket.receive()
            if message.get("type") == "websocket.disconnect":
                break

            if message.get("bytes") is not None:
                audio_buffer.extend(message["bytes"])
                continue

            raw_text = message.get("text")
            if not raw_text:
                continue

            try:
                payload = json.loads(raw_text)
            except json.JSONDecodeError:
                await websocket.send_json({"type": "error", "message": "Invalid JSON frame."})
                continue

            msg_type = payload.get("type")

            if msg_type == "config":
                raw_cid = payload.get("conversation_id")
                conversation_id = uuid.UUID(raw_cid) if raw_cid else None
                mission = payload.get("mission") or None
                selector_mode = payload.get("selector_mode") or None
                raw_doc_ids = payload.get("document_ids") or []
                document_ids = [uuid.UUID(d) for d in raw_doc_ids] if raw_doc_ids else None
                await websocket.send_json({"type": "configured", "conversation_id": raw_cid})

            elif msg_type == "audio_chunk":
                b64 = payload.get("data_b64", "")
                if b64:
                    audio_buffer.extend(base64.b64decode(b64))

            elif msg_type == "interrupt":
                active_turn_id += 1
                audio_buffer.clear()
                if active_task and not active_task.done():
                    active_task.cancel()
                await websocket.send_json({"type": "interrupted", "turn_id": active_turn_id})

            elif msg_type == "end_of_speech":
                raw_audio = bytes(audio_buffer)
                audio_buffer.clear()
                active_turn_id += 1
                my_turn = active_turn_id

                db = SessionLocal()
                try:
                    vocab_prompt = build_aerospace_vocab_prompt(db)
                finally:
                    db.close()

                suffix = payload.get("suffix", ".webm")
                stt_res = await asyncio.to_thread(
                    stt.transcribe_bytes, raw_audio, vocab_prompt, suffix
                )

                if stt_res.used_fallback:
                    await websocket.send_json(
                        {
                            "type": "stt_fallback",
                            "turn_id": my_turn,
                            "reason": stt_res.error or f"{stt.active_engine} unavailable",
                        }
                    )
                    continue

                if not stt_res.text.strip():
                    await websocket.send_json(
                        {"type": "transcript", "turn_id": my_turn, "is_final": True, "text": ""}
                    )
                    continue

                await websocket.send_json(
                    {
                        "type": "transcript",
                        "turn_id": my_turn,
                        "is_final": True,
                        "text": stt_res.text,
                    }
                )
                active_task = asyncio.create_task(process_query_turn(my_turn, stt_res.text))

            elif msg_type == "transcript_text":
                # Used by browser Web Speech API fallback — still routes through ONE RAGService
                text = (payload.get("text") or "").strip()
                if not text:
                    continue
                active_turn_id += 1
                my_turn = active_turn_id
                await websocket.send_json(
                    {
                        "type": "transcript",
                        "turn_id": my_turn,
                        "is_final": True,
                        "text": text,
                    }
                )
                active_task = asyncio.create_task(process_query_turn(my_turn, text))

    except WebSocketDisconnect:
        if active_task and not active_task.done():
            active_task.cancel()
