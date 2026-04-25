from __future__ import annotations

import logging
import math
import re
from pathlib import Path
from uuid import uuid4

import httpx


class IndexTTS2Client:
    def __init__(
        self,
        base_url: str,
        ref_audio_path: str,
        emo_alpha: float = 0.6,
        use_emo_text: bool = True,
        max_segment_length: int = 20,
        output_dir: str | Path = "data/cache/tts_real",
        timeout_seconds: float = 120.0,
    ) -> None:
        self.base_url = base_url.strip().rstrip("/")
        self.ref_audio_path = ref_audio_path.strip().strip('"').strip("'")
        self.emo_alpha = emo_alpha
        self.use_emo_text = use_emo_text
        self.max_segment_length = max_segment_length
        self.timeout_seconds = self._normalize_timeout(timeout_seconds)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.logger = logging.getLogger(self.__class__.__name__)

    def synthesize(self, text: str) -> str:
        segments = self.synthesize_streaming(text)
        if not segments:
            raise RuntimeError("IndexTTS2 returned no audio segments.")
        return segments[0][0]

    def synthesize_streaming(self, text: str) -> list[tuple[str, str]]:
        normalized_text = self.normalize_text(text)
        if not normalized_text:
            return []

        segments = self.split_text_streaming(
            normalized_text,
            max_length=self.max_segment_length,
        )
        if not segments:
            return []

        results: list[tuple[str, str]] = []
        for segment_text in segments:
            audio_path = self.synthesize_segment(segment_text)
            results.append((audio_path, segment_text))
        return results

    def synthesize_segment(self, text: str) -> str:
        if not self.ref_audio_path:
            raise RuntimeError("INDEX_TTS2_REF_AUDIO_PATH is not configured.")

        ref_audio_file = Path(self.ref_audio_path)
        if not ref_audio_file.exists():
            raise RuntimeError(f"IndexTTS2 reference audio not found: {self.ref_audio_path}")

        cleaned = self.normalize_text(text)
        if not cleaned:
            raise RuntimeError("IndexTTS2 segment text is empty after normalization.")

        url = f"{self.base_url}/synthesize"
        self.logger.info("Calling IndexTTS2 endpoint: %s", url)

        data = {
            "text": cleaned,
            "emo_alpha": str(self.emo_alpha),
            "use_emo_text": str(self.use_emo_text).lower(),
        }

        timeout = httpx.Timeout(
            connect=min(self.timeout_seconds, 30.0),
            read=self.timeout_seconds,
            write=min(self.timeout_seconds, 60.0),
            pool=min(self.timeout_seconds, 30.0),
        )

        with ref_audio_file.open("rb") as ref_file:
            files = {
                "ref_audio": (ref_audio_file.name, ref_file, "audio/wav"),
            }

            with httpx.Client(timeout=timeout, trust_env=False) as client:
                response = client.post(url, data=data, files=files)

        if response.status_code != 200:
            raise RuntimeError(
                f"IndexTTS2 request failed: {response.status_code} {response.text}"
            )

        content_type = response.headers.get("content-type", "").lower()
        audio_bytes = response.content

        if "application/json" in content_type or "text/plain" in content_type:
            raise RuntimeError(
                f"IndexTTS2 returned non-audio response: {response.text[:300]}"
            )

        if not audio_bytes:
            raise RuntimeError("IndexTTS2 returned empty audio content.")

        if not self._looks_like_wav(audio_bytes):
            preview = audio_bytes[:120].decode("utf-8", errors="ignore")
            raise RuntimeError(f"IndexTTS2 did not return a valid wav stream: {preview}")

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

    def split_text_streaming(self, text: str, max_length: int = 20) -> list[str]:
        strong_punc = "。！？!?"
        weak_punc = "，,；;"

        segments: list[str] = []
        buf = ""

        for ch in text:
            buf += ch

            if ch in strong_punc:
                if buf.strip():
                    segments.append(buf.strip())
                buf = ""
                continue

            if ch in weak_punc and len(buf) >= max_length * 0.7:
                if buf.strip():
                    segments.append(buf.strip())
                buf = ""

            if len(buf) >= max_length:
                if buf.strip():
                    segments.append(buf.strip())
                buf = ""

        if buf.strip():
            segments.append(buf.strip())

        return segments

    def _normalize_timeout(self, value: float | int | str) -> float:
        try:
            timeout = float(value)
        except (TypeError, ValueError):
            self.logger.warning("Invalid timeout value %r, fallback to 120.0", value)
            return 120.0

        if not math.isfinite(timeout):
            self.logger.warning("Non-finite timeout value %r, fallback to 120.0", value)
            return 120.0

        if timeout <= 0:
            self.logger.warning("Non-positive timeout value %r, fallback to 120.0", value)
            return 120.0

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
