"""Search authoritative PostgreSQL chunks while curating RAG eval cases."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from dotenv import dotenv_values
from sqlalchemy import create_engine, text

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _database_url() -> str:
    values = {
        **dotenv_values(PROJECT_ROOT / ".env.rag"),
        **dotenv_values(PROJECT_ROOT / ".env"),
    }
    value = str(values.get("DATABASE_URL") or "")
    if not value:
        raise RuntimeError("DATABASE_URL is not configured.")
    return value.replace(
        "postgresql+asyncpg://", "postgresql+psycopg://", 1
    ).replace("postgresql://", "postgresql+psycopg://", 1)


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("--document")
    parser.add_argument("--needle", default="")
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--documents", action="store_true")
    args = parser.parse_args()
    engine = create_engine(_database_url(), future=True, pool_pre_ping=True)
    statement = text(
        """
        SELECT c.id::text AS chunk_id, c.chunk_index, d.document_number,
               d.title, c.text
        FROM public.document_chunks AS c
        JOIN public.document_versions AS v ON v.id = c.version_id
        JOIN public.documents AS d ON d.id = v.document_id
        WHERE lower(v.processing_status) = 'published'
          AND (:document = '' OR d.document_number ILIKE :document_pattern)
          AND (:needle = '' OR c.text ILIKE :needle_pattern)
        ORDER BY d.document_number, c.chunk_index
        LIMIT :limit
        """
    )
    document_statement = text(
        """
        SELECT d.document_number, d.title, count(c.id) AS chunk_count
        FROM public.documents AS d
        JOIN public.document_versions AS v ON v.document_id = d.id
        JOIN public.document_chunks AS c ON c.version_id = v.id
        WHERE lower(v.processing_status) = 'published'
        GROUP BY d.document_number, d.title
        ORDER BY d.document_number
        """
    )
    try:
        with engine.connect() as connection:
            if args.documents:
                rows = connection.execute(document_statement).mappings().all()
            else:
                rows = connection.execute(
                    statement,
                    {
                        "document": args.document or "",
                        "document_pattern": f"%{args.document or ''}%",
                        "needle": args.needle,
                        "needle_pattern": f"%{args.needle}%",
                        "limit": args.limit,
                    },
                ).mappings().all()
    finally:
        engine.dispose()
    payload = [dict(row) for row in rows]
    rendered = json.dumps(payload, ensure_ascii=False, indent=2)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(rendered + "\n", encoding="utf-8")
    else:
        print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
