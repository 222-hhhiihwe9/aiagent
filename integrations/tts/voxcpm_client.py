from __future__ import annotations

import logging
import math
import re
from pathlib import Path
from uuid import uuid4

import httpx


class VoxCPMClient:
    def __init__(
        self,
        base_url: str,
        timeout_seconds: float = 300.0,
        output_dir: str | Path = "data/cache/tts_real",
    ) -> None:
        self.base_url = base_url.strip().rstrip("/")
        self.timeout_seconds = self._normalize_timeout(timeout_seconds)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.logger = logging.getLogger(self.__class__.__name__)

    def synthesize(self, text: str) -> str:
        cleaned = self.normalize_text(text)
        if not cleaned:
            raise RuntimeError("VoxCPM text is empty after normalization.")

        url = f"{self.base_url}/synthesize"
        self.logger.info("Calling VoxCPM endpoint: %s", url)

        timeout = httpx.Timeout(
            connect=min(self.timeout_seconds, 30.0),
            read=self.timeout_seconds,
            write=min(self.timeout_seconds, 60.0),
            pool=min(self.timeout_seconds, 30.0),
        )

        with httpx.Client(timeout=timeout, trust_env=False) as client:
            response = client.post(
                url,
                data={"text": cleaned},
            )

        if response.status_code != 200:
            raise RuntimeError(
                f"VoxCPM request failed: {response.status_code} {response.text}"
            )

        content_type = response.headers.get("content-type", "").lower()
        audio_bytes = response.content

        if "application/json" in content_type or "text/plain" in content_type:
            raise RuntimeError(
                f"VoxCPM returned non-audio response: {response.text[:300]}"
            )

        if not audio_bytes:
            raise RuntimeError("VoxCPM returned empty audio content.")

        if not self._looks_like_wav(audio_bytes):
            preview = audio_bytes[:120].decode("utf-8", errors="ignore")
            raise RuntimeError(f"VoxCPM did not return a valid wav stream: {preview}")

        file_path = self.output_dir / f"{uuid4().hex}.wav"
        file_path.write_bytes(audio_bytes)
        return str(file_path)

    def normalize_text(self, text: str) -> str:
        text = re.sub(r"（.*?）", "", text)
        text = re.sub(r"\(.*?\)", "", text)
        text = re.sub(r"\[.*?\]", "", text)
        text = re.sub(r"\{.*?\}", "", text)
        text = re.sub(r"\*.*?\*", "", text)
        return text.strip()

    def _normalize_timeout(self, value: float | int | str) -> float:
        try:
            timeout = float(value)
        except (TypeError, ValueError):
            self.logger.warning("Invalid timeout value %r, fallback to 300.0", value)
            return 300.0

        if not math.isfinite(timeout):
            self.logger.warning("Non-finite timeout value %r, fallback to 300.0", value)
            return 300.0

        if timeout <= 0:
            self.logger.warning("Non-positive timeout value %r, fallback to 300.0", value)
            return 300.0

        if timeout > 3600:
            self.logger.warning("Timeout value %r too large, clamped to 3600.0", value)
            return 3600.0

        return timeout

    @staticmethod
    def _looks_like_wav(audio_bytes: bytes) -> bool:
        return (
            len(audio_bytes) >= 12
            and audio_bytes[:4] == b"RIFF"
            and audio_bytes[8:12] == b"WAVE"
        )
