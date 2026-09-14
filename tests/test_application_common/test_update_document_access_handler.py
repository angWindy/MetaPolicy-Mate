"""Unit tests for :class:`UpdateDocumentAccessHandler`.

Tests the R2 mirror logic added in the "Mirror R2 on access change" plan.

Scenarios covered:
* PUBLIC → DEPARTMENT HUST: object_key moves from public/... to hust/...
* DEPARTMENT HUST → PUBLIC: object_key moves from hust/... to public/...
* DEPARTMENT HUST → DEPARTMENT HUCE: object_key moves from hust/... to huce/...
* PUBLIC → DEPARTMENT (same key): no-op when key already aligned.
* Pre-flight failure: old key missing → ConflictException.
* Pre-flight failure: new key already occupied → ConflictException.
"""

from __future__ import annotations

import os
import sys
from datetime import date
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, call
from uuid import UUID, uuid4

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("APP_ENV", "test")

from src.application.common.exceptions.conflict_exception import (
    ConflictException,
)
from src.application.common.exceptions.not_found_exception import (
    NotFoundException,
)
from src.application.features.document_access.update.update_document_access_command import (
    UpdateDocumentAccessCommand,
)
from src.application.features.document_access.update.update_document_access_handler import (
    UpdateDocumentAccessHandler,
)
from src.domain.entities.document import Document
from src.domain.entities.document_version import DocumentVersion
from src.domain.enums.document_access_scope import (
    DocumentAccessScope as AccessScope,
)
from src.domain.enums.document_legal_status import (
    DocumentLegalStatus as LegalStatus,
)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def _doc(
    *,
    doc_id: UUID | None = None,
    document_number: str = "956/QĐ-ĐHBK",
    title: str = "Test document",
    access_scope: AccessScope = AccessScope.PUBLIC,
) -> Document:
    return Document(
        id=doc_id or uuid4(),
        document_number=document_number,
        title=title,
        issued_by="Test issuer",
        issued_date=date(2024, 1, 15),
        effective_date=date(2024, 1, 15),
        legal_status=LegalStatus.DRAFT,
        access_scope=access_scope,
        created_at=None,
        updated_at=None,
    )


def _version(
    *,
    version_id: UUID | None = None,
    document_id: UUID,
    version_number: int = 1,
    object_key: str = "public/documents/956/QĐ-ĐHBK/v1/source.pdf",
) -> DocumentVersion:
    return DocumentVersion(
        id=version_id or uuid4(),
        document_id=document_id,
        version_number=version_number,
        processing_status=MagicMock(),
        checksum="abc123",
        source_filename="source.pdf",
        object_key=object_key,
        content_type="application/pdf",
        size_bytes=12345,
    )


class _FakeBuilder:
    def __init__(self, keys: dict[tuple, str]) -> None:
        # keys: dict[(doc_number, version_number, tenant_code, access_scope)] -> key
        self._keys = keys

    def for_version(
        self,
        *,
        document_number: str,
        version_number: int,
        tenant_code: str | None,
        access_scope: str,
    ) -> str:
        key = self._keys.get(
            (document_number, version_number, tenant_code, access_scope)
        )
        if key is None:
            # Fallback: derive from access_scope
            if access_scope == "PUBLIC":
                return f"public/documents/{document_number}/v{version_number}/source.pdf"
            return f"{tenant_code}/documents/{document_number}/v{version_number}/source.pdf"
        return key


