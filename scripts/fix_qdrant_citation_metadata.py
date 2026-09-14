#!/usr/bin/env python3
"""Fix Qdrant payloads by adding missing citation metadata.

This script updates existing Qdrant points to include:
- title
- document_number

These fields are required for citation validation but were missing
from the original indexing.

Usage:
    python scripts/fix_qdrant_citation_metadata.py
"""
import asyncio
import sys
from pathlib import Path
from uuid import UUID

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env")
load_dotenv(PROJECT_ROOT / ".env.rag", override=True)

from qdrant_client import QdrantClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from src.config import get_settings


async def get_document_metadata():
    """Get document_number and title for all documents."""
    from src.rag.config import get_rag_settings
    
    rag_settings = get_rag_settings()
    db_url = rag_settings.database_url
    
    # Convert to async URL format if needed
    if db_url.startswith("postgresql://"):
        db_url = db_url.replace("postgresql://", "postgresql+psycopg://", 1)
    elif db_url.startswith("postgresql+psycopg2://"):
        db_url = db_url.replace("postgresql+psycopg2://", "postgresql+psycopg://", 1)
    
    engine = create_async_engine(db_url, echo=False)
    async_session = async_sessionmaker(engine, expire_on_commit=False)
    
    doc_metadata = {}
    async with async_session() as session:
        result = await session.execute(
            text("""
                SELECT id::text, document_number, title
                FROM public.documents
            """)
        )
        for row in result.fetchall():
            doc_id, doc_num, title = row
            doc_metadata[doc_id] = {
                "document_number": doc_num,
                "title": title
            }
    
    await engine.dispose()
    return doc_metadata


async def update_qdrant_payloads():
    """Update Qdrant payloads with missing metadata."""
    from src.rag.config import get_rag_settings
    
    rag_settings = get_rag_settings()
    
    # Initialize Qdrant client
    client = QdrantClient(
        url=rag_settings.qdrant_url,
        api_key=rag_settings.qdrant_api_key
    )
    
    collection = rag_settings.qdrant_collection
    
    # Get document metadata from database
    print("Fetching document metadata from database...")
    doc_metadata = await get_document_metadata()
    print(f"Found metadata for {len(doc_metadata)} documents\n")
    
    # Get all points from Qdrant
    print(f"Fetching points from Qdrant collection '{collection}'...")
    results = client.scroll(
        collection_name=collection,
        limit=100,
        with_payload=True,
        with_vectors=False
    )
    
    points = results[0]
    print(f"Found {len(points)} points\n")
    
    # Track updates needed
    updates_by_doc = {}
    for point in points:
        payload = point.payload or {}
        doc_id = payload.get("document_id")
        
        if doc_id in doc_metadata:
            if doc_id not in updates_by_doc:
                updates_by_doc[doc_id] = {
                    "metadata": doc_metadata[doc_id],
                    "point_ids": []
                }
            updates_by_doc[doc_id]["point_ids"].append(point.id)
    
    # Apply updates
    total_updated = 0
    for doc_id, info in updates_by_doc.items():
        metadata = info["metadata"]
        point_ids = info["point_ids"]
        
        print(f"Updating {len(point_ids)} points for document {doc_id}...")
        print(f"  Title: {metadata['title'][:50]}...")
        print(f"  Number: {metadata['document_number']}")
        
        # Update payload
        from qdrant_client.models import PointIdsList, SetPayload
        
        client.set_payload(
            collection_name=collection,
            payload={
                "title": metadata["title"],
                "document_number": metadata["document_number"]
            },
            points=PointIdsList(points=point_ids),
            wait=True
        )
        total_updated += len(point_ids)
        print(f"  ✓ Updated {len(point_ids)} points\n")
    
    print(f"Done! Updated {total_updated} points total.")


if __name__ == "__main__":
    asyncio.run(update_qdrant_payloads())
