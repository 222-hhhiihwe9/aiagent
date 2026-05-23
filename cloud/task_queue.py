from __future__ import annotations

import asyncio
import json
import time
import uuid
from dataclasses import dataclass
from typing import Any

from cloud.config import cloud_settings
from cloud.redis_client import get_redis_client


@dataclass(frozen=True)
class TaskSubmitResult:
    task_id: str
    created: bool
    status: str


class _MemoryTaskStore:
    def __init__(self) -> None:
        self.tasks: dict[str, dict[str, Any]] = {}
        self.unique: dict[str, tuple[str, float]] = {}
        self.queue: asyncio.Queue[str] = asyncio.Queue()
        self.lock = asyncio.Lock()


_memory_store = _MemoryTaskStore()


class CloudTaskQueue:
    def __init__(self, prefix: str) -> None:
        self.prefix = prefix

    def _task_key(self, task_id: str) -> str:
        return f"{self.prefix}:task:{task_id}"

    def _queue_key(self, queue: str) -> str:
        return f"{self.prefix}:tasks:queue:{queue}"

    def _unique_key(self, queue: str, unique_key: str) -> str:
        return f"{self.prefix}:tasks:unique:{queue}:{unique_key}"

    async def enqueue(
        self,
        task_type: str,
        payload: dict[str, Any] | None = None,
        *,
        queue: str = "default",
        unique_key: str | None = None,
        unique_ttl_seconds: int = 1800,
    ) -> TaskSubmitResult:
        payload = payload or {}
        task_id = uuid.uuid4().hex
        now = time.time()

        redis = await get_redis_client()
        if redis is not None:
            if unique_key:
                unique_redis_key = self._unique_key(queue, unique_key)
                ok = await redis.set(
                    unique_redis_key,
                    task_id,
                    nx=True,
                    ex=unique_ttl_seconds,
                )
                if not ok:
                    existing_id = await redis.get(unique_redis_key)
                    if existing_id:
                        existing = await self.get(existing_id)
                        return TaskSubmitResult(
                            task_id=existing_id,
                            created=False,
                            status=str(existing.get("status", "unknown")),
                        )

            record = {
                "id": task_id,
                "type": task_type,
                "queue": queue,
                "status": "queued",
                "payload": json.dumps(payload, ensure_ascii=False),
                "result": "",
                "error": "",
                "unique_key": unique_key or "",
                "created_at": str(now),
                "started_at": "",
                "finished_at": "",
                "worker_id": "",
            }

            await redis.hset(self._task_key(task_id), mapping=record)
            await redis.rpush(self._queue_key(queue), task_id)
            return TaskSubmitResult(task_id=task_id, created=True, status="queued")

        async with _memory_store.lock:
            if unique_key:
                key = self._unique_key(queue, unique_key)
                current = _memory_store.unique.get(key)
                if current and current[1] > now:
                    existing = _memory_store.tasks.get(current[0], {})
                    return TaskSubmitResult(
                        task_id=current[0],
                        created=False,
                        status=str(existing.get("status", "unknown")),
                    )
                _memory_store.unique[key] = (task_id, now + unique_ttl_seconds)

            _memory_store.tasks[task_id] = {
                "id": task_id,
                "type": task_type,
                "queue": queue,
                "status": "queued",
                "payload": payload,
                "result": None,
                "error": "",
                "unique_key": unique_key or "",
                "created_at": now,
                "started_at": None,
                "finished_at": None,
                "worker_id": "",
            }
            await _memory_store.queue.put(task_id)

        return TaskSubmitResult(task_id=task_id, created=True, status="queued")

    async def get(self, task_id: str) -> dict[str, Any]:
        redis = await get_redis_client()
        if redis is not None:
            data = await redis.hgetall(self._task_key(task_id))
            if not data:
                return {}

            data["payload"] = json.loads(data.get("payload") or "{}")
            data["result"] = json.loads(data.get("result") or "null")
            return data

        async with _memory_store.lock:
            return dict(_memory_store.tasks.get(task_id, {}))

    async def pop(self, queue: str = "default", timeout_seconds: int = 5) -> dict[str, Any] | None:
        redis = await get_redis_client()
        if redis is not None:
            item = await redis.blpop(self._queue_key(queue), timeout=timeout_seconds)
            if not item:
                return None
            task_id = item[1]
            return await self.get(task_id)

        try:
            task_id = await asyncio.wait_for(
                _memory_store.queue.get(),
                timeout=timeout_seconds,
            )
        except asyncio.TimeoutError:
            return None

        async with _memory_store.lock:
            return dict(_memory_store.tasks.get(task_id, {}))

    async def start(self, task_id: str, worker_id: str) -> None:
        redis = await get_redis_client()
        now = str(time.time())

        if redis is not None:
            await redis.hset(
                self._task_key(task_id),
                mapping={
                    "status": "running",
                    "started_at": now,
                    "worker_id": worker_id,
                },
            )
            return

        async with _memory_store.lock:
            task = _memory_store.tasks.get(task_id)
            if task:
                task["status"] = "running"
                task["started_at"] = time.time()
                task["worker_id"] = worker_id

    async def finish(self, task_id: str, result: Any) -> None:
        task = await self.get(task_id)
        redis = await get_redis_client()
        now = str(time.time())

        if redis is not None:
            await redis.hset(
                self._task_key(task_id),
                mapping={
                    "status": "succeeded",
                    "result": json.dumps(result, ensure_ascii=False, default=str),
                    "finished_at": now,
                },
            )
            await self._release_unique(task)
            return

        async with _memory_store.lock:
            item = _memory_store.tasks.get(task_id)
            if item:
                item["status"] = "succeeded"
                item["result"] = result
                item["finished_at"] = time.time()

    async def fail(self, task_id: str, error: str) -> None:
        task = await self.get(task_id)
        redis = await get_redis_client()
        now = str(time.time())

        if redis is not None:
            await redis.hset(
                self._task_key(task_id),
                mapping={
                    "status": "failed",
                    "error": error,
                    "finished_at": now,
                },
            )
            await self._release_unique(task)
            return

        async with _memory_store.lock:
            item = _memory_store.tasks.get(task_id)
            if item:
                item["status"] = "failed"
                item["error"] = error
                item["finished_at"] = time.time()

    async def _release_unique(self, task: dict[str, Any]) -> None:
        unique_key = str(task.get("unique_key") or "")
        queue = str(task.get("queue") or "default")
        if not unique_key:
            return

        redis = await get_redis_client()
        if redis is not None:
            await redis.delete(self._unique_key(queue, unique_key))