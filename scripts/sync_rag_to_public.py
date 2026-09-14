#!/usr/bin/env python3
"""Sync rag_legacy.* into public.* so hybrid_retrieval_service can find candidates.

Bridges the gap left by ``scripts/ingest_raw_pdfs.py`` (which writes only to
the RAG pipeline tables) and the chat retrieval service that reads from the
clean-architecture public schema.
"""
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path("/home/angwindy/P-234")
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env")
load_dotenv(PROJECT_ROOT / ".env.rag", override=True)

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

DB_URL = os.environ["DATABASE_URL"].replace(
    "postgresql://", "postgresql+psycopg://", 1
)


def sync_documents(eng: Engine) -> int:
    sql = text("""
        INSERT INTO public.documents (
            id, document_number, title,
            issued_by, issued_date, effective_date,
            legal_status, access_scope,
            created_at, updated_at
        )
        SELECT
            gen_random_uuid(),
            rd.document_number,
            rd.title,
            COALESCE(rd.issued_by, 'unknown'),
            COALESCE(rd.issued_date, CURRENT_DATE),
            COALESCE(rd.issued_date, CURRENT_DATE),
            'effective',
            CASE LOWER(COALESCE(rd.access_level, 'DEPARTMENT'))
                WHEN 'public' THEN 'PUBLIC'
                ELSE 'DEPARTMENT'
            END,
            COALESCE(rd.created_at, NOW()),
            NOW()
        FROM rag_legacy.documents rd
        WHERE NOT EXISTS (
            SELECT 1 FROM public.documents pd
            WHERE pd.document_number = rd.document_number
        )
    """)
    with eng.begin() as c:
        return c.execute(sql).rowcount


def sync_document_versions(eng: Engine) -> int:
    sql = text("""
        INSERT INTO public.document_versions (
            id, document_id, version_number,
            processing_status, checksum,
            source_filename, object_key,
            content_type, size_bytes,
            replaces_version_id, created_at
        )
        SELECT
            gen_random_uuid(),
            pd.id,
            rv.version_number,
            'published',
            COALESCE(rv.checksum, ''),
            COALESCE(rv.source_filename, ''),
            'hust/documents/' || pd.document_number || '/v' || rv.version_number || '/source.pdf',
            'application/pdf',
            COALESCE((rv.metadata_json->>'size_bytes')::bigint, 0),
            NULL,
            COALESCE(rv.created_at, NOW())
        FROM rag_legacy.document_versions rv
        JOIN rag_legacy.documents rd ON rd.id = rv.document_id
        JOIN public.documents pd ON pd.document_number = rd.document_number
        WHERE NOT EXISTS (
            SELECT 1 FROM public.document_versions pv
            WHERE pv.document_id = pd.id AND pv.version_number = rv.version_number
        )
    """)
    with eng.begin() as c:
        return c.execute(sql).rowcount


def sync_document_departments(eng: Engine) -> int:
    sql = text("""
        INSERT INTO public.document_departments (document_id, department_id)
        SELECT pd.id, dep.id
        FROM rag_legacy.documents rd
        JOIN public.documents pd ON pd.document_number = rd.document_number
        CROSS JOIN LATERAL jsonb_array_elements_text(
            COALESCE(rd.allowed_departments::jsonb, '[]'::jsonb)
        ) AS dept_code(code)
        JOIN public.departments dep ON dep.code = dept_code.code
        WHERE rd.access_level IN ('DEPARTMENT', 'department')
        ON CONFLICT DO NOTHING
    """)
    with eng.begin() as c:
        return c.execute(sql).rowcount


def sync_sections(eng: Engine) -> int:
    sql = text("""
        INSERT INTO public.document_sections (
            id, version_id, section_type,
            section_number, heading, heading_path,
            content, page, sort_order
        )
        SELECT
            gen_random_uuid(),
            pv.id,
            rs.section_type,
            rs.section_number,
            rs.heading,
            COALESCE(rs.heading_path, '[]'::json),
            rs.content,
            NULL,
            rs.sort_order
        FROM rag_legacy.sections rs
        JOIN rag_legacy.document_versions rv ON rv.id = rs.version_id
        JOIN rag_legacy.documents rd ON rd.id = rv.document_id
        JOIN public.documents pd ON pd.document_number = rd.document_number
        JOIN public.document_versions pv
          ON pv.document_id = pd.id AND pv.version_number = rv.version_number
        WHERE NOT EXISTS (
            SELECT 1 FROM public.document_sections ps
            WHERE ps.version_id = pv.id AND ps.sort_order = rs.sort_order
        )
    """)
    with eng.begin() as c:
        return c.execute(sql).rowcount


def sync_chunks(eng: Engine) -> int:
    sql = text("""
        INSERT INTO public.document_chunks (
            id, version_id, section_id,
            chunk_index, text, embedding_text,
            content_hash, metadata_json
        )
        SELECT
            rc.id::uuid,
            pv.id,
            ps.id,
            rc.chunk_index,
            rc.text,
            rc.embedding_text,
            COALESCE(rc.content_hash, ''),
            rc.metadata_json
        FROM rag_legacy.chunks rc
        JOIN rag_legacy.document_versions rv ON rv.id = rc.version_id
        JOIN rag_legacy.documents rd ON rd.id = rv.document_id
        JOIN public.documents pd ON pd.document_number = rd.document_number
        JOIN public.document_versions pv
          ON pv.document_id = pd.id AND pv.version_number = rv.version_number
        LEFT JOIN rag_legacy.sections rs ON rs.id::text = rc.section_id
        LEFT JOIN public.document_sections ps
          ON ps.version_id = pv.id AND ps.sort_order = rs.sort_order
        WHERE NOT EXISTS (
            SELECT 1 FROM public.document_chunks pc
            WHERE pc.version_id = pv.id AND pc.chunk_index = rc.chunk_index
        )
    """)
    with eng.begin() as c:
        return c.execute(sql).rowcount


def main() -> int:
    eng = create_engine(DB_URL)
    try:
        for label, fn in [
            ("documents", sync_documents),
            ("versions", sync_document_versions),
            ("document_departments", sync_document_departments),
            ("sections", sync_sections),
            ("chunks", sync_chunks),
        ]:
            n = fn(eng)
            print(f"  {label}: {n} inserted")
    finally:
        eng.dispose()
    return 0


if __name__ == "__main__":
    sys.exit(main())