# --------------------------------------------------------------------------- #
# Test: PUBLIC → DEPARTMENT HUST (key must move)
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_public_to_department_hust_moves_r2_object():
    """When a PUBLIC doc becomes DEPARTMENT HUST, R2 key moves to hust/..."""
    doc_id = uuid4()
    version_id = uuid4()
    hust_dept_id = uuid4()

    document = _doc(
        doc_id=doc_id,
        access_scope=AccessScope.PUBLIC,
    )
    version = _version(
        version_id=version_id,
        document_id=doc_id,
        object_key="public/documents/956/QĐ-ĐHBK/v1/source.pdf",
    )

    doc_repo = AsyncMock()
    doc_repo.get_by_id.return_value = document
    doc_repo.update_object_key = AsyncMock()

    dept_repo = AsyncMock()
    dept = MagicMock()
    dept.code = "HUST"
    dept.is_active = True
    dept_repo.get_by_id.return_value = dept

    doc_dept_repo = AsyncMock()
    digitization_repo = AsyncMock()
    version_repo = AsyncMock()
    version_repo.list_by_document_id.return_value = [version]

    file_storage = AsyncMock()
    # old key exists, new key does not
    async def _head(key: str):
        if key == "public/documents/956/QĐ-ĐHBK/v1/source.pdf":
            return {"ContentLength": 12345}
        return None
    file_storage.head_object = _head
    file_storage.copy_object = AsyncMock()

    rag_index = AsyncMock()
    uow = AsyncMock()

    builder = _FakeBuilder({
        ("956/QĐ-ĐHBK", 1, "hust", "DEPARTMENT"): (
            "hust/documents/956/QĐ-ĐHBK/v1/source.pdf"
        ),
    })

    handler = UpdateDocumentAccessHandler(
        document_repository=doc_repo,
        department_repository=dept_repo,
        document_department_repository=doc_dept_repo,
        digitization_repository=digitization_repo,
        document_version_repository=version_repo,
        file_storage=file_storage,
        object_key_builder=builder,
        rag_index_service=rag_index,
        unit_of_work=uow,
    )

    cmd = UpdateDocumentAccessCommand(
        document_id=doc_id,
        access_scope=AccessScope.DEPARTMENT,
        department_ids=[hust_dept_id],
    )

    result = await handler.handle(cmd)

    assert result is True

    # Neon committed
    uow.save_changes.assert_awaited_once()

    # R2 copy called
    file_storage.copy_object.assert_awaited_once_with(
        source_key="public/documents/956/QĐ-ĐHBK/v1/source.pdf",
        dest_key="hust/documents/956/QĐ-ĐHBK/v1/source.pdf",
    )

    # DB object_key updated
    doc_repo.update_object_key.assert_awaited_once_with(
        version_id=version_id,
        new_key="hust/documents/956/QĐ-ĐHBK/v1/source.pdf",
    )

    # Qdrant synced
    rag_index.update_document_access.assert_awaited_once()


# --------------------------------------------------------------------------- #
# Test: DEPARTMENT HUST → PUBLIC (key must move)
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_department_hust_to_public_moves_r2_object():
    """When a DEPARTMENT HUST doc becomes PUBLIC, R2 key moves to public/..."""
    doc_id = uuid4()
    version_id = uuid4()

    document = _doc(
        doc_id=doc_id,
        access_scope=AccessScope.DEPARTMENT,
    )
    version = _version(
        version_id=version_id,
        document_id=doc_id,
        object_key="hust/documents/956/QĐ-ĐHBK/v1/source.pdf",
    )

    doc_repo = AsyncMock()
    doc_repo.get_by_id.return_value = document
    doc_repo.update_object_key = AsyncMock()

    dept_repo = AsyncMock()
    digitization_repo = AsyncMock()
    version_repo = AsyncMock()
    version_repo.list_by_document_id.return_value = [version]

    file_storage = AsyncMock()

    async def _head(key: str):
        if key == "hust/documents/956/QĐ-ĐHBK/v1/source.pdf":
            return {"ContentLength": 12345}
        return None

    file_storage.head_object = _head
    file_storage.copy_object = AsyncMock()

    rag_index = AsyncMock()
    uow = AsyncMock()

    builder = _FakeBuilder({})

    handler = UpdateDocumentAccessHandler(
        document_repository=doc_repo,
        department_repository=dept_repo,
        document_department_repository=digitization_repo,
        digitization_repository=digitization_repo,
        document_version_repository=version_repo,
        file_storage=file_storage,
        object_key_builder=builder,
        rag_index_service=rag_index,
        unit_of_work=uow,
    )

    cmd = UpdateDocumentAccessCommand(
        document_id=doc_id,
        access_scope=AccessScope.PUBLIC,
        department_ids=[],
    )

    result = await handler.handle(cmd)

    assert result is True

    file_storage.copy_object.assert_awaited_once_with(
        source_key="hust/documents/956/QĐ-ĐHBK/v1/source.pdf",
        dest_key="public/documents/956/QĐ-ĐHBK/v1/source.pdf",
    )

    doc_repo.update_object_key.assert_awaited_once_with(
        version_id=version_id,
        new_key="public/documents/956/QĐ-ĐHBK/v1/source.pdf",
    )


