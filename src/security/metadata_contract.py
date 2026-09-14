"""Shared fail-closed metadata checks for indexing and retrieval consistency."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from src.domain.schemas import ProcessingStatus, QdrantPayload

SECURITY_METADATA_FIELDS = frozenset(
    {
        "tenant_id",
        "status",
        "classification",
        "allowed_roles",
        "allowed_units",
        "valid_from",
    }
)

INDEX_CONSISTENCY_FIELDS = (
    "tenant_id",
    "document_id",
    "version_id",
    "chunk_id",
    "status",
    "classification",
    "allowed_roles",
    "allowed_units",
    "valid_from",
    "valid_to",
    "content_hash",
    "index_version",
)


def derive_security_acl(
    access_level: str,
    allowed_departments: list[str] | None,
    *,
    owner_unit: str | None = None,
) -> tuple[list[str], list[str], str]:
    """Translate the database access model into an explicit index ACL."""

    level = access_level.strip().lower() if isinstance(access_level, str) else ""
    units = [item.strip().upper() for item in (allowed_departments or []) if item.strip()]
    if level == "public":
        return ["*"], ["*"], "public"
    if level == "internal":
        return ["staff", "manager", "data_owner"], ["*"], "internal"
    if level == "department":
        if not units:
            raise ValueError("Department documents require allowed_departments.")
        return ["staff", "manager", "data_owner"], units, "internal"
    if level == "restricted":
        if not units and isinstance(owner_unit, str) and owner_unit.strip():
            units = [owner_unit.strip().upper()]
        if not units:
            raise ValueError("Restricted documents require an explicit unit ACL.")
        return ["restricted_reader"], units, "restricted"
    raise ValueError(f"Unsupported access_level: {access_level!r}")


def validate_security_metadata(value: Mapping[str, Any]) -> dict[str, Any]:
    """Validate the mandatory citation/retrieval ACL contract.

    Returns a dict containing the validated security fields. Raises
    ``ValueError`` if any required field is missing or has the wrong
    type. We validate the security subset directly because the legacy
    ``SecurityMetadata`` Pydantic model was removed during the Qdrant
    payload refactor — the security fields are now a logical subset
    of ``QdrantPayload``.
    """
    payload = dict(value)
    missing = [
        field
        for field in SECURITY_METADATA_FIELDS
        if field not in payload or payload[field] in (None, "")
    ]
    if missing:
        raise ValueError(
            "Security metadata is missing required fields: " + ", ".join(missing)
        )
    if not isinstance(payload.get("allowed_roles"), list):
        raise TypeError("allowed_roles must be a list.")
    if not isinstance(payload.get("allowed_units"), list):
        raise TypeError("allowed_units must be a list.")
    return {field: payload[field] for field in SECURITY_METADATA_FIELDS}


def validate_index_payload(
    value: Mapping[str, Any],
    *,
    processing_status: str,
    version_number: int,
    as_of: datetime | None = None,
) -> QdrantPayload:
    """Reject a payload before any vector-store write occurs."""

    if processing_status not in {
        ProcessingStatus.APPROVED.value,
        ProcessingStatus.PUBLISHED.value,
    }:
        raise ValueError("Only an approved or previously published version may be indexed.")
    if not isinstance(version_number, int) or isinstance(version_number, bool) or version_number < 1:
        raise ValueError("version_number must be a positive integer.")
    # ``legal_status`` is checked against the raw input dict because
    # QdrantPayload.model_validate strips unknown fields; the legal
    # status is part of the document_versions row, not the vector payload.
    if value.get("legal_status") != "effective":
        raise ValueError("Only an effective publication may be indexed.")
    payload = QdrantPayload.model_validate(dict(value))
    target = as_of or datetime.now(UTC)
    if target.tzinfo is None:
        target = target.replace(tzinfo=UTC)
    valid_from = payload.valid_from
    if valid_from.tzinfo is None:
        valid_from = valid_from.replace(tzinfo=UTC)
    valid_to = payload.valid_to
    if valid_to is not None and valid_to.tzinfo is None:
        valid_to = valid_to.replace(tzinfo=UTC)
    if valid_from > target:
        raise ValueError("Document is not yet effective and cannot be indexed.")
    if valid_to is not None and valid_to <= target:
        raise ValueError("Expired document cannot be indexed.")
    return payload


def metadata_consistency_errors(
    postgres_metadata: Mapping[str, Any],
    qdrant_metadata: Mapping[str, Any],
) -> list[str]:
    """Return critical PostgreSQL/Qdrant field mismatches."""

    errors: list[str] = []
    postgres_security: dict[str, Any] | None = None
    qdrant_security: dict[str, Any] | None = None
    try:
        postgres_security = validate_security_metadata(postgres_metadata).model_dump(mode="json")
    except (TypeError, ValueError):
        errors.append("postgres_metadata_invalid")
    try:
        qdrant_security = validate_security_metadata(qdrant_metadata).model_dump(mode="json")
    except (TypeError, ValueError):
        errors.append("qdrant_metadata_invalid")
    for field in INDEX_CONSISTENCY_FIELDS:
        postgres_value = (
            postgres_security.get(field)
            if postgres_security is not None and field in SECURITY_METADATA_FIELDS | {"valid_to"}
            else postgres_metadata.get(field)
        )
        qdrant_value = (
            qdrant_security.get(field)
            if qdrant_security is not None and field in SECURITY_METADATA_FIELDS | {"valid_to"}
            else qdrant_metadata.get(field)
        )
        if postgres_value != qdrant_value:
            errors.append(f"metadata_mismatch:{field}")
    return list(dict.fromkeys(errors))


def assert_metadata_consistent(
    postgres_metadata: Mapping[str, Any],
    qdrant_metadata: Mapping[str, Any],
) -> None:
    errors = metadata_consistency_errors(postgres_metadata, qdrant_metadata)
    if errors:
        raise ValueError("PostgreSQL/Qdrant metadata mismatch: " + ", ".join(errors))


__all__ = [
    "INDEX_CONSISTENCY_FIELDS",
    "SECURITY_METADATA_FIELDS",
    "assert_metadata_consistent",
    "derive_security_acl",
    "metadata_consistency_errors",
    "validate_index_payload",
    "validate_security_metadata",
]
