"""Research registry: durable, queryable domain entity storage (FR-001..FR-005).

The registry is the persistence boundary for L1 Domain. It depends only on the
:class:`~qrsip.infrastructure.storage.StoragePort` abstraction (ADR-0002), so the
same code works with file storage today and PostgreSQL later.

Design rules:

- Writes are append-only per (entity kind, id, version). History is never
  silently overwritten; writing a different payload under the same identity is
  rejected unless ``overwrite=True`` is explicit.
- Listing returns deterministic (sorted) order so lineage and comparisons are
  reproducible.
- Reading an unknown entity fails closed with :class:`RegistryError`.
"""

from __future__ import annotations

from typing import TypeVar

from pydantic import BaseModel

from qrsip.domain.base import BaseEntity
from qrsip.errors import QRSIPError
from qrsip.infrastructure.storage import StoragePort, canonical_json_bytes

__all__ = ["RegistryError", "ResearchRegistry"]

EntityT = TypeVar("EntityT", bound=BaseModel)


class RegistryError(QRSIPError):
    """Raised when a registry operation violates the registry contract."""


_KIND_DIRS: dict[type[BaseModel], str] = {}


def _kind_of(entity_cls: type[BaseModel]) -> str:
    """Map an entity class to its registry directory name (explicit, not magic)."""
    name = entity_cls.__name__
    overrides = {
        "ResearchQuestion": "research_questions",
        "Hypothesis": "hypotheses",
        "StrategySpec": "strategies",
        "DatasetRef": "datasets",
        "Experiment": "experiments",
        "ExperimentRun": "experiment_runs",
        "ValidationResult": "validation_results",
        "ResearchReport": "reports",
        "PromotionDecision": "promotion_decisions",
    }
    return overrides.get(name, f"{name.lower()}s")


class ResearchRegistry:
    """Durable registry for research entities, backed by a storage port."""

    def __init__(self, storage: StoragePort, *, prefix: str = "registry") -> None:
        self._storage = storage
        self._prefix = prefix.strip("/")

    # -- internal helpers --------------------------------------------------

    def _key(self, entity_cls: type[BaseModel], entity_id: str, version: str) -> str:
        if not entity_id or "/" in entity_id or ".." in entity_id:
            raise RegistryError("entity id is not a safe identifier", entity_id=entity_id)
        kind = _kind_of(entity_cls)
        return f"{self._prefix}/{kind}/{entity_id}/{version}.json"

    def _prefix_for(self, entity_cls: type[BaseModel]) -> str:
        return f"{self._prefix}/{_kind_of(entity_cls)}/"

    # -- write -------------------------------------------------------------

    def put(self, entity: BaseEntity, *, overwrite: bool = False) -> str:
        """Persist ``entity``; returns the storage key. Fails closed on conflict."""
        key = self._key(type(entity), entity.id, entity.version)
        payload = entity.model_dump(mode="json")
        new_bytes = canonical_json_bytes(payload)
        if self._storage.exists(key) and not overwrite:
            existing = self._storage.read_bytes(key)
            if existing != new_bytes:
                raise RegistryError(
                    "entity identity already exists with different content",
                    key=key,
                    entity_id=entity.id,
                    version=entity.version,
                )
            return key
        self._storage.write_bytes(key, new_bytes)
        return key

    # -- read --------------------------------------------------------------

    def get(self, entity_cls: type[EntityT], entity_id: str, version: str) -> EntityT:
        """Load a single entity or fail closed."""
        key = self._key(entity_cls, entity_id, version)
        if not self._storage.exists(key):
            raise RegistryError(
                "entity not found", key=key, entity_id=entity_id, version=version
            )
        return entity_cls.model_validate(self._storage.read_json(key))  # type: ignore[attr-defined]

    def list_ids(self, entity_cls: type[BaseModel]) -> list[str]:
        """Return sorted distinct entity ids of a kind."""
        prefix = self._prefix_for(entity_cls)
        ids: list[str] = []
        for key in self._storage.list_keys(prefix):
            relative = key[len(prefix) :]
            entity_id = relative.split("/")[0]
            if entity_id and entity_id not in ids:
                ids.append(entity_id)
        return sorted(ids)

    def list_versions(self, entity_cls: type[BaseModel], entity_id: str) -> list[str]:
        """Return sorted versions available for one entity id."""
        prefix = f"{self._prefix_for(entity_cls)}{entity_id}/"
        versions = [key[len(prefix) : -len(".json")] for key in self._storage.list_keys(prefix)]
        return sorted(versions)

    def list_all(self, entity_cls: type[EntityT]) -> list[EntityT]:
        """Load every entity of a kind in deterministic order."""
        entities: list[EntityT] = []
        for entity_id in self.list_ids(entity_cls):
            for version in self.list_versions(entity_cls, entity_id):
                entities.append(self.get(entity_cls, entity_id, version))
        return entities


def _canonical(payload: object) -> bytes:
    from qrsip.infrastructure.storage import canonical_json_bytes

    return canonical_json_bytes(payload)
