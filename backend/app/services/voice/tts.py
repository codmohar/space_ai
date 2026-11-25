"""Optional Piper TTS synthesizer with clean browser SpeechSynthesis fallback."""

from __future__ import annotations

import logging
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Optional

from app.core.config import get_settings

logger = logging.getLogger(__name__)


@dataclass
class SynthesisResult:
    audio_bytes: Optional[bytes]
    mime_type: str
    used_fallback: bool
    text: str


class TTSService:
    def __init__(self, binary_path: str = "piper", voice_path: str = "") -> None:
        self.binary_path = binary_path
        self.voice_path = Path(voice_path) if voice_path else None

    def is_available(self) -> bool:
        return bool(
            self.voice_path
            and self.voice_path.exists()
            and shutil.which(self.binary_path) is not None
        )

    def synthesize(self, text: str) -> SynthesisResult:
        clean = text.strip()
        if not clean or not self.is_available():
            return SynthesisResult(
                audio_bytes=None,
                mime_type="application/json",
                used_fallback=True,
                text=clean,
            )

        try:
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=True) as tmp:
                proc = subprocess.run(
                    [
                        self.binary_path,
                        "--model",
                        str(self.voice_path),
                        "--output_file",
                        tmp.name,
                    ],
                    input=clean.encode("utf-8"),
                    capture_output=True,
                    timeout=30,
                    check=True,
                )
                _ = proc
                wav_bytes = Path(tmp.name).read_bytes()
                return SynthesisResult(
                    audio_bytes=wav_bytes,
                    mime_type="audio/wav",
                    used_fallback=False,
                    text=clean,
                )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Piper TTS synthesis failed, falling back to browser SpeechSynthesis: %s", exc)
            return SynthesisResult(
                audio_bytes=None,
                mime_type="application/json",
                used_fallback=True,
                text=clean,
            )


@lru_cache(maxsize=1)
def get_tts_service() -> TTSService:
    settings = get_settings()
    return TTSService(
        binary_path=settings.piper_binary_path,
        voice_path=settings.piper_voice_path,
    )
