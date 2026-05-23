from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Depends, File, Form, UploadFile

from cloud.admin_auth import require_cloud_admin
from cloud.config import cloud_settings
from cloud.task_queue import CloudTaskQueue
from cloud.timeouts import to_thread_with_timeout
from apps.api.response_utils import error_response, ok_response
from apps.core.runtime_registry import get_runtime, get_runtime_error
from config.settings import settings

router = APIRouter()
logger = logging.getLogger("aiagent.api.vision")
task_queue = CloudTaskQueue(prefix=cloud_settings.redis_prefix)


@router.post("/vision/analyze")
async def analyze_image(
    file: UploadFile = File(...),
    user_id: str = Form(default="guest"),
    prompt: str = Form(default=""),
):
    try:
        runtime = get_runtime()
    except Exception as exc:
        logger.exception("Runtime init failed in /vision/analyze: %s", exc)
        return error_response(
            stage="runtime_init",
            exc=exc,
            status_code=500,
            runtime_error=get_runtime_error(),
        )

    try:
        if cloud_settings.cloud_mode:
            result = await to_thread_with_timeout(
                "vision_analyze",
                settings.vision_timeout_seconds,
                runtime.analyze_image_upload,
                file_obj=file.file,
                filename=file.filename or "upload.png",
                user_prompt=prompt,
                user_id=user_id,
            )
        else:
            result = await asyncio.to_thread(
                runtime.analyze_image_upload,
                file_obj=file.file,
                filename=file.filename or "upload.png",
                user_prompt=prompt,
                user_id=user_id,
            )

        return ok_response(result=result.model_dump(mode="json"))

    except Exception as exc:
        logger.exception("Vision analyze failed: %s", exc)
        return error_response(stage="vision_analyze", exc=exc, status_code=500)


@router.post("/vision/chat")
async def vision_chat(
    file: UploadFile = File(...),
    user_id: str = Form(default="guest"),
    username: str = Form(default="guest"),
    prompt: str = Form(default="请看这张图片。"),
):
    try:
        runtime = get_runtime()
    except Exception as exc:
        logger.exception("Runtime init failed in /vision/chat: %s", exc)
        return error_response(
            stage="runtime_init",
            exc=exc,
            status_code=500,
            runtime_error=get_runtime_error(),
        )

    try:
        if cloud_settings.cloud_mode:
            output = await to_thread_with_timeout(
                "vision_chat",
                settings.vision_timeout_seconds + settings.llm_timeout_seconds + 10.0,
                runtime.handle_vision_chat_upload,
                file_obj=file.file,
                filename=file.filename or "upload.png",
                user_prompt=prompt,
                user_id=user_id,
                username=username,
            )
        else:
            output = await asyncio.to_thread(
                runtime.handle_vision_chat_upload,
                file_obj=file.file,
                filename=file.filename or "upload.png",
                user_prompt=prompt,
                user_id=user_id,
                username=username,
            )

        packet = output["chat_output"].packet
        vision_state = output["vision_state"]
        vision_result = vision_state["vision_result"]

        return ok_response(
            output_id=output["chat_output"].output_id,
            reply=packet.reply_text,
            base_reply_text=packet.base_reply_text,
            emotion=packet.emotion,
            motion=packet.motion,
            expression=packet.expression,
            audio_path=packet.audio_path,
            audio_url=packet.audio_url,
            audio_segments=packet.audio_segments,
            audio_segment_urls=packet.audio_segment_urls,
            audio_segment_texts=packet.audio_segment_texts,
            live2d_command_path=packet.live2d_command_path,
            live2d=packet.live2d,
            metadata=packet.metadata,
            vision={
                "result": vision_result.model_dump(mode="json"),
                "chat_context": vision_state.get("chat_context", ""),
                "memory_hint": vision_state.get("memory_hint", ""),
                "live2d_suggestion": vision_state.get("live2d_suggestion", {}),
                "metadata": vision_state.get("metadata", {}),
            },
        )

    except Exception as exc:
        logger.exception("Vision chat failed: %s", exc)
        return error_response(stage="vision_chat", exc=exc, status_code=500)


@router.post("/vision/characters/rebuild")
async def rebuild_character_index(
    force_rebuild: bool = True,
    _: None = Depends(require_cloud_admin),
):
    try:
        if cloud_settings.cloud_mode:
            task = await task_queue.enqueue(
                "vision.characters.rebuild",
                payload={"force_rebuild": force_rebuild},
                unique_key="vision.characters.rebuild",
                unique_ttl_seconds=3600,
            )
            return ok_response(
                mode="task",
                task_id=task.task_id,
                created=task.created,
                status=task.status,
            )

        runtime = get_runtime()
        stats = runtime.rebuild_vision_character_index(force_rebuild=force_rebuild)
        return ok_response(mode="sync", stats=stats)

    except Exception as exc:
        logger.exception("Vision character rebuild failed: %s", exc)
        return error_response(stage="vision_character_rebuild", exc=exc, status_code=500)


@router.get("/vision/characters/stats")
def character_index_stats():
    try:
        runtime = get_runtime()
        stats = runtime.get_vision_character_index_stats()
        return ok_response(stats=stats)
    except Exception as exc:
        logger.exception("Vision character stats failed: %s", exc)
        return error_response(stage="vision_character_stats", exc=exc, status_code=500)