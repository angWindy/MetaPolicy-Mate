from __future__ import annotations

import hashlib
import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any

from sqlalchemy import select

from src.db.models import Chunk, Document, DocumentVersion, Section
from src.domain.schemas import LegalStatus, ProcessingStatus
from src.retrieval.vector_store import VectorRecord
from src.services.embeddings import content_hash_for_text

if TYPE_CHECKING:
    from src.rag.container import RAGContainer


def load_regression_corpus(path: str | Path) -> dict[str, Any]:
    source = Path(path)
    corpus = json.loads(source.read_text(encoding="utf-8"))
    if corpus.get("dataset_kind") != "synthetic_regression":
        raise ValueError("Regression seed accepts only dataset_kind=synthetic_regression.")
    documents = corpus.get("documents")
    if not isinstance(documents, list) or not documents:
        raise ValueError("Regression corpus must contain at least one document.")
    if any(not str(item.get("document_number", "")).startswith("EVAL-") for item in documents):
        raise ValueError("Regression document numbers must use the reserved EVAL- prefix.")
    return corpus


def _date(value: str | None) -> date | None:
    return date.fromisoformat(value) if value else None


def _valid_from(value: date | None) -> str:
    return f"{(value or date(1970, 1, 1)).isoformat()}T00:00:00Z"


def _valid_to(value: date | None) -> str | None:
    if value is None:
        return None
    return f"{(value + timedelta(days=1)).isoformat()}T00:00:00Z"


def _acl(document: dict[str, Any]) -> tuple[list[str], list[str], str]:
    access_level = document["access_level"]
    if access_level == "public":
        return ["*"], ["*"], "public"
    if access_level == "department":
        return ["staff", "manager", "data_owner"], list(document["allowed_departments"]), "internal"
    if access_level == "restricted":
        return ["restricted_reader"], list(document["allowed_departments"]), "restricted"
    return ["staff", "manager", "data_owner"], ["*"], "internal"


def _payload(
    *,
    tenant_id: str,
    collection: str,
    document: dict[str, Any],
    version: dict[str, Any],
    chunk: dict[str, Any],
    chunk_index: int,
    previous_chunk_id: str | None,
    next_chunk_id: str | None,
    embedding_model: str,
    embedding_version: str,
) -> tuple[dict[str, Any], str, str]:
    text = chunk["text"]
    digest = content_hash_for_text(text)
    allowed_roles, allowed_units, classification = _acl(document)
    payload = {
        "tenant_id": tenant_id,
        "document_id": document["id"],
        "version_id": version["id"],
        "chunk_id": chunk["id"],
        "parent_chunk_id": None,
        "previous_chunk_id": previous_chunk_id,
        "next_chunk_id": next_chunk_id,
        "owner_unit": document["owner_department"],
        "allowed_roles": allowed_roles,
        "allowed_units": allowed_units,
        "classification": classification,
        "status": "published",
        "valid_from": _valid_from(_date(version.get("effective_from"))),
        "valid_to": _valid_to(_date(version.get("effective_to"))),
        "page": 1,
        "section": chunk["heading"],
        "content_hash": digest,
        "embedding_model": embedding_model,
        "embedding_version": embedding_version,
        "sparse_model": "hashed-lexical",
        "sparse_version": "1",
        "index_version": collection,
        "document_number": document["document_number"],
        "title": document["title"],
        "article": chunk["section_number"],
        "clause": None,
        "point": None,
        "heading": chunk["heading"],
        "heading_path": [chunk["heading"]],
        "section_type": "article",
        "section_number": chunk["section_number"],
        "source_section_index": chunk_index,
        "source_url": None,
        "access_level": document["access_level"],
        "allowed_departments": document["allowed_departments"],
        "effective_from": version.get("effective_from"),
        "effective_to": version.get("effective_to"),
        "legal_status": version["legal_status"],
    }
    embedding_text = (
        f"{document['title']} | {document['document_number']} | {chunk['heading']}\n{text}"
    )
    return payload, embedding_text, digest


