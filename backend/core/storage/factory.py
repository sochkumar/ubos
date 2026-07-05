"""Storage adapter factory. Reads STORAGE_BACKEND at process start."""
from __future__ import annotations

import os
from functools import lru_cache

from .base import StorageAdapter
from .local import LocalDiskAdapter
from .s3 import S3Adapter


@lru_cache(maxsize=1)
def get_storage_adapter() -> StorageAdapter:
    backend = os.environ.get("STORAGE_BACKEND", "local").strip().lower()
    if backend == "local":
        return LocalDiskAdapter(
            root=os.environ.get("LOCAL_STORAGE_ROOT", "/app/backend/uploads"),
            signing_secret=os.environ["MEDIA_SIGNING_SECRET"],
        )
    if backend == "s3":
        return S3Adapter()
    raise RuntimeError(f"Unknown STORAGE_BACKEND '{backend}'")
