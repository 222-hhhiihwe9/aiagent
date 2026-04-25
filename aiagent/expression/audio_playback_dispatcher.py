from __future__ import annotations

from datetime import datetime
from pathlib import Path

from aiagent.schemas.outputs import ResponsePacket
from aiagent.state.speaking_state import SpeakingState
from integrations.audio.audio_player import AudioPlayer


class AudioPlaybackDispatcher:
    def __init__(
        self,
        audio_player: AudioPlayer,
        speaking_state: SpeakingState,
    ) -> None:
        self.audio_player = audio_player
        self.speaking_state = speaking_state

    def dispatch(self, packet: ResponsePacket) -> ResponsePacket:
        self.refresh_state()

        audio_segments = [item for item in packet.audio_segments if item]
        if audio_segments:
            return self._dispatch_segments(packet, audio_segments)

        if not packet.audio_path:
            packet.metadata["audio_playback"] = "skipped_no_audio"
            return packet

        return self._dispatch_single(packet, packet.audio_path)

    def _dispatch_single(self, packet: ResponsePacket, audio_path_str: str) -> ResponsePacket:
        audio_path = Path(audio_path_str)
        suffix = audio_path.suffix.lower()

        if suffix not in {".wav", ".mp3", ".ogg"}:
            packet.metadata["audio_playback"] = f"skipped_non_audio:{suffix or 'no_suffix'}"
            return packet

        self.speaking_state.is_speaking = True
        self.speaking_state.current_text = packet.reply_text
        self.speaking_state.current_audio_path = str(audio_path)
        self.speaking_state.last_audio_path = str(audio_path)
        self.speaking_state.playback_status = "starting"
        self.speaking_state.is_interrupted = False
        self.speaking_state.last_stop_reason = ""
        self.speaking_state.playback_started_at = datetime.now().isoformat(timespec="seconds")
        self.speaking_state.playback_finished_at = ""
        self.speaking_state.last_updated_at = datetime.now().isoformat(timespec="seconds")

        try:
            self.speaking_state.audio_duration_sec = self.audio_player.get_duration_seconds(str(audio_path))
        except Exception:
            self.speaking_state.audio_duration_sec = 0.0

        try:
            self.audio_player.play_async(str(audio_path))
            self.speaking_state.playback_status = "playing"
            packet.metadata["audio_playback"] = "started_async"
        except Exception as exc:
            self.speaking_state.is_speaking = False
            self.speaking_state.playback_status = "failed"
            self.speaking_state.last_stop_reason = str(exc)
            self.speaking_state.playback_finished_at = datetime.now().isoformat(timespec="seconds")
            self.speaking_state.last_updated_at = datetime.now().isoformat(timespec="seconds")
            packet.metadata["audio_playback"] = f"failed:{exc}"

        return packet

    def _dispatch_segments(self, packet: ResponsePacket, audio_segments: list[str]) -> ResponsePacket:
        valid_segments: list[str] = []

        for item in audio_segments:
            path = Path(item)
            suffix = path.suffix.lower()
            if suffix not in {".wav", ".mp3", ".ogg"}:
                continue
            valid_segments.append(str(path))

        if not valid_segments:
            packet.metadata["audio_playback"] = "skipped_no_valid_segments"
            return packet

        self.speaking_state.is_speaking = True
        self.speaking_state.current_text = packet.reply_text
        self.speaking_state.current_audio_path = valid_segments[0]
        self.speaking_state.last_audio_path = valid_segments[-1]
        self.speaking_state.playback_status = "starting"
        self.speaking_state.is_interrupted = False
        self.speaking_state.last_stop_reason = ""
        self.speaking_state.playback_started_at = datetime.now().isoformat(timespec="seconds")
        self.speaking_state.playback_finished_at = ""
        self.speaking_state.last_updated_at = datetime.now().isoformat(timespec="seconds")

        try:
            self.speaking_state.audio_duration_sec = self.audio_player.get_total_duration_seconds(valid_segments)
        except Exception:
            self.speaking_state.audio_duration_sec = 0.0

        try:
            self.audio_player.play_sequence_async(valid_segments)
            self.speaking_state.playback_status = "playing"
            packet.metadata["audio_playback"] = "started_async_segments"
            packet.metadata["audio_segment_count"] = str(len(valid_segments))
        except Exception as exc:
            self.speaking_state.is_speaking = False
            self.speaking_state.playback_status = "failed"
            self.speaking_state.last_stop_reason = str(exc)
            self.speaking_state.playback_finished_at = datetime.now().isoformat(timespec="seconds")
            self.speaking_state.last_updated_at = datetime.now().isoformat(timespec="seconds")
            packet.metadata["audio_playback"] = f"failed:{exc}"

        return packet

    def interrupt(self, reason: str = "manual_interrupt") -> None:
        self.audio_player.stop()
        self.speaking_state.is_speaking = False
        self.speaking_state.playback_status = "interrupted"
        self.speaking_state.is_interrupted = True
        self.speaking_state.last_stop_reason = reason
        self.speaking_state.playback_finished_at = datetime.now().isoformat(timespec="seconds")
        self.speaking_state.last_updated_at = datetime.now().isoformat(timespec="seconds")
        self.speaking_state.current_audio_path = ""
        self.speaking_state.current_text = ""

    def refresh_state(self) -> None:
        now = datetime.now().isoformat(timespec="seconds")

        current_audio_path = self.audio_player.get_current_audio_path()
        if self.audio_player.is_busy():
            self.speaking_state.playback_status = "playing"
            self.speaking_state.is_speaking = True
            self.speaking_state.current_audio_path = current_audio_path
            self.speaking_state.last_updated_at = now
            return

        if self.speaking_state.playback_status in {"playing", "starting"}:
            self.speaking_state.is_speaking = False
            self.speaking_state.playback_status = "completed"
            self.speaking_state.current_audio_path = ""
            self.speaking_state.current_text = ""
            self.speaking_state.playback_finished_at = now
            self.speaking_state.last_updated_at = now
