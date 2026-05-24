"""Speech-to-text using faster-whisper."""

from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np
from faster_whisper import WhisperModel

from src.config import SttConfig
from src.vad.silero import SpeechSegment

logger = logging.getLogger("voice_coder.stt")


@dataclass
class TranscriptResult:
    text: str
    language: str
    duration_sec: float


class WhisperTranscriber:
    """STT via local faster-whisper or Cloud API (OpenAI/Groq) with lazy loading."""

    def __init__(self, config: SttConfig) -> None:
        self._config = config
        self._model: WhisperModel | None = None

    def _ensure_model(self) -> WhisperModel:
        if self._model is None:
            device = self._config.device
            if device == "auto":
                import torch

                device = "cuda" if torch.cuda.is_available() else "cpu"
            logger.info(
                "Loading Whisper model '%s' on %s (%s)",
                self._config.model_size,
                device,
                self._config.compute_type,
            )
            self._model = WhisperModel(
                self._config.model_size,
                device=device,
                compute_type=self._config.compute_type,
            )
        return self._model

    def warmup(self) -> None:
        """Preload model if local, otherwise verify api key."""
        if self._config.provider in ("openai", "groq"):
            logger.info("Cloud STT active (%s)", self._config.provider)
            # Verify key
            key = self._get_api_key()
            if not key:
                logger.warning("Cloud STT key not found in environment!")
        else:
            self._ensure_model()
            logger.info("Local Whisper model ready")

    def _get_api_key(self) -> str:
        import os
        if self._config.provider == "groq":
            return os.environ.get("GROQ_API_KEY", "") or os.environ.get("OPENAI_API_KEY", "")
        return os.environ.get("OPENAI_API_KEY", "")

    def _get_endpoint(self) -> str:
        if self._config.provider == "groq":
            return "https://api.groq.com/openai/v1/audio/transcriptions"
        return "https://api.openai.com/v1/audio/transcriptions"

    def _transcribe_cloud(self, segment: SpeechSegment) -> str:
        import io
        import struct
        import urllib.request
        import urllib.error
        import uuid
        import json

        audio = segment.audio.astype(np.float32)
        if audio.max() > 1.0 or audio.min() < -1.0:
            peak = max(abs(audio.min()), abs(audio.max()), 1e-6)
            audio = audio / peak

        # Convert to 16-bit signed PCM WAV bytes
        pcm_data = (audio * 32767.0).clip(-32768.0, 32767.0).astype(np.int16)
        
        buf = io.BytesIO()
        num_samples = len(pcm_data)
        data_size = num_samples * 2
        
        buf.write(b"RIFF")
        buf.write(struct.pack("<I", 36 + data_size))
        buf.write(b"WAVE")
        buf.write(b"fmt ")
        buf.write(struct.pack("<I", 16))
        buf.write(struct.pack("<H", 1))
        buf.write(struct.pack("<H", 1))
        buf.write(struct.pack("<I", segment.sample_rate))
        buf.write(struct.pack("<I", segment.sample_rate * 2))
        buf.write(struct.pack("<H", 2))
        buf.write(struct.pack("<H", 16))
        buf.write(b"data")
        buf.write(struct.pack("<I", data_size))
        buf.write(pcm_data.tobytes())
        
        wav_bytes = buf.getvalue()

        # Build multipart/form-data
        boundary = f"Boundary-{uuid.uuid4().hex}"
        parts = []
        parts.append(f"--{boundary}".encode("utf-8"))
        parts.append(b'Content-Disposition: form-data; name="file"; filename="audio.wav"')
        parts.append(b"Content-Type: audio/wav")
        parts.append(b"")
        parts.append(wav_bytes)
        
        parts.append(f"--{boundary}".encode("utf-8"))
        parts.append(b'Content-Disposition: form-data; name="model"')
        parts.append(b"")
        parts.append(b"whisper-1")
        
        parts.append(f"--{boundary}--".encode("utf-8"))
        parts.append(b"")
        
        body = b"\r\n".join(parts)
        
        key = self._get_api_key()
        if not key:
            raise ValueError(f"No API key found for STT provider {self._config.provider}")

        req = urllib.request.Request(
            self._get_endpoint(),
            data=body,
            headers={
                "Content-Type": f"multipart/form-data; boundary={boundary}",
                "Authorization": f"Bearer {key}",
            }
        )
        
        with urllib.request.urlopen(req, timeout=30) as res:
            resp_data = json.loads(res.read().decode("utf-8"))
            return resp_data.get("text", "").strip()

    def transcribe_segment(self, segment: SpeechSegment) -> TranscriptResult:
        duration = len(segment.audio) / segment.sample_rate
        if self._config.provider in ("openai", "groq"):
            try:
                text = self._transcribe_cloud(segment)
                logger.info("Cloud Transcribed (%.1fs): %s", duration, text or "<empty>")
                return TranscriptResult(
                    text=text,
                    language=self._config.language,
                    duration_sec=duration,
                )
            except Exception as exc:
                logger.error("Cloud STT failed, falling back to local Whisper: %s", exc)
                # Fall through to local model if local loading is possible

        model = self._ensure_model()
        audio = segment.audio.astype(np.float32)
        if audio.max() > 1.0 or audio.min() < -1.0:
            peak = max(abs(audio.min()), abs(audio.max()), 1e-6)
            audio = audio / peak

        segments, info = model.transcribe(
            audio,
            language=self._config.language,
            beam_size=1,
            vad_filter=False,
        )
        text = " ".join(s.text.strip() for s in segments).strip()
        logger.info("Transcribed (%.1fs): %s", duration, text or "<empty>")
        return TranscriptResult(
            text=text,
            language=info.language or self._config.language,
            duration_sec=duration,
        )
