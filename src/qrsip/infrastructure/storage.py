"""Storage port and file-backed implementation (ADR-0002, NFR-001, NFR-007).

Design:

- ``StoragePort`` is the *only* interface higher layers may depend on when they
  need durable state. Domain entities and quant logic therefore never import a
  concrete database driver.
- ``FileStorage`` is the portable, dependency-free implementation used by early
  phases. It writes under a single root directory using *keys*, not paths, and
  rejects any key that attempts path traversal (fail closed).
- Content identity is a SHA-256 hash over canonical bytes, so artifacts can be
  compared for equality without relying on file metadata.

PostgreSQL will be introduced behind this same port when the registry/lineage
capability actually requires queryable relational storage (ADR-0002).
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from qrsip.errors import ConfigurationError, QRSIPError

__all__ = [
    "FileStorage",
    "StorageError",
    "StoragePort",
    "canonical_json_bytes",
    "sha256_hex",
]


class StorageError(QRSIPError):
    """Raised when a storage operation violates the storage contract."""


def canonical_json_bytes(payload: Any) -> bytes:
    """Serialize a JSON-compatible payload to canonical, deterministic bytes.

    Canonical form: sorted keys, compact separators, ASCII-safe, UTF-8 encoded,
    single trailing newline. These bytes are the basis for content identity and
    for byte-for-byte reproducibility checks (ADR-0006).
    """
    text = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
        default=str,
    )
    return (text + "\n").encode("utf-8")


def sha256_hex(payload: bytes) -> str:
    """Return the hex SHA-256 digest of ``payload``."""
    return hashlib.sha256(payload).hexdigest()


@runtime_checkable
class StoragePort(Protocol):
    """Minimal durable-storage contract used by platform layers."""

    def write_bytes(self, key: str, payload: bytes) -> str:
        """Write ``payload`` to ``key`` and return its content hash."""
        ...

    def read_bytes(self, key: str) -> bytes:
        """Read raw bytes for ``key``."""
        ...

    def exists(self, key: str) -> bool:
        """Return True when ``key`` exists in storage."""
        ...

    def list_keys(self, prefix: str = "") -> list[str]:
        """Return sorted keys (deterministic order) under ``prefix``."""
        ...

    def describe(self, key: str) -> dict[str, Any]:
        """Return size/sha256 metadata for ``key``."""
        ...


def _validate_key(key: str) -> str:
    """Normalize and validate a storage key.

    Keys are POSIX-style relative paths. Absolute paths, parent traversal,
    backslashes, and empty segments are rejected so that storage cannot escape
    its configured root (fail closed).
    """
    if not isinstance(key, str) or not key.strip():
        raise StorageError("storage key must be a non-empty string", key=repr(key))
    if key.startswith("/") or key.startswith("~"):
        raise StorageError("storage key must be relative", key=key)
    if "\\" in key:
        raise StorageError("storage key must not contain backslashes", key=key)
    if ":" in key:
        raise StorageError("storage key must not contain drive separators", key=key)
    if key.endswith("/"):
        raise StorageError("storage key must reference a file, not a directory", key=key)
    parts = key.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise StorageError("storage key contains an invalid segment", key=key)
    return "/".join(parts)
class FileStorage:
    """Deterministic, portable, file-backed :class:`StoragePort` implementation.

    Writes are atomic (temp file + ``os.replace``) so a crashed run cannot leave
    a partially written artifact behind.
    """

    def __init__(self, root: Path) -> None:
        self._root = Path(root).resolve()

    @property
    def root(self) -> Path:
        """Absolute root directory of this store."""
        return self._root

    def path_for(self, key: str) -> Path:
        """Return the absolute path for ``key``, enforcing the root boundary."""
        normalized = _validate_key(key)
        candidate = (self._root / normalized).resolve()
        root = self._root
        if candidate != root and root not in candidate.parents:
            raise StorageError("resolved path escapes the storage root", key=key)
        return candidate

    def write_bytes(self, key: str, payload: bytes) -> str:
        """Atomically write ``payload`` and return the SHA-256 of the bytes."""
        target = self.path_for(key)
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_name(f".{target.name}.tmp")
        try:
            with tmp.open("wb") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp, target)
        except OSError as exc:  # pragma: no cover - exercised via adversarial tests
            raise StorageError(
                "failed to write artifact",
                key=key,
                path=str(target),
                reason=str(exc),
            ) from exc
        return sha256_hex(payload)

    def read_bytes(self, key: str) -> bytes:
        """Read raw bytes for ``key``."""
        target = self.path_for(key)
        if not target.is_file():
            raise StorageError("artifact does not exist", key=key, path=str(target))
        try:
            return target.read_bytes()
        except OSError as exc:  # pragma: no cover - exercised via adversarial tests
            raise StorageError(
                "failed to read artifact",
                key=key,
                path=str(target),
                reason=str(exc),
            ) from exc

    def exists(self, key: str) -> bool:
        """Return True when ``key`` exists as a file."""
        return self.path_for(key).is_file()

    def list_keys(self, prefix: str = "") -> list[str]:
        """Return deterministically sorted keys under ``prefix``."""
        root = self._root
        if not root.is_dir():
            return []
        keys: list[str] = []
        for path in root.rglob("*"):
            if not path.is_file() or path.name.startswith("."):
                continue
            relative = path.relative_to(root).as_posix()
            if relative.endswith(".tmp"):
                continue
            if prefix and not relative.startswith(prefix):
                continue
            keys.append(relative)
        return sorted(keys)

    def describe(self, key: str) -> dict[str, Any]:
        """Return size + content hash metadata for ``key``."""
        payload = self.read_bytes(key)
        return {
            "key": key,
            "size_bytes": len(payload),
            "sha256": sha256_hex(payload),
        }

    # -- convenience helpers used by registries and artifact writers ---------

    def write_text(self, key: str, text: str) -> str:
        """Write UTF-8 text and return its content hash."""
        return self.write_bytes(key, text.encode("utf-8"))

    def read_text(self, key: str) -> str:
        """Read UTF-8 text for ``key``."""
        return self.read_bytes(key).decode("utf-8")

    def write_json(self, key: str, payload: Any) -> str:
        """Write canonical JSON and return its content hash."""
        return self.write_bytes(key, canonical_json_bytes(payload))

    def read_json(self, key: str) -> Any:
        """Read JSON for ``key``. Raises StorageError on malformed content."""
        raw = self.read_bytes(key)
        try:
            return json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise StorageError("artifact is not valid JSON", key=key, reason=str(exc)) from exc

    def require_root(self) -> None:
        """Fail closed when the root does not exist or is not a directory."""
        if not self._root.is_dir():
            raise ConfigurationError("storage root is not a directory", root=str(self._root))
