"""Dispatch text to TTS service."""
from __future__ import annotations

import logging
from datetime import datetime

from aiagent.schemas.outputs import ResponsePacket
from aiagent.state.speaking_state import SpeakingState
from integrations.tts.gpt_sovits_client import GPTSoVITSClient
from integrations.tts.indextts2_client import IndexTTS2Client
from integrations.tts.mock_tts_client import MockTTSClient
from integrations.tts.voxcpm_client import VoxCPMClient


class TTSDispatcher:
    def __init__(
        self,
        mock_tts_client: MockTTSClient,
        speaking_state: SpeakingState,
        tts_provider: str = "mock",
        enable_mock_tts: bool = True,
        gpt_sovits_client: GPTSoVITSClient | None = None,
        index_tts2_client: IndexTTS2Client | None = None,
        voxcpm_client: VoxCPMClient | None = None,
    ) -> None:
        self.mock_tts_client = mock_tts_client
        self.speaking_state = speaking_state
        self.tts_provider = tts_provider
        self.enable_mock_tts = enable_mock_tts
        self.gpt_sovits_client = gpt_sovits_client
        self.index_tts2_client = index_tts2_client
        self.voxcpm_client = voxcpm_client
        self.logger = logging.getLogger(self.__class__.__name__)

    def dispatch(self, packet: ResponsePacket) -> ResponsePacket:
        if not packet.should_speak:
            packet.metadata["tts"] = "skipped_should_speak_false"
            return packet

        self.speaking_state.last_tts_text = packet.reply_text
        self.speaking_state.last_updated_at = datetime.now().isoformat(timespec="seconds")

        try:
            audio_path, audio_segments, segment_texts = self._synthesize(packet.reply_text)
        except Exception as exc:
            self.logger.exception("TTS dispatch failed: %s", exc)
            fallback_audio = self.mock_tts_client.synthesize(packet.reply_text)
            audio_path = fallback_audio
            audio_segments = [fallback_audio]
            segment_texts = [packet.reply_text]

            packet.metadata["tts"] = "mock-fallback"
            packet.metadata["tts_error"] = str(exc)
            self.speaking_state.current_provider = "mock-fallback"
        else:
            packet.metadata["tts"] = self.tts_provider
            packet.metadata["tts_segments"] = str(len(audio_segments))
            self.speaking_state.current_provider = self.tts_provider

        self.speaking_state.last_audio_path = audio_path
        self.speaking_state.last_updated_at = datetime.now().isoformat(timespec="seconds")

        packet.audio_path = audio_path
        packet.audio_segments = audio_segments
        packet.audio_segment_texts = segment_texts
        return packet

    def _synthesize(self, text: str) -> tuple[str, list[str], list[str]]:
        if self.enable_mock_tts or self.tts_provider == "mock":
            self.logger.info("Using mock TTS provider")
            audio_path = self.mock_tts_client.synthesize(text)
            return audio_path, [audio_path], [text]

        if self.tts_provider == "gpt_sovits":
            if self.gpt_sovits_client is None:
                raise RuntimeError("GPT-SoVITS client is not initialized")

            self.logger.info("Using GPT-SoVITS TTS provider")
            audio_path = self.gpt_sovits_client.synthesize(text)
            return audio_path, [audio_path], [text]

        if self.tts_provider == "indextts2":
            if self.index_tts2_client is None:
                raise RuntimeError("IndexTTS2 client is not initialized")

            self.logger.info("Using IndexTTS2 streaming TTS provider")
            segment_results = self.index_tts2_client.synthesize_streaming(text)
            if not segment_results:
                raise RuntimeError("IndexTTS2 returned no audio segments.")

            audio_segments = [item[0] for item in segment_results]
            segment_texts = [item[1] for item in segment_results]
            return audio_segments[0], audio_segments, segment_texts

        if self.tts_provider == "voxcpm":
            if self.voxcpm_client is None:
                raise RuntimeError("VoxCPM client is not initialized")

            self.logger.info("Using VoxCPM cloud TTS provider")
            audio_path = self.voxcpm_client.synthesize(text)
            return audio_path, [audio_path], [text]

        raise RuntimeError(f"Unsupported TTS provider: {self.tts_provider}")
