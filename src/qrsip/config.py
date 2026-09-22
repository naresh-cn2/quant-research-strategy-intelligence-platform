"""QRSIP configuration system (L0 infrastructure).

Design principles (spec §section-config, §4.8 fail-closed):

- Configuration is YAML and validated before use.
- Malformed or incomplete configuration is rejected.
- Experiments store the *resolved* configuration, not merely a path to it
  (spec §20).
- Secrets are never stored in configuration values committed to the repo.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from qrsip.errors import ConfigurationError

__all__ = [
    "ConfigLoader",
    "coerce_bool",
    "load_yaml_document",
    "resolve_paths",
    "sanitize_for_storage",
    "validate_required_fields",
]


def coerce_bool(value: Any) -> bool:
    """Coerce common boolean representations to a Python bool.

    Accepts: True/False, "true"/"false"/"yes"/"no"/"1"/"0", 1/0.
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and value in (0, 1):
        return bool(value)
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "yes", "1"}:
            return True
        if lowered in {"false", "no", "0", ""}:
            return False
    raise ValueError(f"cannot coerce {value!r} to bool")


def load_yaml_document(path: Path) -> dict[str, Any]:
    """Load a single YAML document and enforce it is a mapping.

    Returns:
        The parsed mapping.

    Raises:
        ConfigurationError: if the file is missing, unreadable, empty,
            not a mapping, or uses disallowed YAML tags.
    """
    if not path.is_file():
        raise ConfigurationError(
            "configuration file does not exist",
            path=str(path),
        )
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ConfigurationError(
            "cannot read configuration file",
            path=str(path),
            reason=str(exc),
        ) from exc

    if not raw.strip():
        raise ConfigurationError(
            "configuration file is empty",
            path=str(path),
        )

    try:
        parsed = yaml.safe_load(raw)
    except yaml.YAMLError as exc:
        raise ConfigurationError(
            "configuration file is not valid YAML",
            path=str(path),
            reason=str(exc),
        ) from exc

    if not isinstance(parsed, dict):
        raise ConfigurationError(
            "configuration file must contain a mapping, not " + type(parsed).__name__,
            path=str(path),
            type=type(parsed).__name__,
        )

    return parsed


def resolve_paths(
    mapping: dict[str, Any],
    *,
    base: Path | None = None,
    keys: tuple[str, ...] | None = None,
) -> dict[str, Any]:
    """Resolve relative paths in a configuration mapping in place.

    Any value in ``keys`` that is a string and looks like a relative path
    is resolved relative to ``base`` (defaults to the current working
    directory).

    The original mapping is mutated; callers that must not mutate should
    pass a copy.
    """
    base = base or Path.cwd()
    keys = keys or ("data_path", "config_dir", "output_dir", "report_dir")

    for key in keys:
        value = mapping.get(key)
        if isinstance(value, str) and not value.startswith("/"):
            mapping[key] = (base / value).resolve()
    return mapping


def validate_required_fields(
    mapping: dict[str, Any],
    required: tuple[str, ...],
    *,
    section: str = "root",
) -> None:
    """Verify that ``mapping`` contains every required key at top level.

    Raises:
        ConfigurationError: if any required key is absent.
    """
    missing = [key for key in required if key not in mapping]
    if not required:
        raise ConfigurationError(
            "required fields must be non-empty",
            section=section,
        )
    if missing:
        raise ConfigurationError(
            "configuration is missing required fields",
            section=section,
            missing=missing,
        )


def sanitize_for_storage(value: Any) -> Any:
    """Produce a JSON-serializable representation of a configuration value.

    Used when serialising resolved configuration into experiment artifacts so
    that values can be re-serialised reliably. Paths are stored as strings.
    """
    if isinstance(value, Path):
        return value.as_posix()
    if isinstance(value, dict):
        return {key: sanitize_for_storage(val) for key, val in value.items()}
    if isinstance(value, (list, tuple)):
        return [sanitize_for_storage(item) for item in value]
    if isinstance(value, bytes):
        return value.hex()
    return value


@dataclass(slots=True)
class ConfigLoader:
    """A small, deterministic configuration loader with schema bookkeeping."""

    base_dir: Path = field(default_factory=Path.cwd)
    extra_types: dict[str, Any] = field(default_factory=dict)

    def load(
        self,
        config_path: Path,
        *,
        base: Path | None = None,
        resolve_path_keys: tuple[str, ...] | None = None,
    ) -> dict[str, Any]:
        """Load and optionally resolve a configuration document.

        Returns the *resolved* mapping. Raises ConfigurationError on any
        failure.
        """
        base = base or self.base_dir
        mapping = load_yaml_document(config_path)
        resolve_paths(mapping, base=base, keys=resolve_path_keys or ())
        return mapping

    def validate(
        self,
        mapping: dict[str, Any],
        required: tuple[str, ...],
        *,
        section: str = "root",
    ) -> None:
        """Validate required fields. Raises ConfigurationError on failure."""
        validate_required_fields(mapping, required, section=section)

    def dump_json_serializable(self, mapping: dict[str, Any]) -> dict[str, Any]:
        """Return a version suitable for reliable JSON persistence."""
        sanitized: dict[str, Any] = sanitize_for_storage(mapping)
        assert isinstance(sanitized, dict)
        return sanitized


def merge_env_overrides(mapping: dict[str, Any], prefix: str = "QRSIP_") -> dict[str, Any]:
    """Merge uppercase environment variable overrides into a mapping.

    Simple string values override scalar entries. This is a *documentation and
    controlled-override* mechanism only; the canonical source of truth remains
    the YAML configuration file. Secret values should never be sourced from the
    environment in research configurations.

    Returns a new mapping.
    """
    merged: dict[str, Any] = dict(mapping)
    for key, value in os.environ.items():
        if not key.startswith(prefix):
            continue
        field_name = key[len(prefix) :].lower()
        merged[field_name] = value
    return merged


def make_env_example(prefix: str = "QRSIP_", *, out_path: Path | None = None) -> str:
    """Emit a minimal .env.example illustration.

    This is a controlled helper. It does not discover secrets; it only emits the
    documentation structure that tells users which environment variables affect
    QRSIP behavior.
    """
    lines = [
        "# QRSIP environment overrides (optional).",
        "# Configuration is otherwise driven by config/*.yaml files.",
        "# Do NOT commit real secrets; copy .env.example to .env and edit locally.",
        "",
        f"# {prefix}LOG_LEVEL=INFO",
        "",
    ]
    text = "\n".join(lines)
    if out_path is not None:
        out_path.write_text(text, encoding="utf-8")
    return text
