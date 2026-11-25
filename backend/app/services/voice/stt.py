"""faster-whisper STT service with aerospace vocabulary prompting and fallback detection."""

from __future__ import annotations

import logging
import tempfile
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Optional

from app.core.config import get_settings

logger = logging.getLogger(__name__)


@dataclass
class TranscriptionResult:
    text: str
    language: str
    duration_s: float
    used_fallback: bool = False
    error: Optional[str] = None


class STTService:
    def __init__(
        self,
        model_size: str,
        device: str = "cpu",
        compute_type: str = "int8",
        download_root: Optional[str] = None,
        enabled: bool = True,
    ) -> None:
        self.model_size = model_size
        self.device = device
        self.compute_type = compute_type
        self.download_root = download_root
        self.enabled = enabled
        self._model = None
        self._load_error: Optional[str] = None

    def _ensure_model(self):
        if not self.enabled:
            self._load_error = "Server STT disabled by configuration"
            return None
        if self._model is not None:
            return self._model
        if self._load_error is not None:
            return None
        try:
            from faster_whisper import WhisperModel

            self._model = WhisperModel(
                self.model_size,
                device=self.device,
                compute_type=self.compute_type,
                download_root=self.download_root,
            )
            return self._model
        except Exception as exc:  # noqa: BLE001
            logger.warning("faster-whisper unavailable, browser Web Speech fallback active: %s", exc)
            self._load_error = str(exc)
            return None

    def is_available(self) -> bool:
        return self.enabled and self._load_error is None

    def transcribe_bytes(
        self,
        audio_bytes: bytes,
        initial_prompt: str,
        suffix: str = ".webm",
    ) -> TranscriptionResult:
        if not audio_bytes:
            return TranscriptionResult(text="", language="en", duration_s=0.0)

        model = self._ensure_model()
        if model is None:
            return TranscriptionResult(
                text="",
                language="en",
                duration_s=0.0,
                used_fallback=True,
                error=self._load_error or "faster-whisper unavailable",
            )

        with tempfile.NamedTemporaryFile(suffix=suffix, delete=True) as tmp:
            tmp.write(audio_bytes)
            tmp.flush()
            segments, info = model.transcribe(
                tmp.name,
                language="en",
                initial_prompt=initial_prompt,
                vad_filter=True,
                beam_size=3,
            )
            text = " ".join(seg.text.strip() for seg in segments).strip()
            return TranscriptionResult(
                text=text,
                language=getattr(info, "language", "en") or "en",
                duration_s=round(float(getattr(info, "duration", 0.0) or 0.0), 2),
                used_fallback=False,
            )


@lru_cache(maxsize=1)
def get_stt_service() -> STTService:
    settings = get_settings()
    settings.model_cache_dir.mkdir(parents=True, exist_ok=True)
    return STTService(
        model_size=settings.whisper_model_size,
        device=settings.whisper_device,
        compute_type=settings.whisper_compute_type,
        download_root=str(settings.model_cache_dir / "whisper"),
        enabled=settings.enable_server_stt,
    )
