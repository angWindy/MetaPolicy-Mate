from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from src.security.metadata_contract import (
    assert_metadata_consistent,
    derive_security_acl,
    metadata_consistency_errors,
    validate_index_payload,
)


AS_OF = datetime(2026, 8, 20, tzinfo=UTC)


def valid_payload() -> dict:
    return {
        "tenant_id": "tenant-a",
        "document_id": "document-1",
        "version_id": "version-1",
        "chunk_id": "chunk-1",
        "owner_unit": "TCCB",
        "status": "published",
        "legal_status": "effective",
        "classification": "internal",
        "allowed_roles": ["staff", "manager"],
        "allowed_units": ["TCCB"],
        "valid_from": "2026-01-01T00:00:00Z",
        "valid_to": None,
        "content_hash": "sha256:abc",
        "embedding_model": "test-embedding",
        "embedding_version": "1",
        "sparse_model": "hashed-lexical",
        "sparse_version": "1",
        "index_version": "test-index-v1",
    }


def validate(value: dict, *, status: str = "approved", version: int = 1):
    return validate_index_payload(
        value,
        processing_status=status,
        version_number=version,
        as_of=AS_OF,
    )


def test_valid_public_document_is_indexable_with_explicit_acl():
    value = valid_payload()
    value.update(
        classification="public",
        allowed_roles=["*"],
        allowed_units=["*"],
    )
    assert validate(value).tenant_id == "tenant-a"


@pytest.mark.parametrize("processing_status", ["received", "review_required", "failed"])
def test_unapproved_document_is_rejected(processing_status):
    with pytest.raises(ValueError, match="approved"):
        validate(valid_payload(), status=processing_status)


@pytest.mark.parametrize("publication_status", ["draft", "approved", ""])
def test_unpublished_payload_is_rejected(publication_status):
    value = valid_payload()
    value["status"] = publication_status
    with pytest.raises(ValidationError):
        validate(value)


@pytest.mark.parametrize(
    "legal_status", ["draft", "scheduled", "superseded", "expired", "revoked"]
)
def test_invalid_publication_state_is_rejected(legal_status):
    value = valid_payload()
    value["legal_status"] = legal_status
    with pytest.raises(ValueError, match="effective"):
        validate(value)


@pytest.mark.parametrize(
    "field",
    [
        "tenant_id",
        "status",
        "classification",
        "allowed_roles",
        "allowed_units",
        "valid_from",
    ],
)
def test_missing_security_metadata_is_rejected(field):
    value = valid_payload()
    value.pop(field)
    with pytest.raises(ValidationError):
        validate(value)


@pytest.mark.parametrize(
    ("field", "invalid"),
    [
        ("tenant_id", 123),
        ("allowed_roles", "staff"),
        ("allowed_units", {"TCCB"}),
        ("valid_from", ["2026-01-01"]),
    ],
)
def test_invalid_metadata_types_are_rejected(field, invalid):
    value = valid_payload()
    value[field] = invalid
    with pytest.raises((TypeError, ValidationError)):
        validate(value)


@pytest.mark.parametrize("version", [0, -1, True, "1"])
def test_invalid_version_is_rejected(version):
    with pytest.raises(ValueError, match="version_number"):
        validate(valid_payload(), version=version)


def test_not_yet_effective_document_is_rejected():
    value = valid_payload()
    value["valid_from"] = "2026-08-21T00:00:00Z"
    with pytest.raises(ValueError, match="not yet effective"):
        validate(value)


def test_expired_document_is_rejected():
    value = valid_payload()
    value["valid_to"] = "2026-08-19T00:00:00Z"
    with pytest.raises(ValueError, match="Expired"):
        validate(value)


@pytest.mark.parametrize(
    ("field", "different"),
    [
        ("tenant_id", "tenant-b"),
        ("status", "draft"),
        ("version_id", "version-2"),
        ("allowed_roles", ["manager"]),
        ("allowed_units", ["OTHER"]),
    ],
)
def test_postgres_qdrant_mismatch_is_rejected(field, different):
    postgres = valid_payload()
    qdrant = deepcopy(postgres)
    qdrant[field] = different
    assert f"metadata_mismatch:{field}" in metadata_consistency_errors(postgres, qdrant)
    with pytest.raises(ValueError, match="metadata mismatch"):
        assert_metadata_consistent(postgres, qdrant)


def test_wrong_tenant_is_never_treated_as_consistent():
    postgres = valid_payload()
    qdrant = {**postgres, "tenant_id": "other-tenant"}
    with pytest.raises(ValueError, match="tenant_id"):
        assert_metadata_consistent(postgres, qdrant)


def test_department_acl_requires_units_and_restricted_is_not_public():
    with pytest.raises(ValueError, match="allowed_departments"):
        derive_security_acl("department", [])
    roles, units, classification = derive_security_acl(
        "restricted", [], owner_unit="LEGAL"
    )
    assert roles == ["restricted_reader"]
    assert units == ["LEGAL"]
    assert classification == "restricted"
