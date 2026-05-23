from __future__ import annotations

import os
from pathlib import Path

from fastapi import APIRouter, Depends

from cloud.admin_auth import require_cloud_admin
from cloud.config import cloud_settings
from cloud.redis_client import redis_health
from apps.core.runtime_registry import get_runtime_error

router = APIRouter()


def _path_status(path: str) -> dict[str, object]:
    target = Path(path)
    return {
        "path": path,
        "exists": target.exists(),
        "is_dir": target.is_dir(),
    }


@router.get("/cloud/ops/readiness")
async def readiness():
    redis = await redis_health()

    checks = {
        "redis": redis.get("ok", False) if cloud_settings.redis_url else True,
        "storage_provider": cloud_settings.storage_provider in {"local", "cos", "s3"},
        "qdrant_configured": bool(os.getenv("QDRANT_HOST", "")),
        "runtime_import_error": get_runtime_error() is None,
        "data_dir": Path("data").exists(),
    }

    ok = all(bool(value) for value in checks.values())

    return {
        "ok": ok,
        "checks": checks,
        "cloud_mode": cloud_settings.cloud_mode,
    }


@router.get("/cloud/ops/config-snapshot")
async def config_snapshot(_: None = Depends(require_cloud_admin)):
    return {
        "ok": True,
        "cloud": {
            "cloud_mode": cloud_settings.cloud_mode,
            "region": cloud_settings.cloud_deploy_region,
            "rate_limit_enabled": cloud_settings.rate_limit_enabled,
            "inflight_limit_enabled": cloud_settings.inflight_limit_enabled,
            "storage_provider": cloud_settings.storage_provider,
            "global_inflight_limit": cloud_settings.global_inflight_limit,
            "chat_inflight_limit": cloud_settings.chat_inflight_limit,
            "voice_inflight_limit": cloud_settings.voice_inflight_limit,
            "multimodal_inflight_limit": cloud_settings.multimodal_inflight_limit,
        },
        "paths": {
            "data": _path_status("data"),
            "cache": _path_status("data/cache"),
            "knowledge": _path_status("data/knowledge"),
            "characters": _path_status("data/characters"),
        },
        "gpu": {
            "llm": bool(cloud_settings.gpu_llm_base_url),
            "tts": bool(cloud_settings.gpu_tts_base_url),
            "asr": bool(cloud_settings.gpu_asr_base_url),
        },
    }