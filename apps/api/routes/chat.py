from __future__ import annotations

import json
import logging
import traceback
from typing import Any

from fastapi import APIRouter, Response
from pydantic import BaseModel

from apps.core.runtime_registry import get_runtime, get_runtime_error

router = APIRouter()
logger = logging.getLogger("aiagent.api.chat")


class ChatRequest(BaseModel):
    user_id: str = "guest"
    username: str = "guest"
    text: str


@router.post("/chat")
def chat(req: ChatRequest):
    try:
        runtime = get_runtime()
    except Exception as exc:
        logger.exception("Runtime init failed in /chat: %s", exc)

        body = json.dumps(
            {
                "ok": False,
                "stage": "runtime_init",
                "error": str(exc),
                "runtime_error": get_runtime_error(),
                "traceback": traceback.format_exc(),
            },
            ensure_ascii=False,
        )
        return Response(
            content=body,
            media_type="application/json; charset=utf-8",
            status_code=500,
        )

    try:
        output = runtime.handle_chat_full(
            text=req.text,
            user_id=req.user_id,
            username=req.username,
        )
        packet = output.packet
        live2d = packet.live2d or _build_live2d_payload(packet)

        body = json.dumps(
            {
                "ok": True,
                "output_id": output.output_id,
                "reply": packet.reply_text,
                "base_reply_text": packet.base_reply_text,
                "emotion": packet.emotion,
                "motion": packet.motion,
                "expression": packet.expression,
                "audio_path": packet.audio_path,
                "audio_url": packet.audio_url,
                "audio_segments": packet.audio_segments,
                "audio_segment_urls": packet.audio_segment_urls,
                "audio_segment_texts": packet.audio_segment_texts,
                "live2d_command_path": packet.live2d_command_path,
                "live2d":live2d,
                "metadata": packet.metadata,
            },
            ensure_ascii=False,
            default=str,
        )

        return Response(
            content=body,
            media_type="application/json; charset=utf-8",
            status_code=200,
        )

    except Exception as exc:
        logger.exception("Chat route failed: %s", exc)
        body = json.dumps(
            {
                "ok": False,
                "stage": "chat_handler",
                "error": str(exc),
                "traceback": traceback.format_exc(),
            },
            ensure_ascii=False,
        )
        return Response(
            content=body,
            media_type="application/json; charset=utf-8",
            status_code=500,
        )

def _build_live2d_payload(packet) ->dict[str,Any]:
    audio_url = packet.audio_url or ""

    return {
        "character": {
            "character_id": "yzl",
            "model_id": "yzl_v1",
            "emotion": str(packet.emotion),
            "expression": packet.expression or "neutral",
            "motion": packet.motion or "idle",
            "motion_priority": 1,
            "mouth": {
                "mode": "audio" if audio_url else "idle",
                "audio_url": audio_url,
            },
            "eye": {
                "blink": True,
                "look_at": "user",
            },
        },
        "scene": {
            "background_id": "room_default",
            "lighting": "normal",
            "effect": "none",
        },
    }