import argparse
import asyncio
import json
from pathlib import Path

from src.domain.schemas import DocumentMetadata
from src.rag.container import get_rag_container


async def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest one HUST regulation document")
    parser.add_argument("file", type=Path)
    parser.add_argument("--metadata", required=True, type=Path)
    args = parser.parse_args()

    metadata = DocumentMetadata.model_validate(json.loads(args.metadata.read_text(encoding="utf-8")))
    result = await get_rag_container().ingestion.ingest(
        args.file.name,
        args.file.read_bytes(),
        metadata,
    )
    print(result.model_dump_json(indent=2))


if __name__ == "__main__":
    asyncio.run(main())
