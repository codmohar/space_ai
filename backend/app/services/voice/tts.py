"""Text-to-Speech (TTS) synthesizer supporting Sarvam AI (primary), Piper TTS, and browser fallback."""

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
from app.services.voice.sarvam import SarvamVoiceClient

logger = logging.getLogger(__name__)


@dataclass
class SynthesisResult:
    audio_bytes: Optional[bytes]
    mime_type: str
    used_fallback: bool
    text: str
    engine: str = "sarvam"


class TTSService:
    def __init__(
        self,
        binary_path: str = "piper",
        voice_path: str = "",
        sarvam_client: Optional[SarvamVoiceClient] = None,
    ) -> None:
        self.binary_path = binary_path
        self.voice_path = Path(voice_path) if voice_path else None
        self.sarvam = sarvam_client or SarvamVoiceClient()

    def is_available(self) -> bool:
        if self.sarvam.is_configured():
            return True
        return bool(
            self.voice_path
            and self.voice_path.exists()
            and shutil.which(self.binary_path) is not None
        )

    @property
    def active_engine(self) -> str:
        settings = get_settings()
        if self.sarvam.is_configured() and getattr(settings, "prefer_sarvam_voice", True):
            return "sarvam"
        if bool(
            self.voice_path
            and self.voice_path.exists()
            and shutil.which(self.binary_path) is not None
        ):
            return "piper"
        return "browser_speech_synthesis"

    def synthesize(self, text: str) -> SynthesisResult:
        clean = text.strip()
        if not clean:
            return SynthesisResult(
                audio_bytes=None,
                mime_type="application/json",
                used_fallback=True,
                text="",
                engine=self.active_engine,
            )

        settings = get_settings()

        # 1. Attempt Sarvam TTS if configured
        if self.sarvam.is_configured() and getattr(settings, "prefer_sarvam_voice", True):
            audio_bytes, mime, err = self.sarvam.synthesize(
                text=clean,
                speaker=getattr(settings, "sarvam_speaker", "meera"),
                target_language_code=getattr(settings, "sarvam_language_code", "en-IN"),
            )
            if not err and audio_bytes:
                return SynthesisResult(
                    audio_bytes=audio_bytes,
                    mime_type=mime,
                    used_fallback=False,
                    text=clean,
                    engine="sarvam",
                )
            logger.warning("Sarvam TTS synthesis failed, trying Piper/browser fallback: %s", err)

        # 2. Attempt Piper TTS if available
        if (
            self.voice_path
            and self.voice_path.exists()
            and shutil.which(self.binary_path) is not None
        ):
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
                        engine="piper",
                    )
            except Exception as exc:  # noqa: BLE001
                logger.warning("Piper TTS synthesis failed, falling back to browser SpeechSynthesis: %s", exc)

        # 3. Clean fallback to browser SpeechSynthesis
        return SynthesisResult(
            audio_bytes=None,
            mime_type="application/json",
            used_fallback=True,
            text=clean,
            engine="browser_speech_synthesis",
        )


@lru_cache(maxsize=1)
def get_tts_service() -> TTSService:
    settings = get_settings()
    return TTSService(
        binary_path=settings.piper_binary_path,
        voice_path=settings.piper_voice_path,
        sarvam_client=SarvamVoiceClient(),
    )
