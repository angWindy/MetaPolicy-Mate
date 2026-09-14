#!/usr/bin/env python3
"""Re-index all documents to populate missing citation metadata.

This script fixes Qdrant payloads that are missing:
- title
- document_number  
- source_url

Usage:
    python scripts/reindex_all_docs.py [--dry-run]
"""
import argparse
import asyncio
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env")
load_dotenv(PROJECT_ROOT / ".env.rag", override=True)

import httpx
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from src.config import get_settings


async def get_all_version_ids():
    """Get all document version IDs from the database."""
    settings = get_settings()
    engine = create_async_engine(settings.database_url, echo=False)
    async_session = async_sessionmaker(engine, expire_on_commit=False)
    
    async with async_session() as session:
        result = await session.execute(
            text("""
                SELECT dv.id, dv.version_id, d.document_number, d.title
                FROM public.document_versions dv
                JOIN public.documents d ON d.id = dv.document_id
                ORDER BY dv.created_at DESC
            """)
        )
        return list(result.fetchall())


async def reindex_version(version_id: str, dry_run: bool = False):
    """Re-index a document version via the API."""
    if dry_run:
        print(f"  [DRY-RUN] Would re-index {version_id}")
        return True
    
    async with httpx.AsyncClient(timeout=120) as client:
        # Login first
        login_resp = await client.post(
            "http://localhost:8000/api/v1/auth/login",
            json={
                "email": "admin@p234.demo",
                "password": "P234@123",
                "device_id": "reindex-script"
            }
        )
        if login_resp.status_code != 200:
            print(f"  ✗ Login failed: {login_resp.status_code}")
            return False
        
        token = login_resp.json()["access_token"]
        
        # Call reindex endpoint
        resp = await client.post(
            f"http://localhost:8000/api/v1/admin/documents/{version_id}/index",
            headers={"Authorization": f"Bearer {token}"}
        )
        
        if resp.status_code == 200:
            print(f"  ✓ Re-indexed {version_id}")
            return True
        else:
            print(f"  ✗ Failed: {resp.status_code} - {resp.text[:100]}")
            return False


async def main():
    parser = argparse.ArgumentParser(description="Re-index all documents")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be done")
    args = parser.parse_args()
    
    print("Fetching document versions...")
    versions = await get_all_version_ids()
    print(f"Found {len(versions)} document versions\n")
    
    for row in versions:
        version_id = row[0]  # First column is dv.id
        doc_num = row[2] if len(row) > 2 else "?"
        title = row[3][:40] if len(row) > 3 and row[3] else "?"
        print(f"Document: {doc_num} - {title}...")
        await reindex_version(str(version_id), dry_run=args.dry_run)
    
    print("\nDone!")


if __name__ == "__main__":
    asyncio.run(main())
