"""QRSIP domain base entity with identity, versioning, timestamps (spec 13)."""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, Field

__all__ = ["BaseEntity"]


def _utcnow() -> datetime:
    return datetime.now(UTC)


class BaseEntity(BaseModel):
    """Base for all domain entities: stable id + version + timestamps."""

    model_config = {"frozen": True, "extra": "forbid"}

    id: str = Field(..., min_length=1, description="Stable entity identifier")
    version: str = Field(default="1.0.0", description="Entity schema/semantic version")
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)
