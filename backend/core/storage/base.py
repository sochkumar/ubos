"""StorageAdapter ABC + shared value types."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import AsyncIterable


@dataclass
class StorageObject:
    """Result of a successful put()."""
    storage_key: str          # opaque backend-scoped identifier
    size: int
    checksum: str             # sha256 hex
    mime: str


@dataclass
class StorageStat:
    size: int
    checksum: str
    mime: str
    modified_at: str          # ISO


class StorageAdapter(ABC):
    """Minimal object-storage interface UBOS relies on.

    Implementations MUST be safe for concurrent async use and MUST NOT expose
    raw filesystem paths in any return value.
    """

    backend_name: str = "base"

    @abstractmethod
    async def put(
        self,
        org_id: str,
        key_prefix: str,
        filename: str,
        data: bytes,
        mime: str,
    ) -> StorageObject: ...

    @abstractmethod
    async def get_stream(self, key: str) -> AsyncIterable[bytes]: ...

    @abstractmethod
    async def delete(self, key: str) -> None: ...

    @abstractmethod
    async def presigned_get(self, key: str, ttl_seconds: int = 3600) -> str: ...

    @abstractmethod
    async def stat(self, key: str) -> StorageStat: ...

    @abstractmethod
    async def exists(self, key: str) -> bool: ...