async def seed_regression_corpus(
    container: RAGContainer,
    fixture_path: str | Path,
) -> dict[str, Any]:
    source = Path(fixture_path).resolve()
    corpus = load_regression_corpus(source)
    tenant_id = str(corpus["tenant_id"])
    record_specs: list[tuple[str, str, dict[str, Any], str]] = []
    now = datetime.now(UTC).replace(tzinfo=None)

    with container.database.session_factory() as session:
        for document_data in corpus["documents"]:
            document = session.get(Document, document_data["id"])
            by_number = session.scalar(
                select(Document).where(Document.document_number == document_data["document_number"])
            )
            if by_number is not None and by_number.id != document_data["id"]:
                raise ValueError(
                    f"Reserved regression number already belongs to another id: {document_data['document_number']}"
                )
            if document is None:
                document = Document(id=document_data["id"])
                session.add(document)
            document.title = document_data["title"]
            document.document_number = document_data["document_number"]
            document.issued_by = "HUST RAG regression fixture"
            document.owner_department = document_data["owner_department"]
            document.access_level = document_data["access_level"]
            document.allowed_departments = document_data["allowed_departments"]
            document.source_url = None
            session.flush()

            version_data = document_data["version"]
            version = session.get(DocumentVersion, version_data["id"])
            checksum = hashlib.sha256(
                "\n".join(item["text"] for item in document_data["chunks"]).encode("utf-8")
            ).hexdigest()
            if version is None:
                version = DocumentVersion(id=version_data["id"], document_id=document.id)
                session.add(version)
            elif version.document_id != document.id:
                raise ValueError(f"Regression version belongs to another document: {version.id}")
            version.version_number = version_data["version_number"]
            version.issued_date = _date(version_data.get("issued_date"))
            version.effective_from = _date(version_data.get("effective_from"))
            version.effective_to = _date(version_data.get("effective_to"))
            version.legal_status = LegalStatus(version_data["legal_status"]).value
            version.processing_status = ProcessingStatus.PUBLISHED.value
            version.checksum = checksum
            version.source_filename = source.name
            version.source_path = str(source)
            version.metadata_json = {"dataset_kind": corpus["dataset_kind"], "tenant_id": tenant_id}
            version.approved_by = "regression-seed"
            version.approved_at = now
            version.published_at = now
            session.flush()

            expected_chunk_ids = {item["id"] for item in document_data["chunks"]}
            for existing in session.scalars(
                select(Chunk).where(Chunk.version_id == version.id)
            ).all():
                if existing.id not in expected_chunk_ids:
                    session.delete(existing)
            session.flush()

            expected_section_ids = {item["section_id"] for item in document_data["chunks"]}
            for existing in session.scalars(
                select(Section).where(Section.version_id == version.id)
            ).all():
                if existing.id not in expected_section_ids:
                    session.delete(existing)
            session.flush()

            chunks = document_data["chunks"]
            for index, chunk_data in enumerate(chunks):
                section = session.get(Section, chunk_data["section_id"])
                if section is None:
                    section = Section(id=chunk_data["section_id"], version_id=version.id)
                    session.add(section)
                elif section.version_id != version.id:
                    raise ValueError(f"Regression section belongs to another version: {section.id}")
                section.section_type = "article"
                section.section_number = chunk_data["section_number"]
                section.heading = chunk_data["heading"]
                section.heading_path = [chunk_data["heading"]]
                section.content = chunk_data["text"]
                section.sort_order = index

                payload, embedding_text, digest = _payload(
                    tenant_id=tenant_id,
                    collection=container.settings.qdrant_collection,
                    document=document_data,
                    version=version_data,
                    chunk=chunk_data,
                    chunk_index=index,
                    previous_chunk_id=chunks[index - 1]["id"] if index else None,
                    next_chunk_id=chunks[index + 1]["id"] if index + 1 < len(chunks) else None,
                    embedding_model=container.embeddings.model_name,
                    embedding_version=container.embeddings.model_version,
                )
                chunk = session.get(Chunk, chunk_data["id"])
                if chunk is None:
                    chunk = Chunk(id=chunk_data["id"], version_id=version.id)
                    session.add(chunk)
                elif chunk.version_id != version.id:
                    raise ValueError(f"Regression chunk belongs to another version: {chunk.id}")
                chunk.section_id = section.id
                chunk.chunk_index = index
                chunk.text = chunk_data["text"]
                chunk.embedding_text = embedding_text
                chunk.content_hash = digest
                chunk.metadata_json = payload
                chunk.indexed_at = now
                record_specs.append((chunk.id, embedding_text, payload, digest))

        session.commit()

    vectors = await container.embeddings.embed_documents(
        [item[1] for item in record_specs],
        content_hashes=[item[3] for item in record_specs],
    )
    await container.vector_store.upsert(
        [
            VectorRecord(id=chunk_id, vector=vector, payload=payload)
            for (chunk_id, _text, payload, _digest), vector in zip(
                record_specs,
                vectors,
                strict=True,
            )
        ]
    )
    return {
        "dataset_kind": corpus["dataset_kind"],
        "documents": len(corpus["documents"]),
        "chunks": len(record_specs),
        "vector_backend": container.settings.vector_backend,
        "collection": container.settings.qdrant_collection,
    }
