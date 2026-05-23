from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import httpx

from cloud.config import cloud_settings


@dataclass(frozen=True)
class GpuEndpointHealth:
    name: str
    configured: bool
    ok: bool
    status_code: int | None = None
    error: str = ""


def _join_url(base_url: str, path: str) -> str:
    return f"{base_url.rstrip('/')}/{path.lstrip('/')}"


def _auth_headers() -> dict[str, str]:
    token = os.getenv("GPU_API_TOKEN", "").strip()
    if not token:
        return {}
    return {"Authorization": f"Bearer {token}"}


class GpuServiceClient:
    async def health(self, name: str, base_url: str) -> GpuEndpointHealth:
        if not base_url:
            return GpuEndpointHealth(name=name, configured=False, ok=False)

        async with httpx.AsyncClient(timeout=5) as client:
            for path in ("health", "ready", ""):
                try:
                    response = await client.get(
                        _join_url(base_url, path),
                        headers=_auth_headers(),
                    )
                    if response.status_code < 500:
                        return GpuEndpointHealth(
                            name=name,
                            configured=True,
                            ok=response.status_code < 400,
                            status_code=response.status_code,
                        )
                except Exception as exc:
                    last_error = str(exc)

        return GpuEndpointHealth(
            name=name,
            configured=True,
            ok=False,
            error=last_error,
        )

    async def health_all(self) -> dict[str, Any]:
        llm = await self.health("llm", cloud_settings.gpu_llm_base_url)
        tts = await self.health("tts", cloud_settings.gpu_tts_base_url)
        asr = await self.health("asr", cloud_settings.gpu_asr_base_url)

        return {
            "llm": llm.__dict__,
            "tts": tts.__dict__,
            "asr": asr.__dict__,
        }

    async def openai_chat(
        self,
        *,
        base_url: str,
        model: str,
        messages: list[dict[str, str]],
        temperature: float = 0.2,
        max_tokens: int = 128,
        timeout_seconds: float = 30,
    ) -> dict[str, Any]:
        if not base_url:
            raise RuntimeError("GPU LLM base url is not configured.")

        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        async with httpx.AsyncClient(timeout=timeout_seconds) as client:
            response = await client.post(
                _join_url(base_url, "chat/completions"),
                headers={
                    "Content-Type": "application/json",
                    **_auth_headers(),
                },
                json=payload,
            )
            response.raise_for_status()
            return response.json()


gpu_client = GpuServiceClient()