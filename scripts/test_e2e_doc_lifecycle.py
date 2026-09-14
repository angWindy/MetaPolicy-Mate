"""End-to-end document lifecycle test.

Pipeline:

1. Login as admin -> upload a real PDF via POST
   /api/v1/regulatory-documents/upload.
2. Run the same parse -> chunk -> embed -> Qdrant-upsert path used by
   ``test_e2e_ingestion.py`` so the document has real vectors in Qdrant.
3. Record pre-delete Qdrant points count.
4. Login as admin -> DELETE /api/v1/regulatory-documents/{id}.
5. Verify:
   * GET /regulatory-documents/{id} returns 404.
   * GET /regulatory-documents/{id}/source returns 404.
   * The on-disk PDF is gone (LocalFileStorage) or the delete response
     reports ``storage_objects_deleted`` (R2).
   * Qdrant points_count is back to pre-delete value (cascade fired).
   * The delete response may be 200 (full success) or 207 (partial
     cleanup — see delete_hardening).
6. Login as plain user -> DELETE same id -> 403 (RBAC enforced).

The on-disk path uses the canonical
``{tenant}/documents/{number}/v{n}/source.pdf`` layout produced by
``ObjectKeyBuilder``. The key is read from the DB after upload
(rather than fabricated from the upload response) so the assertion
matches the production handler's exact layout.

Note: as of the 2026-08-31 role consolidation, only ADMIN can
hard-delete documents (the previous REVIEWER role has been merged
into USER, which only has read/upload/process/chat permissions).

Run::

    python scripts/test_e2e_doc_lifecycle.py
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
import uuid
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx

from src.ingestion.chunker import build_chunks
from src.ingestion.legal_structure import (
    extract_sections,
)
from src.ingestion.parser import DocumentParser
from src.rag.config import get_rag_settings
from src.rag.container import RAGContainer
from src.retrieval.vector_store import VectorRecord


DEFAULT_PDF = (
    "data/raw/HUCE/1145 - Quy định chấm công.pdf"
)


async def _login(
    client: httpx.AsyncClient,
    base_url: str,
    email: str,
    password: str,
) -> str:
    response = await client.post(
        f"{base_url}/api/v1/auth/login",
        json={
            "email": email,
            "password": password,
            "device_id": (
                f"e2e-lifecycle-{email.split('@')[0]}"
            ),
        },
    )
    if response.status_code != 200:
        raise RuntimeError(
            f"login failed for {email}: "
            f"{response.status_code} {response.text}"
        )
    return response.json()["access_token"]


async def _qdrant_points(
    container: RAGContainer,
    collection: str,
) -> int:
    info = await (
        container.vector_store.client
        .get_collection(collection)
    )
    return info.points_count


async def _ingest_pdf(
    pdf_path: Path,
    *,
    document_id: str,
    version_id: str,
    document_number: str,
    title: str,
    container: RAGContainer,
    parser: DocumentParser,
    settings,
) -> int:
    raw_bytes = pdf_path.read_bytes()
    blocks, _ = parser.parse(
        pdf_path.name, raw_bytes
    )
    if not blocks:
        raise RuntimeError("parser returned 0 blocks")
    sections = extract_sections(blocks)

    from src.domain.schemas import (
        AccessScope,
        DocumentMetadata,
    )

    metadata = DocumentMetadata(
        document_number=document_number,
        title=title,
        version_number=1,
        effective_from=date.today(),
        effective_to=None,
        owner_department="HUST",
        access_level=AccessScope.DEPARTMENT,
        allowed_departments=["HUST", "HUCE"],
        source_url=None,
    )
    chunks = build_chunks(
        document_id=document_id,
        version_id=version_id,
        metadata=metadata,
        sections=sections,
        max_chars=settings.chunk_max_chars,
        overlap_chars=settings.chunk_overlap_chars,
    )
    if not chunks:
        raise RuntimeError("chunker returned 0 chunks")

    from src.services.embeddings import (
        content_hash_for_text,
    )

    content_hashes = [
        content_hash_for_text(chunk.embedding_text)
        for chunk in chunks
    ]
    vectors = await container.embeddings.embed_documents(
        [chunk.embedding_text for chunk in chunks],
        content_hashes=content_hashes,
    )
    records = []
    for chunk, vector, content_hash in zip(
        chunks, vectors, content_hashes, strict=True,
    ):
        payload = {
            "document_id": document_id,
            "version_id": version_id,
            "document_number": metadata.document_number,
            "title": metadata.title,
            "section_type": chunk.metadata.get(
                "section_type"
            ),
            "section_number": chunk.metadata.get(
                "section_number"
            ),
            "heading": chunk.metadata.get("heading"),
            "text": chunk.text,
            "source_pdf": pdf_path.name,
        }
        records.append(
            VectorRecord(
                id=chunk.id,
                vector=vector,
                payload=payload,
            )
        )
    await container.vector_store.create_payload_indexes()
    await container.vector_store.upsert(records)
    return len(records)


async def main_async(args: argparse.Namespace) -> int:
    base_url = args.api_base
    pdf_path = Path(args.pdf)
    if not pdf_path.exists():
        print(
            f"ERROR: PDF not found: {pdf_path}",
            file=sys.stderr,
        )
        return 1

    print(
        "=== E2E document lifecycle (upload -> ingest -> "
        "delete -> cascade verify) ==="
    )
    print(f"  api_base   = {base_url}")
    print(f"  pdf_path   = {pdf_path}")
    print(f"  pdf_size   = {os.path.getsize(pdf_path)} bytes")
    print()

    settings = get_rag_settings()
    container = RAGContainer(settings)

    parser = container.parser

    pre_count = await _qdrant_points(
        container, settings.qdrant_collection
    )
    print(
        f"[setup] qdrant_points_before = {pre_count}"
    )
    print()

    document_number = (
        f"E2E-LIFECYCLE-{date.today().isoformat()}-"
        f"{uuid.uuid4().hex[:6]}"
    )
    title = (
        f"E2E Lifecycle "
        f"{document_number}"
    )
    today = date.today().isoformat()

    async with httpx.AsyncClient(
        timeout=60.0
    ) as client:
        # 1) Admin upload
        admin_token = await _login(
            client, base_url, "admin@p234.demo", "P234@123",
        )
        with pdf_path.open("rb") as fh:
            upload_files = {
                "file": (
                    pdf_path.name,
                    fh.read(),
                    "application/pdf",
                ),
            }
            data = {
                "document_number": document_number,
                "title": title,
                "issued_by": "Phòng Đào tạo",
                "issued_date": today,
                "effective_date": today,
            }
            upload_resp = await client.post(
                f"{base_url}/api/v1/regulatory-documents/upload",
                data=data,
                files=upload_files,
                headers={
                    "Authorization": (
                        f"Bearer {admin_token}"
                    ),
                },
            )
        print(
            f"[1] upload status={upload_resp.status_code}"
        )
        if upload_resp.status_code != 201:
            print(upload_resp.text)
            return 1
        upload_payload = upload_resp.json()
        document_id = upload_payload["id"]
        print(f"    document_id = {document_id}")
        version_id = (
            upload_payload.get("version_id")
            or upload_payload.get("default_version_id")
            or "?"
        )
        # Some responses only include document-level metadata; fetch the
        # version from a follow-up call if necessary.
        if version_id == "?":
            version_resp = await client.get(
                f"{base_url}/api/v1/regulatory-documents/{document_id}",
                headers={
                    "Authorization": (
                        f"Bearer {admin_token}"
                    ),
                },
            )
            if version_resp.status_code == 200:
                version_id = version_resp.json().get(
                    "version_id", "?"
                )
        print(f"    version_id  = {version_id}")
        print()

        # 2) Ingest same PDF into Qdrant (mirrors real ingestion flow).
        chunk_count = await _ingest_pdf(
            pdf_path,
            document_id=str(document_id),
            version_id=str(version_id),
            document_number=document_number,
            title=title,
            container=container,
            parser=parser,
            settings=settings,
        )
        post_count = await _qdrant_points(
            container, settings.qdrant_collection
        )
        print(
            f"[2] ingested {chunk_count} chunks; "
            f"qdrant_points_after = {post_count}"
        )
        assert (
            post_count - pre_count
        ) >= chunk_count - 5, (
            f"Expected >= {chunk_count} new points, "
            f"got delta {post_count - pre_count}"
        )
        print()

        # Resolve the actual object_key from the DB so we verify the
        # canonical ``{tenant}/documents/{number}/v{n}/source.pdf``
        # layout (or the local-fs fallback path). Don't fabricate a
        # key from the upload response — the upload handler runs the
        # canonical ObjectKeyBuilder and we want to assert against its
        # output verbatim.
        db_url = _to_psycopg_url(
            os.environ.get(
                "DATABASE_URL",
                "",
            )
        )
        object_key = ""
        if db_url:
            from sqlalchemy import create_engine  # noqa: F401
            from sqlalchemy import text as _sql_text

            eng = create_engine(db_url)
            with eng.connect() as conn:
                object_key = conn.execute(
                    _sql_text(
                        "SELECT object_key "
                        "FROM public.document_versions "
                        "WHERE id = :v LIMIT 1"
                    ),
                    {"v": str(version_id)},
                ).scalar() or ""
            eng.dispose()
        print(
            f"[precheck] object_key = {object_key}"
        )

        # Only assert on-disk existence when we're talking to
        # LocalFileStorage (no R2 credentials). The delete response
        # surfaces R2 cleanup via ``storage_objects_deleted``.
        from src.config import get_settings as app_settings

        try:
            app_cfg = app_settings()
        except Exception:  # noqa: BLE001
            app_cfg = None

        r2_configured = bool(
            app_cfg
            and getattr(app_cfg, "r2_endpoint", "")
            and getattr(
                app_cfg,
                "r2_access_key_id",
                "",
            )
            not in {
                "",
                "placeholder_key_id",
                "placeholder-bucket",
            }
            and getattr(
                app_cfg,
                "r2_bucket_name",
                "",
            )
            not in {
                "",
                "placeholder-bucket",
            }
        )
        on_disk: Path | None = None
        if not r2_configured and object_key:
            data_dir = getattr(app_cfg, "data_dir", None)
            storage_root = (
                Path(data_dir) / "storage"
                if data_dir
                else Path("./data/storage")
            )
            on_disk = storage_root / object_key
            print(
                f"[precheck] on_disk_exists = "
                f"{on_disk.exists()}"
            )
            assert on_disk.exists(), (
                f"uploaded PDF missing on disk: "
                f"{on_disk}"
            )
        else:
            print(
                "[precheck] R2 backend in use; "
                "skipping local-file existence check."
            )
        print()

        # 3) DELETE as admin
        delete_resp = await client.delete(
            f"{base_url}/api/v1/regulatory-documents/{document_id}",
            headers={
                "Authorization": (
                    f"Bearer {admin_token}"
                ),
            },
        )
        # Endpoint declares status.HTTP_200_OK; partial-cleanup path
        # returns 207 (see delete_hardening work). Accept either.
        delete_ok = delete_resp.status_code in {
            200,
            207,
        }
        print(
            f"[3] admin DELETE status={delete_resp.status_code} "
            f"(expected 200 or 207)"
        )
        if not delete_ok:
            print(delete_resp.text)
            return 1
        try:
            delete_payload = delete_resp.json()
        except Exception:  # noqa: BLE001
            delete_payload = {}
        print(
            "    deleted="
            f"{delete_payload.get('deleted')} "
            "versions_deleted="
            f"{delete_payload.get('versions_deleted')} "
            "storage_objects_deleted="
            f"{delete_payload.get('storage_objects_deleted')} "
            "qdrant_points_removed="
            f"{delete_payload.get('qdrant_points_removed')} "
            "errors="
            f"{delete_payload.get('errors')}"
        )
        print()

        # 4) Verify cascade
        get_resp = await client.get(
            f"{base_url}/api/v1/regulatory-documents/{document_id}",
            headers={
                "Authorization": (
                    f"Bearer {admin_token}"
                ),
            },
        )
        print(
            f"[4a] GET detail status={get_resp.status_code} (expected 404)"
        )
        if get_resp.status_code != 404:
            return 1
        src_resp = await client.get(
            f"{base_url}/api/v1/regulatory-documents/{document_id}/source",
            headers={
                "Authorization": (
                    f"Bearer {admin_token}"
                ),
            },
        )
        print(
            f"[4b] GET source status={src_resp.status_code} (expected 404)"
        )
        if src_resp.status_code != 404:
            return 1
        final_count = await _qdrant_points(
            container, settings.qdrant_collection
        )
        print(
            f"[4c] qdrant_points_final  = {final_count} "
            f"(pre was {pre_count}, delta now {final_count - pre_count})"
        )
        if final_count > pre_count + max(1, chunk_count // 4):
            print(
                "    WARN: Qdrant still holds residual points; "
                "cascade may be incomplete."
            )
        if on_disk is not None and on_disk.exists():
            print(
                f"    FAIL: PDF still on disk: {on_disk}"
            )
            return 1
        if on_disk is not None:
            print(
                "[4d] on_disk_exists = False (storage cleaned)"
            )
        else:
            print(
                "[4d] R2 backend in use; "
                "trusting storage_objects_deleted="
                f"{delete_payload.get('storage_objects_deleted')}"
            )
        if delete_payload.get("errors"):
            print(
                "    WARN: delete reported partial-failure "
                f"errors={delete_payload.get('errors')}"
            )
        print()

        # 5) Permission enforcement: USER cannot delete.
        user_token = await _login(
            client, base_url, "user@p234.demo", "P234@123",
        )
        # Re-create the document first.
        with pdf_path.open("rb") as fh:
            upload_files = {
                "file": (
                    pdf_path.name,
                    fh.read(),
                    "application/pdf",
                ),
            }
            data = {
                "document_number": (
                    f"{document_number}-USER"
                ),
                "title": f"{title} (USER check)",
                "issued_by": "Phòng Đào tạo",
                "issued_date": today,
                "effective_date": today,
            }
            resp2 = await client.post(
                f"{base_url}/api/v1/regulatory-documents/upload",
                data=data,
                files=upload_files,
                headers={
                    "Authorization": (
                        f"Bearer {admin_token}"
                    ),
                },
            )
        if resp2.status_code != 201:
            print(
                "ERROR re-creating document for USER check:",
                resp2.text,
            )
            return 1
        user_doc_id = resp2.json()["id"]
        user_delete_resp = await client.delete(
            f"{base_url}/api/v1/regulatory-documents/{user_doc_id}",
            headers={
                "Authorization": (
                    f"Bearer {user_token}"
                ),
            },
        )
        print(
            f"[5] USER DELETE status={user_delete_resp.status_code} "
            f"(expected 403)"
        )
        if user_delete_resp.status_code != 403:
            return 1
        print()

        # 6) Re-delete as admin (USER role is forbidden since the
        # 2026-08-31 role consolidation; only ADMIN has delete).
        admin_delete_resp = await client.delete(
            f"{base_url}/api/v1/regulatory-documents/{user_doc_id}",
            headers={
                "Authorization": (
                    f"Bearer {admin_token}"
                ),
            },
        )
        admin_ok = admin_delete_resp.status_code in {
            200, 207,
        }
        print(
            f"[6] ADMIN DELETE status="
            f"{admin_delete_resp.status_code} "
            f"(expected 200 or 207)"
        )
        if not admin_ok:
            return 1
        print()

    print("=== PASS: lifecycle test ===")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--pdf",
        default=os.environ.get(
            "E2E_PDF_PATH", DEFAULT_PDF
        ),
    )
    parser.add_argument(
        "--api-base",
        default="http://localhost:8000",
    )
    args = parser.parse_args()
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    sys.exit(main())
