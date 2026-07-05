"""LocalDiskAdapter — MVP storage backend, atomic writes, HMAC-signed serve URLs."""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import AsyncIterable

import aiofiles
import aiofiles.os as aios

from .base import StorageAdapter, StorageObject, StorageStat

_SAFE_FILENAME = re.compile(r"[^A-Za-z0-9._-]+")


def _safe(name: str) -> str:
    name = _SAFE_FILENAME.sub("_", name).strip("._") or "file"
    # cap length
    return name[-96:]


def _sign(key: str, exp: int, secret: str) -> str:
    payload = f"{key}|{exp}".encode()
    mac = hmac.new(secret.encode(), payload, hashlib.sha256).digest()
    sig = base64.urlsafe_b64encode(mac).rstrip(b"=").decode()
    return sig


def sign_token(key: str, exp_ts: int, secret: str) -> str:
    b64key = base64.urlsafe_b64encode(key.encode()).rstrip(b"=").decode()
    sig = _sign(key, exp_ts, secret)
    return f"{b64key}.{exp_ts}.{sig}"


def verify_token(token: str, secret: str) -> str | None:
    """Return the original storage key iff token is valid + unexpired, else None."""
    try:
        b64key, exp_s, sig = token.split(".", 2)
    except ValueError:
        return None
    try:
        exp = int(exp_s)
    except ValueError:
        return None
    if exp < int(datetime.now(timezone.utc).timestamp()):
        return None
    # b64key can lack padding
    padded = b64key + "=" * (-len(b64key) % 4)
    try:
        key = base64.urlsafe_b64decode(padded.encode()).decode()
    except (ValueError, UnicodeDecodeError):
        return None
    expected = _sign(key, exp, secret)
    if not hmac.compare_digest(sig, expected):
        return None
    return key


class LocalDiskAdapter(StorageAdapter):
    backend_name = "local"

    def __init__(self, root: str, signing_secret: str, presigned_base_path: str = "/api/media/serve"):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.secret = signing_secret
        self.serve_path = presigned_base_path.rstrip("/")

    def _abs(self, key: str) -> Path:
        # Defence in depth: keys are UUID-prefixed strings we generate. Reject
        # any absolute/traversal attempt.
        if key.startswith("/") or ".." in key.split("/"):
            raise ValueError(f"invalid storage key: {key}")
        return self.root / key

    async def put(
        self, org_id: str, key_prefix: str, filename: str,
        data: bytes, mime: str,
    ) -> StorageObject:
        now = datetime.now(timezone.utc)
        safe = _safe(filename)
        key = f"{org_id}/{now:%Y/%m}/{key_prefix or ''}{uuid.uuid4().hex[:12]}-{safe}"
        path = self._abs(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        checksum = hashlib.sha256(data).hexdigest()
        async with aiofiles.open(tmp, "wb") as f:
            await f.write(data)
        os.replace(tmp, path)  # atomic
        return StorageObject(storage_key=key, size=len(data), checksum=checksum, mime=mime)

    async def put_bytes_at_key(self, key: str, data: bytes) -> StorageObject:
        """Escape hatch used by media thumbnail cache — writes at a specific
        derived key. NOT part of the abstract interface."""
        path = self._abs(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        async with aiofiles.open(tmp, "wb") as f:
            await f.write(data)
        os.replace(tmp, path)
        return StorageObject(
            storage_key=key, size=len(data),
            checksum=hashlib.sha256(data).hexdigest(),
            mime="application/octet-stream",
        )

    async def get_stream(self, key: str) -> AsyncIterable[bytes]:
        path = self._abs(key)
        async with aiofiles.open(path, "rb") as f:
            while True:
                chunk = await f.read(64 * 1024)
                if not chunk:
                    break
                yield chunk

    async def read_all(self, key: str) -> bytes:
        async with aiofiles.open(self._abs(key), "rb") as f:
            return await f.read()

    async def delete(self, key: str) -> None:
        path = self._abs(key)
        try:
            await aios.remove(path)
        except FileNotFoundError:
            return

    async def presigned_get(self, key: str, ttl_seconds: int = 3600) -> str:
        exp = int(datetime.now(timezone.utc).timestamp()) + int(ttl_seconds)
        token = sign_token(key, exp, self.secret)
        return f"{self.serve_path}/{token}"

    async def stat(self, key: str) -> StorageStat:
        path = self._abs(key)
        st = path.stat()
        # We don't rehash on stat — checksum is stored in the media doc.
        return StorageStat(
            size=st.st_size, checksum="",
            mime="application/octet-stream",
            modified_at=datetime.fromtimestamp(st.st_mtime, timezone.utc).isoformat(),
        )

    async def exists(self, key: str) -> bool:
        return self._abs(key).exists()
