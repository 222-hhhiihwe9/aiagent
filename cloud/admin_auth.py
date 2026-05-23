from __future__ import annotations

import os
from hmac import compare_digest

from fastapi import Header, HTTPException


def _admin_token() -> str:
    return os.getenv("CLOUD_ADMIN_TOKEN", "").strip()


async def require_cloud_admin(x_admin_token: str | None = Header(default=None)) -> None:
    expected = _admin_token()

    if not expected:
        raise HTTPException(
            status_code=503,
            detail="CLOUD_ADMIN_TOKEN is not configured.",
        )

    if not x_admin_token or not compare_digest(x_admin_token, expected):
        raise HTTPException(
            status_code=403,
            detail="Invalid admin token.",
        )