# --------------------------------------------------------------------------- #
# Test: DEPARTMENT HUST → DEPARTMENT HUCE (key must move)
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_department_hust_to_huce_moves_r2_object():
    """DEPARTMENT HUST → DEPARTMENT HUCE moves key from hust/.. to huce/..."""
    doc_id = uuid4()
    version_id = uuid4()
    huce_dept_id = uuid4()

    document = _doc(
        doc_id=doc_id,
        access_scope=AccessScope.DEPARTMENT,
    )
    version = _version(
        version_id=version_id,
        document_id=doc_id,
        object_key="hust/documents/956/QĐ-ĐHBK/v1/source.pdf",
    )

    doc_repo = AsyncMock()
    doc_repo.get_by_id.return_value = document
    doc_repo.update_object_key = AsyncMock()

    huce_dept = MagicMock()
    huce_dept.code = "HUCE"
    huce_dept.is_active = True
    dept_repo = AsyncMock()
    dept_repo.get_by_id.return_value = huce_dept

    doc_dept_repo = AsyncMock()
    digitization_repo = AsyncMock()
    version_repo = AsyncMock()
    version_repo.list_by_document_id.return_value = [version]

    file_storage = AsyncMock()

    async def _head(key: str):
        if key == "hust/documents/956/QĐ-ĐHBK/v1/source.pdf":
            return {"ContentLength": 12345}
        return None

    file_storage.head_object = _head
    file_storage.copy_object = AsyncMock()

    rag_index = AsyncMock()
    uow = AsyncMock()

    builder = _FakeBuilder({})

    handler = UpdateDocumentAccessHandler(
        document_repository=doc_repo,
        department_repository=dept_repo,
        document_department_repository=doc_dept_repo,
        digitization_repository=digitization_repo,
        document_version_repository=version_repo,
        file_storage=file_storage,
        object_key_builder=builder,
        rag_index_service=rag_index,
        unit_of_work=uow,
    )

    cmd = UpdateDocumentAccessCommand(
        document_id=doc_id,
        access_scope=AccessScope.DEPARTMENT,
        department_ids=[huce_dept_id],
    )

    result = await handler.handle(cmd)

    assert result is True

    file_storage.copy_object.assert_awaited_once_with(
        source_key="hust/documents/956/QĐ-ĐHBK/v1/source.pdf",
        dest_key="huce/documents/956/QĐ-ĐHBK/v1/source.pdf",
    )


# --------------------------------------------------------------------------- #
# Test: key already aligned → no R2 operation
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_key_already_aligned_skips_r2():
    """When old_key == new_key, copy is skipped."""
    doc_id = uuid4()
    version_id = uuid4()

    document = _doc(
        doc_id=doc_id,
        access_scope=AccessScope.PUBLIC,
    )
    # Already under public/.. so PUBLIC scope matches
    version = _version(
        version_id=version_id,
        document_id=doc_id,
        object_key="public/documents/956/QĐ-ĐHBK/v1/source.pdf",
    )

    doc_repo = AsyncMock()
    doc_repo.get_by_id.return_value = document
    doc_repo.update_object_key = AsyncMock()

    dept_repo = AsyncMock()
    doc_dept_repo = AsyncMock()
    digitization_repo = AsyncMock()
    version_repo = AsyncMock()
    version_repo.list_by_document_id.return_value = [version]

    file_storage = AsyncMock()
    rag_index = AsyncMock()
    uow = AsyncMock()
    builder = _FakeBuilder({})

    handler = UpdateDocumentAccessHandler(
        document_repository=doc_repo,
        department_repository=dept_repo,
        document_department_repository=doc_dept_repo,
        digitization_repository=digitization_repo,
        document_version_repository=version_repo,
        file_storage=file_storage,
        object_key_builder=builder,
        rag_index_service=rag_index,
        unit_of_work=uow,
    )

    # Change from PUBLIC → PUBLIC (no-op)
    cmd = UpdateDocumentAccessCommand(
        document_id=doc_id,
        access_scope=AccessScope.PUBLIC,
        department_ids=[],
    )

    await handler.handle(cmd)

    file_storage.copy_object.assert_not_called()
    doc_repo.update_object_key.assert_not_called()
    rag_index.update_document_access.assert_awaited_once()


