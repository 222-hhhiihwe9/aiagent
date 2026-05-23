from __future__ import annotations

import asyncio
import mimetypes
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol

from cloud.config import cloud_settings


@dataclass(frozen=True)
class StoredObject:
    key: str
    url: str
    size: int
    content_type: str


class ObjectStore(Protocol):
    async def put_bytes(self, key: str, data: bytes, content_type: str) -> StoredObject:
        ...

    async def presigned_put_url(self, key: str, content_type: str, expires_seconds: int) -> str:
        ...

    async def presigned_get_url(self, key: str, expires_seconds: int) -> str:
        ...


def build_object_key(prefix: str, filename: str | None) -> str:
    now = datetime.now(timezone.utc)
    safe_prefix = _safe_path_part(prefix or "uploads")
    name = _safe_filename(filename or "file.bin")
    return f"{safe_prefix}/{now:%Y/%m/%d}/{now:%H%M%S}-{name}"


def _safe_path_part(value: str) -> str:
    value = value.strip().strip("/")
    value = re.sub(r"[^a-zA-Z0-9/_-]+", "-", value)
    return value or "uploads"


def _safe_filename(value: str) -> str:
    value = Path(value).name
    value = re.sub(r"[^a-zA-Z0-9._-]+", "-", value)
    return value or "file.bin"


def guess_content_type(filename: str | None, fallback: str = "application/octet-stream") -> str:
    if not filename:
        return fallback
    return mimetypes.guess_type(filename)[0] or fallback


class LocalObjectStore:
    def __init__(self, root: str, public_base_url: str) -> None:
        self.root = Path(root)
        self.public_base_url = public_base_url.rstrip("/")

    async def put_bytes(self, key: str, data: bytes, content_type: str) -> StoredObject:
        path = self.root / key
        path.parent.mkdir(parents=True, exist_ok=True)
        await asyncio.to_thread(path.write_bytes, data)

        if self.public_base_url:
            url = f"{self.public_base_url}/cloud-files/{key}"
        else:
            url = f"/cloud-files/{key}"

        return StoredObject(
            key=key,
            url=url,
            size=len(data),
            content_type=content_type,
        )

    async def presigned_put_url(self, key: str, content_type: str, expires_seconds: int) -> str:
        raise RuntimeError("local storage does not support presigned upload url")

    async def presigned_get_url(self, key: str, expires_seconds: int) -> str:
        if self.public_base_url:
            return f"{self.public_base_url}/cloud-files/{key}"
        return f"/cloud-files/{key}"


class S3ObjectStore:
    def __init__(self) -> None:
        if not cloud_settings.s3_bucket:
            raise RuntimeError("S3_BUCKET is required when STORAGE_PROVIDER=cos")

        import boto3

        self.bucket = cloud_settings.s3_bucket
        self.public_base_url = cloud_settings.s3_public_base_url.rstrip("/")
        self.client = boto3.client(
            "s3",
            endpoint_url=cloud_settings.s3_endpoint_url or None,
            region_name=cloud_settings.s3_region,
            aws_access_key_id=cloud_settings.s3_access_key_id,
            aws_secret_access_key=cloud_settings.s3_secret_access_key,
        )

    async def put_bytes(self, key: str, data: bytes, content_type: str) -> StoredObject:
        await asyncio.to_thread(
            self.client.put_object,
            Bucket=self.bucket,
            Key=key,
            Body=data,
            ContentType=content_type,
        )

        url = f"{self.public_base_url}/{key}" if self.public_base_url else await self.presigned_get_url(key, 3600)

        return StoredObject(
            key=key,
            url=url,
            size=len(data),
            content_type=content_type,
        )

    async def presigned_put_url(self, key: str, content_type: str, expires_seconds: int) -> str:
        return await asyncio.to_thread(
            self.client.generate_presigned_url,
            "put_object",
            Params={
                "Bucket": self.bucket,
                "Key": key,
                "ContentType": content_type,
            },
            ExpiresIn=expires_seconds,
        )

    async def presigned_get_url(self, key: str, expires_seconds: int) -> str:
        return await asyncio.to_thread(
            self.client.generate_presigned_url,
            "get_object",
            Params={
                "Bucket": self.bucket,
                "Key": key,
            },
            ExpiresIn=expires_seconds,
        )


_object_store: ObjectStore | None = None


def get_object_store() -> ObjectStore:
    global _object_store

    if _object_store is not None:
        return _object_store

    if cloud_settings.storage_provider.lower() in {"cos", "s3"}:
        _object_store = S3ObjectStore()
    else:
        _object_store = LocalObjectStore(
            root=cloud_settings.local_storage_root,
            public_base_url=cloud_settings.api_public_base_url,
        )

    return _object_store