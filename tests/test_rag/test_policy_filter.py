import uuid
import warnings
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from src.domain.schemas import (
    ClassificationLevel,
    QdrantPayload,
    QdrantPointInput,
    SparseVectorData,
)
from src.models.schemas import ChatRequest
from src.rag.config import RAGSettings
from src.retrieval.vector_store import QdrantVectorStore
from src.security.policy import (
    POLICY_VERSION,
    AuthenticatedIdentity,
    audit_access_decision,
    build_access_filter,
    build_user_context,
    can_access_document,
    resolve_clearance_level,
    resolve_effective_roles,
)

AS_OF = datetime(2026, 8, 4, tzinfo=UTC)


class AuditRecorder:
    def __init__(self):
        self.records: list[dict] = []

    def create_audit_log(self, **record):
        self.records.append(record)


def authenticated_user(*roles: str, clearance=None):
    return build_user_context(
        AuthenticatedIdentity(
            user_id="user-1",
            tenant_id="tenant-a",
            department="UNIT-A",
            assigned_roles=frozenset(roles or {"staff"}),
            granted_clearance=clearance,
        )
    )


def payload(**overrides) -> QdrantPayload:
    values = {
        "tenant_id": "tenant-a",
        "document_id": str(uuid.uuid4()),
        "version_id": str(uuid.uuid4()),
        "chunk_id": str(uuid.uuid4()),
        "parent_chunk_id": None,
        "previous_chunk_id": None,
        "next_chunk_id": None,
        "owner_unit": "UNIT-A",
        "allowed_roles": ["staff"],
        "allowed_units": ["UNIT-A"],
        "classification": "internal",
        "status": "published",
        "valid_from": "2026-01-01T00:00:00Z",
        "valid_to": None,
        "page": 1,
        "section": "Điều 1",
        "content_hash": f"sha256:{uuid.uuid4().hex}",
        "embedding_model": "test-embedding",
        "embedding_version": "test-v1",
        "sparse_model": "hashed-lexical",
        "sparse_version": "test-v1",
        "index_version": "test-index-v1",
    }
    values.update(overrides)
    return QdrantPayload.model_validate(values)


def point(document: QdrantPayload) -> QdrantPointInput:
    return QdrantPointInput(
        payload=document,
        dense_vector=[0.125] * 32,
        sparse_vector=SparseVectorData(indices=[1], values=[1.0]),
    )


def build_store() -> QdrantVectorStore:
    return QdrantVectorStore(
        RAGSettings(
            app_env="test",
            vector_backend="qdrant",
            qdrant_local_path=":memory:",
            qdrant_collection=f"policy-{uuid.uuid4()}",
            embedding_dimensions=32,
        )
    )


def test_build_user_context_uses_only_authenticated_identity():
    roles = resolve_effective_roles(["manager"])
    assert roles == {"manager", "staff"}
    assert resolve_clearance_level(roles) == ClassificationLevel.INTERNAL
    with pytest.raises(PermissionError):
        build_user_context(
            AuthenticatedIdentity(
                user_id="user-1",
                tenant_id="tenant-a",
                department="UNIT-A",
                is_authenticated=False,
            )
        )


def test_chat_request_rejects_client_supplied_allowed_roles():
    with pytest.raises(ValidationError):
        ChatRequest.model_validate(
            {"message": "Nội dung quy định?", "allowed_roles": ["admin"]}
        )


@pytest.mark.parametrize(
    "document",
    [
        payload(tenant_id="tenant-b"),
        payload(allowed_roles=["manager"], allowed_units=["UNIT-B"]),
        {**payload().model_dump(mode="json"), "status": "draft"},
        payload(valid_to="2026-08-04T00:00:00Z"),
        payload(classification="confidential"),
    ],
    ids=["cross-tenant", "cross-department", "draft", "expired", "confidential"],
)
def test_can_access_document_denies_unauthorized_cases(document):
    assert not can_access_document(authenticated_user("staff"), document, as_of=AS_OF)


def test_security_admin_has_no_implicit_confidential_access():
    user = authenticated_user("security_admin")
    document = payload(
        classification="confidential",
        allowed_roles=["security_admin"],
        allowed_units=["UNIT-A"],
    )
    assert user.clearance_level == ClassificationLevel.INTERNAL
    assert not can_access_document(user, document, as_of=AS_OF)


def test_include_historical_is_explicit_and_defaults_to_false():
    user = authenticated_user("staff")
    expired = payload(valid_to="2026-01-01T00:00:00Z")
    assert not can_access_document(user, expired, as_of=AS_OF)
    assert can_access_document(user, expired, as_of=AS_OF, include_historical=True)


@pytest.mark.asyncio
async def test_qdrant_receives_policy_filter_and_returns_zero_unauthorized_chunks():
    store = build_store()
    authorized = payload()
    unauthorized = [
        payload(tenant_id="tenant-b"),
        payload(allowed_roles=["manager"], allowed_units=["UNIT-B"]),
        payload(valid_to="2026-08-04T00:00:00Z"),
        payload(classification="confidential"),
    ]
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        await store.upsert_chunks(
            [point(authorized), *(point(item) for item in unauthorized)]
        )
    user = authenticated_user("staff")
    access_filter = build_access_filter(user, as_of=AS_OF)
    query_points = AsyncMock(wraps=store.client.query_points)
    store.client.query_points = query_points

    results = await store.search(
        [0.125] * 32,
        limit=20,
        query_filter=access_filter,
    )

    assert query_points.await_args.kwargs["query_filter"] is access_filter
    assert [chunk_id for chunk_id, _score, _payload in results] == [
        authorized.chunk_id
    ]
    unauthorized_ids = {item.chunk_id for item in unauthorized}
    returned_ids = {chunk_id for chunk_id, _score, _payload in results}
    assert not returned_ids.intersection(unauthorized_ids)


def test_audit_access_decision_records_allow_deny_and_policy_version():
    recorder = AuditRecorder()
    user = authenticated_user("staff")
    document = payload()

    audit_access_decision(
        recorder,
        request_id="request-allow",
        user=user,
        document=document,
        allowed=True,
        reason="policy_match",
    )
    audit_access_decision(
        recorder,
        request_id="request-deny",
        user=user,
        document=document,
        allowed=False,
        reason="classification_denied",
    )

    assert [record["outcome"] for record in recorder.records] == ["allow", "deny"]
    assert all(
        record["metadata"]["policy_version"] == POLICY_VERSION
        for record in recorder.records
    )