# --------------------------------------------------------------------------- #
# Test: old key missing → ConflictException
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_old_key_missing_raises_conflict():
    """Pre-flight fails when old key is absent in R2 → 409."""
    doc_id = uuid4()
    version_id = uuid4()
    hust_dept_id = uuid4()

    document = _doc(
        doc_id=doc_id,
        access_scope=AccessScope.PUBLIC,
    )
    version = _version(
        version_id=version_id,
        document_id=doc_id,
        object_key="public/documents/OLD/v1/source.pdf",
    )

    doc_repo = AsyncMock()
    doc_repo.get_by_id.return_value = document
    doc_repo.update_object_key = AsyncMock()

    hust_dept = MagicMock()
    hust_dept.code = "HUST"
    hust_dept.is_active = True
    dept_repo = AsyncMock()
    dept_repo.get_by_id.return_value = hust_dept

    doc_dept_repo = AsyncMock()
    digitization_repo = AsyncMock()
    version_repo = AsyncMock()
    version_repo.list_by_document_id.return_value = [version]

    file_storage = AsyncMock()
    file_storage.head_object = AsyncMock(return_value=None)  # old key missing
    file_storage.copy_object = AsyncMock()

    rag_index = AsyncMock()
    uow = AsyncMock()
    uow.save_changes = AsyncMock()

    builder = _FakeBuilder({})

    handler = UpdateDocumentAccessHandler(
        document_repository=doc_repo,
        department_repository=dept_repo,
        document_department_repository=doc_dept_repo,
        digitization_repository=digitization_repo,
        document_version_repository=version_repo,
        file_storage=file_storage,
        object_key_builder=builder,
        rag_index_service=rag_index,
        unit_of_work=uow,
    )

    cmd = UpdateDocumentAccessCommand(
        document_id=doc_id,
        access_scope=AccessScope.DEPARTMENT,
        department_ids=[hust_dept_id],
    )

    with pytest.raises(ConflictException) as exc_info:
        await handler.handle(cmd)

    assert "source PDF not found" in str(exc_info.value)

    file_storage.copy_object.assert_not_called()
    doc_repo.update_object_key.assert_not_called()


# --------------------------------------------------------------------------- #
# Test: new key already occupied → ConflictException
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_new_key_occupied_with_different_content_raises_conflict():
    """Pre-flight fails when new key has DIFFERENT content → 409.
    If new key has the SAME content (same ETag or same size), we
    treat it as already-aligned and just update the DB.
    """
    doc_id = uuid4()
    version_id = uuid4()
    hust_dept_id = uuid4()

    document = _doc(
        doc_id=doc_id,
        access_scope=AccessScope.PUBLIC,
    )
    version = _version(
        version_id=version_id,
        document_id=doc_id,
        object_key="public/documents/956/QĐ-ĐHBK/v1/source.pdf",
    )

    doc_repo = AsyncMock()
    doc_repo.get_by_id.return_value = document
    doc_repo.update_object_key = AsyncMock()

    hust_dept = MagicMock()
    hust_dept.code = "HUST"
    hust_dept.is_active = True
    dept_repo = AsyncMock()
    dept_repo.get_by_id.return_value = hust_dept

    doc_dept_repo = AsyncMock()
    digitization_repo = AsyncMock()
    version_repo = AsyncMock()
    version_repo.list_by_document_id.return_value = [version]

    file_storage = AsyncMock()

    async def _head(key: str):
        if key == "public/documents/956/QĐ-ĐHBK/v1/source.pdf":
            return {"ContentLength": 12345, "ETag": "etag-A"}
        if key == "hust/documents/956/QĐ-ĐHBK/v1/source.pdf":
            # DIFFERENT content - different size and ETag.
            return {"ContentLength": 67890, "ETag": "etag-B"}
        return None

    file_storage.head_object = _head
    file_storage.copy_object = AsyncMock()

    rag_index = AsyncMock()
    uow = AsyncMock()
    uow.save_changes = AsyncMock()

    builder = _FakeBuilder({})

    handler = UpdateDocumentAccessHandler(
        document_repository=doc_repo,
        department_repository=dept_repo,
        document_department_repository=doc_dept_repo,
        digitization_repository=digitization_repo,
        document_version_repository=version_repo,
        file_storage=file_storage,
        object_key_builder=builder,
        rag_index_service=rag_index,
        unit_of_work=uow,
    )

    cmd = UpdateDocumentAccessCommand(
        document_id=doc_id,
        access_scope=AccessScope.DEPARTMENT,
        department_ids=[hust_dept_id],
    )

    with pytest.raises(ConflictException) as exc_info:
        await handler.handle(cmd)

    assert "different content" in str(exc_info.value).lower()

    file_storage.copy_object.assert_not_called()


