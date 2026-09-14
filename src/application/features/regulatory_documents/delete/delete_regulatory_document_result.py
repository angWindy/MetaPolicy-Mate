from dataclasses import dataclass, field


@dataclass(frozen=True)
class DeleteRegulatoryDocumentResult:
    deleted: bool
    qdrant_points_removed: int
    versions_deleted: int
    storage_objects_deleted: int
    # Errors surfaced from the cascade-down phase. The endpoint
    # returns ``200`` when this list is empty (clean success) and
    # ``207 Multi-Status`` when any cleanup step failed. The DB rows
    # are still removed so the document is gone from the API surface
    # either way — partial-failure is a hint to the operator that
    # storage or Qdrant may have residual artifacts.
    errors: list[str] = field(default_factory=list)
