#!/usr/bin/env python3
"""Sync R2 objects to Neon database.

This script reads all PDF objects from Cloudflare R2 and creates
corresponding documents in Neon if they don't exist.

This ensures R2 and Neon stay in sync, especially after:
- Manual uploads to R2
- Failed seed scripts
- Database migrations

Usage:
    python scripts/sync_r2_to_neon.py [--dry-run]
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import logging
import re
import sys
from pathlib import Path
from uuid import UUID, uuid4

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env")

import boto3
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from src.config import get_settings
from src.infrastructure.storage.object_key import ObjectKeyBuilder


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("sync_r2_to_neon")


def _to_async_url(db_url: str) -> str:
    """Convert DATABASE_URL to async format."""
    if db_url.startswith("postgresql+psycopg://"):
        return db_url
    if db_url.startswith("postgresql://"):
        return db_url.replace("postgresql://", "postgresql+psycopg://", 1)
    return db_url


def _parse_object_key(key: str) -> dict | None:
    """Parse R2 object key to extract document info.
    
    Expected format: {tenant}/documents/{document_number}/v{version}/source.pdf
    Returns dict with tenant, document_number, version_number or None if invalid.
    """
    # Pattern: hust/documents/SEED-HUST-xxx/v1/source.pdf
    # or: huce/documents/SEED-HUCE-xxx/v1/source.pdf
    pattern = r"^(?P<tenant>hust|huce)/documents/(?P<doc_num>SEED-[A-Z]+-[^/]+)/v(?P<version>\d+)/source\.pdf$"
    match = re.match(pattern, key, re.IGNORECASE)
    if match:
        return {
            "tenant": match.group("tenant").upper(),
            "document_number": match.group("doc_num"),
            "version_number": int(match.group("version")),
        }
    return None


async def main_async(args: argparse.Namespace) -> int:
    settings = get_settings()
    
    # Setup R2 client
    r2_client = boto3.client(
        "s3",
        endpoint_url=settings.r2_endpoint,
        aws_access_key_id=settings.r2_access_key_id,
        aws_secret_access_key=settings.r2_secret_access_key,
        region_name="auto",
    )
    
    # Setup DB
    engine = create_async_engine(
        _to_async_url(settings.database_url),
        echo=False,
    )
    async_session = async_sessionmaker(engine, expire_on_commit=False)
    
    # List all R2 objects
    log.info("Fetching objects from R2 bucket: %s", settings.r2_bucket_name)
    
    all_objects = []
    continuation_token = None
    
    while True:
        kwargs = {"Bucket": settings.r2_bucket_name, "MaxKeys": 1000}
        if continuation_token:
            kwargs["ContinuationToken"] = continuation_token
        
        response = await asyncio.to_thread(r2_client.list_objects_v2, **kwargs)
        contents = response.get("Contents", [])
        all_objects.extend(contents)
        
        if not response.get("IsTruncated"):
            break
        continuation_token = response.get("NextContinuationToken")
    
    log.info("Found %d objects in R2", len(all_objects))
    
    # Filter to only PDF source files
    pdf_sources = [
        obj for obj in all_objects
        if obj["Key"].endswith("/source.pdf")
    ]
    log.info("Found %d source PDFs", len(pdf_sources))
    
    # Parse object keys
    parsed = []
    for obj in pdf_sources:
        info = _parse_object_key(obj["Key"])
        if info:
            info["key"] = obj["Key"]
            info["size"] = obj["Size"]
            info["etag"] = obj["ETag"].strip('"')
            parsed.append(info)
        else:
            log.warning("Skipping non-standard key: %s", obj["Key"])
    
    if not parsed:
        log.warning("No valid PDF sources found")
        return 0
    
    # Process each document
    inserted = 0
    skipped = 0
    failed = 0
    
    async with async_session() as session:
        for info in parsed:
            try:
                # Check if document exists
                result = await session.execute(
                    text("""
                        SELECT d.id, v.id 
                        FROM public.documents d
                        JOIN public.document_versions v ON v.document_id = d.id
                        WHERE d.document_number = :doc_num
                        LIMIT 1
                    """),
                    {"doc_num": info["document_number"]}
                )
                existing = result.fetchone()
                
                if existing:
                    log.info("SKIP %s (already exists)", info["document_number"])
                    skipped += 1
                    continue
                
                if args.dry_run:
                    log.info("DRY would insert: %s", info["document_number"])
                    continue
                
                # Create document and version
                document_id = uuid4()
                version_id = uuid4()
                
                # Map tenant to department
                school = info["tenant"]
                dept_result = await session.execute(
                    text("SELECT id FROM public.departments WHERE code = :code LIMIT 1"),
                    {"code": school}
                )
                dept_row = dept_result.fetchone()
                department_id = str(dept_row[0]) if dept_row else None
                
                access_scope = "DEPARTMENT" if department_id else "PUBLIC"
                legal_status = "draft"
                processing_status = "received"
                
                # Insert document
                await session.execute(
                    text("""
                        INSERT INTO public.documents (
                            id, document_number, title, issued_by,
                            issued_date, effective_date, legal_status,
                            access_scope, created_at, updated_at
                        ) VALUES (
                            :id, :doc_num, :title, :issued_by,
                            '2026-01-01', '2026-01-01', :legal_status,
                            :access_scope, NOW(), NULL
                        )
                    """),
                    {
                        "id": str(document_id),
                        "doc_num": info["document_number"],
                        "title": info["document_number"].replace("-", " ")[:200],
                        "issued_by": school,
                        "legal_status": legal_status,
                        "access_scope": access_scope,
                    }
                )
                
                # Insert version
                await session.execute(
                    text("""
                        INSERT INTO public.document_versions (
                            id, document_id, version_number,
                            processing_status, checksum, source_filename,
                            object_key, content_type, size_bytes,
                            replaces_version_id, created_at
                        ) VALUES (
                            :id, :doc_id, :version,
                            :processing_status, :checksum,
                            'source.pdf', :object_key,
                            'application/pdf', :size_bytes,
                            NULL, NOW()
                        )
                    """),
                    {
                        "id": str(version_id),
                        "doc_id": str(document_id),
                        "version": info["version_number"],
                        "processing_status": processing_status,
                        "checksum": info["etag"],
                        "object_key": info["key"],
                        "size_bytes": info["size"],
                    }
                )
                
                # Link to department if applicable
                if department_id:
                    await session.execute(
                        text("""
                            INSERT INTO public.document_departments (
                                document_id, department_id
                            ) VALUES (
                                :doc_id, :dept_id
                            ) ON CONFLICT DO NOTHING
                        """),
                        {
                            "doc_id": str(document_id),
                            "dept_id": department_id,
                        }
                    )
                
                await session.commit()
                log.info("INSERTED %s -> %s", info["document_number"], info["key"])
                inserted += 1
                
            except Exception as exc:
                await session.rollback()
                log.error("FAILED %s: %s", info["document_number"], exc)
                failed += 1
    
    log.info("Done. inserted=%d, skipped=%d, failed=%d", inserted, skipped, failed)
    await engine.dispose()
    
    return 0 if failed == 0 else 1


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Sync R2 objects to Neon database"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without making changes",
    )
    args = parser.parse_args()
    
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    sys.exit(main())
