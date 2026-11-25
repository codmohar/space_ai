"""Sarvam AI Voice Client for Speech-to-Text (STT) and Text-to-Speech (TTS).

Supports:
- STT: Saarika / Saaras models (REST POST https://api.sarvam.ai/speech-to-text)
- TTS: Bulbul models (REST POST https://api.sarvam.ai/text-to-speech)
Handles text segmentation for TTS (>500 character inputs) and audio reassembly.
"""

from __future__ import annotations

import base64
import logging
import re
from typing import List, Optional, Tuple

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)

SARVAM_STT_ENDPOINT = "https://api.sarvam.ai/speech-to-text"
SARVAM_TTS_ENDPOINT = "https://api.sarvam.ai/text-to-speech"
MAX_TTS_INPUT_LENGTH = 480


class SarvamVoiceClient:
    """Client for Sarvam AI Voice STT and TTS services."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        stt_model: Optional[str] = None,
        tts_model: Optional[str] = None,
        language_code: Optional[str] = None,
        speaker: Optional[str] = None,
        timeout_seconds: float = 25.0,
    ) -> None:
        settings = get_settings()
        self.api_key = (api_key or getattr(settings, "sarvam_api_key", "")).strip()
        self.stt_model = stt_model or getattr(settings, "sarvam_stt_model", "saarika:v1")
        self.tts_model = tts_model or getattr(settings, "sarvam_tts_model", "bulbul:v1")
        self.language_code = language_code or getattr(settings, "sarvam_language_code", "en-IN")
        self.speaker = speaker or getattr(settings, "sarvam_speaker", "meera")
        self.timeout = timeout_seconds

    def is_configured(self) -> bool:
        """Check if Sarvam API key is available."""
        settings = get_settings()
        key = self.api_key or getattr(settings, "sarvam_api_key", "").strip()
        return bool(key)

    def _get_api_key(self) -> str:
        settings = get_settings()
        return (self.api_key or getattr(settings, "sarvam_api_key", "")).strip()

    def transcribe(
        self,
        audio_bytes: bytes,
        filename: str = "audio.wav",
        language_code: Optional[str] = None,
        prompt: Optional[str] = None,
    ) -> Tuple[Optional[str], Optional[str]]:
        """Transcribe audio bytes using Sarvam STT.

        Returns (transcript_text, error_message).
        """
        api_key = self._get_api_key()
        if not api_key:
            return None, "SARVAM_API_KEY is not configured"

        if not audio_bytes:
            return "", None

        mime_type = "audio/wav"
        if filename.endswith(".webm"):
            mime_type = "audio/webm"
        elif filename.endswith(".mp3"):
            mime_type = "audio/mp3"
        elif filename.endswith(".ogg"):
            mime_type = "audio/ogg"

        headers = {
            "api-subscription-key": api_key,
        }
        data = {
            "model": self.stt_model,
            "language_code": language_code or self.language_code,
        }
        if prompt:
            data["prompt"] = prompt[:200]

        files = {
            "file": (filename, audio_bytes, mime_type),
        }

        try:
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.post(
                    SARVAM_STT_ENDPOINT,
                    headers=headers,
                    data=data,
                    files=files,
                )

                if resp.status_code != 200:
                    err_msg = f"Sarvam STT failed HTTP {resp.status_code}: {resp.text[:300]}"
                    logger.warning(err_msg)
                    return None, err_msg

                body = resp.json()
                transcript = body.get("transcript", "")
                if not transcript and "results" in body:
                    results = body["results"]
                    if isinstance(results, list) and results:
                        transcript = " ".join(
                            r.get("transcript", "") for r in results if isinstance(r, dict)
                        ).strip()

                return transcript.strip(), None
        except Exception as exc:  # noqa: BLE001
            logger.warning("Sarvam STT request error: %s", exc)
            return None, str(exc)

    def synthesize(
        self,
        text: str,
        speaker: Optional[str] = None,
        target_language_code: Optional[str] = None,
        pace: Optional[float] = None,
        sample_rate: Optional[int] = None,
    ) -> Tuple[Optional[bytes], str, Optional[str]]:
        """Synthesize text to speech using Sarvam TTS.

        Returns (audio_bytes, mime_type, error_message).
        """
        api_key = self._get_api_key()
        if not api_key:
            return None, "application/json", "SARVAM_API_KEY is not configured"

        clean_text = text.strip()
        if not clean_text:
            return None, "application/json", "Empty text provided"

        settings = get_settings()
        chosen_speaker = speaker or self.speaker
        lang = target_language_code or self.language_code
        rate = sample_rate or getattr(settings, "sarvam_sample_rate", 16000)
        speed = pace or getattr(settings, "sarvam_pace", 1.05)

        # Split text into segments <= 480 characters to comply with Sarvam input limits
        inputs = self._chunk_text(clean_text, MAX_TTS_INPUT_LENGTH)
        if not inputs:
            return None, "application/json", "No valid text chunks to synthesize"

        headers = {
            "api-subscription-key": api_key,
            "Content-Type": "application/json",
        }

        payload = {
            "inputs": inputs,
            "target_language_code": lang,
            "speaker": chosen_speaker,
            "pitch": 0,
            "pace": speed,
            "loudness": getattr(settings, "sarvam_loudness", 1.5),
            "speech_sample_rate": rate,
            "enable_preprocessing": True,
            "model": self.tts_model,
        }

        try:
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.post(
                    SARVAM_TTS_ENDPOINT,
                    headers=headers,
                    json=payload,
                )

                if resp.status_code != 200:
                    err_msg = f"Sarvam TTS failed HTTP {resp.status_code}: {resp.text[:300]}"
                    logger.warning(err_msg)
                    return None, "application/json", err_msg

                body = resp.json()
                audios = body.get("audios", [])
                if not audios or not isinstance(audios, list):
                    return None, "application/json", "Sarvam TTS returned empty audio list"

                # Decode base64 audio chunks
                decoded_chunks: List[bytes] = []
                for b64 in audios:
                    if b64:
                        decoded_chunks.append(base64.b64decode(b64))

                if not decoded_chunks:
                    return None, "application/json", "Failed to decode Sarvam audio output"

                # If single chunk, return directly; if multiple chunks, concatenate WAV PCM or chunks
                final_audio = self._combine_wav_chunks(decoded_chunks)
                return final_audio, "audio/wav", None
        except Exception as exc:  # noqa: BLE001
            logger.warning("Sarvam TTS request error: %s", exc)
            return None, "application/json", str(exc)

    @staticmethod
    def _chunk_text(text: str, max_len: int) -> List[str]:
        """Split text into sentence-aware chunks of at most max_len characters."""
        if len(text) <= max_len:
            return [text]

        sentences = re.split(r"(?<=[.!?])\s+", text)
        chunks: List[str] = []
        current: List[str] = []
        curr_len = 0

        for s in sentences:
            s_clean = s.strip()
            if not s_clean:
                continue
            if curr_len + len(s_clean) + 1 > max_len and current:
                chunks.append(" ".join(current))
                current = [s_clean]
                curr_len = len(s_clean)
            else:
                current.append(s_clean)
                curr_len += len(s_clean) + 1

        if current:
            chunks.append(" ".join(current))

        # In case a single chunk is still > max_len, hard-split it
        final_chunks: List[str] = []
        for c in chunks:
            if len(c) <= max_len:
                final_chunks.append(c)
            else:
                words = c.split()
                sub = ""
                for w in words:
                    if len(sub) + len(w) + 1 > max_len:
                        if sub:
                            final_chunks.append(sub.strip())
                        sub = w
                    else:
                        sub = f"{sub} {w}" if sub else w
                if sub:
                    final_chunks.append(sub.strip())

        return final_chunks or [text[:max_len]]

    @staticmethod
    def _combine_wav_chunks(chunks: List[bytes]) -> bytes:
        """Combine multiple WAV byte segments into a single valid WAV file if possible."""
        if len(chunks) == 1:
            return chunks[0]

        try:
            import io
            import wave

            output_io = io.BytesIO()
            with wave.open(output_io, "wb") as outfile:
                for idx, chunk in enumerate(chunks):
                    with wave.open(io.BytesIO(chunk), "rb") as infile:
                        if idx == 0:
                            outfile.setparams(infile.getparams())
                        outfile.writeframes(infile.readframes(infile.getnframes()))

            return output_io.getvalue()
        except Exception:
            # If wave concatenation fails (e.g. non-WAV headers), return first or raw joined
            return chunks[0]
