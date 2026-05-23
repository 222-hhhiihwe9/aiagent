from __future__ import annotations

from fastapi import APIRouter, File, UploadFile
from pydantic import BaseModel
from starlette.responses import JSONResponse

from cloud.config import cloud_settings
from cloud.object_storage import build_object_key, get_object_store, guess_content_type
from cloud.redis_client import redis_health

router = APIRouter()


class PresignUploadRequest(BaseModel):
    filename: str
    content_type: str = "application/octet-stream"
    prefix: str = "uploads"
    expires_seconds: int = 900


@router.get("/cloud/ready")
async def cloud_ready():
    return {
        "ok": True,
        "cloud_mode": cloud_settings.cloud_mode,
        "region": cloud_settings.cloud_deploy_region,
        "redis": await redis_health(),
        "storage": {
            "provider": cloud_settings.storage_provider,
            "bucket_configured": bool(cloud_settings.s3_bucket),
            "public_base_url_configured": bool(cloud_settings.s3_public_base_url),
        },
        "gpu": {
            "llm_configured": bool(cloud_settings.gpu_llm_base_url),
            "tts_configured": bool(cloud_settings.gpu_tts_base_url),
            "asr_configured": bool(cloud_settings.gpu_asr_base_url),
        },
    }


@router.get("/cloud/limits")
def cloud_limits():
    return {
        "ok": True,
        "rate_limit_enabled": cloud_settings.rate_limit_enabled,
        "inflight_limit_enabled": cloud_settings.inflight_limit_enabled,
        "limits": {
            "global_inflight": cloud_settings.global_inflight_limit,
            "chat_inflight": cloud_settings.chat_inflight_limit,
            "multimodal_inflight": cloud_settings.multimodal_inflight_limit,
            "voice_inflight": cloud_settings.voice_inflight_limit,
            "rebuild_inflight": cloud_settings.rebuild_inflight_limit,
            "chat_per_minute": cloud_settings.rate_limit_chat_per_minute,
            "multimodal_per_minute": cloud_settings.rate_limit_multimodal_per_minute,
            "voice_per_minute": cloud_settings.rate_limit_voice_per_minute,
            "rebuild_per_minute": cloud_settings.rate_limit_rebuild_per_minute,
        },
    }


@router.post("/cloud/storage/presign-upload")
async def presign_upload(req: PresignUploadRequest):
    key = build_object_key(req.prefix, req.filename)
    store = get_object_store()

    try:
        url = await store.presigned_put_url(
            key=key,
            content_type=req.content_type,
            expires_seconds=req.expires_seconds,
        )
    except Exception as exc:
        return JSONResponse(
            status_code=400,
            content={
                "ok": False,
                "stage": "presign_upload",
                "error": str(exc),
            },
        )

    return {
        "ok": True,
        "key": key,
        "upload_url": url,
        "content_type": req.content_type,
        "expires_seconds": req.expires_seconds,
    }


@router.post("/cloud/storage/upload")
async def direct_upload(prefix: str = "uploads", file: UploadFile = File(...)):
    data = await file.read()
    if len(data) > cloud_settings.upload_max_bytes:
        return JSONResponse(
            status_code=413,
            content={
                "ok": False,
                "stage": "upload_size_limit",
                "error": "uploaded file is too large",
                "max_bytes": cloud_settings.upload_max_bytes,
            },
        )

    content_type = file.content_type or guess_content_type(file.filename)
    key = build_object_key(prefix, file.filename)
    stored = await get_object_store().put_bytes(
        key=key,
        data=data,
        content_type=content_type,
    )

    return {
        "ok": True,
        "object": {
            "key": stored.key,
            "url": stored.url,
            "size": stored.size,
            "content_type": stored.content_type,
        },
    }