@pytest.mark.asyncio
async def test_new_key_occupied_with_same_content_skips_copy():
    """When new key already has the SAME content (same ETag/size),
    we skip the R2 copy and just update the DB object_key."""
    doc_id = uuid4()
    version_id = uuid4()
    hust_dept_id = uuid4()

    document = _doc(
        doc_id=doc_id,
        access_scope=AccessScope.PUBLIC,
    )
    version = _version(
        version_id=version_id,
        document_id=doc_id,
        object_key="public/documents/956/QĐ-ĐHBK/v1/source.pdf",
    )

    doc_repo = AsyncMock()
    doc_repo.get_by_id.return_value = document
    doc_repo.update_object_key = AsyncMock()

    hust_dept = MagicMock()
    hust_dept.code = "HUST"
    hust_dept.is_active = True
    dept_repo = AsyncMock()
    dept_repo.get_by_id.return_value = hust_dept

    doc_dept_repo = AsyncMock()
    digitization_repo = AsyncMock()
    version_repo = AsyncMock()
    version_repo.list_by_document_id.return_value = [version]

    file_storage = AsyncMock()

    async def _head(key: str):
        # Both keys return the SAME ETag + size.
        return {
            "ContentLength": 686996,
            "ETag": '"0d844cd7b2188edbd52737a7d2afed6c"',
        }

    file_storage.head_object = _head
    file_storage.copy_object = AsyncMock()

    rag_index = AsyncMock()
    uow = AsyncMock()

    builder = _FakeBuilder({})

    handler = UpdateDocumentAccessHandler(
        document_repository=doc_repo,
        department_repository=dept_repo,
        document_department_repository=doc_dept_repo,
        digitization_repository=digitization_repo,
        document_version_repository=version_repo,
        file_storage=file_storage,
        object_key_builder=builder,
        rag_index_service=rag_index,
        unit_of_work=uow,
    )

    cmd = UpdateDocumentAccessCommand(
        document_id=doc_id,
        access_scope=AccessScope.DEPARTMENT,
        department_ids=[hust_dept_id],
    )

    await handler.handle(cmd)

    # No copy because the bytes are already aligned.
    file_storage.copy_object.assert_not_called()
    # DB updated though.
    doc_repo.update_object_key.assert_awaited_once_with(
        version_id=version_id,
        new_key="hust/documents/956/QĐ-ĐHBK/v1/source.pdf",
    )


# --------------------------------------------------------------------------- #
# Test: document not found → NotFoundException
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_document_not_found():
    """Returns 404 when the document does not exist."""
    doc_id = uuid4()

    doc_repo = AsyncMock()
    doc_repo.get_by_id.return_value = None

    dept_repo = AsyncMock()
    doc_dept_repo = AsyncMock()
    digitization_repo = AsyncMock()
    version_repo = AsyncMock()
    file_storage = AsyncMock()
    rag_index = AsyncMock()
    uow = AsyncMock()
    builder = _FakeBuilder({})

    handler = UpdateDocumentAccessHandler(
        document_repository=doc_repo,
        department_repository=dept_repo,
        document_department_repository=doc_dept_repo,
        digitization_repository=digitization_repo,
        document_version_repository=version_repo,
        file_storage=file_storage,
        object_key_builder=builder,
        rag_index_service=rag_index,
        unit_of_work=uow,
    )

    cmd = UpdateDocumentAccessCommand(
        document_id=doc_id,
        access_scope=AccessScope.PUBLIC,
        department_ids=[],
    )

    with pytest.raises(NotFoundException):
        await handler.handle(cmd)


# --------------------------------------------------------------------------- #
# Test: DEPARTMENT scope without departments → ConflictException
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_department_scope_without_departments():
    """DEPARTMENT scope requires at least one department_id."""
    doc_id = uuid4()

    document = _doc(
        doc_id=doc_id,
        access_scope=AccessScope.PUBLIC,
    )

    doc_repo = AsyncMock()
    doc_repo.get_by_id.return_value = document

    dept_repo = AsyncMock()
    doc_dept_repo = AsyncMock()
    digitization_repo = AsyncMock()
    version_repo = AsyncMock()
    file_storage = AsyncMock()
    rag_index = AsyncMock()
    uow = AsyncMock()
    builder = _FakeBuilder({})

    handler = UpdateDocumentAccessHandler(
        document_repository=doc_repo,
        department_repository=dept_repo,
        document_department_repository=doc_dept_repo,
        digitization_repository=digitization_repo,
        document_version_repository=version_repo,
        file_storage=file_storage,
        object_key_builder=builder,
        rag_index_service=rag_index,
        unit_of_work=uow,
    )

    cmd = UpdateDocumentAccessCommand(
        document_id=doc_id,
        access_scope=AccessScope.DEPARTMENT,
        department_ids=[],  # empty!
    )

    with pytest.raises(ConflictException):
        await handler.handle(cmd)
