"""S3-compatible adapter — STUB. Implements the interface so imports succeed
without boto3 installed. All operations raise NotImplementedError. Sub-pass C
or a later phase will fill this in against boto3 / aioboto3."""
from __future__ import annotations

from typing import AsyncIterable

from .base import StorageAdapter, StorageObject, StorageStat

try:  # optional dep — not required for local backend
    import boto3  # type: ignore
    _HAS_BOTO3 = True
except ImportError:
    boto3 = None  # type: ignore
    _HAS_BOTO3 = False


class S3Adapter(StorageAdapter):
    backend_name = "s3"

    def __init__(self, *_a, **_kw):
        raise NotImplementedError(
            "S3Adapter is a stub in Sub-pass B. "
            "Set STORAGE_BACKEND=local (default) until this is implemented."
        )

    async def put(self, org_id, key_prefix, filename, data, mime) -> StorageObject:  # noqa: D401
        raise NotImplementedError("S3Adapter.put is not implemented")

    async def get_stream(self, key: str) -> AsyncIterable[bytes]:
        raise NotImplementedError("S3Adapter.get_stream is not implemented")
        yield b""  # pragma: no cover

    async def delete(self, key: str) -> None:
        raise NotImplementedError("S3Adapter.delete is not implemented")

    async def presigned_get(self, key: str, ttl_seconds: int = 3600) -> str:
        raise NotImplementedError("S3Adapter.presigned_get is not implemented")

    async def stat(self, key: str) -> StorageStat:
        raise NotImplementedError("S3Adapter.stat is not implemented")

    async def exists(self, key: str) -> bool:
        raise NotImplementedError("S3Adapter.exists is not implemented")
