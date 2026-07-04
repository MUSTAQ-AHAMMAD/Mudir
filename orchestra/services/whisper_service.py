"""Whisper service — offline voice transcription via the whisper.cpp CLI.

Uses the locally installed ``whisper.cpp`` binary (default ``whisper-cli``) with
a GGML model file. Audio is normalised to 16 kHz mono WAV with ``ffmpeg`` so
that WAV / MP3 / OPUS (WhatsApp voice notes are OPUS/OGG) are all supported.

No cloud transcription APIs are used.
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlparse

import requests

from .config import config, get_logger

_log = get_logger(__name__)

# Origins that WhatsApp media is allowed to be downloaded from. This mirrors
# the SSRF hardening already applied to the Node backend: only Twilio media
# hosts are permitted so a spoofed media URL cannot reach internal services.
_ALLOWED_MEDIA_HOSTS = ("api.twilio.com", "media.twiliocdn.com", "mcs.us1.twilio.com")


class WhisperServiceError(RuntimeError):
    """Raised when transcription cannot be completed."""


class WhisperService:
    """Wrapper around the whisper.cpp CLI for offline transcription."""

    def __init__(
        self,
        binary: Optional[str] = None,
        model_path: Optional[str] = None,
        language: Optional[str] = None,
    ) -> None:
        self.binary = binary or config.whisper_binary
        self.model_path = model_path or config.whisper_model_path
        self.language = language or config.whisper_language

    # -- public API ---------------------------------------------------------
    def transcribe(self, audio_path: str, language: Optional[str] = None) -> str:
        """Transcribe an audio file and return the plain-text transcript.

        Args:
            audio_path: Path to a WAV/MP3/OPUS/OGG audio file.
            language: Optional ISO language override (defaults to Arabic).

        Raises:
            WhisperServiceError: If the file is missing or transcription fails.
        """

        result = self._run(audio_path, language=language, with_timestamps=False)
        return result["text"]

    def transcribe_with_timestamps(
        self, audio_path: str, language: Optional[str] = None
    ) -> dict[str, Any]:
        """Transcribe and return ``{"text", "segments": [{start, end, text}]}``."""

        return self._run(audio_path, language=language, with_timestamps=True)

    def transcribe_whatsapp_voice(
        self, media_url: str, language: Optional[str] = None
    ) -> str:
        """Download a WhatsApp voice note and transcribe it.

        The media URL is validated against an allow-list of Twilio hosts to
        avoid server-side request forgery, then downloaded to a temporary file
        and transcribed.
        """

        self._validate_media_url(media_url)
        suffix = self._guess_suffix(media_url)
        auth = self._twilio_auth()
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp_path = tmp.name
        try:
            _log.info("Downloading WhatsApp voice note")
            resp = requests.get(media_url, timeout=30, stream=True, auth=auth)
            resp.raise_for_status()
            with open(tmp_path, "wb") as fh:
                for chunk in resp.iter_content(chunk_size=8192):
                    if chunk:
                        fh.write(chunk)
            return self.transcribe(tmp_path, language=language)
        except requests.RequestException as exc:
            raise WhisperServiceError(f"Failed to download voice note: {exc}") from exc
        finally:
            self._safe_unlink(tmp_path)

    # -- internals ----------------------------------------------------------
    def _run(
        self, audio_path: str, language: Optional[str], with_timestamps: bool
    ) -> dict[str, Any]:
        src = Path(audio_path)
        if not src.is_file():
            raise WhisperServiceError(f"Audio file not found: {audio_path}")
        if not Path(self.model_path).is_file():
            raise WhisperServiceError(
                f"Whisper model not found at {self.model_path}. Run auto-install.sh first."
            )

        wav_path = self._to_wav(src)
        out_prefix = wav_path.with_suffix("")
        cmd = [
            self.binary,
            "-m", self.model_path,
            "-f", str(wav_path),
            "-l", language or self.language,
            "-oj",  # emit JSON alongside the audio
            "-of", str(out_prefix),
        ]
        try:
            _log.info("Running whisper.cpp on %s", wav_path.name)
            subprocess.run(cmd, capture_output=True, text=True, check=True)
        except FileNotFoundError as exc:
            raise WhisperServiceError(
                f"whisper.cpp binary '{self.binary}' not found on PATH"
            ) from exc
        except subprocess.CalledProcessError as exc:
            raise WhisperServiceError(
                f"whisper.cpp failed (exit {exc.returncode}): {exc.stderr.strip()}"
            ) from exc
        finally:
            # Remove the intermediate WAV if we created it (not the caller's file).
            if wav_path != src:
                self._safe_unlink(str(wav_path))

        json_path = Path(f"{out_prefix}.json")
        try:
            return self._parse_output(json_path, with_timestamps)
        finally:
            self._safe_unlink(str(json_path))

    def _to_wav(self, src: Path) -> Path:
        """Convert ``src`` to 16 kHz mono WAV via ffmpeg (no-op if already WAV)."""

        if src.suffix.lower() == ".wav":
            return src
        target = Path(tempfile.gettempdir()) / f"orchestra_{os.getpid()}_{src.stem}.wav"
        cmd = [
            "ffmpeg", "-y", "-i", str(src),
            "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le",
            str(target),
        ]
        try:
            subprocess.run(cmd, capture_output=True, text=True, check=True)
        except FileNotFoundError as exc:
            raise WhisperServiceError("ffmpeg not found on PATH") from exc
        except subprocess.CalledProcessError as exc:
            raise WhisperServiceError(
                f"ffmpeg conversion failed: {exc.stderr.strip()}"
            ) from exc
        return target

    @staticmethod
    def _parse_output(json_path: Path, with_timestamps: bool) -> dict[str, Any]:
        if not json_path.is_file():
            raise WhisperServiceError(f"whisper.cpp produced no output at {json_path}")
        try:
            data = json.loads(json_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise WhisperServiceError(f"Could not read whisper output: {exc}") from exc

        transcription = data.get("transcription", [])
        text = "".join(seg.get("text", "") for seg in transcription).strip()
        if not with_timestamps:
            return {"text": text}

        segments = []
        for seg in transcription:
            offsets = seg.get("offsets", {})
            segments.append(
                {
                    "start": offsets.get("from", 0) / 1000.0,
                    "end": offsets.get("to", 0) / 1000.0,
                    "text": seg.get("text", "").strip(),
                }
            )
        return {"text": text, "segments": segments}

    @staticmethod
    def _validate_media_url(media_url: str) -> None:
        parsed = urlparse(media_url)
        if parsed.scheme != "https":
            raise WhisperServiceError("Media URL must use HTTPS")
        if parsed.hostname not in _ALLOWED_MEDIA_HOSTS:
            raise WhisperServiceError(f"Media host not allowed: {parsed.hostname!r}")

    @staticmethod
    def _twilio_auth() -> Optional[tuple[str, str]]:
        sid = os.getenv("TWILIO_ACCOUNT_SID")
        token = os.getenv("TWILIO_AUTH_TOKEN")
        if sid and token:
            return (sid, token)
        return None

    @staticmethod
    def _guess_suffix(media_url: str) -> str:
        path = urlparse(media_url).path.lower()
        for ext in (".ogg", ".opus", ".mp3", ".wav", ".m4a"):
            if path.endswith(ext):
                return ext
        return ".ogg"  # WhatsApp voice notes default to OGG/OPUS

    @staticmethod
    def _safe_unlink(path: str) -> None:
        try:
            os.unlink(path)
        except OSError:
            pass


# Module-level singleton and functional wrappers.
_default_service: Optional[WhisperService] = None


def get_service() -> WhisperService:
    """Return a lazily-instantiated shared :class:`WhisperService`."""

    global _default_service
    if _default_service is None:
        _default_service = WhisperService()
    return _default_service


def transcribe(audio_path: str) -> str:
    """Module-level wrapper around :meth:`WhisperService.transcribe`."""

    return get_service().transcribe(audio_path)


def transcribe_whatsapp_voice(media_url: str) -> str:
    """Module-level wrapper around :meth:`WhisperService.transcribe_whatsapp_voice`."""

    return get_service().transcribe_whatsapp_voice(media_url)


def transcribe_with_timestamps(audio_path: str) -> dict[str, Any]:
    """Module-level wrapper around :meth:`WhisperService.transcribe_with_timestamps`."""

    return get_service().transcribe_with_timestamps(audio_path)


__all__ = [
    "WhisperService",
    "WhisperServiceError",
    "get_service",
    "transcribe",
    "transcribe_whatsapp_voice",
    "transcribe_with_timestamps",
]
